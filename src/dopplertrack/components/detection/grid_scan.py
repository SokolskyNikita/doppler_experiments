"""Extract a Doppler event from a spectrogram window and fit the ideal model."""
from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import least_squares, minimize

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.core.propagation import ideal_curve, speed_of_sound
from dopplertrack.runtime.parallel import process_pool, resolve_jobs


@dataclass
class EventFit:
    t_cpa: float        # heard CPA time in the recording, s (observation time of the f0 crossing)
    t_cpa_emit: float   # emission-time CPA (t_cpa - d/c)
    f0: float           # rest fundamental, Hz
    v: float            # speed, m/s
    d: float            # CPA slant distance, m
    t_start: float
    t_end: float
    score: float        # mean whitened dB along the fitted curve
    f_pre: float
    f_post: float
    weak: str | None = None  # why the fit couldn't be made (the other fields are then NaN); None for a fit

    def to_dict(self):
        """The fields as a dict; `weak` only when set, so existing JSON is unchanged."""
        d = asdict(self)
        if d["weak"] is None:
            del d["weak"]
        return d

    @classmethod
    def unfit(cls, t_start: float, t_end: float, reason: str) -> "EventFit":
        nan = float("nan")
        return cls(t_cpa=nan, t_cpa_emit=nan, f0=nan, v=nan, d=nan, t_start=t_start, t_end=t_end, score=nan,
                   f_pre=nan, f_post=nan, weak=reason)


def local_whiten(sp: Spectrogram, floor: float = 0.0) -> Spectrogram:
    """Remove tones that are stationary over this window (per-bin median), clip at floor. A spectrogram
    whitened across frequency (sp.whitening == "frequency") keeps its stationary tones: it is only
    clipped at floor."""
    if sp.whitening == "frequency":
        S = np.maximum(sp.S, floor).astype(np.float32)
        S[:, ~sp.valid] = floor
        return sp.with_S(S)
    S = np.maximum(sp.S - sp.bin_median(), floor).astype(np.float32)
    S[:, ~sp.valid] = floor
    return sp.with_S(S)


def ridge(sp: Spectrogram, max_step_bins: int = 3, smooth: float = 1.5) -> np.ndarray:
    """Viterbi ridge through S (F,T): maximise sum(S) - smooth*|Δbin|. Returns freq per frame."""
    S = sp.S
    F, T = S.shape
    cost = np.full((T, F), -np.inf)
    back = np.zeros((T, F), np.int16)
    cost[0] = S[:, 0]
    offs = np.arange(-max_step_bins, max_step_bins + 1)
    pen = smooth * np.abs(offs)
    for t in range(1, T):
        prev = cost[t - 1]
        cand = np.full((len(offs), F), -np.inf)
        for k, o in enumerate(offs):
            if o >= 0:
                cand[k, o:] = prev[: F - o] - pen[k]
            else:
                cand[k, :o] = prev[-o:] - pen[k]
        kbest = np.argmax(cand, axis=0)
        cost[t] = cand[kbest, np.arange(F)] + S[:, t]
        back[t] = offs[kbest]
    path = np.zeros(T, int)
    path[-1] = int(np.argmax(cost[-1]))
    for t in range(T - 1, 0, -1):
        path[t - 1] = path[t] - back[t, path[t]]
    return sp.f[path]


CONTRAST_DF = 0.04     # sideband offset as a fraction of frequency
SWEEP_FLOOR = 0.15     # weight given to the flat tails of a curve, relative to its steepest part


def sweep_weights(ratio, t, axis=-1):
    """Per-sample weights proportional to |d ratio / dt| (the sweeping part of a Doppler
    curve carries the information; flat asymptotes also fit any steady tone), normalised to
    a peak of 1 per curve, plus SWEEP_FLOOR."""
    g = np.abs(np.gradient(ratio, t, axis=axis))
    g = np.nan_to_num(g, nan=0.0)
    peak = np.max(g, axis=axis, keepdims=True)
    return g / np.maximum(peak, 1e-12) + SWEEP_FLOOR


def curve_contrast(sp: Spectrogram, t, f):
    """Per-sample ridge contrast: brightness on the curve minus the mean of two sidebands.
    A broadband burst is as bright off the curve as on it and so scores ~0. Off-grid -> 0."""
    return sp.sample(t, f) - 0.5 * (sp.sample(t, f * (1 + CONTRAST_DF)) + sp.sample(t, f * (1 - CONTRAST_DF)))


def _shape(v, d, c, span=400.0, n=161):
    """Observation-time offsets and frequency ratios for a straight pass, relative to
    emission-time CPA (tau=0)."""
    tau = np.linspace(-span, span, n)
    r = np.sqrt(d * d + (v * tau) ** 2)
    rr = v * v * tau / r
    return tau + r / c, c / (c + rr)


