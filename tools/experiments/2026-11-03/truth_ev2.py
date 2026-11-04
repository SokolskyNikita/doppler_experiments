"""Ground truth for the two Oyster Bay events at the known location.

Prints the CPA rows the pairing step sees for the two true flights, the true heard-time
offset, and, for each event, the best time shift and fundamental when the real trajectory's
curve is scored against the spectrogram over a wide f0 range. Then compares fitted events
(any JSON files given) with that truth. Usage: truth_ev2.py DATA_DIR [EV1 EV2 ...pairs]"""
import json
import sys

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.audio import Spectrogram
from dopplertrack.doppler import speed_of_sound
from dopplertrack.search import Grid, build_segments, cpa_table
from dopplertrack.score import EventWindow, modelled_curve
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

data = sys.argv[1]
TRUTH = (40.876466, -73.524951)
ICAO = ("a1dfeb", "ace391")
c = speed_of_sound()

sp = Spectrogram.load(f"{data}/rec.npz")
traces = load_traces(f"{data}/traces_ny.npz")
el = Terrain().elevation(np.array([TRUTH[0]]), np.array([TRUTH[1]]))
grid = Grid.points([TRUTH[0]], [TRUTH[1]], el)
r = 12000.0
segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(-r, r, -r, r))
cpa = cpa_table(grid, segs, max_range_m=r, c=c)
cpa["icao"] = [segs[s].icao for s in cpa.seg]
rows = {i: cpa[cpa.icao == i].sort_values("d").iloc[0] for i in ICAO}
for i in ICAO:
    x = rows[i]
    print(f"{i}: seg {int(x.seg)}, heard CPA {x.t_heard:.2f}, d {x.d:.0f} m, v {x.v:.1f} m/s")
dt_true = rows[ICAO[1]].t_heard - rows[ICAO[0]].t_heard
print(f"true heard offset {dt_true:.2f} s\n")

ref1 = EventFit(**json.load(open(f"{data}/ev1_docs.json")))
ref2 = EventFit(**json.load(open(f"{data}/ev2_docs.json")))
# audio = unix + t0_map; solve event 1's placement over shifts and a wide f0 range
seg1, seg2 = segs[int(rows[ICAO[0]].seg)], segs[int(rows[ICAO[1]].seg)]
scales = np.arange(0.85, 1.1501, 0.0025)
shifts = np.arange(-15, 15.01, 0.25)
w1 = EventWindow.from_fit(sp, ref1, 2)
t0_map = ref1.t_cpa - rows[ICAO[0]].t_heard
to1, r1 = modelled_curve(seg1, grid.enu[0], c)
sc1 = w1.sweep_scores(to1 + t0_map, r1, shifts, scales)
i, j = np.unravel_index(np.argmax(sc1), sc1.shape)
sh = shifts[i]
print(f"event 1 at truth: shift {sh:+.2f} s, f0 {ref1.f0 * scales[j]:.2f} Hz, score {sc1[i, j]:.2f}")
w2 = EventWindow.from_fit(sp, ref2, 1)
to2, r2 = modelled_curve(seg2, grid.enu[0], c)
sc2 = w2.sweep_scores(to2 + t0_map, r2, [sh], scales)[0]
k = int(np.argmax(sc2))
print(f"event 2 at truth (locked to event 1's clock): f0 {ref2.f0 * scales[k]:.2f} Hz, score {sc2[k]:.2f}")
# same, but letting event 2's own time shift float, to see whether geometry alone places it
sc2f = w2.sweep_scores(to2 + t0_map, r2, shifts, scales)
a, b = np.unravel_index(np.argmax(sc2f), sc2f.shape)
print(f"event 2 with its own shift free: shift {shifts[a]:+.2f} s, f0 {ref2.f0 * scales[b]:.2f} Hz, score {sc2f[a, b]:.2f}")
true_f0 = (ref1.f0 * scales[j], ref2.f0 * scales[k])

print("\nfit errors against truth (heard offset vs true; f0 vs trajectory-matched f0):")
args = sys.argv[2:]
for p in range(0, len(args), 2):
    e1 = EventFit(**json.load(open(args[p]))); e2 = EventFit(**json.load(open(args[p + 1])))
    print(f"  {args[p].split('/')[-1]} + {args[p + 1].split('/')[-1]}: offset {e2.t_cpa - e1.t_cpa:.2f} "
          f"(err {e2.t_cpa - e1.t_cpa - dt_true:+.2f} s); "
          f"ev1 f0 {e1.f0:.1f} v {e1.v:.0f} d {e1.d:.0f}; ev2 f0 {e2.f0:.1f} (x{e2.f0 / true_f0[1]:.3f}) v {e2.v:.0f} d {e2.d:.0f}")
