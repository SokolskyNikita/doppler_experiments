"""Candidate observers scored by the curves they would hear: the curve integral (curve_integral) of each event,
maximised over time shift and f0 scale. Both exports are custom_ (no standard name): see their docstrings."""
# old module: dopplertrack.components.scoring.trajectory_brightness
from __future__ import annotations


import numpy as np

from dopplertrack.core.propagation import speed_of_sound
from dopplertrack.components.search.types import Segment
from dopplertrack.components.scoring.curve_integral import EventWindow
from dopplertrack.components.scoring.modelled_curve import modelled_curve


# old name: locked_score
def custom_locked_score(ev1: EventWindow, ev2: EventWindow, seg1: Segment, seg2: Segment, obs_enu,
                 t_heard1: float, c: float | None = None,
                 shifts=np.arange(-8, 8.01, 0.5), f0_scales=np.arange(0.95, 1.0501, 0.005),
                 curves=None, t0_map: float | None = None, f0_scales2=None, temperature_c: float | None = None):
    """No standard name: two events scored with one shared time shift, by conditional maximisation.

    Event 1's placement is swept over small time shifts and f0 scales (both are
    measurements). Event 2 is placed with the *same* time shift, event 1's best, so its
    timing relative to event 1 is fixed purely by flight geometry; only its f0 scale is
    swept. The total s1 + s2 is therefore not the joint maximum of s1 + s2 over the shift.
    Nearest standard idea: non-coherent combining at a shared clock bias (Axelrad 2011,
    collective detection), which sums the events before maximising.
    curves: (to1, r1, to2, r2) from modelled_curve, if the caller already has them.
    t0_map: audio = unix + t0_map; by default the modelled heard CPA of event 1 lands on the measured one.
    f0_scales2: event 2's f0 sweep, if it differs from event 1's.
    Returns (total, s1, s2, best_shift).
    """
    c = speed_of_sound() if c is None else c
    # map unix time -> audio time so that the modelled heard-CPA of event 1 lands on the measured one
    t0_map = ev1.fit.t_cpa - t_heard1 if t0_map is None else t0_map
    if curves is None:
        to1, r1 = modelled_curve(seg1, obs_enu, c, temperature_c)
        to2, r2 = modelled_curve(seg2, obs_enu, c, temperature_c)
    else:
        to1, r1, to2, r2 = curves
    sc1 = ev1.sweep_scores(to1 + t0_map, r1, shifts, f0_scales)
    i, j = np.unravel_index(np.argmax(sc1), sc1.shape)
    s1, sh = float(sc1[i, j]), float(shifts[i])
    s2 = float(ev2.sweep_scores(to2 + t0_map, r2, [sh], f0_scales if f0_scales2 is None else f0_scales2).max())
    return s1 + s2, s1, s2, sh


# old name: single_score
def custom_single_score(ev: EventWindow, seg: Segment, obs_enu, t_heard: float, c=None,
                 shifts=np.arange(-8, 8.01, 0.5), f0_scales=np.arange(0.95, 1.0501, 0.005),
                 temperature_c: float | None = None):
    """No standard name: one event's curve integral, maximised over time shift and f0 scale (as the spectrogram
    GLRT maximises over nuisance parameters, Kay 1998 §7.6.4), with the clock set so the modelled heard CPA lands
    on the fit's."""
    c = speed_of_sound() if c is None else c
    to, r = modelled_curve(seg, obs_enu, c, temperature_c)
    t0_map = ev.fit.t_cpa - t_heard
    return float(ev.sweep_scores(to + t0_map, r, shifts, f0_scales).max())
