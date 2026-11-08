"""Local median whitening: per-bin median normalisation over a window, then a spectral floor (Vary & Martin 2023
§12.3.4.2), which removes tones that are stationary over the window."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram


def local_whiten(sp: Spectrogram, spectral_floor: float = 0.0) -> Spectrogram:
    """Subtract each bin's median over this window's valid frames (removing tones stationary over it), then
    clip from below at `spectral_floor` (old name: floor; Vary & Martin 2023 §12.3.4.2). A spectrogram
    whitened across frequency (sp.whitening == "frequency") keeps its stationary tones: it is only
    clipped at the spectral floor."""
    if sp.whitening == "frequency":
        S = np.maximum(sp.S, spectral_floor).astype(np.float32)
        S[:, ~sp.valid] = spectral_floor
        return sp.with_S(S)
    S = np.maximum(sp.S - sp.bin_median(), spectral_floor).astype(np.float32)
    S[:, ~sp.valid] = spectral_floor
    return sp.with_S(S)
