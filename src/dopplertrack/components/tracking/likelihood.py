"""Frequency tracks from a likelihood (PLAN Phase 2 item 3, round 3; docs/proposals/2026-11-04-tracker-likelihood.md).

Each cell's power over the frame's noise level across frequency, z = P / sigma^2, is Exp(1) in noise and Rician
with a tone of per-cell SNR a; the cell's evidence is the log-likelihood ratio l(z; a) = -a + ln I0(2 sqrt(a z))
(Kay I Ex. 7.16). On a grid of fundamentals, each observable harmonic h = 1..3 is present with prior q, so the
frame's evidence for fundamental k is sum_h ln(1 - q + q e^l_h). A hidden Markov model with OFF, ON(k) and DIP(k)
(a tone still there but under the noise: Streit & Barrett's lost state) is decoded by forward-backward; a track is
a run of frames whose posterior P(ON or DIP) exceeds 0.5 and that holds an ON frame. Transitions per frame: birth
OFF -> ON(k) at a prior per Hz per second, the end of a pass at dt/T_pass, into and out of a dip at dt/T_run and
dt/T_dip, and frequency moves by a Laplace kernel of scale slope_scale * f per second, capped at max_rel_slope * f.
Frequencies are measured on the original STFT per harmonic and combined with weights h^2 A_h^2 (Quinn & Hannan
eq. 3.11).

The spectrogram must be whitened across frequency (compute_spectrogram(whiten="frequency")): its S is then
10 log10(P / median P over +-bg_hz), and z = ln 2 * 10^(S/10)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import convolve1d
from scipy.special import i0e

import dopplertrack.components.tracking.viterbi as ft
from dopplertrack.components.spectrogram import Spectrogram


@dataclass(frozen=True)
class LLParams:
    design_snr: float = 4.0            # a, the per-cell SNR of the tone the likelihood assumes (linear)
    birth_prior: float = 1e-5          # beta, births per Hz per second
    harmonic_prior: float = 0.5        # q, the prior that each harmonic is present
    t_pass_s: float = 120.0            # mean audible pass
    t_run_s: float = 10.0              # mean run between dips
    t_dip_s: float = 2.0               # mean dip
    slope_scale: float = 0.02          # Laplace scale of |df/dt| / f, per second
    max_rel_slope: float = 0.25        # cap on |df/dt| / f, per second (PLAN 6.1)
    grid_frac: float = 0.25            # fundamental grid step, as a fraction of a bin
    frame_weight: float = 1.0         # evidence per frame; harris_weight() tempers it for overlapping frames
    harmonics: int = 3
    exclusion_bins: int = 4
    families: int = 2
    min_track_s: float = 1.0
    estimator: str = "quinn2"
    harmonic_tol: float = 0.01
    max_order: int = 6


def with_params(p: LLParams, **kw) -> LLParams:
    return dataclasses.replace(p, **kw)


def harris_weight(nperseg: int, hop: int) -> float:
    """1 / (1 + 2 sum_m rho(m hop)^2): the share of a frame's evidence that is its own when Hann frames overlap,
    with rho the window's overlap correlation (Harris 1978) and rho^2 the correlation of the cells' powers."""
    w = np.hanning(nperseg)
    e = float(np.dot(w, w))
    rho = [float(np.dot(w[:-m * hop], w[m * hop:])) / e for m in range(1, (nperseg - 1) // hop + 1)]
    return 1.0 / (1.0 + 2.0 * sum(r * r for r in rho))


def llr(z: np.ndarray, a: float) -> np.ndarray:
    """ln f1(z) / f0(z) for z ~ Exp(1) under noise and Rician (noncentrality a) under a tone."""
    u = 2.0 * np.sqrt(a * np.maximum(z, 0.0))
    return -a + np.log(i0e(u)) + u                                       # ln I0(u) = ln i0e(u) + u


def normalised_power(sp: Spectrogram) -> np.ndarray:
    """z = P / sigma^2 per cell, (F, T); sigma^2 = median / ln 2, the frame's noise level across frequency."""
    if sp.whitening != "frequency":
        raise ValueError("lltrack needs a spectrogram whitened across frequency (whiten='frequency')")
    return np.log(2.0) * 10.0 ** (sp.S.astype(np.float64) / 10.0)


def evidence(z: np.ndarray, f: np.ndarray, f0s: np.ndarray, p: LLParams, exclude: np.ndarray | None = None) -> np.ndarray:
    """(T, K): sum over observable harmonics of ln(1 - q + q e^l(z; a)); a harmonic off the grid or in an excluded
    cell adds nothing. z is (F, T); exclude is (T, F)."""
    df = f[1] - f[0]
    T, K = z.shape[1], len(f0s)
    out = np.zeros((T, K))
    q = p.harmonic_prior
    for h in range(1, p.harmonics + 1):
        b = np.rint((h * f0s - f[0]) / df).astype(np.int64)
        ok = (b >= 0) & (b < len(f))
        bb = np.clip(b, 0, len(f) - 1)
        ell = llr(z[bb].T, p.design_snr)                                  # (T, K)
        term = np.logaddexp(np.log1p(-q), np.log(q) + ell)
        mask = np.broadcast_to(ok, (T, K)).copy()
        if exclude is not None:
            mask &= ~exclude[:, bb]
        out += np.where(mask, term, 0.0)
    return p.frame_weight * out


