"""Criterion (d) of the trace join: join each Eclipse site's 2024-04-07 and 2024-04-08 cuts and report every
seam near midnight. Structural only: no audio is read and nothing is searched.

usage: trace_join_check.py OUT_JSON SITE=DAY1.npz,DAY2.npz [...]"""
import json
import sys

import numpy as np

from dopplertrack.adsb import join_days, load_traces
from dopplertrack.search import build_segments

MIDNIGHT = 1712534400.0       # 2024-04-08 00:00 UTC
NEAR_S = 600.0                # a seam counts as near midnight if both sides lie within 10 min of it

out = {}
for arg in sys.argv[2:]:
    site, files = arg.split("=")
    paths = files.split(",")
    day1 = {t.icao: t for t in load_traces(paths[0])}
    day2 = {t.icao: t for t in load_traces(paths[1])}
    near = {k for k in set(day1) & set(day2)
            if day1[k].t[-1] > MIDNIGHT - NEAR_S and day2[k].t[0] < MIDNIGHT + NEAR_S}
    traces, meta = join_days(paths)
    seams = [s for s in meta["seams"] if s["icao"] in near]
    joined = {s["icao"] for s in seams if s["joined"]}
    by_icao = {}
    for t in traces:
        by_icao.setdefault(t.icao, []).append(t)
    increasing = all(np.all(np.diff(t.t) > 0) for k in joined for t in by_icao[k])
    lat0, lon0 = float(np.mean([t.lat[0] for t in traces])), float(np.mean([t.lon[0] for t in traces]))
    def crossing(trs):     # airborne segments spanning midnight
        return sum(1 for s in build_segments(trs, lat0, lon0) if s.t[0] < MIDNIGHT < s.t[-1])
    out[site] = {"files": paths, "traces_day1": len(day1), "traces_day2": len(day2), "traces_joined": len(traces),
                 "seams_near_midnight": seams, "joined": sorted(joined), "times_strictly_increasing": bool(increasing),
                 "segments_spanning_midnight": {"unjoined": crossing(list(day1.values()) + list(day2.values())),
                                                "joined": crossing(traces)},
                 "coverage_bbox": meta.get("coverage_bbox")}
    print(f"{site}: {len(seams)} seams near midnight, joined {sorted(joined)}; spanning midnight "
          f"{out[site]['segments_spanning_midnight']}; increasing {increasing}")
    for s in seams:
        print(f"   {s['icao']} gap {s['gap_s']:.1f} s, jump {s.get('jump_m')} m, climb {s.get('altitude_change_m')} m, "
              f"gs {s.get('ground_speed_m_s')} -> {'joined' if s['joined'] else 'split'} ({s['reason']})")
json.dump(out, open(sys.argv[1], "w"), indent=1)
