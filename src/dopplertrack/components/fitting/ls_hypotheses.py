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
)
from dopplertrack.components.fitting.profile_intervals import profile_box
from dopplertrack.components.fitting.track_regression import fit_track
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
    for rss, tc, s in fit.optima[:MAX_OPTIMA]:
        if rss > fit.optima[0][0] + threshold:
            continue
        sub = tracks_fit_at(track, tc, s, c)
        if sub is None:
            continue
        f0, v, d = sub
        theta = np.array([f0, v, d, tc])
        span = (ev.t_start - TAU_REACH_S, ev.t_end + TAU_REACH_S)
        out.append(profile_box(obj, theta, threshold, span, (f_lo, f_hi), ["ls"], fit.corr_v_d, fit.identified, c))
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
