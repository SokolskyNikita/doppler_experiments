import importlib.util
import json
import sys
from pathlib import Path

import pytest

DATA_TOOLS = Path(__file__).resolve().parents[1] / "tools" / "data"
sys.path.insert(0, str(DATA_TOOLS))
SPEC = importlib.util.spec_from_file_location("shards", DATA_TOOLS / "shards.py")
shards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shards)

IDS = [f"u{i}" for i in range(7)]
PARAMS = {"cases": ["a", "b"], "n": 1000}


def test_shards_cover_every_unit_once(tmp_path):
    seen = []
    for k in (1, 2, 3):
        seen += shards.Units(tmp_path, IDS, PARAMS, (k, 3)).todo()
    assert sorted(seen) == sorted(IDS)


def test_stopped_shards_resume_and_merge_from_several_folders(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    ua = shards.Units(a, IDS, PARAMS, (1, 2))
    for u in ua.todo()[:2]:            # stopped after two units
        (ua.dir(u)).mkdir(parents=True)
        (ua.dir(u) / "out.txt").write_text(u)
        ua.finish(u, {"x": 1})
    shards.Units(b, IDS, PARAMS).dir("u5").mkdir(parents=True)     # begun, never finished: rerun
    ub = shards.Units(b, IDS, PARAMS, (2, 2))
    for u in ub.todo():
        ub.finish(u)
    uc = shards.Units(c, IDS, PARAMS, (1, 1), resume=[a, b])
    left = uc.todo()
    assert left == ["u4", "u6"]
    for u in left:
        uc.finish(u)
    folders = uc.all()
    assert set(folders) == set(IDS) and folders["u0"] == a / "units" / "u0" and folders["u4"] == c / "units" / "u4"
    assert json.loads((folders["u0"] / "unit.json").read_text())["summary"] == {"x": 1}


def test_merge_refuses_missing_units_and_other_parameters(tmp_path):
    u = shards.Units(tmp_path, IDS, PARAMS)
    u.finish("u0")
    with pytest.raises(SystemExit, match="6 of 7 units unfinished"):
        u.all()
    other = shards.Units(tmp_path, IDS, {**PARAMS, "n": 2000})
    with pytest.raises(SystemExit, match="other parameters"):
        other.todo()


def test_open_run_keeps_run_json_and_records_each_invocation(tmp_path, monkeypatch):
    monkeypatch.delenv("RUN", raising=False)
    run = tmp_path / "r"
    run.mkdir()
    (run / "run.json").write_text(json.dumps({"topic": "t", "git_commit": "abc", "host": {"zone": "z"}}))
    shards.open_run(run, "t", {"params": PARAMS, "invocation": {"shard": "1/2"}})
    shards.open_run(run, "t", {"params": PARAMS, "invocation": {"shard": "2/2"}})
    info = json.loads((run / "run.json").read_text())
    assert info["host"] == {"zone": "z"} and info["driver"]["params"] == PARAMS
    assert [i["shard"] for i in info["invocations"]] == ["1/2", "2/2"]
    monkeypatch.setenv("RUN", str(tmp_path / "box"))
    box = shards.open_run(None, "t", {})
    assert box == tmp_path / "box" and "git_commit" in json.loads((box / "run.json").read_text())


def test_shard_defaults_to_the_boxs_spec(monkeypatch):
    import argparse
    monkeypatch.setenv("DOPPLERTRACK_SHARD_SPEC", "2/3")       # what `runs launch --shards 3` sets on box 2
    ap = argparse.ArgumentParser()
    shards.add_args(ap)
    assert ap.parse_args([]).shard == (2, 3) and ap.parse_args(["--shard", "1/1"]).shard == (1, 1)


def test_shard_argument():
    assert shards.parse_shard("2/5") == (2, 5)
    for bad in ("0/3", "4/3", "x"):
        with pytest.raises(Exception):
            shards.parse_shard(bad)
