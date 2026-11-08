"""Inflection-point consistency gate and clock anchor: a one-dimensional rectangular gate (Blackman & Popoli 1999
§6.3.1) on the gap between a pair's two modelled Doppler inflections, which must match the two fits' gap; event 1's
inflection can also set the clock."""
# old module: dopplertrack.components.scoring.steepest_gate
from __future__ import annotations

import numpy as np

from dopplertrack.components.scoring.doppler_inflection import INFLECTION_FLAT_RATIO, doppler_inflection
from dopplertrack.components.types import EventFit
from dopplertrack.core.propagation import ideal_curve


# old name: fitted_steepest_fall
def fitted_inflection(ev: EventFit, c: float, window_s: float = 60.0, smooth_s: float = 3.0,
                         flat_ratio: float = INFLECTION_FLAT_RATIO) -> float | None:
    """doppler_inflection of a fit's own ideal curve, in recording seconds (within 0.3 s of t_cpa_emit for the
    development fits)."""
    tq = ev.t_cpa_emit + np.arange(-window_s - smooth_s - 2, window_s + smooth_s + 3, 1.0)
    return doppler_inflection(tq, ideal_curve(tq, ev.f0, ev.v, ev.d, ev.t_cpa_emit, c=c) / ev.f0, ev.t_cpa_emit,
                         window_s, smooth_s, flat_ratio)


def gate_settings(ev1: EventFit, ev2: EventFit, c: float, tol_s: float | None, anchor: str, window_s: float,
                  smooth_s: float, flat_ratio: float) -> dict:
    """What inflection_gate needs, with the two fits' own inflections computed once."""
    return {"tol_s": tol_s, "anchor": anchor, "window_s": window_s, "smooth_s": smooth_s, "flat_ratio": flat_ratio,
            "fit": tuple(fitted_inflection(e, c, window_s, smooth_s, flat_ratio) for e in (ev1, ev2))}


# old name: steepest_gate
def inflection_gate(to1, r1, t_emit1: float, to2, r2, t_emit2: float, sf: dict) -> tuple[bool, bool, float | None]:
    """(kept, unplaceable, clock) for one triple's modelled curves (times, ratios) and its segments' emission CPA
    times. Unplaceable when an inflection can't be placed on either curve or fit: the triple is kept unchecked.
    Otherwise it is dropped when the curves' inflection gap differs from the fits' by more than sf["tol_s"]
    (None: no check), and when the anchor is the value "steepest" (CLI `--anchor`) clock is the audio-minus-unix
    offset that puts event 1's modelled inflection on its fit's; else clock is None."""
    m1 = doppler_inflection(to1, r1, t_emit1, sf["window_s"], sf["smooth_s"], sf["flat_ratio"])
    m2 = doppler_inflection(to2, r2, t_emit2, sf["window_s"], sf["smooth_s"], sf["flat_ratio"])
    f1, f2 = sf["fit"]
    if m1 is None or m2 is None or f1 is None or f2 is None:
        return True, True, None
    if sf["tol_s"] is not None and abs((m2 - m1) - (f2 - f1)) > sf["tol_s"]:
        return False, False, None
    return True, False, (f1 - m1 if sf["anchor"] == "steepest" else None)
