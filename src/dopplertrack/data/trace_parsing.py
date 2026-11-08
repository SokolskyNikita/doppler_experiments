"""Trace parsing: an adsb.lol / readsb trace file into a Trace."""
from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path

import numpy as np

from dopplertrack.data.trajectories import Trace

FT = 0.3048
KT = 0.514444
TRACE_ERRORS = (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, EOFError,
                OverflowError, zlib.error)


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
