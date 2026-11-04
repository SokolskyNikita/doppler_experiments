"""Part 3's completeness check for the adsbfetch comparison: every flight in our adsb.lol cut whose heard CPA
at the case's reference point falls inside the recording, within 12 km, must be in the windowed mirror
set. One missing is the one way the windowed set could change a search's rank.

usage: uv run python tools/experiments/2026-11-04/adsbfetch_completeness.py "$RUN"
"""
import json
import sys
from pathlib import Path

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.doppler import speed_of_sound
from dopplertrack.search import Grid, build_segments, cpa_table
from dopplertrack.terrain import Terrain

DATA = Path.home() / "data" / "dopplertrack"
# case reference point, audio zero (the cases' reference_clock_utc) and recording length
CASES = {"ny": ("oyster-bay", DATA / "derived/oyster_bay/traces_ny.npz", (40.876466, -73.524951), 1788898650.72, 3600.0),
         "swfl": ("eagle-cam-clip-18000s", DATA / "derived/swfl/traces_swfl.npz", (26.702359, -81.847766), 1735413673.29, 5400.0)}


def heard(traces_path, point, t0, length):
    traces = load_traces(traces_path)
    grid = Grid.points([point[0]], [point[1]], Terrain().elevation(np.array([point[0]]), np.array([point[1]])))
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(-12000, 12000, -12000, 12000))
    cpa = cpa_table(grid, segs, max_range_m=12000, c=speed_of_sound())
    cpa["icao"] = [segs[s].icao for s in cpa.seg]
    x = cpa[(cpa.t_heard >= t0) & (cpa.t_heard <= t0 + length) & (cpa.d <= 12000)]
    return {(r.icao, round(float(r.t_heard), 1), round(float(r.d))) for r in x.itertuples()}


def main(run: Path):
    out = {}
    for site, (case, cut, point, t0, length) in CASES.items():
        window = {h.strip().lstrip("~") for h in open(run / f"window_{site}.txt") if h.strip()}
        ours = heard(cut, point, t0, length)
        mirror = heard(run / f"{site}_mirror_union.npz", point, t0, length)
        missing = sorted(r for r in ours if r[0].lstrip("~") not in window)
        not_in_union = sorted(r for r in ours if r[0] not in {m[0] for m in mirror})
        extra = sorted(r for r in mirror if r[0] not in {o[0] for o in ours})
        out[site] = dict(case=case, cut_flights_heard=len(ours), mirror_flights_heard=len(mirror),
                         missing_from_window=[list(r) for r in missing], cut_heard_not_in_union=[list(r) for r in not_in_union],
                         union_heard_not_in_cut=[list(r) for r in extra])
        print(site, json.dumps({k: (v if not isinstance(v, list) or len(v) < 12 else f"{len(v)} rows") for k, v in out[site].items()}), flush=True)
    json.dump(out, open(run / "completeness.json", "w"), indent=1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
