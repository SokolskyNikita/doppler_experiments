"""The collective find on synthetic data: two flights heard at the origin, plus a window no flight explains. The coarse
to fine map's winner must be near the origin, with both flights matched and the empty window adding nothing.

The windows stand in for detection's: each true pass's heard CPA and tone, off by what a coarse straight template
leaves (+4 s, +3 %), so the clock vote and the f0 sweep have real work. A +-4 % sweep and 60 null draws keep it fast."""
import numpy as np

from dopplertrack import audio, collective, doppler, search
from dopplertrack.adsb import Trace
from dopplertrack.geo import enu_to_lla, haversine_m


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
    segs = search.build_segments(traces, lat0, lon0)
    tt = np.arange(0, 1800, 1 / sr)
    x = 0.4 * np.random.default_rng(1).standard_normal(len(tt)).astype(np.float32)
    wins = []
    for seg, f0 in zip(segs, (120.0, 130.0)):
        to, ratio, _ = doppler.curve_from_trajectory(seg.t, seg.enu, np.zeros(3), f0=1.0, c=c)
        finst = np.interp(tt + T0, to, ratio, left=np.nan, right=np.nan) * f0
        m = np.isfinite(finst)
        x[m] += 0.05 * np.sin(2 * np.pi * np.cumsum(np.nan_to_num(finst, nan=0.0)) / sr)[m]
        heard = float(to[np.argmin(np.abs(ratio - 1))]) - T0          # the heard CPA: no Doppler shift
        wins.append(collective.Window(heard - 100, heard + 100, 1.03 * f0, heard + 4.0, 1.0))
    sp = audio.compute_spectrogram(x, sr, nperseg=8192, hop_s=0.5, fmin=60, fmax=300, whiten_window_s=None)
    wins.append(collective.Window(1500.0, 1700.0, 150.0, 1600.0, 0.0))     # nothing passes then: noise only
    out = collective.collective_find(sp, wins, traces, (lat0 - 0.03, lat0 + 0.03, lon0 - 0.035, lon0 + 0.035),
                                     c=c, workers=1, log=lambda m: None, f0_span=0.04, null_n=60)
    w = out["winner"]
    assert w is not None, out.get("reason")
    assert haversine_m(w["lat"], w["lon"], lat0, lon0) < 1000.0, w
    matched = [m for m in w["windows"][:2] if m and m["z"] > 0]
    assert {m["icao"] for m in matched} == {"aaa001", "aaa002"}, w["windows"]
    assert abs(w["clock_audio_minus_unix"] + T0) < 10.0
    empty = w["windows"][2]
    assert empty is None or empty["z"] <= 0 or w["n_matched"] == 3      # a floor: it adds nothing, never subtracts
