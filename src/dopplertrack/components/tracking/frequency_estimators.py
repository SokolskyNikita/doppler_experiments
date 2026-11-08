"""Three-coefficient (DFT interpolation) frequency estimators (Quinn & Hannan 2001 §6.2.2) on the original STFT:
parabolic interpolation on log magnitude, Candan's Hann-window estimator and Quinn's FTI(2) (Quinn 1995 §IV.B);
and a path measured with them."""
from __future__ import annotations

import math

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.tracking.types import SampleSTFT, Track, TrackParams


# old name: quadratic_delta
def log_parabolic_delta(a: complex, b: complex, c: complex) -> float:
    """Log-parabolic interpolation: the vertex of a parabola through the log magnitudes of bins k-1, k, k+1. Not
    Quinn & Hannan's "quadratic interpolation" (2001 §6.2.3), which fits the squared magnitudes. Selected by the
    `estimator` value "quadratic"."""
    la, lb, lc = (math.log(max(abs(z), 1e-300)) for z in (a, b, c))
    den = la - 2 * lb + lc
    return 0.0 if den == 0 else 0.5 * (la - lc) / den


def candan_hann_delta(a: complex, b: complex, c: complex) -> float:
    """Candan's three-sample estimator for a Hann window (Candan 2011, not in the reference folder). For a Hann-windowed tone the three
    coefficients are proportional to 1/((d - m)(1 - (d - m)^2)), m = -1, 0, 1, which makes
    Re[(X-1 - X+1)/(2 X0 - X-1 - X+1)] = d/2 exactly as N grows."""
    den = 2 * b - a - c
    return 0.0 if den == 0 else float(2 * ((a - c) / den).real)


def _kappa(x: float) -> float:
    r = math.sqrt(2 / 3)
    return 0.25 * math.log(3 * x ** 4 + 6 * x ** 2 + 1) - math.sqrt(6) / 24 * math.log((x * x + 1 - r) / (x * x + 1 + r))


def quinn2_delta(a: complex, b: complex, c: complex) -> float:
    """Quinn's FTI(2) (Quinn 1995 §IV.B; Quinn & Hannan 2001 Algorithm 5) on the unwindowed DFT coefficients at
    k-1, k, k+1."""
    if b == 0:
        return 0.0
    a1, a2 = (a / b).real, (c / b).real
    d1, d2 = a1 / (1 - a1), -a2 / (1 - a2)
    return (d1 + d2) / 2 - _kappa(d1) + _kappa(d2)


def refine(stft: SampleSTFT, k: int, b: int, estimator: str = "candan", iterations: int = 3) -> tuple[float, float]:
    """(frequency Hz, amplitude dB) of the peak near bin b in frame k of the original STFT: the
    largest Hann bin within one of b, then the estimator. Candan is iterated on the DTFT
    around its own estimate, as dopplerprint does."""
    X = stft.dft(k)
    if stft.wbin != 1:
        return _refine_padded(stft, k, b, X, estimator, iterations)
    lo = max(b - 1, 1)
    j = lo + int(np.argmax(np.abs(X[lo:b + 2])))
    j = min(max(j, 1), len(X) - 2)
    if estimator == "quadratic":
        d = log_parabolic_delta(X[j - 1], X[j], X[j + 1])
    elif estimator == "quinn2":
        Y = stft.dft(k, window=False)
        d = quinn2_delta(Y[j - 1], Y[j], Y[j + 1])
    elif estimator == "candan":
        d = candan_hann_delta(X[j - 1], X[j], X[j + 1])
        for _ in range(iterations - 1):
            Z = stft.dtft(k, j + d + np.array([-1.0, 0.0, 1.0]))
            d += candan_hann_delta(*Z)
    else:
        raise ValueError(f"unknown estimator {estimator!r}")
    d = float(np.clip(d, -1.0, 1.0))
    w = abs(np.sinc(d) / (1 - d * d)) if abs(d) < 0.999 else 0.5
    amp = 20 * math.log10(max(abs(X[j]), 1e-300) / (w * stft.window.sum() / 2))
    return (j + d) * stft.df, amp


def _refine_padded(stft: SampleSTFT, k: int, b: int, X: np.ndarray, estimator: str, iterations: int) -> tuple[float, float]:
    """refine() on a zero-padded STFT: the estimators' three samples are one resolution bin apart
    (sr / nperseg), so they are evaluated on the DTFT rather than read from the padded bins."""
    w = stft.wbin
    r = int(math.ceil(w))
    lo = max(b - r, 1)
    j = lo + int(np.argmax(np.abs(X[lo:b + r + 1])))
    pos = j + w * np.array([-1.0, 0.0, 1.0])
    if estimator == "quadratic":
        d = log_parabolic_delta(*stft.dtft(k, pos))
    elif estimator == "quinn2":
        d = quinn2_delta(*stft.dtft(k, pos, window=False))
    elif estimator == "candan":
        d = candan_hann_delta(*stft.dtft(k, pos))
        for _ in range(iterations - 1):
            d += candan_hann_delta(*stft.dtft(k, j + w * (d + np.array([-1.0, 0.0, 1.0]))))
    else:
        raise ValueError(f"unknown estimator {estimator!r}")
    d = float(np.clip(d, -1.0, 1.0))
    amp = 20 * math.log10(max(abs(stft.dtft(k, [j + w * d])[0]), 1e-300) / (stft.window.sum() / 2))   # at the peak itself
    return (j + w * d) * stft.df, amp


def measure_path(win: Spectrogram, stft: SampleSTFT, k0: int, path: np.ndarray, p: TrackParams) -> Track:
    n = len(path)
    t = win.t[k0:k0 + n]
    f = np.full(n, np.nan); amp = np.full(n, np.nan); level = np.full(n, np.nan)
    f_offset = int(round(win.f[0] / stft.df))                     # win bins -> full-STFT bins
    for i, b in enumerate(path):
        if b < 0:
            continue
        level[i] = win.S[b, k0 + i]
        f[i], amp[i] = refine(stft, stft.frame(float(t[i])), int(b) + f_offset, p.estimator)
    return Track(t.copy(), f, amp, level, path >= 0, path.copy())
