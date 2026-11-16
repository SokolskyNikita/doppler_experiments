"""Research readiness R6: the study runner. The worker's request, the collective record, complete accounting, the
wall-time cap, study files, and a study with a baseline, two variants and wrong-day controls on the synthetic fixture
(tools/data/synthetic_study.py), with a failed case and missing units."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dopplertrack.evaluation import accounting, cases, runner, study  # noqa: E402
from dopplertrack.runtime import records  # noqa: E402
from test_result import example_record  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fixture = _load("synthetic_study", REPO / "tools" / "data" / "synthetic_study.py")
CLEAN = {"package_version": "0.2.0", "git_commit": "c" * 40, "git_dirty": False}


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """The data and cache roots in the test's folder, for the processes it starts too."""
    monkeypatch.setenv("DOPPLERTRACK_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("DOPPLERTRACK_CACHE", str(tmp_path / "cache"))
    return tmp_path


# ---- the worker's request (R6.3) -------------------------------------------------------------------------------

def test_a_worker_gets_no_label_and_no_evaluator_only_field_checked_on_the_serialized_request(tmp_path):
    case = fixture._case("synthetic-a", tmp_path, [40.0, 40.1, -74.0, -73.9], tmp_path / "rec.npz")
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": [case]}))
    seen = {}

    def execute(case, case_dir, log=print, code=None):
        seen.update(case)
        rec = example_record()
        rec["provenance"]["code"] = code
        return rec
    entry = runner.bench_case("synthetic-a", tmp_path / "out", execute=execute, cases_path=path, code=CLEAN)
    assert not set(seen) & set(cases.EVALUATOR_ONLY) and seen["search"]["bbox"] == [40.0, 40.1, -74.0, -73.9]
    on_disk = (tmp_path / "out" / runner.REQUEST_FILE).read_bytes()
    assert b"expected_outcome" not in on_disk and b"true_pair" not in on_disk and b'"labels"' not in on_disk
    assert cases.read_worker_request(on_disk) == seen
    assert entry["expected_outcome"] == "located" and entry["group"] == "synthetic"     # the evaluator still has them
    for leak in ({"case": {**seen, "expected_outcome": "located"}}, {"case": {**seen, "events": {"true_pair": ["a", "b"]}}},
                 {"case": seen, "labels": {}}):
        with pytest.raises(cases.CaseError, match="evaluator-only"):
            cases.read_worker_request(json.dumps(leak).encode())


# ---- the collective record (R6.6) ------------------------------------------------------------------------------

def _collective_record(z=7.0, control=None, errors=()):
    from dopplertrack.methods.collective import search
    from dopplertrack.methods.collective.parameters import CollectiveParameters
    p = CollectiveParameters()
    passes = [{"icao": "aaa001", "z": 4.0, "score": 1.0}, None]
    mode = {"lat": 40.0, "lon": -74.0, "Z": z, "clock_audio_minus_unix": -100.0, "n_matched": 1, "windows": passes}
    return {"schema_version": 1, "kind": records.COLLECTIVE_KIND, "case": {"id": "c", "version": 1},
            "provenance": {"created": "2026-11-15T00:00:00+00:00", "code": CLEAN, "parameters": {"search_overrides": {}},
                           "inputs": [{"role": "spectrogram", "path": "rec.npz", "bytes": 1, "sha256": "s1"}], "caches": []},
            "statistic": search.STATISTIC, "statistic_identity": search.statistic_identity(p),
            "domain": {"bbox": [40.0, 40.1, -74.0, -73.9], "terrain": False, "windows_sha256": "w"},
            "windows": [{"t_start": 0.0, "t_end": 200.0, "f0": 120.0, "t_cpa": 100.0, "score": 1.0}] * 2,
            "winner": None if z is None else mode, "reason": None if z is not None else "no fine point has a window above its null",
            "modes": [] if z is None else [mode], "control": control, "parameters": p.to_dict(),
            "execution": {"errors": list(errors), "warnings": [], "stages": []}}


def test_the_collective_record_is_versioned_and_validated():
    rec = _collective_record()
    records.validate(rec)                                   # the one validate serves both kinds
    for broken, where in ((dict(rec, statistic_identity={"name": "x"}), "statistic_identity.code_sha256"),
                          (dict(rec, modes=[{"lat": 40.0}]), "modes[0].lon"),
                          (dict(rec, control={"traffic_day": "2023-11-13"}), "control.recording_day"),
                          (dict(rec, schema_version=9), "schema_version")):
        with pytest.raises(records.RecordError, match=where.replace("[", r"\[").replace("]", r"\]")):
            records.validate(broken)
    records.validate(dict(rec, winner=None, modes=[], statistic_identity=records.unavailable("the search did not run")))
    records.validate(example_record())                      # the grid_pair record is as it was


def test_a_collective_entry_is_scored_and_a_control_draw_never_reads_the_labels(tmp_path):
    from dopplertrack.evaluation.collective import compare_collective
    labels = {"reference": {"lat": 40.0, "lon": -74.0}, "true_pair": ["aaa001", "aaa002"]}
    entry = compare_collective(_collective_record(), {"case": "c"}, lambda: labels)
    assert entry["status"] == "scored" and entry["Z"] == 7.0 and entry["top_error_m"] == 0.0
    assert entry["matched_flights"] == ["aaa001"] and entry["true_flights_matched"] is False

    def no_labels():
        raise AssertionError("a control draw read the labels")
    control = {"traffic_day": "2023-11-13", "recording_day": "2023-11-14", "shift_s": 86400.0}
    draw = compare_collective(_collective_record(control=control), {"case": "c"}, no_labels)
    assert draw["control_day"] == "2023-11-13" and draw["Z"] == 7.0 and "unavailable" in draw["top_error_m"]
    assert compare_collective(_collective_record(z=None), {"case": "c"}, lambda: labels)["candidates"] == 0
    assert compare_collective(_collective_record(errors=["boom"]), {"case": "c"}, lambda: labels)["status"] == "error"


# ---- complete accounting (R6.4) --------------------------------------------------------------------------------

def _entry(cid, **kw):
    return {"case": cid, "group": "g1", "status": "scored", "flight_pairs": 3, "record_sha256": f"sha-{cid}",
            "top_error_m": 100.0, "stages": [], **kw}


def _run(path, entries, scheduled, crashed=None, started=(), stopped=()):
    path.mkdir(parents=True)
    for c in started:
        (path / c).mkdir()
    for c in stopped:
        (path / c).mkdir()
        (path / c / runner.INCOMPLETE_FILE).write_text(json.dumps({"reason": "stopped at the per-unit wall-time cap"}))
    doc = {"cases": entries, "crashed": crashed or {}, "git_commit": "c" * 9}
    if scheduled is not None:
        doc["scheduled"] = [{"case": c, "group": "g2" if c.startswith("z") else "g1"} for c in scheduled]
    (path / "results.json").write_text(json.dumps(doc))
    return path


def test_every_scheduled_case_is_in_exactly_one_class(tmp_path):
    entries = [_entry("a"), _entry("b", verdict={"outcome": "ambiguous", "reason_codes": []}),
               _entry("c", flight_pairs=0), _entry("d", status="error", errors=["ValueError: no file"]),
               _entry("e", status="discarded", reason="hash"), _entry("z1", group="g2", verdict={"outcome": "located"})]
    scheduled = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "z1", "z2"]
    acct = accounting.account(_run(tmp_path / "r", entries, scheduled, crashed={"f": "exit 1"}, started=["g"], stopped=["h"]))
    assert acct["classes"] == {"a": "answered", "b": "abstained", "c": "no_candidate", "d": "failed", "e": "failed",
                               "f": "failed", "g": "incomplete", "h": "incomplete", "i": "missing", "z1": "answered",
                               "z2": "missing"}
    rows = accounting.counts(acct)
    assert rows["all"] == {"scheduled": 11, "answered": 2, "abstained": 1, "no_candidate": 1, "failed": 3,
                           "incomplete": 2, "missing": 2}
    assert rows["g2"] == {"scheduled": 2, "answered": 1, "abstained": 0, "no_candidate": 0, "failed": 0,
                          "incomplete": 0, "missing": 1}
    assert all(sum(r[k] for k in accounting.CLASSES) == r["scheduled"] for r in rows.values())
    text = "\n".join(accounting.table(acct))
    assert "wall-time cap" in text and "ValueError: no file" in text
    # a run from before the scheduled list: what it has is counted, the denominator is not guessed
    old = accounting.account(_run(tmp_path / "old", entries[:2], None))
    assert old["scheduled"] is None and accounting.counts(old)["all"]["scheduled"] is None
    assert "denominator is unknown" in "\n".join(accounting.table(old))
    # a study knows what an arm was to run even when nothing of it exists
    never = accounting.account(tmp_path / "never", [{"case": "a", "group": "g1"}])
    assert never["classes"] == {"a": "missing"}


