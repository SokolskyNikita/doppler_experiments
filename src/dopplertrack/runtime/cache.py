"""One way to cache a derived artefact (spectrograms, detections, window fits), and the one rule that
identifies a producer's code in a cache key (the CPA table's fingerprint uses it too).

An entry's key is the SHA-256 of a canonical JSON description of everything that determines it: the
SHA-256 of every input file or array, every parameter, the producer's qualified name, the hash of the
code that produces it (code_sha256) and the versions that can change the result (versions). Entries live
under $DOPPLERTRACK_CACHE/<kind>/, beside the CPA tables in cpa/ and the terrain tiles in terrarium/.

A producer's code is derived, not listed: its own module and every dopplertrack module that module
imports, directly or through another, read from source without importing anything (code_modules).
dopplertrack.runtime is left out: it is plumbing (pools, paths, this cache) and no result may depend on
it. Each file counts as its module name and its whole AST less docstrings and the messages of raise and
warnings.warn, so a comment, docstring or message edit keeps every entry and any other edit to a file
rebuilds the caches whose producer imports it.

joblib.Memory stores the entries: one folder per entry, holding output.pkl and a metadata.json naming the
call's arguments, written atomically (to a temporary name, then renamed). A filelock per entry makes
a second process wait for the first instead of building the same artefact. An entry that won't load,
or whose stored description differs from the request, is a miss and is rebuilt.

The CPA table keeps its own storage (runtime.cpa_cache.cached_cpa_table): one file at an explicit path,
holding the fingerprint of its inputs and of its builder's code. See docs/architecture.md."""
from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import importlib.util
import json
import sys
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

    `parts` must describe every input of produce(): file and array hashes, parameters, the producer's
    name (producer_name), its code (code_sha256) and the versions that matter (versions). Values must pickle."""
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


# ---- a producer's code -----------------------------------------------------------------------

PACKAGE = "dopplertrack"
PLUMBING = "runtime"      # <package>.runtime: pools, paths and this cache. No result may depend on it.

_PARSED: dict[tuple[str, str], tuple[str, tuple[tuple[str, str | None], ...]]] = {}


def _module_file(name: str) -> Path | None:
    """The source file of the named module (a package's __init__.py), found on disk without importing
    anything, or None when there is none: `name` is an attribute, a namespace package or not Python source."""
    top, *rest = name.split(".")
    try:
        spec = importlib.util.find_spec(top)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if not rest:
        return Path(spec.origin) if spec.has_location and spec.origin and spec.origin.endswith(".py") else None
    for base in spec.submodule_search_locations or ():
        stem = Path(base).joinpath(*rest)
        for candidate in (stem.parent / f"{stem.name}.py", stem / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _without_text(node):
    """An AST with what can't change a result taken out: docstrings, and the messages of raise and
    warnings.warn. Comments never reach the AST."""
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


def _imports(tree: ast.Module, name: str, is_package: bool) -> tuple[tuple[str, str | None], ...]:
    """Every module `tree` imports, at module level or inside a definition, as (name, fallback): `from a import b`
    is the module a.b if there is one and otherwise a. Relative imports are resolved against `name`."""
    package = name if is_package else name.rpartition(".")[0]
    out: list[tuple[str, str | None]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(alias.name, None) for alias in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parent = package.split(".")[:len(package.split(".")) - (n.level - 1)] if package else []
                base = ".".join(parent + ([n.module] if n.module else []))
            if base:
                out += [(base, None) if alias.name == "*" else (f"{base}.{alias.name}", base) for alias in n.names]
    return tuple(dict.fromkeys(out))


def _parsed(name: str, path: Path) -> tuple[str, tuple[tuple[str, str | None], ...]]:
    """(hash of the file's AST less its text, its imports). Parsed once per file contents in a process."""
    raw = path.read_bytes()
    memo = (name, hashlib.sha256(raw).hexdigest())
    if memo not in _PARSED:
        tree = ast.parse(raw, filename=str(path))
        digest = hashlib.sha256(ast.dump(_without_text(tree)).encode()).hexdigest()
        _PARSED[memo] = (digest, _imports(tree, name, path.name == "__init__.py"))
    return _PARSED[memo]


def _unwrapped(produce):
    while isinstance(produce, functools.partial):
        produce = produce.func
    return produce


def _start(producer) -> tuple[str, Path]:
    """A producer's module and its source file: a callable's own module (already imported, so its file is
    known), or a module name looked up on disk."""
    if isinstance(producer, str):
        name, path = producer, _module_file(producer)
    else:
        name = getattr(_unwrapped(producer), "__module__", None) or ""
        file = getattr(sys.modules.get(name), "__file__", None)
        path = Path(file) if file and str(file).endswith(".py") else None
    if path is None or not path.is_file():
        raise ValueError(f"no source file for {producer!r}: its code can't be put in a cache key")
    return name, path


def code_modules(*producers) -> dict[str, Path]:
    """The source files that make up the producers' code, by module name: each producer's own module (a callable,
    or a module name) and every module it imports, directly or through another, that belongs to dopplertrack or to
    the producer's own top-level package. Imports inside functions and relative imports count. `<package>.runtime`
    is left out, however it is imported. Nothing is imported to find them.

    A package's __init__.py counts when something is imported from it by name, not for being a parent of a module
    that is imported."""
    todo = [_start(p) for p in producers]
    packages = {PACKAGE} | {name.split(".")[0] for name, _ in todo}
    found: dict[str, Path] = {}
    while todo:
        name, path = todo.pop()
        if name in found:
            continue
        found[name] = path
        for module, fallback in _parsed(name, path)[1]:
            top = module.split(".")[0]
            if top not in packages:
                continue
            file = _module_file(module)
            if file is None and fallback is not None:
                module, file = fallback, _module_file(fallback)
            if file is None or module in found or f"{module}.".startswith(f"{top}.{PLUMBING}."):
                continue
            todo.append((module, file))
    return dict(sorted(found.items()))


def code_sha256(*producers) -> str:
    """Hash of the producers' code (code_modules): each file's module name and its AST less docstrings and the
    messages of raise and warnings.warn. A comment, docstring or message edit leaves it unchanged; any other edit
    to one of the files, or a new import that brings another file in, changes it."""
    h = hashlib.sha256()
    for name, path in code_modules(*producers).items():
        h.update(f"{name};{_parsed(name, path)[0]};".encode())
    return h.hexdigest()


def producer_name(produce) -> str:
    """The producer's qualified name, module included."""
    produce = _unwrapped(produce)
    return f"{getattr(produce, '__module__', '?')}.{getattr(produce, '__qualname__', repr(produce))}"


def versions(*libraries: str) -> dict[str, str]:
    """The versions a key records: the named libraries', and the Python minor version, since an AST dump (and so
    code_sha256) differs between them."""
    return {"python": "%d.%d" % tuple(sys.version_info[:2]),
            **{name: str(importlib.import_module(name).__version__) for name in libraries}}


# ---- detections ------------------------------------------------------------------------------

DETECT_IGNORED = ("workers", "progress")    # change how detections are computed, not what they are


def spectrogram_sha256(sp) -> str:
    """Hash of a Spectrogram's contents: grid, power, mask and start time."""
    start = None if sp.start_utc is None else np.float64(sp.start_utc)
    return array_sha256(sp.t, sp.f, sp.S, sp.valid, start)


def detection_parts(sp, produce: Callable, **params) -> dict:
    """What a detection result depends on: the spectrogram's contents, every detect parameter except those
    in DETECT_IGNORED, the producer and its code (code_sha256 of the producer passed, so a variant detector
    has its own key), and the Python and numeric-library versions."""
    return {"spectrogram": spectrogram_sha256(sp), "params": {k: v for k, v in params.items() if k not in DETECT_IGNORED},
            "producer": producer_name(produce), "code": code_sha256(produce), "versions": versions("numpy", "scipy")}


def detection_key(sp, produce: Callable, **params) -> str:
    """The cache key cached_detections files these detections under, to record beside a result."""
    return entry_key(detection_parts(sp, produce, **params))


def cached_detections(sp, produce: Callable[..., T], root: str | Path | None = None, **params) -> T:
    """produce(sp, **params), cached on detection_parts. Meant for
    grid_scan.detect_events: cached_detections(sp, detect_events, f_lo=60, f_hi=300, top=10)."""
    return cached("detections", detection_parts(sp, produce, **params), lambda: produce(sp, **params), root=root)
