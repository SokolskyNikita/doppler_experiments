"""Nearest-neighbour association (Blackman & Popoli 1999 §1.3.2, p.45) of a further event to a flight: the flight
whose modelled curve, on the recording's clock, scores highest at the observer."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.search.types import Segment
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.core.propagation import speed_of_sound
from dopplertrack.data.coverage import DEFAULT_MAX_RANGE_M


def pick_flight(sp: Spectrogram, ev: EventFit, segs: list[Segment], obs_enu, t0_map: float, shift: float,
                harmonics: int = 1, c=None, max_range_m=DEFAULT_MAX_RANGE_M, alive_pad_s=300.0,
                temperature_c: float | None = None, f0_scales=None, pad_s: float = 40.0, n: int = 160,
                spectral_floor: float = 0.0) -> tuple[int, float]:
    """Which flight does an observer at obs_enu hear as `ev`, given the recording's time map
    (audio = unix + t0_map) and the time shift already chosen for event 1? Returns
    (segment index, its score: the best of EventWindow.sweep_scores at that shift); (-1, 0) if no flight near at
    that time scores above 0. f0_scales is the f0 sweep (default 0.95 to 1.05 by 0.005); pad_s, n and spectral_floor
    build the event's EventWindow."""
    from dopplertrack.components.scoring.curve_integral import EventWindow
    from dopplertrack.components.scoring.modelled_curve import modelled_curve
    c = speed_of_sound() if c is None else c
    w = EventWindow.from_fit(sp, ev, harmonics, pad_s=pad_s, n=n, spectral_floor=spectral_floor)
    f0_scales = np.arange(0.95, 1.0501, 0.005) if f0_scales is None else f0_scales
    t_unix = ev.t_cpa - t0_map
    best, best_s = -1, 0.0
    for k, seg in enumerate(segs):
        if not (seg.t[0] - alive_pad_s <= t_unix <= seg.t[-1] + alive_pad_s):
            continue
        if np.linalg.norm(seg.enu - obs_enu, axis=1).min() > max_range_m:
            continue
        to, r = modelled_curve(seg, obs_enu, c, temperature_c)
        sc = float(w.sweep_scores(to + t0_map, r, [shift], f0_scales).max())
        if sc > best_s:
            best, best_s = k, sc
    return best, best_s
