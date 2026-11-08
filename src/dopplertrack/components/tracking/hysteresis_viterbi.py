"""Hysteresis-threshold Viterbi tracker: hysteresis thresholding (Nixon & Aguado 2012 pp. 172-178) with tentative
-> confirmed tracks (Blackman & Popoli 1999 p. 42), decoded by the Viterbi algorithm (PLAN Phase 2 item 3, round 2).
Not an HMM: the path maximises additive dB scores, not a likelihood. Ours: confirmation is N-of-N frames in the dB
domain.

A Viterbi over a grid of fundamentals per frame, the frame's harmonic sum taken first
(harmonic_sum.harmonic_sum: the observable harmonics h = 1..3, weights (N + 1 - h)/N), with three kinds of state
(OFF is Streit & Barrett 1990's zero state; BORN and ON are ours):
- OFF, no track;
- BORN_a, a tentative track at age a = 1..n_born frames, rewarded E - theta_birth;
- ON, a confirmed, continuing track, rewarded E - theta_cont, with theta_cont below theta_birth.
OFF -> BORN_1 costs `birth`, ON -> OFF costs `death`, BORN -> OFF is free (a failed birth makes no
track). A track must hold n_born frames above theta_birth before it is ON, so a short run of noise
can't afford to be born while a weak tone already ON can continue through a dip. Transitions between
fundamentals are one step in fundamental space with an L1 cost per grid step, capped at the physical
sweep bound; frames the spectrogram marks invalid are crossed without a measurement, for at most
max_bridge_s. Up to two tone families are decoded, the second after excluding the first's harmonic
cells; a second family harmonically related to the first joins it. Round 1's resolve_crossings runs
after decoding. Frequencies are measured on the original STFT (frequency_estimators.refine), per harmonic,
and combined into the fundamental weighted by amplitude squared, A_h^2. That is not inverse-variance weighting,
which needs h^2 A_h^2 (Quinn & Hannan 2001 Theorem 8, §3.3; as hmm_tracker does)."""
# old module: dopplertrack.components.tracking.hmm
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.harmonic_sum import harmonic_sum
from dopplertrack.components.tracking.frequency_estimators import refine
from dopplertrack.components.tracking.harmonic_links import harmonic_groups, harmonic_links
from dopplertrack.components.tracking.segment_rules import resolve_crossings
from dopplertrack.components.tracking.types import EventTracks, SampleSTFT, Track, TrackParams


# old name: HMMParams
@dataclass(frozen=True)
class HysteresisParams:
    theta_birth: float = 9.5          # dB: a BORN frame's reward is E - theta_birth
    theta_cont: float = 6.0           # dB: an ON frame's reward is E - theta_cont
    n_born: int = 4                   # frames a track spends BORN before it is ON (1 s at 0.25 s)
    birth: float = 6.0
    death: float = 6.0
    jump_cost: float = 0.1            # dB per bin of fundamental change between frames
    max_rel_slope: float = 0.25       # cap on |df/dt| / f, per second (PLAN 6.1)
    max_bridge_s: float = 5.0
    grid_frac: float = 0.25           # fundamental grid step, as a fraction of a bin
    harmonics: int = 3
    exclusion_bins: int = 4            # a smeared line plus the harmonic sum's +-1 bin
    families: int = 2
    min_track_s: float = 1.0
    estimator: str = "quinn2"
    harmonic_tol: float = 0.01
    max_order: int = 6


def _capped_l1_max(prev: np.ndarray, cap: int, cost: float) -> np.ndarray:
    """out[k] = max over |k - j| <= cap of prev[j] - cost |k - j|: the larger of a running maximum of
    prev[j] + cost j over j in [k - cap, k] and of prev[j] - cost j over j in [k, k + cap]."""
    K = len(prev)
    idx = np.arange(K) * cost
    pad = np.full(cap, -np.inf)
    left = np.lib.stride_tricks.sliding_window_view(np.r_[pad, prev + idx], cap + 1).max(axis=1) - idx
    right = np.lib.stride_tricks.sliding_window_view(np.r_[prev - idx, pad], cap + 1).max(axis=1) + idx
    return np.maximum(left, right)


def _argmax_near(prev: np.ndarray, k: int, cap: int, cost: float) -> int:
    lo, hi = max(0, k - cap), min(len(prev), k + cap + 1)
    j = np.arange(lo, hi)
    return int(j[np.argmax(prev[lo:hi] - cost * np.abs(j - k))])


