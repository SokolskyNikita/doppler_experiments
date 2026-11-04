"""Frequency tracks (dopplertrack.freqtrack): sub-bin estimators, the off state, gaps, harmonic links
and each segment rule on its own."""
import numpy as np
import pytest

from dopplertrack import audio, freqtrack as ft
from dopplertrack.tracks import ridge, local_whiten

SR, N, HOP = 4000, 8192, 0.25
DF = SR / N
P = ft.TrackParams()


def _tones(dur, parts, noise=0.4, seed=0):
    """Noise plus tones: parts are (f_hz or callable of t, amplitude, t_on, t_off)."""
    t = np.arange(0, dur, 1 / SR)
    x = noise * np.random.default_rng(seed).standard_normal(len(t))
    for f, a, t0, t1 in parts:
        fi = f(t) if callable(f) else np.full(len(t), float(f))
        x += a * np.sin(2 * np.pi * np.cumsum(fi) / SR) * ((t >= t0) & (t < t1))
    return x.astype(np.float32)


def _track(x, lo, hi, blocks=None, **kw):
    sp = (audio.compute_spectrogram(x, SR, whiten_window_s=None) if blocks is None
          else audio.spectrogram_from_blocks(blocks, SR, whiten_window_s=None))
    return sp, ft.track_window(sp, ft.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], lo, hi, **kw)


@pytest.mark.parametrize("name,tol", [("quadratic", 0.05), ("candan", 0.002), ("quinn2", 0.002)])
def test_estimators_on_a_clean_tone(name, tol):
    x = _tones(4.0, [(200.0 + 0.3 * DF, 1.0, 0, 4)], noise=0.0)
    st = ft.SampleSTFT(x, SR, N, HOP)
    f, _ = ft.refine(st, 2, int(round(200.0 / DF)), name)
    assert abs(f - (200.0 + 0.3 * DF)) / DF < tol


def test_off_state_starts_and_ends_with_the_tone():
    x = _tones(100.0, [(130.0, 0.2, 20, 60)])
    _, ev = _track(x, 100, 160)
    (tr,) = ev.tracks
    assert abs(tr.start - 20) < 2.5 and abs(tr.end - 60) < 2.5          # within the 2.048 s window
    inner = (tr.t > 22) & (tr.t < 58)                                   # the window's edges leak
    assert np.nanmax(np.abs(tr.f[inner] - 130.0)) < 0.05 and tr.measured.all()


def test_consecutive_sources_are_not_chained():
    x = _tones(100.0, [(120.0, 0.2, 10, 40), (126.0, 0.2, 55, 85)])
    sp, ev = _track(x, 100, 160)
    assert len(ev.tracks) == 2
    assert ev.tracks[0].end < 45 and ev.tracks[1].start > 50
    r = ridge(local_whiten(sp.crop(sp.t[0], sp.t[-1], 100, 160)))     # today's ridge spans the window
    assert len(r) == len(sp.t)


def _sweep(f0):
    return lambda t: f0 - 0.3 * t          # local_whiten removes a tone that sits in one bin for long


def test_invalid_frames_are_crossed_without_a_measurement():
    x = _tones(60.0, [(_sweep(140.0), 0.2, 0, 60)])
    def blocks(gap):
        a, b = int(28 * SR), int((28 + gap) * SR)
        return [(x[:a], True), (x[a:b], False), (x[b:], True)]
    _, ev = _track(x, 100, 160, blocks(1.0))
    (tr,) = ev.tracks
    assert (~tr.measured).sum() >= 8 and len(tr.gaps()) == 1 and np.all(np.isnan(tr.f[~tr.measured]))
    _, ev = _track(x, 100, 160, blocks(8.0))                           # longer than max_bridge_s
    assert len(ev.tracks) == 2


