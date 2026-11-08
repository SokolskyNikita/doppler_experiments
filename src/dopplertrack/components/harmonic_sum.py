"""Harmonic sum: per frame (or block) and fundamental, a weighted sum of spectral values at the harmonics (Eddy 1980
eqs. 16-17, 25: the "weighted sum of spectral estimates"). Ours: a weighted mean over the observable harmonics of
the largest value within +-near bins; on dB input, as the trackers pass it, this is the log of a weighted geometric
mean of the harmonics' levels rather than a sum of powers."""
# old module: dopplertrack.components.harmonic_pooling
from __future__ import annotations

import numpy as np


def harmonic_weights(n: int) -> np.ndarray:
    return (n + 1 - np.arange(1, n + 1)) / n


# old name: pooled
def harmonic_sum(S: np.ndarray, f: np.ndarray, f0s: np.ndarray, harmonics: int = 3, near: int = 1,
           exclude: np.ndarray | None = None) -> np.ndarray:
    """(B, K): per block and fundamental, the weighted mean over the observable harmonics h = 1..harmonics
    of the largest value within +-near bins of h f0.

    A harmonic is observable in a block when at least one of its bins lies on the grid and outside the
    cells marked in exclude (B, F); the mean is normalised by the observable harmonics' weights, so a
    harmonic beyond the grid's top or under an excluded cell neither scores nor counts as observed. A
    fundamental with no observable harmonic in a block scores 0 there."""
    df = f[1] - f[0]
    w = harmonic_weights(harmonics)
    num = np.zeros((S.shape[0], len(f0s)))
    den = np.zeros((S.shape[0], len(f0s)))
    for h, wh in zip(range(1, harmonics + 1), w):
        j = np.rint((h * f0s - f[0]) / df).astype(int)
        best = np.full((S.shape[0], len(f0s)), -np.inf)
        for o in range(-near, near + 1):
            jj = j + o
            on_grid = (jj >= 0) & (jj < S.shape[1])
            vals = np.full((S.shape[0], len(f0s)), -np.inf)
            vals[:, on_grid] = S[:, jj[on_grid]]
            if exclude is not None:
                ex = np.ones((S.shape[0], len(f0s)), bool)
                ex[:, on_grid] = exclude[:, jj[on_grid]]
                vals[ex] = -np.inf
            best = np.maximum(best, vals)
        seen = np.isfinite(best)
        num += wh * np.where(seen, best, 0.0)
        den += wh * seen
    return np.where(den > 0, num / np.maximum(den, 1e-12), 0.0)
