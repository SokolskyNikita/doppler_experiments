from pathlib import Path
import json

import numpy as np

from dopplertrack import adsb

HERE = Path(__file__).parent


def test_parse_readsb_trace():
    tr = adsb.parse_trace_file(HERE / "data" / "trace_full_a2f38b.json")
    assert tr.icao == "a2f38b" and tr.typ == "SR20" and tr.reg == "N29EF"
    assert len(tr) > 500
    assert np.all(np.diff(tr.t) >= 0)
    assert tr.lat.min() > 39 and tr.lat.max() < 42 and tr.lon.min() > -76
    air = ~tr.on_ground
    assert np.nanmax(tr.alt[air]) > 300          # metres
    assert np.nanmax(tr.gs[air]) > 40            # m/s
    segs = tr.segments()
    assert segs and all(not tr.on_ground[s.start] for s in segs)
    t, enu = tr.enu(segs[0], 40.1, -74.1)
    assert enu.shape == (len(t), 3) and np.all(np.isfinite(enu))


def test_save_load_round_trip(tmp_path):
    tr = adsb.parse_trace_file(HERE / "data" / "trace_full_a2f38b.json")
    adsb.save_traces([tr], tmp_path / "t.npz")
    back = adsb.load_traces(tmp_path / "t.npz")[0]
    assert back.icao == tr.icao and back.typ == tr.typ
    assert np.allclose(back.t, tr.t) and np.array_equal(back.on_ground, tr.on_ground)
    assert np.array_equal(back.alt_source, tr.alt_source)
    assert np.array_equal(back.position_source, tr.position_source)
    assert np.array_equal(back.flags, tr.flags)


def test_altitude_and_position_provenance_and_readsb_flags():
    def row(t, alt, flags=0, source="adsb_icao", geom=None):
        return [t, 40, -74, alt, 100, 90, flags, None, None, source, geom]
    tr = adsb.parse_trace_bytes(json.dumps(dict(timestamp=0, trace=[
        row(0, 1000, source="mlat", geom=1200),
        row(5, 1300, flags=8, source="tisb_icao"),
        row(10, 900), row(15, None), row(20, "ground"),
    ])).encode())
    assert list(tr.alt_source) == ["geometric", "geometric", "barometric", "none", "none"]
    assert list(tr.position_source) == ["mlat", "tisb_icao", "adsb_icao", "adsb_icao", "adsb_icao"]
    assert np.allclose(tr.alt[:3], np.array([1200, 1300, 900]) * adsb.FT)
    assert np.isnan(tr.alt[3:]).all()
    assert list(tr.flags) == [0, 8, 0, 0, 0]


def test_fresh_fixes_after_reception_gaps_are_not_dropped():
    rows = [[t, 40, -74, 1000, 100, 90, flag] for t, flag in
            [(0, 0), (5, 0), (30, 1), (35, 0), (40, 0)]]
    tr = adsb.parse_trace_bytes(json.dumps(dict(trace=rows)).encode())
    assert [(sl.start, sl.stop) for sl in tr.segments()] == [(0, 5)]
    assert list(tr.coverage_gaps()) == []
    t, _, _, _, valid = tr.resample(tr.segments()[0], return_valid=True)
    assert valid.all() and ((t > 5) & (t < 30)).any()


def test_missing_altitude_and_new_legs_break_segments():
    rows = [[t, 40, -74, 1000, 100, 90, flag] for t, flag in
            [(0, 0), (5, 0), (10, 1), (15, 0), (20, 0), (25, 2), (30, 0)]]
    tr = adsb.parse_trace_bytes(json.dumps(dict(trace=rows)).encode())
    assert [(sl.start, sl.stop) for sl in tr.segments()] == [(0, 5), (5, 7)]
    tr.alt[3] = np.nan
    assert [(sl.start, sl.stop) for sl in tr.segments()] == [(0, 3), (5, 7)]


def test_coverage_gaps_share_position_and_boundary_rules():
    rows = [[t, 40, -74, alt, 100, 90, flag] for t, alt, flag in
            [(0, 1000, 0), (5, 1000, 0), (10, None, 0), (15, 1000, 0), (20, 1000, 2),
             (25, 1000, 0), (70, 1000, 1), (75, 1000, 0), (80, "ground", 0), (85, 1000, 0)]]
    tr = adsb.parse_trace_bytes(json.dumps(dict(trace=rows)).encode())
    assert list(tr.coverage_gaps()) == [(1, 3, "missing position/altitude"), (3, 4, "new leg"), (5, 6, "time gap")]
    assert list(tr.break_indices(30)) == [2, 3, 4, 6, 8, 9]


def test_legacy_npz_does_not_invent_altitude_provenance(tmp_path):
    tr = adsb.parse_trace_file(HERE / "data" / "trace_full_a2f38b.json")
    tr.alt_source = tr.position_source = tr.flags = None
    target = tmp_path / "legacy.npz"
    adsb.save_traces([tr], target)
    back = adsb.load_traces(target)[0]
    assert back.alt_source is None and back.position_source is None and back.flags is None