def test_harmonics_link_with_gcd_orders():
    sw = lambda h: (lambda t: h * (100.0 - 0.3 * t))
    x = _tones(40.0, [(sw(2), 0.2, 0, 40), (sw(3), 0.2, 0, 40), (sw(4), 0.15, 0, 40)])
    _, ev = _track(x, 150, 450)
    g = ev.event_track()
    assert sorted(g["orders"].values()) == [2, 3, 4]
    x = _tones(40.0, [(sw(1), 0.2, 0, 40), (sw(2), 0.2, 0, 40), (sw(3), 0.15, 0, 40)])
    _, ev = _track(x, 80, 350)
    assert sorted(ev.event_track()["orders"].values()) == [1, 2, 3]


def _mk(t, f, level=None):
    t = np.asarray(t, float); f = np.asarray(f, float)
    lv = np.full(len(t), 20.0) if level is None else np.asarray(level, float)
    return ft.Track(t, f, np.zeros(len(t)), lv, np.isfinite(f), np.where(np.isfinite(f), 1, -1))


def test_cut_weak_drops_a_long_weak_run():
    t = np.arange(0, 20, 0.25)
    lv = np.where((t > 8) & (t < 12.5), 1.0, 20.0)
    pieces = ft.cut_weak(_mk(t, np.full(len(t), 100.0), lv), P)
    assert len(pieces) == 2 and pieces[0].end <= 8 and pieces[1].start >= 12.5
    lv = np.where((t > 8) & (t < 10), 1.0, 20.0)                    # 2 s: kept
    assert len(ft.cut_weak(_mk(t, np.full(len(t), 100.0), lv), P)) == 1


def test_rise_is_cut_or_flagged():
    t = np.arange(0, 20, 0.25)
    f = np.where(t < 10, 120 - 0.5 * t, 115 + 3.0 * (t - 10))       # falls, then rises 3 Hz/s
    pieces = ft.cut_rise(_mk(t, f), P, DF)
    assert len(pieces) == 2 and pieces[0].end < 11.5
    whole = ft.cut_rise(_mk(t, f), P, DF, flag_only=True)
    assert len(whole) == 1 and whole[0].flags["rise"]
    assert len(ft.cut_rise(_mk(t, 120 - 0.5 * t), P, DF)) == 1      # a falling pass is kept


def test_hop_onto_another_line_is_cut():
    t = np.arange(0, 20, 0.25)
    f = np.where(t < 10, 120 - 0.2 * t, 140 - 0.2 * t)               # a 20 Hz jump at 10 s
    pieces = ft.cut_hop(_mk(t, f), P, DF)
    assert len(pieces) == 2 and abs(pieces[1].start - 10) < 0.3
    assert len(ft.cut_hop(_mk(t, 120 - 2.0 * t), P, DF)) == 1         # a steady steep slope is not a hop


def test_link_across_a_short_gap():
    a = _mk(np.arange(0, 10, 0.25), 120 - 0.5 * np.arange(0, 10, 0.25))
    tb = np.arange(13, 20, 0.25)
    joined = ft.link_gaps([a, _mk(tb, 120 - 0.5 * tb)], P, DF, 0.25)
    assert len(joined) == 1 and len(joined[0].gaps()) == 1 and joined[0].flags["linked"] == 1
    off = ft.link_gaps([a, _mk(tb, 140 - 0.5 * tb)], P, DF, 0.25)  # starts far from the extrapolation
    assert len(off) == 2


def test_crossing_re_pairs_by_slope():
    t = np.arange(0, 20, 0.25)
    fall, steady = 130 - 2.0 * t, np.full(len(t), 110.0)             # cross at 10 s
    a = _mk(t, np.where(t <= 10, fall, steady))                      # the tracker swapped at the crossing
    b = _mk(t, np.where(t <= 10, steady, fall))
    out = ft.resolve_crossings([a, b], P, DF)
    f0 = sorted(out, key=lambda tr: tr.f[0])
    assert np.allclose(f0[0].f, steady) and np.allclose(f0[1].f, fall)
