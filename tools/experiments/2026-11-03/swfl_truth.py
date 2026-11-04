"""Eagle cam at the nest: the true flights' CPA rows (what the pairing step sees), and which search
filter each event-fit variant trips there (gap +-6 s, speed +-35 %, distance 0.4-2.5x)."""
import json
from pathlib import Path

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.doppler import speed_of_sound
from dopplertrack.search import Grid, build_segments, cpa_table
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

NEST = (26.702359, -81.847766)
ICAO = ("a2baea", "a336e4")
c = speed_of_sound()
traces = load_traces("data/swfl/traces_swfl.npz")
grid = Grid.points([NEST[0]], [NEST[1]], Terrain().elevation(np.array([NEST[0]]), np.array([NEST[1]])))
segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(-12000, 12000, -12000, 12000))
cpa = cpa_table(grid, segs, max_range_m=12000, c=c)
cpa["icao"] = [segs[s].icao for s in cpa.seg]
# the pass heard near the events' time (both flights may pass more than once in a day)
rows = []
for icao, t_audio in zip(ICAO, (20247.5, 20585.3)):
    x = cpa[cpa.icao == icao].copy()
    rows.append(x)
t_map = None
r1 = rows[0].sort_values("d").iloc[0]
r2 = rows[1].iloc[np.argmin(np.abs(rows[1].t_heard.to_numpy() - (r1.t_heard + 338.0)))]
gap = r2.t_heard - r1.t_heard
print(f"truth at the nest: {ICAO[0]} d {r1.d:.0f} v {r1.v:.1f}; {ICAO[1]} d {r2.d:.0f} v {r2.v:.1f}; heard gap {gap:.2f} s\n")


def check(label, e1, e2):
    g = e2.t_cpa - e1.t_cpa
    fails = []
    if abs(g - gap) > 6: fails.append(f"gap {g - gap:+.1f} s")
    for k, (e, r) in enumerate(((e1, r1), (e2, r2)), 1):
        if not (0.65 * e.v <= r.v <= 1.35 * e.v): fails.append(f"ev{k} speed (fit {e.v:.0f}, true {r.v:.0f})")
        if not (0.4 * e.d <= r.d <= 2.5 * e.d): fails.append(f"ev{k} distance (fit {e.d:.0f}, true {r.d:.0f})")
    print(f"{label:11s} ev1 v {e1.v:5.1f} d {e1.d:5.0f}  ev2 v {e2.v:5.1f} d {e2.d:5.0f}  gap err {g - gap:+6.1f}  -> {'; '.join(fails) or 'passes'}")


det = [EventFit(**d) for d in json.load(open("docs/results/swfl_detected.json"))]
check("detect", det[4], det[12])
for v in ("A-bright", "A-contrast", "B-bright", "B-contrast"):
    e1, e2 = (EventFit(**json.load(open(f"data/rewin/swfl_{v}_ev{k}.json"))) for k in (1, 2))
    check(v, e1, e2)
