"""Non-coherent integration of the whitened spectrogram along a modelled instantaneous-frequency curve, over an
event's fit window: Kay 1998 §7.6.4 (spectrogram GLRT, maximised over nuisance parameters) with a known frequency
law, Iatsenko 2016 eq. 3.3 (the path integral of a time-frequency representation), and track-before-detect's
integration along candidate trajectories (Blackman & Popoli 1999 §7.8, §17.5). Not a matched filter: no phase is
used."""
# old module: dopplertrack.components.scoring.curve_brightness
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten


@dataclass
class EventWindow:
    """Whitened spectrogram crop for one event plus its measured parameters."""
    fit: EventFit
    sp: Spectrogram
    harmonics: int = 1
    n: int = 160                # the curve's samples over the fit window (sweep_scores' default n)

    @classmethod
    def from_fit(cls, sp: Spectrogram, fit: EventFit, harmonics: int = 1, pad_s: float = 40.0, n: int = 160,
                 spectral_floor: float = 0.0):
        """The fit window padded by pad_s, 0.8 f_post to 1.25 f_pre per harmonic, through local_whiten."""
        w = sp.crop(fit.t_start - pad_s, fit.t_end + pad_s, max(fit.f_post * 0.8, sp.f[0]),
                    min(fit.f_pre * 1.25 * harmonics, sp.f[-1]))
        return cls(fit, local_whiten(w, spectral_floor), harmonics, n)

    def curve_score(self, t_audio, ratio, f0_scale=1.0) -> float:
        """The curve integral averaged over the event's fit window (uncovered parts
        count as zero); same convention as sweep_scores, for a single placement."""
        return float(self.sweep_scores(t_audio, ratio, [0.0], [f0_scale])[0, 0])

    def sweep_scores(self, t_audio, ratio, shifts, f0_scales, n=None) -> np.ndarray:
        """Scores for every (shift, f0_scale) combination in one vectorised pass.
        The curve is resampled onto n points (default self.n) of the fit window for each shift.

        The score is the whitened level summed along the curve divided by n, i.e. the mean
        over the *whole* fit window, with the parts of the window the modelled curve does
        not cover counting as zero, then averaged over the harmonics. A flight whose trajectory only explains half the
        measured sweep (it took off, landed or left the data mid-pass) therefore earns
        half the score, instead of being judged only where it happens to fit."""
        n = self.n if n is None else n
        tq = np.linspace(self.fit.t_start, self.fit.t_end, n)
        rel = tq[None, :] - np.asarray(shifts)[:, None]                       # (S, n) un-shifted audio time
        # Retain invalid frequency samples so interpolation cannot bridge holes
        # in a modelled curve. Only nonfinite time coordinates must be removed.
        ok = np.isfinite(t_audio)
        if np.count_nonzero(ok) < 2:
            return np.zeros((len(shifts), len(f0_scales)))
        rat = np.interp(rel, t_audio[ok], ratio[ok], left=np.nan, right=np.nan)  # (S, n)
        valid = np.isfinite(rat).sum(1) >= 10                                  # (S,)
        total = np.zeros((len(shifts), len(f0_scales)))
        for h in range(1, self.harmonics + 1):
            F = h * self.fit.f0 * np.asarray(f0_scales)[None, :, None] * rat[:, None, :]   # (S, K, n)
            T = np.broadcast_to(tq[None, None, :], F.shape)
            v = self.sp.sample(T.ravel(), np.nan_to_num(F.ravel(), nan=-1.0)).reshape(F.shape)
            v = np.where(np.isfinite(F), v, 0.0)
            total += v.sum(axis=2) / n
        total[~valid] = 0.0
        return total / self.harmonics
