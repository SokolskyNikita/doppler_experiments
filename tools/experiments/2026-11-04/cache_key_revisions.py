"""The old (whole-module) and new (function-level) detector keys at each recent revision of tracks, doppler, audio."""
import hashlib, importlib.util, subprocess, sys, tempfile, types
from pathlib import Path
sys.path.insert(0, "src")
from dopplertrack import cache

MODS = ("tracks", "doppler", "audio")


def files_at(rev, tmp):
    out = {}
    for m in MODS:
        p = Path(tmp) / rev / f"{m}.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(subprocess.run(["git", "show", f"{rev}:src/dopplertrack/{m}.py"], capture_output=True, check=True).stdout)
        out[f"dopplertrack.{m}"] = p
    return out


def keys(paths):
    old = hashlib.sha256()
    for name in cache.DETECTOR_MODULES:
        old.update(name.encode() + b";"); old.update(paths[name].read_bytes())
    real = importlib.util.find_spec
    importlib.util.find_spec = lambda n, *a: types.SimpleNamespace(origin=str(paths[n])) if n in paths else real(n, *a)
    try:
        new = cache.code_sha256(cache.DETECTOR_CODE)
    except ValueError as exc:
        new = f"n/a ({exc})"
    finally:
        importlib.util.find_spec = real
    return old.hexdigest()[:12], new[:12]


revs = sys.argv[1:]
with tempfile.TemporaryDirectory() as tmp:
    prev = None
    for rev in revs:
        o, n = keys(files_at(rev, tmp))
        subject = subprocess.run(["git", "log", "-1", "--format=%h %s", rev], capture_output=True, text=True).stdout.strip()
        changed = "" if prev is None else f"  old {'changed' if o != prev[0] else 'same'}, new {'changed' if n != prev[1] else 'same'}"
        print(f"{subject[:70]:<70} old {o} new {n}{changed}")
        prev = (o, n)
