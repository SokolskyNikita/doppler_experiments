"""Write bench/manifest.json: every file under $DOPPLERTRACK_DATA/raw with its size, SHA-256, source and licence.

raw/ is never modified, so this is how another machine, worktree or agent checks that it has the same inputs.
It is an integrity inventory: --check compares paths and hashes only, not the source or licence fields.

Sources and licences are assigned below, from what the data root's MANIFEST.md records: per recording for
xeno-canto (from its selected.json) and Eclipse Soundscapes (one Zenodo record per site), by path prefix
for the rest. null means not recorded, not "unrestricted".

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
    ("raw/audio/youtube/oyster_bay", "https://youtu.be/4CxVxuMVkMc (colsto)", None),
    ("raw/audio/youtube/swfl_", "https://youtu.be/zs2o5Rhlp5w (SWFL Eagle Cam #3)", None),
    ("raw/audio/eclipse/sites.csv", "Eclipse Soundscapes site list compiled from Zenodo", None),
    ("raw/audio/xenocanto/", "xeno-canto.org API v3 search results", None),
    ("raw/audio/livermore/zenodo-23424278/", "https://zenodo.org/records/23424278", "https://creativecommons.org/licenses/by/4.0/"),
    ("raw/audio/aerosonicdb/zenodo-10215080/", "https://zenodo.org/records/10215080", "https://creativecommons.org/licenses/by-nc/4.0/"),
    ("raw/audio/datasec/zenodo-23097290/", "https://zenodo.org/records/23097290", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    ("raw/audio/datased/zenodo-15346092/", "https://zenodo.org/records/15346092", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    ("raw/audio/a2o/", "https://data.acousticobservatory.org/projects/1 (Australian Acoustic Observatory; recording/site IDs in filenames and metadata)", "https://creativecommons.org/licenses/by/4.0/"),
    ("raw/aux/metar/", "Iowa Environmental Mesonet: ASOS/METAR and RAOB soundings", None),
    ("raw/models/rnnoise/", "RNNoise models for ffmpeg arnndn", None),
]
ECLIPSE_ZENODO = {"375": "21708608", "710": "21722091", "740": "21877430", "937": "21829727"}
CC_BY_4 = "https://creativecommons.org/licenses/by/4.0/"


def xenocanto_records() -> dict:
    p = ROOT / "raw" / "audio" / "xenocanto" / "selected.json"
    return {str(r["id"]): r for r in json.load(open(p))} if p.exists() else {}


def describe(rel: str, xc: dict) -> tuple[str | None, str | None]:
    """(source, licence) of one raw file, given its path relative to ROOT."""
    name = rel.rsplit("/", 1)[-1]
    if rel.startswith("raw/audio/a2o/"):
        recording_id = name.rsplit(".", 1)[0]
        if recording_id.isdigit():
            return (f"https://api.acousticobservatory.org/audio_recordings/{recording_id}", CC_BY_4)
        if name == "site.json":
            site_id = rel.split("/")[3].removeprefix("site-")
            return (f"https://api.acousticobservatory.org/sites/{site_id}", CC_BY_4)
    if rel.startswith("raw/audio/xenocanto/XC"):
        r = xc.get(name[2:].split("_")[0])
        return (r["url"], r["lic"]) if r else (None, None)
    if rel.startswith("raw/audio/eclipse/ESID_"):
        record = ECLIPSE_ZENODO.get(rel.split("/")[3].removeprefix("ESID_"))
        return (f"https://zenodo.org/records/{record}" if record else "Eclipse Soundscapes on Zenodo", CC_BY_4)
    return next(((s, l) for prefix, s, l in SOURCES if rel.startswith(prefix)), (None, None))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan() -> list[dict]:
    xc = xenocanto_records()
    files = []
    for p in sorted((ROOT / "raw").rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(ROOT).as_posix()
        source, licence = describe(rel, xc)
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
