"""The case manifest, `bench/cases.json`: what each benchmark case is made of and how to rebuild it.

Paths under `raw/` and `derived/` are relative to $DOPPLERTRACK_DATA, CPA caches to $DOPPLERTRACK_CACHE and
saved fits to the repo. Every raw file a case uses is linked by path and SHA-256 to its `bench/manifest.json`
entry. A case's derived files carry runnable recipes, so `build` can remake them from `raw/` on another
machine; a recipe's placeholders are {data}, {cache}, {repo} and {out}, the temporary file it must write.

The runner reads a case through `blind_case`, which leaves out its labels; `case_labels` is only for the
comparison step, after the result record and its hash are on disk."""
from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from dopplertrack.result import sha256_file

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "bench" / "cases.json"
MANIFEST = REPO / "bench" / "manifest.json"
SETS = ("development", "calibration", "evaluation")
OUTCOMES = ("located", "not_located", "located_or_abstain")


def data_root() -> Path:
    return Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))


def cache_root() -> Path:
    return Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack"))


def resolve(path: str) -> Path:
    """A manifest path on this machine: raw/ and derived/ under the data root, cpa/ under the cache root,
    anything else relative to the repo."""
    if path.startswith(("raw/", "derived/")):
        return data_root() / path
    if path.startswith("cpa/"):
        return cache_root() / path
    return REPO / path


class CaseError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _need(case: dict, dotted: str, problems: list[str], where: str):
    node = case
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            problems.append(f"{where}: {dotted} is missing")
            return None
        node = node[part]
    return node


REQUIRED = ("id", "version", "group", "set", "expected_outcome", "description", "source.identifiers",
            "source.acquisition", "source.raw", "start_time.source", "start_time.utc", "start_time.uncertainty_s",
            "audio.path", "audio.clip_offset_s", "audio.clip_offset_samples", "audio.sample_rate_hz",
            "derived", "spectrogram", "flight_data.date", "flight_data.pod", "flight_data.archive_assets",
            "flight_data.traces", "flight_data.extraction_box", "search.bbox", "search.spacing_m",
            "search.harmonics", "search.tol_s", "search.v_tol", "search.d_tol", "search.silence_d_m",
            "search.max_range_m", "search.dem", "search.cpa_cache", "refine", "events.mode", "labels.reference",
            "labels.true_pair", "labels.checked_by", "built_with")


# A case that can't run yet (its audio needs the gap-aware spectrogram, its flight data isn't fetched, or it
# waits for a milestone) carries runnable = {"blocked": reason} and needs only what identifies it.
REQUIRED_BLOCKED = ("id", "version", "group", "set", "expected_outcome", "description", "source.identifiers",
                    "source.acquisition", "source.raw", "start_time.source", "start_time.utc",
                    "start_time.uncertainty_s", "flight_data.date", "labels.reference", "labels.checked_by",
                    "built_with")


def is_runnable(case: dict) -> bool:
    return case.get("runnable", True) is True


