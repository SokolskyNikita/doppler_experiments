"""Nelder-Mead simplex fit (Nelder & Mead 1965, not in folder) after a grid search (Kay 1993 §7.7): (f0, v, d, t_cpa)
of the highest-scoring Doppler-shaped curve in a window. The objective is a contrast, not a likelihood."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from dopplertrack.components.detection.custom_curve_contrast import (CONTRAST_DF, SWEEP_FLOOR, custom_curve_contrast,
                                                                     custom_sweep_weights)
from dopplertrack.components.detection.grid_search import grid_search
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten
from dopplertrack.core.propagation import ideal_curve, speed_of_sound


def fit_event(sp: Spectrogram, t_start: float, t_end: float, f_lo: float, f_hi: float,
              c: float | None = None, harmonics: int = 1, whiten: bool = True,
              init: tuple[float, float, float, float] | None = None,
              v_bounds: tuple[float, float] = (10.0, 300.0), d_bounds: tuple[float, float] = (100.0, 30000.0),
              objective: str = "contrast", contrast_df: float = CONTRAST_DF, sweep_floor: float = SWEEP_FLOOR,
              spectral_floor: float = 0.0) -> EventFit:
    """Fit (f0, v, d, t_cpa) to the highest-scoring Doppler-shaped curve in a window.

    init=(f0, v, d, t0_emit) narrows the grid search to around that solution.

    objective="contrast" (what detect uses) maximises the sweep-weighted ridge contrast, which
    ignores broadband bursts and steady tones. objective="brightness" (the key) maximises the plain mean
    level along the curve, so the flat asymptotes count as much as the sweep; fits made
    before f890572 used it, including the committed docs/results event fits, and `fit` uses it
    by default for a window chosen by hand. contrast_df and sweep_floor are the contrast's (custom_curve_contrast),
    spectral_floor local_whiten's."""
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
        win = local_whiten(win, spectral_floor)
    if init is None:
        score0, (f0, v, d, t0) = grid_search(win, t_start, t_end, f_lo, f_hi, c, harmonics, objective=objective,
                                             contrast_df=contrast_df, sweep_floor=sweep_floor)
    else:   # full v/d grids, but only near the given fundamental and CPA time
        f0, v, d, t0 = init
        score0, (f0, v, d, t0) = grid_search(win, t_start, t_end, f_lo, f_hi, c, harmonics,
                                             t0_range=(t0 - 30, t0 + 30), f0_range=(max(f0 - 12, 1), f0 + 12),
                                             objective=objective, contrast_df=contrast_df, sweep_floor=sweep_floor)
    tt = np.linspace(t_start, t_end, 400)

    def neg(p):
        f0_, v_, d_, t0_ = p
        if not (v_bounds[0] < v_ < v_bounds[1] and d_bounds[0] < d_ < d_bounds[1]):
            return 1e3
        s = 0.0
        base = ideal_curve(tt, f0_, v_, d_, t0_, c=c)
        if objective == "brightness":
            return -sum(float(np.mean(win.sample(tt, h * base))) for h in range(1, harmonics + 1)) / harmonics
        w = custom_sweep_weights(base / f0_, tt, sweep_floor=sweep_floor)
        for h in range(1, harmonics + 1):
            s += float(np.sum(w * custom_curve_contrast(win, tt, h * base, contrast_df)) / np.sum(w))
        return -s / harmonics

    best = minimize(neg, [f0, v, d, t0], method="Nelder-Mead",
                    options={"xatol": 1e-2, "fatol": 1e-4, "maxiter": 4000,
                             "initial_simplex": np.array([[f0, v, d, t0], [f0 + 2, v, d, t0], [f0, v + 10, d, t0],
                                                          [f0, v, d * 1.3, t0], [f0, v, d, t0 + 2]])})
    f0, v, d, t0 = best.x
    return EventFit(t_cpa=float(t0 + d / c), t_cpa_emit=float(t0), f0=float(f0), v=float(v), d=float(d),
                    t_start=t_start, t_end=t_end, score=float(-best.fun),
                    f_pre=float(f0 * c / (c - v)), f_post=float(f0 * c / (c + v)))
