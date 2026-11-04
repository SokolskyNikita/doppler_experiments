"""PLAN Phase 2 item 1, development pass: on one benchmark case and one pair of events, the triples
reaching scoring and whether the true flight pair is among them, under today's heard gate and under
every (emission gate G_e, steepest-fall tolerance T_sf) on the pre-declared grid. Nothing is scored,
so the clock anchor (which changes scores, not survival) isn't part of this table.

The emission gate is applied once at the widest G_e: a narrower gate keeps a subset of its triples,
and the silence filter acts on each triple alone. Each triple's two modelled steepest falls are
computed once, with the same estimator run_search uses. The true pair counts as surviving if its two
flights form a surviving triple anywhere in the box, as the runner counts it.

It also records, at the grid point nearest the reference, each true flight's modelled steepest fall
minus its CPA table t_emit (the PLAN item's measurement bullet).

usage: python timing_grid.py --case ID --events EVENTS.json [--pick R1 R2] --cpa TABLE.npz --out OUT.json
       [--jobs N]
EVENTS.json is a list of EventFit dicts (a detect output, or a runner record's events); --pick takes
two 1-based ranks from it (default: the first two). The CPA table is only read; if its fingerprint
doesn't match, the table is built in memory and not saved."""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

from dopplertrack import search
from dopplertrack.adsb import load_traces
from dopplertrack.doppler import speed_of_sound
from dopplertrack.parallel import ordered_map
from dopplertrack.pipeline import fitted_steepest_fall
from dopplertrack.score import SF_FLAT_RATIO, modelled_curve, steepest_fall
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit

REPO = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
G_E = (8.0, 12.0, 16.0, 20.0)
T_SF = (2.0, 3.0, 4.0, 6.0)
SF = dict(window_s=60.0, smooth_s=3.0, flat_ratio=SF_FLAT_RATIO)
_STATE: dict = {}


def _init(segs, c):
    _STATE.update(segs=segs, c=c)


