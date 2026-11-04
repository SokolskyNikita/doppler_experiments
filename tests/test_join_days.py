"""Joining consecutive day files of flight data across UTC midnight (adsb.join_days)."""
import numpy as np
import pytest

from dopplertrack.adsb import Trace, join_days, load_traces, save_traces
from dopplertrack.geo import enu_to_lla
from dopplertrack.search import Grid, build_segments, cpa_fingerprint, cpa_table

MIDNIGHT = 1712534400.0          # 2024-04-08 00:00 UTC
LAT0, LON0, V, ALT = 40.0, -84.0, 60.0, 1500.0
C = 343.0


def _pass(t):
    """A straight, level eastward pass whose CPA to the origin is 20 s after midnight."""
    x = V * (t - (MIDNIGHT + 20.0))
    lat, lon, _ = enu_to_lla(x, np.zeros_like(x), np.zeros_like(x), LAT0, LON0)
    n = len(t)
    return Trace("abc123", None, "C172", None, t, np.asarray(lat), np.asarray(lon), np.full(n, ALT), np.full(n, V),
                 np.zeros(n, bool), np.full(n, "geometric"), np.full(n, "adsb_icao"), np.zeros(n, np.int32))


def _days(tmp_path, seam_s=15.0, jump_m=0.0, new_leg=True):
    """The pass cut at midnight into two day files with a seam_s gap, the later one optionally displaced."""
    t = np.arange(MIDNIGHT - 600.0, MIDNIGHT + 600.0, 1.0)
    whole = _pass(t)
    a, b = _pass(t[t < MIDNIGHT - seam_s / 2]), _pass(t[t >= MIDNIGHT + seam_s / 2])
    if jump_m:
        b.lat = b.lat + jump_m / 111320.0
    if new_leg:
        b.flags[0] |= 2
    box = [39.5, 40.5, -84.7, -83.3]
    paths = []
    for name, tr in (("d1", a), ("d2", b)):
        paths.append(tmp_path / f"{name}.npz")
        save_traces([tr], paths[-1], metadata={"coverage_bbox": box, "max_range_m": 0.0,
                                               "scan": {"seen": 1, "kept": 1, "malformed": 0, "empty": 0,
                                                        "outside_bbox": 0, "excluded_types": 0}})
    return whole, paths


def _grid():
    """Points 2 km north of the track whose CPAs fall from 40 s before to 40 s after midnight."""
    m = np.arange(-40.0, 41.0, 2.0)
    lat, lon, _ = enu_to_lla(V * (m - 20.0), np.full_like(m, 2000.0), np.zeros_like(m), LAT0, LON0)
    return Grid.points(lat, lon, np.zeros_like(m), LAT0, LON0), m


def _cpa(traces):
    grid, m = _grid()
    segs = build_segments(traces, LAT0, LON0)
    cpa = cpa_table(grid, segs, max_range_m=12000.0, c=C, workers=1)
    return {int(g): (float(r.t_emit), float(r.d)) for g, r in zip(cpa.gidx, cpa.itertuples())}, m


def test_a_pass_cut_at_midnight_keeps_its_cpa_only_when_joined(tmp_path):
    whole, paths = _days(tmp_path)
    ref, m = _cpa([whole])
    in_seam = [i for i, mm in enumerate(m) if abs(mm) <= 7.5]
    assert in_seam and all(i in ref for i in in_seam)
    split, _ = _cpa([tr for p in paths for tr in load_traces(p)])
    assert not any(i in split for i in in_seam)          # the defect: CPAs in the seam are lost
    traces, meta = join_days(paths)
    assert len(traces) == 1 and len(build_segments(traces, LAT0, LON0)) == 1
    joined, _ = _cpa(traces)
    for i in ref:
        assert abs(joined[i][0] - ref[i][0]) <= 0.5 and abs(joined[i][1] - ref[i][1]) <= 5.0
    (seam,) = meta["seams"]
    assert seam["joined"] and seam["icao"] == "abc123" and seam["gap_s"] == pytest.approx(16.0)
    assert meta["coverage_bbox"] == [39.5, 40.5, -84.7, -83.3] and meta["scan"]["kept"] == 2
    assert traces[0].flags[len(load_traces(paths[0])[0])] & 2 == 0      # the file-start new-leg bit is cleared
    assert np.all(np.diff(traces[0].t) > 0)


@pytest.mark.parametrize("seam_s, jump_m, reason", [(300.0, 0.0, "gap over"), (15.0, 5000.0, "position jump")])
def test_a_long_seam_or_a_jump_stays_split(tmp_path, seam_s, jump_m, reason):
    _, paths = _days(tmp_path, seam_s=seam_s, jump_m=jump_m)
    traces, meta = join_days(paths)
    assert len(traces) == 2
    (seam,) = meta["seams"]
    assert not seam["joined"] and reason in seam["reason"]


def test_one_day_is_exactly_load_traces(tmp_path):
    _, paths = _days(tmp_path)
    traces, meta = join_days(paths[:1])
    plain = load_traces(paths[0])
    grid, _ = _grid()
    assert cpa_fingerprint(grid, build_segments(traces, LAT0, LON0), 12000.0, C) == \
        cpa_fingerprint(grid, build_segments(plain, LAT0, LON0), 12000.0, C)
    assert "seams" not in meta


def test_a_legacy_day_joins_with_unknown_provenance(tmp_path):
    whole, paths = _days(tmp_path)
    a = load_traces(paths[0])[0]
    a.alt_source = a.position_source = a.flags = None
    save_traces([a], paths[0])                                   # no metadata, no provenance: a legacy cut
    traces, meta = join_days(paths)
    assert len(traces) == 1 and "coverage_bbox" not in meta
    assert set(traces[0].alt_source[:len(a)]) == {"unknown"} and set(traces[0].alt_source[len(a):]) == {"geometric"}
    assert meta["joined_days"][0]["metadata"].startswith("legacy")
