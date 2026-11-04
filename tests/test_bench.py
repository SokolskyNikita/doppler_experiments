"""The case manifest and the runner's hash-before-truth rule (PLAN.md 5.1, 5.5). No data needed."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import cases, runner  # noqa: E402
from dopplertrack.result import dumps  # noqa: E402
from test_result import example_record  # noqa: E402


SEED = {"oyster-bay", "eagle-cam-clip-18000s", "oyster-bay-moved-wsw150", "oyster-bay-hp150-aac32k"}


def test_committed_manifest_is_valid():
    doc = cases.load_cases()          # validates every case and refuses duplicate versions
    assert {c["set"] for c in doc["cases"]} <= set(cases.SETS)
    blocked = [c for c in doc["cases"] if not cases.is_runnable(c)]
    assert all(c["runnable"]["blocked"].strip() for c in blocked)
    runnable = {c["id"] for c in doc["cases"] if cases.is_runnable(c)}
    assert SEED <= runnable
    # only development cases run before Phase 4; calibration and evaluation cases wait, with a reason
    assert all(c["set"] == "development" for c in doc["cases"] if cases.is_runnable(c))
    assert {c["set"] for c in blocked} >= {"calibration", "evaluation"}


def _case():
    return copy.deepcopy(cases.load_cases()["cases"][0])


@pytest.mark.parametrize("field", ["source", "uncertainty_s"])
def test_a_case_without_a_start_time_source_or_uncertainty_is_refused(field):
    case = _case()
    del case["start_time"][field]
    with pytest.raises(cases.CaseError, match=f"start_time.{field}"):
        cases.validate_case(case, cases.manifest_files())


@pytest.mark.parametrize("value", [0, -5, float("nan"), "12 h"])
def test_start_time_uncertainty_must_be_positive_seconds(value):
    case = _case()
    case["start_time"]["uncertainty_s"] = value
    with pytest.raises(cases.CaseError, match="uncertainty_s"):
        cases.validate_case(case, cases.manifest_files())


def test_unknown_start_time_is_allowed_with_an_explicit_uncertainty():
    case = _case()
    case["start_time"] = {"source": "unknown", "utc": "2026-09-08T12:00:00Z", "uncertainty_s": 43200}
    cases.validate_case(case, cases.manifest_files())


def test_set_and_raw_hash_links_are_checked():
    case = _case()
    case["set"] = "training"
    case["source"]["raw"][0]["sha256"] = "0" * 64
    with pytest.raises(cases.CaseError) as exc:
        cases.validate_case(case, cases.manifest_files())
    assert any("set must be" in p for p in exc.value.problems)
    assert any("differs from its bench/manifest.json entry" in p for p in exc.value.problems)


def test_blind_case_has_no_labels():
    assert "labels" not in cases.blind_case("oyster-bay")
    assert cases.case_labels("oyster-bay", 1)["true_pair"] == ["a1dfeb", "ace391"]


@pytest.fixture
def one_case(tmp_path):
    case = _case()
    case["id"] = "synthetic"
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": [case]}))
    return path


def _fake_execute(case, case_dir, log=print, code=None):
    assert "labels" not in case
    rec = example_record()
    rec["provenance"]["code"] = code
    return rec


def test_the_record_and_its_hash_are_written_before_any_label_is_read(tmp_path, one_case):
    seen = []

    def labels(case_id, version, path):
        # the comparison may read the truth only once the record and its hash are on disk and agree
        sha = (tmp_path / "out" / runner.HASH_FILE).read_text().split()[0]
        assert cases.sha256_file(tmp_path / "out" / "result.json") == sha
        seen.append(case_id)
        return cases.case_labels(case_id, version, path)

    entry = runner.bench_case("synthetic", tmp_path / "out", execute=_fake_execute, labels=labels, cases_path=one_case)
    assert seen == ["synthetic"]
    assert entry["status"] == "scored" and entry["true_pair_rank"] == 1
    assert entry["true_pair_survived"] == {"speed_distance_time_gates": True, "silence_filter": True}
    assert entry["top_error_m"] < 200 and entry["margin_pct"] == pytest.approx(100 * (27.1 - 25.8) / 25.8)


def test_a_record_changed_after_its_hash_is_discarded_without_reading_the_truth(tmp_path, one_case):
    runner.bench_case("synthetic", tmp_path / "out", execute=_fake_execute, cases_path=one_case)
    rec = json.loads((tmp_path / "out" / "result.json").read_text())
    rec["candidates"][0]["lat"], rec["candidates"][0]["lon"] = 40.876466, -73.524951
    (tmp_path / "out" / "result.json").write_bytes(dumps(rec))

    def labels():
        raise AssertionError("labels read for a record that changed after its hash")

    meta = {"id": "synthetic", "version": 1, "group": "g", "set": "development", "expected_outcome": "located"}
    entry = runner.compare_case(tmp_path / "out", meta, labels)
    assert entry["status"] == "discarded" and "hash" in entry["reason"]


def test_a_record_without_its_hash_is_discarded(tmp_path, one_case):
    runner.bench_case("synthetic", tmp_path / "out", execute=_fake_execute, cases_path=one_case)
    (tmp_path / "out" / runner.HASH_FILE).unlink()
    meta = {"id": "synthetic", "version": 1, "group": "g", "set": "development", "expected_outcome": "located"}
    assert runner.compare_case(tmp_path / "out", meta, lambda: {})["status"] == "discarded"


def test_compare_runs_prints_both_runs(tmp_path, one_case):
    for name in ("a", "b"):
        entry = runner.bench_case("synthetic", tmp_path / name / "synthetic", execute=_fake_execute, cases_path=one_case)
        (tmp_path / name / "results.json").write_text(json.dumps({"git_commit": name * 9, "cases": [entry]}))
    out = runner.compare_runs(tmp_path / "a", tmp_path / "b")
    assert "synthetic" in out and "record identical" not in out.splitlines()[0]
    assert "true_pair_rank" in out and "+0.0" in out


def test_each_record_carries_the_code_revision_it_was_given(tmp_path, one_case):
    code = {"package_version": "0.2.0", "git_commit": "f" * 40, "git_dirty": True}
    runner.bench_case("synthetic", tmp_path / "out", execute=_fake_execute, cases_path=one_case, code=code)
    rec = json.loads((tmp_path / "out" / "result.json").read_text())
    assert rec["provenance"]["code"] == code


def test_a_blocked_case_needs_a_reason_and_is_never_run(tmp_path):
    case = _case()
    for k in ("derived", "spectrogram", "search", "refine", "events"):
        del case[k]
    case["runnable"] = {"blocked": "waits for the gap-aware spectrogram"}
    cases.validate_case(case, cases.manifest_files())
    case["runnable"] = {"blocked": ""}
    with pytest.raises(cases.CaseError, match="runnable"):
        cases.validate_case(case, cases.manifest_files())
    case["runnable"] = {"blocked": "waits for flight data"}
    case["id"] = "blocked"
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": [case]}))
    assert cases.case_ids(path) == [] and cases.case_ids(path, runnable_only=False) == ["blocked"]
    with pytest.raises(cases.CaseError, match="not runnable"):
        cases.blind_case("blocked", path)


def test_pick_detected_takes_the_two_best_scores_in_time_order():
    det = [{"t_cpa": 300.0, "score": 5.0}, {"t_cpa": 100.0, "score": 9.0}, {"t_cpa": 200.0, "score": 7.0}]
    assert [d["t_cpa"] for d in runner.pick_detected(det)] == [100.0, 200.0]
    with pytest.raises(ValueError):
        runner.pick_detected(det[:1])


def test_an_export_that_differs_from_its_commit_is_refused(tmp_path):
    import subprocess
    from bench import revisions
    commit = revisions._git("rev-parse", "HEAD")
    rev = revisions.Revision(commit, revisions._git("rev-parse", "HEAD^{tree}"), tmp_path / "rev")
    (rev.src).mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(cases.REPO), "archive", commit, "bench", "tests"],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(rev.src)], input=archive, check=True)
    # a partial tree stands in for a full export: its own tree hash is what verify compares
    rev.tree = revisions.tree_on_disk(rev.src)
    with pytest.raises(revisions.RevisionError, match="unfinished"):
        revisions.verify(rev)
    (rev.root / "export.json").write_text(json.dumps({"commit": commit}))
    revisions.verify(rev)
    (rev.src / "bench" / "cases.json").write_text("{}")
    with pytest.raises(revisions.RevisionError, match="changed after it was made"):
        revisions.verify(rev)
    (rev.root / "export.json").write_text(json.dumps({"commit": "0" * 40}))
    with pytest.raises(revisions.RevisionError, match="exported from"):
        revisions.verify(rev)


def test_a_revision_that_fails_verification_yields_an_error_not_a_result(tmp_path):
    from bench import revisions

    class Stale:
        short = "deadbee"
        def provenance(self):
            return {"package_version": "0", "git_commit": "d" * 40, "git_dirty": False}

    def stale_verify(rev):
        raise revisions.RevisionError("stale export")

    orig, revisions.verify = revisions.verify, stale_verify
    try:
        rec = runner.execute_case_at(cases.blind_case("oyster-bay"), tmp_path, Stale(), log=lambda m: None)
    finally:
        revisions.verify = orig
    assert rec["candidates"] == [] and any("stale export" in e for e in rec["execution"]["errors"])


def test_a_record_with_execution_errors_is_an_error_entry(tmp_path, one_case):
    def failing(case, case_dir, log=print, code=None):
        rec = _fake_execute(case, case_dir, code=code)
        rec["execution"]["errors"] = ["RuntimeError: search failed"]
        return rec
    entry = runner.bench_case("synthetic", tmp_path / "out", execute=failing, cases_path=one_case)
    assert entry["status"] == "error"
