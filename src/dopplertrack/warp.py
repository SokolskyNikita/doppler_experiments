"""Emission-time resampling (de-Dopplerisation) and its tone score (PLAN Phase 2 item 8).

For an observer, a recording clock and a trajectory, the recording is evaluated at the reception
times of a uniform grid of emission times u: t_r = u + |p(u) - x|/c, so t = tau + r/c in Kelly &
Wilson 1993 eq. 12 (the Markdown copy drops its minus sign) and t_s = t_r - D/c in Ramseier & Pieren
eq. 9. A steady emitted tone from the right geometry then becomes a stationary line.
- Interpolation: a Hamming-windowed sinc of 2L taps (Ramseier & Pieren eqs. 7-8); linear and nearest
  are kept for the test that measures each one's floor (Howell 1986 3.1).
- Aliasing: the output grid has the input's rate. Undoing a recede reads the input up to
  1 + R'/c samples per output sample, so the input is low-passed at sr / (2 max_rate) first, and a
  geometry needing a rate above max_rate is refused.
- No amplitude correction: the score below normalises each block, identically for every candidate.

Score: Hann blocks of the warped signal; each block's dB less its median across frequency within
+-bg_hz (Ramseier & Pieren eq. 11), not over time, which would erase the stationary line; per block
and fundamental, the harmonics' evidence pooled first (weights (N + 1 - h) / N, eq. 12 of the PDF);
then a path over blocks in fundamental space with an off state, a tone constant within each block,
strict (one fundamental per event) or with bounded drift, and up to two tone families."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.signal as ss
from scipy.ndimage import median_filter


# ---- resampling --------------------------------------------------------------------------

def lowpass(x: np.ndarray, sr: int, fc: float, order: int = 8) -> np.ndarray:
    """Zero-phase Butterworth low-pass."""
    sos = ss.butter(order, fc / (sr / 2), output="sos")
    return ss.sosfiltfilt(sos, np.asarray(x, np.float64))


def bandpass(x: np.ndarray, sr: int, lo: float, hi: float, order: int = 8) -> np.ndarray:
    sos = ss.butter(order, [lo / (sr / 2), hi / (sr / 2)], btype="band", output="sos")
    return ss.sosfiltfilt(sos, np.asarray(x, np.float64))


def resample_at(x: np.ndarray, idx: np.ndarray, method: str = "sinc", taps: int = 16, chunk: int = 1 << 16) -> np.ndarray:
    """x evaluated at fractional sample indices idx. Indices whose support leaves x give NaN."""
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


@dataclass
class Warped:
    y: np.ndarray            # the warped signal on the emission grid, NaN outside the support
    u: np.ndarray            # emission times (the trajectory's clock), s
    max_rate: float          # largest d t_r / d u over the support


def warp(x: np.ndarray, sr: int, audio_minus_traj: float, t_traj: np.ndarray, enu: np.ndarray, obs_enu: np.ndarray,
         c: float, u0: float, u1: float, valid: np.ndarray | None = None, method: str = "sinc", taps: int = 16,
         max_rate: float = 1.35, prefiltered: bool = False) -> Warped:
    """The recording x (sample 0 at audio time 0) at the reception times of emission times u0..u1 on a
    grid at sr. Trajectory times t_traj and audio time differ by audio_minus_traj (the clock).
    Positions are interpolated linearly between the trajectory's samples; an emission time is used only
    where both neighbouring samples are valid. Raises ValueError if the geometry needs a reading rate
    above max_rate. x is low-passed at sr / (2 max_rate) unless prefiltered."""
    u = u0 + np.arange(int(np.floor((u1 - u0) * sr))) / sr
    inside = (u >= t_traj[0]) & (u <= t_traj[-1])
    if valid is not None:
        j = np.clip(np.searchsorted(t_traj, u) - 1, 0, len(t_traj) - 2)
        inside &= np.asarray(valid, bool)[j] & np.asarray(valid, bool)[j + 1]
    p = np.stack([np.interp(u, t_traj, enu[:, k]) for k in range(3)], axis=1)
    r = np.linalg.norm(p - obs_enu[None, :], axis=1)
    t_r = u + r / c + audio_minus_traj
    rate = np.gradient(t_r, u)
    mr = float(np.max(rate[inside])) if inside.any() else 1.0
    if mr > max_rate:
        raise ValueError(f"geometry needs a reading rate of {mr:.3f} > {max_rate}")
    xf = x if prefiltered else lowpass(x, sr, sr / (2 * max_rate))
    y = resample_at(xf, t_r * sr, method, taps)
    y[~inside] = np.nan
    return Warped(y, u, mr)


# ---- blocks, background, pooling, path -----------------------------------------------------

def block_db(y: np.ndarray, sr: int, nperseg: int = 8192, hop: int = 2048, nfft: int | None = None,
             min_support: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """dB power of Hann blocks of y, only blocks whose samples are all (min_support of them) inside
    the support. Returns (block centres in samples, frequencies, dB (B, F))."""
    nfft = nfft or nperseg
    w = ss.get_window("hann", nperseg)
    ok = np.isfinite(y)
    starts = np.arange(0, len(y) - nperseg + 1, hop)
    keep = [s for s in starts if ok[s:s + nperseg].mean() >= min_support]
    f = np.fft.rfftfreq(nfft, 1 / sr)
    if not keep:
        return np.array([]), f, np.zeros((0, len(f)))
    seg = np.stack([np.nan_to_num(y[s:s + nperseg]) * w for s in keep])
    P = np.abs(np.fft.rfft(seg, n=nfft, axis=1)) ** 2
    return np.array(keep) + nperseg / 2, f, 10 * np.log10(P + 1e-30)


def across_frequency(db: np.ndarray, df: float, bg_hz: float = 10.0) -> np.ndarray:
    """Each block's dB less its running median across frequency within +-bg_hz."""
    size = 2 * int(round(bg_hz / df)) + 1
    return db - median_filter(db, size=(1, size), mode="nearest")


