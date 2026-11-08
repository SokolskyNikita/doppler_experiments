"""A flight segment: one trace's 1 Hz emission times, ENU positions and speeds."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Segment:
    trace_idx: int
    icao: str
    t: np.ndarray       # emission times (unix s), 1 Hz
    enu: np.ndarray     # (N,3)
    speed: np.ndarray   # (N,) m/s, the 3-D speed in ENU (climb rate included), not ground-track speed
    valid: np.ndarray | None = None  # the original trace covers this sample; geometry may interpolate a hole