def grid_search(sp: Spectrogram, t_start, t_end, f_lo, f_hi, c, harmonics=1,
                v_grid=None, d_grid=None, f0_step=1.0, t0_step=1.0, n_curve=120,
                t0_range=None, f0_range=None, per_t0=False, fat_bins=5, objective="contrast"):
    """Coarse maximisation of brightness under ideal curves. Returns (score, (f0, v, d, t0_emit)).

    objective="contrast" scores the sweep-weighted ridge contrast (sweep_weights,
    curve_contrast) on a spectrogram max-filtered over `fat_bins` frequency bins, so that a
    grid curve a hertz or two off a narrow ridge still scores; the Nelder-Mead stage in
    fit_event refines on the unfiltered spectrogram. objective="brightness" scores the plain
    mean brightness under the curve, unweighted and unfiltered.

    The curve is scored on [t_start, t_end]; t0_range / f0_range (optional) restrict the
    searched emission-CPA times and fundamentals, which otherwise span the window / band.
    per_t0=True returns instead (t0s, best_score[T0], best_params[T0, 3]) so a caller can
    pick several local maxima in time."""
    from scipy.ndimage import maximum_filter1d
    if objective not in ("contrast", "brightness"):
        raise ValueError(f"unknown objective {objective!r}")
    contrast = objective == "contrast"
    if contrast and fat_bins and fat_bins > 1:
        sp = sp.with_S(maximum_filter1d(sp.S, fat_bins, axis=0))
    v_grid = np.arange(30, 170, 10.0) if v_grid is None else v_grid
    d_grid = np.geomspace(300, 9000, 14) if d_grid is None else d_grid
    f0_min, f0_max = f0_range or (f_lo * 1.15, f_hi * 0.85)
    t0_min, t0_max = t0_range or (t_start, t_end)
    f0s = np.arange(f0_min, f0_max, f0_step)
    t0s = np.arange(t0_min, t0_max, t0_step)
    tq = np.linspace(t_start, t_end, n_curve)
    bs = np.full(len(t0s), -np.inf); bp = np.zeros((len(t0s), 3))
    for v in v_grid:
        for d in d_grid:
            dto, ratio = _shape(v, d, c)
            rel = tq[None, :] - t0s[:, None]                         # (T0, N)
            rat = np.interp(rel, dto, ratio, left=np.nan, right=np.nan)  # (T0, N)
            if contrast:
                w = sweep_weights(rat, tq, axis=1)                    # (T0, N)
                w = np.where(np.isnan(rat), 0.0, w)
            else:                                                     # samples past the curve's span count as zero
                w = np.ones_like(rat)
            wsum = np.maximum(w.sum(axis=1), 1e-12)
            total = np.zeros((len(t0s), len(f0s)))
            for h in range(1, harmonics + 1):
                F = h * f0s[None, None, :] * rat[:, :, None]           # (T0, N, F0)
                T = np.broadcast_to(tq[None, :, None], F.shape)
                vals = curve_contrast(sp, T.ravel(), F.ravel()) if contrast else sp.sample(T.ravel(), F.ravel())
                total += np.einsum("tn,tnf->tf", w, np.nan_to_num(vals.reshape(F.shape))) / wsum[:, None]
            total /= harmonics
            j = np.argmax(total, axis=1); sc = total[np.arange(len(t0s)), j]
            upd = sc > bs
            bs[upd] = sc[upd]; bp[upd, 0] = f0s[j[upd]]; bp[upd, 1] = v; bp[upd, 2] = d
    if per_t0:
        return t0s, bs, bp
    i = int(np.argmax(bs))
    return float(bs[i]), (float(bp[i, 0]), float(bp[i, 1]), float(bp[i, 2]), float(t0s[i]))


