"""PLAN Phase 2 item 7, stage A: event choice by the comparable score Z. SDE-B's event_pairs.py (copied, not
changed) with run_search(comparable=True): each event is scored against its own null and the ten pairs of
detect's top five are ranked by their search's top Z, blind, and the ranking hashed before any label is read.

Criterion (docs/experiments/2026-11-04-comparable-score.md, fixed before running):
  A1  eagle-cam-clip-18000s: the true pair (detect ranks 2 + 5) ranks first of the ten by top Z.
  A2  oyster-bay-moved-wsw150: the top pair's Z margin over the second pair is no larger than the eagle cam's
      true pair's Z margin over its second.
  A3  oyster-bay: events 1 + 2 stay first of its ten.
Reported separately, as the PM asked: whether the true pair survives the coarse search within 250 m of the
reference (the runner's triples sidecar), and its rank once retained.

usage, from the repo root:
  event_pairs_z.py [RUN] --detected DETECTED_RUN --case CASE [CASE ...] [--hypotheses] [--score comparable|raw]
                   [--workers-per-search 4] [--null-n N] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
  event_pairs_z.py one RUN_DIR VARIANT CODE PARAMS      (internal) one variant

Each of the pairs' searches is a unit (tools/data/shards.py): --shard splits them across machines, a stopped run
resumes from its folder with --resume, and once every unit is finished in RUN or the --resume folders the ranking
is written, hashed and only then revealed. The searches run $DOPPLERTRACK_JOBS / --workers-per-search at a time.
--score raw ranks by the search's own score, as SDE-B's event_pairs.py did; --hypotheses is stage B's
run_search(hypotheses=True) (the EVENT_PAIRS_HYPOTHESES=1 switch before)."""
import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "data"))
import shards                                                     # noqa: E402
from bench import cases, runner                                   # noqa: E402
from dopplertrack import pipeline                                 # noqa: E402
from dopplertrack.parallel import JOBS_ENV, default_jobs          # noqa: E402
from dopplertrack.result import read_record, sha256_bytes, write_record   # noqa: E402

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
TOP = 5
TRUE_EVENTS = {"eagle-cam-clip-18000s": [2, 5], "oyster-bay": [1, 2]}


