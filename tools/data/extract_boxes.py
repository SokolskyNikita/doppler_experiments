"""One pass over a local (possibly split) adsb.lol day tar, writing prop traces for several boxes.

usage: extract_boxes.py DAY_DIR OUT_DIR name=LATMIN,LATMAX,LONMIN,LONMAX [...]
"""
import io
import os
import sys
import time
from pathlib import Path

from dopplertrack.adsb import AircraftTypes, in_bbox, save_traces
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


day_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
boxes = {}
for arg in sys.argv[3:]:
    name, v = arg.split("=")
    boxes[name] = tuple(float(x) for x in v.split(","))
union = (min(b[0] for b in boxes.values()), max(b[1] for b in boxes.values()),
         min(b[2] for b in boxes.values()), max(b[3] for b in boxes.values()))
parts = sorted(p for p in day_dir.iterdir() if ".tar" in p.name)
t0 = time.time()
stream = Chained(parts)
prog = lambda n, _: print(f"  {n} traces scanned, {stream.total / 1e9:.2f} GB, {time.time() - t0:.0f} s", flush=True) if n % 20000 == 0 else None
hits = list(iter_tar_traces(io.BufferedReader(stream, 1 << 22), union, prog))
types = AircraftTypes()
out_dir.mkdir(parents=True, exist_ok=True)
for name, b in boxes.items():
    tr = [t for t in hits if in_bbox(t, b)]
    prop = [t for t in tr if types.is_prop(t.typ)]
    save_traces(prop, out_dir / f"{name}.npz")
    if os.environ.get("KEEP_ALL"):
        save_traces(tr, out_dir / f"{name}_all.npz")
    print(f"{name} {b}: {len(tr)} traces, {len(prop)} prop -> {out_dir / (name + '.npz')}", flush=True)
print(f"done in {time.time() - t0:.0f} s", flush=True)