def test_paired_differences_use_only_cases_complete_in_both_runs(tmp_path):
    a = _run(tmp_path / "a", [_entry("a"), _entry("b"), _entry("c")], ["a", "b", "c", "d"])
    b = _run(tmp_path / "b", [_entry("a", top_error_m=150.0), _entry("b", status="error", top_error_m=0.0)],
             ["a", "b", "c", "d"], started=["c"])
    acct_a, acct_b = accounting.account(a), accounting.account(b)
    assert accounting.paired_cases(acct_a, acct_b) == ["a"]
    out = runner.compare_runs(a, b)
    assert "b  [answered -> failed]" in out and "c  [answered -> incomplete]" in out and "d  [missing -> missing]" in out
    assert "over the 1 cases complete in both" in out and "mean +50.00" in out
    assert out.count("+50.0") == 2          # case a's row and the mean: b's error entry gives no difference


@pytest.fixture
def fake_runs(monkeypatch):
    def fake_case(cid, case_dir, execute, log, code, reveal=False):
        return _entry(cid)
    monkeypatch.setattr(runner, "bench_case", fake_case)
    monkeypatch.setattr(runner, "latest_case", lambda cid, **kw: {"group": "g1"})
    monkeypatch.setattr(runner, "_executor", lambda *a, **k: (dict(CLEAN), None))