def _falls(task):
    obs, s1, s2, te1, te2 = task
    out = []
    for o, a, b, t1, t2 in zip(obs, s1, s2, te1, te2):
        m = [steepest_fall(*modelled_curve(_STATE["segs"][int(k)], o, _STATE["c"]), float(t), **SF)
             for k, t in ((a, t1), (b, t2))]
        out.append(np.nan if None in m else m[1] - m[0])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True); ap.add_argument("--events", required=True)
    ap.add_argument("--pick", nargs=2, type=int); ap.add_argument("--cpa", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    case = next(c for c in json.loads((REPO / "bench/cases.json").read_text())["cases"] if c["id"] == a.case)
    s, lab = case["search"], case["labels"]
    evs = json.loads(Path(a.events).read_text())
    picks = [p - 1 for p in (a.pick or (1, 2))]
    ev1, ev2 = sorted((EventFit(**{k: evs[p][k] for k in EventFit.__dataclass_fields__}) for p in picks),
                      key=lambda e: e.t_cpa)
    c = speed_of_sound()
    t0 = time.perf_counter()
    grid = search.Grid.make(*s["bbox"], s["spacing_m"], Terrain().elevation if s["dem"] else None)
    traces = load_traces(DATA / case["flight_data"]["traces"])
    r = s["max_range_m"]
    clip = (grid.enu[:, 0].min() - r, grid.enu[:, 0].max() + r, grid.enu[:, 1].min() - r, grid.enu[:, 1].max() + r)
    segs = search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip)
    cpa = search.load_cpa_table(a.cpa, search.cpa_fingerprint(grid, segs, r, c))
    built = cpa is None
    if built:
        cpa = search.cpa_table(grid, segs, r, c, workers=a.jobs)
    icao = np.array([sg.icao for sg in segs])
    true = tuple(lab["true_pair"])
    gates = dict(v1=(ev1.v * (1 - s["v_tol"]), ev1.v * (1 + s["v_tol"])), d1=(ev1.d * s["d_tol"][0], ev1.d * s["d_tol"][1]),
                 v2=(ev2.v * (1 - s["v_tol"]), ev2.v * (1 + s["v_tol"])), d2=(ev2.d * s["d_tol"][0], ev2.d * s["d_tol"][1]),
                 silence_d_m=s["silence_d_m"])

    def survives(p):
        return bool(np.any((icao[p.seg1.to_numpy()] == true[0]) & (icao[p.seg2.to_numpy()] == true[1])))

    fh: dict = {}
    heard = search.pair_candidates(cpa, ev2.t_cpa - ev1.t_cpa, tol_s=s["tol_s"], funnel=fh, **gates)
    fe: dict = {}
    dt_emit = ev2.t_cpa_emit - ev1.t_cpa_emit
    em = search.pair_candidates(cpa, dt_emit, tol_s=max(G_E), funnel=fe, time_col="t_emit", **gates)
    cols = [em[k].to_numpy() for k in ("gidx", "seg1", "seg2", "t_emit1", "t_emit2")]
    used = np.union1d(cols[1], cols[2])
    tasks = [(grid.enu[cols[0][i:i + 500]], *(x[i:i + 500] for x in cols[1:])) for i in range(0, len(em), 500)]
    dm = np.array([x for part in ordered_map(_falls, tasks, a.jobs, _init, ({int(k): segs[k] for k in used}, c))
                   for x in part], float)
    f1, f2 = (fitted_steepest_fall(e, c, **SF) for e in (ev1, ev2))
    df = np.nan if f1 is None or f2 is None else f2 - f1
    gap_err = np.abs((em.t_emit2 - em.t_emit1).to_numpy() - dt_emit)
    unplaceable = ~np.isfinite(dm) | (not np.isfinite(df))
    rows = []
    for g in G_E:
        in_gate = gap_err <= g
        for t in (None, *T_SF):
            keep = in_gate if t is None else in_gate & (unplaceable | (np.abs(dm - df) <= t))
            rows.append({"G_e": g, "T_sf": t, "reaching_scoring": int(keep.sum()), "unplaceable": int((keep & unplaceable).sum()),
                         "true_pair_survives": survives(em[keep]), "flight_pairs": len(set(zip(icao[cols[1][keep]], icao[cols[2][keep]])))})
    # the measurement bullet: true flights at the grid point nearest the reference
    ref = lab["reference"]
    near = int(np.argmin((grid.lat - ref["lat"]) ** 2 + ((grid.lon - ref["lon"]) * np.cos(np.radians(ref["lat"]))) ** 2))
    meas = []
    for p in (em, heard):
        hit = p[(p.gidx == near) & (icao[p.seg1.to_numpy()] == true[0]) & (icao[p.seg2.to_numpy()] == true[1])]
        if len(hit):
            h = hit.iloc[0]
            for k in (1, 2):
                sg = segs[int(h[f"seg{k}"])]
                m = steepest_fall(*modelled_curve(sg, grid.enu[near], c), float(h[f"t_emit{k}"]), **SF)
                meas.append({"flight": sg.icao, "t_emit": float(h[f"t_emit{k}"]), "d_m": float(h[f"d{k}"]),
                             "steepest_fall_minus_t_emit_s": None if m is None else m - float(h[f"t_emit{k}"])})
            break
    out = {"case": a.case, "events": a.events, "pick": a.pick, "event_fits": [ev1.to_dict(), ev2.to_dict()],
           "true_pair": true, "cpa_table": a.cpa, "cpa_built_in_memory": built, "sf_knobs": SF,
           "fitted_steepest_fall_gap_s": None if not np.isfinite(df) else float(df), "fitted_emission_gap_s": dt_emit,
           "heard_gate": {"tol_s": s["tol_s"], **fh, "true_pair_survives": survives(heard)},
           "emission_widest": fe, "grid": rows, "true_flights_at_reference": meas,
           "wall_s": round(time.perf_counter() - t0, 1)}
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("case", "heard_gate", "fitted_steepest_fall_gap_s", "true_flights_at_reference", "wall_s")}, indent=1))
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
