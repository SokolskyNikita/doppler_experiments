"""One pass over a local (possibly split) adsb.lol day tar, writing prop traces for several boxes.

Refuses to start if any output already exists, and writes each file under a temporary name before
renaming it into place, so an interrupted run never leaves a half-written box behind.

usage: extract_boxes.py [--max-range METRES] DAY_DIR OUT_DIR name=LATMIN,LATMAX,LONMIN,LONMAX [...]
Each box is padded by --max-range (default 0) the way fetch-day pads its --bbox, so a box given with
--max-range 12000 is the search box and one given without it is the envelope itself. Each npz carries
the same extraction metadata fetch-day writes (requested box, envelope, scan counts), which
`adsb.load_trace_metadata` reads back and `report_coverage` checks.
"""
import io
import os
import sys
import time
from pathlib import Path

from dopplertrack.adsb import AircraftTypes, in_bbox, save_traces
from dopplertrack.coverage import ScanReport, extraction_metadata, padded_bbox
from dopplertrack.fetch import iter_tar_traces


class Chained(io.RawIOBase):
    def __init__(self, paths):
        self.paths, self.i, self.f, self.total = list(paths), 0, None, 0

    def readable(self):
        return True

    def readinto(self, b):
        while self.i < len(self.paths):
            if self.f is None:
                self.f = open(self.paths[self.i], "rb")
            n = self.f.readinto(b)
            if n:
                self.total += n
                return n
            self.f.close(); self.f = None; self.i += 1
        return 0


args = sys.argv[1:]
max_range = 0.0
if args[:1] == ["--max-range"]:
    max_range, args = float(args[1]), args[2:]
day_dir, out_dir = Path(args[0]), Path(args[1])
boxes, envelopes = {}, {}
for arg in args[2:]:
    name, v = arg.split("=")
    boxes[name] = tuple(float(x) for x in v.split(","))
    envelopes[name] = tuple(float(x) for x in padded_bbox(boxes[name], max_range))
outs = [out_dir / f"{name}{suffix}.npz" for name in boxes for suffix in ("", "_all") if suffix == "" or os.environ.get("KEEP_ALL")]
if taken := [str(p) for p in outs if p.exists()]:
    sys.exit("refusing to overwrite: " + ", ".join(taken))


def publish(traces, path, metadata):
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp.npz")
    save_traces(traces, tmp, metadata=metadata)
    os.replace(tmp, path)


union = (min(b[0] for b in envelopes.values()), max(b[1] for b in envelopes.values()),
         min(b[2] for b in envelopes.values()), max(b[3] for b in envelopes.values()))
parts = sorted(p for p in day_dir.iterdir() if ".tar" in p.name)
t0 = time.time()
stream = Chained(parts)
prog = lambda n, _: print(f"  {n} traces scanned, {stream.total / 1e9:.2f} GB, {time.time() - t0:.0f} s", flush=True) if n % 20000 == 0 else None
scan = ScanReport()
hits = list(iter_tar_traces(io.BufferedReader(stream, 1 << 22), union, prog, report=scan))
types = AircraftTypes()
out_dir.mkdir(parents=True, exist_ok=True)
for name, b in boxes.items():
    tr = [t for t in hits if in_bbox(t, envelopes[name])]
    prop = [t for t in tr if types.is_prop(t.typ)]
    for traces, suffix in ((prop, ""), (tr, "_all")):
        if suffix and not os.environ.get("KEEP_ALL"):
            continue
        # the scan is shared; what lies outside this box's envelope counts as outside_bbox for it
        rep = ScanReport(seen=scan.seen, malformed=scan.malformed, empty=scan.empty,
                         outside_bbox=scan.seen - scan.malformed - scan.empty - len(tr),
                         excluded_types=len(tr) - len(traces), kept=len(traces))
        meta = extraction_metadata(b, max_range, rep, archive_dir=str(day_dir), archive_files=[p.name for p in parts])
        publish(traces, out_dir / f"{name}{suffix}.npz", meta)
    print(f"{name} {b} (envelope {envelopes[name]}): {len(tr)} traces, {len(prop)} prop -> {out_dir / (name + '.npz')}",
          flush=True)
print(f"done in {time.time() - t0:.0f} s", flush=True)
