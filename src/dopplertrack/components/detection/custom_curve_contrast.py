"""No standard name: the level along a curve less the mean of two sidebands at +-CONTRAST_DF, weighted by how fast the
curve sweeps. Nearest standard idea: a replica correlator (Kay 1998 §4.3) against a local background estimate; ours
takes the background from two frequency sidebands only and uses Doppler-rate weights rather than the signal."""
# old module: dopplertrack.components.detection.curve_contrast
from __future__ import annotations

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram

CONTRAST_DF = 0.04     # sideband offset as a fraction of frequency
SWEEP_FLOOR = 0.15     # weight given to the flat tails of a curve, relative to its fastest-sweeping part


# old name: sweep_weights
def custom_sweep_weights(ratio, t, axis=-1, sweep_floor: float = SWEEP_FLOOR):
    """Per-sample weights proportional to |d ratio / dt| (the sweeping part of a Doppler
    curve carries the information about the pass; flat asymptotes also fit any steady tone), normalised to
    a peak of 1 per curve, plus sweep_floor (default SWEEP_FLOOR)."""
    g = np.abs(np.gradient(ratio, t, axis=axis))
    g = np.nan_to_num(g, nan=0.0)
    peak = np.max(g, axis=axis, keepdims=True)
    return g / np.maximum(peak, 1e-12) + sweep_floor


# old name: curve_contrast
def custom_curve_contrast(sp: Spectrogram, t, f, contrast_df: float = CONTRAST_DF):
    """Per-sample ridge contrast: level on the curve minus the mean of two sidebands.
    A broadband burst is as bright off the curve as on it and so scores ~0. Off-grid -> 0. The sidebands are at
    +-contrast_df (a fraction of frequency, default CONTRAST_DF)."""
    return sp.sample(t, f) - 0.5 * (sp.sample(t, f * (1 + contrast_df)) + sp.sample(t, f * (1 - contrast_df)))
