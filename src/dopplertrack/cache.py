"""One way to cache a derived artefact (spectrograms, detections).

An entry's key is the SHA-256 of a canonical JSON description of everything that determines it: the
SHA-256 of every input file or array, every parameter, and the SHA-256 of the source of the code
that produces it, so editing that code invalidates its entries. Entries live under
$DOPPLERTRACK_CACHE/<kind>/, beside the CPA tables in cpa/ and the terrain tiles in terrarium/.

joblib.Memory stores them: one folder per entry, holding output.pkl and a metadata.json naming the
call's arguments, written atomically (to a temporary name, then renamed). A filelock per entry makes
a second process wait for the first instead of building the same artefact. An entry that won't load,
or whose stored description differs from the request, is a miss and is rebuilt.

The CPA table keeps its own cache (pipeline.cached_cpa_table), which already follows these rules."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from filelock import FileLock
from joblib import Memory

T = TypeVar("T")


def cache_root() -> Path:
    return Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack"))


def file_sha256(path: str | Path, block: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(block):
            h.update(chunk)
    return h.hexdigest()


def array_sha256(*arrays) -> str:
    """Hash of the arrays' dtypes, shapes and bytes, in order (None hashes as itself)."""
    h = hashlib.sha256()
    for a in arrays:
        if a is None:
            h.update(b"none;")
            continue
        a = np.ascontiguousarray(a)
        h.update(f"{a.dtype.str}{a.shape};".encode())
        h.update(a.tobytes())
    return h.hexdigest()


def source_sha256(*modules: str) -> str:
    """Hash of the source files of the named modules (e.g. "dopplertrack.tracks"), read from disk
    without importing them."""
    h = hashlib.sha256()
    for name in modules:
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise ValueError(f"no source for module {name}")
        h.update(name.encode() + b";")
        h.update(Path(spec.origin).read_bytes())
    return h.hexdigest()


def _canonical(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _canonical(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_canonical(v) for v in x]
    if isinstance(x, np.ndarray):
        return {"array": array_sha256(x)}
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, Path):
        return str(x)
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    raise TypeError(f"cannot put {type(x).__name__} in a cache key")


def describe(parts: dict) -> str:
    """The canonical JSON an entry is keyed on: sorted keys, arrays by their hash."""
    return json.dumps(_canonical(parts), sort_keys=True, separators=(",", ":"), allow_nan=True)


def entry_key(parts: dict) -> str:
    return hashlib.sha256(describe(parts).encode()).hexdigest()


def _build(kind: str, key: str, description: str, produce: Callable[[], Any]):
    """What joblib stores: the description beside the value, so a hit can be checked."""
    return {"description": description, "value": produce()}


def cached(kind: str, parts: dict, produce: Callable[[], T], root: str | Path | None = None) -> T:
    """produce(), or the value an earlier call with identical `parts` stored under `kind`.

    `parts` must describe every input of produce(): file and array hashes, parameters, and the
    producer's source hash (source_sha256). Values must pickle."""
    folder = Path(root or cache_root()) / kind
    description = describe(parts)
    key = hashlib.sha256(description.encode()).hexdigest()
    (folder / "locks").mkdir(parents=True, exist_ok=True)
    memo = Memory(folder, verbose=0).cache(_build, ignore=["produce"])
    with FileLock(folder / "locks" / f"{key}.lock"):
        out = memo(kind, key, description, produce)
        if not isinstance(out, dict) or out.get("description") != description:
            out = memo.call(kind, key, description, produce)[0]      # rebuilds and stores
    return out["value"]


# ---- detections ------------------------------------------------------------------------------

DETECTOR_MODULES = ("dopplertrack.tracks", "dopplertrack.doppler", "dopplertrack.audio")
DETECT_IGNORED = ("workers", "progress")    # change how detections are computed, not what they are


def spectrogram_sha256(sp) -> str:
    """Hash of a Spectrogram's contents: grid, power, mask and start time."""
    start = None if sp.start_utc is None else np.float64(sp.start_utc)
    return array_sha256(sp.t, sp.f, sp.S, sp.valid, start)


def cached_detections(sp, produce: Callable[..., T], root: str | Path | None = None, **params) -> T:
    """produce(sp, **params), cached on the spectrogram's contents, every detect parameter except
    those in DETECT_IGNORED, and the source of the detector (DETECTOR_MODULES). Meant for
    tracks.detect_events: cached_detections(sp, detect_events, f_lo=60, f_hi=300, top=10)."""
    key_params = {k: v for k, v in params.items() if k not in DETECT_IGNORED}
    import scipy
    parts = {"spectrogram": spectrogram_sha256(sp), "params": key_params,
             "producer": getattr(produce, "__qualname__", repr(produce)),
             "source": source_sha256(*DETECTOR_MODULES),
             "versions": {"numpy": np.__version__, "scipy": scipy.__version__}}
    return cached("detections", parts, lambda: produce(sp, **params), root=root)
