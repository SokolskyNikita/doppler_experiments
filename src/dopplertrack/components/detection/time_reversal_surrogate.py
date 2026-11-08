"""Time-reversal surrogate null (time-reversed surrogate data, Theiler et al. 1992, not in folder; the null hypothesis
H0 as in Kay 1998 ch. 3): an event's score less the best fit on its own window reversed in time. The best-of-many
maximum on the surrogate puts the search over a parameter absent under H0 into the null (Davies 1987)."""
# old module: dopplertrack.components.detection.s2_reversed_null
from __future__ import annotations

import dataclasses

import numpy as np

from dopplertrack.components.detection.custom_curve_contrast import CONTRAST_DF, SWEEP_FLOOR
from dopplertrack.components.detection.event_fit import fit_event
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.core.propagation import speed_of_sound


# old name: rescore_null
def rescore_surrogate(sp: Spectrogram, events: list[EventFit], f_lo: float, f_hi: float, c: float | None = None,
                 harmonics: int = 1, diagnostics: list | None = None, v_bounds: tuple = (35.0, 200.0),
                 d_bounds: tuple = (200.0, 15000.0), objective: str = "contrast", contrast_df: float = CONTRAST_DF,
                 sweep_floor: float = SWEEP_FLOOR, spectral_floor: float = 0.0) -> list[EventFit]:
    """detect_events' fits with D = S0 - (fit_event's maximum S0 on the event's window and band reversed in time) as
    the score (PLAN item 6, retune 1). Reversal keeps every steady tone, burst and level of the window, while a
    falling Doppler curve becomes a rising one the model can't fit, so D measures the event against its own
    window's clutter, with the search's best-of-many tail in the null. This returns D, not S2: the caller forms
    S2 = D / sigma_null, with sigma_null the spread of D on null data (one window gives one null sample). The
    diagnostics keys `s0`, `s0_reversed` and `d` are unchanged. Same order and fits as
    `events`; kept apart from detect_events so detect's code and the detections cache don't change."""
    c = speed_of_sound() if c is None else c
    pad = 0.3 * (f_hi - f_lo)
    out = []
    for ef in events:
        win = sp.crop(ef.t_start - 30, ef.t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1]))
        rev = dataclasses.replace(win, S=win.S[:, ::-1], valid=win.valid[::-1])
        nf = fit_event(rev, ef.t_start, ef.t_end, f_lo, f_hi, c=c, harmonics=harmonics,
                       v_bounds=(float(v_bounds[0]), float(v_bounds[1])),
                       d_bounds=(float(d_bounds[0]), float(d_bounds[1])), objective=objective,
                       contrast_df=contrast_df, sweep_floor=sweep_floor, spectral_floor=spectral_floor)
        d = ef.score - nf.score if np.isfinite(nf.score) else float("nan")
        if diagnostics is not None:
            diagnostics.append(dict(t_cpa=ef.t_cpa, s0=ef.score, s0_reversed=nf.score, d=d))
        out.append(dataclasses.replace(ef, score=d))
    return out
