"""Read adsb.lol / readsb `globe_history` daily archives and classify aircraft."""
from __future__ import annotations

import csv
import gzip
import json
import os
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

from .geo import lla_to_enu
from .coverage import ScanReport
from .doppler import MAX_TRACE_GAP_S

FT = 0.3048
KT = 0.514444
_DOC8643_URL = "https://opensky-network.org/datasets/metadata/doc8643AircraftTypes.csv"
TRACE_ERRORS = (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, EOFError,
                OverflowError, zlib.error)


def _cache_dir() -> Path:
    p = Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack"))
    p.mkdir(parents=True, exist_ok=True)
    return p


class AircraftTypes:
    """ICAO Doc 8643 designator -> engine class ('Piston', 'Turboprop', 'Jet', ...)."""

    def __init__(self, path: str | Path | None = None):
        p = Path(path) if path else _cache_dir() / "doc8643AircraftTypes.csv"
        if not p.exists():
            p.write_bytes(requests.get(_DOC8643_URL, timeout=120).content)
        self.types: dict[str, dict] = {}
        with open(p, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self.types.setdefault(row["Designator"], row)

    def engine(self, designator: str | None) -> str | None:
        r = self.types.get(designator or "")
        return r["EngineType"] if r else None

    def is_prop(self, designator: str | None, unknown_ok: bool = True) -> bool:
        e = self.engine(designator)
        if e is None:
            return unknown_ok
        return any(k in e for k in ("Piston", "Turboprop", "Electric"))


@dataclass
class Trace:
    icao: str
    reg: str | None
    typ: str | None
    desc: str | None
    t: np.ndarray        # unix seconds
    lat: np.ndarray
    lon: np.ndarray
    alt: np.ndarray      # metres: WGS-84 ellipsoidal when geometric, else pressure altitude
    gs: np.ndarray       # m/s (nan if missing)
    on_ground: np.ndarray
    alt_source: np.ndarray | None = None       # geometric, barometric, none; unknown for legacy files
    position_source: np.ndarray | None = None  # readsb slot 9 (adsb_icao, mlat, tisb_icao, ...)
    flags: np.ndarray | None = None            # slot 6; bit 1 fix after reception gap, bit 2 new leg, bit 8 geometric height

    def __len__(self):
        return len(self.t)

    def valid_positions(self):
        """Airborne points with usable coordinates and altitude.

        readsb's stale bit describes the gap *before* this new reliable fix;
        it does not invalidate the fix (readsb track.c, seenPosReliable).
        """
        return (~self.on_ground & np.isfinite(self.alt) & np.isfinite(self.lat) & np.isfinite(self.lon))

    def break_indices(self, max_gap_s: float):
        """Shared boundaries for geometry segments and coverage diagnostics."""
        flags = self.flags if self.flags is not None else np.zeros(len(self.t), int)
        valid = self.valid_positions()
        return np.flatnonzero((np.diff(self.t) > max_gap_s) | (valid[1:] != valid[:-1])
                              | ((flags[1:] & 2) != 0)) + 1

    def segments(self, max_gap_s: float = 90.0) -> list[slice]:
        """Airborne geometry runs; resampling separately masks evidence gaps over 30 s.

        Keeping the 90 s geometry bound allows a CPA proposal inside a short
        reception hole without inventing acoustic evidence in that hole.
        """
        out = []
        if len(self.t) == 0:
            return out
        valid = self.valid_positions()
        brk = self.break_indices(max_gap_s)
        starts = np.r_[0, brk]; ends = np.r_[brk, len(self.t)]
        for s, e in zip(starts, ends):
            if e - s >= 2 and valid[s]:
                out.append(slice(s, e))
        return out

    def coverage_gaps(self, max_gap_s: float = MAX_TRACE_GAP_S):
        """Interior evidence holes bracketed by usable airborne points.

        Uses the same validity and boundary rules as segments(), with the
        stricter evidence gap bound. Known ground intervals are not holes.
        """
        points = np.flatnonzero(self.valid_positions())
        boundaries = np.zeros(len(self.t), int)
        boundaries[self.break_indices(max_gap_s)] = 1
        boundaries = np.cumsum(boundaries)
        ground = np.cumsum(self.on_ground)
        flags = self.flags if self.flags is not None else np.zeros(len(self.t), int)
        legs = np.cumsum((flags & 2) != 0)
        left, right = points[:-1], points[1:]
        missing = (boundaries[right] != boundaries[left]) & (ground[right] == ground[left])
        for left, right in zip(left[missing], right[missing]):
            reasons = []
            if self.t[right] - self.t[left] > max_gap_s:
                reasons.append("time gap")
            if right > left + 1:
                reasons.append("missing position/altitude")
            if legs[right] != legs[left]:
                reasons.append("new leg")
            yield left, right, ", ".join(reasons)

    def resample(self, sl: slice, dt: float = 1.0, *, return_valid=False):
        """Resample geometry; optionally retain the original observations' support mask.

        Interpolated coordinates across 30–90 s holes serve CPA proposals only.
        The mask prevents modelled curves from scoring those coordinates.
        """
        t = self.t[sl]
        tq = np.arange(t[0], t[-1], dt)
        result = (tq, np.interp(tq, t, self.lat[sl]), np.interp(tq, t, self.lon[sl]), np.interp(tq, t, self.alt[sl]))
        if not return_valid:
            return result
        idx = np.clip(np.searchsorted(t, tq, side="right") - 1, 0, len(t) - 2)
        valid = ((t[idx + 1] - t[idx] <= MAX_TRACE_GAP_S)
                 | (tq == t[idx]) | (tq == t[idx + 1]))
        return (*result, valid)

    def enu(self, sl: slice, lat0: float, lon0: float, dt: float = 1.0, *, return_valid=False):
        tq, la, lo, al, valid = self.resample(sl, dt, return_valid=True)
        result = (tq, lla_to_enu(la, lo, al, lat0, lon0))
        return (*result, valid) if return_valid else result


def parse_trace_file(path: str | Path) -> Trace | None:
    return parse_trace_bytes(Path(path).read_bytes(), Path(path).stem.split("_")[-1])


def parse_trace_bytes(raw: bytes, fallback_icao: str = "") -> Trace | None:
    """Parse one readsb trace_full JSON document (gzipped or not).

    Field and flag definitions: https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons
    Missing altitudes are retained for provenance but excluded by segments().
    Stale-flagged fixes remain usable: that flag records a preceding reception
    gap, not a faulty current position.
    """
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    d = json.loads(raw)
    base = float(d.get("timestamp", 0.0))
    rows = d.get("trace") or []
    t, lat, lon, alt, gs, grd = [], [], [], [], [], []
    alt_source, position_source, flags = [], [], []
    for r in rows:
        if r[1] is None or r[2] is None:
            continue
        a = r[3]
        flag = int(r[6] or 0) if len(r) > 6 else 0
        on_ground = a == "ground"
        geom = r[10] if len(r) > 10 else None
        if isinstance(geom, (int, float)) and np.isfinite(geom):
            am = geom * FT
            source = "geometric"
        elif isinstance(a, (int, float)) and np.isfinite(a):
            am = a * FT
            source = "geometric" if flag & 8 else "barometric"
        else:
            am, source = np.nan, "none"
        t.append(base + r[0]); lat.append(r[1]); lon.append(r[2]); alt.append(am)
        gs.append(r[4] * KT if isinstance(r[4], (int, float)) else np.nan); grd.append(on_ground)
        alt_source.append(source)
        position_source.append(r[9] if len(r) > 9 and isinstance(r[9], str) else "unknown")
        flags.append(flag)
    if not t:
        return None
    return Trace(d.get("icao", fallback_icao), d.get("r"), d.get("t"), d.get("desc"),
                 np.array(t), np.array(lat), np.array(lon), np.array(alt), np.array(gs), np.array(grd),
                 np.array(alt_source), np.array(position_source), np.array(flags, dtype=np.int32))


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
    with ProcessPoolExecutor(workers or os.cpu_count()) as ex:
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