def prepare(run: Path, detected_run: Path, case_ids: list[str]) -> dict:
    doc = cases.load_cases()
    variants, plan = [], {}
    for cid in case_ids:
        base = next(c for c in doc["cases"] if c["id"] == cid)
        det = json.loads((detected_run / cid / "detected.json").read_text())
        top = sorted(det, key=lambda d: d["score"], reverse=True)[:TOP]
        for k, d in enumerate(top, 1):
            d["detect_rank"] = k
        plan[cid] = []
        for a, b in itertools.combinations(top, 2):
            e1, e2 = sorted((a, b), key=lambda d: d["t_cpa"])
            vid = f"{cid}--d{e1['detect_rank']}d{e2['detect_rank']}"
            files = []
            for e in (e1, e2):
                p = run / "events" / f"{cid}-d{e['detect_rank']}.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({k: v for k, v in e.items() if k != "detect_rank"}, indent=1) + "\n")
                files.append(str(p))
            v = json.loads(json.dumps(base))
            v.update(id=vid, version=1)
            v["events"] = {"mode": "saved_fits", "files": files, "pick": None, "time_offset_s": 0.0}
            v["search"]["harmonics"] = [1, 1]
            variants.append(v)
            plan[cid].append({"variant": vid, "events": [e1["detect_rank"], e2["detect_rank"]],
                              "t_cpa": [e1["t_cpa"], e2["t_cpa"]]})
    (run / "cases.json").write_text(json.dumps({"schema": 1, "cases": variants}, indent=1) + "\n")
    (run / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    return plan


def one(run: Path, vid: str, params: dict):
    case = cases.blind_case(vid, run / "cases.json")
    out = run / "units" / vid
    out.mkdir(parents=True, exist_ok=True)
    overrides = {"workers": params["workers_per_search"], **({"comparable": True} if params["score"] == "comparable" else {}),
                 **({"hypotheses": True} if params["hypotheses"] else {}),
                 **({"null_n": params["null_n"]} if "null_n" in params else {})}
    nulls: dict = {}
    search = pipeline.run_search

    def keep_nulls(*a, **k):        # the record has no nulls; keep run_search's for a1_noise.py
        res, segs = search(*a, **k)
        nulls.update(res.attrs.get("null", {}))
        return res, segs

    pipeline.run_search = keep_nulls
    with open(out / "run.log", "w") as fh:
        record = runner.execute_case(case, out, log=lambda m: print(m, file=fh, flush=True), code=CODE,
                                     overrides=overrides)
    sha = write_record(out / "result.json", record)
    (out / runner.HASH_FILE).write_text(f"{sha}  result.json\n")
    (out / "null.json").write_text(json.dumps(nulls, indent=1) + "\n")


def rank(folders: dict, plan: dict) -> dict:
    """Each case's ten pairs ordered by the search's own top score, from the hashed records only."""
    table = {}
    for cid, rows in plan.items():
        out = []
        for r in rows:
            d = folders[r["variant"]]
            rec = read_record(d / "result.json", (d / runner.HASH_FILE).read_text().split()[0])
            c = rec["candidates"]
            out.append({**r, "errors": rec["execution"]["errors"], "flight_pairs": len(c),
                        "top_score": c[0]["score"] if c else None, "top_flights": c[0]["flights"] if c else None,
                        "top_raw_score": sum(c[0]["event_scores"]) if c else None,
                        "top_event_scores": c[0]["event_scores"] if c else None,
                        "z_margin_within": (c[0]["score"] - c[1]["score"]) if len(c) > 1 else None,
                        "margin_pct": (100 * (c[0]["score"] - c[1]["score"]) / c[1]["score"]) if len(c) > 1 else None})
        out.sort(key=lambda r: -(r["top_score"] or 0))
        for k, r in enumerate(out, 1):
            r["search_rank"] = k
        if len(out) > 1:
            out[0]["z_margin_over_next_pair"] = out[0]["top_score"] - out[1]["top_score"]
        table[cid] = out
    return table


def detected_file(detected_run: Path, cid: str) -> Path:
    return detected_run / cid / "detected.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--detected", type=Path, required=True, help="the raw-audio run whose detections are paired")
    ap.add_argument("--case", nargs="+", required=True)
    ap.add_argument("--score", choices=("comparable", "raw"), default="comparable")
    ap.add_argument("--hypotheses", action="store_true")
    ap.add_argument("--workers-per-search", type=int, default=4)
    ap.add_argument("--null-n", type=int, help="the null's draws per event (run_search's null_n; default its 1,000)")
    a = ap.parse_args()
    if a.inputs:
        rel = [str(detected_file(a.detected, c).resolve().relative_to(DATA.resolve())) for c in a.case]
        caches = sorted({cases.latest_case(c)["search"]["cpa_cache"] for c in a.case})
        shards.print_inputs(a.case, rel, caches)
        return
    params = {"cases": a.case, "score": a.score, "hypotheses": a.hypotheses, "top": TOP,
              "workers_per_search": a.workers_per_search, **({"null_n": a.null_n} if a.null_n else {}),
              "detected": {c: hashlib.sha256(detected_file(a.detected, c).read_bytes()).hexdigest() for c in a.case}}
    topic = "hypotheses-pairs" if a.hypotheses else ("comparable-score" if a.score == "comparable" else "event-pairs")
    run = shards.open_run(a.run, topic, {"script": "tools/experiments/2026-11-04/event_pairs_z.py",
                                        "detected": str(a.detected), "params": params,
                                        "invocation": {"shard": "%d/%d" % a.shard,
                                                       "resume": [str(r) for r in a.resume], "merge": a.merge}})
    plan = prepare(run, a.detected, a.case)
    units = shards.Units(run, [r["variant"] for rows in plan.values() for r in rows], params, a.shard, a.resume)
    if not a.merge:
        search(run, units, params)
    try:
        folders = units.all()
    except SystemExit as e:
        if a.merge:
            raise
        print(f"this shard is done; not merging yet: {e}", flush=True)
        return
    finish(run, plan, folders)


