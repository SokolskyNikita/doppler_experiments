"""Unit files for resumable, splittable experiment jobs (local or on the AWS fleet through tools/aws/runs).

A job is a list of units. Each unit's result is one JSON file, written atomically when the unit finishes; a
unit whose file exists is skipped, so a stopped job resumes by running the same command again, and boxes can
split a job by naming disjoint units. A merge step reads whatever files exist. Pools size themselves from
DOPPLERTRACK_JOBS (dopplertrack.parallel.default_jobs)."""
import json
import os
from pathlib import Path

from dopplertrack.parallel import default_jobs


def jobs() -> int:
    return default_jobs()


def path(root: Path, *parts: str) -> Path:
    p = Path(root).joinpath(*parts)
    p = p.with_name(p.name + ".json")                                    # not with_suffix: a name may hold dots (0.03)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def done(p: Path) -> bool:
    return p.exists()


def write(p: Path, obj) -> None:
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    os.replace(tmp, p)


def read_all(root: Path, pattern: str = "*.json") -> list:
    return [json.loads(p.read_text()) for p in sorted(Path(root).glob(pattern))]


def select(all_units: list[str], chosen: list[str]) -> list[str]:
    """The named units (all when none are named); a name that isn't a unit is an error."""
    bad = sorted(set(chosen) - set(all_units))
    if bad:
        raise SystemExit(f"unknown units: {bad}; known: {all_units}")
    return [u for u in all_units if not chosen or u in chosen]


def shard(items: list) -> list:
    """This box's share of items: every DOPPLERTRACK_SHARDS-th from the DOPPLERTRACK_SHARD-th (1-based), as
    `runs launch --shards n` sets them; all of them when unset."""
    k, n = int(os.environ.get("DOPPLERTRACK_SHARD", 1)), int(os.environ.get("DOPPLERTRACK_SHARDS", 1))
    return list(items)[k - 1::n]
