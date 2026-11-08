"""Result types shared between methods: a fitted Doppler event and a frequency track."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class EventFit:
    t_cpa: float        # heard CPA time in the recording, s (reception time of the f0 crossing)
    t_cpa_emit: float   # emission-time CPA (t_cpa - d/c): Ferguson & Quinn 1994's t_c
    f0: float           # rest fundamental, Hz
    v: float            # speed, m/s
    d: float            # distance of closest approach (slant range at CPA), m
    t_start: float
    t_end: float
    score: float        # the fit's score: sweep-weighted contrast (dB) by default, mean dB along the curve for
                        # objective="brightness", S1 after custom_rescore_zscore, D after rescore_surrogate
    f_pre: float
    f_post: float
    weak: str | None = None  # why the fit couldn't be made (the other fields are then NaN); None for a fit

    def to_dict(self):
        """The fields as a dict; `weak` only when set, so existing JSON is unchanged."""
        d = asdict(self)
        if d["weak"] is None:
            del d["weak"]
        return d

    @classmethod
    def unfit(cls, t_start: float, t_end: float, reason: str) -> "EventFit":
        nan = float("nan")
        return cls(t_cpa=nan, t_cpa_emit=nan, f0=nan, v=nan, d=nan, t_start=t_start, t_end=t_end, score=nan,
                   f_pre=nan, f_post=nan, weak=reason)


@dataclass
class Track:
    """A frequency track, the least-squares fit's input, from ridge() or any other tracker."""
    t: np.ndarray                      # recording seconds
    f: np.ndarray                      # Hz: `harmonic` times the fundamental
    amplitude: np.ndarray | None = None  # per point; the weighted fit weights each point by amplitude²
    valid: np.ndarray | None = None    # False where the tracker has no measurement
    harmonic: int = 1

    def usable(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(t, fundamental frequency, amplitude) at the valid, finite points."""
        t, f = np.asarray(self.t, float), np.asarray(self.f, float)
        a = np.ones_like(f) if self.amplitude is None else np.asarray(self.amplitude, float)
        ok = np.isfinite(t) & np.isfinite(f) & np.isfinite(a) & (a > 0)
        if self.valid is not None:
            ok &= np.asarray(self.valid, bool)
        return t[ok], f[ok] / self.harmonic, a[ok]
