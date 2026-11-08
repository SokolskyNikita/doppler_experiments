"""The usability check (S6): the detections a search can use, and the share of the recording's frames that are valid."""
from __future__ import annotations

import numpy as np


def usable_events(found: list) -> list:
    """The detections with a fit: none weak, every one with a finite f0."""
    return [e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)]


def valid_share(sp) -> float:
    """The share of the spectrogram's frames that are valid (1 when it has no mask)."""
    return float(np.mean(sp.valid)) if sp.valid is not None else 1.0
