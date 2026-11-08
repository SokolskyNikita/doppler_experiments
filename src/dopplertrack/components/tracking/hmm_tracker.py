"""HMM frequency-line tracker (Streit & Barrett 1990; Quinn & Hannan 2001 §7.4), decoded by forward-backward
(PLAN Phase 2 item 3, round 3; docs/experiments/designs/2026-11-04-tracker-likelihood.md).

Each cell's power over the frame's noise level across frequency, z = P / sigma^2, is Exp(1) in noise and Rician
with a tone of per-cell SNR a; the cell's log-likelihood ratio is l(z; a) = -a + ln I0(2 sqrt(a z))
(Kay 1998 Problem 7.22; Eddy 1980 eq. 14). On a grid of fundamentals, each observable harmonic h = 1..3 is present
with prior q, so the frame's log-likelihood ratio for fundamental k is sum_h ln(1 - q + q e^l_h) (Eddy eq. 22).
A hidden Markov model with OFF (Streit & Barrett's zero state), ON(k) and DIP(k) is decoded by forward-backward.
DIP, a tone still there but under the noise, is a fade state of our own (ours): S&B have only the zero state. A track
is a run of frames whose posterior P(ON or DIP), S&B's gate occupancy probability, exceeds 0.5 and that holds an
ON frame. Transitions per frame: birth OFF -> ON(k) at a rate per Hz per second, the end of a pass at dt/T_pass, into and out of a dip at dt/T_run and
dt/T_dip, and frequency moves by a Laplace kernel of scale slope_scale * f per second, capped at max_rel_slope * f.
Frequencies are measured on the original STFT per harmonic and combined with weights h^2 A_h^2, the inverse of
each harmonic's asymptotic variance (Quinn & Hannan 2001 Theorem 8, §3.3).

The spectrogram must be whitened across frequency (compute_spectrogram(whiten="frequency")): its S is then
10 log10(P / median P over +-bg_hz), and z = ln 2 * 10^(S/10)."""
# old module: dopplertrack.components.tracking.likelihood
from __future__ import annotations


import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.tracking.forward_backward import posterior, runs
from dopplertrack.components.tracking.hmm_tracker_params import HMMTrackerParams
from dopplertrack.components.tracking.harmonic_llr import harmonic_llr, normalised_power
from dopplertrack.components.tracking.frequency_estimators import refine
from dopplertrack.components.tracking.harmonic_links import harmonic_groups, harmonic_links
from dopplertrack.components.tracking.segment_rules import resolve_crossings
from dopplertrack.components.tracking.types import EventTracks, SampleSTFT, Track, TrackParams


def _measure(win: Spectrogram, stft: SampleSTFT, k0: int, path: np.ndarray, f0s: np.ndarray, E: np.ndarray,
             p: HMMTrackerParams) -> Track:
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
            fh, ah = refine(stft, frame, b + off, p.estimator)
            if abs(fh / h - f0s[k]) <= 1.5 * win.df:                      # a harmonic measured off its line is dropped
                est.append(fh / h); wts.append(h * h * 10 ** (ah / 10))      # Quinn & Hannan Theorem 8: h^2 A_h^2
        if est:
            f[i] = float(np.average(est, weights=wts)); amp[i] = 10 * np.log10(max(wts))
    keep = np.isfinite(f)
    return Track(t.copy(), f, amp, level, keep, np.where(keep, path, -1))


# old name: ll_track
def hmm_posterior_track(sp: Spectrogram, stft: SampleSTFT, t_start: float, t_end: float, f_lo: float, f_hi: float,
             p: HMMTrackerParams = HMMTrackerParams()) -> EventTracks:
    """Families of tracks whose fundamental lies in [f_lo, f_hi] between t_start and t_end; sp is whitened across
    frequency."""
    top = min(sp.f[-1], p.harmonics * f_hi + 2 * sp.df)
    win = sp.crop(t_start, t_end, max(f_lo - 2 * sp.df, sp.f[0]), top)
    z = normalised_power(win)
    step = p.grid_frac * win.df
    f0s = np.arange(f_lo, f_hi + step / 2, step)
    dt = float(np.median(np.diff(win.t))) if len(win.t) > 1 else 0.25
    excl = np.zeros((len(win.t), len(win.f)), bool)
    tracks: list[Track] = []
    for _ in range(p.families):
        E = harmonic_llr(z, win.f, f0s, p, exclude=excl)
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
    tracks = resolve_crossings(tracks, TrackParams(), win.df)
    links = harmonic_links(tracks, TrackParams(harmonic_tol=p.harmonic_tol, max_order=p.max_order))
    groups = harmonic_groups(tracks, links)
    return EventTracks(tracks, links, groups)
