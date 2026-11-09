"""The hysteresis-in-states tracker (dopplertrack.components.tracking.hysteresis_viterbi): a missing fundamental, crossing lines,
hysteresis through a dip, a short tone never born, and a gap of invalid frames."""
import numpy as np
import pytest

from dopplertrack.core import propagation as doppler
from dopplertrack.components.tracking import hysteresis_viterbi as hm
import dopplertrack.components.stft as stft
import dopplertrack.components.tracking.types as tracking_types

SR, N, HOP = 4000, 8192, 0.25
P = hm.HysteresisParams()


def _audio(dur, parts, noise=0.4, seed=0):
    t = np.arange(0, dur, 1 / SR)
    x = noise * np.random.default_rng(seed).standard_normal(len(t))
    for f, a, t0, t1 in parts:
        fi = f(t) if callable(f) else np.full(len(t), float(f))
        x += a * np.sin(2 * np.pi * np.cumsum(fi) / SR) * ((t >= t0) & (t < t1))
    return x.astype(np.float32)


def _run(x, lo, hi, blocks=None, fmax=1000.0, p=P, whiten="time"):
    sp = (stft.compute_spectrogram(x, SR, fmax=fmax, whiten_window_s=None, whiten=whiten) if blocks is None
          else stft.spectrogram_from_blocks(blocks, SR, fmax=fmax, whiten_window_s=None, whiten=whiten))
    return sp, hm.hysteresis_track(sp, tracking_types.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], lo, hi, p)


def _pass(f0):
    return lambda t: np.nan_to_num(doppler.ideal_curve(t, f0, 60.0, 900.0, 60.0, c=340.0), nan=f0)


def test_missing_fundamental_tracks_the_fundamental():
    g = _pass(100.0)
    x = _audio(120.0, [(lambda t, h=h: h * g(t), 0.15, 0, 120) for h in (2, 3, 4)])     # no fundamental
    _, ev = _run(x, 80, 125)
    tr = max(ev.tracks, key=lambda q: q.measured.sum())
    ref = g(tr.t)
    ok = tr.measured & (tr.t > 10) & (tr.t < 110)
    assert np.median(np.abs(tr.f[ok] - ref[ok])) < 0.5                     # f0, not 2 f0 or f0/2
    assert tr.measured.mean() > 0.8


def _keeps_lines(ev, lines):
    """Every track lies on one of the lines and follows it for 90 % of its points: no swap at a crossing."""
    for tr in ev.tracks:
        ok = tr.measured
        err = {name: np.median(np.abs(tr.f[ok] - g(tr.t[ok]))) for name, g in lines.items()}
        name = min(err, key=err.get)
        assert err[name] < 1.0, (tr.start, tr.end, err)
        assert (np.abs(tr.f[ok] - lines[name](tr.t[ok])) < 2.0).mean() > 0.9, (tr.start, tr.end, name)
    return {min(lines, key=lambda n: np.median(np.abs(tr.f[tr.measured] - lines[n](tr.t[tr.measured]))))
            for tr in ev.tracks}


def test_a_pass_crossing_a_steady_tone():
    """Whitened across frequency: a steady tone that lasts the whole window survives, where the median over
    time would erase it."""
    fall = _pass(150.0)
    x = _audio(120.0, [(fall, 0.2, 0, 120), (140.0, 0.12, 0, 120)])
    _, ev = _run(x, 115, 200, p=hm.with_params(P, harmonics=1), whiten="frequency")
    assert _keeps_lines(ev, {"fall": fall, "tone": lambda t: np.full(len(t), 140.0)}) == {"fall", "tone"}


def test_two_passes_crossing():
    a, b = _pass(150.0), (lambda t: np.nan_to_num(doppler.ideal_curve(t, 120.0, 70.0, 700.0, 75.0, c=340.0), nan=120.0))
    x = _audio(140.0, [(a, 0.2, 0, 140), (b, 0.15, 0, 140)])
    _, ev = _run(x, 95, 200, p=hm.with_params(P, harmonics=1))
    assert _keeps_lines(ev, {"a": a, "b": b}) == {"a", "b"}


def test_hysteresis_carries_a_weak_dip():
    g = _pass(120.0)
    amp = lambda t: np.where((t > 50) & (t < 53), 0.035, 0.2)             # a 3 s dip below theta_birth
    t = np.arange(0, 120, 1 / SR)
    x = (0.4 * np.random.default_rng(1).standard_normal(len(t)) + amp(t) * np.sin(2 * np.pi * np.cumsum(g(t)) / SR)).astype(np.float32)
    _, ev = _run(x, 95, 150, p=hm.with_params(P, harmonics=1, families=1))
    long = [tr for tr in ev.tracks if tr.end - tr.start > 60]
    assert len(long) == 1 and long[0].start < 45 and long[0].end > 60


@pytest.mark.xfail(strict=True, reason="theta_cont/theta_birth come from the noise derivation, job 2")
def test_noise_and_a_short_tone_make_no_track():
    x = _audio(120.0, [(130.0, 0.2, 40, 40.5)])                            # 0.5 s: shorter than n_born frames
    _, ev = _run(x, 100, 160, p=hm.with_params(P, harmonics=1))
    assert ev.tracks == []


def test_invalid_frames_are_crossed_without_a_measurement():
    x = _audio(60.0, [(lambda t: 140.0 - 0.3 * t, 0.2, 0, 60)])
    a, b = int(28 * SR), int(29 * SR)
    _, ev = _run(x, 110, 160, [(x[:a], True), (x[a:b], False), (x[b:], True)], p=hm.with_params(P, harmonics=1, families=1))
    (tr,) = ev.tracks
    assert (~tr.measured).sum() >= 8 and tr.end - tr.start > 50
