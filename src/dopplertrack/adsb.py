"""Read adsb.lol / readsb `globe_history` daily archives and classify aircraft."""
from __future__ import annotations

import csv
import gzip
import json
import os
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

from .geo import lla_to_enu
from .coverage import ScanReport
from .doppler import MAX_TRACE_GAP_S
from .parallel import process_pool, resolve_jobs

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


# Joining day files (PLAN 5.6: recordings that cross UTC midnight). Each day's archive ends at midnight,
# so a flight in the air then becomes two traces with a short seam between them. A seam is joined only
# when the aircraft is plainly the same flight across it; the four limits are judgement, set before any
# audio was looked at.
SEAM_MAX_GAP_S = 90.0          # the segmenter's geometry bound
SEAM_SPEED_FACTOR = 1.5        # horizontal jump <= factor * mean ground speed * gap + slack
SEAM_JUMP_SLACK_M = 500.0
SEAM_CLIMB_M_S = 8.0           # altitude change <= rate * gap + slack: a propeller climb is 2.5-7.5 m/s
SEAM_ALT_SLACK_M = 100.0


def _seam(a: Trace, b: Trace) -> dict:
    """Whether trace b continues trace a across a day boundary, and the numbers that decided it."""
    from .geo import haversine_m
    va, vb = np.flatnonzero(a.valid_positions()), np.flatnonzero(b.valid_positions())
    out = {"icao": a.icao, "gap_s": float(b.t[0] - a.t[-1]), "joined": False}
    if not len(va) or not len(vb):
        return {**out, "reason": "no usable position on one side of the seam"}
    i, j = va[-1], vb[0]
    gap = float(b.t[j] - a.t[i])
    jump = float(haversine_m(a.lat[i], a.lon[i], b.lat[j], b.lon[j]))
    climb = float(abs(b.alt[j] - a.alt[i]))
    gs = np.nanmean([a.gs[i], b.gs[j]]) if np.isfinite([a.gs[i], b.gs[j]]).any() else np.nan
    out.update(gap_s=gap, jump_m=round(jump, 1), altitude_change_m=round(climb, 1),
               ground_speed_m_s=None if not np.isfinite(gs) else round(float(gs), 1))
    if gap > SEAM_MAX_GAP_S:
        return {**out, "reason": f"gap over {SEAM_MAX_GAP_S:g} s"}
    if not np.isfinite(gs):
        return {**out, "reason": "no ground speed at the seam"}
    if jump > SEAM_SPEED_FACTOR * gs * max(gap, 0.0) + SEAM_JUMP_SLACK_M:
        return {**out, "reason": "position jump too large for the speed"}
    if climb > SEAM_CLIMB_M_S * max(gap, 0.0) + SEAM_ALT_SLACK_M:
        return {**out, "reason": "altitude change too large for the gap"}
    return {**out, "joined": True, "reason": "continuous"}


def _concat(a: Trace, b: Trace) -> Trace:
    n_a, n_b = len(a), len(b)

    def provenance(name, fill):
        x, y = getattr(a, name), getattr(b, name)
        if x is None and y is None:
            return None
        return np.concatenate([np.full(n_a, fill) if x is None else x, np.full(n_b, fill) if y is None else y])

    flags_b = None if b.flags is None else b.flags.copy()
    if flags_b is not None and n_b:
        flags_b[0] &= ~2       # the later file's first point starts that file, not a new leg
    b = Trace(b.icao, b.reg, b.typ, b.desc, b.t, b.lat, b.lon, b.alt, b.gs, b.on_ground, b.alt_source,
              b.position_source, flags_b)
    t = np.concatenate([a.t, b.t])
    keep = np.r_[True, np.diff(t) > 0]          # day files don't overlap; a repeated time keeps the first
    cat = {k: np.concatenate([getattr(a, k), getattr(b, k)])[keep] for k in ("t", "lat", "lon", "alt", "gs", "on_ground")}
    prov = {k: (None if v is None else v[keep]) for k, v in (("alt_source", provenance("alt_source", "unknown")),
                                                               ("position_source", provenance("position_source", "unknown")),
                                                               ("flags", provenance("flags", np.int32(0))))}
    return Trace(a.icao, a.reg or b.reg, a.typ or b.typ, a.desc or b.desc, **cat, **prov)


def join_days(paths) -> tuple[list[Trace], dict]:
    """Traces and extraction metadata from one or more consecutive day files of the same box. One file is
    exactly load_traces and load_trace_metadata. With several, a flight that continues across a day
    boundary becomes one trace (see _seam), and the metadata lists every day's own metadata, the
    intersection of their coverage envelopes when all are known, and every seam with what decided it."""
    paths = [str(p) for p in paths]
    if len(paths) == 1:
        return load_traces(paths[0]), load_trace_metadata(paths[0])
    days = [(p, load_traces(p), load_trace_metadata(p)) for p in paths]
    days.sort(key=lambda d: min((float(t.t[0]) for t in d[1] if len(t)), default=np.inf))
    open_: dict[str, Trace] = {}
    done: list[Trace] = []
    seams = []
    for k, (_, traces, _) in enumerate(days):
        carried = open_
        open_ = {}
        for tr in traces:
            prev = carried.pop(tr.icao, None)
            if prev is not None:
                seam = _seam(prev, tr)
                seams.append(seam)
                if seam["joined"]:
                    tr = _concat(prev, tr)
                else:
                    done.append(prev)
            if tr.icao in open_:          # two traces of one aircraft in one day file: keep both, join the later
                done.append(open_[tr.icao])
            open_[tr.icao] = tr
        done.extend(carried.values())
    done.extend(open_.values())
    metas = [m for _, _, m in days]
    meta = {"version": 1, "joined_days": [{"path": p, "metadata": m or "legacy: no extraction metadata"} for p, _, m in days],
            "seams": seams}
    if all(m.get("coverage_bbox") for m in metas):
        boxes = np.array([m["coverage_bbox"] for m in metas], float)
        meta["coverage_bbox"] = [float(boxes[:, 0].max()), float(boxes[:, 1].min()),
                                 float(boxes[:, 2].max()), float(boxes[:, 3].min())]
        meta["max_range_m"] = min(float(m.get("max_range_m", 0.0)) for m in metas)
    if all(m.get("scan") for m in metas):
        meta["scan"] = {k: sum(int(m["scan"][k]) for m in metas) for k in metas[0]["scan"]}
    if metas[0].get("height_datums"):
        meta["height_datums"] = metas[0]["height_datums"]
    return done, meta
