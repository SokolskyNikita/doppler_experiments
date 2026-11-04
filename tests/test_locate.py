"""dopplertrack locate (PLAN Phase 3 step A): every outcome on synthetic inputs, with the search stubbed."""
import datetime

import numpy as np
import pandas as pd
import pytest

from dopplertrack import adsb, audio, cache, locate, pipeline, tracks
from dopplertrack.result import validate

DAY = "2026-09-08"
DAY0 = datetime.datetime(2026, 9, 8, tzinfo=datetime.timezone.utc).timestamp()
BOX = [40.0, 40.05, -74.0, -73.95]
ENVELOPE = [39.8, 40.3, -74.3, -73.6]


def _event(t, score):
    return tracks.EventFit(t, t - 3, 120, 100, 1000, t - 30, t + 30, score, 150, 90)


@pytest.fixture
def spec(tmp_path):
    t, f = np.arange(0, 3600, 1.0), np.arange(40, 251, 1.0)
    path = tmp_path / "spec.npz"
    audio.Spectrogram(t, f, np.zeros((len(f), len(t)), np.float32)).save(path)
    return path


def _traces(tmp_path, envelope=ENVELOPE, covered=None, metadata=True, name="traces.npz"):
    path = tmp_path / name
    meta = {"coverage_bbox": envelope, "date": DAY}
    if covered:
        meta["covered_utc"] = covered
    adsb.save_traces([], path, metadata=meta if metadata else None)
    return path


def _detections(monkeypatch, events):
    monkeypatch.setattr(cache, "cached_detections", lambda sp, produce, **kw: events)


def _search_returning(monkeypatch, t_heard1, empty=False):
    """run_search stubbed: one candidate whose clock maps audio second 1000 to t_heard1 (unix)."""
    def fake(sp, ev1, ev2, traces, grid, **kw):
        rows = [] if empty else [dict(gidx=0, lat=40.02, lon=-73.97, seg1=0, seg2=1, icao1="a", icao2="b",
                                      t_heard1=t_heard1, d1=1, v1=1, d2=1, v2=1, score=10.0, s1=6.0, s2=4.0, shift=0.0),
                                 dict(gidx=0, lat=40.03, lon=-73.96, seg1=2, seg2=3, icao1="c", icao2="d",
                                      t_heard1=t_heard1, d1=1, v1=1, d2=1, v2=1, score=8.0, s1=5.0, s2=3.0, shift=0.0)]
        res = pd.DataFrame(rows, columns=["gidx", "lat", "lon", "seg1", "seg2", "icao1", "icao2", "t_heard1", "d1",
                                          "v1", "d2", "v2", "score", "s1", "s2", "shift"])
        res.attrs["funnel"] = {"cpa_rows": 10, "time_join": 4, "silence": 4, "scored": len(rows)}
        segs = [type("S", (), {"icao": k})() for k in "abcd"]
        return res, segs
    monkeypatch.setattr(pipeline, "run_search", fake)
    monkeypatch.setattr(pipeline, "pick_flight", lambda *a, **k: (-1, 0.0))
    monkeypatch.setattr(pipeline, "refine", lambda *a, **k: pd.DataFrame([dict(lat=40.021, lon=-73.971, score=10.5,
                                                                                  s1=6.1, s2=4.4, shift=0.0)]))


def _run(spec, traces, tmp_path, **cfg):
    out = locate.locate(spec, DAY, BOX, traces, locate.LocateConfig(dem=False, **cfg), out_dir=tmp_path / "out")
    validate(out.record)
    return out.record["verdict"]


def test_fewer_than_two_usable_flyovers(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), tracks.EventFit.unfit(1500, 1600, "band too narrow")])
    v = _run(spec, [_traces(tmp_path)], tmp_path)
    assert v["outcome"] == "insufficient_evidence" and v["reason_codes"] == ["no_usable_flyovers"]


@pytest.mark.parametrize("kw", [dict(envelope=[40.0, 40.05, -74.0, -73.95]), dict(metadata=False)])
def test_flight_data_short_of_the_box_or_without_an_envelope(monkeypatch, spec, tmp_path, kw):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    v = _run(spec, [_traces(tmp_path, **kw)], tmp_path)
    assert v["reason_codes"] == ["flight_data_missing_box"]


def test_a_declared_envelope_stands_in_for_missing_metadata(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    v = _run(spec, [_traces(tmp_path, metadata=False)], tmp_path, envelope=[ENVELOPE])
    assert v["outcome"] == "ambiguous"


def test_flight_data_short_of_the_day(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    v = _run(spec, [_traces(tmp_path, covered=[DAY0, DAY0 + 70000.0])], tmp_path)
    assert v["reason_codes"] == ["flight_data_missing_time"]


def test_no_surviving_candidate(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0, empty=True)
    v = _run(spec, [_traces(tmp_path)], tmp_path)
    assert v["reason_codes"] == ["no_surviving_candidate"]


def test_a_clock_past_utc_midnight_with_one_day(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 86000.0)            # audio 1000 s at 23:53:20, so the hour ends past midnight
    v = _run(spec, [_traces(tmp_path)], tmp_path)
    assert v["reason_codes"] == ["past_utc_midnight"] and "--days 1" in v["reasons"][0]


def test_a_found_answer_is_ambiguous_with_its_reasons_and_both_rules_report(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0), _event(3000, 3.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    out = locate.locate(spec, DAY, BOX, [_traces(tmp_path)], locate.LocateConfig(dem=False, pair_rule="both"),
                        out_dir=tmp_path / "out")
    validate(out.record)
    v = out.record["verdict"]
    assert v["outcome"] == "ambiguous" and v["reason_codes"] == ["winner_only_refined", "silence_filter_off"]
    rules = {r["rule"]: r for r in out.record["pair_rules"]}
    assert rules["top2"]["chosen"] and not rules["comparable"]["chosen"] and rules["top2"]["events"] == [1, 2]
    assert out.record["refined"]["lat"] == pytest.approx(40.021)
    assert (tmp_path / "out" / "funnel_triples.npz").exists()
    assert any("rule comparable" in line and " s" in line for line in out.summary)       # its time is printed


def test_locate_never_emits_located(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    assert _run(spec, [_traces(tmp_path)], tmp_path, silence_d_m=6000.0)["outcome"] != "located"


def test_a_ground_temperature_reaches_the_search_and_the_refinement(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0), _event(3000, 3.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    seen = {}

    def spy(name, fn):
        def wrapped(*args, **kw):
            seen[name] = kw
            return fn(*args, **kw)
        return wrapped
    monkeypatch.setattr(pipeline, "run_search", spy("search", pipeline.run_search))
    monkeypatch.setattr(pipeline, "refine", spy("refine", pipeline.refine))
    _run(spec, [_traces(tmp_path)], tmp_path, c=346.5, temperature_c=25.6)
    assert all(seen[k]["temperature_c"] == 25.6 and seen[k]["c"] == 346.5 for k in ("search", "refine"))


def test_the_cpa_table_folder_is_made_on_a_fresh_cache(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    table = tmp_path / "fresh-cache" / "cpa" / "bench" / "x.npz"
    _run(spec, [_traces(tmp_path)], tmp_path, cpa_cache=str(table))
    assert table.parent.is_dir()
