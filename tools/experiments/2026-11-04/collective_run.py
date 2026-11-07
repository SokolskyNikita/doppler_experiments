"""The collective find on the development cases (docs/experiments/designs/2026-11-04-collective-find.md; criteria and design
steps in docs/experiments/2026-11-04-collective-find.md, written before each run): locate's detection (60-300 Hz,
harmonics 1, top 10, 240 s windows) on the case's spectrogram, its usable windows as collective.Window (bounds, coarse
tone, coarse heard CPA only), then collective.collective_find over the case's box with its flight data, 15 C, the
weather off, each candidate's tone over +-25 %. The result is written before any label is read.

The second design step runs in two stages, each a shards.py job:
- the coarse stage, one unit per case ("<case>--cell0"): the whole coarse map, the margin rule's kept cells, and the
  fine stage in the highest kept cell, which times one cell;
- the fine stage (--fine-from KEPT.json, {case: kept cells}): "<case>--cell<k>" for the other kept cells. Every unit
  repeats the deterministic coarse stage, so the cells' fine results combine by maximum at the merge.
The merge reports each case's best cell, judged, and the true cell's rank in the coarse map.

With --null, the units are A's other-day draws instead (verdict_null_days.json, and verdict_null_days-essex.json less
its five days without a release): "<case>--null--<day>" runs the same find, under the same rule (each candidate's
tone over +-25 %, every kept cell), with the case's box swapped to that day's cut of the same box, and writes null_draws.npz for
collective_null.py (day, max_S = the winner's Z, second_S = the best mode 2 km or more from it, lat, lon, n_matched,
clock_audio_minus_utc_s).

usage: uv run python tools/experiments/2026-11-04/collective_run.py [RUN] [--null [--null-cases C,...] | --fine-from KEPT.json] [--shard K/N] [--resume DIR ...] [--merge [--extra-units DIR ...]] [--inputs]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, runner  # noqa: E402

POSITIVES = ["oyster-bay", "oyster-bay-hp150-aac32k", "eagle-cam-clip-18000s", "eagle-cam-midnight"]
NEGATIVES = ["oyster-bay-moved-wsw150", "oyster-bay-moved-north150", "oyster-bay-sources-removed", "xenocanto-xc990819"]
UNITS = [f"{c}--cell0" for c in POSITIVES + NEGATIVES]
DETECT = dict(f_lo=60.0, f_hi=300.0, harmonics=1, top=10, window_s=240.0)
NULL_GROUPS = json.loads((HERE / "verdict_null_days.json").read_text())["groups"]
# Essex: the seeded 50 less the five days adsb.lol has no planes-readsb-prod-0 release for (A, not substituted)
ESSEX_NO_RELEASE = {"2025-05-28", "2025-05-31", "2025-06-06", "2025-06-07", "2025-06-10"}
NULL_GROUPS += [dict(g, days=[d for d in g["days"] if d not in ESSEX_NO_RELEASE])
                for g in json.loads((HERE / "verdict_null_days-essex.json").read_text())["groups"]]
NULL_UNITS = [f"{c}--null--{day}" for g in NULL_GROUPS for c in g["cases"] for day in g["days"]]


def null_traces(cid, day):
    """The case's box file on another day: derived/traces/<day>/<the same box stem>.npz."""
    own = cases.blind_case(cid)["flight_data"]["traces"]
    return f"derived/traces/{day}/{Path(own).name}"


def run_unit(cid, out_dir, day=None, cells=None):
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections
    from dopplertrack.collective import COARSE_M, Window, collective_find
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import detect_events
    case = cases.blind_case(cid)
    sp = Spectrogram.load(runner.resolve(case["spectrogram"]))
    found = cached_detections(sp, detect_events, **DETECT)
    usable = sorted([e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)], key=lambda e: -e.score)[:10]
    wins = [Window.from_detection(e) for e in usable]
    traces, _ = join_days([runner.resolve(null_traces(cid, day))] if day else runner.trace_paths(case))
    elevation = Terrain().elevation if case["search"]["dem"] else None
    g = f"{int(COARSE_M)}m"
    cache = (f"cpa/collective/null/{day}/{Path(null_traces(cid, day)).stem}_{g}.npz" if day else
             f"cpa/collective/{Path(case['search']['cpa_cache']).stem}_{g}.npz")
    path = runner.resolve(cache); path.parent.mkdir(parents=True, exist_ok=True)
    log_lines = []
    out = collective_find(sp, wins, traces, tuple(case["search"]["bbox"]), max_range_m=case["search"]["max_range_m"],
                          elevation=elevation, cpa_cache=str(path), log=log_lines.append, only_cells=cells)
    out["log"] = log_lines
    out["case"] = {"id": cid, "version": case["version"], "null_day": day, "cells": cells}
    return out


