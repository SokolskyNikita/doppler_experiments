"""Parameters of the HMM frequency-line tracker (Streit & Barrett 1990 §III): the harmonic log-likelihood ratio, the
hidden Markov model and the measurement."""
# old module: dopplertrack.components.tracking.likelihood_params
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


# old name: LLParams
@dataclass(frozen=True)
class HMMTrackerParams:
    tracker_snr: float = 4.0            # a, the "tracker SNR" (Streit & Barrett 1990 §III-D): per-cell, linear
    birth_rate: float = 1e-5          # beta, track initiation rate OFF -> ON, per Hz per second (S&B's u, as a rate)
    harmonic_prior: float = 0.5        # q, the prior that each harmonic is present
    t_pass_s: float = 120.0            # mean audible pass: ON/DIP -> OFF at dt / t_pass_s per frame
    t_run_s: float = 10.0              # mean run between dips: ON -> DIP at dt / t_run_s
    t_dip_s: float = 2.0               # mean dip (the fade state, ours): DIP -> ON at dt / t_dip_s
    slope_scale: float = 0.02          # Laplace scale of |df/dt| / f, per second (S&B's process noise d)
    max_rel_slope: float = 0.25        # cap on |df/dt| / f, per second (PLAN 6.1)
    grid_frac: float = 0.25            # fundamental grid step, as a fraction of a bin
    frame_weight: float = 1.0         # weight on each frame's log-likelihood ratio; harris_weight() tempers it for overlapping frames
    harmonics: int = 3
    exclusion_bins: int = 4
    families: int = 2
    min_track_s: float = 1.0
    estimator: str = "quinn2"
    harmonic_tol: float = 0.01
    max_order: int = 6


def with_params(p: HMMTrackerParams, **kw) -> HMMTrackerParams:
    return dataclasses.replace(p, **kw)
