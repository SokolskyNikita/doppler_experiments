"""Median spectral subtraction (Ramseier & Pieren 2024 eq. 11; spectral subtraction, Vary & Martin 2023 §12.3.2):
each frame's dB less its sliding median across frequency."""
from __future__ import annotations

import numpy as np


def whiten_frequency(L: np.ndarray, df: float, bg_hz: float, chunk: int = 4096) -> np.ndarray:
    """Each frame's dB less its running median across frequency within +-bg_hz, in place, a chunk of
    frames at a time."""
    from scipy.ndimage import median_filter
    size = 2 * int(round(bg_hz / df)) + 1
    for k in range(0, L.shape[1], chunk):
        L[:, k:k + chunk] -= median_filter(L[:, k:k + chunk], size=(size, 1), mode="nearest")
    return L