def test_a_shard_that_never_came_back_is_missing_from_the_merged_run(tmp_path, fake_runs):
    ids = ["a", "b", "c", "d", "e"]
    runner.run_bench(ids, run_dir=tmp_path / "s1", profile="locate", shard="1/2")
    one = json.loads((tmp_path / "s1" / "results.json").read_text())
    assert [s["case"] for s in one["scheduled"]] == ["a", "c", "e"]            # the shard's own duty
    doc = runner.merge_runs(tmp_path / "all", [tmp_path / "s1"])
    assert [s["case"] for s in doc["scheduled"]] == ["a", "c", "e", "b", "d"] and not doc["complete"]
    acct = accounting.account(tmp_path / "all")
    assert accounting.counts(acct)["all"]["scheduled"] == 5 and accounting.counts(acct)["all"]["missing"] == 2


# ---- bounded units (R6.5) --------------------------------------------------------------------------------------

def test_a_unit_past_the_wall_time_cap_is_stopped_and_incomplete_never_a_result(tmp_path, roots, monkeypatch):
    case = fixture._case("synthetic-a", tmp_path, [40.0, 40.1, -74.0, -73.9], tmp_path / "rec.npz")
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 1, "cases": [case]}))
    monkeypatch.setattr(runner, "POLL_S", 0.02)
    with pytest.raises(ValueError, match="above zero"):
        runner.run_bench(["synthetic-a"], run_dir=tmp_path / "bad", profile="collective", unit_wall_s=0, cases_path=path)
    run = runner.run_bench(["synthetic-a"], run_dir=tmp_path / "run", profile="collective", unit_wall_s=0.01,
                           cases_path=path, log=lambda m: None)       # no process starts Python in 10 ms
    doc = json.loads((run / "results.json").read_text())
    assert doc["cases"] == [] and not doc["complete"] and "wall-time cap" in doc["incomplete"]["synthetic-a"]["reason"]
    assert not (run / "synthetic-a" / "entry.json").exists()
    assert accounting.account(run)["classes"] == {"synthetic-a": "incomplete"}


# ---- study files (R6.2) ----------------------------------------------------------------------------------------

def _study(tmp_path, **changes):
    doc = {"name": "s", "cases": ["oyster-bay"], "unit_wall_s": 60, "seed": 7,
           "baseline": {"recipe": "collective", "profile": "collective", "parameters": {"null.null_n": 60}},
           "variants": {"v": {"parameters": {"planning.max_modes": 2}}}, **changes}
    doc = {k: v for k, v in doc.items() if v is not ...}
    path = tmp_path / "study.json"
    path.write_text(json.dumps(doc))
    return path