def _kernel(step_hz: float, f_ref: float, dt: float, p: LLParams) -> np.ndarray:
    scale = max(p.slope_scale * f_ref * dt / step_hz, 1e-6)              # grid steps
    cap = max(1, int(np.ceil(p.max_rel_slope * f_ref * dt / step_hz)))
    d = np.arange(-cap, cap + 1)
    k = np.exp(-np.abs(d) / scale)
    return k / k.sum()


def _conv(v: np.ndarray, ker: np.ndarray) -> np.ndarray:
    return convolve1d(v, ker, mode="constant")                           # mass moved off the grid leaves the band


def posterior(E: np.ndarray, valid: np.ndarray, dt: float, step_hz: float, f0s: np.ndarray, p: LLParams
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Forward-backward. Returns the posteriors of ON (T, K), DIP (T, K) and OFF (T,). Invalid frames carry no
    evidence."""
    T, K = E.shape
    ker = _kernel(step_hz, float(f0s[-1]), dt, p)
    p_end, p_dip, p_up = dt / p.t_pass_s, dt / p.t_run_s, dt / p.t_dip_s
    birth = p.birth_prior * step_hz * dt                                  # per grid cell
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
    """Maximal runs of frames with P(ON or DIP) > 0.5 holding at least one frame where ON outweighs DIP, as
    (first frame, last frame, posterior-mode grid index per frame)."""
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


def _measure(win: Spectrogram, stft: ft.SampleSTFT, k0: int, path: np.ndarray, f0s: np.ndarray, E: np.ndarray,
             p: LLParams) -> ft.Track:
    n = len(path)
    t = win.t[k0:k0 + n]
    f = np.full(n, np.nan); amp = np.full(n, np.nan); level = np.full(n, np.nan)
    off = int(round(win.f[0] / stft.df))
    for i, k in enumerate(path):
        if not win.valid[k0 + i]:
            continue
        level[i] = E[k0 + i, k]
        frame = stft.frame(float(t[i]))
        est, wts = [], []
        for h in range(1, p.harmonics + 1):
            b = int(round((h * f0s[k] - win.f[0]) / win.df))
            if b < 1 or b >= len(win.f) - 1:
                continue
            fh, ah = ft.refine(stft, frame, b + off, p.estimator)
            if abs(fh / h - f0s[k]) <= 1.5 * win.df:                      # a harmonic measured off its line is dropped
                est.append(fh / h); wts.append(h * h * 10 ** (ah / 10))      # Quinn & Hannan eq. 3.11: h^2 A_h^2
        if est:
            f[i] = float(np.average(est, weights=wts)); amp[i] = 10 * np.log10(max(wts))
    keep = np.isfinite(f)
    return ft.Track(t.copy(), f, amp, level, keep, np.where(keep, path, -1))


def ll_track(sp: Spectrogram, stft: ft.SampleSTFT, t_start: float, t_end: float, f_lo: float, f_hi: float,
             p: LLParams = LLParams()) -> ft.EventTracks:
    """Families of tracks whose fundamental lies in [f_lo, f_hi] between t_start and t_end; sp is whitened across
    frequency."""
    top = min(sp.f[-1], p.harmonics * f_hi + 2 * sp.df)
    win = sp.crop(t_start, t_end, max(f_lo - 2 * sp.df, sp.f[0]), top)
    z = normalised_power(win)
    step = p.grid_frac * win.df
    f0s = np.arange(f_lo, f_hi + step / 2, step)
    dt = float(np.median(np.diff(win.t))) if len(win.t) > 1 else 0.25
    excl = np.zeros((len(win.t), len(win.f)), bool)
    tracks: list[ft.Track] = []
    for _ in range(p.families):
        E = evidence(z, win.f, f0s, p, exclude=excl)
        g_on, g_dip, _ = posterior(E, win.valid, dt, step, f0s, p)
        found = [r for r in runs(g_on, g_dip) if win.t[r[1]] - win.t[r[0]] >= p.min_track_s]
        if not found:
            break
        for k0, k1, path in found:
            tracks.append(_measure(win, stft, k0, path, f0s, E, p))
            for i, k in enumerate(path):
                for h in range(1, p.harmonics + 1):
                    b = int(round((h * f0s[k] - win.f[0]) / win.df))
                    excl[k0 + i, max(b - p.exclusion_bins, 0):max(b + p.exclusion_bins + 1, 0)] = True
    tracks = ft.resolve_crossings(tracks, ft.TrackParams(), win.df)
    links = ft.harmonic_links(tracks, ft.TrackParams(harmonic_tol=p.harmonic_tol, max_order=p.max_order))
    groups = ft.harmonic_groups(tracks, links)
    return ft.EventTracks(tracks, links, groups)