def decode(E: np.ndarray, t: np.ndarray, valid: np.ndarray, step_hz: float, f0s: np.ndarray, p: HysteresisParams
           ) -> list[tuple[int, int, np.ndarray]]:
    """Best state path; returns the runs that reached ON as (first frame, last frame, grid index per frame,
    -1 where a frame is invalid)."""
    T, K = E.shape
    vidx = np.nonzero(valid)[0]
    if len(vidx) == 0:
        return []
    cost = p.jump_cost * (f0s[1] - f0s[0]) / step_hz if K > 1 else 0.0       # dB per grid step
    nb = p.n_born
    NEG = -np.inf
    # layers 0..nb-1: BORN_1..BORN_nb; layer nb: ON
    V = np.full((len(vidx), nb + 1, K), NEG)
    off = np.zeros(len(vidx))
    off_from = np.full(len(vidx), -2, np.int64)          # -1: off, else the layer it died from (only ON)
    off_k = np.zeros(len(vidx), np.int64)
    rb, rc = E[vidx] - p.theta_birth, E[vidx] - p.theta_cont
    V[0, 0] = -p.birth + rb[0]
    for n in range(1, len(vidx)):
        dt = t[vidx[n]] - t[vidx[n - 1]]
        if dt > p.max_bridge_s + 1e-9:
            off[n] = max(off[n - 1], float(np.max(V[n - 1, nb])) - p.death)
            off_from[n] = -1 if off[n] == off[n - 1] else nb
            off_k[n] = int(np.argmax(V[n - 1, nb]))
            V[n, 0] = off[n - 1] - p.birth + rb[n]
            continue
        cap = max(2, int(np.ceil(p.max_rel_slope * f0s[-1] * dt / (f0s[1] - f0s[0])))) if K > 1 else 0
        # BORN_1 from OFF
        V[n, 0] = off[n - 1] - p.birth + rb[n]
        for a in range(1, nb):                                            # BORN_a+1 from BORN_a
            V[n, a] = _capped_l1_max(V[n - 1, a - 1], cap, cost) + rb[n]
        src = np.maximum(V[n - 1, nb - 1], V[n - 1, nb])                   # ON from BORN_nb or ON
        V[n, nb] = _capped_l1_max(src, cap, cost) + rc[n]
        kk = int(np.argmax(V[n - 1, nb])); die = V[n - 1, nb, kk] - p.death
        born_end = float(np.max(V[n - 1, :nb]))                           # a failed birth goes OFF for free
        best = max(off[n - 1], die, born_end)
        off[n] = best
        if best == off[n - 1]:
            off_from[n] = -1
        elif best == die:
            off_from[n] = nb; off_k[n] = kk
        else:
            a_fail, k_fail = np.unravel_index(int(np.argmax(V[n - 1, :nb])), (nb, K))
            off_from[n] = int(a_fail); off_k[n] = int(k_fail)
    # end: ON pays death, BORN ends free
    end_on = float(np.max(V[-1, nb])) - p.death
    end_born = float(np.max(V[-1, :nb]))
    a_end, k_end = (int(x) for x in np.unravel_index(int(np.argmax(V[-1, :nb])), (nb, K)))
    choices: list[tuple[float, int, int]] = [(float(off[-1]), -1, 0), (end_on, nb, int(np.argmax(V[-1, nb]))),
                                             (end_born, a_end, k_end)]
    _, layer, k = max(choices, key=lambda c: c[0])
    states = np.full(len(vidx), -1, np.int64); layers = np.full(len(vidx), -1, np.int64)
    for n in range(len(vidx) - 1, -1, -1):
        states[n] = k if layer >= 0 else -1; layers[n] = layer
        if n == 0:
            break
        dt = t[vidx[n]] - t[vidx[n - 1]]
        cap = max(2, int(np.ceil(p.max_rel_slope * f0s[-1] * dt / (f0s[1] - f0s[0])))) if K > 1 else 0
        if layer < 0:                                                     # OFF came from off, ON (died) or BORN (failed)
            if off_from[n] == -1:
                continue
            layer, k = int(off_from[n]), int(off_k[n])
        elif layer == 0:                                                  # BORN_1 came from OFF
            layer = -1
        elif layer < nb:
            k = _argmax_near(V[n - 1, layer - 1], k, cap, cost); layer -= 1
        else:                                                             # ON from BORN_nb or ON
            vb_arr = V[n - 1, nb - 1]; vo_arr = V[n - 1, nb]
            kb, ko = _argmax_near(vb_arr, k, cap, cost), _argmax_near(vo_arr, k, cap, cost)
            vb, vo = vb_arr[kb] - cost * abs(kb - k), vo_arr[ko] - cost * abs(ko - k)
            k, layer = (ko, nb) if vo >= vb else (kb, nb - 1)
    out, n = [], 0
    while n < len(vidx):
        if layers[n] < 0:
            n += 1
            continue
        m = n
        while m + 1 < len(vidx) and layers[m + 1] >= 0:
            m += 1
        if (layers[n:m + 1] == nb).any():                                 # a run that never became ON is no track
            k0, k1 = vidx[n], vidx[m]
            path = np.full(k1 - k0 + 1, -1, np.int64)
            for q in range(n, m + 1):
                path[vidx[q] - k0] = states[q]
            out.append((int(k0), int(k1), path))
        n = m + 1
    return out


