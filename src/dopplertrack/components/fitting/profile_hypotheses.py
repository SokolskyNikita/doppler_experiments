"""Each event's hypotheses instead of independent speed, distance and f0 gates (PLAN Phase 2, item 7, stage B).

An event's hypotheses are up to K optima from each of two sources:
- "ls": the least-squares fit of ridge()'s track (tracks.fit_track), when it says identified. It is the
  better estimator when the track stays on the pass, and item 4 showed the track sometimes doesn't;
- "fit_event": fit_event's optima, from its coarse grid's best emission-CPA times, each refined.

Each optimum gets a region from profiles (Raue 2009): for each of v, k = v^2/d (which the steep middle of a pass
pins even when v and d separately aren't, PLAN 6.1), tau (emission CPA) and f0, the range over which the
objective, re-optimised over the other parameters, stays within a threshold of the optimum:
- for "ls", the track's residual sum of squares within LS_DCHI2 times its residual variance;
- for "fit_event", the brightness under the ideal curve (EventWindow.curve_score, the scale of the event's
  null, pipeline.event_null) within NULL_DELTA null sigmas.
They are sensitivity ranges, not confidence intervals: neither objective is a calibrated likelihood. A range
that runs into its bound before the objective falls off is flagged weak (flat or one-sided) and widened to the
bound. Optima from the two sources at nearly the same place (each inside the other's v, k and tau ranges) merge
into one hypothesis with the wider ranges.

A CPA row (grid point, flight) is admitted for an event if some hypothesis holds both its speed and its
v^2/d: each candidate flight's own ground speed gives the distance it implies."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.detection.grid_scan import EventFit, Track, fit_event, fit_track, grid_search, local_whiten, ridge_track

K = 3                       # optima kept per source
LS_DCHI2 = 3.84 * 3.0       # chi2(1, 0.95) times the variance inflation of 88 %-overlapping frames (about 3, from
                            # the model-error study's c(r)^2 frame-correlation model, docs/experiments/2026-11-04-model-error.md)
NULL_DELTA = 2.0            # brightness threshold, in the event's null sigma
MODEL_ERROR_FACTOR = 3.0    # both thresholds are multiplied by its square: a misspecified model's profile measures
                            # spread about its best approximation, not distance to the truth (White 1982), and the model-error study
                            # measured that distance at 2.8-3.2x the information bound in slant range on Livermore
                            # (docs/experiments/2026-11-04-model-error.md). The one counted retune of stage B.
MIN_SEP_S = 20.0            # fit_event optima: distinct emission-CPA times at least this far apart
V_BOUNDS = (10.0, 300.0)
D_BOUNDS = (100.0, 30000.0)
K_BOUNDS = (V_BOUNDS[0] ** 2 / D_BOUNDS[1], V_BOUNDS[1] ** 2 / D_BOUNDS[0])
TAU_REACH_S = 60.0          # tau profiles stop this far from the optimum
COARSE_V = np.arange(40, 170, 13.0)          # detect_events' coarse scan grid, where fit_event's optima start
COARSE_D = np.geomspace(400, 9000, 10)


@dataclass
class Hypothesis:
    """One optimum of one event's fit with the region it supports."""
    sources: list
    f0: float
    v: float
    d: float
    t_cpa_emit: float
    t_cpa: float
    v_range: tuple
    k_range: tuple
    tau_range: tuple
    f0_range: tuple
    weak: list = field(default_factory=list)      # parameters whose profile was flat or one-sided
    corr_v_d: float | None = None                 # speed-distance correlation, where the source gives one
    identified: bool | None = None                # fit_track's own verdict, for "ls"
    d_range: tuple | None = None                  # "gate" only: admits by today's distance box instead of k

    @property
    def k(self) -> float:
        return self.v * self.v / self.d

    def admits(self, cpa: pd.DataFrame) -> np.ndarray:
        v = cpa.v.to_numpy(np.float64)
        d = cpa.d.to_numpy(np.float64)
        in_v = (v >= self.v_range[0]) & (v <= self.v_range[1])
        if self.d_range is not None:
            return in_v & (d >= self.d_range[0]) & (d <= self.d_range[1])
        k = v * v / d
        return in_v & (k >= self.k_range[0]) & (k <= self.k_range[1])

    def contains(self, other: "Hypothesis") -> bool:
        return (self.v_range[0] <= other.v <= self.v_range[1] and self.k_range[0] <= other.k <= self.k_range[1]
                and self.tau_range[0] <= other.t_cpa_emit <= self.tau_range[1])

    def event(self, like: EventFit) -> EventFit:
        c = self.d / (self.t_cpa - self.t_cpa_emit) if self.t_cpa > self.t_cpa_emit else 343.0
        return EventFit(t_cpa=self.t_cpa, t_cpa_emit=self.t_cpa_emit, f0=self.f0, v=self.v, d=self.d,
                        t_start=like.t_start, t_end=like.t_end, score=like.score,
                        f_pre=self.f0 * c / (c - self.v), f_post=self.f0 * c / (c + self.v))

    def to_dict(self):
        return asdict(self)


