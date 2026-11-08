"""Frequency-line tracking by dynamic programming (Viterbi) over blocks (Ramseier & Pieren 2023 §II.C.3 eq. 12),
with an off state for an absent signal, as Streit & Barrett 1990's zero state (§I). Strict (one fundamental per
event) or with bounded drift (at most `step` grid points per block: RP's slope bound delta). `birth` is the cost of
each switch on or off, and `theta` a per-block threshold subtracted first; RP's path has neither (ours)."""
from __future__ import annotations

import numpy as np


def path_strict(E: np.ndarray, theta: float, birth: float) -> tuple[float, int, np.ndarray]:
    """One fundamental per event (column of E) with an off state: per block on (E - theta) or off
    (0), a cost `birth` for each switch on and each switch off. Returns (best total / blocks,
    the fundamental's index, on mask)."""
    B, K = E.shape
    r = E - theta
    on = r[0] - birth; off = np.zeros(K)
    back_on = np.zeros((B, K), bool); back_off = np.zeros((B, K), bool)    # True: came from "on"
    for b in range(1, B):
        n_on = np.maximum(on, off - birth); back_on[b] = on >= off - birth
        n_off = np.maximum(off, on - birth); back_off[b] = on - birth > off
        on, off = n_on + r[b], n_off
    end_on = on - birth
    total = np.maximum(end_on, off)
    k = int(np.argmax(total))
    state = end_on[k] >= off[k]
    mask = np.zeros(B, bool)
    for b in range(B - 1, -1, -1):
        mask[b] = state
        state = back_on[b, k] if state else back_off[b, k]
    return float(total[k] / B), k, mask


def _drift_dp(r: np.ndarray, birth: float, step: int) -> tuple[float, np.ndarray]:
    """Viterbi over K on-states (a fundamental index) and one off state. On k at block b may come
    from on k' with |k - k'| <= step, or from off at a cost `birth`; off may come from off or from
    any on at a cost `birth`. Returns (total, per-block index, -1 when off)."""
    B, K = r.shape
    on = r[0] - birth; off = 0.0
    back = np.zeros((B, K), np.int64)                    # previous on-index, or -1 for off
    back_off = np.full(B, -1, np.int64)                  # previous on-index for off, or -1 for off
    for b in range(1, B):
        cand = np.full((2 * step + 1, K), -np.inf)
        for o in range(-step, step + 1):
            lo, hi = max(0, -o), min(K, K - o)
            cand[o + step, lo:hi] = on[lo + o:hi + o]
        j = np.argmax(cand, axis=0)
        stay = cand[j, np.arange(K)]
        born = off - birth
        back[b] = np.where(born > stay, -1, np.arange(K) + j - step)
        kk = int(np.argmax(on))
        n_off = max(off, on[kk] - birth)
        back_off[b] = kk if on[kk] - birth > off else -1
        on, off = np.maximum(stay, born) + r[b], n_off
    kk = int(np.argmax(on))
    total, state = (on[kk] - birth, kk) if on[kk] - birth >= off else (off, -1)
    idx = np.full(B, -1, np.int64)
    for b in range(B - 1, -1, -1):
        idx[b] = state
        if b == 0:
            break
        state = back[b, state] if state >= 0 else back_off[b]
    return float(total), idx


def path_drift(E: np.ndarray, f0s: np.ndarray, theta: float, birth: float, step: int, range_frac: float
               ) -> tuple[float, np.ndarray, np.ndarray]:
    """A fundamental per block with an off state, moving at most `step` grid points per block, inside
    a range of range_frac of its centre: the DP runs in each sliding sub-band of that width (half-
    overlapping) and the best is kept. Returns (best total / blocks, fundamental index per block or
    -1, on mask)."""
    B, K = E.shape
    r = E - theta
    width = max(1, int(np.ceil(range_frac * f0s.mean() / (f0s[1] - f0s[0])))) if K > 1 else 1
    best = (-np.inf, np.full(B, -1))
    for a in range(0, max(K - width, 0) + 1, max(1, width // 2)):
        sl = slice(a, min(a + width + 1, K))
        total, idx = _drift_dp(r[:, sl], birth, step)
        if total > best[0]:
            best = (total, np.where(idx >= 0, idx + a, -1))
    return float(best[0] / B), best[1], best[1] >= 0
