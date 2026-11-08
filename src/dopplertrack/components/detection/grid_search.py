"""Grid search (Kay 1993 §7.7) over straight-pass Doppler curve templates: coarse maximisation of the contrast or the
mean level along the curve."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.detection.custom_curve_contrast import (CONTRAST_DF, SWEEP_FLOOR, custom_curve_contrast,
                                                                     custom_sweep_weights)
from dopplertrack.components.detection.doppler_curve import straight_pass_doppler_curve
from dopplertrack.components.spectrogram import Spectrogram


def grid_search(sp: Spectrogram, t_start, t_end, f_lo, f_hi, c, harmonics=1,
                v_grid=None, d_grid=None, f0_step=1.0, t0_step=1.0, n_curve=120,
                t0_range=None, f0_range=None, per_t0=False, fat_bins=5, objective="contrast",
                contrast_df: float = CONTRAST_DF, sweep_floor: float = SWEEP_FLOOR):
    """Coarse grid-search maximisation of the score along ideal curves (default: the contrast).
    Returns (score, (f0, v, d, t0_emit)).

    objective="contrast" scores the sweep-weighted ridge contrast (custom_sweep_weights,
    custom_curve_contrast) on a spectrogram max-filtered over `fat_bins` frequency bins, so that a
    grid curve a hertz or two off a narrow ridge still scores; the Nelder-Mead stage in
    fit_event refines on the unfiltered spectrogram. objective="brightness" (the key) scores the plain
    mean level along the curve, unweighted and unfiltered.

    The curve is scored on [t_start, t_end]; t0_range / f0_range (optional) restrict the
    searched emission-CPA times and fundamentals, which otherwise span the window / band.
    per_t0=True returns instead (t0s, best_score[T0], best_params[T0, 3]) so a caller can
    pick several local maxima in time: peak picking over the unknown arrival time, as in the GLRT
    (Kay 1998 §7.5-7.6), though the score here is not a likelihood."""
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
            dto, ratio = straight_pass_doppler_curve(v, d, c)
            rel = tq[None, :] - t0s[:, None]                         # (T0, N)
            rat = np.interp(rel, dto, ratio, left=np.nan, right=np.nan)  # (T0, N)
            if contrast:
                w = custom_sweep_weights(rat, tq, axis=1, sweep_floor=sweep_floor)   # (T0, N)
                w = np.where(np.isnan(rat), 0.0, w)
            else:                                                     # samples past the curve's span count as zero
                w = np.ones_like(rat)
            wsum = np.maximum(w.sum(axis=1), 1e-12)
            total = np.zeros((len(t0s), len(f0s)))
            for h in range(1, harmonics + 1):
                F = h * f0s[None, None, :] * rat[:, :, None]           # (T0, N, F0)
                T = np.broadcast_to(tq[None, :, None], F.shape)
                vals = (custom_curve_contrast(sp, T.ravel(), F.ravel(), contrast_df) if contrast
                        else sp.sample(T.ravel(), F.ravel()))
                total += np.einsum("tn,tnf->tf", w, np.nan_to_num(vals.reshape(F.shape))) / wsum[:, None]
            total /= harmonics
            j = np.argmax(total, axis=1); sc = total[np.arange(len(t0s)), j]
            upd = sc > bs
            bs[upd] = sc[upd]; bp[upd, 0] = f0s[j[upd]]; bp[upd, 1] = v; bp[upd, 2] = d
    if per_t0:
        return t0s, bs, bp
    i = int(np.argmax(bs))
    return float(bs[i]), (float(bp[i, 0]), float(bp[i, 1]), float(bp[i, 2]), float(t0s[i]))
