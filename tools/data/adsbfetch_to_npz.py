"""Turn adsbfetch `trace` output into one of our trace npz files (adsb.save_traces), one UTC day.

usage: adsbfetch_to_npz.py OUT.npz --day YYYY-MM-DD --box S N W E --from SOURCE 'GLOB' [--from ...]
           [--prop-only] [--cache ~/.cache/adsbfetch] [--basis TEXT]

Each GLOB matches adsbfetch `trace --out` jsonl files fetched from SOURCE (adsbfi, airplaneslive,
adsblol, adsbx); the aircraft is the hex in the file's rows, or the <hex> in its name
(<anything>_<hex>_<source>.jsonl) when the day had no track. Rows from the fixed adsbfetch (they carry
ts_epoch, alt_geom, alt_is_geom and source_type) are read directly and give the same trace as our
parse_trace_bytes on the raw body. Rows from adsbfetch 0.2.0 rounded times to the second and kept only
slot 3's height, so for those the trace is rebuilt from the raw trace_full body the CLI cached
(~/.cache/adsbfetch, keyed by the sha256 of its URL); only when that body is missing are the old rows
used, and the metadata counts those traces as lossy.

Several sources are merged per aircraft: every point from each, sorted by time, dropping a point within
50 ms of one already kept (the networks share a schema, so this is the (hex, ts) dedupe; their positions
for one instant agree to tens of metres). Written with fetch-day's extraction metadata: requested_bbox
and coverage_bbox are the --box, max_range_m 0, scan counts per aircraft (seen = hexes asked for, kept =
traces written, empty = no track that day on every source, malformed = unreadable bodies,
excluded_types = jets dropped by --prop-only), and coverage_basis says how the aircraft were chosen, so
the envelope is not read as an archive's.
"""
import argparse
import glob
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dopplertrack.adsb import FT, KT, AircraftTypes, Trace, parse_trace_bytes, save_traces
from dopplertrack.coverage import ScanReport, extraction_metadata

ORIGINS = {"adsbx": "https://globe.adsbexchange.com", "adsbfi": "https://globe.adsb.fi",
           "airplaneslive": "https://globe.airplanes.live", "adsblol": "https://adsb.lol"}
DEDUPE_S = 0.05


def trace_url(origin, hex_, day):
    """The trace file's URL; a "~" address keeps its tilde in the file name (trace_full_~2a1633.json)."""
    return f"{origin}/globe_history/{day:%Y/%m/%d}/traces/{hex_[-2:]}/trace_full_{hex_}.json"


def from_fixed_rows(rows, hex_):
    """From adsbfetch's fixed trace rows (ts_epoch to the millisecond, alt_geom, alt_baro, alt_is_geom,
    source_type): the same trace parse_trace_bytes makes from the raw body. Height is alt_geom when present
    (slot 10, or slot 3 when flag 8 marks it geometric), else alt_baro, as parse_trace_bytes does."""
    ok = [r for r in rows if r.get("lat") is not None and r.get("lon") is not None]
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    alt, src = [], []
    for r in ok:
        if num(r.get("alt_geom")):
            alt.append(r["alt_geom"] * FT); src.append("geometric")
        elif num(r.get("alt_baro")):
            alt.append(r["alt_baro"] * FT); src.append("barometric")
        else:
            alt.append(np.nan); src.append("none")
    flags = np.array([int(bool(r.get("stale"))) | 2 * int(bool(r.get("new_leg"))) | 4 * int(bool(r.get("rate_is_geom")))
                      | 8 * int(bool(r.get("alt_is_geom"))) for r in ok], dtype=np.int32)
    return Trace(hex_, ok[0].get("registration"), ok[0].get("aircraft_type"), ok[0].get("type_name"),
                 np.array([float(r["ts_epoch"]) for r in ok]), np.array([r["lat"] for r in ok], float),
                 np.array([r["lon"] for r in ok], float), np.array(alt),
                 np.array([r["gs"] * KT if num(r.get("gs")) else np.nan for r in ok]),
                 np.array([r.get("alt_baro") == "ground" for r in ok]), np.array(src),
                 np.array([r.get("source_type") or "unknown" for r in ok]), flags)


def from_rows(rows, hex_):
    """Lossy fallback from adsbfetch 0.2.0 rows: whole-second times, barometric (or flagged geometric) height."""
    t = np.array([datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp() for r in rows])
    alt = np.array([r["alt_baro"] * FT if isinstance(r.get("alt_baro"), (int, float)) else np.nan for r in rows])
    gs = np.array([r["gs"] * KT if isinstance(r.get("gs"), (int, float)) else np.nan for r in rows])
    grd = np.array([r.get("alt_baro") == "ground" for r in rows])
    src = np.array(["geometric" if r.get("geom_alt") else ("barometric" if np.isfinite(a) else "none") for r, a in zip(rows, alt)])
    flags = np.array([int(bool(r.get("stale"))) | 2 * int(bool(r.get("new_leg"))) | 4 * int(bool(r.get("geom_rate")))
                      | 8 * int(bool(r.get("geom_alt"))) for r in rows], dtype=np.int32)
    return Trace(hex_, rows[0].get("registration"), rows[0].get("aircraft_type"), None, t,
                 np.array([r["lat"] for r in rows], float), np.array([r["lon"] for r in rows], float), alt, gs, grd,
                 src, np.array(["unknown"] * len(rows)), flags)


