"""The f0 sweep: a grid of scales of an event's fitted f0, a nuisance parameter the score is maximised over (Kay 1998
§7.6.4), widened to its hypotheses' f0 ranges."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.scoring.curve_integral import EventWindow


def f0_sweep(w: EventWindow, hyps: list) -> np.ndarray:
    """Scales of the event's fitted f0 to sweep in scoring: today's +-5 %, widened to every hypothesis's f0 range."""
    lo = min([0.95] + [h.f0_range[0] / w.fit.f0 for h in hyps])
    hi = max([1.05] + [h.f0_range[1] / w.fit.f0 for h in hyps])
    return np.arange(lo, hi + 1e-9, 0.005)
