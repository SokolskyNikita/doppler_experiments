"""Event choice by search score: search all ten pairs of detect's top five events, rank them blind, then reveal.

For each case: take the five highest-scoring detections from the raw-audio baseline run, make one variant case
per pair (earlier event first, harmonics 1 and 1 as in the raw-audio profile, the case's gates and cached CPA
table), and run each through the benchmark runner with run_search at one worker, two variants at a time. The
ten records are written and hashed, then ranked by the search's own top score, and that ranking is written and
hashed before any label is read. Only then are the true pair's places revealed.

usage, from the repo root:
  event_pairs.py RUN_DIR DETECTED_RUN CASE [CASE ...]     prepare, run, rank, reveal
  event_pairs.py one RUN_DIR VARIANT                      (internal) one variant"""
import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bench import cases, runner                                   # noqa: E402
from dopplertrack.result import read_record, sha256_bytes, write_record   # noqa: E402

TOP = 5
JOBS = 2


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


def one(run: Path, vid: str):
    case = cases.blind_case(vid, run / "cases.json")
    out = run / vid
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "run.log", "w") as fh:
        record = runner.execute_case(case, out, log=lambda m: print(m, file=fh, flush=True), code=CODE,
                                     overrides={"workers": 1})
    sha = write_record(out / "result.json", record)
    (out / runner.HASH_FILE).write_text(f"{sha}  result.json\n")


def rank(run: Path, plan: dict) -> dict:
    """Each case's ten pairs ordered by the search's own top score, from the hashed records only."""
    table = {}
    for cid, rows in plan.items():
        out = []
        for r in rows:
            d = run / r["variant"]
            rec = read_record(d / "result.json", (d / runner.HASH_FILE).read_text().split()[0])
            c = rec["candidates"]
            out.append({**r, "errors": rec["execution"]["errors"], "flight_pairs": len(c),
                        "top_score": c[0]["score"] if c else None, "top_flights": c[0]["flights"] if c else None,
                        "margin_pct": (100 * (c[0]["score"] - c[1]["score"]) / c[1]["score"]) if len(c) > 1 else None})
        out.sort(key=lambda r: -(r["top_score"] or 0))
        for k, r in enumerate(out, 1):
            r["search_rank"] = k
        table[cid] = out
    return table


def main():
    run, detected_run, case_ids = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    plan = prepare(run, detected_run, case_ids)
    pending = [r["variant"] for rows in plan.values() for r in rows]
    running = []
    t0 = time.time()
    while pending or running:
        while pending and len(running) < JOBS:
            vid = pending.pop(0)
            running.append((vid, subprocess.Popen([sys.executable, __file__, "one", str(run), vid, json.dumps(CODE)])))
            print(f"[{time.time() - t0:5.0f} s] started {vid}", flush=True)
        for vid, p in list(running):
            if p.poll() is not None:
                running.remove((vid, p))
                print(f"[{time.time() - t0:5.0f} s] {vid} exited {p.returncode}", flush=True)
        time.sleep(2)
    table = rank(run, plan)
    data = (json.dumps(table, indent=1, sort_keys=True) + "\n").encode()
    (run / "ranking.json").write_bytes(data)
    (run / "ranking.json.sha256").write_text(f"{sha256_bytes(data)}  ranking.json\n")
    print("ranking written and hashed; reading labels", flush=True)
    reveal = {}
    for cid, rows in table.items():
        lab = cases.case_labels(cid, cases.latest_case(cid)["version"])
        for r in rows:
            meta = {"id": r["variant"], "version": 1, "group": "", "set": "development", "expected_outcome": ""}
            e = runner.compare_case(run / r["variant"], meta, lambda: lab)
            r.update({k: e.get(k) for k in ("status", "true_pair_rank", "top_error_m", "refined_error_m",
                                            "true_pair_near_reference", "true_pair_min_distance_m")})
        reveal[cid] = rows
    (run / "reveal.json").write_text(json.dumps(reveal, indent=1, sort_keys=True) + "\n")
    for cid, rows in reveal.items():
        print(f"\n{cid}")
        for r in rows:
            print(f"  {r['search_rank']:>2}  d{r['events'][0]}+d{r['events'][1]}  score {r['top_score'] or 0:6.2f}  "
                  f"margin {r['margin_pct'] if r['margin_pct'] is None else round(r['margin_pct'], 2)} %  "
                  f"pairs {r['flight_pairs']:>4}  top {r['top_flights']}  error {r['top_error_m']}  "
                  f"true-pair rank {r['true_pair_rank']}")


if __name__ == "__main__":         # run_search may start spawn pools, which re-import this file
    if sys.argv[1] == "one":
        CODE = json.loads(sys.argv[4])
        one(Path(sys.argv[2]), sys.argv[3])
    else:
        CODE = runner.code_revision()
        main()
