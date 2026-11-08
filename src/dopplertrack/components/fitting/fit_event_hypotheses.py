"""Fit-event hypotheses: fit_event's optima from its coarse grid's best emission-CPA times, each with its box of
pointwise profile intervals (Raue 2009, eq. 10) of the curve integral, which is not a likelihood (ours)."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.detection.event_fit import fit_event
from dopplertrack.components.detection.grid_search import grid_search
from dopplertrack.components.fitting.hypothesis import (D_BOUNDS, MAX_OPTIMA, MODEL_ERROR_FACTOR, TAU_REACH_S, V_BOUNDS,
                                                        Hypothesis, k_bounds)
from dopplertrack.components.fitting.profile_intervals import profile_box
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten

NULL_DELTA = 2.0            # Raue's Delta for the curve integral, in the event's decoy-null sigma (MADN)
MIN_SEP_S = 20.0            # fit_event optima: distinct emission-CPA times at least this far apart
COARSE_V = np.arange(40, 170, 13.0)          # detect_events' coarse scan grid, where fit_event's optima start
COARSE_D = np.geomspace(400, 9000, 10)


def closed_form_ratio(t, v, d, tau, c):
    """f/f0 heard at times t from a straight pass (Ferguson & Quinn 1994, eq. 15): exact, unlike ideal_curve's
    interpolated table, and cheap enough for profiles."""
    u = t - tau
    return c * c / (c * c - v * v) * (1 - v * v * u / np.sqrt(d * d * (c * c - v * v) + v * v * c * c * u * u))


# old name: _brightness_objective
def _curve_integral_objective(w, c: float):
    """Minus the curve integral under the ideal curve over the event's fit window, sampled where curve_score samples."""
    to = np.linspace(w.fit.t_start, w.fit.t_end, w.n)

    def neg(theta):
        f0, v, d, tau = theta
        if not (0 < v < c and d > 0 and f0 > 0):
            return np.inf
        return -w.curve_score(to, closed_form_ratio(to, v, d, tau, c), f0 / w.fit.f0)
    return neg


def fit_event_hypotheses(sp: Spectrogram, w, ev: EventFit, f_lo: float, f_hi: float, c: float, null_sigma: float,
                         harmonic: int = 1, *, max_optima: int = MAX_OPTIMA, null_delta: float = NULL_DELTA,
                         model_error_factor: float = MODEL_ERROR_FACTOR, min_sep_s: float = MIN_SEP_S,
                         v_bounds: tuple = V_BOUNDS, d_bounds: tuple = D_BOUNDS, tau_reach_s: float = TAU_REACH_S,
                         coarse_v=None, coarse_d=None, spectral_floor: float = 0.0) -> list[Hypothesis]:
    """fit_event's optima from up to max_optima coarse starts at least min_sep_s apart, within
    null_delta * model_error_factor^2 null sigmas of the best, each with its profile box. coarse_v and coarse_d are the
    coarse grid (COARSE_V, COARSE_D by default); the other defaults are the module constants."""
    coarse_v = COARSE_V if coarse_v is None else coarse_v
    coarse_d = COARSE_D if coarse_d is None else coarse_d
    pad = 0.3 * (f_hi - f_lo)
    win = local_whiten(sp.crop(ev.t_start - 30, ev.t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonic + pad, sp.f[-1])),
                       spectral_floor)
    if 1.15 * f_lo >= 0.85 * f_hi or len(win.t) < 2:
        return []
    # optima are found on detect's coarse scan grid, then refined by fit_event
    t0s, bs, bp = grid_search(win, ev.t_start, ev.t_end, f_lo, f_hi, c, harmonic, v_grid=coarse_v, d_grid=coarse_d,
                              f0_step=2.0, t0_step=2.0, n_curve=80, per_t0=True)
    starts: list[int] = []
    for i in np.argsort(-bs):
        if np.isfinite(bs[i]) and all(abs(t0s[i] - t0s[j]) >= min_sep_s for j in starts):
            starts.append(int(i))
        if len(starts) >= max_optima:
            break
    obj = _curve_integral_objective(w, c)
    fits = [fit_event(sp, ev.t_start, ev.t_end, f_lo, f_hi, c=c, harmonics=harmonic,
                      init=(bp[i, 0], bp[i, 1], bp[i, 2], t0s[i]), v_bounds=tuple(v_bounds), d_bounds=tuple(d_bounds),
                      spectral_floor=spectral_floor) for i in starts]
    fits = [f for f in fits if f.weak is None and np.isfinite(f.score)]
    if not fits:
        return []
    thetas = [np.array([f.f0, f.v, f.d, f.t_cpa_emit]) for f in fits]
    vals = [obj(th) for th in thetas]
    best = min(vals)
    threshold = null_delta * model_error_factor ** 2 * null_sigma
    span = (ev.t_start - tau_reach_s, ev.t_end + tau_reach_s)
    return [profile_box(obj, th, threshold, span, (f_lo, f_hi), ["fit_event"], c=c, v_bounds=tuple(v_bounds),
                        k_bounds=k_bounds(v_bounds, d_bounds), tau_reach_s=tau_reach_s)
            for th, val in zip(thetas, vals) if val - best <= threshold]
