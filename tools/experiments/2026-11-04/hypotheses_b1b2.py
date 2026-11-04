"""PLAN Phase 2 item 7, stage B: B1 and B2 on the positive seed cases.

For each case and event: the event's null (pipeline.event_null), its hypotheses (hypotheses.event_hypotheses),
the CPA rows they admit against those today's speed and distance gates admit (B2), and whether the true flight's
pass is admitted at a grid point within 250 m of the reference (B1), and by which source.

The true pass of each true flight is its segment whose heard time, at the grid point nearest the reference, pairs
with the other true flight's at the trajectories' true heard gap (closest within 60 s).

Cases (docs/experiments/2026-11-04-hypotheses.md): oyster-bay and oyster-bay-hp150-aac32k at raw-audio, the top two
of detect's output in the raw-audio baseline at 5314396 by score, earlier first; eagle-cam-clip-18000s with its
committed fits (detect's full-stream ranks 5 and 13, shifted by the clip's -18,000 s), as item 1's ruling set it.

usage: hypotheses_b1b2.py [RUN] [--detected DETECTED_RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
Each case is a unit (tools/data/shards.py); workers come from $DOPPLERTRACK_JOBS."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "data"))
import shards                                                            # noqa: E402
from bench import cases as bench_cases                                   # noqa: E402
from dopplertrack import hypotheses as H, search                         # noqa: E402
from dopplertrack.adsb import load_traces                                # noqa: E402
from dopplertrack.audio import Spectrogram                               # noqa: E402
from dopplertrack.cache import cache_root                                # noqa: E402
from dopplertrack.doppler import speed_of_sound                          # noqa: E402
from dopplertrack.parallel import default_jobs                           # noqa: E402
from dopplertrack.pipeline import event_null                             # noqa: E402
from dopplertrack.score import EventWindow                               # noqa: E402
from dopplertrack.terrain import Terrain                                 # noqa: E402
from dopplertrack.tracks import EventFit                                 # noqa: E402

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
BASELINE = DATA / "runs/2026-11-04-bench-5314396-raw-audio-t2"
TRUE_GAP = {"oyster-bay": 922.96, "oyster-bay-hp150-aac32k": 922.96, "eagle-cam-clip-18000s": 331.61}
NEAR_M = 250.0


def events_for(case: dict, cid: str, baseline: Path) -> list[EventFit]:
    if cid == "eagle-cam-clip-18000s":
        det = json.loads((REPO / "docs/results/swfl_detected.json").read_text())
        off = case["events"]["time_offset_s"]
        evs = []
        for r in case["events"]["pick"]:
            e = dict(det[r - 1])
            for k in ("t_cpa", "t_cpa_emit", "t_start", "t_end"):
                e[k] += off
            evs.append(EventFit(**e))
    else:
        det = json.loads((baseline / cid / "detected.json").read_text())
        evs = [EventFit(**{k: v for k, v in d.items() if k in EventFit.__dataclass_fields__})
               for d in sorted(det, key=lambda d: d["score"], reverse=True)[:2]]
    return sorted(evs, key=lambda e: e.t_cpa)


def one_case(cid: str, baseline: Path, jobs: int) -> dict:
    doc = bench_cases.load_cases()
    t0 = time.perf_counter()
    case = next(c for c in doc["cases"] if c["id"] == cid)
    s, lab = case["search"], bench_cases.case_labels(cid, case["version"])
    c = speed_of_sound()
    sp = Spectrogram.load(DATA / case["spectrogram"])
    grid = search.Grid.make(*s["bbox"], s["spacing_m"], Terrain().elevation if s["dem"] else None)
    traces = load_traces(DATA / case["flight_data"]["traces"])
    r = s["max_range_m"]
    clip = (grid.enu[:, 0].min() - r, grid.enu[:, 0].max() + r, grid.enu[:, 1].min() - r, grid.enu[:, 1].max() + r)
    segs = search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip)
    cpa = search.load_cpa_table(cache_root() / s["cpa_cache"], search.cpa_fingerprint(grid, segs, r, c))
    built = cpa is None
    if built:
        cpa = search.cpa_table(grid, segs, r, c, workers=jobs)
    icao = np.array([sg.icao for sg in segs])
    ref = lab["reference"]
    dist = np.hypot((grid.lat - ref["lat"]) * 111320.0, (grid.lon - ref["lon"]) * 111320.0 * np.cos(np.radians(ref["lat"])))
    near_pts = np.flatnonzero(dist <= NEAR_M)
    nearest = int(np.argmin(dist))
    true = list(lab["true_pair"])
    # the true passes: the two true flights' segments whose heard gap at the nearest point is closest to the true gap
    at = cpa[cpa.gidx == nearest]
    r1, r2 = at[icao[at.seg.to_numpy()] == true[0]], at[icao[at.seg.to_numpy()] == true[1]]
    best = min(((abs(b.t_heard - a.t_heard - TRUE_GAP[cid]), int(a.seg), int(b.seg))
                for a in r1.itertuples() for b in r2.itertuples()), default=None)
    true_segs = [best[1], best[2]] if best and best[0] <= 60 else None
    evs = events_for(case, cid, baseline)
    harmonics = s.get("harmonics", [1, 1]) if cid == "eagle-cam-clip-18000s" else [1, 1]
    res = {"events": [e.to_dict() for e in evs], "true_pair": true, "true_segments": true_segs,
           "true_gap_error_s": best[0] if best else None, "cpa_built_in_memory": built}
    for k, (ev, h) in enumerate(zip(evs, harmonics), 1):
        a0 = time.perf_counter()
        w = EventWindow.from_fit(sp, ev, h)
        null = event_null(w, cpa, segs, grid.enu, c, workers=jobs)
        hyps = H.event_hypotheses(sp, w, ev, c, null["sigma"], h, v_tol=s["v_tol"], d_tol=tuple(s["d_tol"]))
        adm = H.admitted(cpa, hyps)
        v_tol, (dlo, dhi) = s["v_tol"], s["d_tol"]
        today = (cpa.v.between(ev.v * (1 - v_tol), ev.v * (1 + v_tol)) & cpa.d.between(ev.d * dlo, ev.d * dhi)).to_numpy()
        ev_res = {"null": null, "hypotheses": [h_.to_dict() for h_ in hyps], "admitted_rows": int(adm.sum()),
                  "today_gate_rows": int(today.sum()), "B2": bool(adm.sum() <= today.sum()), "seconds": time.perf_counter() - a0}
        if true_segs is not None:
            rows = cpa[(cpa.seg == true_segs[k - 1]).to_numpy() & np.isin(cpa.gidx.to_numpy(), near_pts)]
            ev_res["true_rows_near"] = len(rows)
            by = [[i for i, h_ in enumerate(hyps) if h_.admits(rows.iloc[[j]])[0]] for j in range(len(rows))]
            ev_res["B1"] = bool(any(by))
            ev_res["admitted_by_sources"] = sorted({src for b in by for i in b for src in hyps[i].sources})
            ev_res["today_gates_admit_true"] = bool(np.any(today[rows.index.to_numpy()]))
            tr = rows.iloc[0] if len(rows) else None
            ev_res["true_row_example"] = None if tr is None else {"v": float(tr.v), "d": float(tr.d), "k": float(tr.v) ** 2 / float(tr.d)}
        res[f"event{k}"] = ev_res
        print(cid, f"event {k}: {len(hyps)} hypotheses {[h_.sources for h_ in hyps]}, admitted {int(adm.sum())} vs today "
              f"{int(today.sum())}, B1 {ev_res.get('B1')} via {ev_res.get('admitted_by_sources')}", flush=True)
    res["seconds"] = time.perf_counter() - t0
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--detected", type=Path, default=BASELINE, help="the raw-audio run whose top two are judged")
    a = ap.parse_args()
    raw = [c for c in TRUE_GAP if c != "eagle-cam-clip-18000s"]
    if a.inputs:
        doc = bench_cases.load_cases()
        caches = sorted({next(c for c in doc["cases"] if c["id"] == cid)["search"]["cpa_cache"] for cid in TRUE_GAP})
        shards.print_inputs(list(TRUE_GAP), [str((a.detected / c / "detected.json").resolve().relative_to(DATA.resolve()))
                                             for c in raw], caches)
        return
    params = {"cases": list(TRUE_GAP), "near_m": NEAR_M,
              "detected": {c: hashlib.sha256((a.detected / c / "detected.json").read_bytes()).hexdigest() for c in raw}}
    run = shards.open_run(a.run, "hypotheses-b1b2", {"script": "tools/experiments/2026-11-04/hypotheses_b1b2.py",
                                                    "detected": str(a.detected), "params": params,
                                                    "invocation": {"shard": "%d/%d" % a.shard,
                                                                   "resume": [str(r) for r in a.resume], "merge": a.merge}})
    units = shards.Units(run, list(TRUE_GAP), params, a.shard, a.resume)
    if not a.merge:
        jobs = default_jobs()
        for cid in units.todo():
            res = one_case(cid, a.detected, jobs)
            units.dir(cid).mkdir(parents=True, exist_ok=True)
            (units.dir(cid) / "case.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
            units.finish(cid, {"seconds": round(res["seconds"]), "jobs": jobs})
    try:
        folders = units.all()
    except SystemExit as e:
        if a.merge:
            raise
        print(f"this shard is done; not merging yet: {e}", flush=True)
        return
    out = {cid: json.loads((folders[cid] / "case.json").read_text()) for cid in TRUE_GAP}
    (run / "b1b2.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    summary = {cid: {"B1": all(r.get(f"event{k}", {}).get("B1") for k in (1, 2)),
                     "B2": all(r[f"event{k}"]["B2"] for k in (1, 2))} for cid, r in out.items()}
    summary["met"] = all(v["B1"] and v["B2"] for v in summary.values() if isinstance(v, dict))
    (run / "b1b2_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