def merge(traces):
    """One trace from several sources' traces of one aircraft (sorted, 50 ms dedupe)."""
    if len(traces) == 1:
        return traces[0]
    fill = {"alt_source": "unknown", "position_source": "unknown", "flags": 0}

    def cat(name):      # traces cut before Phase 0 carry no provenance arrays
        return np.concatenate([getattr(tr, name) if getattr(tr, name) is not None else np.full(len(tr.t), fill[name])
                               for tr in traces])
    t = cat("t"); order = np.argsort(t, kind="stable"); t = t[order]
    keep = np.ones(len(t), bool)
    last = -np.inf
    for i, x in enumerate(t):
        if x - last < DEDUPE_S:
            keep[i] = False
        else:
            last = x
    idx = order[keep]
    first = traces[0]
    return Trace(first.icao, first.reg, first.typ, first.desc, cat("t")[idx], cat("lat")[idx], cat("lon")[idx],
                 cat("alt")[idx], cat("gs")[idx], cat("on_ground")[idx], cat("alt_source")[idx],
                 cat("position_source")[idx], cat("flags")[idx])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--day", required=True)
    ap.add_argument("--box", nargs=4, type=float, required=True, metavar=("S", "N", "W", "E"))
    ap.add_argument("--from", dest="inputs", nargs=2, action="append", required=True, metavar=("SOURCE", "GLOB"))
    ap.add_argument("--prop-only", action="store_true")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "adsbfetch"))
    ap.add_argument("--basis", default="aircraft listed by the caller, then full day traces")
    a = ap.parse_args()
    day = datetime.strptime(a.day, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()
    per_hex, files_seen = {}, []
    n_malformed = n_lossy = n_fixed = 0
    for source, pattern in a.inputs:
        for f in sorted(glob.glob(os.path.expanduser(pattern))):
            files_seen.append((source, os.path.basename(f)))
            rows = [json.loads(line) for line in open(f) if line.strip()]
            m = re.search(r"_(~?[0-9a-f]{6})_[a-z]+\.jsonl$", f)
            hex_ = (rows[0]["hex"] if rows else (m.group(1) if m else None))
            if hex_ is None:
                continue
            hex_ = hex_.lower()        # a non-ICAO (TIS-B) address keeps its "~", as in our tar cuts
            per_hex.setdefault(hex_, [])
            body = Path(a.cache) / hashlib.sha256(trace_url(ORIGINS[source], hex_, day).encode()).hexdigest()
            if rows and "ts_epoch" in rows[0]:         # the fixed CLI's rows carry everything we read
                per_hex[hex_].append(from_fixed_rows(rows, hex_)); n_fixed += 1
            elif body.exists():
                try:
                    tr = parse_trace_bytes(body.read_bytes(), hex_)
                except (ValueError, KeyError, TypeError, IndexError):
                    n_malformed += 1
                    continue
                if tr is not None:
                    per_hex[hex_].append(tr)
            elif rows:
                per_hex[hex_].append(from_rows(rows, hex_)); n_lossy += 1
    for h in [h for h, v in per_hex.items() if not v and "~" + h in per_hex]:
        del per_hex[h]       # an empty file names its aircraft without the "~" its other source's rows carry
    types = AircraftTypes()
    merged = [merge(v) for v in per_hex.values() if v]
    kept = [tr for tr in merged if types.is_prop(tr.typ)] if a.prop_only else merged
    rep = ScanReport(seen=len(per_hex), malformed=n_malformed, empty=sum(1 for v in per_hex.values() if not v),
                     outside_bbox=0, excluded_types=len(merged) - len(kept), kept=len(kept))
    meta = extraction_metadata(tuple(a.box), 0.0, rep, date=a.day, source="adsbfetch " + "+".join(sorted({s for s, _ in a.inputs})),
                               coverage_basis=a.basis, rebuilt_from=f"{n_fixed} from adsbfetch rows (ts_epoch, alt_geom), the rest from cached trace_full bodies via parse_trace_bytes",
                               lossy_traces=n_lossy, dedupe_s=DEDUPE_S, files=len(files_seen))
    tmp = Path(a.out).with_name(f".{Path(a.out).stem}.{os.getpid()}.tmp.npz")
    save_traces(kept, tmp, metadata=meta)
    os.replace(tmp, a.out)
    print(f"{len(kept)} traces ({rep.excluded_types} excluded by type, {rep.empty} empty, {n_malformed} malformed, "
          f"{n_lossy} lossy) from {len(files_seen)} files -> {a.out}")


if __name__ == "__main__":
    main()
