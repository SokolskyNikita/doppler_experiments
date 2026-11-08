"""Harmonic-set log-likelihood ratio: per frame and fundamental, the log average likelihood ratio of a harmonic set
against noise (Eddy 1980 eqs. 14 and 22), each harmonic's term the random-phase sinusoid LR (Kay 1998 Problem 7.22):
Rician envelope under a tone, Exp(1) normalised power under noise. Ours: a two-point amplitude prior per harmonic
(absent with probability 1 - q, present at SNR a with probability q)."""
# old module: dopplertrack.components.tracking.rician_evidence
from __future__ import annotations

import numpy as np
from scipy.special import i0e

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.tracking.hmm_tracker_params import HMMTrackerParams


def harris_weight(nperseg: int, hop: int) -> float:
    """1 / (1 + 2 sum_m rho(m hop)^2): the large-K reciprocal of Welch's variance ratio for averaged, overlapped
    transforms (Harris 1978 eqs. 17-19), with rho the window's overlap correlation c(r) and rho^2 the correlation of
    the cells' powers: the share of a frame's log-likelihood ratio that is its own when Hann frames overlap."""
    w = np.hanning(nperseg)
    e = float(np.dot(w, w))
    rho = [float(np.dot(w[:-m * hop], w[m * hop:])) / e for m in range(1, (nperseg - 1) // hop + 1)]
    return 1.0 / (1.0 + 2.0 * sum(r * r for r in rho))


def llr(z: np.ndarray, a: float) -> np.ndarray:
    """ln f1(z) / f0(z) for z ~ Exp(1) under noise and Rician (noncentrality a) under a tone: -a + ln I0(2 sqrt(a z)),
    the random-phase sinusoid LR (Kay 1998 Problem 7.22; Eddy 1980 eq. 14)."""
    u = 2.0 * np.sqrt(a * np.maximum(z, 0.0))
    return -a + np.log(i0e(u)) + u                                       # ln I0(u) = ln i0e(u) + u


def normalised_power(sp: Spectrogram) -> np.ndarray:
    """z = P / sigma^2 per cell, (F, T); sigma^2 = median / ln 2, the frame's noise level across frequency."""
    if sp.whitening != "frequency":
        raise ValueError("lltrack needs a spectrogram whitened across frequency (whiten='frequency')")
    return np.log(2.0) * 10.0 ** (sp.S.astype(np.float64) / 10.0)


# old name: evidence
def harmonic_llr(z: np.ndarray, f: np.ndarray, f0s: np.ndarray, p: HMMTrackerParams, exclude: np.ndarray | None = None) -> np.ndarray:
    """(T, K): the log-likelihood ratio sum over observable harmonics of ln(1 - q + q e^l(z; a)) (Eddy 1980 eq. 22
    with a two-point amplitude prior), times frame_weight; a harmonic off the grid or in an excluded cell adds nothing.
    z is (F, T); exclude is (T, F)."""
    df = f[1] - f[0]
    T, K = z.shape[1], len(f0s)
    out = np.zeros((T, K))
    q = p.harmonic_prior
    for h in range(1, p.harmonics + 1):
        b = np.rint((h * f0s - f[0]) / df).astype(np.int64)
        ok = (b >= 0) & (b < len(f))
        bb = np.clip(b, 0, len(f) - 1)
        ell = llr(z[bb].T, p.tracker_snr)                                  # (T, K)
        term = np.logaddexp(np.log1p(-q), np.log(q) + ell)
        mask = np.broadcast_to(ok, (T, K)).copy()
        if exclude is not None:
            mask &= ~exclude[:, bb]
        out += np.where(mask, term, 0.0)
    return p.frame_weight * out
