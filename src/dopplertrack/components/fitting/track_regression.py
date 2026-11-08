"""Separable nonlinear least squares by variable projection (Golub & Pereyra 2003, §2, eq. 2.2): the
least-squares straight-pass fit (Ferguson & Quinn 1994, eq. 16) of a frequency track."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares, minimize

from dopplertrack.components.types import EventFit, Track
from dopplertrack.core.propagation import speed_of_sound

LS_Z_SPAN_MIN = 0.5    # z(t) must cover this much of its (-1, 1) range, or alpha and beta can't be told apart


@dataclass
class TrackFit:
    """The least-squares straight-pass fit of a track, with its diagnostics.

    f(t) = alpha + beta*z(t), z = (t - t_c)/sqrt(s^2 + (t - t_c)^2) (Ferguson & Quinn 1994, eq. 16), with t_c
    the emission CPA (the curve's midpoint and Doppler inflection point) and t_c + d/c the heard CPA. cov is the
    asymptotic (inverse Gauss-Newton) covariance (Raue 2009, eq. 7), valid for independent, correctly specified
    errors; overlapping STFT frames aren't independent, and under misspecification the sandwich A^-1 B A^-1
    applies (White 1982, §3), so it is not an estimate of the spread (PLAN Phase 2, item 7). identified is a
    heuristic acceptance check, not identifiability in Raue's sense (2009, §2.3)."""
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
    identified: bool         # z_span, bounds, a falling curve and convergence all hold (a heuristic, not Raue's)
    cov: list                # 4x4 asymptotic covariance over (f0, v, t_cpa_emit, d) (see above)
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
    """The variable projection functional (Golub & Pereyra 2003, eq. 2.2): weighted residual sum of squares with
    alpha and beta solved in closed form (F&Q eq. 18/19, weighted as Quinn 1995 eq. 2), under the physical bound beta <= 0: a pass's curve falls, so its speed is positive.
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