def admitted(cpa: pd.DataFrame, hyps: list[Hypothesis]) -> np.ndarray:
    """Rows of the CPA table some hypothesis admits."""
    mask = np.zeros(len(cpa), bool)
    for h in hyps:
        mask |= h.admits(cpa)
    return mask


# ---- objectives over theta = (f0, v, d, tau) -----------------------------------------------------------------

def _ls_objective(track: Track, c: float):
    t, g, a = track.usable()
    w = np.ones_like(g)

    def rss(theta):
        f0, v, d, tau = theta
        if not (0 < v < c and d > 0 and f0 > 0):
            return np.inf
        al = f0 * c * c / (c * c - v * v)
        be = -f0 * c * v / (c * c - v * v)
        s = d * np.sqrt(c * c - v * v) / (v * c)
        z = (t - tau) / np.sqrt(s * s + (t - tau) ** 2)
        return float((w * (g - al - be * z) ** 2).sum())
    return rss, len(t)


def closed_form_ratio(t, v, d, tau, c):
    """f/f0 heard at times t from a straight pass (Ferguson & Quinn 1994, eq. 15): exact, unlike ideal_curve's
    interpolated table, and cheap enough for profiles."""
    u = t - tau
    return c * c / (c * c - v * v) * (1 - v * v * u / np.sqrt(d * d * (c * c - v * v) + v * v * c * c * u * u))


def _brightness_objective(w, c: float):
    """Minus the brightness under the ideal curve over the event's fit window, sampled where curve_score samples."""
    to = np.linspace(w.fit.t_start, w.fit.t_end, 160)

    def neg(theta):
        f0, v, d, tau = theta
        if not (0 < v < c and d > 0 and f0 > 0):
            return np.inf
        return -w.curve_score(to, closed_form_ratio(to, v, d, tau, c), f0 / w.fit.f0)
    return neg


# ---- profiles ---------------------------------------------------------------------------------------------------

_FREE = {"v": (0, 2, 3), "k": (0, 1, 3), "tau": (0, 1, 2), "f0": (1, 2, 3)}


def _theta(which: str, value: float, x: np.ndarray, base: np.ndarray) -> np.ndarray:
    th = base.copy()
    free = _FREE[which]
    for i, xi in zip(free, x):
        th[i] = np.exp(xi) if i in (1, 2) else xi
    if which == "v":
        th[1] = value
    elif which == "k":
        th[2] = th[1] ** 2 / value
    elif which == "tau":
        th[3] = value
    else:
        th[0] = value
    return th


def _x0(which: str, theta: np.ndarray) -> np.ndarray:
    return np.array([np.log(theta[i]) if i in (1, 2) else theta[i] for i in _FREE[which]])


def _profile_value(obj, which, value, theta_opt, x_start):
    r = minimize(lambda x: obj(_theta(which, value, x, theta_opt)), x_start, method="Nelder-Mead",
                 options={"maxiter": 80, "xatol": 1e-3, "fatol": 1e-9})
    return float(r.fun), r.x