def search(run: Path, units, params: dict):
    """This shard's unfinished searches, as many at once as $DOPPLERTRACK_JOBS allows at
    --workers-per-search each."""
    per = params["workers_per_search"]
    slots = max(1, default_jobs() // per)
    env = {**os.environ, JOBS_ENV: str(per)}
    pending, running = units.todo(), []
    t0 = time.time()
    print(f"{len(pending)} searches, {slots} at a time with {per} workers each", flush=True)
    while pending or running:
        while pending and len(running) < slots:
            vid = pending.pop(0)
            running.append((vid, subprocess.Popen([sys.executable, __file__, "one", str(run), vid, json.dumps(CODE),
                                                   json.dumps(params)], env=env)))
            print(f"[{time.time() - t0:5.0f} s] started {vid}", flush=True)
        for vid, p in list(running):
            if p.poll() is not None:
                running.remove((vid, p))
                print(f"[{time.time() - t0:5.0f} s] {vid} exited {p.returncode}", flush=True)
                d = units.dir(vid)
                if p.returncode == 0 and (d / runner.HASH_FILE).exists():
                    units.finish(vid, {"seconds": round(time.time() - t0)})
        time.sleep(2)


def finish(run: Path, plan: dict, folders: dict):
    table = rank(folders, plan)
    data = (json.dumps(table, indent=1, sort_keys=True) + "\n").encode()
    (run / "ranking.json").write_bytes(data)
    (run / "ranking.json.sha256").write_text(f"{sha256_bytes(data)}  ranking.json\n")
    print("ranking written and hashed; reading labels", flush=True)
    reveal = {}
    for cid, rows in table.items():
        lab = cases.case_labels(cid, cases.latest_case(cid)["version"])
        for r in rows:
            meta = {"id": r["variant"], "version": 1, "group": "", "set": "development", "expected_outcome": ""}
            e = runner.compare_case(folders[r["variant"]], meta, lambda: lab)
            r.update({k: e.get(k) for k in ("status", "true_pair_rank", "top_error_m", "refined_error_m",
                                            "true_pair_near_reference", "true_pair_within_refine_reach",
                                            "true_pair_min_distance_m")})
        reveal[cid] = rows
    (run / "reveal.json").write_text(json.dumps(reveal, indent=1, sort_keys=True) + "\n")
    (run / "evaluation.json").write_text(json.dumps(evaluate(reveal), indent=1, sort_keys=True) + "\n")
    for cid, rows in reveal.items():
        print(f"\n{cid}")
        for r in rows:
            print(f"  {r['search_rank']:>2}  d{r['events'][0]}+d{r['events'][1]}  Z {r['top_score'] or 0:6.2f}  "
                  f"raw {r['top_raw_score'] or 0:6.2f}  near {r['true_pair_near_reference']}  "
                  f"pairs {r['flight_pairs']:>4}  top {r['top_flights']}  error {r['top_error_m']}  "
                  f"true-pair rank {r['true_pair_rank']}")


def evaluate(reveal: dict) -> dict:
    """A1-A3 from the revealed table, plus each case's ten top Z values."""
    out = {"z_distribution": {cid: [r["top_score"] for r in rows] for cid, rows in reveal.items()}}
    def by_events(cid, ev):
        return next((r for r in reveal.get(cid, []) if sorted(r["events"]) == sorted(ev)), None)
    eagle = by_events("eagle-cam-clip-18000s", TRUE_EVENTS["eagle-cam-clip-18000s"])
    if eagle is not None:
        rows = reveal["eagle-cam-clip-18000s"]
        nxt = [r for r in rows if r is not eagle][0]
        out["A1"] = {"true_pair_event_rank": eagle["search_rank"], "met": eagle["search_rank"] == 1}
        out["eagle_true_margin_over_second"] = eagle["top_score"] - nxt["top_score"]
    wsw = reveal.get("oyster-bay-moved-wsw150")
    if wsw and eagle is not None:
        m = wsw[0]["top_score"] - wsw[1]["top_score"]
        out["A2"] = {"wsw_top_margin": m, "eagle_true_margin": out["eagle_true_margin_over_second"],
                     "met": m <= out["eagle_true_margin_over_second"]}
    ob = by_events("oyster-bay", TRUE_EVENTS["oyster-bay"])
    if ob is not None:
        out["A3"] = {"events_1_2_rank": ob["search_rank"], "met": ob["search_rank"] == 1}
    return out


if __name__ == "__main__":         # run_search may start spawn pools, which re-import this file
    if len(sys.argv) > 1 and sys.argv[1] == "one":
        CODE = json.loads(sys.argv[4])
        one(Path(sys.argv[2]), sys.argv[3], json.loads(sys.argv[5]))
    else:
        CODE = runner.code_revision()
        main()
