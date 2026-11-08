"""Ridge curve by path optimisation (Iatsenko 2016 §3, eqs. 3.3-3.4, scheme I: penalised frequency jumps), solved by
dynamic programming (Viterbi): the strongest smooth path through a spectrogram window, as a frequency track."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.types import Track
from dopplertrack.components.whitening.local_median import local_whiten


# old name: ridge
def ridge_curve(sp: Spectrogram, max_step_bins: int = 3, jump_penalty: float = 1.5) -> np.ndarray:
    """Ridge curve through S (F,T) by path optimisation (Iatsenko 2016 eq. 3.3): maximise
    sum(S) - jump_penalty*|Δbin| (scheme I, eq. 3.4, with S in dB as the log amplitude), with
    |Δbin| <= max_step_bins as a hard limit, by dynamic programming. Returns freq per frame."""
    S = sp.S
    F, T = S.shape
    cost = np.full((T, F), -np.inf)
    back = np.zeros((T, F), np.int16)
    cost[0] = S[:, 0]
    offs = np.arange(-max_step_bins, max_step_bins + 1)
    pen = jump_penalty * np.abs(offs)
    for t in range(1, T):
        prev = cost[t - 1]
        cand = np.full((len(offs), F), -np.inf)
        for k, o in enumerate(offs):
            if o >= 0:
                cand[k, o:] = prev[: F - o] - pen[k]
            else:
                cand[k, :o] = prev[-o:] - pen[k]
        kbest = np.argmax(cand, axis=0)
        cost[t] = cand[kbest, np.arange(F)] + S[:, t]
        back[t] = offs[kbest]
    path = np.zeros(T, int)
    path[-1] = int(np.argmax(cost[-1]))
    for t in range(T - 1, 0, -1):
        path[t - 1] = path[t] - back[t, path[t]]
    return sp.f[path]


def ridge_track(sp: Spectrogram, t_start: float, t_end: float, f_lo: float, f_hi: float, harmonic: int = 1) -> Track:
    """ridge_curve() through the window, on local_whiten of exactly the band (times the harmonic), as a Track:
    bin-centre frequencies, amplitude 10^(dB/20) of the whitened level on the path, and the
    spectrogram's frame mask. Unlike fit_event's padded crop, which constrains its curve to the band,
    ridge_curve() takes the strongest path through whatever it is given, so any margin lets it lock onto a
    line outside the band."""
    win = local_whiten(sp.crop(t_start, t_end, harmonic * f_lo, harmonic * f_hi))
    f = ridge_curve(win)
    level = win.S[np.searchsorted(win.f, f), np.arange(len(win.t))]
    return Track(win.t, f, 10.0 ** (level / 20.0), win.valid.copy(), harmonic)
