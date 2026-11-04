"""Count prop-aircraft passes near each Eclipse Soundscapes site in one adsb.lol day tar.

usage: site_traffic.py DAY_DIR SITES_CSV OUT_CSV
A pass = one airborne segment of a prop (or unknown-type) aircraft whose 3-D slant distance to the
site drops below 12 km (counted also at 6 km), below 4 km MSL. Site elevation is taken as 0.
"""
import csv
import io
import sys
import time
from pathlib import Path

import numpy as np

from dopplertrack.adsb import AircraftTypes
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


day_dir, sites_csv, out_csv = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sites = [r for r in csv.DictReader(open(sites_csv)) if r["lat"] and r["lon"]]
slat = np.array([float(r["lat"]) for r in sites]); slon = np.array([float(r["lon"]) for r in sites])
bbox = (slat.min() - 0.2, slat.max() + 0.2, slon.min() - 0.3, slon.max() + 0.3)
n12 = np.zeros(len(sites), int); n6 = np.zeros(len(sites), int); nearest = np.full(len(sites), np.inf)
types = AircraftTypes()
R = 6371e3
t0 = time.time()
stream = Chained(sorted(p for p in day_dir.iterdir() if ".tar" in p.name))
for k, tr in enumerate(iter_tar_traces(io.BufferedReader(stream, 1 << 22), bbox)):
    if not types.is_prop(tr.typ):
        continue
    for sl in tr.segments():
        la, lo, al = tr.lat[sl], tr.lon[sl], tr.alt[sl]
        ok = np.isfinite(al) & (al < 4000)
        if not ok.any():
            continue
        la, lo, al = la[ok], lo[ok], al[ok]
        near = (np.abs(slat[:, None] - la[None]) < 0.15).any(1)
        for i in np.where(near)[0]:
            dn = np.radians(la - slat[i]) * R
            de = np.radians(lo - slon[i]) * R * np.cos(np.radians(slat[i]))
            d = np.sqrt(dn ** 2 + de ** 2 + al ** 2).min()
            nearest[i] = min(nearest[i], d)
            n12[i] += d < 12000; n6[i] += d < 6000
    if k % 2000 == 0:
        print(f"  {k} region traces, {stream.total / 1e9:.2f} GB, {time.time() - t0:.0f} s", flush=True)
with open(out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "title", "lat", "lon", "time_setting", "passes_12km", "passes_6km", "nearest_m", "zips"])
    for i, r in enumerate(sites):
        w.writerow([r["id"], r["title"], r["lat"], r["lon"], r["time_setting"], n12[i], n6[i],
                    round(nearest[i]) if np.isfinite(nearest[i]) else "", r["zips"]])
print(f"done in {time.time() - t0:.0f} s -> {out_csv}", flush=True)
