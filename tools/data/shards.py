"""Units of a long experiment that several machines can split, stop and resume, and that merge to the same numbers.

A driver names its units (one search, one case, one sweep cell) in a fixed order and gives the parameters that
decide their results. Each unit writes into <run>/units/<id>/ and is finished when unit.json is there; that file
is written last, by rename, so a stopped unit is never mistaken for a finished one. A finished unit records the
parameters, the commit and whether the tree was dirty.

Common options (`add_args`):
  RUN                the run folder (default $RUN, which the AWS box sets; else a new one from new_run.py)
  --shard K/N        run every N-th unit starting at the K-th, 1-based (default 1/1)
  --resume DIR ...   earlier run folders of the same experiment: their finished units are kept, not rerun
  --merge            run nothing: check every unit is finished in RUN or the --resume folders, then merge
  --inputs           print the case ids, data-root paths, cache kinds and CPA tables the job reads, as JSON, and exit

Merging refuses units whose parameters or commit differ from this invocation's, so a merged result is the one a
single run on one machine would have given. Worker counts come from $DOPPLERTRACK_JOBS (parallel.default_jobs)
and never change a result."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import new_run  # noqa: E402

UNIT_FILE = "unit.json"


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("run", nargs="?", type=Path, help="run folder (default $RUN, else a new one)")
    ap.add_argument("--shard", default="1/1", type=parse_shard, help="K/N: every N-th unit from the K-th")
    ap.add_argument("--resume", nargs="+", type=Path, default=[], metavar="DIR",
                    help="earlier run folders whose finished units are kept")
    ap.add_argument("--merge", action="store_true", help="only merge finished units")
    ap.add_argument("--inputs", action="store_true", help="print what the job reads, as JSON, and exit")


def parse_shard(text: str) -> tuple[int, int]:
    try:
        k, n = (int(x) for x in text.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--shard takes K/N, got {text!r}")
    if not 1 <= k <= n:
        raise argparse.ArgumentTypeError(f"--shard needs 1 <= K <= N, got {text!r}")
    return k, n


def code() -> dict:
    """This checkout's commit and dirty flag, as new_run.py records them."""
    def git(*args):
        return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {"git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}


def open_run(run: Path | None, topic: str, driver: dict) -> Path:
    """The run folder: `run`, else $RUN, else a new one. Its run.json is new_run.py's (written here if the folder
    has none) with `driver` merged under "driver", plus each invocation's shard under "invocations"."""
    if run is None and os.environ.get("RUN"):
        run = Path(os.environ["RUN"])
    if run is None:
        run = new_run.make(topic)
    run.mkdir(parents=True, exist_ok=True)
    path = run / "run.json"
    info = json.loads(path.read_text()) if path.exists() else new_run.info(topic)
    info.setdefault("invocations", []).append({"argv": sys.argv, **driver.pop("invocation", {})})
    info["driver"] = {**info.get("driver", {}), **driver}
    path.write_text(json.dumps(info, indent=1) + "\n")
    return run


class Units:
    """The units of one experiment, in order, with where each finished one lives."""

    def __init__(self, run: Path, ids: list[str], params: dict, shard: tuple[int, int] = (1, 1),
                 resume: list[Path] = ()):
        if len(set(ids)) != len(ids):
            raise ValueError("unit ids must be unique")
        self.run, self.ids, self.params, self.shard = run, list(ids), params, shard
        self.folders = [run, *resume]
        self.code = code()

    def dir(self, uid: str) -> Path:
        return self.run / "units" / uid

    def where(self, uid: str) -> Path | None:
        """The folder holding `uid` finished, checked against this experiment's parameters and commit."""
        for f in self.folders:
            d = f / "units" / uid
            if (d / UNIT_FILE).exists():
                rec = json.loads((d / UNIT_FILE).read_text())
                self.check(uid, rec)
                return d
        return None

    def check(self, uid: str, rec: dict) -> None:
        if rec["params"] != json.loads(json.dumps(self.params)):
            raise SystemExit(f"unit {uid} in {rec.get('folder')} ran with other parameters: {rec['params']}")
        if rec["git_commit"] != self.code["git_commit"]:
            raise SystemExit(f"unit {uid} ran at {rec['git_commit']}, this checkout is {self.code['git_commit']}")

    def todo(self) -> list[str]:
        """This shard's units not finished anywhere yet."""
        k, n = self.shard
        return [u for i, u in enumerate(self.ids) if i % n == k - 1 and self.where(u) is None]

    def finish(self, uid: str, summary: dict | None = None) -> None:
        d = self.dir(uid)
        d.mkdir(parents=True, exist_ok=True)
        rec = {"unit": uid, "params": self.params, **self.code, "folder": str(self.run), "summary": summary or {}}
        tmp = d / (UNIT_FILE + ".tmp")
        tmp.write_text(json.dumps(rec, indent=1, default=float) + "\n")
        tmp.replace(d / UNIT_FILE)

    def all(self) -> dict[str, Path]:
        """Every unit's folder, or exit naming the missing ones."""
        found = {u: self.where(u) for u in self.ids}
        missing = [u for u, d in found.items() if d is None]
        if missing:
            raise SystemExit(f"{len(missing)} of {len(self.ids)} units unfinished: {', '.join(missing)}")
        return {u: d for u, d in found.items() if d is not None}


def print_inputs(case_ids: list[str], inputs: list[str], cpa_tables: list[str],
                 cache_kinds: tuple[str, ...] = ("terrarium",)) -> None:
    """What `runs launch` needs: --case for each case id, --input for the other data-root paths and --cache for
    each cache kind; plus the CPA tables (under $DOPPLERTRACK_CACHE) the job reads, or builds when absent."""
    print(json.dumps({"cases": case_ids, "inputs": inputs, "cache_kinds": list(cache_kinds),
                      "cpa_tables": cpa_tables}, indent=1))
