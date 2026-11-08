"""Grids for a coarse-to-fine search (Axelrad 2011, Direct Positioning and Fig. 16): the residual shift, the f0
sweep and the curve's samples a window is scored over, the nuisance parameters the score is maximised over."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from dopplertrack.components.scoring.log_view import LOG_DU, SUB_S, log_offsets

F0_SPAN = 0.25                # each candidate's own tone: the f0 sweep about detection's coarse tone


@dataclass(frozen=True)
class Sweep:
    """The residual shift and the f0 sweep (fractions around the window's coarse tone), and the curve's samples: n per
    SUB_S stretch, so a window's own n scales with its length (n_for)."""
    shift_s: float
    shift_step: float
    f0_span: float
    f0_step: float
    n: int = 80
    # the views' log-frequency step and best-stretch length; left out of repr, which seeds the window decoy nulls,
    # so a sweep at the defaults draws R1's rows
    log_du: float = field(default=LOG_DU, repr=False)
    sub_s: float = field(default=SUB_S, repr=False)

    def n_for(self, length_s: float) -> int:
        return max(self.n, int(round(self.n * length_s / self.sub_s)))

    def shifts(self):
        return np.arange(-self.shift_s, self.shift_s + 1e-9, self.shift_step)

    def offsets(self):
        return log_offsets(self.f0_span, self.f0_step, self.log_du)

    def f0_scales(self):
        return np.exp(self.offsets() * self.log_du)


def fine_sweep(f0_span: float = F0_SPAN) -> Sweep:
    return Sweep(8.0, 0.5, f0_span, 0.005)


def coarse_sweep(f0_span: float = F0_SPAN) -> Sweep:
    """A COARSE_M cell's span: up to COARSE_M / sqrt(2) from its centre, about 4 s of travel, widens the shift, and the
    curve's shape changes with it, so the f0 sweep widens by 2 points. 60 samples per SUB_S stretch at 1 s and 1 % (the
    fourth design step: 60 samples over a whole 240 s window left 30 in the stretch and missed the eagle cam's peak)."""
    return Sweep(14.0, 1.0, f0_span + 0.02, 0.01, 60)
