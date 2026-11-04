"""tools/aws: the parts of `runs` and the box's supervisor that need no AWS account."""
import datetime
import json
import importlib.util
import io
import subprocess
import tarfile
from pathlib import Path

import pytest

AWS = Path(__file__).resolve().parent.parent / "tools" / "aws"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runs = _load("aws_runs", AWS / "runs.py")
supervisor = _load("aws_supervisor", AWS / "box" / "supervisor.py")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def branch(tmp_path):
    """A repo with two commits, an uncommitted edit, a new tracked file, an untracked file and an ignored one."""
    repo = tmp_path / "mac"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / ".gitignore").write_text(".venv/\n")
    (repo / "a.txt").write_text("one\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "one")
    (repo / "a.txt").write_text("two\n")
    _git(repo, "commit", "-qam", "two")
    (repo / "a.txt").write_text("three, uncommitted\n")
    (repo / "b.bin").write_bytes(bytes(range(256)))
    _git(repo, "add", "b.bin")
    (repo / "notes.md").write_text("untracked\n")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "big").write_text("ignored\n")
    return repo


def test_the_box_rebuilds_the_branch_with_its_commit_and_dirty_state(branch, tmp_path):
    code = runs.code_bundle(tmp_path / "code", repo=branch)
    assert code["git_commit"] == _git(branch, "rev-parse", "HEAD") and code["git_dirty"] and code["untracked"] == 1
    box = tmp_path / "box"
    supervisor.rebuild_tree(tmp_path / "code", code, box)
    assert (box / "a.txt").read_text() == "three, uncommitted\n"
    assert (box / "b.bin").read_bytes() == bytes(range(256)) and (box / "notes.md").exists()
    assert not (box / ".venv").exists()
    assert _git(box, "rev-parse", "HEAD") == code["git_commit"]
    assert _git(box, "log", "--format=%s") == "two\none"


def test_a_clean_branch_is_clean_on_the_box_and_a_mismatch_stops_the_job(branch, tmp_path):
    _git(branch, "add", "-A")
    _git(branch, "commit", "-qm", "three")
    code = runs.code_bundle(tmp_path / "code", repo=branch)
    assert not code["git_dirty"] and code["untracked"] == 0
    supervisor.rebuild_tree(tmp_path / "code", code, tmp_path / "box")
    assert _git(tmp_path / "box", "status", "--porcelain") == ""
    with pytest.raises(RuntimeError, match="dirty"):
        supervisor.rebuild_tree(tmp_path / "code", {**code, "git_dirty": True}, tmp_path / "box2")


def _entry(root, kind, h, payload=b"x"):
    d = root / kind / "dopplertrack" / "cache" / "_build" / h
    d.mkdir(parents=True)
    (d / "output.pkl").write_bytes(payload)
    (d / "metadata.json").write_text("{}")
    return d


def test_only_new_entries_of_the_named_kinds_go_back(tmp_path):
    cache = tmp_path / "cache"
    _entry(cache, "detections", "old")
    (cache / "detections" / "locks").mkdir()
    (cache / "detections" / "dopplertrack" / "cache" / "_build" / "func_code.py").write_text("def _build(): ...")
    before = supervisor.cache_files(cache)
    _entry(cache, "detections", "new")
    _entry(cache, "cpa", "table")
    (cache / "detections" / "locks" / "new.lock").write_text("")
    added = supervisor.new_cache_entries(before, supervisor.cache_files(cache), ["detections"])
    assert added == [f"detections/dopplertrack/cache/_build/new/{f}" for f in ("metadata.json", "output.pkl")]


def test_a_delta_adds_entries_here_and_never_overwrites_one(tmp_path):
    box = tmp_path / "box"
    _entry(box, "window_fits", "e1", b"from the box")
    _entry(box, "window_fits", "e2", b"from the box")
    files = sorted(supervisor.cache_files(box))
    supervisor.write_delta(box, files, tmp_path / "delta.tar")
    local = tmp_path / "local"
    _entry(local, "window_fits", "e1", b"already here")
    assert runs.merge_cache_delta((tmp_path / "delta.tar").read_bytes(), local) == 1
    base = local / "window_fits" / "dopplertrack" / "cache" / "_build"
    assert (base / "e1" / "output.pkl").read_bytes() == b"already here"
    assert (base / "e2" / "output.pkl").read_bytes() == b"from the box" and (base / "e2" / "metadata.json").exists()
    assert sorted(p.name for p in base.iterdir()) == ["e1", "e2"]


