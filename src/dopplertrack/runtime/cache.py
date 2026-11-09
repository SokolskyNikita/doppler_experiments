"""One way to cache a derived artefact (spectrograms, detections).

An entry's key is the SHA-256 of a canonical JSON description of everything that determines it: the
SHA-256 of every input file or array, every parameter, and the SHA-256 of the source of the code
that produces it, so editing that code invalidates its entries. Entries live under
$DOPPLERTRACK_CACHE/<kind>/, beside the CPA tables in cpa/ and the terrain tiles in terrarium/.

joblib.Memory stores them: one folder per entry, holding output.pkl and a metadata.json naming the
call's arguments, written atomically (to a temporary name, then renamed). A filelock per entry makes
a second process wait for the first instead of building the same artefact. An entry that won't load,
or whose stored description differs from the request, is a miss and is rebuilt.

The CPA table keeps its own cache (pipeline.cached_cpa_table): content fingerprints and a manual
CPA_CACHE_VERSION, rather than an automatic producer-source hash. See docs/architecture.md for its policy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from filelock import FileLock
from joblib import Memory

T = TypeVar("T")


def cache_root() -> Path:
    from dopplertrack.runtime.paths import cache_root as resolve_root
    return resolve_root()


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


def _module_source_path(name: str) -> Path:
    """A module's source file, found without importing it."""
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise ValueError(f"no source for module {name}")
    return Path(spec.origin)


def source_sha256(*modules: str) -> str:
    """Hash of the source files of the named modules (e.g. "dopplertrack.components.detection.grid_scan"), read from disk
    without importing them."""
    h = hashlib.sha256()
    for name in modules:
        h.update(name.encode() + b";")
        h.update(_module_source_path(name).read_bytes())
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

DETECTOR_MODULES = ("dopplertrack.components.detection.grid_scan", "dopplertrack.components.detection.event_fit",
                    "dopplertrack.components.detection.grid_search", "dopplertrack.components.detection.custom_curve_contrast",
                    "dopplertrack.components.detection.doppler_curve", "dopplertrack.components.whitening.local_median",
                    "dopplertrack.components.types", "dopplertrack.core.propagation",
                    "dopplertrack.components.spectrogram")
# What detect_events and fit_event actually run, by module: the functions and classes whose code decides a
# detection or a fit. tests/test_cache.py traces both producers and fails if they call anything not listed here,
# so the list can't fall behind the code. Process-pool plumbing (parallel.py) is left out: results don't depend on
# the number of workers.
DETECTOR_CODE = {
    "dopplertrack.components.detection.grid_scan": ("ScanRequest", "Candidate", "_scan_window", "non_maximum_suppression",
                                                    "detect_events"),
    "dopplertrack.components.detection.event_fit": ("fit_event",),
    "dopplertrack.components.detection.grid_search": ("grid_search",),
    "dopplertrack.components.detection.custom_curve_contrast": ("custom_sweep_weights", "custom_curve_contrast"),
    "dopplertrack.components.detection.doppler_curve": ("straight_pass_doppler_curve",),
    "dopplertrack.components.whitening.local_median": ("local_whiten",),
    "dopplertrack.components.types": ("EventFit",),
    "dopplertrack.core.propagation": ("speed_of_sound", "observed_frequency", "ideal_curve"),
    "dopplertrack.components.spectrogram": ("Spectrogram",),
}


def _without_text(node):
    """A definition's AST with what can't change a result taken out: docstrings, and the messages of raise and
    warnings.warn. Comments never reach the AST."""
    import ast
    import copy
    node = copy.deepcopy(node)
    for n in ast.walk(node):
        body = getattr(n, "body", None)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and body and \
                isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and \
                isinstance(body[0].value.value, str):
            n.body = body[1:] or [ast.Pass()]
        messages = []
        if isinstance(n, ast.Raise) and n.exc is not None:
            messages = [n.exc]
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "warn":
            messages = list(n.args[:1])
        for m in messages:
            for sub in ast.walk(m):
                if isinstance(sub, ast.Call):
                    sub.args = [ast.Constant("") if isinstance(a, (ast.Constant, ast.JoinedStr)) and
                                not isinstance(getattr(a, "value", ""), (int, float)) else a for a in sub.args]
                if isinstance(sub, ast.JoinedStr):
                    sub.values = []
    return node


def code_sha256(code: dict[str, tuple[str, ...]] = DETECTOR_CODE) -> str:
    """Hash of the named top-level functions and classes, read from source without importing them: each
    definition's AST less its docstrings and error messages, plus the module-level constants it reads. A docstring
    or message edit leaves it unchanged; any change to code that runs, or to a constant it uses, changes it."""
    import ast
    h = hashlib.sha256()
    for module, names in sorted(code.items()):
        tree = ast.parse(_module_source_path(module).read_text())
        defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        consts = {t.id: n for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        missing = [name for name in names if name not in defs]
        if missing:
            raise ValueError(f"{module} has no top-level {missing}")
        for name in names:
            node = defs[name]
            used = sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in consts})
            h.update(f"{module}:{name};".encode())
            h.update(ast.dump(_without_text(node)).encode())
            for c in used:
                h.update(ast.dump(consts[c]).encode())
    return h.hexdigest()
DETECT_IGNORED = ("workers", "progress")    # change how detections are computed, not what they are


def spectrogram_sha256(sp) -> str:
    """Hash of a Spectrogram's contents: grid, power, mask and start time."""
    start = None if sp.start_utc is None else np.float64(sp.start_utc)
    return array_sha256(sp.t, sp.f, sp.S, sp.valid, start)


def detection_parts(sp, produce: Callable, **params) -> dict:
    """What a detection result depends on: the spectrogram's contents, every detect parameter except those
    in DETECT_IGNORED, the producer, the code detect and fit run (DETECTOR_CODE, without docstrings and messages)
    and the numeric libraries."""
    import scipy
    return {"spectrogram": spectrogram_sha256(sp), "params": {k: v for k, v in params.items() if k not in DETECT_IGNORED},
            "producer": getattr(produce, "__qualname__", repr(produce)),
            "code": code_sha256(DETECTOR_CODE),
            "versions": {"numpy": np.__version__, "scipy": scipy.__version__}}


def detection_key(sp, produce: Callable, **params) -> str:
    """The cache key cached_detections files these detections under, to record beside a result."""
    return entry_key(detection_parts(sp, produce, **params))


def cached_detections(sp, produce: Callable[..., T], root: str | Path | None = None, **params) -> T:
    """produce(sp, **params), cached on detection_parts. Meant for
    tracks.detect_events: cached_detections(sp, detect_events, f_lo=60, f_hi=300, top=10)."""
    return cached("detections", detection_parts(sp, produce, **params), lambda: produce(sp, **params), root=root)
