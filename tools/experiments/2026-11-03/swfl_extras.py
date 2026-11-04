"""Which committed detect candidates were the README's three extra eagle-cam flyovers?
Recompute each candidate's extra-event score at the committed refined peak, the way refine does,
and compare with s3..s5 of docs/results/swfl_refined_50m.csv (6.43, 3.81, 2.82)."""
import json

import numpy as np
import pandas as pd

from dopplertrack import pipeline
from dopplertrack.adsb import load_traces
from dopplertrack.audio import Spectrogram
from dopplertrack.geo import lla_to_enu
from dopplertrack.score import EventWindow, f0_sweep, modelled_curve
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

pipeline.log = lambda *a, **k: None
BBOX = (26.1, 27.3, -82.5, -81.2)
sp = Spectrogram.load("data/swfl/rec.npz")
traces = load_traces("data/swfl/traces_swfl.npz")
det = [EventFit(**d) for d in json.load(open("docs/results/swfl_detected.json"))]
ev1, ev2 = det[4], det[12]
best = pd.read_csv("docs/results/swfl_search_best_per_pair.csv").iloc[0]
peak = pd.read_csv("docs/results/swfl_refined_50m.csv").iloc[0]
segs = pipeline.segments_for_search(traces, BBOX, float(best.lat0), float(best.lon0))
row = pipeline.relocate_row(best, segs, ev2.t_cpa - ev1.t_cpa)
elev = Terrain().elevation
c = 340.29

el0 = float(elev(np.array([row.lat]), np.array([row.lon]))[0])
obs0 = lla_to_enu(row.lat, row.lon, el0, row.lat0, row.lon0)
t0_map0 = ev1.t_cpa - float(row.t_heard1)
elp = float(elev(np.array([peak.lat]), np.array([peak.lon]))[0])
obsp = lla_to_enu(peak.lat, peak.lon, elp, row.lat0, row.lon0)
seg1 = segs[int(row.seg1)]
d = np.linalg.norm(seg1.enu - obsp, axis=1); j = int(np.argmin(d))
t0_map_p = ev1.t_cpa - float(seg1.t[j] + d[j] / pipeline.speed_of_sound())
print(f"rank-1 row {row.icao1}/{row.icao2} at {row.lat:.5f},{row.lon:.5f}; peak shift {peak['shift']}")
for i, ev in enumerate(det):
    if i in (4, 12):
        continue
    k, sc = pipeline.pick_flight(sp, ev, segs, obs0, t0_map0, float(row["shift"]))
    if k < 0:
        continue
    to, r = modelled_curve(segs[k], obsp, pipeline.speed_of_sound())
    s_peak = float(EventWindow.from_fit(sp, ev, 1).sweep_scores(to + t0_map_p, r, [float(peak["shift"])], f0_sweep()).max())
    flag = " <--" if min(abs(s_peak - x) for x in (6.4307, 3.8071, 2.8224)) < 0.02 else ""
    print(f"#{i + 1:2d} t {ev.t_cpa:8.1f} -> {segs[k].icao} score at candidate {sc:.2f}, at peak {s_peak:.4f}{flag}")
