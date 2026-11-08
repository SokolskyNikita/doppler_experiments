"""Scaled forward-backward recursions (Quinn & Hannan 2001 §7.3.3; Sayed 2023 §39.3) for the OFF / ON(k) / DIP(k)
hidden Markov model: the state occupancy probabilities (Streit & Barrett 1990 eq. 2.11), and the runs of frames it
holds a tone over. DIP is our own fade state (ours); OFF is S&B's zero state."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve1d

from dopplertrack.components.tracking.hmm_tracker_params import HMMTrackerParams


def _kernel(step_hz: float, f_ref: float, dt: float, p: HMMTrackerParams) -> np.ndarray:
    scale = max(p.slope_scale * f_ref * dt / step_hz, 1e-6)              # grid steps
    cap = max(1, int(np.ceil(p.max_rel_slope * f_ref * dt / step_hz)))
    d = np.arange(-cap, cap + 1)
    k = np.exp(-np.abs(d) / scale)
    return k / k.sum()


def _conv(v: np.ndarray, ker: np.ndarray) -> np.ndarray:
    return convolve1d(v, ker, mode="constant")                           # mass moved off the grid leaves the band


def posterior(E: np.ndarray, valid: np.ndarray, dt: float, step_hz: float, f0s: np.ndarray, p: HMMTrackerParams
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scaled forward-backward. Returns the state occupancy probabilities of ON (T, K), DIP (T, K) and OFF (T,).
    Invalid frames carry no log-likelihood ratio (E = 0)."""
    T, K = E.shape
    ker = _kernel(step_hz, float(f0s[-1]), dt, p)
    p_end, p_dip, p_up = dt / p.t_pass_s, dt / p.t_run_s, dt / p.t_dip_s
    birth = p.birth_rate * step_hz * dt                                  # per grid cell
    B = birth * K
    L = np.where(valid[:, None], E, 0.0)
    L = L - L.max(axis=1, keepdims=True).clip(min=0.0)                    # scale each frame; OFF's 0 shifts alike
    shift = E.max(axis=1).clip(min=0.0) * valid
    e = np.exp(L)
    e_off = np.exp(-shift)
    a_on = np.zeros((T, K)); a_dip = np.zeros((T, K)); a_off = np.zeros(T); c = np.zeros(T)
    on0, dip0, off0 = birth * e[0], np.zeros(K), (1 - B) * e_off[0] + 0.0
    s = on0.sum() + off0
    a_on[0], a_dip[0], a_off[0], c[0] = on0 / s, dip0, off0 / s, s
    for n in range(1, T):
        co, cd = _conv(a_on[n - 1], ker), _conv(a_dip[n - 1], ker)
        m = a_on[n - 1].sum() + a_dip[n - 1].sum()
        on = ((1 - p_end - p_dip) * co + p_up * cd + birth * a_off[n - 1]) * e[n]
        dip = (p_dip * co + (1 - p_end - p_up) * cd) * e_off[n]
        off = ((1 - B) * a_off[n - 1] + p_end * m) * e_off[n]
        s = on.sum() + dip.sum() + off
        a_on[n], a_dip[n], a_off[n], c[n] = on / s, dip / s, off / s, s
    b_on = np.ones((T, K)); b_dip = np.ones((T, K)); b_off = np.ones(T)
    for n in range(T - 2, -1, -1):
        x_on = e[n + 1] * b_on[n + 1]
        x_dip = e_off[n + 1] * b_dip[n + 1]
        x_off = e_off[n + 1] * b_off[n + 1]
        on = _conv((1 - p_end - p_dip) * x_on + p_dip * x_dip, ker) + p_end * x_off
        dip = _conv(p_up * x_on + (1 - p_end - p_up) * x_dip, ker) + p_end * x_off
        off = (1 - B) * x_off + birth * x_on.sum()
        b_on[n], b_dip[n], b_off[n] = on / c[n + 1], dip / c[n + 1], off / c[n + 1]
    g_on, g_dip, g_off = a_on * b_on, a_dip * b_dip, a_off * b_off
    tot = g_on.sum(axis=1) + g_dip.sum(axis=1) + g_off
    return g_on / tot[:, None], g_dip / tot[:, None], g_off / tot


def runs(g_on: np.ndarray, g_dip: np.ndarray) -> list[tuple[int, int, np.ndarray]]:
    """Maximal runs of frames whose gate occupancy probability P(ON or DIP) exceeds 0.5 (Streit & Barrett 1990
    §III-D) holding at least one frame where ON outweighs DIP, as (first frame, last frame, grid index per frame by
    per-frame maximum posterior decoding, Sayed 2023 eq. 39.1)."""
    present = (g_on.sum(axis=1) + g_dip.sum(axis=1)) > 0.5
    on = g_on.sum(axis=1) > g_dip.sum(axis=1)
    out, n, T = [], 0, len(present)
    while n < T:
        if not present[n]:
            n += 1
            continue
        m = n
        while m + 1 < T and present[m + 1]:
            m += 1
        if on[n:m + 1].any():
            out.append((n, m, np.argmax(g_on[n:m + 1] + g_dip[n:m + 1], axis=1).astype(np.int64)))
        n = m + 1
    return out
