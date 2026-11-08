"""Windowed-sinc interpolation with a Hamming kernel, read at arbitrary times: the asynchronous resampling of
Ramseier & Pieren 2023 §II.C.2 eqs. 7-8. Also zero-phase Butterworth low- and band-pass filters."""
from __future__ import annotations

import numpy as np
import scipy.signal as ss


def lowpass(x: np.ndarray, sr: int, fc: float, order: int = 8) -> np.ndarray:
    """Zero-phase (forward-backward) Butterworth low-pass; the magnitude response is applied twice."""
    sos = ss.butter(order, fc / (sr / 2), output="sos")
    return ss.sosfiltfilt(sos, np.asarray(x, np.float64))


def bandpass(x: np.ndarray, sr: int, lo: float, hi: float, order: int = 8) -> np.ndarray:
    """Zero-phase (forward-backward) Butterworth band-pass."""
    sos = ss.butter(order, [lo / (sr / 2), hi / (sr / 2)], btype="band", output="sos")
    return ss.sosfiltfilt(sos, np.asarray(x, np.float64))


def resample_at(x: np.ndarray, idx: np.ndarray, method: str = "sinc", taps: int = 16, chunk: int = 1 << 16) -> np.ndarray:
    """x evaluated at fractional sample indices idx: windowed-sinc interpolation over 2 taps samples with a Hamming
    kernel (Ramseier & Pieren eqs. 7-8), or linear or nearest. Indices whose support leaves x give NaN."""
    x = np.asarray(x, np.float64)
    idx = np.asarray(idx, np.float64)
    out = np.full(len(idx), np.nan)
    if method == "nearest":
        k = np.rint(idx).astype(np.int64)
        ok = (k >= 0) & (k < len(x))
        out[ok] = x[k[ok]]
        return out
    if method == "linear":
        k = np.floor(idx).astype(np.int64)
        ok = (k >= 0) & (k + 1 < len(x))
        a = idx[ok] - k[ok]
        out[ok] = (1 - a) * x[k[ok]] + a * x[k[ok] + 1]
        return out
    if method != "sinc":
        raise ValueError(f"unknown method {method!r}")
    L = taps
    m = np.arange(-L + 1, L + 1)                                         # offsets from floor(idx)
    for i0 in range(0, len(idx), chunk):
        s = idx[i0:i0 + chunk]
        k0 = np.floor(s).astype(np.int64)
        ok = (k0 - L + 1 >= 0) & (k0 + L < len(x))
        if not ok.any():
            continue
        kk = k0[ok][:, None] + m[None, :]
        d = s[ok][:, None] - kk                                          # |d| < L
        w = np.sinc(d) * (0.54 + 0.46 * np.cos(np.pi * d / L))
        res = np.full(len(s), np.nan)
        res[ok] = np.einsum("ij,ij->i", w, x[kk])
        out[i0:i0 + chunk] = res
    return out