def fit_event(sp: Spectrogram, t_start: float, t_end: float, f_lo: float, f_hi: float,
              c: float | None = None, harmonics: int = 1, whiten: bool = True,
              init: tuple[float, float, float, float] | None = None,
              v_bounds: tuple[float, float] = (10.0, 300.0), d_bounds: tuple[float, float] = (100.0, 30000.0),
              objective: str = "contrast") -> EventFit:
    """Fit (f0, v, d, t_cpa) to the brightest Doppler-shaped curve in a window.

    init=(f0, v, d, t0_emit) narrows the grid search to around that solution.

    objective="contrast" (what detect uses) maximises the sweep-weighted ridge contrast, which
    ignores broadband bursts and steady tones. objective="brightness" maximises the plain mean
    brightness under the curve, so the flat asymptotes count as much as the sweep; fits made
    before f890572 used it, including the committed docs/results event fits, and `fit` uses it
    by default for a window chosen by hand."""
    c = speed_of_sound() if c is None else c
    pad = 0.3 * (f_hi - f_lo)
    win = sp.crop(t_start - 30, t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1]))
    # a search with nothing to search returns a weak fit with its reason, not an error
    f0_lo, f0_hi = (f_lo * 1.15, f_hi * 0.85) if init is None else (max(init[0] - 12, 1), init[0] + 12)
    if not f0_lo < f0_hi:   # grid_search takes f0 from 1.15 f_lo to 0.85 f_hi: empty when f_hi/f_lo < 1.15/0.85
        return EventFit.unfit(t_start, t_end, f"band narrower than the f0 search margins: f_hi/f_lo = "
                                              f"{f_hi / f_lo:.3f} < {1.15 / 0.85:.3f} for {f_lo:g}-{f_hi:g} Hz, "
                                              f"so the f0 range {f0_lo:g}-{f0_hi:g} Hz is empty")
    if not t_start < t_end or len(win.t) < 2 or len(win.f) < 2:
        return EventFit.unfit(t_start, t_end, f"the window {t_start:g}-{t_end:g} s and band {f_lo:g}-{f_hi:g} Hz "
                                              "hold no spectrogram to fit")
    if whiten:
        win = local_whiten(win)
    if init is None:
        score0, (f0, v, d, t0) = grid_search(win, t_start, t_end, f_lo, f_hi, c, harmonics, objective=objective)
    else:   # full v/d grids, but only near the given fundamental and CPA time
        f0, v, d, t0 = init
        score0, (f0, v, d, t0) = grid_search(win, t_start, t_end, f_lo, f_hi, c, harmonics,
                                             t0_range=(t0 - 30, t0 + 30), f0_range=(max(f0 - 12, 1), f0 + 12),
                                             objective=objective)
    tt = np.linspace(t_start, t_end, 400)

    def neg(p):
        f0_, v_, d_, t0_ = p
        if not (v_bounds[0] < v_ < v_bounds[1] and d_bounds[0] < d_ < d_bounds[1]):
            return 1e3
        s = 0.0
        base = ideal_curve(tt, f0_, v_, d_, t0_, c=c)
        if objective == "brightness":
            return -sum(float(np.mean(win.sample(tt, h * base))) for h in range(1, harmonics + 1)) / harmonics
        w = sweep_weights(base / f0_, tt)
        for h in range(1, harmonics + 1):
            s += float(np.sum(w * curve_contrast(win, tt, h * base)) / np.sum(w))
        return -s / harmonics

    best = minimize(neg, [f0, v, d, t0], method="Nelder-Mead",
                    options={"xatol": 1e-2, "fatol": 1e-4, "maxiter": 4000,
                             "initial_simplex": np.array([[f0, v, d, t0], [f0 + 2, v, d, t0], [f0, v + 10, d, t0],
                                                          [f0, v, d * 1.3, t0], [f0, v, d, t0 + 2]])})
    f0, v, d, t0 = best.x
    return EventFit(t_cpa=float(t0 + d / c), t_cpa_emit=float(t0), f0=float(f0), v=float(v), d=float(d),
                    t_start=t_start, t_end=t_end, score=float(-best.fun),
                    f_pre=float(f0 * c / (c - v)), f_post=float(f0 * c / (c + v)))


# ---- least-squares fit of a frequency track (PLAN Phase 2, item 4) ----------------------------

