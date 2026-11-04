"""Score candidate observers by modelling the exact Doppler curve they would hear."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio import Spectrogram
from .doppler import curve_from_trajectory, speed_of_sound
from .search import Segment
from .tracks import EventFit, local_whiten


@dataclass
class EventWindow:
    """Whitened spectrogram crop for one event plus its measured parameters."""
    fit: EventFit
    sp: Spectrogram
    harmonics: int = 1

    @classmethod
    def from_fit(cls, sp: Spectrogram, fit: EventFit, harmonics: int = 1, pad_s: float = 40.0):
        w = sp.crop(fit.t_start - pad_s, fit.t_end + pad_s, max(fit.f_post * 0.8, sp.f[0]),
                    min(fit.f_pre * 1.25 * harmonics, sp.f[-1]))
        return cls(fit, local_whiten(w), harmonics)

    def curve_score(self, t_audio, ratio, f0_scale=1.0) -> float:
        """Brightness under the curve averaged over the event's fit window (uncovered parts
        count as zero); same convention as sweep_scores, for a single placement."""
        return float(self.sweep_scores(t_audio, ratio, [0.0], [f0_scale])[0, 0])

    def sweep_scores(self, t_audio, ratio, shifts, f0_scales, n=160) -> np.ndarray:
        """Scores for every (shift, f0_scale) combination in one vectorised pass.
        The curve is resampled onto n points of the fit window for each shift.

        The score is the brightness summed along the curve divided by n, i.e. the mean
        over the *whole* fit window, with the parts of the window the modelled curve does
        not cover counting as zero. A flight whose trajectory only explains half the
        measured sweep (it took off, landed or left the data mid-pass) therefore earns
        half the score, instead of being judged only where it happens to fit."""
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


def modelled_curve(seg: Segment, obs_enu, c):
    """(t_obs unix, ratio f/f0) the observer at obs_enu hears from this segment."""
    t_obs, ratio, r, valid = curve_from_trajectory(seg.t, seg.enu, obs_enu, f0=1.0, c=c,
                                                return_valid=True, sample_valid=seg.valid)
    return t_obs, np.where(valid, ratio, np.nan)


def locked_score(ev1: EventWindow, ev2: EventWindow, seg1: Segment, seg2: Segment, obs_enu,
                 t_heard1: float, c: float | None = None,
                 shifts=np.arange(-8, 8.01, 0.5), f0_scales=np.arange(0.95, 1.0501, 0.005)):
    """Two-event locked scoring.

    Event 1's placement is swept over small time shifts and f0 scales (both are
    measurements). Event 2 is placed with the *same* time shift, so its timing
    relative to event 1 is fixed purely by flight geometry.
    Returns (total, s1, s2, best_shift).
    """
    c = speed_of_sound() if c is None else c
    # map unix time -> audio time so that the modelled heard-CPA of event 1 lands on the measured one
    t0_map = ev1.fit.t_cpa - t_heard1
    to1, r1 = modelled_curve(seg1, obs_enu, c)
    to2, r2 = modelled_curve(seg2, obs_enu, c)
    sc1 = ev1.sweep_scores(to1 + t0_map, r1, shifts, f0_scales)
    i, j = np.unravel_index(np.argmax(sc1), sc1.shape)
    s1, sh = float(sc1[i, j]), float(shifts[i])
    s2 = float(ev2.sweep_scores(to2 + t0_map, r2, [sh], f0_scales).max())
    return s1 + s2, s1, s2, sh


def single_score(ev: EventWindow, seg: Segment, obs_enu, t_heard: float, c=None,
                 shifts=np.arange(-8, 8.01, 0.5), f0_scales=np.arange(0.95, 1.0501, 0.005)):
    c = speed_of_sound() if c is None else c
    to, r = modelled_curve(seg, obs_enu, c)
    t0_map = ev.fit.t_cpa - t_heard
    return float(ev.sweep_scores(to + t0_map, r, shifts, f0_scales).max())
