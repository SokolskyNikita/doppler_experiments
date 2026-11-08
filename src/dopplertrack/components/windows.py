"""A detection, as collective detection (Axelrad 2011) uses it: its bounds, a coarse tone and a coarse heard CPA."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Window:
    """What detection keeps of an event: its bounds, a coarse tone and a coarse heard CPA (the clock prior)."""
    t_start: float
    t_end: float
    f0: float
    t_cpa: float
    score: float

    @classmethod
    def from_detection(cls, e) -> "Window":
        return cls(float(e.t_start), float(e.t_end), float(e.f0), float(e.t_cpa), float(e.score))