def profile_range(obj, theta_opt: np.ndarray, which: str, threshold: float, bounds: tuple) -> tuple[float, float, bool]:
    """(lo, hi, weak): the range of one parameter (v, k, tau or f0) over which obj, re-optimised over the others,
    stays within threshold of its value at theta_opt. A side that reaches its bound first is weak and is set to
    the bound."""
    f_opt = obj(theta_opt)
    p0 = {"v": theta_opt[1], "k": theta_opt[1] ** 2 / theta_opt[2], "tau": theta_opt[3], "f0": theta_opt[0]}[which]
    additive = which == "tau"
    steps = [1, 2, 4, 8, 16, 32, TAU_REACH_S] if additive else [1.02, 1.05, 1.1, 1.2, 1.35, 1.6, 2.0, 3.0, 5.0]
    ends, weak = [], False
    for sign in (-1, 1):
        x = _x0(which, theta_opt)
        inside, outside = p0, None
        for st in steps:
            val = p0 + sign * st if additive else p0 * st ** sign
            if not (bounds[0] <= val <= bounds[1]):
                break
            f, x = _profile_value(obj, which, val, theta_opt, x)
            if f - f_opt > threshold:
                outside = val
                break
            inside = val
        if outside is None:
            ends.append(bounds[0] if sign < 0 else bounds[1])
            weak = True
            continue
        for _ in range(3):                          # bisect between the last inside and the first outside
            mid = 0.5 * (inside + outside) if additive else float(np.sqrt(inside * outside))
            f, _ = _profile_value(obj, which, mid, theta_opt, x)
            if f - f_opt > threshold:
                outside = mid
            else:
                inside = mid
        ends.append(inside)
    return min(ends), max(ends), weak


def _region(obj, theta, threshold, tau_bounds, f0_bounds, sources, corr=None, identified=None, c=343.0):
    f0, v, d, tau = theta
    ranges, weak = {}, []
    for which, bounds in (("v", V_BOUNDS), ("k", K_BOUNDS), ("tau", tau_bounds), ("f0", f0_bounds)):
        lo, hi, wk = profile_range(obj, np.asarray(theta, float), which, threshold, bounds)
        ranges[which] = (lo, hi)
        if wk:
            weak.append(which)
    return Hypothesis(sources=list(sources), f0=float(f0), v=float(v), d=float(d), t_cpa_emit=float(tau),
                      t_cpa=float(tau + d / c), v_range=ranges["v"], k_range=ranges["k"], tau_range=ranges["tau"],
                      f0_range=ranges["f0"], weak=weak, corr_v_d=corr, identified=identified)


# ---- the two sources --------------------------------------------------------------------------------------------

def ls_hypotheses(sp: Spectrogram, ev: EventFit, f_lo: float, f_hi: float, c: float, harmonic: int = 1) -> list[Hypothesis]:
    track = ridge_track(sp, ev.t_start, ev.t_end, f_lo, f_hi, harmonic=harmonic)
    try:
        fit = fit_track(track, c=c, v_bounds=V_BOUNDS, d_bounds=D_BOUNDS)
    except ValueError:
        return []
    if not fit.identified:
        return []
    obj, n = _ls_objective(track, c)
    sigma2 = fit.optima[0][0] / max(n - 4, 1)
    threshold = LS_DCHI2 * MODEL_ERROR_FACTOR ** 2 * sigma2
    out = []
    for rss, tc, s in fit.optima[:K]:
        if rss > fit.optima[0][0] + threshold:
            continue
        sub = tracks_fit_at(track, tc, s, c)
        if sub is None:
            continue
        f0, v, d = sub
        theta = np.array([f0, v, d, tc])
        span = (ev.t_start - TAU_REACH_S, ev.t_end + TAU_REACH_S)
        out.append(_region(obj, theta, threshold, span, (f_lo, f_hi), ["ls"], fit.corr_v_d, fit.identified, c))
    return out


def tracks_fit_at(track: Track, tc: float, s: float, c: float):
    """(f0, v, d) of the closed-form alpha, beta at (t_c, s), or None for a rising curve."""
    t, g, _ = track.usable()
    z = (t - tc) / np.sqrt(s * s + (t - tc) ** 2)
    (al, be), *_ = np.linalg.lstsq(np.stack([np.ones_like(z), z], 1), g, rcond=None)
    v = -be * c / al
    if not 0 < v < c:
        return None
    return float(al * (1 - v * v / c / c)), float(v), float(s * v * c / np.sqrt(c * c - v * v))