def test_a_study_file_needs_its_cap_and_seed_and_refuses_what_it_cannot_run(tmp_path):
    for field in ("unit_wall_s", "seed"):
        with pytest.raises(study.StudyError, match=f"{field} is missing"):
            study.load_study(_study(tmp_path, **{field: ...}))
    for changes, why in (({"unit_wall_s": 0}, "unit_wall_s"), ({"seed": "x"}, "seed"), ({"extra": 1}, "unknown field"),
                         ({"baseline": {"recipe": "collective", "profile": "locate"}}, "baseline"),
                         ({"baseline": {"recipe": "grid_pair", "profile": "locate"}, "controls": {"days": ["2026-09-07"]}},
                          "only the collective recipe"),
                         ({"controls": {"days": ["7 Sept"]}}, "controls"),
                         ({"variants": {"baseline": {"parameters": {}}}}, "variants")):
        with pytest.raises(study.StudyError, match=why):
            study.load_study(_study(tmp_path, **changes))
    with pytest.raises(study.StudyError, match="changes nothing"):
        study.plan(study.load_study(_study(tmp_path, variants={"same": {"parameters": {"null.null_n": 60}}})))
    with pytest.raises(ValueError, match="no_such_parameter"):
        study.plan(study.load_study(_study(tmp_path, variants={"v": {"parameters": {"no_such_parameter": 1}}})))
    with pytest.raises(study.StudyError, match="set by the study's seed"):
        study.plan(study.load_study(_study(tmp_path, variants={"v": {"parameters": {"null.seed": 3}}})))


def test_the_plan_names_every_run_and_what_each_variant_changes(tmp_path):
    planned = study.plan(study.load_study(_study(
        tmp_path, cases=["oyster-bay", "eagle-cam-clip-18000s"],
        controls={"days": {"oyster-bay": ["2026-09-06", "2026-09-07"]}},
        variants={"v": {"parameters": {"planning.max_modes": 2, "assignment.method": "greedy_assignment",
                                        "detection.top": 6}}})))
    assert planned["arms"]["v"]["differences"] == ["detection.top: 10 -> 6", "planning.max_modes: 5 -> 2"]
    assert planned["arms"]["baseline"]["resolved"]["parameters"]["null.seed"] == 7      # the master seed, in every arm
    dirs = {r["dir"]: r for r in planned["runs"]}
    assert set(dirs) == {"arms/baseline", "arms/v", "controls/baseline/2026-09-06", "controls/baseline/2026-09-07",
                         "controls/v/2026-09-06", "controls/v/2026-09-07"}
    assert dirs["controls/v/2026-09-06"]["cases"] == ["oyster-bay"]            # only the case that lists the day
    assert dirs["controls/v/2026-09-06"]["overrides"]["control_day"] == "2026-09-06"
    text = "\n".join(study.announce(planned))
    assert "v: 2 cases, 2 control draws" in text and "planning.max_modes: 5 -> 2" in text


def test_a_grid_pair_study_resolves_its_profile_and_takes_the_seed(tmp_path):
    planned = study.plan(study.load_study(_study(
        tmp_path, baseline={"recipe": "grid_pair", "profile": "locate"},
        variants={"zscore": {"parameters": {"scoring.normalisation": "pair_zscore", "clock_gate": False}}})))
    assert planned["arms"]["zscore"]["differences"] == ['scoring.normalisation: "raw" -> "pair_zscore"',
                                                         'clock_gate: "(unset)" -> false']
    assert planned["arms"]["baseline"]["resolved"]["parameters"]["scoring.null_seed"] == 7
    assert [r["dir"] for r in planned["runs"]] == ["arms/baseline", "arms/zscore"]


def test_a_collective_launch_is_named_by_its_statistic_label_and_carries_the_studys_limit(tmp_path):
    from dopplertrack.evaluation.collective import resolved_parameters
    from dopplertrack.methods.collective.search import statistic_identity, statistic_label
    path = _study(tmp_path, aws={"max_boxes": 3, "max_vcpus": 192, "shards": 4})
    st = study.load_study(path)
    base, variant = study.launch_commands(path)
    label = statistic_label(statistic_identity(resolved_parameters(None, study.arm_overrides(st, "baseline"))[0]))
    assert f"tools/aws/runs launch {label.lower()} --study s --max-boxes 3 --max-vcpus 192 --shards 4" in base
    assert base.endswith("--arm baseline --out $RUN") and base.split()[2] != variant.split()[2]
    with pytest.raises(study.StudyError, match="aws.max_vcpus"):
        study.launch_commands(_study(tmp_path, aws={"max_boxes": 3}))


def test_the_master_seed_changes_the_draws_and_the_statistic_and_none_leaves_them(tmp_path):
    from dopplertrack.components.nulls import robust
    from dopplertrack.methods.collective.parameters import CollectiveParameters, resolve_collective
    from dopplertrack.methods.collective.search import statistic_identity
    assert CollectiveParameters().null.seed is None
    assert statistic_identity(resolve_collective({"null.seed": 7}))["id"] != statistic_identity(CollectiveParameters())["id"]
    key = (0.0, 200.0, 120.0, 100.0, "sweep")
    assert robust.null_seed(key + (7,)) != robust.null_seed(key)
    assert not np.array_equal(robust.draw_rows(1000, 50, robust.null_seed(key + (7,))),
                              robust.draw_rows(1000, 50, robust.null_seed(key)))


