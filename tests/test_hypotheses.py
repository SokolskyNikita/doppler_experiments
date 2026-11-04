"""PLAN Phase 2, item 7, stage B: each event's hypotheses instead of independent gates."""
import numpy as np
import pandas as pd
import pytest

from dopplertrack import audio, hypotheses as H, pipeline, search
from dopplertrack.doppler import ideal_curve
from dopplertrack.score import EventWindow
from dopplertrack.tracks import EventFit

C = 340.0


def _hyp(v, d, tau, v_range, k_range, tau_range=(0, 1e12), f0=120.0, sources=("ls",)):
    return H.Hypothesis(list(sources), f0, v, d, tau, tau + d / C, v_range, k_range, tau_range, (f0 * 0.9, f0 * 1.1))


def test_profile_range_of_a_known_bowl():
    """obj = ((v - 100)/5)^2 + ((tau - 50)/2)^2: within 1 of its minimum, v spans 95-105 and tau 48-52."""
    def obj(th):
        return ((th[1] - 100) / 5) ** 2 + ((th[3] - 50) / 2) ** 2
    th = np.array([120.0, 100.0, 2000.0, 50.0])
    lo, hi, weak = H.profile_range(obj, th, "v", 1.0, H.V_BOUNDS)
    assert lo == pytest.approx(95, abs=0.6) and hi == pytest.approx(105, abs=0.6) and not weak
    lo, hi, weak = H.profile_range(obj, th, "tau", 1.0, (0, 1000))
    assert lo == pytest.approx(48, abs=0.3) and hi == pytest.approx(52, abs=0.3) and not weak
    lo, hi, weak = H.profile_range(lambda t: 0.0, th, "v", 1.0, H.V_BOUNDS)        # flat: weak, to the bounds
    assert (lo, hi, weak) == (H.V_BOUNDS[0], H.V_BOUNDS[1], True)


def test_admission_follows_the_k_band_not_a_box():
    h = _hyp(100, 2000, 1000, (80, 120), (4.5, 5.5))                   # k = v^2/d = 5
    cpa = pd.DataFrame({"v": np.float32([100, 120, 80, 120, 100]), "d": np.float32([2000, 2880, 1280, 2000, 1000])})
    assert h.admits(cpa).tolist() == [True, True, True, False, False]    # 120 m/s at 2 km implies k = 7.2


def test_agreeing_optima_merge_with_the_wider_ranges():
    a = _hyp(100, 2000, 1000, (95, 105), (4.8, 5.2), (995, 1005), sources=("ls",))
    b = _hyp(101, 2020, 1002, (90, 110), (4.5, 5.5), (990, 1010), sources=("fit_event",))
    far = _hyp(60, 1000, 1100, (55, 65), (3.0, 4.2), (1090, 1110), sources=("fit_event",))
    out = H.merge([a, b, far])
    assert len(out) == 2 and out[0].sources == ["fit_event", "ls"]
    assert out[0].v_range == (90, 110) and out[0].tau_range == (990, 1010) and out[0].v == 100


def test_ls_hypothesis_holds_a_painted_pass():
    f0, v, d, tc = 120.0, 90.0, 1500.0, 200.0
    t, f = np.arange(0, 400, 0.5), np.arange(60, 201, 0.5)
    S = np.random.default_rng(0).uniform(0, 1, (len(f), len(t))).astype(np.float32)
    cur = ideal_curve(t, f0, v, d, tc, c=C)
    on = np.isfinite(cur)
    S[np.rint((cur[on] - f[0]) / 0.5).astype(int), np.flatnonzero(on)] += 10
    ev = EventFit(tc + d / C, tc, f0, v, d, 140, 260, 5, f0 * C / (C - v), f0 * C / (C + v))
    hs = H.ls_hypotheses(audio.Spectrogram(t, f, S), ev, 0.85 * ev.f_post, 1.15 * ev.f_pre, C)
    assert len(hs) >= 1 and hs[0].sources == ["ls"] and hs[0].identified
    h = hs[0]
    assert abs(h.v - v) / v < 0.02 and abs(h.k - v * v / d) / (v * v / d) < 0.03 and abs(h.t_cpa_emit - tc) < 1
    assert h.corr_v_d is not None and h.corr_v_d > 0.5