def fit_event_hypotheses(sp: Spectrogram, w, ev: EventFit, f_lo: float, f_hi: float, c: float, null_sigma: float,
                         harmonic: int = 1) -> list[Hypothesis]:
    pad = 0.3 * (f_hi - f_lo)
    win = local_whiten(sp.crop(ev.t_start - 30, ev.t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonic + pad, sp.f[-1])))
    if 1.15 * f_lo >= 0.85 * f_hi or len(win.t) < 2:
        return []
    # optima are found on detect's coarse scan grid, then refined by fit_event
    t0s, bs, bp = grid_search(win, ev.t_start, ev.t_end, f_lo, f_hi, c, harmonic, v_grid=COARSE_V, d_grid=COARSE_D,
                              f0_step=2.0, t0_step=2.0, n_curve=80, per_t0=True)
    starts: list[int] = []
    for i in np.argsort(-bs):
        if np.isfinite(bs[i]) and all(abs(t0s[i] - t0s[j]) >= MIN_SEP_S for j in starts):
            starts.append(int(i))
        if len(starts) >= K:
            break
    obj = _brightness_objective(w, c)
    fits = [fit_event(sp, ev.t_start, ev.t_end, f_lo, f_hi, c=c, harmonics=harmonic,
                      init=(bp[i, 0], bp[i, 1], bp[i, 2], t0s[i])) for i in starts]
    fits = [f for f in fits if f.weak is None and np.isfinite(f.score)]
    if not fits:
        return []
    thetas = [np.array([f.f0, f.v, f.d, f.t_cpa_emit]) for f in fits]
    vals = [obj(th) for th in thetas]
    best = min(vals)
    threshold = NULL_DELTA * MODEL_ERROR_FACTOR ** 2 * null_sigma
    span = (ev.t_start - TAU_REACH_S, ev.t_end + TAU_REACH_S)
    return [_region(obj, th, threshold, span, (f_lo, f_hi), ["fit_event"], c=c)
            for th, val in zip(thetas, vals) if val - best <= threshold]


def merge(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Optima at nearly the same place, each inside the other's v, k and tau ranges, become one hypothesis with the
    wider ranges; the first one's optimum is kept."""
    out: list[Hypothesis] = []
    for h in hyps:
        for o in out:
            if o.contains(h) and h.contains(o):
                o.sources = sorted(set(o.sources) | set(h.sources))
                for r in ("v_range", "k_range", "tau_range", "f0_range"):
                    a, b = getattr(o, r), getattr(h, r)
                    setattr(o, r, (min(a[0], b[0]), max(a[1], b[1])))
                o.weak = sorted(set(o.weak) | set(h.weak))
                if o.corr_v_d is None:
                    o.corr_v_d, o.identified = h.corr_v_d, h.identified
                break
        else:
            out.append(h)
    return out


def gate_hypothesis(ev: EventFit, v_tol: float, d_tol: tuple, c: float) -> Hypothesis:
    """Today's speed and distance gates as a hypothesis: an event without an informative one admits as they do."""
    v_range, d_range = (ev.v * (1 - v_tol), ev.v * (1 + v_tol)), (ev.d * d_tol[0], ev.d * d_tol[1])
    return Hypothesis(sources=["gate"], f0=ev.f0, v=ev.v, d=ev.d, t_cpa_emit=ev.t_cpa_emit, t_cpa=ev.t_cpa,
                      v_range=v_range, k_range=(v_range[0] ** 2 / d_range[1], v_range[1] ** 2 / d_range[0]),
                      tau_range=(ev.t_cpa_emit, ev.t_cpa_emit), f0_range=(0.95 * ev.f0, 1.05 * ev.f0), d_range=d_range)


def informative(hyps: list[Hypothesis]) -> list[Hypothesis]:
    """Drop a hypothesis weak in v, k and tau together: its region is the whole table."""
    return [h for h in hyps if not {"v", "k", "tau"} <= set(h.weak)]


def event_hypotheses(sp: Spectrogram, w, ev: EventFit, c: float, null_sigma: float, harmonic: int = 1,
                     v_tol: float = 0.35, d_tol: tuple = (0.4, 2.5)) -> list[Hypothesis]:
    """Both sources' hypotheses for one event, merged, without uninformative ones; with none left, today's gates
    (gate_hypothesis). The band is 0.85 f_post to 1.15 f_pre of the event's fit."""
    f_lo, f_hi = 0.85 * ev.f_post, 1.15 * ev.f_pre
    hyps = informative(merge(ls_hypotheses(sp, ev, f_lo, f_hi, c, harmonic) +
                             fit_event_hypotheses(sp, w, ev, f_lo, f_hi, c, null_sigma, harmonic)))
    return hyps or [gate_hypothesis(ev, v_tol, d_tol, c)]
