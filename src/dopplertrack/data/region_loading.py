"""Region loading: every trace of a day's archive that enters a bounding box, and saved traces."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dopplertrack.data.coverage import ScanReport
from dopplertrack.data.trace_parsing import TRACE_ERRORS, parse_trace_file
from dopplertrack.data.trajectories import Trace
from dopplertrack.runtime.parallel import process_pool, resolve_jobs


def _scan_one(args):
    path, bbox = args
    try:
        tr = parse_trace_file(path)
    except TRACE_ERRORS:
        return None, "malformed"
    if tr is None:
        return None, "empty"
    lat0, lat1, lon0, lon1 = bbox
    m = (tr.lat >= lat0) & (tr.lat <= lat1) & (tr.lon >= lon0) & (tr.lon <= lon1)
    if not m.any():
        return None, "outside_bbox"
    return tr, "kept"


def load_region(archive_dir: str | Path, bbox: tuple[float, float, float, float],
                workers: int | None = None, report: ScanReport | None = None) -> list[Trace]:
    """All traces with at least one point inside bbox=(lat_min, lat_max, lon_min, lon_max)."""
    files = sorted(Path(archive_dir).glob("traces/*/trace_full_*.json"))
    out = []
    report = report if report is not None else ScanReport()
    with process_pool(resolve_jobs(workers)) as ex:      # spawn, as everywhere: fork under numpy threads can deadlock
        for tr, outcome in ex.map(_scan_one, ((str(f), bbox) for f in files), chunksize=256):
            report.seen += 1
            setattr(report, outcome, getattr(report, outcome) + 1)
            if tr is not None:
                out.append(tr)
    return out


def in_bbox(tr: Trace, bbox) -> bool:
    lat0, lat1, lon0, lon1 = bbox
    return bool(((tr.lat >= lat0) & (tr.lat <= lat1) & (tr.lon >= lon0) & (tr.lon <= lon1)).any())


def save_traces(traces: list[Trace], path: str | Path, metadata: dict | None = None):
    extra = {"metadata": np.array(json.dumps(metadata))} if metadata is not None else {}
    for i, tr in enumerate(traces):
        for name in ("alt_source", "position_source", "flags"):
            values = getattr(tr, name)
            if values is not None:
                extra[f"{name}{i}"] = values
    np.savez_compressed(path, n=len(traces),
                        meta=np.array([json.dumps([t.icao, t.reg, t.typ, t.desc]) for t in traces]),
                        **extra,
                        **{f"a{i}": np.stack([t.t, t.lat, t.lon, t.alt, t.gs, t.on_ground.astype(float)]) for i, t in enumerate(traces)})


def load_traces(path: str | Path) -> list[Trace]:
    out = []
    with np.load(path, allow_pickle=False) as z:
        for i in range(int(z["n"])):
            icao, reg, typ, desc = json.loads(str(z["meta"][i]))
            a = z[f"a{i}"]
            provenance = [z[f"{name}{i}"] if f"{name}{i}" in z else None
                          for name in ("alt_source", "position_source", "flags")]
            out.append(Trace(icao, reg, typ, desc, a[0], a[1], a[2], a[3], a[4], a[5].astype(bool), *provenance))
    return out


def load_trace_metadata(path: str | Path) -> dict:
    """Extraction diagnostics, or an empty mapping for older trace files."""
    with np.load(path, allow_pickle=False) as z:
        return json.loads(str(z["metadata"])) if "metadata" in z else {}
