"""A modelled curve that only covers part of the measured window must not score as well as one
that covers all of it, otherwise a flight that landed mid-pass can win on the bright half alone."""
import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.scoring.curve_integral import EventWindow
from dopplertrack.components.types import EventFit


def _window():
    t = np.arange(0, 200, 0.25); f = np.arange(60, 260, 0.5)
    S = np.zeros((len(f), len(t)), np.float32)
    ridge = 150.0 - 50.0 / (1 + np.exp(-(t - 100) / 8))     # bright sigmoid ridge, 150 -> 100 Hz
    for k, tk in enumerate(t):
        S[np.argmin(np.abs(f - ridge[k])), k] = 10.0
    fit = EventFit(t_cpa=100, t_cpa_emit=97, f0=1.0, v=80, d=1500, t_start=40, t_end=160, score=0, f_pre=150, f_post=100)
    return EventWindow(fit, Spectrogram(t, f, S)), t, ridge


def test_partial_coverage_scores_proportionally():
    w, t, ridge = _window()
    full = w.curve_score(t, ridge)
    half_t = t[t <= 100]
    half = w.curve_score(half_t, ridge[: len(half_t)])
    assert full > 0
    assert 0.4 * full < half < 0.6 * full


def test_sweep_matches_curve_score():
    w, t, ridge = _window()
    s = w.sweep_scores(t, ridge, [0.0, 20.0], [1.0])
    assert np.isclose(s[0, 0], w.curve_score(t, ridge))
    assert s[1, 0] < 0.5 * s[0, 0]         # shifted 20 s off the ridge


def test_invalid_curve_samples_do_not_become_interpolated_evidence():
    w, t, ridge = _window()
    full = w.curve_score(t, ridge)
    masked = ridge.copy()
    masked[(t >= 80) & (t <= 120)] = np.nan
    partial = w.curve_score(t, masked)
    assert 0.55 * full < partial < 0.75 * full
    assert w.curve_score(t, np.full_like(ridge, np.nan)) == 0
    assert w.curve_score(np.array([0.0]), np.array([100.0])) == 0
