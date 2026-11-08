"""Viterbi track over spectral peaks with a zero state (Streit & Barrett 1990 §II; ridge-curve path optimisation,
Iatsenko 2016 §3) (PLAN Phase 2 item 3): each tone as a line with an explicit start, end and gaps.

A track is found on the whitened image and measured on the original STFT:
- **Finding.** A Viterbi over the strongest spectral peaks of each frame, plus an "off" state (S&B's zero
  state) with birth and death penalties (source unknown; not Hermes 1988). Ours: additive dB scores, not a
  likelihood. A cell's reward is its whitened level less `theta_db`,
  so steady noise scores below zero and a path ends where the tone does. Frames the spectrogram
  marks invalid are crossed without a measurement, for at most `max_bridge_s`. Tracks are taken one
  at a time, each path's cells removed before the next is sought.
- **Measuring.** Each point's frequency is refined below the bin width on the original STFT, since
  whitening shifts a peak that sits near the floor it partly subtracted. The estimators are parabolic
  interpolation on log magnitude, Candan's three-sample estimator in its Hann form, and Quinn's FTI(2)
  on the unwindowed DFT.
- **Segment rules.** Custom cuts at a weak run, a rise and a hop, a link across a short gap, and re-pairing
  at a crossing. Each is a separate function applied after the Viterbi, so each can be tested and
  switched alone.
- **Harmonic links.** Two overlapping tracks whose frequency ratio holds near p/q are linked; a
  group's orders are the smallest integers consistent with its links, whose gcd is 1 (source unknown; not Hermes 1988).

The original STFT comes from the samples (SampleSTFT), because a Spectrogram holds whitened dB only.
A later version may carry the un-whitened dB in the Spectrogram instead.

This module is the finding step. Measuring is in frequency_estimators, the segment rules in segment_rules, the
harmonic links in harmonic_links, and track_window runs them in that order."""
from __future__ import annotations


import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.tracking.frequency_estimators import measure_path
from dopplertrack.components.tracking.types import SampleSTFT, Track, TrackParams


def _peaks(S: np.ndarray, band: np.ndarray, M: int) -> tuple[np.ndarray, np.ndarray]:
    """Per frame, the M highest local maxima along frequency inside `band`: bins (T, M), -1 for
    none, and their levels (T, M), -inf for none."""
    F, T = S.shape
    loc = np.zeros_like(S, bool)
    loc[1:-1] = (S[1:-1] > S[:-2]) & (S[1:-1] >= S[2:])
    loc &= band[:, None]
    lev = np.where(loc, S, -np.inf)
    idx = np.argsort(-lev, axis=0)[:M].T                                   # (T, M)
    val = np.take_along_axis(lev.T, idx, axis=1)
    idx = np.where(np.isfinite(val), idx, -1)
    return idx, val


def viterbi_segments(bins: np.ndarray, levels: np.ndarray, valid: np.ndarray, t: np.ndarray, f: np.ndarray,
                     p: TrackParams) -> list[tuple[int, int, np.ndarray]]:
    """Best path through peaks and "off": the runs of frames it spends on a peak, as
    (first frame, last frame, bin per frame or -1 across invalid frames)."""
    T, M = bins.shape
    df = float(f[1] - f[0])
    vidx = np.nonzero(valid)[0]
    if len(vidx) == 0:
        return []
    reward = levels - p.theta_db                                           # -inf where no peak
    U = np.full(M + 1, -np.inf); U[M] = 0.0                                # state M is "off"
    back = np.zeros((len(vidx), M + 1), np.int64)
    prev_bins = None; prev_t = None
    for n, k in enumerate(vidx):
        b = bins[k]
        new = np.full(M + 1, -np.inf)
        from_off = U[M] - p.birth
        if prev_bins is None:
            cand = np.full((M, 1), from_off); src = np.full((M, 1), M)
        else:
            dt = t[k] - prev_t
            jump = np.abs(b[:, None] - prev_bins[None, :]).astype(float)   # (M_now, M_prev)
            cap = np.maximum(2.0, p.max_rel_slope * f[np.maximum(b, 0)] * dt / df + 1)[:, None]
            ok = (b[:, None] >= 0) & (prev_bins[None, :] >= 0) & (jump <= cap) & (dt <= p.max_bridge_s + 1e-9)
            stay = np.where(ok, U[None, :M] - p.jump_cost * jump, -np.inf)
            cand = np.concatenate([stay, np.full((M, 1), from_off)], axis=1)
            src = np.broadcast_to(np.r_[np.arange(M), M], cand.shape)
        best = np.argmax(cand, axis=1)
        new[:M] = cand[np.arange(M), best] + reward[k]
        back[n, :M] = src[np.arange(M), best]
        to_off = U[:M] - p.death
        j = int(np.argmax(to_off))
        if to_off[j] > U[M]:
            new[M] = to_off[j]; back[n, M] = j
        else:
            new[M] = U[M]; back[n, M] = M
        U = np.where(np.isfinite(new), new, -np.inf)
        prev_bins, prev_t = b, t[k]
    end = U[:M] - p.death
    s = int(np.argmax(end)) if end.max() > U[M] else M
    states = np.empty(len(vidx), np.int64)
    for n in range(len(vidx) - 1, -1, -1):
        states[n] = s
        s = back[n, s]
    out, n = [], 0
    while n < len(vidx):
        if states[n] == M:
            n += 1
            continue
        m = n
        while m + 1 < len(vidx) and states[m + 1] != M:
            m += 1
        k0, k1 = vidx[n], vidx[m]
        path = np.full(k1 - k0 + 1, -1, np.int64)
        for q in range(n, m + 1):
            path[vidx[q] - k0] = bins[vidx[q], states[q]]
        out.append((int(k0), int(k1), path))
        n = m + 1
    return out


def find_tracks(win: Spectrogram, stft: SampleSTFT, f_lo: float, f_hi: float,
                p: TrackParams = TrackParams()) -> list[Track]:
    """Tracks in a whitened, unclipped window (local_whiten(..., spectral_floor=-inf)), measured on stft,
    before any segment rule."""
    S = np.where(win.valid[None, :], win.S, -np.inf)
    band = (win.f >= f_lo) & (win.f <= f_hi)
    bins, levels = _peaks(S, band, p.peaks_per_frame)
    tracks = []
    for _ in range(p.max_tracks):
        segs = viterbi_segments(bins, levels, win.valid, win.t, win.f, p)
        segs = [s for s in segs if win.t[s[1]] - win.t[s[0]] >= p.min_track_s]
        if not segs:
            break
        for k0, k1, path in segs:
            tracks.append(measure_path(win, stft, k0, path, p))
            for i, b in enumerate(path):
                if b >= 0:
                    row = bins[k0 + i]
                    kill = (row >= 0) & (np.abs(row - b) <= p.exclusion_bins)
                    bins[k0 + i, kill] = -1; levels[k0 + i, kill] = -np.inf
    tracks.sort(key=lambda tr: tr.start)
    return tracks
