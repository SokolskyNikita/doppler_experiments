"""Robust location and scale of a decoy null: the median and the normalized MAD, MADN = MAD/0.6745 = 1.4826 MAD
(Maronna et al. 2019, p. 32 and eq. 2.63), of n decoy rows' scores, drawn uniformly with replacement under a seed
derived from what is being tested. The event and window decoy nulls are this with their own scores."""
from __future__ import annotations

import hashlib

import numpy as np


def null_seed(key) -> int:
    """A 64-bit seed from repr(key), so the same subject always draws the same rows."""
    return int(hashlib.sha256(repr(key).encode()).hexdigest()[:16], 16)


def draw_rows(n_rows: int, n: int, seed: int) -> np.ndarray:
    """n row indices into a table of n_rows, uniform with replacement, sorted."""
    return np.sort(np.random.default_rng(seed).integers(0, n_rows, n))


# old name: robust_spread
def median_madn(scores) -> tuple[float, float]:
    """(median, MADN) of the scores: MADN = 1.4826 * median absolute deviation (Maronna et al. 2019, eq. 2.63)."""
    s = np.asarray(scores, float)
    med = float(np.median(s))
    return med, float(1.4826 * np.median(np.abs(s - med)))


def sample_sha256(idx: np.ndarray) -> str:
    """The drawn rows' hash, recorded beside a null so that its sample can be checked."""
    return hashlib.sha256(np.ascontiguousarray(idx).tobytes()).hexdigest()
