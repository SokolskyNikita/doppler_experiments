import numpy as np
import pandas as pd

from dopplertrack.components.search import grid as search
import dopplertrack.components.search.cpa_storage as cpa_storage
import dopplertrack.components.search.cpa_table as cpa_table
import dopplertrack.components.search.pair_gate as pair_gate
import dopplertrack.components.search.types as search_types


def _cpa(rows):
    return pd.DataFrame(rows, columns=["gidx", "seg", "t_emit", "t_heard", "d", "v"]).astype(
        {"gidx": np.int32, "seg": np.int32, "d": np.float32, "v": np.float32})


def test_pair_candidates_matches_brute_force_across_bucket_edges():
    rng = np.random.default_rng(0)
    n = 4000
    cpa = _cpa({
        "gidx": rng.integers(0, 40, n), "seg": rng.integers(0, 60, n),
        "t_emit": 0.0, "t_heard": rng.uniform(0, 5000, n),
        "d": rng.uniform(500, 9000, n), "v": rng.uniform(40, 160, n),
    })
    dt, tol = 918.0, 6.0
    got = pair_gate.pair_candidates(cpa, dt, tol_s=tol, silence_d_m=None)
    # brute force: full per-point cross product, then the same filter
    bf = cpa.merge(cpa, on="gidx", suffixes=("1", "2"))
    bf = bf[(bf.seg1 != bf.seg2) & ((bf.t_heard2 - bf.t_heard1 - dt).abs() <= tol)]
    key = lambda df: set(zip(df.gidx.tolist(), df.seg1.tolist(), df.seg2.tolist()))
    assert key(got) == key(bf) and len(got) == len(bf) > 0


def test_pair_candidates_exact_tolerance_and_silence():
    # point 0: a pair exactly tol apart, which must survive; point 1: a third flight in between
    cpa = _cpa([
        (0, 1, 0, 1000.0, 3000, 100), (0, 2, 0, 1000.0 + 918 + 6.0, 3000, 100),
        (1, 1, 0, 1000.0, 3000, 100), (1, 2, 0, 1918.0, 3000, 100), (1, 3, 0, 1500.0, 2000, 100),
        (2, 1, 0, 1000.0, 3000, 100), (2, 2, 0, 1918.0 + 6.5, 3000, 100),
    ])
    funnel = {}
    m = pair_gate.pair_candidates(cpa, 918.0, tol_s=6.0, silence_d_m=None, funnel=funnel)
    assert set(m.gidx) == {0, 1}
    assert funnel == dict(cpa_rows=7, event1_gates=7, event2_gates=7, time_join=2, silence=2)
    m = pair_gate.pair_candidates(cpa, 918.0, tol_s=6.0, silence_d_m=6000.0, funnel=funnel)
    assert set(m.gidx) == {0}
    assert funnel == dict(cpa_rows=7, event1_gates=7, event2_gates=7, time_join=2, silence=1)
    pair_gate.pair_candidates(cpa, 918.0, tol_s=6.0, d1=(0, 2500), funnel=funnel)
    assert funnel["event1_gates"] == 1 and funnel["event2_gates"] == 7


def test_cpa_cache_roundtrip(tmp_path):
    cpa = _cpa([(0, 1, 5.0, 10.0, 3000, 100), (3, 2, 6.0, 12.0, 4000, 90)])
    fp = {"grid": (2, 40.0), "segs": (2, 100)}
    p = tmp_path / "cpa.npz"
    cpa_storage.save_cpa_table(p, cpa, fp)
    back = cpa_storage.load_cpa_table(p, fp)
    pd.testing.assert_frame_equal(back, cpa)
    assert cpa_storage.load_cpa_table(p, {"grid": (3, 40.0), "segs": (2, 100)}) is None
    old = tmp_path / "compressed.npz"            # tables saved before the cache stopped compressing
    np.savez_compressed(old, fingerprint=np.array(repr(fp)), **{k: cpa[k].to_numpy() for k in cpa_table.CPA_COLUMNS})
    pd.testing.assert_frame_equal(cpa_storage.load_cpa_table(old, fp), cpa)


def test_run_search_reports_stage_timings_and_funnel(monkeypatch):
    from dopplertrack.methods.grid_pair import pipeline
    from dopplertrack.components.types import EventFit
    cpa = _cpa([(0, 1, 0, 1000.0, 3000, 100), (0, 2, 0, 1918.0, 3000, 100),
                (1, 1, 0, 1000.0, 3000, 100), (1, 2, 0, 1918.0, 3000, 100), (1, 3, 0, 1500.0, 500, 100)])
    segs = [search_types.Segment(0, f"s{k}", np.zeros(2), np.zeros((2, 3)), np.zeros(2)) for k in range(4)]
    monkeypatch.setattr(pipeline, "build_segments", lambda *a, **k: segs)
    monkeypatch.setattr(pipeline, "cached_cpa_table", lambda *a, **k: cpa)
    monkeypatch.setattr(pipeline.EventWindow, "from_fit", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(pipeline, "custom_locked_score", lambda *a, **k: (2.0, 1.0, 1.0, 0.0))
    monkeypatch.setattr(pipeline, "modelled_curve", lambda *a: (np.zeros(2), np.zeros(2)))
    for name in ("report_coverage", "report_altitude_sources", "report_candidate_gaps"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: None)
    grid = search.Grid.points([40.0, 40.01], [-74.0, -74.0], np.zeros(2))
    ev1 = EventFit(1000.0, 997.0, 120, 100, 3000, 950, 1050, 5, 150, 90)
    ev2 = EventFit(1918.0, 1915.0, 120, 100, 3000, 1870, 1970, 5, 150, 90)
    res, _ = pipeline.pair_grid_search(None, ev1, ev2, [], grid, progress=False, workers=1)   # patches don't reach workers
    assert res.attrs["funnel"] == dict(cpa_rows=5, event1_gates=4, event2_gates=4, time_join=2, silence=1, scored=1)
    assert list(res.attrs["stages"]) == ["segments", "cpa_table", "pairing", "scoring", "gap_report"]
    assert all(v["wall_s"] >= 0 and v["cpu_s"] >= 0 for v in res.attrs["stages"].values())