def _measure(win: Spectrogram, stft: SampleSTFT, k0: int, path: np.ndarray, f0s: np.ndarray, E: np.ndarray,
             p: HysteresisParams) -> Track:
    n = len(path)
    t = win.t[k0:k0 + n]
    f = np.full(n, np.nan); amp = np.full(n, np.nan); level = np.full(n, np.nan)
    off = int(round(win.f[0] / stft.df))
    for i, k in enumerate(path):
        if k < 0:
            continue
        level[i] = E[k0 + i, k]
        frame = stft.frame(float(t[i]))
        est, wts = [], []
        for h in range(1, p.harmonics + 1):
            b = int(round((h * f0s[k] - win.f[0]) / win.df))
            if b < 1 or b >= len(win.f) - 1:
                continue
            fh, ah = refine(stft, frame, b + off, p.estimator)
            if abs(fh / h - f0s[k]) <= 1.5 * win.df:                      # a harmonic measured off its line is dropped
                est.append(fh / h); wts.append(10 ** (ah / 10))
        if est:
            f[i] = float(np.average(est, weights=wts)); amp[i] = 10 * np.log10(max(wts))
    return Track(t.copy(), f, amp, level, np.isfinite(f), np.where(np.isfinite(f), path, -1))


# old name: hmm_track
def hysteresis_track(sp: Spectrogram, stft: SampleSTFT, t_start: float, t_end: float, f_lo: float, f_hi: float,
              p: HysteresisParams = HysteresisParams()) -> EventTracks:
    """Families of tracks whose fundamental lies in [f_lo, f_hi] between t_start and t_end."""
    from dopplertrack.components.whitening.local_median import local_whiten
    top = min(sp.f[-1], p.harmonics * f_hi + 2 * sp.df)
    win = local_whiten(sp.crop(t_start, t_end, max(f_lo - 2 * sp.df, sp.f[0]), top), spectral_floor=-np.inf)
    S = np.where(win.valid[None, :], win.S, -np.inf).T                      # (T, F)
    S = np.where(np.isfinite(S), S, -1e3)
    step = p.grid_frac * win.df
    f0s = np.arange(f_lo, f_hi + step / 2, step)
    excl = np.zeros(S.shape, bool)
    tracks: list[Track] = []
    fam_of: list[int] = []
    for fam in range(p.families):                                         # one decode per family
        E = harmonic_sum(S, win.f, f0s, p.harmonics, exclude=excl)
        E[~win.valid] = -1e3
        runs = [r for r in decode(E, win.t, win.valid, win.df, f0s, p) if win.t[r[1]] - win.t[r[0]] >= p.min_track_s]
        if not runs:
            break
        for k0, k1, path in runs:
            tracks.append(_measure(win, stft, k0, path, f0s, E, p)); fam_of.append(fam)
            for i, k in enumerate(path):
                if k < 0:
                    continue
                for h in range(1, p.harmonics + 1):
                    b = int(round((h * f0s[k] - win.f[0]) / win.df))
                    excl[k0 + i, max(b - p.exclusion_bins, 0):max(b + p.exclusion_bins + 1, 0)] = True
    tracks = resolve_crossings(tracks, TrackParams(), win.df)
    links = harmonic_links(tracks, TrackParams(harmonic_tol=p.harmonic_tol, max_order=p.max_order))
    groups = harmonic_groups(tracks, links)
    return EventTracks(tracks, links, groups)


def with_params(p: HysteresisParams, **kw) -> HysteresisParams:
    return dataclasses.replace(p, **kw)
