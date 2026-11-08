"""dopplertrack locate (PLAN Phase 3 step A): every outcome on synthetic inputs, with the search stubbed."""
import datetime

import numpy as np
import pandas as pd
import pytest

from dopplertrack import audio, cache, locate, pipeline
from dopplertrack.result import validate
import dopplertrack.components.types as components_types
import dopplertrack.components.assignment.pick_flight as pick_flight
from dopplertrack.components.search.clock_gate import clock_gate
import dopplertrack.data.region_loading as region_loading
from dopplertrack.methods.grid_pair.parameters import resolve

DAY = "2026-09-08"
DAY0 = datetime.datetime(2026, 9, 8, tzinfo=datetime.timezone.utc).timestamp()
BOX = [40.0, 40.05, -74.0, -73.95]
ENVELOPE = [39.8, 40.3, -74.3, -73.6]


def _event(t, score):
    return components_types.EventFit(t, t - 3, 120, 100, 1000, t - 30, t + 30, score, 150, 90)


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
    region_loading.save_traces([], path, metadata=meta if metadata else None)
    return path


def _detections(monkeypatch, events):
    monkeypatch.setattr(cache, "cached_detections", lambda sp, produce, **kw: events)


def _search_returning(monkeypatch, t_heard1, empty=False):
    """run_search stubbed: one candidate whose clock maps audio second 1000 to t_heard1 (unix)."""
    def fake(sp, ev1, ev2, traces, grid, params=None, **kw):
        rows = [] if empty else [dict(gidx=0, lat=40.02, lon=-73.97, seg1=0, seg2=1, icao1="a", icao2="b",
                                      t_heard1=t_heard1, d1=1, v1=1, d2=1, v2=1, score=10.0, s1=6.0, s2=4.0, shift=0.0),
                                 dict(gidx=0, lat=40.03, lon=-73.96, seg1=2, seg2=3, icao1="c", icao2="d",
                                      t_heard1=t_heard1, d1=1, v1=1, d2=1, v2=1, score=8.0, s1=5.0, s2=3.0, shift=0.0)]
        res = pd.DataFrame(rows, columns=["gidx", "lat", "lon", "seg1", "seg2", "icao1", "icao2", "t_heard1", "d1",
                                          "v1", "d2", "v2", "score", "s1", "s2", "shift"])
        res.attrs["funnel"] = {"cpa_rows": 10, "time_join": 4, "silence": 4, "scored": len(rows)}
        segs = [type("S", (), {"icao": k})() for k in "abcd"]
        return res, segs
    monkeypatch.setattr(pipeline, "pair_grid_search", fake)
    monkeypatch.setattr(pipeline, "pick_flight", lambda *a, **k: (-1, 0.0))
    monkeypatch.setattr(pick_flight, "pick_flight", lambda *a, **k: (-1, 0.0))      # runner looks it up there
    monkeypatch.setattr(pipeline, "refine", lambda *a, **k: pd.DataFrame([dict(lat=40.021, lon=-73.971, score=10.5,
                                                                                  s1=6.1, s2=4.4, shift=0.0)]))


RUN = ("envelope", "cpa_cache", "workers")


def _locate(spec, traces, tmp_path, **cfg):
    """locate on the locate profile with the terrain off; cfg holds parameter overrides and run settings."""
    run = locate.RunSettings(**{k: cfg.pop(k) for k in RUN if k in cfg})
    return locate.locate(spec, DAY, BOX, traces, resolve("locate", overrides={"grid.dem": False, **cfg}), run,
                         out_dir=tmp_path / "out")


def _run(spec, traces, tmp_path, **cfg):
    out = _locate(spec, traces, tmp_path, **cfg)
    validate(out.record)
    return out.record["verdict"]


def test_fewer_than_two_usable_flyovers(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), components_types.EventFit.unfit(1500, 1600, "band too narrow")])
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


