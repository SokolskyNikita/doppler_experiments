"""Private cases (docs/proposals/2026-11-04-private-cases.md): the owner's recordings, run on this Mac only.

A private case in bench/cases.json names a `site` and carries no coordinate, audio path or derived file. Those live
under $DOPPLERTRACK_DATA/private/:
- sites/<site>.json: {"site_json": "<path under the data root>"}, a pointer to the owner's site file, read in place
  (its lat, lon, ground_m, mic_height_m and optional geoid_undulation_m);
- cases/<case>.json: what the case runs on, merged into the blind case at run time: "spectrogram", "audio",
  "derived" (with recipes and hashes), "flight_data" (traces, extraction_box) and "search" (bbox, cpa_cache).

A record of a private case is written site-relative unless the run reveals it: every candidate and the refined point
become east and north offsets in metres from the site, every box an offset box, and the triples sidecar east and
north arrays; then `assert_no_site` refuses the record if any container still holds a latitude and a longitude near
the site's, so a field this misses fails loudly instead of leaking.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .cases import data_root, is_private

GUARD_DEG = 0.5            # a latitude and a longitude this close to the site's, in one container, is a leak


class PrivateDataError(RuntimeError):
    """A private case's files are missing or malformed, or a record would leak the site."""


def private_root() -> Path:
    return data_root() / "private"


def load_site(site_id: str) -> dict:
    """The site's position from the owner's file, read in place: {"lat", "lon", "elev_m"}."""
    pointer = private_root() / "sites" / f"{site_id}.json"
    if not pointer.exists():
        raise PrivateDataError(f"no site pointer {pointer}")
    target = data_root() / json.loads(pointer.read_text())["site_json"]
    if not target.exists():
        raise PrivateDataError(f"the site file {target} named by {pointer} is missing")
    s = json.loads(target.read_text())
    try:
        elev = float(s["ground_m"]) + float(s["mic_height_m"]) + float(s.get("geoid_undulation_m", 0.0))
        return {"lat": float(s["lat"]), "lon": float(s["lon"]), "elev_m": elev}
    except (KeyError, TypeError, ValueError) as exc:
        raise PrivateDataError(f"{target} lacks a finite lat, lon, ground_m or mic_height_m") from exc


def resolve_case(case: dict) -> dict:
    """The blind private case with its private fields merged in, for a run on this Mac."""
    if not is_private(case):
        return case
    path = private_root() / "cases" / f"{case['id']}.json"
    if not path.exists():
        raise PrivateDataError(f"no private case file {path}")
    extra = json.loads(path.read_text())
    out = dict(case)
    for key in ("spectrogram", "audio", "derived"):
        if key in extra:
            out[key] = extra[key]
    for key in ("flight_data", "search"):
        out[key] = {**case.get(key, {}), **extra.get(key, {})}
    return out


def _enu(lat, lon, site: dict):
    """East and north metres from the site, on a local tangent plane (good to metres over a search box)."""
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    north = np.radians(lat - site["lat"]) * 6371008.8
    east = np.radians(lon - site["lon"]) * 6371008.8 * math.cos(math.radians(site["lat"]))
    return east, north


def _offset(lat, lon, site) -> dict:
    e, n = _enu(lat, lon, site)
    return {"east": round(float(e), 1), "north": round(float(n), 1)}


def _offset_box(box, site) -> list:
    """[lat0, lat1, lon0, lon1] as [south, north, west, east] metres from the site."""
    east, north = _enu([box[0], box[1]], [box[2], box[3]], site)
    return [round(float(north[0]), 1), round(float(north[1]), 1), round(float(east[0]), 1), round(float(east[1]), 1)]


def _is_box(v) -> bool:
    return isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v)


def _boxes_to_offsets(obj, site):
    """Every four-number box anywhere in obj, and lists of them, rewritten as offset boxes."""
    if isinstance(obj, dict):
        return {k: _boxes_to_offsets(v, site) for k, v in obj.items()}
    if _is_box(obj) and abs(obj[0] - site["lat"]) < 5 and abs(obj[2] - site["lon"]) < 5:
        return {"offset_box_m": _offset_box(obj, site)}
    if isinstance(obj, list):
        return [_boxes_to_offsets(v, site) for v in obj]
    return obj


def to_site_relative(record: dict, site_id: str, site: dict, case_dir: Path) -> dict:
    """The record in the site's frame: candidates and refined point as offsets, boxes as offset boxes, the triples
    sidecar rewritten with east and north arrays and its hash updated."""
    from dopplertrack.result import sha256_file
    rec = json.loads(json.dumps(record))
    for c in rec.get("candidates", []):
        c["offset_m"] = _offset(c.pop("lat"), c.pop("lon"), site)
    ref = rec.get("refined")
    if isinstance(ref, dict) and "lat" in ref:
        ref["offset_m"] = _offset(ref.pop("lat"), ref.pop("lon"), site)
    rec["provenance"] = _boxes_to_offsets(rec["provenance"], site)
    rec["data_limitations"] = _boxes_to_offsets(rec["data_limitations"], site)
    tf = rec.get("funnel", {}).get("triples_file")
    if isinstance(tf, dict) and "path" in tf:
        path = case_dir / tf["path"]
        with np.load(path) as z:
            arrays = {k: z[k] for k in z.files}
        for stage in tf.get("stages", []):
            e, n = _enu(arrays.pop(f"{stage}__lat"), arrays.pop(f"{stage}__lon"), site)
            arrays[f"{stage}__east"], arrays[f"{stage}__north"] = e, n
        tmp = path.with_name(f".{path.name}.tmp.npz")
        np.savez_compressed(tmp, **arrays)
        tmp.replace(path)
        tf["sha256"] = sha256_file(path)
    rec["frame"], rec["site"] = "site-relative", site_id
    return rec


def assert_no_site(obj, site: dict, where: str = "record") -> None:
    """Refuse obj if any one dict or list holds a number within GUARD_DEG of the site's latitude and another within
    GUARD_DEG of its longitude: a position near the site, whatever the field is called."""
    if isinstance(obj, (dict, list)):
        items = list(obj.items()) if isinstance(obj, dict) else list(enumerate(obj))
        nums = [v for _, v in items if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if any(abs(v - site["lat"]) < GUARD_DEG for v in nums) and any(abs(v - site["lon"]) < GUARD_DEG for v in nums):
            raise PrivateDataError(f"{where} holds a position near the site; refusing to write it")
        for k, v in items:
            assert_no_site(v, site, f"{where}.{k}" if isinstance(obj, dict) else f"{where}[{k}]")


def new_private_run(topic: str) -> Path:
    """A new run folder under private/runs/ (as tools/data/new_run.py makes them under runs/): a private case's
    records stay where nothing uploads them."""
    import datetime
    import subprocess
    now = datetime.datetime.now().astimezone()
    base = private_root() / "runs" / f"{now:%Y-%m-%d}-{topic}"
    base.parent.mkdir(parents=True, exist_ok=True)
    for n in range(1, 1000):
        run = base if n == 1 else base.with_name(f"{base.name}-{n}")
        try:
            run.mkdir()
            break
        except FileExistsError:
            continue

    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
    (run / "run.json").write_text(json.dumps({"created": now.isoformat(timespec="seconds"), "topic": topic,
                                              "git_commit": git("rev-parse", "HEAD"),
                                              "git_dirty": bool(git("status", "--porcelain")), "private": True},
                                             indent=1) + "\n")
    return run
