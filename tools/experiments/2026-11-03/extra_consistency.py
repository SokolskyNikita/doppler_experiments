"""Does adding further detected flyovers separate the true flight pair from wrong ones?

For each of the top flight pairs from a finished search, place the observer at that pair's best
point, then for every extra detected event ask which flight that observer would hear at that
time (pipeline.pick_flight) and how well its modelled curve scores. Also prints simple per-query
statistics of the per-pair maxima. Usage: extra_consistency.py DATA_DIR [TOP_PAIRS]"""
import json
import sys

import numpy as np
import pandas as pd

from dopplertrack import pipeline
from dopplertrack.adsb import load_traces
from dopplertrack.audio import Spectrogram
from dopplertrack.geo import lla_to_enu
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit
from dopplertrack.doppler import cpa_from_trajectory, speed_of_sound
from dopplertrack.score import EventWindow, modelled_curve

data = sys.argv[1]
top = int(sys.argv[2]) if len(sys.argv) > 2 else 8
TOL = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
bbox = (40.4, 41.3, -74.4, -72.6)
truth = ("a1dfeb", "ace391")

sp = Spectrogram.load(f"{data}/rec.npz")
ev1 = EventFit(**json.load(open(f"{data}/ev1_docs.json")))
ev2 = EventFit(**json.load(open(f"{data}/ev2_docs.json")))
detected = [EventFit(**d) for d in json.load(open(f"{data}/detected.json"))]
# extras: every detected event that is not one of the two search events
extra = [e for e in detected if min(abs(e.t_cpa - ev1.t_cpa), abs(e.t_cpa - ev2.t_cpa)) > 60]

res = pd.read_csv(f"{data}/results.csv")
best = res.sort_values("score", ascending=False).drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
s = best.score.to_numpy()
mad = np.median(np.abs(s - np.median(s)))
print(f"{len(best)} pairs; best {s[0]:.2f}, 2nd {s[1]:.2f}, median {np.median(s):.2f}, "
      f"robust z of best {(s[0] - np.median(s)) / (1.4826 * mad):.1f}, of 2nd {(s[1] - np.median(s)) / (1.4826 * mad):.1f}")
print(f"extra events at {[round(e.t_cpa) for e in extra]} s\n")

traces = load_traces(f"{data}/traces_ny.npz")
elev = Terrain().elevation
segs = pipeline.segments_for_search(traces, bbox, float(best.lat0[0]), float(best.lon0[0]))
rows = []
for r in range(min(top, len(best))):
    row = pipeline.relocate_row(best.iloc[r], segs, ev2.t_cpa - ev1.t_cpa)
    el0 = float(elev(np.array([row.lat]), np.array([row.lon]))[0])
    obs0 = lla_to_enu(row.lat, row.lon, el0, row.lat0, row.lon0)
    t0_map = ev1.t_cpa - float(row.t_heard1)
    scores = []
    for ev in extra:
        k, sc = pipeline.pick_flight(sp, ev, segs, obs0, t0_map, float(row["shift"]))
        scores.append(sc if k >= 0 else 0.0)
    scores = np.array(scores)
    # strict: only flights whose heard CPA at this observer falls within TOL s of the event,
    # optionally also within the search's speed / distance ranges for that event
    strict_t, strict_g = [], []
    for ev in extra:
        w = EventWindow.from_fit(sp, ev, 1)
        bt, bg = 0.0, 0.0
        for seg in segs:
            if np.linalg.norm(seg.enu - obs0, axis=1).min() > 12000:
                continue
            _, t_heard, d, v = cpa_from_trajectory(seg.t, seg.enu, obs0)
            if abs(t_heard + t0_map - ev.t_cpa) > TOL:
                continue
            to, rr = modelled_curve(seg, obs0, speed_of_sound())
            sc = float(w.sweep_scores(to + t0_map, rr, [float(row["shift"])], np.arange(0.95, 1.0501, 0.005)).max())
            bt = max(bt, sc)
            if 0.65 * ev.v <= v <= 1.35 * ev.v and 0.4 * ev.d <= d <= 2.5 * ev.d:
                bg = max(bg, sc)
        strict_t.append(bt); strict_g.append(bg)
    strict_t, strict_g = np.array(strict_t), np.array(strict_g)
    tag = "TRUE" if (row.icao1, row.icao2) == truth else ""
    rows.append((r + 1, f"{row.icao1}/{row.icao2}", tag, round(row.score, 2), round(scores.sum(), 2),
                 round(strict_t.sum(), 2), int((strict_t >= 3.0).sum()), round(strict_g.sum(), 2), int((strict_g >= 3.0).sum()),
                 " ".join(f"{x:.1f}" for x in strict_t)))
print(f"TOL = {TOL} s")
print(pd.DataFrame(rows, columns=["rank", "pair", "", "pair", "naive", "time-gated", "n>=3", "time+geom", "n>=3",
                                  "time-gated per extra"]).to_string(index=False))
