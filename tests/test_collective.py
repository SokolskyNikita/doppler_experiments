"""The collective find on synthetic data: two flights heard at the origin, plus a window no flight explains. The coarse
to fine map's winner must be near the origin, with both flights matched and the empty window adding nothing.

The windows stand in for detection's: each true pass's heard CPA and tone, off by what a coarse straight template
leaves (+4 s, +3 %), so the clock vote and the f0 sweep have real work. A +-4 % sweep and 60 null draws keep it fast."""
import numpy as np

from dopplertrack.methods.collective import search as collective
from dopplertrack.core import propagation as doppler
from dopplertrack.data.trajectories import Trace
from dopplertrack.core.geometry import enu_to_lla, haversine_m
import dopplertrack.components.search.segments as segments
import dopplertrack.components.stft as stft
import dopplertrack.components.scoring.point_score as point_score
import dopplertrack.components.windows as windows
from dopplertrack.methods.collective.parameters import resolve_collective


def _trace(icao, t, enu, lat0, lon0, gs):
    lat, lon, alt = enu_to_lla(enu[:, 0], enu[:, 1], enu[:, 2], lat0, lon0)
    return Trace(icao, None, "C172", "synthetic", t, lat, lon, alt, np.full_like(t, gs), np.zeros(len(t), bool))


def test_collective_find_puts_the_winner_at_the_observer_and_floors_an_empty_window():
    c, sr, T0 = 340.0, 4000, 1_700_000_000.0
    lat0, lon0 = 40.8765, -73.525
    t1 = T0 + np.arange(0, 900, 5.0)
    enu1 = np.stack([110.0 * (t1 - (T0 + 300)), np.full_like(t1, 2500.0), np.full_like(t1, 1500.0)], -1)
    t2 = T0 + np.arange(900, 1800, 5.0)
    tau = t2 - (T0 + 1220)
    enu2 = np.stack([3000.0 + 0.02 * tau ** 2, 95.0 * tau, np.full_like(t2, 1200.0)], -1)   # a gentle turn
    traces = [_trace("aaa001", t1, enu1, lat0, lon0, 110 / 0.5144), _trace("aaa002", t2, enu2, lat0, lon0, 95 / 0.5144)]
    segs = segments.build_segments(traces, lat0, lon0)
    tt = np.arange(0, 1800, 1 / sr)
    x = 0.4 * np.random.default_rng(1).standard_normal(len(tt)).astype(np.float32)
    wins = []
    for seg, f0 in zip(segs, (120.0, 130.0)):
        to, ratio, _ = doppler.curve_from_trajectory(seg.t, seg.enu, np.zeros(3), f0=1.0, c=c)
        finst = np.interp(tt + T0, to, ratio, left=np.nan, right=np.nan) * f0
        m = np.isfinite(finst)
        x[m] += 0.05 * np.sin(2 * np.pi * np.cumsum(np.nan_to_num(finst, nan=0.0)) / sr)[m]
        heard = float(to[np.argmin(np.abs(ratio - 1))]) - T0          # the heard CPA: no Doppler shift
        wins.append(windows.Window(heard - 100, heard + 100, 1.03 * f0, heard + 4.0, 1.0))
    sp = stft.compute_spectrogram(x, sr, nperseg=8192, hop_s=0.5, fmin=60, fmax=300, whiten_window_s=None)
    wins.append(windows.Window(1500.0, 1700.0, 150.0, 1600.0, 0.0))     # nothing passes then: noise only
    params = resolve_collective({"speed_of_sound_m_s": c, "f0_span": 0.04, "null_n": 60})
    out = collective.collective_detection(sp, wins, traces, (lat0 - 0.03, lat0 + 0.03, lon0 - 0.035, lon0 + 0.035),
                                          params, workers=1, log=lambda m: None)
    w = out["winner"]
    assert w is not None, out.get("reason")
    assert haversine_m(w["lat"], w["lon"], lat0, lon0) < 1000.0, w
    matched = [m for m in w["windows"][:2] if m and m["z"] > 0]
    assert {m["icao"] for m in matched} == {"aaa001", "aaa002"}, w["windows"]
    assert abs(w["clock_audio_minus_unix"] + T0) < 10.0
    empty = w["windows"][2]
    assert empty is None or empty["z"] <= 0 or w["n_matched"] == 3      # a floor: it adds nothing, never subtracts


def test_a_pass_explains_one_window_and_the_other_falls_back():
    import pandas as pd
    scored = pd.DataFrame({"gidx": [0, 0, 0], "w": [0, 1, 1], "seg": [0, 0, 1], "t_heard": [100.0, 100.0, 200.0],
                           "b": [-50.0, -50.0, -50.0], "s": [0.0] * 3, "f0_scale": [1.0] * 3, "z": [5.0, 4.0, 1.0]})
    assert point_score.point_scores(scored, 2).Z.iloc[0] == 6.0                     # window 1 falls back to segment 1
    assert point_score.point_scores(scored, 2, one_pass=False).Z.iloc[0] == 9.0     # the old rule counted segment 0 twice


def _scored_rows(rows):
    import pandas as pd
    return pd.DataFrame([dict(gidx=0, w=w, seg=seg, t_heard=heard, b=-50.0, s=z, f0_scale=1.0, z=z)
                         for w, seg, heard, z in rows])


def _assert_report_matches_score(scored, n_windows, expected_z, expected_windows):
    from types import SimpleNamespace
    point = point_score.point_scores(scored, n_windows).iloc[0]
    segs = [SimpleNamespace(icao=f"flight-{i}") for i in range(int(scored.seg.max()) + 1)]
    wins = [SimpleNamespace(f0=120.0) for _ in range(n_windows)]
    matches, _ = point_score.matched_at(scored, 0, float(point.b), segs, wins)
    positive = {i: m for i, m in enumerate(matches) if m and m["z"] > 0}
    assert point.Z == expected_z
    assert set(positive) == set(expected_windows)
    assert point.n_matched == len(positive)
    assert sum(m["z"] for m in positive.values()) == point.Z


def test_greedy_fallback_does_not_consume_an_unused_alternate_pass():
    scored = _scored_rows([(0, 0, 100.0, 5.0), (0, 1, 200.0, 4.0), (1, 1, 200.0, 3.0)])
    _assert_report_matches_score(scored, 2, 8.0, [0, 1])


def test_report_uses_the_same_rounded_pass_identity_as_the_score():
    scored = _scored_rows([(0, 0, 100.1, 5.0), (1, 0, 100.4, 4.0)])
    _assert_report_matches_score(scored, 2, 5.0, [0])


def test_report_respects_the_same_bounded_fallback_as_the_score():
    scored = _scored_rows([(0, 0, 100.0, 10.0), (0, 1, 200.0, 9.0), (0, 2, 300.0, 8.0), (0, 3, 400.0, 7.0),
                           (1, 0, 100.0, 11.0), (2, 1, 200.0, 12.0), (3, 2, 300.0, 13.0)])
    _assert_report_matches_score(scored, 4, 36.0, [1, 2, 3])
