"""PLAN Phase 2, item 7, stage A: each event's score against its own null, so event pairs share one scale."""
import numpy as np
import pandas as pd
import pytest

from dopplertrack import pipeline, search
from dopplertrack.score import EventWindow
from dopplertrack.tracks import EventFit


def _cpa(rows):
    return pd.DataFrame(rows, columns=["gidx", "seg", "t_emit", "t_heard", "d", "v"]).astype(
        {"gidx": np.int32, "seg": np.int32, "d": np.float32, "v": np.float32})


EV1 = EventFit(1008.8, 1000.0, 120, 100, 3000, 950, 1050, 5, 150, 90)
EV2 = EventFit(1926.8, 1918.0, 120, 100, 3000, 1870, 1970, 5, 150, 90)


def _patch(monkeypatch, cpa, segs, locked):
    monkeypatch.setattr(pipeline, "build_segments", lambda *a, **k: segs)
    monkeypatch.setattr(pipeline, "cached_cpa_table", lambda *a, **k: cpa)
    monkeypatch.setattr(pipeline.EventWindow, "from_fit", staticmethod(lambda sp, fit, h=1: EventWindow(fit, None, h)))
    monkeypatch.setattr(pipeline, "modelled_curve", lambda *a: (np.zeros(2), np.zeros(2)))
    monkeypatch.setattr(pipeline, "locked_score", locked)
    # the null: event 1's wrong flights score around 10 (spread 2), event 2's around 1 (spread 0.5)
    monkeypatch.setattr(pipeline, "single_score", lambda w, seg, o, t, c=None:
                        (10.0 + 2.0 * np.sin(seg.trace_idx)) if w.fit is EV1 else (1.0 + 0.5 * np.sin(seg.trace_idx)))
    for name in ("report_coverage", "report_altitude_sources", "report_candidate_gaps"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: None)


def test_comparable_score_ranks_by_each_events_own_null(monkeypatch):
    cpa = _cpa([(0, 1, 1000.0, 1008.8, 3000, 100), (0, 2, 1918.0, 1926.8, 3000, 100),
                (1, 3, 1000.0, 1008.8, 3000, 100), (1, 4, 1918.0, 1926.8, 3000, 100)])
    segs = [search.Segment(k, f"s{k}", np.zeros(2), np.zeros((2, 3)), np.zeros(2)) for k in range(5)]
    # point 0: a loud event 1 and nothing for event 2 (raw 13.5); point 1: both modestly above their nulls (raw 13)
    scores = {0: (12.5, 1.0), 1: (11.0, 2.0)}
    _patch(monkeypatch, cpa, segs, lambda w1, w2, s1, s2, obs, th, **k: (sum(scores[int(obs[0])]), *scores[int(obs[0])], 0.0))
    grid = search.Grid.points([40.0, 40.01], [-74.0, -74.0], np.zeros(2))
    grid.enu[:, 0] = [0.0, 1.0]
    run = dict(silence_d_m=None, progress=False, workers=1)
    plain, _ = pipeline.run_search(None, EV1, EV2, [], grid, **run)
    assert list(plain.gidx) == [0, 1] and "z1" not in plain                     # raw: the loud event wins
    res, _ = pipeline.run_search(None, EV1, EV2, [], grid, comparable=True, **run)
    n1, n2 = res.attrs["null"]["event1"], res.attrs["null"]["event2"]
    assert n1["n"] == pipeline.NULL_N and n1["seed"] != n2["seed"] and len(n1["sample_sha256"]) == 64
    assert list(res.gidx) == [1, 0]                                              # comparable: point 1 wins
    row = res.set_index("gidx").loc[1]
    assert row.z1 == pytest.approx((11.0 - n1["median"]) / n1["sigma"])
    assert row.z2 == pytest.approx((2.0 - n2["median"]) / n2["sigma"])
    assert row.score == pytest.approx(row.z1 + row.z2) and row.raw_score == pytest.approx(13.0)


def test_the_null_belongs_to_the_event_not_the_pair(monkeypatch):
    cpa = _cpa([(g, k, 1000.0 + k, 1008.0 + k, 3000, 100) for g in range(20) for k in range(30)])
    segs = [search.Segment(k, f"s{k}", np.zeros(2), np.zeros((2, 3)), np.zeros(2)) for k in range(30)]
    _patch(monkeypatch, cpa, segs, None)
    enu = np.zeros((20, 3))
    a = pipeline.event_null(EventWindow(EV1, None), cpa, segs, enu, 340.0, n=200, workers=1)
    b = pipeline.event_null(EventWindow(EV1, None), cpa, segs, enu, 340.0, n=200, workers=1)
    other = pipeline.event_null(EventWindow(EV2, None), cpa, segs, enu, 340.0, n=200, workers=1)
    assert a == b and a["sample_sha256"] != other["sample_sha256"]
    assert a["median"] == pytest.approx(10.0, abs=1.0) and 0.5 < a["sigma"] < 3.5
