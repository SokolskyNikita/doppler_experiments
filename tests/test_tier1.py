"""Tier 1's span matching and its record discipline (bench/tier1.py). No data needed."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import tier1  # noqa: E402

WINDOWS = [
    {"index": 0, "class": "clear", "start": 100.0, "end": 200.0, "lines": [[130, 65], [345, 255]]},
    {"index": 1, "class": "absent", "start": 200.0, "end": 300.0, "lines": []},
    {"index": 2, "class": "uncertain", "start": 300.0, "end": 400.0, "lines": [[150, 205]]},
    {"index": 3, "class": "clear", "start": 400.0, "end": 500.0, "lines": [[235, 165]]},
]


def det(t, f0, score=5.0):
    return {"t_cpa": t, "f0": f0, "score": score}


def test_matched_missed_and_extra_with_the_uncertain_window_counted_nowhere():
    m = tier1.match([det(150, 95), det(250, 120), det(350, 180)], WINDOWS)
    assert m["clear"] == {"windows": 2, "matched": 1, "missed": 1, "outside_model": 0}
    assert m["extra"] == {"total": 1, "by_window_class": {"absent": 1}}
    assert m["excluded_detections"] == 1


def test_a_harmonic_and_the_cpa_slack_count_as_a_match():
    # 2 x 100 Hz lies on the 235-165 Hz line; 503 s is within the 5 s slack of the window's end
    m = tier1.match([det(503, 100)], WINDOWS)
    assert m["clear"]["matched"] == 1 and m["extra"]["total"] == 0
    m = tier1.match([det(510, 100)], WINDOWS)
    assert m["clear"]["matched"] == 0 and m["extra"] == {"total": 1, "by_window_class": {"outside": 1}}


def test_a_detection_off_every_line_in_a_clear_window_is_extra():
    m = tier1.match([det(150, 420)], WINDOWS)          # 420, 210 and 840 Hz all miss both lines' bands
    assert m["clear"]["matched"] == 0 and m["extra"]["by_window_class"] == {"clear": 1}


def test_the_threshold_curve_drops_detections_below_each_score():
    rows = tier1.threshold_curve([det(150, 95, 3.0), det(250, 120, 6.0)], WINDOWS, hours=1 / 9)
    by = {r["min_score"]: r for r in rows}
    assert by[0.0]["matched"] == 1 and by[0.0]["extra"] == 1 and by[0.0]["extra_per_hour"] == pytest.approx(9.0)
    assert by[6.0]["matched"] == 0 and by[6.0]["extra"] == 1


def test_the_run_sees_no_class_id_or_association():
    labels = {"span": [0, 1200], "windows": [{"id": "ob-e03", "class": "clear", "start": 105, "end": 200,
                                              "lines": [[130, 65]], "notes": "N360NY"}],
              "associations": [{"window": "ob-e03", "flight": {"icao": "a40d8f"}}]}
    span, windows = tier1.span_inputs(labels)
    assert span == [0.0, 1200.0]
    assert windows == [{"window": 0, "start": 105.0, "end": 200.0, "lines": [[130.0, 65.0]]}]
    assert "a40d8f" not in json.dumps(windows) and "clear" not in json.dumps(windows)


def _record(tmp_path, detections):
    rec = {"schema_version": 1, "kind": tier1.SPAN_KIND, "span": {"id": "s", "labels": "l.json", "start": 0.0, "end": 600.0},
           "conventions": {}, "provenance": {"created": "now", "code": {}, "parameters": {}, "inputs": []},
           "detections": detections, "window_fits": [],
           "execution": {"errors": [], "warnings": [], "stages": []}}
    return tier1.write_span(tmp_path, rec)


def test_compare_reads_the_labels_only_after_the_hash(tmp_path):
    full = [{"t_cpa": 150.0, "t_cpa_emit": 130.0, "f0": 95.0, "v": 50.0, "d": 6000.0, "t_start": 100.0,
             "t_end": 200.0, "score": 5.0, "f_pre": 120.0, "f_post": 70.0}]
    _record(tmp_path, full)
    labels = {"windows": [{"class": w["class"], "start": w["start"], "end": w["end"], "lines": w["lines"]} for w in WINDOWS]}

    def read():
        assert (tmp_path / tier1.SPAN_HASH).exists()
        return labels
    e = tier1.compare_span(tmp_path, read)
    assert e["status"] == "scored" and e["detection"]["clear"]["matched"] == 1
    rec = json.loads((tmp_path / tier1.SPAN_FILE).read_text())
    rec["detections"][0]["f0"] = 200.0
    (tmp_path / tier1.SPAN_FILE).write_text(json.dumps(rec))

    def never():
        raise AssertionError("labels read for a changed span record")
    assert tier1.compare_span(tmp_path, never)["status"] == "discarded"


def test_line_f0_inverts_a_straight_pass():
    c, v, f0 = 343.0, 60.0, 120.0
    assert tier1.line_f0([f0 * c / (c - v), f0 * c / (c + v)]) == pytest.approx(f0)


def test_the_trajectory_reference_of_a_straight_pass():
    import numpy as np
    from dopplertrack.adsb import Trace
    from dopplertrack.geo import enu_to_lla
    c, v, t_cpa, y = 343.0, 60.0, 1_700_000_100.0, 2000.0
    t = np.arange(t_cpa - 300, t_cpa + 300, 1.0)
    lat, lon, _ = enu_to_lla(v * (t - t_cpa), np.full_like(t, y), np.zeros_like(t), 40.0, -84.0)
    n = len(t)
    tr = Trace("abc123", None, None, None, t, np.asarray(lat), np.asarray(lon), np.full(n, 1500.0), np.full(n, v),
               np.zeros(n, bool))
    ref = tier1.trajectory_reference([tr], "abc123", np.zeros(3), 40.0, -84.0, t_cpa - 1000.0, 1000.0, c)
    d = np.hypot(y, 1500.0)
    assert ref["slant_range_m"] == pytest.approx(d, abs=2.0)
    assert ref["t_heard_cpa_s"] == pytest.approx(1000.0 + d / c, abs=0.6)
    assert ref["ground_speed_m_s"] == pytest.approx(v, rel=0.01)
    # the heard curve falls fastest at the emission CPA, R/c before the heard CPA (PLAN 6.1)
    assert ref["t_steepest_fall_s"] == pytest.approx(1000.0, abs=1.0)


def test_a_window_with_only_rising_lines_is_outside_the_model_not_a_miss():
    windows = WINDOWS + [{"index": 4, "class": "clear", "start": 600.0, "end": 700.0, "lines": [[150, 205]]}]
    m = tier1.match([det(650, 180)], windows)          # on the rising line, inside the window
    assert m["clear"] == {"windows": 2, "matched": 0, "missed": 2, "outside_model": 1}
    assert m["extra"]["total"] == 0 and m["excluded_detections"] == 1
    assert tier1.rising([150, 205]) and not tier1.rising([235, 165])


@pytest.mark.parametrize("span", tier1.load_tier1()["spans"], ids=lambda s: s["id"])
def test_the_committed_labels_fit_what_tier1_reads(span):
    labels = json.loads((tier1.REPO / span["labels"]).read_text())
    (a, b), windows = tier1.span_inputs(labels)
    assert a < b and windows and all(set(w) == {"window", "start", "end", "lines"} for w in windows)
    ids = {w["id"]: w for w in labels["windows"]}
    for assoc in labels["associations"]:
        if isinstance(assoc["flight"], dict):
            assert 0 <= assoc["line"] < len(ids[assoc["window"]]["lines"])