def harmonic_weights(n: int) -> np.ndarray:
    return (n + 1 - np.arange(1, n + 1)) / n


def pooled(S: np.ndarray, f: np.ndarray, f0s: np.ndarray, harmonics: int = 3, near: int = 1,
           exclude: np.ndarray | None = None) -> np.ndarray:
    """(B, K): per block and fundamental, the weighted mean over h = 1..harmonics of the largest
    value within +-near bins of h f0. Cells marked in exclude (B, F) are -inf."""
    S = np.where(exclude, -np.inf, S) if exclude is not None else S
    df = f[1] - f[0]
    w = harmonic_weights(harmonics)
    out = np.zeros((S.shape[0], len(f0s)))
    for h, wh in zip(range(1, harmonics + 1), w):
        j = np.rint(h * f0s / df).astype(int)
        best = np.full((S.shape[0], len(f0s)), -np.inf)
        for o in range(-near, near + 1):
            jj = np.clip(j + o, 0, S.shape[1] - 1)
            best = np.maximum(best, S[:, jj])
        out += wh * np.where(np.isfinite(best), best, 0.0)
    return out / w.sum()


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


@dataclass
class ToneScore:
    score: float             # the families' path totals per block, summed
    f0: list                 # each family's fundamental (strict) or median fundamental (drift)
    on: float                # share of blocks the first family is on
    blocks: int


def tone_score(S: np.ndarray, f: np.ndarray, f0_lo: float, f0_hi: float, harmonics: int = 3,
               theta: float = 0.0, birth: float = 0.0, drift_step_hz: float | None = None,
               range_frac: float = 0.02, families: int = 2, exclude_bins: int = 2) -> ToneScore:
    """The event's tone score on background-normalised blocks S (B, F). Strict when drift_step_hz is
    None, else bounded drift with a fundamental grid of drift_step_hz (at most one bin) and one grid
    step per block. A second family is sought after excluding the first's harmonics."""
    if S.shape[0] == 0:
        return ToneScore(0.0, [], 0.0, 0)
    df = f[1] - f[0]
    grid = df if drift_step_hz is None else min(df, drift_step_hz)
    f0s = np.arange(f0_lo, f0_hi + grid / 2, grid)
    excl = np.zeros(S.shape, bool)
    total, f0_out, on_share = 0.0, [], 0.0
    for fam in range(families):
        E = pooled(S, f, f0s, harmonics, exclude=excl)
        if drift_step_hz is None:
            s, k, mask = path_strict(E, theta, birth)
            fb = np.full(S.shape[0], f0s[k])
        else:
            s, idx, mask = path_drift(E, f0s, theta, birth, 1, range_frac)
            fb = np.where(idx >= 0, f0s[np.maximum(idx, 0)], np.nan)
        if fam > 0 and s <= 0:
            break
        total += s
        f0_out.append(float(np.nanmedian(fb[mask])) if mask.any() else float("nan"))
        if fam == 0:
            on_share = float(mask.mean())
        for b in np.nonzero(mask)[0]:                                     # exclude this family's harmonics
            for h in range(1, harmonics + 1):
                j = int(round(h * fb[b] / df))
                excl[b, max(j - exclude_bins, 0):j + exclude_bins + 1] = True
    return ToneScore(total, f0_out, on_share, S.shape[0])