def test_job_ids_follow_new_run_and_pulls_never_reuse_a_folder(tmp_path, monkeypatch):
    ids = runs.candidate_ids("oyster-t2", datetime.date(2026, 11, 4))
    assert [next(ids) for _ in range(3)] == ["2026-11-04-oyster-t2", "2026-11-04-oyster-t2-2", "2026-11-04-oyster-t2-3"]
    monkeypatch.setattr(runs, "DATA_ROOT", tmp_path)
    assert runs.free_local("2026-11-04-x") == "2026-11-04-x"
    (tmp_path / "runs" / "2026-11-04-x").mkdir(parents=True)
    (tmp_path / "runs" / "2026-11-04-x-2").mkdir()
    assert runs.free_local("2026-11-04-x") == "2026-11-04-x-3"


def test_a_case_brings_its_audio_spectrogram_and_traces():
    got = runs.case_inputs(["oyster-bay"])
    # the case's latest version, as case_inputs reads it: its trace file changes with the case bumps
    case = [c for c in json.loads((runs.REPO / "bench" / "cases.json").read_text())["cases"] if c["id"] == "oyster-bay"][-1]
    assert {case["audio"]["path"], case["spectrogram"], case["flight_data"]["traces"]} <= set(got)
    assert "raw/audio/youtube/oyster_bay.webm" in got and "derived/oyster_bay/rec.npz" in got
    assert len(got) == len(set(got)) and not any(p.startswith("raw/adsb") for p in got)


def test_the_fleet_request_spans_every_family_and_subnet():
    out = {"Subnets": "s-a,s-b,s-c,s-d", "TemplateArm64": "lt-arm", "TemplateAmd64": "lt-x86"}
    req = runs.fleet_request(out, "2026-11-04-x", "16xlarge", on_demand=False)
    arm, x86 = req["LaunchTemplateConfigs"]
    assert arm["LaunchTemplateSpecification"]["LaunchTemplateId"] == "lt-arm" and len(arm["Overrides"]) == 12
    assert {o["InstanceType"] for o in arm["Overrides"]} == {"c8g.16xlarge", "c8gd.16xlarge", "c7g.16xlarge"}
    assert {o["InstanceType"] for o in x86["Overrides"]} == {"c7a.16xlarge"} and len(x86["Overrides"]) == 4
    assert req["TargetCapacitySpecification"] == {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "spot"}
    tags = {t["Key"]: t["Value"] for t in req["TagSpecifications"][0]["Tags"]}
    assert tags["dopplertrack-job"] == "2026-11-04-x" and tags["project"] == "dopplertrack"
    od = runs.fleet_request(out, "j", "8xlarge", on_demand=True)
    assert od["TargetCapacitySpecification"]["DefaultTargetCapacityType"] == "on-demand"


def test_the_interruption_notice_is_read_from_instance_metadata():
    class Md:
        def __init__(self, body):
            self.body = body

        def get(self, path):
            assert path == "spot/instance-action"
            return self.body

    assert supervisor.interruption(Md(None)) is None
    assert supervisor.interruption(Md('{"action": "terminate", "time": "2026-11-04T17:00:00Z"}'))["action"] == "terminate"
    tar = io.BytesIO()
    tarfile.open(fileobj=tar, mode="w").close()
    assert runs.merge_cache_delta(tar.getvalue(), Path("/nonexistent")) == 0


def test_everything_after_the_double_dash_is_the_command(monkeypatch):
    seen = {}
    monkeypatch.setattr(runs, "launch", lambda a: seen.update(vars(a)) or "job")
    runs.main(["launch", "t2", "--case", "oyster-bay", "--jobs", "8", "--", "python", "-m", "bench", "run", "--tier", "t2"])
    assert seen["case"] == ["oyster-bay"] and seen["jobs"] == 8
    assert seen["command"] == ["python", "-m", "bench", "run", "--tier", "t2"]


