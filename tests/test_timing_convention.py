"""PLAN Phase 2, item 1: pairing on emission CPA times and the like-for-like steepest-fall check."""
import numpy as np
import pandas as pd
import pytest

from dopplertrack.core import propagation as doppler
from dopplertrack.methods.grid_pair import pipeline
from dopplertrack.components.search import grid as search
from dopplertrack.core.propagation import ideal_curve
from dopplertrack.components.scoring.doppler_inflection import INFLECTION_FLAT_RATIO, doppler_inflection
from dopplertrack.components.types import EventFit
import dopplertrack.components.search.pair_gate as pair_gate
import dopplertrack.components.search.types as search_types
import dopplertrack.components.scoring.inflection_gate as steepest_gate
from dopplertrack.methods.grid_pair.parameters import resolve as resolve_parameters

C = 340.0


def _cpa(rows):
    return pd.DataFrame(rows, columns=["gidx", "seg", "t_emit", "t_heard", "d", "v"]).astype(
        {"gidx": np.int32, "seg": np.int32, "d": np.float32, "v": np.float32})


@pytest.mark.parametrize("v,d", [(100, 1500), (103.5, 3600), (55, 1315), (140, 6264)])
def test_steepest_fall_of_an_ideal_curve_is_its_emission_cpa(v, d):
    t = 1000 + np.arange(-300, 300, 1.0)
    sf = doppler_inflection(t, ideal_curve(t, 120, v, d, 1000.0, c=C) / 120, 1000.0)
    assert sf is not None and abs(sf - 1000) < 0.5


def test_unplaceable_curves():
    t = np.arange(-300, 300, 1.0)
    flat = ideal_curve(t, 120, 40, 9000, 0.0, c=C) / 120          # defines SF_FLAT_RATIO
    assert doppler_inflection(t, flat, 0.0) is None
    assert doppler_inflection(t, flat, 0.0, flat_ratio=1.0) is not None
    sharp = ideal_curve(t, 120, 100, 1500, 0.0, c=C) / 120
    holed = np.where(np.abs(t) < 40, np.nan, sharp)               # no evidence across the CPA
    assert doppler_inflection(t, holed, 0.0) is None
    assert doppler_inflection(t, sharp, 200.0) is None                 # the fall lies outside the window
    assert INFLECTION_FLAT_RATIO == 1.03


def test_emission_gate_pairs_on_t_emit():
    cpa = _cpa([(0, 1, 1000.0, 1004.0, 3000, 100), (0, 2, 1918.0, 1930.0, 3000, 100),   # emission gap 918
                (1, 1, 1000.0, 1004.0, 3000, 100), (1, 2, 1930.0, 1922.0, 3000, 100)])  # heard gap 918
    funnel = {}
    assert set(pair_gate.pair_candidates(cpa, 918.0, silence_d_m=None, funnel=funnel).gidx) == {1}
    assert "time_join" in funnel
    funnel, triples = {}, {}
    assert set(pair_gate.pair_candidates(cpa, 918.0, silence_d_m=None, funnel=funnel, time_col="t_emit",
                                      triples=triples).gidx) == {0}
    assert funnel["emission_gate"] == 1 and "time_join" not in funnel
    assert set(triples) == {"emission_gate", "silence"}
    assert {k: v.tolist() for k, v in triples["emission_gate"].items()} == {"gidx": [0], "seg1": [1], "seg2": [2]}
    assert triples["emission_gate"]["gidx"].dtype == np.int32


def test_steepest_fall_check_in_run_search(monkeypatch):
    cpa = _cpa([(0, 1, 1000.0, 1000.0, 3000, 100), (0, 2, 1918.0, 1918.0, 3000, 100),    # gaps agree: kept
                (1, 1, 1000.0, 1000.0, 3000, 100), (1, 2, 1930.0, 1918.0, 3000, 100),    # 12 s off: dropped
                (2, 1, 1000.0, 1000.0, 3000, 100), (2, 3, 1918.0, 1918.0, 3000, 100)])   # unplaceable: kept
    segs = [search_types.Segment(k, f"s{k}", np.zeros(2), np.zeros((2, 3)), np.zeros(2)) for k in range(4)]
    anchors = []
    monkeypatch.setattr(pipeline, "build_segments", lambda *a, **k: segs)
    monkeypatch.setattr(pipeline, "cached_cpa_table", lambda *a, **k: cpa)
    monkeypatch.setattr(pipeline.EventWindow, "from_fit", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(pipeline, "custom_locked_score", lambda *a, **k: anchors.append(k["t0_map"]) or (2.0, 1.0, 1.0, 0.0))
    monkeypatch.setattr(pipeline, "modelled_curve", lambda seg, o, c: (np.full(2, float(seg.trace_idx)), np.zeros(2)))
    monkeypatch.setattr(steepest_gate, "doppler_inflection", lambda t, r, center, *a: None if t[0] == 3 else center)
    for name in ("report_coverage", "report_altitude_sources", "report_candidate_gaps"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: None)
    grid = search.Grid.points([40.0, 40.01, 40.02], [-74.0, -74.0, -74.0], np.zeros(3))
    ev1 = EventFit(1008.8, 1000.0, 120, 100, 3000, 950, 1050, 5, 150, 90)
    ev2 = EventFit(1926.8, 1918.0, 120, 100, 3000, 1870, 1970, 5, 150, 90)
    run = dict(progress=False, workers=1)

    def params(**kw):
        return resolve_parameters(overrides={"negative_information_distance_m": None, **kw})
    triples = {}
    res, _ = pipeline.pair_grid_search(None, ev1, ev2, [], grid, params(inflection_tol_s=4.0), triples=triples, **run)
    assert sorted(res.gidx) == [0, 2]
    assert sorted(triples["time_join"]["gidx"]) == [0, 1, 2] and sorted(triples["steepest_fall"]["gidx"]) == [0, 2]
    assert sorted(triples["steepest_fall"]["seg2"]) == [2, 3]
    f = res.attrs["funnel"]
    assert (f["time_join"], f["steepest_fall"], f["unplaceable"], f["scored"]) == (3, 2, 1, 2)
    assert anchors == [None, None]                                  # the heard anchor
    anchors.clear()
    res, _ = pipeline.pair_grid_search(None, ev1, ev2, [], grid, params(clock_anchor="doppler_inflection"), **run)
    fit1 = steepest_gate.fitted_inflection(ev1, doppler.speed_of_sound())
    assert len(res) == 3 and anchors[0] == pytest.approx(fit1 - 1000.0) and anchors[2] is None
    plain, _ = pipeline.pair_grid_search(None, ev1, ev2, [], grid, params(), **run)
    assert "steepest_fall" not in plain.attrs["funnel"]
    with pytest.raises(ValueError):
        pipeline.pair_grid_search(None, ev1, ev2, [], grid, params(time_convention="steepest"), **run)
