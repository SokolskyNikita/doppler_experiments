"""Viterbi decoding with backtracking (Viterbi 1967; Quinn & Hannan 2001 §7.4; Sayed 2023 §39.4) of the OFF / ON(k) /
DIP(k) hidden Markov model of forward_backward.py: the single most probable state sequence, and the runs of frames it
holds a tone over. Every step of the sequence is an allowed transition, so a run's frequency never moves more than
the transition kernel's cap per frame, which per-frame maximum posterior decoding (forward_backward.runs) does not
guarantee."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from dopplertrack.components.tracking.forward_backward import _kernel
from dopplertrack.components.tracking.hmm_tracker_params import HMMTrackerParams


def _move(v: np.ndarray, log_ker: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The best predecessor of each grid cell under the frequency move: max over j of v[j] + log_ker[k - j], and that
    j. The first of tied predecessors (the lowest j) is taken."""
    cap = len(log_ker) // 2
    pad = np.full(len(v) + 2 * cap, -np.inf)
    pad[cap:cap + len(v)] = v
    cand = sliding_window_view(pad, 2 * cap + 1) + log_ker
    j = np.argmax(cand, axis=1)
    k = np.arange(len(v))
    return cand[k, j], k + j - cap


def viterbi_path(E: np.ndarray, valid: np.ndarray, dt: float, step_hz: float, f0s: np.ndarray, p: HMMTrackerParams
                 ) -> np.ndarray:
    """The most probable state per frame, as 0 for OFF, 1 + k for ON(k) and 1 + K + k for DIP(k), under the same
    initial, transition and emission terms as forward_backward.posterior. Invalid frames carry no log-likelihood
    ratio (E = 0)."""
    T, K = E.shape
    with np.errstate(divide="ignore"):                                    # log 0 = -inf: a transition that can't happen
        log_ker = np.log(_kernel(step_hz, float(f0s[-1]), dt, p))
        p_end, p_dip, p_up = dt / p.t_pass_s, dt / p.t_run_s, dt / p.t_dip_s
        birth = p.birth_rate * step_hz * dt
        l_birth, l_stay_off, l_end = np.log(birth), np.log(1 - birth * K), np.log(p_end)
        l_on_on, l_on_dip = np.log(1 - p_end - p_dip), np.log(p_dip)
        l_dip_on, l_dip_dip = np.log(p_up), np.log(1 - p_end - p_up)
    L = np.where(valid[:, None], E, 0.0)
    back_on = np.zeros((T, K), np.int64); back_dip = np.zeros((T, K), np.int64); back_off = np.zeros(T, np.int64)
    on, dip, off = l_birth + L[0], np.full(K, -np.inf), l_stay_off
    for n in range(1, T):
        mo, jo = _move(on, log_ker)
        md, jd = _move(dip, log_ker)
        from_on, from_dip, from_off = l_on_on + mo, l_dip_on + md, np.full(K, l_birth + off)
        pick = np.argmax(np.stack([from_on, from_dip, from_off]), axis=0)
        new_on = np.choose(pick, [from_on, from_dip, from_off]) + L[n]
        back_on[n] = np.choose(pick, [1 + jo, 1 + K + jd, np.zeros(K, np.int64)])
        to_dip_on, to_dip_dip = l_on_dip + mo, l_dip_dip + md
        stay = to_dip_dip > to_dip_on
        new_dip = np.where(stay, to_dip_dip, to_dip_on)
        back_dip[n] = np.where(stay, 1 + K + jd, 1 + jo)
        ko, kd = int(np.argmax(on)), int(np.argmax(dip))
        ends = [l_stay_off + off, l_end + on[ko], l_end + dip[kd]]
        e = int(np.argmax(ends))
        back_off[n] = (0, 1 + ko, 1 + K + kd)[e]
        on, dip, off = new_on, new_dip, ends[e]
    ko, kd = int(np.argmax(on)), int(np.argmax(dip))
    state = (0, 1 + ko, 1 + K + kd)[int(np.argmax([off, on[ko], dip[kd]]))]
    path = np.zeros(T, np.int64)
    for n in range(T - 1, -1, -1):
        path[n] = state
        if n:
            state = int(back_off[n] if state == 0 else back_on[n, state - 1] if state <= K else back_dip[n, state - 1 - K])
    return path


def viterbi_runs(E: np.ndarray, valid: np.ndarray, dt: float, step_hz: float, f0s: np.ndarray, p: HMMTrackerParams
                 ) -> list[tuple[int, int, np.ndarray]]:
    """Maximal runs of frames the most probable state sequence spends in ON or DIP, holding at least one ON frame, as
    (first frame, last frame, grid index per frame): the shape forward_backward.runs returns."""
    K = E.shape[1]
    path = viterbi_path(E, valid, dt, step_hz, f0s, p)
    out, n, T = [], 0, len(path)
    while n < T:
        if path[n] == 0:
            n += 1
            continue
        m = n
        while m + 1 < T and path[m + 1] != 0:
            m += 1
        if (path[n:m + 1] <= K).any():
            out.append((n, m, ((path[n:m + 1] - 1) % K).astype(np.int64)))
        n = m + 1
    return out