# ---- the finish check: a study on the synthetic fixture --------------------------------------------------------

def test_a_study_with_two_variants_and_wrong_day_controls_accounts_for_every_unit(roots):
    """A baseline, two variants and a control day on the synthetic scene, each unit a real run in its own process:
    one case is found, one fails (its recording does not exist), and one arm's control draws are never run."""
    path = fixture.write(roots / "fixture")
    doc = json.loads(path.read_text())
    doc.update(cases=["synthetic-a", "synthetic-broken"], parallel=4)
    doc["controls"]["days"] = ["2023-11-13"]
    path.write_text(json.dumps(doc))
    said = []
    out = study.run_study(path, out_dir=roots / "out", arms=["baseline", "fewer-modes"], log=said.append)
    study.run_study(path, out_dir=out, arms=["wider-tone"], controls=False, log=said.append)
    assert said.index("    planning.max_modes: 5 -> 2") < said.index("-- arms/baseline: 2 cases")    # announced first
    done = json.loads((out / "summary.json").read_text())["arms"]
    zero = dict.fromkeys(accounting.CLASSES, 0)
    for arm in ("baseline", "fewer-modes", "wider-tone"):
        assert done[arm]["counts"]["all"] == {**zero, "scheduled": 2, "answered": 1, "failed": 1}
        assert done[arm]["classes"] == {"synthetic-a": "answered", "synthetic-broken": "failed"}
    for arm in ("baseline", "fewer-modes"):
        assert done[arm]["control_counts"]["all"]["scheduled"] == 2 and done[arm]["control_counts"]["all"]["failed"] == 1
        assert done[arm]["control_classes"]["synthetic-a@2023-11-13"] in accounting.COMPLETE
        assert done[arm]["nulls"]["synthetic-a"]["draws"] == 1
        assert "own-day search is failed" in done[arm]["nulls"]["synthetic-broken"]["refused"]
    assert done["wider-tone"]["control_counts"]["all"] == {**zero, "scheduled": 2, "missing": 2}
    assert "did not finish: 2023-11-13 missing" in done["wider-tone"]["nulls"]["synthetic-a"]["refused"]
    assert done["fewer-modes"]["paired"]["cases"] == ["synthetic-a"]            # the failed case pairs with nothing
    assert done["fewer-modes"]["paired"]["differences"]["Z"]["mean"] == 0.0     # fewer modes kept: the same winner
    # the baseline's own-day run: the known receiver, both flights, a versioned record, no label in the request
    own = out / "arms" / "baseline" / "synthetic-a"
    entry = json.loads((own / "entry.json").read_text())
    assert entry["top_error_m"] < 1000.0 and entry["true_flights_matched"] is True
    record = records.read_record(own / "result.json")
    assert record["kind"] == records.COLLECTIVE_KIND and record["control"] is None
    assert all("windows" in m for m in record["modes"]) and record["parameters"]["null"]["seed"] == doc["seed"]
    assert b"true_pair" not in (own / "request.json").read_bytes()
    draw = records.read_record(out / "controls" / "baseline" / "2023-11-13" / "synthetic-a" / "result.json")
    assert draw["control"] == {"traffic_day": "2023-11-13", "recording_day": "2023-11-14", "shift_s": 86400.0}
    assert draw["statistic_identity"] == record["statistic_identity"]           # one statistic, own day and draw
    # the collected null names that statistic; another's draws are refused
    from dopplertrack.methods.collective import null, units
    table = null.load_draws(out / "nulls" / "baseline" / "synthetic-a.npz", record["statistic_identity"])
    assert list(table["day"]) == ["2023-11-13"] and float(table["own_max_Z"]) == entry["Z"]
    other = records.read_record(out / "arms" / "wider-tone" / "synthetic-a" / "result.json")["statistic_identity"]
    with pytest.raises(units.IncompleteUnit, match="not collective-Z"):
        null.load_draws(out / "nulls" / "baseline" / "synthetic-a.npz", other)
    with pytest.raises(study.StudyError, match="another study's plan"):
        path.write_text(json.dumps({**doc, "seed": 1}))
        study.run_study(path, out_dir=out, log=said.append)
