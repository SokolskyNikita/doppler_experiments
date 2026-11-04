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
    (rev.src / "stray.pyc").write_bytes(b"")
    with pytest.raises(revisions.RevisionError, match="changed after it was made") as exc:
        revisions.verify(rev)
    assert "M bench/cases.json" in str(exc.value) and "A stray.pyc" in str(exc.value)
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


@pytest.mark.parametrize("flags, writes", [(["-I", "-B"], False), (["-I"], True)])
def test_the_export_flags_keep_spawned_workers_from_writing_bytecode(tmp_path, flags, writes):
    # a16b700's detect starts spawn workers; whatever the parent is run with must reach them
    import subprocess
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "work.py").write_text("def square(x):\n    return x * x\n")
    # only the worker imports `work`, so any bytecode for it was written by the worker
    code = (f"import sys; sys.path.insert(0, {str(pkg)!r})\n"
            "import multiprocessing as mp\n"
            "def load(x):\n"
            "    import work\n"
            "    return work.square(x)\n"
            "if __name__ == '__main__':\n"
            "    with mp.get_context('spawn').Pool(1) as p:\n"
            "        assert p.map(load, [3]) == [9]\n"
            "    assert 'work' not in sys.modules\n")
    (tmp_path / "main.py").write_text(code)
    subprocess.run([sys.executable, *flags, str(tmp_path / "main.py")], check=True, cwd=tmp_path)
    assert (pkg / "__pycache__").exists() is writes


def _execute_with_triples(rows):
    """A fake run whose scored triples are `rows` (icao1, icao2, lat, lon), written as the runner writes them."""
    import pandas as pd

    def execute(case, case_dir, log=print, code=None):
        rec = _fake_execute(case, case_dir, code=code)
        draft = runner.Draft(cases.blind_case("oyster-bay"), {}, "saved-fit", lambda m: None)
        df = pd.DataFrame(rows, columns=["icao1", "icao2", "lat", "lon"]).assign(gidx=0, score=1.0)
        draft.write_triples(case_dir, {"silence": df, "scored": df})
        rec["funnel"]["triples_file"] = draft.funnel["triples_file"]
        rec["provenance"]["parameters"]["refine"] = {"half_m": 600.0}
        return rec
    return execute


def test_near_reference_is_decided_from_the_scored_triples_after_the_hash(tmp_path, one_case):
    truth = cases.case_labels("oyster-bay", 1)["reference"]
    rows = [("a1dfeb", "ace391", truth["lat"] + 0.004, truth["lon"]),      # about 445 m north
            ("a1dfeb", "ace391", truth["lat"] + 0.0015, truth["lon"]),     # about 167 m north
            ("a53001", "a19b2f", truth["lat"], truth["lon"])]              # another pair on the truth
    entry = runner.bench_case("synthetic", tmp_path / "out", execute=_execute_with_triples(rows), cases_path=one_case)
    assert entry["true_pair_near_reference"] is True and entry["true_pair_within_refine_reach"] is True
    assert 160 < entry["true_pair_min_distance_m"]["scored"] < 175
    far = runner.bench_case("synthetic", tmp_path / "far", execute=_execute_with_triples(rows[:1]), cases_path=one_case)
    assert far["true_pair_near_reference"] is False and far["true_pair_within_refine_reach"] is True


def test_a_changed_triples_file_discards_the_record(tmp_path, one_case):
    runner.bench_case("synthetic", tmp_path / "out", execute=_execute_with_triples([("a", "b", 0.0, 0.0)]),
                      cases_path=one_case)
    (tmp_path / "out" / runner.TRIPLES_FILE).write_bytes(b"changed")

    def labels():
        raise AssertionError("labels read for a record whose triples changed")
    meta = {"id": "synthetic", "version": 1, "group": "g", "set": "development", "expected_outcome": "located"}
    assert runner.compare_case(tmp_path / "out", meta, labels)["status"] == "discarded"


