"""An event's hypothesis: one local optimum of its fit with the box of pointwise profile-likelihood intervals
(Raue 2009, eqs. 8 and 10) in speed, k = v^2/d, emission CPA and f0. "Hypothesis" is a candidate here, not a
tested H0 or H1 (ours)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from dopplertrack.components.types import EventFit

# old name: K
MAX_OPTIMA = 3                       # optima kept per source
MODEL_ERROR_FACTOR = 3.0    # both thresholds are multiplied by its square: a misspecified model's profile measures
                            # spread about theta*, the KLIC minimiser (White 1982, Thm 2.2), not distance to the truth,
                            # and the model-error study measured that distance at 2.8-3.2x the information bound in
                            # slant range on Livermore (docs/experiments/2026-11-04-model-error.md). The one counted
                            # retune of stage B.
V_BOUNDS = (10.0, 300.0)
D_BOUNDS = (100.0, 30000.0)
K_BOUNDS = (V_BOUNDS[0] ** 2 / D_BOUNDS[1], V_BOUNDS[1] ** 2 / D_BOUNDS[0])
TAU_REACH_S = 60.0          # tau profiles stop this far from the optimum


def k_bounds(v_bounds: tuple, d_bounds: tuple) -> tuple[float, float]:
    """The range of k = v^2/d that speed and distance bounds allow (K_BOUNDS for the defaults)."""
    return (v_bounds[0] ** 2 / d_bounds[1], v_bounds[1] ** 2 / d_bounds[0])


@dataclass
class Hypothesis:
    """One optimum of one event's fit with its profile-interval box; admits holds the CPA rows inside it."""
    sources: list
    f0: float
    v: float
    d: float
    t_cpa_emit: float
    t_cpa: float
    v_range: tuple
    k_range: tuple
    tau_range: tuple
    f0_range: tuple
    weak: list = field(default_factory=list)      # practically non-identifiable parameters (Raue 2009, Def. 1)
    corr_v_d: float | None = None                 # speed-distance correlation, where the source gives one
    identified: bool | None = None                # fit_track's heuristic acceptance check, for "ls"
    d_range: tuple | None = None                  # "gate" only: admits by the rectangular distance gate instead of k

    @property
    def k(self) -> float:
        return self.v * self.v / self.d

    def admits(self, cpa: pd.DataFrame) -> np.ndarray:
        v = cpa.v.to_numpy(np.float64)
        d = cpa.d.to_numpy(np.float64)
        in_v = (v >= self.v_range[0]) & (v <= self.v_range[1])
        if self.d_range is not None:
            return in_v & (d >= self.d_range[0]) & (d <= self.d_range[1])
        k = v * v / d
        return in_v & (k >= self.k_range[0]) & (k <= self.k_range[1])

    def contains(self, other: "Hypothesis") -> bool:
        return (self.v_range[0] <= other.v <= self.v_range[1] and self.k_range[0] <= other.k <= self.k_range[1]
                and self.tau_range[0] <= other.t_cpa_emit <= self.tau_range[1])

    def event(self, like: EventFit) -> EventFit:
        c = self.d / (self.t_cpa - self.t_cpa_emit) if self.t_cpa > self.t_cpa_emit else 343.0
        return EventFit(t_cpa=self.t_cpa, t_cpa_emit=self.t_cpa_emit, f0=self.f0, v=self.v, d=self.d,
                        t_start=like.t_start, t_end=like.t_end, score=like.score,
                        f_pre=self.f0 * c / (c - self.v), f_post=self.f0 * c / (c + self.v))

    def to_dict(self):
        return asdict(self)


def admitted(cpa: pd.DataFrame, hyps: list[Hypothesis]) -> np.ndarray:
    """Rows of the CPA table some hypothesis admits."""
    mask = np.zeros(len(cpa), bool)
    for h in hyps:
        mask |= h.admits(cpa)
    return mask
