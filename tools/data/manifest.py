"""Write bench/manifest.json: every file under $DOPPLERTRACK_DATA/raw with its size, SHA-256, source and licence.

raw/ is never modified, so this is how another machine, worktree or agent checks that it has the same inputs.
Sources and licences come from MANIFEST.md in the data root; null means not recorded there.

usage (from the repo root): uv run python tools/data/manifest.py [--check]
--check re-hashes raw/ and lists files that are missing, new or changed (exit status 1 if any)."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
OUT = Path(__file__).resolve().parents[2] / "bench" / "manifest.json"

SOURCES = [   # (path prefix, source, licence)
    ("raw/adsb/", "adsb.lol globe_history day archive, planes-readsb-prod-0 (github.com/adsblol)", None),
    ("raw/audio/youtube/oyster_bay", "youtu.be/4CxVxuMVkMc (colsto)", None),
    ("raw/audio/youtube/swfl_", "youtu.be/zs2o5Rhlp5w (SWFL Eagle Cam #3)", None),
    ("raw/audio/eclipse/", "Eclipse Soundscapes on Zenodo; record per site in MANIFEST.md", "CC BY 4.0"),
    ("raw/audio/xenocanto/", "xeno-canto.org API v3", "CC BY-NC-SA 4.0 (one recording BY-NC-ND)"),
    ("raw/aux/metar/", "Iowa Environmental Mesonet: ASOS/METAR and RAOB soundings", None),
    ("raw/models/rnnoise/", "RNNoise models for ffmpeg arnndn", None),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan() -> list[dict]:
    files = []
    for p in sorted((ROOT / "raw").rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(ROOT).as_posix()
        source, licence = next(((s, l) for prefix, s, l in SOURCES if rel.startswith(prefix)), (None, None))
        files.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p), "source": source, "licence": licence})
    return files


if __name__ == "__main__":
    files = scan()
    if "--check" in sys.argv:
        want = {f["path"]: f["sha256"] for f in json.load(open(OUT))["files"]}
        got = {f["path"]: f["sha256"] for f in files}
        bad = sorted(set(want) ^ set(got)) + sorted(k for k in set(want) & set(got) if want[k] != got[k])
        for k in bad:
            print("missing, new or changed:", k)
        sys.exit(1 if bad else 0)
    OUT.parent.mkdir(exist_ok=True)
    json.dump({"schema": 1, "root": "$DOPPLERTRACK_DATA", "files": files}, open(OUT, "w"), indent=1)
    print(f"{len(files)} files, {sum(f['bytes'] for f in files) / 1e9:.1f} GB -> {OUT}")
