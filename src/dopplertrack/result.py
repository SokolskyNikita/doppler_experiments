"""The result record (`result.json`): one per run of a recording, holding the decisions themselves.

A field the pipeline can't fill yet holds `unavailable(reason)` rather than a guess or a null, so a
reader can tell "not computed" from "computed and empty". `validate` checks a record against the
schema of its `schema_version`; `write_record` validates, writes atomically and returns the SHA-256 of
the bytes written, which a benchmark stores beside the record before it reads any reference answer.

Version 1 holds what the pipeline can fill today (PLAN.md section 5.5). Fields arrive with the
features that produce them, each with a version bump."""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from pathlib import Path

SCHEMA_VERSION = 1
KIND = "dopplertrack.result"


class RecordError(ValueError):
    """A record that doesn't match its schema; `problems` lists every mismatch found."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def unavailable(reason: str) -> dict:
    """The value of a field this run could not fill, with why."""
    if not reason:
        raise ValueError("an unavailable field needs a reason")
    return {"unavailable": reason}


def is_unavailable(value) -> bool:
    return isinstance(value, dict) and set(value) == {"unavailable"} and isinstance(value["unavailable"], str) \
        and bool(value["unavailable"])


CONVENTIONS_V1 = {
    "coordinates": "WGS-84 latitude and longitude, decimal degrees",
    "height": {
        "observer": "terrain height from the Terrarium DEM (orthometric, clamped at 0 m), or 0 m with --no-dem",
        "aircraft": "ADS-B geometric altitude (WGS-84 ellipsoidal) where present, else barometric pressure altitude; "
                    "no geoid or pressure correction",
    },
    "times": {
        "audio": "seconds from the recording's first sample",
        "utc": "Unix seconds",
        "cpa_kinds": {
            "emission": "when the aircraft is at closest approach",
            "heard": "when sound emitted at closest approach reaches the observer (emission + slant range / c)",
            "steepest_fall": "when the heard frequency falls fastest; equals the emission CPA for a straight, "
                             "constant-speed pass",
        },
    },
    "distances": "slant range at closest approach, metres; not altitude or ground range",
}


# The schema.
# A spec is a type (str, int, float, bool, dict, list), a dict of field -> spec (all required), or one of
# the wrappers below. `Maybe(spec)` also accepts unavailable(reason).

class Maybe:
    def __init__(self, spec):
        self.spec = spec


class ListOf:
    def __init__(self, spec):
        self.spec = spec


class OneOf:
    def __init__(self, *values):
        self.values = values


class Nullable:
    def __init__(self, spec):
        self.spec = spec


NUMBER = (int, float)
STAGE = {"name": str, "wall_s": NUMBER, "cpu_s": NUMBER}
FILE = {"role": str, "path": str, "bytes": int, "sha256": str}
FIT = {"t_heard_cpa_audio_s": NUMBER, "t_emission_cpa_audio_s": NUMBER, "t_steepest_fall_audio_s": NUMBER,
       "f0_hz": NUMBER, "speed_m_s": NUMBER, "slant_range_m": NUMBER, "window_s": ListOf(NUMBER),
       "f_pre_hz": NUMBER, "f_post_hz": NUMBER}
EVENT = {
    "id": str,
    "source": OneOf("saved_fit", "detect"),
    "fit": FIT,
    "harmonics": int,
    "diagnostics": {"score": NUMBER, "score_kind": str, "covariance": Maybe(list)},
    "assignment": Maybe({"flight": str, "basis": str}),
    "utc": Maybe({"t_heard_cpa": NUMBER, "t_emission_cpa": NUMBER, "basis": str}),
}
CANDIDATE = {
    "rank": int,
    "lat": NUMBER, "lon": NUMBER,
    "flights": ListOf(str),
    "clock": {"audio_minus_utc_s": NUMBER, "shift_s": NUMBER, "drift": Maybe(NUMBER)},
    "score": NUMBER,
    "event_scores": ListOf(NUMBER),
    "mode": Maybe(str),
}
SCHEMA_V1 = {
    "schema_version": int,
    "kind": OneOf(KIND),
    "case": Nullable({"id": str, "version": int}),
    "conventions": dict,
    "provenance": {
        "created": str,
        "code": {"package_version": str, "git_commit": Maybe(str), "git_dirty": Maybe(bool)},
        "parameters": dict,
        "inputs": ListOf(FILE),
        "caches": ListOf(FILE),
    },
    "events": ListOf(EVENT),
    "candidates": ListOf(CANDIDATE),
    "refined": Maybe({"lat": NUMBER, "lon": NUMBER, "score": NUMBER, "event_scores": ListOf(NUMBER),
                      "shift_s": NUMBER, "spacing_m": NUMBER, "half_width_m": NUMBER, "from_rank": int,
                      "extra_flights": ListOf(str)}),
    "funnel": {
        "cpa_records": Maybe(int),
        "after_speed_gate": Maybe(int),
        "after_distance_gate": Maybe(int),
        "after_time_gate": Maybe(int),
        "before_silence_filter": Maybe(int),
        "after_silence_filter": Maybe(int),
        "flight_pairs_before_silence_filter": Maybe(ListOf(ListOf(str))),
        "flight_pairs_after_silence_filter": Maybe(ListOf(ListOf(str))),
        "scored": Maybe(int),
        "unevaluated_budget": Maybe(int),
    },
    "verdict": Maybe({"outcome": OneOf("located", "abstain"), "reasons": ListOf(str)}),
    "region": Maybe(dict),
    "data_limitations": {
        "flight_data": dict,
        "altitude_sources": Maybe(dict),
        "candidate_gaps": Maybe(list),
        "possible_edits": Maybe(list),
        "ads_b": str,
    },
    "execution": {"errors": ListOf(str), "warnings": ListOf(str), "stages": ListOf(STAGE)},
}
SCHEMAS = {1: SCHEMA_V1}


def _check(value, spec, where: str, problems: list[str]):
    if isinstance(spec, Maybe):
        if is_unavailable(value):
            return
        _check(value, spec.spec, where, problems)
    elif isinstance(spec, Nullable):
        if value is not None:
            _check(value, spec.spec, where, problems)
    elif isinstance(spec, OneOf):
        if value not in spec.values:
            problems.append(f"{where}: {value!r} is not one of {list(spec.values)}")
    elif isinstance(spec, ListOf):
        if not isinstance(value, list):
            problems.append(f"{where}: expected a list, got {type(value).__name__}")
            return
        for i, v in enumerate(value):
            _check(v, spec.spec, f"{where}[{i}]", problems)
    elif isinstance(spec, dict):
        if not isinstance(value, dict):
            problems.append(f"{where}: expected an object, got {type(value).__name__}")
            return
        for k, sub in spec.items():
            if k not in value:
                problems.append(f"{where}.{k}: missing")
            else:
                _check(value[k], sub, f"{where}.{k}", problems)
    else:
        types = spec if isinstance(spec, tuple) else (spec,)
        # bool is an int in Python; a count or a score must not silently accept True
        if isinstance(value, bool) and bool not in types:
            problems.append(f"{where}: expected {'/'.join(t.__name__ for t in types)}, got bool")
        elif not isinstance(value, types):
            problems.append(f"{where}: expected {'/'.join(t.__name__ for t in types)}, got {type(value).__name__}")
        elif isinstance(value, float) and not math.isfinite(value):
            problems.append(f"{where}: {value} is not finite")


def validate(record) -> None:
    """Raise RecordError listing every way `record` departs from the schema of its version."""
    if not isinstance(record, dict):
        raise RecordError([f"record: expected an object, got {type(record).__name__}"])
    version = record.get("schema_version")
    if version not in SCHEMAS:
        raise RecordError([f"schema_version: {version!r} is not one of {sorted(SCHEMAS)}"])
    problems: list[str] = []
    _check(record, SCHEMAS[version], "record", problems)
    if problems:
        raise RecordError(problems)


def dumps(record) -> bytes:
    """The record's canonical bytes: the hash is taken over exactly these."""
    return (json.dumps(record, indent=1, sort_keys=True, allow_nan=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def _atomic_write(path: Path, data: bytes):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_record(path, record) -> str:
    """Validate `record`, write it atomically to `path` and return the SHA-256 of the written bytes."""
    validate(record)
    data = dumps(record)
    _atomic_write(Path(path), data)
    return sha256_bytes(data)


def read_record(path, expected_sha256: str | None = None) -> dict:
    """Load and validate a record. With expected_sha256, refuse a file whose bytes don't hash to it."""
    data = Path(path).read_bytes()
    if expected_sha256 is not None and sha256_bytes(data) != expected_sha256:
        raise RecordError([f"{path}: SHA-256 {sha256_bytes(data)} does not match the recorded {expected_sha256}"])
    record = json.loads(data)
    validate(record)
    return record


def file_entry(role: str, path) -> dict:
    p = Path(path)
    return {"role": role, "path": str(p), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