def save_draw(r, day, path):
    """collective_null.py's FIELDS for one other-day map: NaN where the map has no winner or no second mode."""
    from dopplertrack.geo import haversine_m
    w = r.get("winner") or {}
    nan = float("nan")
    second = max([m["Z"] for m in r.get("modes") or []
                  if w and haversine_m(m["lat"], m["lon"], w["lat"], w["lon"]) >= 2000.0], default=nan)
    np.savez(path, day=np.array(day), max_S=float(w.get("Z", nan)), second_S=float(second), lat=float(w.get("lat", nan)),
             lon=float(w.get("lon", nan)), n_matched=int(w.get("n_matched", 0)),
             clock_audio_minus_utc_s=float(w.get("clock_audio_minus_unix", nan)))


def judge(cid, r):
    """Against the criteria: distance to the reference and the true flights in the matched set (positives); the clock's
    day (eagle-cam-midnight); the maximum Z (every case, for the null)."""
    from dopplertrack.geo import haversine_m
    full = cases.latest_case(cid)
    lab = cases.case_labels(cid, full["version"])
    w = r.get("winner")
    out = {"Z": w["Z"] if w else None, "n_matched": w["n_matched"] if w else 0}
    if w is None:
        return out
    matched = [m for m in w["windows"] if m and m["z"] > 0]
    out["matched_flights"] = sorted({m["icao"] for m in matched})
    ref = lab.get("reference")
    if ref:
        out["distance_m"] = float(haversine_m(w["lat"], w["lon"], ref["lat"], ref["lon"]))
    pair = lab.get("true_pair")
    if pair:
        out["true_flights_matched"] = all(p in out["matched_flights"] for p in pair)
        out["true_flights_z"] = {p: max([m["z"] for m in matched if m["icao"] == p], default=None) for p in pair}
    start_unix = -w["clock_audio_minus_unix"]
    out["recording_start_utc"] = datetime.datetime.fromtimestamp(start_unix, datetime.timezone.utc).isoformat()
    st = full.get("start_time") or {}
    if st.get("utc") and float(st.get("uncertainty_s", 1e9)) < 3600:
        t0 = datetime.datetime.fromisoformat(st["utc"].replace("Z", "+00:00")).timestamp()
        out["start_time_error_s"] = start_unix - t0
        out["right_day"] = (datetime.datetime.fromtimestamp(start_unix, datetime.timezone.utc).date()
                            == datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).date())
    return out


