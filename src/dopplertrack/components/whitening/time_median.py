"""Time-axis median whitening, a prewhitener (Kay 1998 §4.4, Example 4.3) with each bin's noise level taken as its
median: in dB, each frequency bin less its median over time (global, or block medians linearly interpolated)."""
from __future__ import annotations

import numpy as np


def whiten_time(L: np.ndarray, valid: np.ndarray | None, hop_s: float, whiten_window_s: float | None) -> np.ndarray:
    """Subtract each bin's median (global, or over blocks of `whiten_window_s` linearly interpolated
    between block centres), in place where it can be. Medians are taken over valid frames only;
    valid=None means all frames are valid."""
    if valid is not None and valid.all():
        valid = None
    T = L.shape[1]
    w = None if whiten_window_s is None else int(whiten_window_s / hop_s)
    if w is None or w >= T:
        if valid is None:
            return L - np.median(L, axis=1, keepdims=True)
        if not valid.any():
            return L
        for k in range(L.shape[0]):
            L[k] -= np.median(L[k, valid])
        return L
    # block medians (cheap, adequate for slow drifts; not a sliding median), linearly blended between
    # block centres to avoid seams; a block without a valid frame contributes no centre
    nb = int(np.ceil(T / w))
    centers: list[float] = []
    meds: list[np.ndarray] = []
    for b in range(nb):
        sl = slice(b * w, min((b + 1) * w, T))
        if valid is None:
            meds.append(np.median(L[:, sl], axis=1))
        elif valid[sl].any():
            meds.append(np.median(L[:, sl][:, valid[sl]], axis=1))
        else:
            continue
        centers.append((sl.start + sl.stop) / 2)
    if not centers:
        return L
    cm = np.array(meds)                                                  # (nb, F)
    idx = np.arange(T)
    out = L if L.dtype == np.float32 else L.astype(np.float32)
    for k in range(L.shape[0]):                                          # row by row: no (F, T) float64 copy
        out[k] = L[k] - np.interp(idx, centers, cm[:, k])
    return out
