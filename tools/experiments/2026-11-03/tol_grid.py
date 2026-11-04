"""Known-point check over a grid of (time tolerance, f0 sweep half-width) for several event sets.
Usage: tol_grid.py SPEC TRACES LAT LON NAME:EV1:EV2 [NAME:EV1:EV2 ...] [--h1 N]"""
import json
import sys

import numpy as np

from dopplertrack import pipeline
from dopplertrack.adsb import load_traces
from dopplertrack.audio import Spectrogram
from dopplertrack.search import Grid
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

args, h1 = [], 1
argv = iter(sys.argv[1:])
for a in argv:
    if a == "--h1":
        h1 = int(next(argv))
    elif a.startswith("--h1="):
        h1 = int(a.split("=", 1)[1])
    else:
        args.append(a)
spec, traces_p, lat, lon = args[0], args[1], float(args[2]), float(args[3])
sets = [s.split(":") for s in args[4:]]

pipeline.log = lambda *a, **k: None
sp = Spectrogram.load(spec)
traces = load_traces(traces_p)
el = Terrain().elevation(np.array([lat]), np.array([lon]))
grid = Grid.points([lat], [lon], el)
print(f"{'events':10s} {'tol s':>6s} {'f0 tol':>6s} {'triples':>7s} {'score':>6s} {'s1':>6s} {'s2':>6s}")
for name, p1, p2 in sets:
    ev1, ev2 = (EventFit(**json.load(open(p))) for p in (p1, p2))
    for tol in (6, 10, 12, 15):
        for ft in (0.05, 0.10, 0.12, 0.15):
            res, _ = pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=(h1, 1), tol_s=tol, f0_tol=ft, progress=False)
            if len(res):
                b = res.iloc[0]
                print(f"{name:10s} {tol:6.0f} {ft:6.2f} {len(res):7d} {b.score:6.2f} {b.s1:6.2f} {b.s2:6.2f}  {b.icao1}/{b.icao2}")
            else:
                print(f"{name:10s} {tol:6.0f} {ft:6.2f} {0:7d}")
