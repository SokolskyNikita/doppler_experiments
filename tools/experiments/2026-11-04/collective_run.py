"""The collective find on the development cases (docs/proposals/2026-11-04-collective-find.md; criteria in
docs/experiments/2026-11-04-collective-find.md, written before the run). One shards.py unit per (case, f0 sweep):
locate's detection (60-300 Hz, harmonics 1, top 10, 240 s windows) on the case's spectrogram, its usable windows as
collective.Window (bounds, coarse tone, coarse heard CPA only), then collective.collective_find over the case's box with
its flight data, 15 C, the weather off. The result is written before any label is read; the merge judges the criteria.

With --null, the units are A's other-day draws instead (verdict_null_days.json, and verdict_null_days-essex.json less
its five days without a release): "<case>--null--<day>" runs the same
find, at +-10 % f0, with the case's box swapped to that day's cut of the same box, and writes null_draws.npz for
collective_null.py (day, max_S = the winner's Z, second_S = the best mode 2 km or more from it, lat, lon, n_matched,
clock_audio_minus_utc_s).

usage: uv run python tools/experiments/2026-11-04/collective_run.py [RUN] [--null] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
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
UNITS = [f"{c}--f0-10" for c in POSITIVES + NEGATIVES] + [f"{c}--f0-5" for c in POSITIVES]
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


def run_unit(cid, span, out_dir, day=None):
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections
    from dopplertrack.collective import Window, collective_find
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import detect_events
    case = cases.blind_case(cid)
    sp = Spectrogram.load(runner.resolve(case["spectrogram"]))
    found = cached_detections(sp, detect_events, **DETECT)
    usable = sorted([e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)], key=lambda e: -e.score)[:10]
    wins = [Window.from_detection(e) for e in usable]
    traces, _ = join_days([runner.resolve(null_traces(cid, day))] if day else runner.trace_paths(case))
    elevation = Terrain().elevation if case["search"]["dem"] else None
    cache = (f"cpa/collective/null/{day}/{Path(null_traces(cid, day)).stem}_2km.npz" if day else
             f"cpa/collective/{Path(case['search']['cpa_cache']).stem}_2km.npz")
    path = runner.resolve(cache); path.parent.mkdir(parents=True, exist_ok=True)
    log_lines = []
    out = collective_find(sp, wins, traces, tuple(case["search"]["bbox"]), max_range_m=case["search"]["max_range_m"],
                          elevation=elevation, f0_span=span, cpa_cache=str(path), log=log_lines.append)
    out["log"] = log_lines
    out["case"] = {"id": cid, "version": case["version"], "null_day": day}
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--null", action="store_true", help="A's other-day draws (verdict_null_days.json) instead of the cases")
    a = ap.parse_args()
    unit_ids = NULL_UNITS if a.null else UNITS
    if a.inputs:
        from bench import inputs as bench_inputs
        doc = bench_inputs.run_inputs(sorted({u.split("--")[0] for u in unit_ids}), "locate")
        days = sorted({null_traces(*u.split("--null--")) for u in NULL_UNITS}) if a.null else []
        shards.print_inputs(doc["cases"], doc["inputs"] + days, [], tuple(doc["cache_kinds"]))
        return
    params = dict(units=unit_ids, detect=DETECT, k=10, c="15 C", weather=False,
                  collective=dict(coarse_m=2000, fine_m=200, keep_top=5, cluster_s=20, agree_s=6, null_n=1000))
    if a.null:
        params.update(f0_span=0.10, null_days="tools/experiments/2026-11-04/verdict_null_days.json")
    run = shards.open_run(a.run, "collective-null" if a.null else "collective-find",
                          {"script": "tools/experiments/2026-11-04/collective_run.py", "params": params})
    units = shards.Units(run, unit_ids, params, a.shard, a.resume)
    if not a.merge:
        for uid in units.todo():
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            if a.null:
                cid, day = uid.split("--null--")
                r = run_unit(cid, 0.10, d, day)
                save_draw(r, day, d / "null_draws.npz")
            else:
                cid, span = uid.split("--"); span = int(span.split("-")[1]) / 100
                r = run_unit(cid, span, d)
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")     # before any label is read
            units.finish(uid, {"Z": (r.get("winner") or {}).get("Z"), "walls": r.get("walls")})
            print(uid, json.dumps({"winner": r.get("winner") and {k: r["winner"][k] for k in ("lat", "lon", "Z", "n_matched")},
                                   "walls": r.get("walls"), "counts": r.get("counts")}, default=float), flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    if a.null:          # collective_null.py reads the draws and judges; the merge only lists them
        rows = {u: dict(np.load(d / "null_draws.npz")) for u, d in units.all().items()}
        (run / "null_draws.json").write_text(json.dumps({u: {k: v.item() for k, v in r.items()} for u, r in rows.items()},
                                                        indent=1, default=float) + "\n")
        return
    out = {}
    for uid, d in units.all().items():
        r = json.loads((d / "result.json").read_text())
        out[uid] = dict(judged=judge(uid.split("--")[0], r), walls=r.get("walls"), counts=r.get("counts"),
                        winner=r.get("winner"), modes=r.get("modes"), coarse_top=r.get("coarse_top"), windows=r.get("windows"))
    (run / "collective.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for uid, v in out.items():
        print(uid, json.dumps(v["judged"], default=float))


if __name__ == "__main__":
    main()
