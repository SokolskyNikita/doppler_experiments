"""Which event time to pair on. At the true location of both development recordings: the true flights'
heard-CPA gap (CPA emission time + slant/c), emission-CPA gap, and the gap between the times their heard
curves fall fastest; then how far each saved pair of event fits is off under the heard convention
(t_cpa, what pair_candidates uses today) and the emission convention (t_cpa_emit).

Under a straight, constant-speed pass the heard curve falls fastest at the emission-CPA instant
(Ferguson & Lo 2000, eqs. 3-4), so t_cpa_emit should be compared with the CPA table's t_emit, and it
does not depend on the fitted distance. Run from the repo root:
    uv run python tools/experiments/2026-11-03/timing_conventions.py
"""
import json
import os

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.doppler import curve_from_trajectory, speed_of_sound
from dopplertrack.search import Grid, build_segments, cpa_table
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

DATA = os.environ.get("DOPPLERTRACK_DATA", os.path.expanduser("~/data/dopplertrack"))
ISSUE1 = f"{DATA}/runs/2026-11-03-issue-1"
REWIN = f"{DATA}/runs/2026-11-03-rewindow"
c = speed_of_sound()


def truth(traces_path, lat, lon, icaos, t_guess2_after):
    """CPA rows of the two flights at (lat, lon) and the heard time of each curve's steepest fall."""
    traces = load_traces(traces_path)
    grid = Grid.points([lat], [lon], Terrain().elevation(np.array([lat]), np.array([lon])))
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(-12000, 12000, -12000, 12000))
    cpa = cpa_table(grid, segs, max_range_m=12000, c=c)
    cpa["icao"] = [segs[s].icao for s in cpa.seg]
    r1 = cpa[cpa.icao == icaos[0]].sort_values("d").iloc[0]
    x = cpa[cpa.icao == icaos[1]]
    r2 = x.iloc[np.argmin(np.abs(x.t_heard.to_numpy() - (r1.t_heard + t_guess2_after)))]
    out = []
    for r in (r1, r2):
        s = segs[int(r.seg)]
        k = 5                                             # 5 s running mean of the 1 Hz track
        enu = np.vstack([np.convolve(s.enu[:, j], np.ones(k) / k, mode="same") for j in range(3)]).T
        to, ratio, _ = curve_from_trajectory(s.t[k:-k], enu[k:-k], grid.enu[0], f0=1.0, c=c)
        slope = np.where(np.abs(to - r.t_heard) < 120, np.gradient(ratio, to), np.inf)
        out.append(dict(icao=r.icao, d=float(r.d), v=float(r.v), t_emit=float(r.t_emit),
                        t_heard=float(r.t_heard), t_steep=float(to[int(np.argmin(slope))])))
    return out


def report(name, tr, fits):
    a, b = tr
    for x in tr:
        print(f"{name} {x['icao']}: d {x['d']:.0f} m, v {x['v']:.1f} m/s; heard CPA {x['t_heard'] - x['t_emit']:+.1f} s "
              f"and steepest fall {x['t_steep'] - x['t_emit']:+.1f} s after the emission CPA")
    gh, ge, gs = b["t_heard"] - a["t_heard"], b["t_emit"] - a["t_emit"], b["t_steep"] - a["t_steep"]
    print(f"{name} true gaps: heard {gh:.2f} s, emission {ge:.2f} s, steepest fall {gs:.2f} s")
    for label, (e1, e2) in fits.items():
        fh, fe = e2.t_cpa - e1.t_cpa, e2.t_cpa_emit - e1.t_cpa_emit
        print(f"  {label:11s} heard gap err {fh - gh:+6.1f} s   emission gap err {fe - ge:+6.1f} s   "
              f"emission gap vs steepest-fall gap {fe - gs:+6.1f} s   (d fits {e1.d:.0f}, {e2.d:.0f} m)")
    print()


def load(path):
    return EventFit(**json.load(open(path)))


oyster = truth(f"{DATA}/derived/oyster_bay/traces_ny.npz", 40.876466, -73.524951, ("a1dfeb", "ace391"), 923.0)
report("Oyster Bay", oyster, {
    "committed": (load(f"{ISSUE1}/ev1_docs.json"), load(f"{ISSUE1}/ev2_docs.json")),
    "contrast": (load(f"{ISSUE1}/ev1.json"), load(f"{ISSUE1}/ev2.json")),
    "detect": (load(f"{ISSUE1}/ev1_det.json"), load(f"{ISSUE1}/ev2_det.json")),
})

swfl = truth(f"{DATA}/derived/swfl/traces_swfl.npz", 26.702359, -81.847766, ("a2baea", "a336e4"), 338.0)
det = [EventFit(**d) for d in json.load(open("docs/results/swfl_detected.json"))]
fits = {"committed": (load(f"{ISSUE1}/swfl/ev1_docs.json"), load(f"{ISSUE1}/swfl/ev2_docs.json")),
        "detect": (det[4], det[12])}
for v in ("A-bright", "A-contrast", "B-bright", "B-contrast"):
    fits[v] = tuple(load(f"{REWIN}/swfl_{v}_ev{k}.json") for k in (1, 2))
report("Eagle cam", swfl, fits)