def _shard_env(monkeypatch, placeable):
    """launch_all with AWS stubbed: placeable(job, round) says whether the shard gets a box in that round."""
    rounds = {"n": 0}
    monkeypatch.setattr(runs, "launch", lambda a: a.topic)
    monkeypatch.setattr(runs, "session", lambda region=None: runs.argparse.Namespace(client=lambda name: None))
    monkeypatch.setattr(runs, "outputs", lambda region=None: {"Bucket": "b"})
    monkeypatch.setattr(runs.time, "sleep", lambda s: rounds.update(n=rounds["n"] + 1))
    tried = []

    def place(b, job, s3, bucket, wait_s, final):
        tried.append((rounds["n"], job, final))
        return not final and placeable(job, rounds["n"])
    monkeypatch.setattr(runs, "place", place)
    return tried


def test_shards_launch_one_job_per_box_and_resumed_runs_come_back_home(tmp_path, monkeypatch):
    tried = _shard_env(monkeypatch, lambda job, r: True)
    a = runs.argparse.Namespace(topic="whiten", shards=3, shard=None, wait_for_capacity=90)
    assert runs.launch_all(a) == ["whiten-s1of3", "whiten-s2of3", "whiten-s3of3"]
    assert [j for _, j, _ in tried] == ["whiten-s1of3", "whiten-s2of3", "whiten-s3of3"]
    run = tmp_path / "2026-11-04-whiten"
    run.mkdir()
    assert not runs.same_run(run)
    (run / "run.json").write_text('{"job": "2026-11-04-whiten"}')
    assert runs.same_run(run)
    (run / "run.json").write_text('{"job": "2026-11-04-other"}')
    assert not runs.same_run(run)


def test_both_input_listings_become_cases_paths_and_cache_kinds():
    shards = {"cases": ["oyster-bay"], "inputs": ["derived/swfl/rec.npz", "runs/2026-11-04-livermore-audit"],
              "cache_kinds": ["terrarium", "detections"], "cpa_tables": ["bench/oyster-bay_200m_dem.npz"]}
    assert runs.listed_inputs(shards) == (["oyster-bay"], ["derived/swfl/rec.npz", "runs/2026-11-04-livermore-audit"],
                                          ["terrarium", "detections"])
    bench = {"data": [{"path": "derived/oyster_bay/rec.npz"}, {"path": "derived/oyster_bay/rec.npz"}],
             "repo": [{"path": "bench/cases.json"}],
             "cache": [{"path": "terrarium/10/301/385.png"}, {"path": "cpa/bench/oyster-bay_200m_dem.npz"}]}
    assert runs.listed_inputs(bench) == ([], ["derived/oyster_bay/rec.npz"], ["terrarium"])


def test_a_shard_without_capacity_doesnt_stop_the_others(monkeypatch):
    # shard 2 finds room only in the second round; shards 1 and 3 aren't held back by it
    tried = _shard_env(monkeypatch, lambda job, r: job != "t-s2of3" or r >= 1)
    a = runs.argparse.Namespace(topic="t", shards=3, shard=None, wait_for_capacity=90)
    assert sorted(runs.launch_all(a)) == ["t-s1of3", "t-s2of3", "t-s3of3"]
    assert [(r, j) for r, j, _ in tried] == [(0, "t-s1of3"), (0, "t-s2of3"), (0, "t-s3of3"), (1, "t-s2of3")]
    # with no wait, a shard still without room is marked failed and named for --only-shard
    tried = _shard_env(monkeypatch, lambda job, r: job != "t-s2of3")
    with pytest.raises(SystemExit, match=r"1 of 3 shards not launched: \[2\]"):
        runs.launch_all(runs.argparse.Namespace(topic="t", shards=3, shard=None, wait_for_capacity=0))
    assert tried[-1] == (0, "t-s2of3", True)
    tried = _shard_env(monkeypatch, lambda job, r: True)
    runs.launch_all(runs.argparse.Namespace(topic="t", shards=3, shard=None, only_shard=[2], wait_for_capacity=0))
    assert [j for _, j, _ in tried] == ["t-s2of3"]
