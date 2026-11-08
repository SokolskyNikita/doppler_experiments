"""Tone tracking on the de-Dopplerized, median-subtracted spectrogram (Ramseier & Pieren 2023 §II.C.2-3; Howell
1986 §2.1), PLAN Phase 2 item 8.

For an observer, a recording clock and a trajectory, the recording is evaluated at the reception
times of a uniform grid of emission times u: t_r = u + |p(u) - x|/c, so t = tau + r/c in Kelly &
Wilson 1993 eq. 12 (the Markdown copy drops its minus sign) and t_s = t_r - D/c in Ramseier & Pieren
eq. 9. A steady emitted tone from the right geometry then becomes a stationary line.
- Interpolation: a Hamming-windowed sinc of 2L taps (Ramseier & Pieren eqs. 7-8); linear and nearest
  are kept for the test that measures each one's floor (Howell 1986 3.1).
- Aliasing: the output grid has the input's rate. Undoing a recede reads the input up to
  1 + R'/c samples per output sample, so the input is low-passed at sr / (2 max_rate) first, and a
  geometry needing a rate above max_rate is refused.
- No amplitude correction: the score below normalises each block, identically for every candidate. Gao 2021's
  Doppler-warping transform (§2.2 eq. 7) scales by sqrt(h'(t)); this one does not (ours).

Score: Hann blocks of the warped signal; each block's dB less its median across frequency within
+-bg_hz (Ramseier & Pieren eq. 11), not over time, which would erase the stationary line; per block
and fundamental, a weighted harmonic sum (weights (N + 1 - h) / N, eq. 12 of the PDF; RP weight the
harmonics inside the path recursion, here they are summed per block first, ours); then a Viterbi path over
blocks in fundamental space with an off state, a tone constant within each block, strict (one fundamental
per event) or with bounded drift, and up to two tone families. Integration is coherent only within each
FFT block; across blocks it is non-coherent (dB levels summed along the path; Kay 1998 §7.3).

This module is the tone score. The filters and resampling are in resampling, the warp in dedoppler_warp, the
block spectra in block_spectra, the harmonic sum in components/harmonic_sum and the paths in block_paths."""
# old module: dopplertrack.components.scoring.coherent
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from dopplertrack.components.harmonic_sum import harmonic_sum
from dopplertrack.components.scoring.block_paths import path_drift, path_strict


@dataclass
class ToneScore:
    score: float             # the families' path totals per block, summed (RP's global score Q, per block)
    f0: list                 # each family's fundamental (strict) or median fundamental (drift)
    on: float                # share of blocks the first family is on
    blocks: int


def tone_score(S: np.ndarray, f: np.ndarray, f0_lo: float, f0_hi: float, harmonics: int = 3,
               theta: float = 0.0, birth: float = 0.0, drift_step_hz: float | None = None,
               range_frac: float = 0.02, families: int = 2, exclude_bins: int = 2) -> ToneScore:
    """The event's tone score on median-subtracted blocks S (B, F). Strict when drift_step_hz is
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
        E = harmonic_sum(S, f, f0s, harmonics, exclude=excl)
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
                j = int(round((h * fb[b] - f[0]) / df))
                if 0 <= j < S.shape[1] + exclude_bins:
                    excl[b, max(j - exclude_bins, 0):max(j + exclude_bins + 1, 0)] = True
    return ToneScore(total, f0_out, on_share, S.shape[0])
