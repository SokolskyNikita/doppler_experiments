"""Extraction margins, durable diagnostics, and candidate-local trace gaps."""
import io
import json
import tarfile

import numpy as np
import pandas as pd
import pytest

from dopplertrack import adsb, coverage, fetch, pipeline, search
from dopplertrack.audio import Spectrogram
from dopplertrack.geo import enu_to_lla
from dopplertrack.tracks import EventFit


def _trace_bytes(north_m=0):
    t = np.arange(0, 601, 5.0)
    lat, lon, alt = enu_to_lla(100 * (t - 300), np.full_like(t, north_m),
                              np.full_like(t, 1000), 40, -74)
    rows = [[float(ti), float(la), float(lo), float(al / adsb.FT), 194]
            for ti, la, lo, al in zip(t, lat, lon, alt)]
    return json.dumps(dict(icao="abc123", t="C172", timestamp=1e9, trace=rows)).encode()


def _tar(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for i, raw in enumerate(entries):
            ti = tarfile.TarInfo(f"traces/00/trace_full_{i:06x}.json")
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
    return buf.getvalue()


def test_fetch_margin_keeps_outside_flight_with_cpa_near_edge(tmp_path, monkeypatch, capsys):
    bbox = (39.99, 40.01, -74.01, -73.99)
    tr = adsb.parse_trace_bytes(_trace_bytes(north_m=8000))
    assert not adsb.in_bbox(tr, bbox)
    archive = _tar([_trace_bytes(north_m=8000), b"not JSON"])
    seen = []

    def fake_fetch(date, envelope, pod, progress, report):
        seen.append(envelope)
        return list(fetch.iter_tar_traces(io.BytesIO(archive), envelope, report=report))

    monkeypatch.setattr(fetch, "fetch_day", fake_fetch)
    target = tmp_path / "flights.npz"
    kept = pipeline.fetch_region("2024-04-07", bbox, target, prop_only=False, max_range_m=9000)
    assert len(kept) == 1 and adsb.in_bbox(tr, seen[0])
    back = adsb.load_traces(target)
    meta = adsb.load_trace_metadata(target)
    assert meta["requested_bbox"] == list(bbox)
    assert meta["coverage_bbox"] == list(seen[0]) and meta["max_range_m"] == 9000
    assert meta["date"] == "2024-04-07"
    assert meta["scan"] == dict(seen=2, kept=1, malformed=1, empty=0, outside_bbox=0, excluded_types=0)
    grid = search.Grid.points([40.01], [-74], [0])
    cpa = search.cpa_table(grid, search.build_segments(back, grid.lat0, grid.lon0), max_range_m=9000)
    assert len(cpa) == 1 and cpa.d.iloc[0] < 9000
    assert "1 skipped as malformed" in capsys.readouterr().out


def test_local_extraction_records_margin_and_skip_counts(tmp_path, monkeypatch):
    folder = tmp_path / "traces" / "00"
    folder.mkdir(parents=True)
    (folder / "trace_full_abc123.json").write_bytes(_trace_bytes(8000))
    (folder / "trace_full_bad000.json").write_bytes(b"{} broken")
    # Run the real worker in-process to keep this test independent of process spawning.
    class SerialExecutor:
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def map(self, func, jobs, **kwargs):
            return map(func, jobs)
    monkeypatch.setattr(adsb, "process_pool", SerialExecutor)
    target = tmp_path / "flights.npz"
    kept = pipeline.extract_region(tmp_path, (39.99, 40.01, -74.01, -73.99), target, prop_only=False)
    assert len(kept) == 1
    assert adsb.load_trace_metadata(target)["scan"]["malformed"] == 1


def test_scan_counts_malformed_empty_and_outside():
    report = coverage.ScanReport()
    archive = _tar([_trace_bytes(), b"bad json", b'{"trace":[[0]]}', b'{"trace":[]}', _trace_bytes(50000)])
    kept = list(fetch.iter_tar_traces(io.BytesIO(archive), (39, 41, -75, -73), report=report))
    assert len(kept) == 2
    assert report.seen == 5 and report.kept == 2 and report.malformed == 2 and report.empty == 1
    report = coverage.ScanReport()
    assert list(fetch.iter_tar_traces(io.BytesIO(archive), (0, 1, 0, 1), report=report)) == []
    assert report.outside_bbox == 2


def test_coverage_warns_for_missing_or_insufficient_envelope(tmp_path):
    bbox = (40, 41, -75, -74)
    target = tmp_path / "legacy.npz"
    adsb.save_traces([], target)
    assert adsb.load_trace_metadata(target) == {}
    messages = []
    coverage.report_coverage({}, bbox, 12000, messages.append)
    assert any("unknown" in m for m in messages)
    assert coverage.ADS_B_LIMITATION in messages
    meta = coverage.extraction_metadata(bbox, 6000, coverage.ScanReport())
    messages.clear()
    coverage.report_coverage(meta, bbox, 12000, messages.append)
    assert any("does not cover" in m for m in messages)
    messages.clear()
    coverage.report_coverage(meta, bbox, 6000, messages.append)
    assert not any("WARNING" in m for m in messages)


@pytest.mark.parametrize("bbox", [(0, 1, 179.99, 180), (89.99, 90, -1, 1)])
def test_padding_near_dateline_and_pole_is_conservative(bbox):
    envelope = coverage.padded_bbox(bbox, 12000)
    assert envelope[2:] == (-180, 180)


def test_candidate_gaps_are_local_in_space_and_time():
    tr = adsb.parse_trace_bytes(_trace_bytes())
    # Remove observations around CPA; keep both ends of the known gap.
    keep = (tr.t < 1e9 + 200) | (tr.t > 1e9 + 400)
    for name in ("t", "lat", "lon", "alt", "gs", "on_ground", "alt_source", "position_source", "flags"):
        setattr(tr, name, getattr(tr, name)[keep])
    assert coverage.candidate_gaps([tr], 40, -74, 1e9, 1e9 + 600, 12000) == [
        ("abc123", 1e9 + 195, 1e9 + 405, "time gap")]
    assert coverage.candidate_gaps([tr], 0, 0, 1e9, 1e9 + 600, 12000) == []
    assert coverage.candidate_gaps([tr], 40, -74, 1e9 + 500, 1e9 + 600, 12000) == []
    sp = Spectrogram(np.array([0, 600]), np.array([100, 101]), np.zeros((2, 2)))
    ev = EventFit(300, 297, 120, 100, 1000, 200, 400, 1, 150, 90)
    rows = pd.DataFrame([dict(lat=40, lon=-74, t_heard1=1e9 + 300, shift=0)])
    messages = []
    coverage.report_candidate_gaps([tr], rows, sp, ev, 12000, 340, messages.append)
    assert any("candidate 1: 1 known nearby trace gaps" in m for m in messages)


@pytest.mark.parametrize("clip", [None, (-15000, 15000, -12000, 12000)])
def test_resampling_masks_a_cpa_gap_without_moving_the_cpa_proposal(clip):
    tr = adsb.parse_trace_bytes(_trace_bytes())
    keep = (tr.t <= 1e9 + 280) | (tr.t >= 1e9 + 325)
    for name in ("t", "lat", "lon", "alt", "gs", "on_ground", "alt_source", "position_source", "flags"):
        setattr(tr, name, getattr(tr, name)[keep])
    segs = search.build_segments([tr], 40, -74, clip_enu=clip)
    assert len(segs) == 1
    segment = segs[0]
    gap = (segment.t > 1e9 + 280) & (segment.t < 1e9 + 325)
    assert gap.any() and not segment.valid[gap].any()
    assert segment.valid[~gap].all()
    # CPA uses the interpolated geometry for a proposal, so it remains inside
    # the hole. The curve's evidence mask must survive all the way to scoring.
    grid = search.Grid.points([40], [-74], [0])
    cpa = search.cpa_table(grid, segs, max_range_m=12000, c=340)
    assert len(cpa) == 1 and abs(cpa.t_emit.iloc[0] - (1e9 + 300)) <= 1
    from dopplertrack.score import modelled_curve, EventWindow
    to, ratio = modelled_curve(segment, np.zeros(3), 340)
    assert np.isnan(ratio[gap]).all()
    fit = EventFit(1e9 + 303, 1e9 + 300, 1, 100, 1000, to.min(), to.max(), 0, 150, 90)
    times = np.arange(to.min(), to.max(), 0.25)
    spec = Spectrogram(times, np.array([0.0, 1.0, 2.0]), np.ones((3, len(times))) * 10)
    window = EventWindow(fit, spec)
    gidx = int(cpa.gidx.iloc[0])
    obs = grid.enu[gidx]
    to, ratio = modelled_curve(segment, obs, 340)
    _, full_ratio = modelled_curve(search.Segment(segment.trace_idx, segment.icao, segment.t,
                                                 segment.enu, segment.speed), obs, 340)
    full = window.curve_score(to, full_ratio)
    assert 0.6 * full < window.curve_score(to, ratio) < full - 0.3


def test_diagnostic_reports_missing_height_and_new_leg_boundaries():
    tr = adsb.parse_trace_bytes(_trace_bytes())
    tr.alt[55:57] = np.nan
    tr.flags[65] |= 2
    gaps = coverage.candidate_gaps([tr], 40, -74, 1e9, 1e9 + 600, 12000)
    assert [(start, end, reason) for _, start, end, reason in gaps] == [
        (1e9 + 270, 1e9 + 285, "missing position/altitude"), (1e9 + 320, 1e9 + 325, "new leg")]


def test_stale_flag_preserves_cpa_inside_a_25_second_reception_gap():
    tr = adsb.parse_trace_bytes(_trace_bytes())
    keep = (tr.t <= 1e9 + 290) | (tr.t >= 1e9 + 315)
    for name in ("t", "lat", "lon", "alt", "gs", "on_ground", "alt_source", "position_source", "flags"):
        setattr(tr, name, getattr(tr, name)[keep])
    tr.flags[tr.t == 1e9 + 315] |= 1
    segs = search.build_segments([tr], 40, -74)
    assert len(segs) == 1 and segs[0].valid.all()
    grid = search.Grid.points([40], [-74], [0])
    cpa = search.cpa_table(grid, segs, max_range_m=12000, c=340)
    assert len(cpa) == 1 and abs(cpa.t_emit.iloc[0] - (1e9 + 300)) <= 1


def test_data_report_quantifies_barometric_only_and_unknown_altitudes():
    tr = adsb.parse_trace_bytes(_trace_bytes())
    tr.alt_source[:] = "geometric"
    tr.alt_source[:10] = "barometric"
    messages = []
    coverage.report_altitude_sources([tr], messages.append)
    assert "10/121 points barometric-only" in messages[0]
    tr.alt_source = None
    coverage.report_altitude_sources([tr], messages.append)
    assert "121 source unknown" in messages[1]
