"""The curve integral over a window's whole span (EventWindow.sweep_scores: non-coherent integration along the modelled
curve, Kay 1998 §7.6.4; Iatsenko 2016 eq. 3.3) behind LogView's interface, so the collective recipe can score passes
with either. Unlike LogView it keeps no best sub-stretch: the mean runs over the whole window, uncovered parts counting
as zero, and it samples the whitened crop bilinearly at each f0 scale instead of gathering rows of a log-frequency
matrix."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.scoring.curve_integral import EventWindow
from dopplertrack.components.scoring.log_view import LOG_DU, SUB_S
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten
from dopplertrack.components.windows import Window


class EventWindowView:
    """A window's whitened crop (as LogView crops it) scored by EventWindow's whole-window mean. sweep_scores takes
    f0 offsets in log_du units, as LogView's does; sub_s is accepted for the same signature and unused."""

    def __init__(self, win: Window, sp: Spectrogram, n: int, pad_s: float = 40.0, f_lo: float = 0.45,
                 f_hi: float = 2.0, log_du: float = LOG_DU, sub_s: float = SUB_S, spectral_floor: float = 0.0):
        crop = local_whiten(sp.crop(win.t_start - pad_s, win.t_end + pad_s, max(f_lo * win.f0, sp.f[0]),
                                    min(f_hi * win.f0, sp.f[-1])), spectral_floor)
        nan = float("nan")
        fit = EventFit(t_cpa=win.t_cpa, t_cpa_emit=nan, f0=win.f0, v=nan, d=nan, t_start=win.t_start,
                       t_end=win.t_end, score=win.score, f_pre=nan, f_post=nan)
        self.f0, self.n, self.log_du, self.sub_s = win.f0, n, log_du, sub_s
        self.window = EventWindow(fit, crop, 1, n)

    def sweep_scores(self, t_audio, ratio, shifts, offsets) -> np.ndarray:
        """(shift, f0 offset) scores: EventWindow.sweep_scores at scales exp(offset * log_du)."""
        scales = np.exp(np.asarray(offsets, float) * self.log_du)
        return self.window.sweep_scores(np.asarray(t_audio, float), np.asarray(ratio, float), shifts, scales)