def test_search_overrides_parse_and_refuse_the_cpa_inputs():
    assert runner.parse_overrides(["tol_s=12", "time_convention=emission", "sf_tol_s=null", "d_tol=[0.5, 2]"]) == \
        {"tol_s": 12, "time_convention": "emission", "sf_tol_s": None, "d_tol": [0.5, 2]}
    with pytest.raises(ValueError):
        runner.parse_overrides(["tol_s"])
    case = cases.blind_case("oyster-bay")
    d = runner.Draft(case, {}, "saved-fit", lambda m: None, {"tol_s": 12, "time_convention": "emission"})
    assert d.search["tol_s"] == 12 and d.extra_kwargs == {"time_convention": "emission"}
    assert d.params["search_overrides"] == {"tol_s": 12, "time_convention": "emission"}
    with pytest.raises(ValueError, match="CPA table"):
        runner.Draft(case, {}, "saved-fit", lambda m: None, {"spacing_m": 100})


def test_a_recipe_can_write_into_a_folder(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setenv("DOPPLERTRACK_DATA", str(tmp_path))
    body = b"cut"
    write = "import pathlib, sys; pathlib.Path(sys.argv[1], 'box.npz').write_bytes(b'cut'); pathlib.Path(sys.argv[1], 'other.npz').write_bytes(b'x')"
    case = {"derived": [{"path": "derived/traces/box.npz", "sha256": hashlib.sha256(body).hexdigest(),
                         "recipe": [["python", "-c", write, "{out_dir}"]]}]}
    assert cases.build(case, log=lambda m: None) == []
    assert (tmp_path / "derived" / "traces" / "box.npz").read_bytes() == body
    assert sorted(p.name for p in (tmp_path / "derived" / "traces").iterdir()) == ["box.npz"]


def test_locate_reads_its_own_traces_with_their_own_envelopes_and_cpa_cache(tmp_path, monkeypatch):
    from dopplertrack.adsb import save_traces
    monkeypatch.setattr(runner, "resolve", lambda p: tmp_path / p)
    case = _case()
    save_traces([], tmp_path / case["flight_data"]["traces"].replace("/", "_"))
    case["flight_data"]["traces"] = case["flight_data"]["traces"].replace("/", "_")      # a legacy file
    legacy = runner.locate_flight_data(case, "/c/cpa/bench/x_200m_dem.npz")
    assert legacy == (runner.trace_paths(case), runner.day_boxes(case), "/c/cpa/bench/x_200m_dem.npz")
    v2 = "derived/ny_margin12_v2.npz"
    (tmp_path / "derived").mkdir()
    save_traces([], tmp_path / v2, metadata={"coverage_bbox": [40.0, 41.5, -74.6, -72.4]})
    case["derived"].append({"path": v2, "sha256": "0" * 64, "recipe": [["python", "x"]]})
    case["flight_data"]["locate_traces"] = v2
    cases.validate_case(case, cases.manifest_files())
    paths, envelope, cpa = runner.locate_flight_data(case, "/c/cpa/bench/x_200m_dem.npz")
    assert paths == [tmp_path / v2] and envelope is None and cpa == "/c/cpa/bench/x_200m_dem-locate.npz"
    assert runner.trace_paths(case) == legacy[0]           # the other profiles keep the legacy file
    case["derived"].pop()
    with pytest.raises(cases.CaseError, match="locate_traces"):
        cases.validate_case(case, cases.manifest_files())


def test_a_case_runs_only_under_its_profiles():
    assert set(cases.PROFILE_NAMES) == set(runner.PROFILES)
    case = _case()
    case["profiles"] = ["locate"]
    case["events"] = {"mode": "detect"}
    cases.validate_case(case, cases.manifest_files())
    case["profiles"] = ["saved-fit", "locate"]
    with pytest.raises(cases.CaseError, match="detect-mode"):
        cases.validate_case(case, cases.manifest_files())
    case["profiles"] = ["nope"]
    with pytest.raises(cases.CaseError, match="profiles"):
        cases.validate_case(case, cases.manifest_files())


CLEAN = {"package_version": "0.2.0", "git_commit": "c" * 40, "git_dirty": False}


@pytest.fixture
def fake_runs(monkeypatch):
    """run_bench with the case work stubbed: each case writes an entry; a case named in `stop` stops the run once."""
    ran, stop = [], set()

    def fake_case(cid, case_dir, execute, log, code, reveal=False):
        if cid in stop:
            stop.discard(cid)
            raise KeyboardInterrupt
        ran.append(cid)
        return {"case": cid, "status": "scored", "record_sha256": f"sha-{cid}"}
    monkeypatch.setattr(runner, "bench_case", fake_case)
    monkeypatch.setattr(runner, "latest_case", lambda cid: {})
    monkeypatch.setattr(runner, "_executor", lambda *a, **k: (dict(CLEAN), None))
    return ran, stop


def test_a_stopped_run_resumes_with_only_its_unfinished_cases(tmp_path, fake_runs):
    ran, stop = fake_runs
    run = tmp_path / "run"
    run.mkdir()
    stop.add("b")
    with pytest.raises(KeyboardInterrupt):
        runner.run_bench(["a", "b", "c"], run_dir=run, profile="locate")
    partial = json.loads((run / "results.json").read_text())       # written as each case finished
    assert [e["case"] for e in partial["cases"]] == ["a"] and not partial["complete"]
    assert partial["missing"] == ["b", "c"]
    with pytest.raises(ValueError, match="--resume"):
        runner.run_bench(["a", "b", "c"], run_dir=run, profile="locate")
    with pytest.raises(ValueError, match="profile"):
        runner.run_bench(["a", "b", "c"], run_dir=run, profile="saved-fit", resume=True)
    runner.run_bench(["a", "b", "c"], run_dir=run, profile="locate", resume=True)
    assert ran == ["a", "b", "c"]
    done = json.loads((run / "results.json").read_text())
    assert done["complete"] and [e["case"] for e in done["cases"]] == ["a", "b", "c"]
    assert len(json.loads((run / "run.json").read_text())["attempts"]) == 2


def test_a_dirty_tree_never_resumes(tmp_path, fake_runs, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(runner, "_executor", lambda *a, **k: ({**CLEAN, "git_dirty": True}, None))
    runner.run_bench(["a"], run_dir=run, profile="locate")
    with pytest.raises(ValueError, match="uncommitted"):
        runner.run_bench(["a", "b"], run_dir=run, profile="locate", resume=True)


def test_shards_split_the_cases_and_merge_into_one_run(tmp_path, fake_runs):
    assert runner.shard_of(["d", "a", "c", "b", "e"], "1/2") == ["a", "c", "e"]
    assert runner.shard_of(["d", "a", "c", "b", "e"], "2/2") == ["b", "d"]
    with pytest.raises(ValueError):
        runner.shard_of(["a"], "3/2")
    ids = ["a", "b", "c", "d", "e"]
    for k in (1, 2):
        (tmp_path / f"s{k}").mkdir()
        runner.run_bench(ids, run_dir=tmp_path / f"s{k}", profile="locate", shard=f"{k}/2")
    (tmp_path / "all").mkdir()
    doc = runner.merge_runs(tmp_path / "all", [tmp_path / "s1", tmp_path / "s2"])
    assert doc["complete"] and sorted(e["case"] for e in doc["cases"]) == ids
    assert (tmp_path / "all" / "c" / "entry.json").exists()
    other = tmp_path / "other"
    other.mkdir()
    (other / "run.json").write_text(json.dumps({**json.loads((tmp_path / "s1" / "run.json").read_text()),
                                                "code": {**CLEAN, "git_commit": "d" * 40}}))
    with pytest.raises(ValueError, match="code"):
        runner.merge_runs(tmp_path / "all2", [tmp_path / "s1", other])


def test_inputs_name_each_profiles_flight_data_and_cpa_table(monkeypatch):
    from bench import inputs
    v3 = next(c for c in cases.load_cases()["cases"] if c["id"] == "oyster-bay" and c["version"] == 3)
    monkeypatch.setattr(inputs, "latest_case", lambda cid: copy.deepcopy(v3))     # the version with locate_traces
    loc = inputs.run_inputs(["oyster-bay"], "locate")
    fit = inputs.run_inputs(["oyster-bay"], "saved-fit")
    for doc in (loc, fit):          # tools/data/shards.py's shape, which `runs launch` reads
        assert set(doc) == {"cases", "inputs", "cache_kinds", "cpa_tables", "detail"} and doc["cases"] == ["oyster-bay"]
        assert all(isinstance(p, str) and not p.startswith("raw/") for p in doc["inputs"])
    v2 = v3["flight_data"]["locate_traces"]
    assert v2 in loc["inputs"] and v2 not in fit["inputs"]
    assert any(p.endswith("-locate.npz") for p in loc["cpa_tables"])
    assert not any(p.endswith("-locate.npz") for p in fit["cpa_tables"])
    assert "docs/results/oyster_bay_ev1.json" in {e["path"] for e in fit["detail"]["repo"]}
    t1 = inputs.tier1_inputs()
    assert {"detections", "window_fits", "terrarium"} <= set(t1["cache_kinds"])
    assert t1["cpa_tables"] == []                           # the known point needs no table


def test_a_box_command_with_resume_starts_fresh_and_continues_alike(tmp_path, fake_runs):
    ran, _ = fake_runs
    run = tmp_path / "run"
    run.mkdir()
    runner.run_bench(["a", "b"], run_dir=run, profile="locate", resume=True)      # nothing finished: a fresh start
    runner.run_bench(["a", "b", "c"], run_dir=run, profile="locate", resume=True)  # a restarted box: only c runs
    assert ran == ["a", "b", "c"]


def test_the_box_environment_sets_the_run_folder_and_the_shard(tmp_path, monkeypatch):
    from bench import __main__ as cli
    seen = {}
    monkeypatch.setattr(runner, "run_bench", lambda ids, **kw: seen.update(kw) or kw["run_dir"])
    monkeypatch.setenv("RUN", str(tmp_path))
    monkeypatch.setenv("DOPPLERTRACK_SHARD", "2")
    monkeypatch.setenv("DOPPLERTRACK_SHARDS", "10")
    cli.main(["run", "--profile", "locate", "oyster-bay"])
    assert seen["run_dir"] == tmp_path and seen["shard"] == "2/10"


def test_prepare_builds_a_cases_cpa_table_without_its_labels_and_reuses_it(tmp_path, monkeypatch, capsys):
    import numpy as np
    from bench import prepare
    from dopplertrack.adsb import Trace, save_traces
    t = np.arange(1.0e9, 1.0e9 + 600, 2.0)
    lon = np.linspace(-74.2, -73.8, len(t))
    tr = Trace("abc123", None, "C172", None, t, np.full(len(t), 40.5), lon, np.full(len(t), 800.0),
               np.full(len(t), 60.0), np.zeros(len(t), bool))
    (tmp_path / "derived").mkdir()
    save_traces([tr], tmp_path / "derived" / "t.npz", metadata={"coverage_bbox": [40.0, 41.0, -74.5, -73.5]})
    case = {"id": "x", "version": 1, "labels": "must not be read",
            "flight_data": {"traces": "derived/t.npz"}, "weather": {"temperature_c": None},
            "search": {"bbox": [40.45, 40.55, -74.1, -73.9], "spacing_m": 2000, "max_range_m": 12000.0, "dem": False,
                       "cpa_cache": "cpa/bench/x_2000m.npz"}}
    monkeypatch.setattr(cases, "latest_case", lambda cid: copy.deepcopy(case))
    monkeypatch.setattr(runner, "resolve", lambda p: tmp_path / p)
    seen = []
    out = prepare.prepare_case("x", log=seen.append)
    assert (tmp_path / "cpa/bench/x_2000m.npz").exists() and out["cpa_records"] > 0 and out["segments"] == 1
    capsys.readouterr()
    again = prepare.prepare_case("x", log=seen.append)
    assert again["cpa_records"] == out["cpa_records"] and "loaded CPA table" in capsys.readouterr().out


def test_a_private_case_runs_with_its_caches_under_private(tmp_path, monkeypatch):
    from dopplertrack.cache import cache_root
    monkeypatch.setenv("DOPPLERTRACK_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("DOPPLERTRACK_CACHE", str(tmp_path / "shared"))
    seen = {}
    (tmp_path / "data" / "private" / "cases").mkdir(parents=True)
    (tmp_path / "data" / "private" / "cases" / "home.json").write_text("{}")

    def execute(case, case_dir, log=print, code=None):
        seen[case["id"]] = cache_root()
        raise RuntimeError("stop after recording the cache root")
    for cid, extra in (("public", {}), ("home", {"site": "a-site", "private": True})):
        monkeypatch.setattr(runner, "blind_case", lambda c, extra=extra, cid=cid: {"id": cid, **extra})
        with pytest.raises(RuntimeError):
            runner.bench_case(cid, tmp_path / cid, execute=execute)
    assert seen["public"] == tmp_path / "shared"
    assert seen["home"] == tmp_path / "data" / "private" / "cache"
    assert cache_root() == tmp_path / "shared"                  # restored afterwards
    assert cases.is_private({"site": "x"}) and not cases.is_private({"id": "y"})


SITE = {"lat": 40.8765, "lon": -73.5250, "ground_m": 30.0, "mic_height_m": 2.0}


@pytest.fixture
def private_home(tmp_path, monkeypatch):
    """A private case `home-1` at a fake site, its private files under a temporary data root."""
    data = tmp_path / "data"
    (data / "private" / "sites").mkdir(parents=True)
    (data / "private" / "cases").mkdir(parents=True)
    (data / "incoming").mkdir()
    (data / "incoming" / "site.json").write_text(json.dumps(SITE))
    (data / "private" / "sites" / "home.json").write_text(json.dumps({"site_json": "incoming/site.json"}))
    (data / "private" / "cases" / "home-1.json").write_text(json.dumps(
        {"spectrogram": "private/derived/home-1/rec.npz", "search": {"bbox": [40.4, 41.3, -74.4, -72.6]},
         "flight_data": {"traces": "private/traces/home-1/area.npz"}}))
    monkeypatch.setenv("DOPPLERTRACK_DATA", str(data))
    case = _case()
    for k in ("audio", "derived", "spectrogram", "reference_clock_utc", "traffic"):
        case.pop(k, None)
    case["flight_data"] = {k: v for k, v in case["flight_data"].items() if k not in ("traces", "extraction_box")}
    case["search"] = {k: v for k, v in case["search"].items() if k != "bbox"}
    case.update(id="home-1", site="home", private=True)
    case["labels"] = {"reference": {"site": "home"}, "true_pair": ["a1dfeb", "ace391"], "checked_by": "fixture"}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": [case]}))
    return path


def _private_execute(case, case_dir, log=print, code=None):
    """A record with absolute candidates near the site, and a triples sidecar, as a real run would write."""
    import numpy as np
    from dopplertrack.result import sha256_file
    assert case["search"]["bbox"] == [40.4, 41.3, -74.4, -72.6]          # resolved from the private file
    rec = example_record()
    rec["provenance"]["parameters"]["search"]["bbox"] = case["search"]["bbox"]
    np.savez_compressed(case_dir / "funnel_triples.npz", **{
        "scored__icao1": np.array(["a1dfeb"]), "scored__icao2": np.array(["ace391"]), "scored__gidx": np.array([0]),
        "scored__lat": np.array([40.8761]), "scored__lon": np.array([-73.5236]), "scored__score": np.array([27.1])})
    rec["funnel"]["triples_file"] = {"path": "funnel_triples.npz", "sha256": sha256_file(case_dir / "funnel_triples.npz"),
                                     "stages": ["scored"], "rows": {"scored": 1}}
    return rec


def test_a_private_record_is_written_in_the_sites_frame_and_scored_from_it(tmp_path, private_home):
    from dopplertrack.result import validate
    entry = runner.bench_case("home-1", tmp_path / "out", execute=_private_execute, cases_path=private_home)
    text = (tmp_path / "out" / "result.json").read_text()
    rec = json.loads(text)
    validate(rec)
    assert rec["frame"] == "site-relative" and rec["site"] == "home"
    assert '"lat"' not in text and '"lon"' not in text and "40.87" not in text and "-73.5" not in text
    assert rec["provenance"]["parameters"]["search"]["bbox"]["offset_box_m"][0] < 0       # the box's south edge
    import numpy as np
    with np.load(tmp_path / "out" / "funnel_triples.npz") as z:
        assert "scored__lat" not in z.files and "scored__east" in z.files
    # the candidate 40.8761, -73.5236 is about 125 m from the site; the comparison measures it from the offsets
    assert entry["status"] == "scored" and 100 < entry["top_error_m"] < 150 and entry["true_pair_rank"] == 1
    assert entry["true_pair_near_reference"] is True


def test_reveal_keeps_absolute_coordinates_and_says_so(tmp_path, private_home):
    runner.bench_case("home-1", tmp_path / "out", execute=_private_execute, cases_path=private_home, reveal=True)
    rec = json.loads((tmp_path / "out" / "result.json").read_text())
    assert "frame" not in rec and "lat" in rec["candidates"][0]
    assert "reveal" in rec["provenance"]["parameters"]["revealed"]


def test_a_position_near_the_site_under_any_name_is_refused(tmp_path, private_home):
    from bench import private

    def leaky(case, case_dir, log=print, code=None):
        rec = _private_execute(case, case_dir)
        rec["data_limitations"]["flight_data"] = {"centre": {"a": 40.88, "b": -73.52}}       # not a box, not a candidate
        return rec
    with pytest.raises(private.PrivateDataError, match="near the site"):
        runner.bench_case("home-1", tmp_path / "out", execute=leaky, cases_path=private_home)
    assert not (tmp_path / "out" / "result.json").exists()


def test_a_private_case_never_lists_its_inputs_or_shares_a_run(private_home, monkeypatch):
    from bench import inputs
    case = json.loads(private_home.read_text())["cases"][0]
    monkeypatch.setattr(inputs, "latest_case", lambda cid: copy.deepcopy(case))
    with pytest.raises(ValueError, match="private"):
        inputs.run_inputs(["home-1"], "locate")
    public = _case()
    monkeypatch.setattr(runner, "latest_case", lambda cid: case if cid == "home-1" else public)
    monkeypatch.setattr(runner, "_executor", lambda *a, **k: (dict(CLEAN), None))
    with pytest.raises(ValueError, match="share a run folder"):
        runner.run_bench(["home-1", "oyster-bay"], run_dir=None, profile="locate")


def test_a_private_case_entry_carries_nothing_that_places_it(private_home):
    case = json.loads(private_home.read_text())["cases"][0]
    cases.validate_case(case, cases.manifest_files())
    bad = copy.deepcopy(case)
    bad["labels"]["reference"] = {"site": "home", "lat": 40.8765, "lon": -73.525}
    with pytest.raises(cases.CaseError, match="no coordinate"):
        cases.validate_case(bad, cases.manifest_files())
    bad = copy.deepcopy(case)
    bad["search"]["bbox"] = [40.4, 41.3, -74.4, -72.6]
    with pytest.raises(cases.CaseError, match="search box"):
        cases.validate_case(bad, cases.manifest_files())