def validate_case(case: dict, manifest_files: dict[str, str]) -> None:
    """Raise CaseError listing every problem with one case entry. manifest_files maps path -> sha256."""
    where = case.get("id", "<case without id>") if isinstance(case, dict) else "<not an object>"
    if not isinstance(case, dict):
        raise CaseError([f"{where}: a case must be an object"])
    problems: list[str] = []
    runnable = is_runnable(case)
    if not runnable and not (isinstance(case.get("runnable"), dict) and str(case["runnable"].get("blocked", "")).strip()):
        problems.append(f"{where}: runnable must be true or {{\"blocked\": reason}}")
    for dotted in REQUIRED if runnable else REQUIRED_BLOCKED:
        _need(case, dotted, problems, where)
    if case.get("set") not in SETS:
        problems.append(f"{where}: set must be one of {SETS}, not {case.get('set')!r}")
    if case.get("expected_outcome") not in OUTCOMES:
        problems.append(f"{where}: expected_outcome must be one of {OUTCOMES}")
    if not isinstance(case.get("version"), int) or isinstance(case.get("version"), bool) or case.get("version", 0) < 1:
        problems.append(f"{where}: version must be a positive integer")
    st = case.get("start_time")
    if isinstance(st, dict):
        # no default: an honest "unknown" source is allowed, a missing one or a missing uncertainty is not
        if not isinstance(st.get("source"), str) or not st.get("source", "").strip():
            problems.append(f"{where}: start_time.source must be a non-empty string")
        if "uncertainty_s" in st and not (_num(st["uncertainty_s"]) and st["uncertainty_s"] > 0):
            problems.append(f"{where}: start_time.uncertainty_s must be a finite number of seconds above zero")
        if "utc" in st:
            try:
                datetime.fromisoformat(str(st["utc"]).replace("Z", "+00:00"))
            except ValueError:
                problems.append(f"{where}: start_time.utc {st['utc']!r} is not ISO-8601")
    raw = (case.get("source") or {}).get("raw", [])
    for f in raw if isinstance(raw, list) else []:
        path, sha = f.get("path"), f.get("sha256")
        if not str(path).startswith("raw/"):
            problems.append(f"{where}: source.raw path {path!r} is not under raw/")
        elif path not in manifest_files:
            problems.append(f"{where}: {path} has no bench/manifest.json entry")
        elif manifest_files[path] != sha:
            problems.append(f"{where}: {path} SHA-256 differs from its bench/manifest.json entry")
    for f in (case.get("flight_data") or {}).get("archive_assets", []):
        if f.get("path") not in manifest_files or manifest_files[f.get("path")] != f.get("sha256"):
            problems.append(f"{where}: flight-data asset {f.get('path')} is not linked to bench/manifest.json by hash")
    for d in case.get("derived", []) if isinstance(case.get("derived"), list) else []:
        for k in ("path", "sha256", "recipe"):
            if k not in d:
                problems.append(f"{where}: derived entry {d.get('path', '?')} has no {k}")
        if not str(d.get("path", "")).startswith("derived/"):
            problems.append(f"{where}: derived file {d.get('path')!r} is not under derived/")
        if not (isinstance(d.get("recipe"), list) and d["recipe"] and all(isinstance(s, list) and s for s in d["recipe"])):
            problems.append(f"{where}: derived {d.get('path')} recipe must be a list of argv lists")
    s = case.get("search") or {}
    if "bbox" in s and not (isinstance(s["bbox"], list) and len(s["bbox"]) == 4 and all(map(_num, s["bbox"]))):
        problems.append(f"{where}: search.bbox must be four numbers")
    if "cpa_cache" in s and not str(s["cpa_cache"]).startswith("cpa/"):
        problems.append(f"{where}: search.cpa_cache must be a path under the cache root's cpa/")
    ev = case.get("events") or {}
    if runnable and ev.get("mode") not in ("saved_fits", "detect"):
        problems.append(f"{where}: events.mode must be saved_fits or detect")
    if runnable and ev.get("mode") == "saved_fits" and not ev.get("files"):
        problems.append(f"{where}: saved_fits needs events.files")
    lab = case.get("labels") or {}
    ref = lab.get("reference")
    if ref is not None and not (isinstance(ref, dict) and _num(ref.get("lat")) and _num(ref.get("lon"))):
        problems.append(f"{where}: labels.reference needs numeric lat and lon")
    if problems:
        raise CaseError(problems)


def manifest_files() -> dict[str, str]:
    with open(MANIFEST) as f:
        return {e["path"]: e["sha256"] for e in json.load(f)["files"]}


