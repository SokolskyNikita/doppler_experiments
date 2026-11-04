"""Make a failure-case trace file from a cut with extraction metadata: end the flight data early, or remove flights.

usage: edit_traces.py IN OUT [--end-utc ISO] [--drop ICAO,...]
--end-utc   drops every point after that time (and traces left empty), and sets the metadata's covered_utc to
            the archive day's start through that time, so the file says honestly what it covers.
--drop      removes every trace of those aircraft; every other trace is copied point for point, so the traffic
            around the removed flights is untouched.
The metadata is the input's, plus `edited`: the input's path and SHA-256 and what was changed. Refuses to
overwrite OUT.
"""
import argparse
import dataclasses
import datetime
import hashlib
import os
from pathlib import Path

from dopplertrack.adsb import load_trace_metadata, load_traces, save_traces

ARRAYS = ("t", "lat", "lon", "alt", "gs", "on_ground", "alt_source", "position_source", "flags")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--end-utc")
    ap.add_argument("--drop", default="")
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit(f"{a.out} exists")
    meta = load_trace_metadata(a.src)
    if not meta:
        raise SystemExit(f"{a.src} has no extraction metadata; cut it again with extract_boxes.py first")
    traces = load_traces(a.src)
    root = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack")).resolve()
    src = a.src.resolve()
    edit = {"from": str(src.relative_to(root)) if src.is_relative_to(root) else src.name, "sha256": _sha256(a.src), "traces_in": len(traces)}
    drop = {x.strip().lower() for x in a.drop.split(",") if x.strip()}
    if drop:
        missing = drop - {t.icao for t in traces}
        if missing:
            raise SystemExit(f"no trace of {sorted(missing)} in {a.src}")
        edit["dropped"] = sorted(drop)
        edit["dropped_traces"] = sum(t.icao in drop for t in traces)
        traces = [t for t in traces if t.icao not in drop]
    if a.end_utc:
        end = datetime.datetime.fromisoformat(a.end_utc.replace("Z", "+00:00")).timestamp()
        day = datetime.datetime.fromisoformat(Path(meta["archive_dir"]).name).replace(tzinfo=datetime.timezone.utc)
        kept = []
        for t in traces:
            keep = t.t <= end
            if keep.any():
                kept.append(dataclasses.replace(t, **{k: getattr(t, k)[keep] for k in ARRAYS
                                                      if getattr(t, k) is not None}))
        edit["ends_utc"] = a.end_utc
        meta["covered_utc"] = [day.timestamp(), end]
        traces = kept
    edit["traces_out"] = len(traces)
    meta["edited"] = edit
    save_traces(traces, a.out, metadata=meta)
    print(f"{a.src.name} -> {a.out}: {edit['traces_in']} traces in, {len(traces)} out; {edit}")


if __name__ == "__main__":
    main()
