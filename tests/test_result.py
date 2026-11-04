"""The result record v1: schema, validator and hashed round trip (PLAN.md 5.5)."""
import copy
import json

import pytest

from dopplertrack.result import (CONVENTIONS_V1, KIND, SCHEMA_VERSION, RecordError, dumps, is_unavailable,
                                 read_record, sha256_bytes, unavailable, validate, write_record)


def example_record():
    """A small record with every v1 field, some filled and some explicitly unavailable."""
    fit = {"t_heard_cpa_audio_s": 2155.96, "t_emission_cpa_audio_s": 2137.05, "t_steepest_fall_audio_s": 2137.05,
           "f0_hz": 112.6, "speed_m_s": 139.9, "slant_range_m": 6433.5, "window_s": [2090.0, 2200.0],
           "f_pre_hz": 191.2, "f_post_hz": 79.8}
    return {
        "schema_version": SCHEMA_VERSION, "kind": KIND, "case": {"id": "synthetic", "version": 1},
        "conventions": CONVENTIONS_V1,
        "provenance": {"created": "2026-11-04T00:00:00+00:00",
                       "code": {"package_version": "0.2.0", "git_commit": "abc", "git_dirty": False},
                       "parameters": {"search": {"bbox": [40.4, 41.3, -74.4, -72.6]}},
                       "inputs": [{"role": "spectrogram", "path": "rec.npz", "bytes": 3, "sha256": "0" * 64}],
                       "caches": []},
        "events": [{"id": "ev1", "source": "saved_fit", "fit": fit, "harmonics": 2,
                    "diagnostics": {"score": 16.5, "score_kind": "brightness", "covariance": unavailable("none yet")},
                    "assignment": {"flight": "a1dfeb", "basis": "top candidate"},
                    "utc": {"t_heard_cpa": 1788900805.7, "t_emission_cpa": 1788900786.8, "basis": "top candidate"}},
                   {"id": "ev2", "source": "saved_fit", "fit": fit, "harmonics": 1,
                    "diagnostics": {"score": 11.1, "score_kind": "brightness", "covariance": unavailable("none yet")},
                    "assignment": unavailable("unmatched"), "utc": unavailable("no clock")}],
        "candidates": [{"rank": 1, "lat": 40.8761, "lon": -73.5236, "flights": ["a1dfeb", "ace391"],
                        "clock": {"audio_minus_utc_s": -1788898650.7, "shift_s": -1.0, "drift": unavailable("no drift")},
                        "score": 27.1, "event_scores": [16.1, 11.0], "mode": unavailable("no modes")},
                       {"rank": 2, "lat": 41.0755, "lon": -72.7255, "flights": ["a53001", "a19b2f"],
                        "clock": {"audio_minus_utc_s": -1788865766.2, "shift_s": 0.0, "drift": unavailable("no drift")},
                        "score": 25.8, "event_scores": [15.4, 10.4], "mode": unavailable("no modes")}],
        "refined": unavailable("not refined"),
        "funnel": {"cpa_records": 10, "after_speed_gate": unavailable("one call"),
                   "after_distance_gate": unavailable("one call"), "after_time_gate": unavailable("one call"),
                   "before_silence_filter": 5, "after_silence_filter": 2,
                   "flight_pairs_before_silence_filter": [["a1dfeb", "ace391"], ["a53001", "a19b2f"]],
                   "flight_pairs_after_silence_filter": [["a1dfeb", "ace391"], ["a53001", "a19b2f"]],
                   "scored": 2, "unevaluated_budget": 0},
        "verdict": unavailable("no verdict before Phase 4"), "region": unavailable("no region before Phase 4"),
        "pair_rules": unavailable("chosen by profile"),
        "data_limitations": {"flight_data": {"traces_loaded": 3}, "altitude_sources": unavailable("not loaded"),
                             "candidate_gaps": [], "possible_edits": unavailable("no edit detection"),
                             "ads_b": "A complete archive download does not mean every aircraft broadcast ADS-B."},
        "execution": {"errors": [], "warnings": [], "stages": [{"name": "search", "wall_s": 1.0, "cpu_s": 0.9}]},
    }


def test_round_trip(tmp_path):
    rec = example_record()
    sha = write_record(tmp_path / "result.json", rec)
    assert sha == sha256_bytes((tmp_path / "result.json").read_bytes())
    assert read_record(tmp_path / "result.json", expected_sha256=sha) == json.loads(json.dumps(rec))
    assert dumps(read_record(tmp_path / "result.json")) == dumps(rec)


@pytest.mark.parametrize("path", [("provenance", "inputs"), ("verdict",), ("funnel", "after_silence_filter"),
                                  ("execution", "errors"), ("events", 0, "fit", "t_heard_cpa_audio_s")])
def test_validator_rejects_a_missing_required_field(path, tmp_path):
    rec = example_record()
    node = rec
    for k in path[:-1]:
        node = node[k]
    del node[path[-1]]
    with pytest.raises(RecordError) as exc:
        validate(rec)
    assert any(p.endswith("missing") and str(path[-1]) in p for p in exc.value.problems)
    with pytest.raises(RecordError):
        write_record(tmp_path / "result.json", rec)
    assert not (tmp_path / "result.json").exists()


def test_unavailable_needs_a_reason_and_is_only_allowed_where_declared():
    with pytest.raises(ValueError):
        unavailable("")
    assert is_unavailable(unavailable("why")) and not is_unavailable({"unavailable": ""})
    rec = example_record()
    rec["verdict"] = {"unavailable": ""}
    with pytest.raises(RecordError):
        validate(rec)
    rec = example_record()
    rec["candidates"][0]["score"] = unavailable("scores are always computed")
    with pytest.raises(RecordError):
        validate(rec)


def test_validator_rejects_wrong_types_and_versions():
    rec = example_record()
    rec["funnel"]["scored"] = True
    with pytest.raises(RecordError):
        validate(rec)
    rec = example_record()
    rec["schema_version"] = 99
    with pytest.raises(RecordError):
        validate(rec)
    rec = copy.deepcopy(example_record())
    rec["events"][0]["source"] = "guess"
    with pytest.raises(RecordError):
        validate(rec)


def test_a_changed_record_fails_its_hash(tmp_path):
    sha = write_record(tmp_path / "result.json", example_record())
    rec = json.loads((tmp_path / "result.json").read_text())
    rec["candidates"][0]["lat"] = 40.876466
    (tmp_path / "result.json").write_bytes(dumps(rec))
    with pytest.raises(RecordError):
        read_record(tmp_path / "result.json", expected_sha256=sha)


def test_a_version_1_record_still_validates_and_version_2_checks_the_verdict():
    rec = example_record()
    v1 = {k: v for k, v in rec.items() if k != "pair_rules"}
    v1["schema_version"] = 1
    validate(v1)
    rec["verdict"] = {"outcome": "ambiguous", "reason_codes": ["winner_only_refined"], "reasons": ["only the winner"]}
    validate(rec)
    rec["verdict"]["reason_codes"] = ["made_up"]
    with pytest.raises(RecordError):
        validate(rec)