def load_cases(path=CASES) -> dict:
    """The whole manifest, every case validated, with duplicate (id, version) pairs refused."""
    with open(path) as f:
        doc = json.load(f)
    if doc.get("schema") != 1 or not isinstance(doc.get("cases"), list):
        raise CaseError([f"{path}: expected schema 1 with a cases list"])
    files = manifest_files()
    problems, seen = [], set()
    for case in doc["cases"]:
        try:
            validate_case(case, files)
        except CaseError as exc:
            problems += exc.problems
        key = (case.get("id"), case.get("version"))
        if key in seen:
            problems.append(f"{key[0]}: version {key[1]} appears twice")
        seen.add(key)
    if problems:
        raise CaseError(problems)
    return doc


def _latest(doc: dict, case_id: str) -> dict:
    versions = [c for c in doc["cases"] if c["id"] == case_id]
    if not versions:
        raise KeyError(f"no case {case_id!r} in {CASES}")
    return max(versions, key=lambda c: c["version"])


def blind_case(case_id: str, path=CASES) -> dict:
    """The latest version of a case without its labels: everything the runner may see."""
    case = copy.deepcopy(_latest(load_cases(path), case_id))
    if not is_runnable(case):
        raise CaseError([f"{case_id}: not runnable yet: {case['runnable']['blocked']}"])
    del case["labels"]
    return case


def case_labels(case_id: str, version: int, path=CASES) -> dict:
    """The labels of one case version, for the comparison step only."""
    for c in load_cases(path)["cases"]:
        if c["id"] == case_id and c["version"] == version:
            return copy.deepcopy(c["labels"])
    raise KeyError(f"no case {case_id!r} version {version}")


def latest_case(case_id: str, path=CASES) -> dict:
    """The latest version of a case as written, runnable or not: for building and checking its files."""
    return copy.deepcopy(_latest(load_cases(path), case_id))


def case_ids(path=CASES, runnable_only: bool = True) -> list[str]:
    cases = load_cases(path)["cases"]
    return sorted({c["id"] for c in cases if is_runnable(c) or not runnable_only})


def _expand(argv: list[str], out: Path) -> list[str]:
    subs = {"data": str(data_root()), "cache": str(cache_root()), "repo": str(REPO), "out": str(out),
            "out_dir": str(out)}
    cmd = [a.format(**subs) for a in argv]
    if cmd[0] == "dopplertrack":
        cmd = [sys.executable, "-m", "dopplertrack.cli", *cmd[1:]]
    elif cmd[0] == "python":
        cmd = [sys.executable, *cmd[1:]]
    return cmd


def build(case: dict, log=print, check_only: bool = False) -> list[str]:
    """Make each missing derived file of a case from its recipe, in order, and check every derived file's
    hash. Each file is written under a temporary name in its folder and renamed into place when the
    recipe succeeds, so another session never reads it half-written. Returns the hash mismatches."""
    mismatches = []
    for d in case.get("derived", []):
        target = resolve(d["path"])
        if not target.exists():
            if check_only:
                mismatches.append(f"{d['path']}: missing")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # a recipe writes {out}, a temporary file, or into {out_dir}, a temporary folder in which it
            # must leave a file of the target's name (tools that write a folder of outputs)
            in_dir = any("{out_dir}" in a for argv in d["recipe"] for a in argv)
            tmp = target.with_name(f".{target.stem}.{os.getpid()}.{threading.get_ident()}.tmp" + ("" if in_dir else target.suffix))
            if in_dir:
                tmp.mkdir()
            try:
                for argv in d["recipe"]:
                    cmd = _expand(argv, tmp)
                    log(f"building {d['path']}: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True)
                os.replace(tmp / target.name if in_dir else tmp, target)
            finally:
                if in_dir:
                    for f in tmp.iterdir():
                        f.unlink()
                    tmp.rmdir()
                else:
                    tmp.unlink(missing_ok=True)
        sha = sha256_file(target)
        if sha != d["sha256"]:
            mismatches.append(f"{d['path']}: SHA-256 {sha} differs from the manifest's {d['sha256']}")
    return mismatches