def test_closed_form_ratio_is_the_ideal_curve():
    t = np.arange(0, 400, 0.5)
    assert np.allclose(H.closed_form_ratio(t, 90, 1500, 200, C), ideal_curve(t, 1.0, 90, 1500, 200, c=C), rtol=1e-4)


def test_run_search_pairs_every_hypothesis_pair(monkeypatch):
    rows = [(0, 1, 1000.0, 1008.0, 3000, 100), (0, 2, 1918.0, 1926.0, 3000, 100),       # hypotheses 0 and 0
            (1, 3, 1000.0, 1008.0, 1000, 60), (1, 4, 1968.0, 1976.0, 1000, 60)]          # hypotheses 1 and 1
    cpa = pd.DataFrame(rows, columns=["gidx", "seg", "t_emit", "t_heard", "d", "v"]).astype(
        {"gidx": np.int32, "seg": np.int32, "d": np.float32, "v": np.float32})
    segs = [search.Segment(k, f"s{k}", np.zeros(2), np.zeros((2, 3)), np.zeros(2)) for k in range(5)]
    fast = [_hyp(100, 3000, 1000, (90, 110), (3.0, 3.7)), _hyp(60, 1000, 1000, (55, 65), (3.4, 3.9))]
    slow = [_hyp(100, 3000, 1918, (90, 110), (3.0, 3.7)), _hyp(60, 1000, 1968, (55, 65), (3.4, 3.9))]
    anchors, sweeps = [], []
    monkeypatch.setattr(pipeline, "build_segments", lambda *a, **k: segs)
    monkeypatch.setattr(pipeline, "cached_cpa_table", lambda *a, **k: cpa)
    monkeypatch.setattr(pipeline.EventWindow, "from_fit", staticmethod(lambda sp, fit, h=1: EventWindow(fit, None, h)))
    monkeypatch.setattr(pipeline, "event_null", lambda *a, **k: {"median": 0.0, "sigma": 1.0})
    monkeypatch.setattr(pipeline, "event_hypotheses", lambda sp, w, ev, c, s, h: fast if ev.t_cpa < 1500 else slow)
    monkeypatch.setattr(pipeline, "modelled_curve", lambda *a: (np.zeros(2), np.zeros(2)))

    def locked(*a, t0_map=None, f0_scales=None, f0_scales2=None, **k):
        anchors.append(t0_map); sweeps.append((len(f0_scales), len(f0_scales2)))
        return 2.0, 1.0, 1.0, 0.0
    monkeypatch.setattr(pipeline, "locked_score", locked)
    for name in ("report_coverage", "report_altitude_sources", "report_candidate_gaps"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: None)
    grid = search.Grid.points([40.0, 40.01], [-74.0, -74.0], np.zeros(2))
    ev1 = EventFit(1008.8, 1000.0, 120, 100, 3000, 950, 1050, 5, 150, 90)
    ev2 = EventFit(1926.8, 1918.0, 120, 100, 3000, 1870, 1970, 5, 150, 90)
    triples = {}
    res, _ = pipeline.run_search(None, ev1, ev2, [], grid, silence_d_m=None, progress=False, workers=1,
                                 hypotheses=True, triples=triples)
    f = res.attrs["funnel"]
    assert sorted(res.gidx) == [0, 1] and f["event1_hypotheses"] == 2 and f["event1_gates"] == 4   # rows, not pairs
    assert f["time_join"] == 2 and f["silence"] == 2 and set(triples) == {"time_join", "silence"}
    assert sorted(a + 1008.0 for a in anchors) == pytest.approx(sorted([fast[0].t_cpa, fast[1].t_cpa]))
    assert all(n1 == n2 and n1 > 21 for n1, n2 in sweeps)                     # 0.9-1.1 of f0, wider than +-5 %
    assert len(res.attrs["hypotheses"]["event2"]) == 2
    with pytest.raises(ValueError):
        pipeline.run_search(None, ev1, ev2, [], grid, progress=False, workers=1, hypotheses=True, sf_tol_s=4.0)
