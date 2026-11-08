"""Log-frequency resampling of a window's whitened spectrogram, so a curve at any f0 (Doppler) scale is an index
offset: on a log axis a scale is a shift, the change of variable behind the Mellin transform (Flandrin 2018 §16.3).
The curve integral over it keeps the best SUB_S stretch, a scan statistic (Glaz, Naus & Wallenstein 2001, not in
folder)."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.whitening.local_median import local_whiten
from dopplertrack.components.windows import Window

LOG_DU = float(np.log1p(0.0025))    # the log-frequency grid's step: 0.25 %, about one bin at 125 Hz
SUB_S = 120.0                       # a (flight, window) scores its best SUB_S stretch: detect's 240 s windows are twice
                                    # the length of the lines they hold (the find test's true lines: about 110 s)


class LogView:
    """A window's whitened crop resampled once onto (log frequency x the sweep's n times), so a curve at any f0 scale is
    an index offset into one matrix: the sweep's f0 points cost a gather each, not a bilinear sampling each. The crop
    is 0.45-2.0 times the coarse tone, which holds a +-25 % f0 sweep over a pass's Doppler span; outside it, and on
    invalid frames, the level is 0, as sweep_scores' fill."""

    def __init__(self, win: Window, sp: Spectrogram, n: int, pad_s: float = 40.0):
        crop = local_whiten(sp.crop(win.t_start - pad_s, win.t_end + pad_s, max(0.45 * win.f0, sp.f[0]),
                                    min(2.0 * win.f0, sp.f[-1])))
        self.f0, self.n = win.f0, n
        self.tq = np.linspace(win.t_start, win.t_end, n)
        self.u0 = float(np.log(crop.f[0])) if len(crop.f) else 0.0
        J = int(np.floor((np.log(crop.f[-1]) - self.u0) / LOG_DU)) + 1 if len(crop.f) > 1 else 0
        F = np.exp(self.u0 + LOG_DU * np.arange(J))
        T, FF = np.broadcast_to(self.tq[None, :], (J, n)), np.broadcast_to(F[:, None], (J, n))
        self.A = crop.sample(T.ravel(), FF.ravel()).reshape(J, n).astype(np.float32) if J else np.zeros((0, n), np.float32)

    def sweep_scores(self, t_audio, ratio, shifts, offsets) -> np.ndarray:
        """(shift, f0 offset) scores: the best mean level along the curve over any SUB_S stretch of the n times,
        zero where the curve doesn't cover them; offsets are f0 scales in LOG_DU steps (scale = exp(offset * LOG_DU)).
        The window decoy nulls use the same rule, so the extra maximum over the stretch's position is priced there
        (a nuisance parameter present only under the alternative, Davies 1977)."""
        J, n = self.A.shape
        ok = np.isfinite(t_audio)
        if np.count_nonzero(ok) < 2 or J < 2:
            return np.zeros((len(shifts), len(offsets)))
        rel = self.tq[None, :] - np.asarray(shifts)[:, None]                          # (S, n)
        rat = np.interp(rel, t_audio[ok], ratio[ok], left=np.nan, right=np.nan)
        valid = np.isfinite(rat).sum(1) >= 10
        with np.errstate(invalid="ignore", divide="ignore"):
            x = (np.log(self.f0 * rat) - self.u0) / LOG_DU                              # (S, n) fractional row
        x = x[:, None, :] + np.asarray(offsets, float)[None, :, None]                   # (S, K, n)
        good = np.isfinite(x) & (x >= 0) & (x <= J - 1)
        j0 = np.where(good, np.floor(x), 0).astype(np.int64)
        j1 = np.minimum(j0 + 1, J - 1)
        w = np.where(good, x - j0, 0.0)
        flat = self.A.ravel(); col = np.arange(n)[None, None, :]
        v = flat[j0 * n + col] * (1 - w) + flat[j1 * n + col] * w
        v = np.where(good, v, 0.0)
        span = (self.tq[-1] - self.tq[0]) / max(n - 1, 1)
        L = int(min(n, max(1, round(SUB_S / span) + 1))) if span > 0 else n
        cs = np.concatenate([np.zeros(v.shape[:2] + (1,)), np.cumsum(v, axis=2)], axis=2)
        total = ((cs[..., L:] - cs[..., :-L]) / L).max(axis=2)
        total[~valid] = 0.0
        return total


def log_offsets(span: float, step: float) -> np.ndarray:
    """f0 offsets in LOG_DU units covering scales 1 - span to 1 + span at about `step` (uniform in log f0)."""
    m = max(1, int(round(np.log1p(step) / LOG_DU)))
    lo = int(np.floor(np.log1p(-span) / (m * LOG_DU))); hi = int(np.ceil(np.log1p(span) / (m * LOG_DU)))
    return m * np.arange(lo, hi + 1)
