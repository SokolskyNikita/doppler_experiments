"""Least-squares hypotheses: the optima of the variable-projection fit (Golub & Pereyra 2003) of ridge_track's
track, each with its box of pointwise profile-likelihood intervals of the RSS (Raue 2009, eqs. 8 and 10)."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.detection.ridge import ridge_track
from dopplertrack.components.fitting.hypothesis import (
    D_BOUNDS,
    MODEL_ERROR_FACTOR,
    TAU_REACH_S,
    V_BOUNDS,
    Hypothesis,
    MAX_OPTIMA,
    k_bounds,
)
from dopplertrack.components.fitting.profile_intervals import profile_box
from dopplertrack.components.fitting.track_regression import LS_Z_SPAN_MIN, fit_track
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit, Track

LS_DCHI2 = 3.84 * 3.0       # Raue's Delta = chi2(1, 0.95) (2009, eq. 8) times the variance inflation of 88 %-overlapping
                            # frames (about 3, from the model-error study's c(r)^2 frame-correlation model,
                            # docs/experiments/2026-11-04-model-error.md)


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


def ls_hypotheses(sp: Spectrogram, ev: EventFit, f_lo: float, f_hi: float, c: float, harmonic: int = 1, *,
                  max_optima: int = MAX_OPTIMA, ls_dchi2: float = LS_DCHI2,
                  model_error_factor: float = MODEL_ERROR_FACTOR, v_bounds: tuple = V_BOUNDS,
                  d_bounds: tuple = D_BOUNDS, tau_reach_s: float = TAU_REACH_S, z_span_min: float = LS_Z_SPAN_MIN,
                  spectral_floor: float = 0.0) -> list[Hypothesis]:
    """Up to max_optima optima of the track's fit within ls_dchi2 * model_error_factor^2 of the best, each with its
    profile box; the defaults are the module constants."""
    track = ridge_track(sp, ev.t_start, ev.t_end, f_lo, f_hi, harmonic=harmonic, spectral_floor=spectral_floor)
    try:
        fit = fit_track(track, c=c, v_bounds=tuple(v_bounds), d_bounds=tuple(d_bounds), z_span_min=z_span_min)
    except ValueError:
        return []
    if not fit.identified:
        return []
    obj, n = _ls_objective(track, c)
    sigma2 = fit.optima[0][0] / max(n - 4, 1)
    threshold = ls_dchi2 * model_error_factor ** 2 * sigma2
    out = []
    for rss, tc, s in fit.optima[:max_optima]:
        if rss > fit.optima[0][0] + threshold:
            continue
        sub = tracks_fit_at(track, tc, s, c)
        if sub is None:
            continue
        f0, v, d = sub
        theta = np.array([f0, v, d, tc])
        span = (ev.t_start - tau_reach_s, ev.t_end + tau_reach_s)
        out.append(profile_box(obj, theta, threshold, span, (f_lo, f_hi), ["ls"], fit.corr_v_d, fit.identified, c,
                               v_bounds=tuple(v_bounds), k_bounds=k_bounds(v_bounds, d_bounds), tau_reach_s=tau_reach_s))
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