@dataclass
class Track:
    """A frequency track, the least-squares fit's input, from ridge() or any other tracker."""
    t: np.ndarray                      # recording seconds
    f: np.ndarray                      # Hz: `harmonic` times the fundamental
    amplitude: np.ndarray | None = None  # per point; the weighted fit weights each point by amplitude²
    valid: np.ndarray | None = None    # False where the tracker has no measurement
    harmonic: int = 1

    def usable(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(t, fundamental frequency, amplitude) at the valid, finite points."""
        t, f = np.asarray(self.t, float), np.asarray(self.f, float)
        a = np.ones_like(f) if self.amplitude is None else np.asarray(self.amplitude, float)
        ok = np.isfinite(t) & np.isfinite(f) & np.isfinite(a) & (a > 0)
        if self.valid is not None:
            ok &= np.asarray(self.valid, bool)
        return t[ok], f[ok] / self.harmonic, a[ok]


def ridge_track(sp: Spectrogram, t_start: float, t_end: float, f_lo: float, f_hi: float, harmonic: int = 1) -> Track:
    """ridge() through the window, on local_whiten of exactly the band (times the harmonic), as a Track:
    bin-centre frequencies, amplitude 10^(dB/20) of the whitened level on the path, and the
    spectrogram's frame mask. Unlike fit_event's padded crop, which constrains its curve to the band,
    ridge() takes the strongest path through whatever it is given, so any margin lets it lock onto a
    line outside the band."""
    win = local_whiten(sp.crop(t_start, t_end, harmonic * f_lo, harmonic * f_hi))
    f = ridge(win)
    level = win.S[np.searchsorted(win.f, f), np.arange(len(win.t))]
    return Track(win.t, f, 10.0 ** (level / 20.0), win.valid.copy(), harmonic)


LS_Z_SPAN_MIN = 0.5    # z(t) must cover this much of its (-1, 1) range, or alpha and beta can't be told apart


@dataclass
class TrackFit:
    """The least-squares straight-pass fit of a track, with its diagnostics.

    f(t) = alpha + beta*z(t), z = (t - t_c)/sqrt(s^2 + (t - t_c)^2) (Ferguson & Quinn 1994, eq. 16), with t_c
    the emission CPA (the curve's midpoint and steepest fall) and t_c + d/c the heard CPA. The covariance
    treats the points as independent; overlapping STFT frames aren't, so it is a floor on the spread,
    not an estimate of it (PLAN Phase 2, item 7)."""
    f0: float
    v: float
    d: float
    t_cpa_emit: float
    t_cpa: float
    t_start: float
    t_end: float
    alpha: float
    beta: float
    s: float
    weighted: bool
    n: int                   # points fitted
    rms_hz: float            # weighted RMS residual, in Hz of the fundamental
    z_span: float            # range of z over the track; below LS_Z_SPAN_MIN alpha and beta are confounded
    cond: float              # condition number of the weighted [1, z] design
    converged: bool          # the best start's optimiser reported success
    n_starts: int
    n_optima: int            # distinct optima the starts reached
    second_optimum_ratio: float  # RSS of the best other optimum over the best's (inf if none)
    at_bound: list           # parameters at a bound or the edge of the search: "t_c", "s", "v", "d"
    identified: bool         # z_span, bounds, a falling curve and convergence all hold
    cov: list                # 4x4 over (f0, v, t_cpa_emit, d), a floor (see above)
    corr_v_d: float          # speed-distance correlation from cov
    optima: list             # the distinct optima as (rss, t_c, s), best first; t_c in the track's seconds

    def event(self, score: float = float("nan")) -> EventFit:
        c = self.v / (-self.beta / self.alpha)
        return EventFit(t_cpa=self.t_cpa, t_cpa_emit=self.t_cpa_emit, f0=self.f0, v=self.v, d=self.d,
                        t_start=self.t_start, t_end=self.t_end, score=score,
                        f_pre=self.f0 * c / (c - self.v), f_post=self.f0 * c / (c + self.v))

    def to_dict(self):
        return asdict(self)


def _z(t, tc, s):
    u = np.sqrt(s * s + (t - tc) ** 2)
    return (t - tc) / u, u


def _profile_rss(t, g, w, tc, s):
    """Weighted residual sum of squares with alpha and beta solved in closed form (eq. 18/19, weighted as
    Quinn 1995 eq. 2), under the physical bound beta <= 0: a pass's curve falls, so its speed is positive.
    beta = Sgz/Szz, so where Sgz >= 0 the bounded optimum is beta = 0, a flat line, whose residual is Sgg.
    tc and s broadcast against each other; t, g, w are the points (last axis)."""
    z, _ = _z(t, np.asarray(tc)[..., None], np.asarray(s)[..., None])
    sw = w.sum()
    gm = (w * g).sum() / sw
    zm = (w * z).sum(-1, keepdims=True) / sw
    szz = (w * (z - zm) ** 2).sum(-1)
    sgz = (w * (g - gm) * (z - zm)).sum(-1)
    sgg = (w * (g - gm) ** 2).sum()
    return sgg - np.where((szz > 0) & (sgz < 0), sgz ** 2 / np.where(szz > 0, szz, 1.0), 0.0)


def fit_track(track: Track, c: float | None = None, weighted: bool = False,
              v_bounds: tuple[float, float] = (10.0, 300.0), d_bounds: tuple[float, float] = (100.0, 30000.0),
              n_tc: int = 24, n_s: int = 24, n_refine: int = 5) -> TrackFit:
    """Least-squares fit of the straight-pass model to a track by variable projection: alpha and beta are
    solved in closed form at each (t_c, s), so the search is over those two only.

    Starts: a grid of n_tc emission-CPA times over the track's span extended by half of it on each side
    (a partial track's CPA can lie outside it), times n_s values of s spanning the speed and distance
    bounds; the n_refine best grid cells are each refined by Nelder-Mead on (t_c, log s), since variable
    projection doesn't remove local optima. The best optimum is then polished by least_squares to
    numerical precision. weighted=True weights each point by its amplitude squared (Quinn 1995). Raises
    ValueError with fewer than 8 usable points."""
    c = speed_of_sound() if c is None else c
    t_abs, g, a = track.usable()
    if len(t_abs) < 8:
        raise ValueError(f"a track needs at least 8 usable points, got {len(t_abs)}")
    # t_c is searched relative to the track's first point: in recording or unix seconds the optimiser's
    # steps and tolerances would scale with the clock's magnitude (the model-error study's item 2 found least_squares
    # stopping early that way)
    t_ref = float(t_abs[0])
    t = t_abs - t_ref
    w = a ** 2 if weighted else np.ones_like(g)
    w = w / w.mean()

    def s_of(v, d):
        return d * np.sqrt(c * c - v * v) / (v * c)
    s_lo, s_hi = s_of(v_bounds[1], d_bounds[0]), s_of(v_bounds[0], d_bounds[1])
    span = t[-1] - t[0]
    tc_lo, tc_hi = t[0] - 0.5 * span, t[-1] + 0.5 * span
    tcs, ss_ = np.linspace(tc_lo, tc_hi, n_tc), np.geomspace(s_lo, s_hi, n_s)
    grid = _profile_rss(t, g, w, tcs[:, None], ss_[None, :])
    starts = np.argsort(grid, axis=None)[:n_refine]

    def obj(p):
        tc, ls = p
        if not (tc_lo <= tc <= tc_hi and np.log(s_lo) <= ls <= np.log(s_hi)):
            return float(grid.max()) * 10 + 1.0
        return float(_profile_rss(t, g, w, tc, np.exp(ls)))

    sols = []
    for k in starts:
        i, j = np.unravel_index(k, grid.shape)
        x0 = np.array([tcs[i], np.log(ss_[j])])
        r = minimize(obj, x0, method="Nelder-Mead",
                     options={"xatol": 1e-4, "fatol": 1e-10 * max(float(grid.min()), 1e-12), "maxiter": 2000,
                              "initial_simplex": np.array([x0, x0 + [max(span / n_tc, 0.5), 0], x0 + [0, 0.2]])})
        sols.append((float(r.fun), float(r.x[0]), float(np.exp(r.x[1])), bool(r.success)))
    sols.sort()
    distinct: list[tuple[float, float, float, bool]] = []
    for sol in sols:
        if all(abs(sol[1] - o[1]) > 1.0 or abs(np.log(sol[2] / o[2])) > 0.05 for o in distinct):
            distinct.append(sol)
    rss, tc, s, converged = distinct[0]
    # polish the best optimum to numerical precision: Nelder-Mead stops at its step tolerance
    sqw = np.sqrt(w)

    def bounded_resid(x):
        zz, _ = _z(t, x[0], np.exp(x[1]))
        zm, gm = (w * zz).sum() / w.sum(), (w * g).sum() / w.sum()
        szz, sgz = (w * (zz - zm) ** 2).sum(), (w * (g - gm) * (zz - zm)).sum()
        b = sgz / szz if szz > 0 and sgz < 0 else 0.0
        return sqw * (g - gm - b * (zz - zm))
    pol = least_squares(bounded_resid, [tc, np.log(s)], bounds=([tc_lo, np.log(s_lo)], [tc_hi, np.log(s_hi)]),
                        x_scale=[1.0, 0.1], xtol=1e-12, ftol=1e-12, gtol=1e-12)
    if pol.success and 2 * pol.cost <= rss:
        tc, s, rss, converged = float(pol.x[0]), float(np.exp(pol.x[1])), 2 * float(pol.cost), True
    z, u = _z(t, tc, s)
    sw = np.sqrt(w)
    X = np.stack([np.ones_like(z), z], 1)
    (alpha, beta), *_ = np.linalg.lstsq(X * sw[:, None], g * sw, rcond=None)
    if beta > 0:                    # the bound (see _profile_rss): no falling curve fits, so a flat one
        alpha, beta = float((w * g).sum() / w.sum()), 0.0
    cond = float(np.linalg.cond(X * sw[:, None]))
    v = float(-beta * c / alpha)
    ok_v = 0 < v < c
    f0 = float(alpha * (1 - v * v / c / c))
    d = float(s * v * c / np.sqrt(c * c - v * v)) if ok_v else float("nan")
    resid = g - alpha - beta * z
    n = len(t)
    sigma2 = float((w * resid ** 2).sum() / max(n - 4, 1))
    # covariance of (alpha, beta, tc, s), then of (f0, v, tc, d) by the delta method
    J = np.stack([np.ones_like(z), z, beta * (-s * s / u ** 3), beta * (-s * z / u ** 2)], 1)
    try:
        cov_p = sigma2 * np.linalg.inv(J.T @ (J * w[:, None]))
    except np.linalg.LinAlgError:
        cov_p = np.full((4, 4), np.nan)

    def derived(p):
        al, be, tc_, s_ = p
        v_ = -be * c / al
        return np.array([al * (1 - v_ * v_ / c / c), v_, tc_, s_ * v_ * c / np.sqrt(c * c - v_ * v_)])
    p0 = np.array([alpha, beta, tc, s])
    D = np.zeros((4, 4))
    for k in range(4):
        h = 1e-6 * max(abs(p0[k]), 1e-3)
        e = np.zeros(4); e[k] = h
        D[:, k] = (derived(p0 + e) - derived(p0 - e)) / (2 * h)
    cov = D @ cov_p @ D.T
    corr = float(cov[1, 3] / np.sqrt(cov[1, 1] * cov[3, 3])) if cov[1, 1] > 0 and cov[3, 3] > 0 else float("nan")
    at_bound = []
    if min(tc - tc_lo, tc_hi - tc) < 0.01 * (tc_hi - tc_lo):
        at_bound.append("t_c")
    if min(np.log(s / s_lo), np.log(s_hi / s)) < 0.01:
        at_bound.append("s")
    if ok_v and not (v_bounds[0] < v < v_bounds[1]):
        at_bound.append("v")
    if ok_v and not (d_bounds[0] < d < d_bounds[1]):
        at_bound.append("d")
    z_span = float(z.max() - z.min())
    identified = bool(z_span >= LS_Z_SPAN_MIN and beta < 0 and ok_v and converged
                      and not ({"v", "d"} & set(at_bound)))
    return TrackFit(f0=f0, v=v, d=d, t_cpa_emit=t_ref + tc, t_cpa=t_ref + tc + d / c, t_start=float(t_abs[0]), t_end=float(t_abs[-1]),
                    alpha=float(alpha), beta=float(beta), s=s, weighted=weighted, n=n,
                    rms_hz=float(np.sqrt((w * resid ** 2).sum() / w.sum())), z_span=z_span, cond=cond,
                    converged=converged, n_starts=len(sols), n_optima=len(distinct),
                    second_optimum_ratio=float(distinct[1][0] / rss) if len(distinct) > 1 and rss > 0 else float("inf"),
                    at_bound=at_bound, identified=identified, cov=cov.tolist(), corr_v_d=corr,
                    optima=[(rss, t_ref + tc, s)] + [(o[0], t_ref + o[1], o[2]) for o in distinct[1:]])


@dataclass(frozen=True)
class ScanRequest:
    """One detector window, as sent to a worker process. Times are recording seconds."""
    window: Spectrogram         # whitened crop, padded 30 s on each side of the scored span
    window_start_s: float       # the scored span and the searched emission-CPA times
    window_end_s: float
    f_lo_hz: float
    f_hi_hz: float
    sound_speed_mps: float
    harmonics: int
    speed_grid_mps: np.ndarray
    slant_grid_m: np.ndarray
    f0_step_hz: float
    t0_step_s: float
    n_curve: int
    per_window: int             # local maxima kept from this window
    min_sep_s: float            # between those maxima's emission-CPA times


@dataclass(frozen=True)
class Candidate:
    """A coarse grid-search maximum, before refinement by fit_event."""
    score: float
    f0_hz: float
    speed_mps: float
    slant_m: float
    t_cpa_emit_s: float         # emission-time CPA in recording seconds, not the heard CPA time


def _scan_window(req: ScanRequest) -> list[Candidate]:
    """Up to req.per_window local maxima (separated by req.min_sep_s seconds) of the coarse search in one window."""
    if not np.any(req.window.S > 0):
        return []
    t0s, bs, bp = grid_search(req.window, req.window_start_s, req.window_end_s, req.f_lo_hz, req.f_hi_hz,
                              req.sound_speed_mps, req.harmonics, req.speed_grid_mps, req.slant_grid_m,
                              f0_step=req.f0_step_hz, t0_step=req.t0_step_s, n_curve=req.n_curve, per_t0=True)
    out: list[Candidate] = []
    order = np.argsort(-bs)
    for i in order:
        if all(abs(t0s[i] - o.t_cpa_emit_s) >= req.min_sep_s for o in out):
            out.append(Candidate(float(bs[i]), float(bp[i, 0]), float(bp[i, 1]), float(bp[i, 2]), float(t0s[i])))
        if len(out) >= req.per_window:
            break
    return out


def merge_candidates(cands: list[Candidate], min_sep_s: float, keep: int) -> list[Candidate]:
    """The best `keep` candidates whose emission-CPA times are at least min_sep_s apart.

    Candidates are ranked by (score, f0, speed, slant range, emission CPA time), all descending, so
    equal scores are broken by the higher fundamental, then speed, and so on; a kept candidate
    suppresses every lower-ranked one within min_sep_s of it."""
    ranked = sorted(cands, key=lambda cnd: (cnd.score, cnd.f0_hz, cnd.speed_mps, cnd.slant_m, cnd.t_cpa_emit_s), reverse=True)
    out: list[Candidate] = []
    for cnd in ranked:
        if all(abs(cnd.t_cpa_emit_s - k.t_cpa_emit_s) >= min_sep_s for k in out):
            out.append(cnd)
        if len(out) >= keep:
            break
    return out


OFF_CURVE = (-0.20, -0.16, -0.12, -0.08, 0.08, 0.12, 0.16, 0.20)    # S1's null: the curve moved off itself


def overlap_weight(hop_s: float, window_s: float = 2.048, n: int = 8192) -> float:
    """Harris's overlap weight 1 / (1 + 2 sum_m rho(m hop)^2) of a Hann window: the share of a frame's evidence that
    is its own (0.254 for the package's 2.048 s window at 0.25 s)."""
    w = np.hanning(n)
    h = max(1, int(round(n * hop_s / window_s)))
    e = float(np.dot(w, w))
    rho = [float(np.dot(w[:-m * h], w[m * h:])) / e for m in range(1, (n - 1) // h + 1)]
    return 1.0 / (1.0 + 2.0 * sum(r * r for r in rho))


def curve_zscore(sp: Spectrogram, ef: EventFit, c: float, harmonics: int = 1, frame_weight: float | None = None
                 ) -> tuple[float, float]:
    """S1 for a fitted curve: sum_k a_k c_k / (sigma_c sqrt(sum_k a_k^2 / w)) over the valid frames k of sp (whitened)
    in [t_start, t_end], with c_k the ridge contrast on the curve (averaged over harmonics), a_k its sweep weights,
    w the frames' overlap weight and sigma_c the robust spread (MAD) of the same contrast along the curve moved off
    itself in frequency (OFF_CURVE). A z-score: unit spread in noise whatever the curve's length or the overlap.
    Returns (S1, sigma_c)."""
    k = (sp.t >= ef.t_start) & (sp.t <= ef.t_end) & sp.valid
    t = sp.t[k]
    if len(t) < 3 or not np.isfinite(ef.f0):
        return float("nan"), float("nan")
    dto, ratio = _shape(ef.v, ef.d, c)
    rat = np.interp(t - ef.t_cpa_emit, dto, ratio, left=np.nan, right=np.nan)
    a = np.where(np.isnan(rat), 0.0, sweep_weights(rat, t))
    rat = np.nan_to_num(rat, nan=1.0)

    def contrast(scale):
        return np.mean([curve_contrast(sp, t, h * ef.f0 * rat * scale) for h in range(1, harmonics + 1)], axis=0)
    on = np.nan_to_num(contrast(1.0))
    off = np.concatenate([contrast(1.0 + s) for s in OFF_CURVE])
    off = off[np.isfinite(off)]
    sigma = 1.4826 * float(np.median(np.abs(off - np.median(off)))) if len(off) else float("nan")
    w = overlap_weight(float(np.median(np.diff(sp.t)))) if frame_weight is None else frame_weight
    den = sigma * np.sqrt(float(np.sum(a * a)) / w)
    return (float(np.sum(a * on) / den) if den > 0 else float("nan")), sigma


def detect_events(sp: Spectrogram, f_lo: float, f_hi: float, c: float | None = None, harmonics: int = 1,
                  window_s: float = 240.0, step_s: float = 120.0, v_grid=None, d_grid=None,
                  f0_step: float = 2.0, t0_step: float = 2.0, n_curve: int = 80, top: int = 20,
                  per_window: int = 3, min_sep_s: float = 60.0, refine: bool = True,
                  workers: int | None = None, progress=None, min_score: float = 0.0) -> list[EventFit]:
    """Scan a whole recording for Doppler-shaped curves whose fundamental lies in [f_lo, f_hi].

    Each window gets the coarse grid search used by fit_event (windows run in `workers`
    processes, parallel.default_jobs() by default; the result doesn't depend on it) and contributes up to `per_window` local maxima in time. Those are merged
    (one event per min_sep_s), the best 2*top are refined with a local grid search plus
    Nelder-Mead, and the best `top` after refinement are returned, sorted by score
    (sweep-weighted ridge contrast, dB). Only finite scores strictly above
    min_score are returned, so the result may be empty. The default rejects zero
    evidence; a useful false-alarm threshold still needs calibration. rescore_z puts the result on S1's scale."""
    if top < 1:
        raise ValueError("top must be at least 1")
    if not np.isfinite(min_score):
        raise ValueError("min_score must be finite")
    c = speed_of_sound() if c is None else c
    v_grid = np.arange(40, 170, 13.0) if v_grid is None else v_grid
    d_grid = np.geomspace(400, 9000, 10) if d_grid is None else d_grid
    pad = 0.3 * (f_hi - f_lo)
    starts = np.arange(sp.t[0], max(sp.t[-1] - window_s, sp.t[0]) + 1e-9, step_s)
    workers = min(resolve_jobs(workers), len(starts))         # no idle workers for a short recording

    def jobs():
        for t in starts:
            t1 = min(t + window_s, sp.t[-1])
            win = local_whiten(sp.crop(t - 30, t1 + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1])))
            yield ScanRequest(window=win, window_start_s=t, window_end_s=t1, f_lo_hz=f_lo, f_hi_hz=f_hi,
                              sound_speed_mps=c, harmonics=harmonics, speed_grid_mps=v_grid, slant_grid_m=d_grid,
                              f0_step_hz=f0_step, t0_step_s=t0_step, n_curve=n_curve, per_window=per_window,
                              min_sep_s=min_sep_s)

    cands: list[Candidate] = []
    with contextlib.ExitStack() as stack:
        if workers == 1:
            it: Iterator[list[Candidate]] = map(_scan_window, jobs())
        else:
            it = stack.enter_context(process_pool(workers)).map(_scan_window, jobs(), chunksize=2)
        for k, r in enumerate(it):
            cands.extend(r)
            if progress:
                progress(k + 1, len(starts))
    keep = merge_candidates(cands, min_sep_s, 2 * top if refine else top)
    out = []
    for cnd in keep:
        f0, v, d, t0 = cnd.f0_hz, cnd.speed_mps, cnd.slant_m, cnd.t_cpa_emit_s
        if refine:
            ef = fit_event(sp, max(t0 - 120, sp.t[0]), min(t0 + 120, sp.t[-1]), f_lo, f_hi, c=c,
                           harmonics=harmonics, init=(f0, v, d, t0), v_bounds=(35.0, 200.0), d_bounds=(200.0, 15000.0))
        else:
            ef = EventFit(t_cpa=t0 + d / c, t_cpa_emit=t0, f0=f0, v=v, d=d, t_start=t0 - 120, t_end=t0 + 120,
                          score=cnd.score, f_pre=f0 * c / (c - v), f_post=f0 * c / (c + v))
        if np.isfinite(ef.score) and ef.score > min_score:
            out.append(ef)
    out.sort(key=lambda e: -e.score)
    final: list[EventFit] = []
    for e in out:          # refined fits can converge onto the same event; keep the best
        if all(abs(e.t_cpa - f.t_cpa) >= min_sep_s for f in final):
            final.append(e)
        if len(final) >= top:
            break
    return final


def rescore_z(sp: Spectrogram, events: list[EventFit], f_lo: float, f_hi: float, c: float | None = None,
              harmonics: int = 1, min_sep_s: float = 60.0, top: int | None = None, min_score: float = 0.0,
              diagnostics: list | None = None) -> list[EventFit]:
    """detect_events' fits rescored by S1 (curve_zscore, PLAN item 6), re-ranked, one event per min_sep_s, the best
    `top` above min_score. The fits are unchanged; only the score is S1's. Kept apart from detect_events so that
    detect's code, and the detections cache keyed on it, don't change before item 6 is decided. With a
    `diagnostics` list, each event's sigma_c is appended beside the median over the events (the cross-window
    estimate)."""
    c = speed_of_sound() if c is None else c
    pad = 0.3 * (f_hi - f_lo)
    scored, rows = [], []
    for ef in events:
        win = local_whiten(sp.crop(ef.t_start - 30, ef.t_end + 30, max(f_lo - pad, sp.f[0]),
                                   min(f_hi * harmonics + pad, sp.f[-1])))
        z, sigma = curve_zscore(win, ef, c, harmonics)
        rows.append(dict(t_cpa=ef.t_cpa, s0=ef.score, s1=z, sigma_c=sigma))
        if np.isfinite(z) and z > min_score:
            scored.append(dataclasses.replace(ef, score=z))
    sig = [r["sigma_c"] for r in rows if np.isfinite(r["sigma_c"])]
    if diagnostics is not None:
        med = float(np.median(sig)) if sig else float("nan")
        diagnostics.extend({**r, "sigma_c_cross_window": med} for r in rows)
    scored.sort(key=lambda e: -e.score)
    final: list[EventFit] = []
    for e in scored:
        if all(abs(e.t_cpa - f.t_cpa) >= min_sep_s for f in final):
            final.append(e)
        if top is not None and len(final) >= top:
            break
    return final



def rescore_null(sp: Spectrogram, events: list[EventFit], f_lo: float, f_hi: float, c: float | None = None,
                 harmonics: int = 1, diagnostics: list | None = None) -> list[EventFit]:
    """detect_events' fits with D = S0 - (fit_event's maximum S0 on the event's window and band reversed in time) as
    the score (PLAN item 6, retune 1). Reversal keeps every steady tone, burst and level of the window, while a
    falling Doppler curve becomes a rising one the model can't fit, so D measures the event against its own
    window's clutter, with the search's best-of-many tail in the null. S2 = D / sigma_null, with sigma_null the
    spread of D on null data (set by the caller, since one window gives one null sample). Same order and fits as
    `events`; kept apart from detect_events so detect's code and the detections cache don't change."""
    c = speed_of_sound() if c is None else c
    pad = 0.3 * (f_hi - f_lo)
    out = []
    for ef in events:
        win = sp.crop(ef.t_start - 30, ef.t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1]))
        rev = dataclasses.replace(win, S=win.S[:, ::-1], valid=win.valid[::-1])
        nf = fit_event(rev, ef.t_start, ef.t_end, f_lo, f_hi, c=c, harmonics=harmonics,
                       v_bounds=(35.0, 200.0), d_bounds=(200.0, 15000.0))
        d = ef.score - nf.score if np.isfinite(nf.score) else float("nan")
        if diagnostics is not None:
            diagnostics.append(dict(t_cpa=ef.t_cpa, s0=ef.score, s0_reversed=nf.score, d=d))
        out.append(dataclasses.replace(ef, score=d))
    return out