def coarse_rank(cid, r):
    """The true location's coarse cell (the coarse map point nearest the reference, within a cell's half-diagonal) and its
    rank by Z among the cells with Z > 0; None where the truth's cell has no window above its null."""
    from dopplertrack.collective import COARSE_M
    from dopplertrack.geo import haversine_m
    lab = cases.case_labels(cid, cases.latest_case(cid)["version"])
    ref, m = lab.get("reference"), r.get("coarse_map") or {}
    if not ref or not m.get("Z"):
        return None
    d = np.array([haversine_m(la, lo, ref["lat"], ref["lon"]) for la, lo in zip(m["lat"], m["lon"])])
    i = int(np.argmin(d))
    if d[i] > COARSE_M / 2 * np.sqrt(2) + 1.0:
        return dict(rank=None, cells=len(m["Z"]), nearest_cell_m=float(d[i]))
    z = np.array(m["Z"])
    return dict(rank=int((z > z[i]).sum()) + 1, Z=float(z[i]), cells=len(z), coarse_max=float(z.max()),
                within_margin=bool(z[i] >= (r.get("margin") or {}).get("margin_threshold", np.inf)))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--null", action="store_true", help="A's other-day draws (verdict_null_days.json) instead of the cases")
    ap.add_argument("--null-cases", default=None, help="with --null, only these cases' draws (comma-separated)")
    ap.add_argument("--fine-from", type=Path, default=None, help="the fine stage: KEPT.json, {case: kept cells}")
    ap.add_argument("--extra-units", nargs="+", type=Path, default=None, metavar="DIR",
                    help="with --merge: the other stage's run folders, whose cell units join each case's best")
    a = ap.parse_args()
    keep = set(a.null_cases.split(",")) if a.null_cases else None
    if keep and not keep <= {u.split("--")[0] for u in NULL_UNITS}:
        ap.error(f"--null-cases: {sorted(keep - {u.split('--')[0] for u in NULL_UNITS})} have no null days")
    kept = json.loads(a.fine_from.read_text()) if a.fine_from else None
    if a.null:
        unit_ids = [u for u in NULL_UNITS if not keep or u.split("--")[0] in keep]
    elif kept is not None:
        unit_ids = [f"{c}--cell{k}" for c in POSITIVES + NEGATIVES for k in range(1, int(kept.get(c, 0)))]
    else:
        unit_ids = UNITS
    if a.inputs:
        from bench import inputs as bench_inputs
        doc = bench_inputs.run_inputs(sorted({u.split("--")[0] for u in unit_ids}), "locate")
        days = sorted({null_traces(*u.split("--null--")) for u in unit_ids}) if a.null else []
        shards.print_inputs(doc["cases"], doc["inputs"] + days, [], tuple(doc["cache_kinds"]))
        return
    from dopplertrack import collective as col
    params = dict(units=unit_ids, detect=DETECT, k=10, c="15 C", weather=False, f0_span=col.F0_SPAN,
                  collective=dict(coarse_m=col.COARSE_M, fine_m=col.FINE_M, margin_sigma=col.MARGIN_SIGMA,
                                  max_cells=col.MAX_CELLS, cluster_s=col.CLUSTER_S, agree_s=col.AGREE_S, null_n=col.NULL_N,
                                  log_du=col.LOG_DU, sub_s=col.SUB_S))
    if a.null:
        params.update(null_days="tools/experiments/2026-11-04/verdict_null_days.json", null_cases=sorted(keep) if keep else None)
    if kept is not None:
        params.update(fine_from=kept)
    topic = "collective-null-v4" if a.null else ("collective-fine-v4" if kept is not None else "collective-coarse-v4")
    run = shards.open_run(a.run, topic, {"script": "tools/experiments/2026-11-04/collective_run.py", "params": params})
    units = shards.Units(run, unit_ids, params, a.shard, a.resume)
    if not a.merge:
        for uid in units.todo():
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            if a.null:
                cid, day = uid.split("--null--")
                r = run_unit(cid, d, day)
                save_draw(r, day, d / "null_draws.npz")
            else:
                cid, cell = uid.split("--cell")
                r = run_unit(cid, d, cells=[int(cell)])
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")     # before any label is read
            units.finish(uid, {"Z": (r.get("winner") or {}).get("Z"), "walls": r.get("walls")})
            print(uid, json.dumps({"winner": r.get("winner") and {k: r["winner"][k] for k in ("lat", "lon", "Z", "n_matched")},
                                   "margin": r.get("margin"), "walls": r.get("walls"), "counts": r.get("counts")}, default=float),
                  flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    if a.null:          # collective_null.py reads the draws and judges; the merge only lists them
        rows = {u: dict(np.load(d / "null_draws.npz")) for u, d in units.all().items()}
        (run / "null_draws.json").write_text(json.dumps({u: {k: v.item() for k, v in r.items()} for u, r in rows.items()},
                                                        indent=1, default=float) + "\n")
        return
    results = {u: json.loads((d / "result.json").read_text()) for u, d in units.all().items()}
    for extra in a.extra_units or []:          # the other stage's run folder: its finished cell units
        for u in sorted((extra / "units").glob("*--cell*")):
            if (u / "result.json").exists():
                results.setdefault(u.name, json.loads((u / "result.json").read_text()))
    by_case = {}
    for uid, r in sorted(results.items()):
        by_case.setdefault(uid.split("--cell")[0], []).append((uid, r))
    out = {}
    for cid, rs in by_case.items():
        best_uid, best = max(rs, key=lambda x: (x[1].get("winner") or {}).get("Z", -np.inf))
        out[cid] = dict(judged=judge(cid, best), best_cell=best_uid, cells=[u for u, _ in rs], margin=best.get("margin"),
                        kept=best.get("kept"), coarse_truth=coarse_rank(cid, best), winner=best.get("winner"),
                        walls={u: r.get("walls") for u, r in rs}, counts=best.get("counts"))
    (run / "collective.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    (run / "KEPT.json").write_text(json.dumps({c: (v["margin"] or {}).get("kept_cells", 0) for c, v in out.items()}, indent=1) + "\n")
    for cid, v in out.items():
        print(cid, json.dumps({k: v[k] for k in ("judged", "best_cell", "coarse_truth")}, default=float))


if __name__ == "__main__":
    main()