def test_with_a_stated_start_the_flight_data_need_cover_only_the_gated_recording(monkeypatch, spec, tmp_path):
    """Audio second 1000 at DAY0 + 72000 puts the start at DAY0 + 71000; the 3600 s recording, the stated 1 s, the
    6 s tol_s and GATE_PAD_S need the data from DAY0 + 70693 to DAY0 + 74906, not the whole day."""
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    gate = dict(start_utc=DAY0 + 71000.0, start_tol_s=1.0)
    v = _run(spec, [_traces(tmp_path, covered=[DAY0, DAY0 + 76000.0])], tmp_path, **gate)
    assert v["outcome"] == "ambiguous"
    v = _run(spec, [_traces(tmp_path, covered=[DAY0, DAY0 + 74000.0], name="short.npz")], tmp_path, **gate)
    assert v["reason_codes"] == ["flight_data_missing_time"] and "stated start" in v["reasons"][0]


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
    out = _locate(spec, [_traces(tmp_path)], tmp_path, report_top2=True, negative_information_distance_m=None)
    validate(out.record)
    v = out.record["verdict"]
    assert v["outcome"] == "ambiguous" and v["reason_codes"] == ["winner_only_refined", "silence_filter_off"]
    rules = {r["rule"]: r for r in out.record["pair_rules"]}
    # both: the default rule's answer is refined, top2's reported beside it
    assert rules["comparable"]["chosen"] and not rules["top2"]["chosen"] and rules["top2"]["events"] == [1, 2]
    assert out.record["refined"]["lat"] == pytest.approx(40.021)
    assert (tmp_path / "out" / "funnel_triples.npz").exists()
    assert any("rule comparable" in line and " s" in line for line in out.summary)       # its time is printed


def test_locate_never_emits_located(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    assert _run(spec, [_traces(tmp_path)], tmp_path, negative_information_distance_m=6000.0)["outcome"] != "located"


def test_a_ground_temperature_reaches_the_search_and_the_refinement(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0), _event(3000, 3.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    seen = {}

    def spy(name, fn):
        def wrapped(*args, **kw):
            seen[name] = args[5]               # the parameters, after sp, the events (or segments) and the grid
            return fn(*args, **kw)
        return wrapped
    monkeypatch.setattr(pipeline, "pair_grid_search", spy("search", pipeline.pair_grid_search))
    monkeypatch.setattr(pipeline, "refine", spy("refine", pipeline.refine))
    _run(spec, [_traces(tmp_path)], tmp_path, speed_of_sound_m_s=346.5, temperature_c=25.6)
    assert all(seen[k].air.temperature_c == 25.6 and seen[k].speed_of_sound() == 346.5 for k in ("search", "refine"))


def test_the_cpa_table_folder_is_made_on_a_fresh_cache(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    table = tmp_path / "fresh-cache" / "cpa" / "bench" / "x.npz"
    _run(spec, [_traces(tmp_path)], tmp_path, cpa_cache=str(table))
    assert table.parent.is_dir()


def test_the_defaults_are_comparable_with_the_silence_filter_on(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0), _event(3000, 3.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)
    calls = []
    search = pipeline.pair_grid_search
    monkeypatch.setattr(pipeline, "pair_grid_search", lambda *a, **k: calls.append(a[5]) or search(*a, **k))
    out = _locate(spec, [_traces(tmp_path)], tmp_path)
    assert [r["rule"] for r in out.record["pair_rules"]] == ["comparable"]
    assert len(calls) == 3 and all(p.scoring.normalisation == "pair_zscore"            # 3 events: 3 pairs
                                   and p.gates.negative_information_distance_m == 6000.0 for p in calls)
    assert out.record["verdict"]["reason_codes"] == ["winner_only_refined"]


def test_a_stated_start_time_drops_every_pair_whose_clock_disagrees(monkeypatch, spec, tmp_path):
    _detections(monkeypatch, [_event(1000, 5.0), _event(2000, 4.0)])
    _search_returning(monkeypatch, DAY0 + 72000.0)                 # clock: audio 0 at DAY0 + 71000
    ok = _run(spec, [_traces(tmp_path)], tmp_path, start_utc=DAY0 + 71030.0, start_tol_s=60.0)
    assert ok["outcome"] == "ambiguous"                             # 30 s off, inside 60 s
    far = _run(spec, [_traces(tmp_path)], tmp_path, start_utc=DAY0 + 71100.0, start_tol_s=60.0)
    assert far["reason_codes"] == ["no_surviving_candidate"] and "stated start time" in far["reasons"][0]
    edge = _run(spec, [_traces(tmp_path)], tmp_path, start_utc=DAY0 + 71065.0, start_tol_s=60.0)
    assert edge["outcome"] == "ambiguous"                           # 65 s: inside 60 s plus the search's 6 s


def test_the_clock_gate_counts_what_it_drops():
    import pandas as pd
    res = pd.DataFrame({"t_heard1": [1000.0, 1100.0, 1300.0], "shift": [0.0, 0.0, 0.0], "score": [3.0, 2.0, 1.0]})
    res.attrs["funnel"] = {"scored": 3}
    out = clock_gate(res, 100.0, start_utc=900.0, start_tol_s=60.0, tol_s=resolve("locate").gates.time_gate_s)
    assert list(out.t_heard1) == [1000.0] and out.attrs["funnel"]["clock_gate"]["after"] == 1
    assert out.attrs["funnel"]["scored"] == 3
