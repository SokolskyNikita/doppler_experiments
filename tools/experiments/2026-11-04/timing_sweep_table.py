"""The deciding table of PLAN Phase 2 item 1's sweep, from the benchmark runs sweep.sh and sweep2.sh made.

Reads each labelled run folder from sweep.log and, per case: the triples reaching scoring (funnel.pipeline.scored),
the unplaceable ones, the true pair's least distance to the reference among them (the "scored" stage of the
triples sidecar), survival within 250 m (deciding), within refine's half-width and box-wide, its rank, the
margin and the top error.

Judged (docs/experiments/2026-11-04-timing-convention.md, with its amendment): oyster-bay and
oyster-bay-hp150-aac32k at raw-audio, eagle-cam-clip-18000s at saved-fit. A cell passes if on each the true
pair survives within 250 m and its count reaching scoring is at most that case's under today's heard gate
(raw-defaults / saved-defaults). Of the passing cells, the one with the smallest total count over the three is
adopted; each case's count is shown too.

usage: timing_sweep_table.py RUN_FOLDER   (writes sweep_table.json and prints the table)"""
import json
import re
import sys
from pathlib import Path

NEAR_M, REACH_M = 250.0, 600.0
JUDGED = {"oyster-bay": "raw", "oyster-bay-hp150-aac32k": "raw", "eagle-cam-clip-18000s": "saved"}


def runs(folder: Path) -> dict:
    out = {}
    for line in (folder / "sweep.log").read_text().splitlines():
        m = re.match(r"== (\S+) end \S+ exit (\d+) run_dir (\S+)", line)
        if m:
            out[m.group(1)] = (int(m.group(2)), Path(m.group(3)))
    return out


def case_rows(run_dir: Path) -> dict:
    res = json.loads((run_dir / "results.json").read_text())
    rows = {}
    for c in res["cases"]:
        rec = json.loads((run_dir / c["case"] / "result.json").read_text())
        pipe = rec["funnel"].get("pipeline", {})
        dist = c.get("true_pair_min_distance_m")
        d_scored = dist.get("scored") if isinstance(dist, dict) else None
        rows[c["case"]] = dict(
            scored=pipe.get("scored"), unplaceable=pipe.get("unplaceable"), gate=pipe.get("emission_gate", pipe.get("time_join")),
            silence=pipe.get("silence"), min_dist_m=d_scored,
            near=d_scored is not None and d_scored <= NEAR_M, reach=d_scored is not None and d_scored <= REACH_M,
            box=bool(c.get("true_pair_survived", {}).get("silence_filter")) if isinstance(c.get("true_pair_survived"), dict) else None,
            rank=c.get("true_pair_rank"), margin_pct=c.get("margin_pct"), top_error_m=c.get("top_error_m"),
            flight_pairs=c.get("flight_pairs"), events=[(e.get("t_cpa"), e.get("f0")) for e in rec.get("events", [])
                                                        if isinstance(e, dict)][:2])
    return rows


def main(folder: Path):
    rr = runs(folder)
    table = {label: {"exit": ex, "run_dir": str(d), "cases": case_rows(d)} for label, (ex, d) in rr.items() if ex == 0}
    base = {"raw": table["raw-defaults"]["cases"], "saved": table["saved-defaults"]["cases"]}
    cells = {}
    for g in (8, 12, 16, 20):
        for t in ("off", 2, 3, 4, 6):
            raw = table.get(f"raw-g{g}-{'off' if t == 'off' else f't{t}'}")
            sav = table.get(f"saved-eagle-g{g}-{'off' if t == 'off' else f't{t}'}")
            if raw is None or sav is None:
                continue
            per = {}
            for case, prof in JUDGED.items():
                row = (raw if prof == "raw" else sav)["cases"][case]
                b = base[prof][case]
                per[case] = dict(row, baseline_scored=b["scored"], passes=bool(row["near"] and row["scored"] <= b["scored"]))
            cells[f"{g}/{t}"] = dict(cases=per, passes=all(p["passes"] for p in per.values()),
                                     total=sum(p["scored"] for p in per.values()))
    passing = {k: v for k, v in cells.items() if v["passes"]}
    adopted = min(passing, key=lambda k: passing[k]["total"]) if passing else None
    out = {"runs": table, "cells": cells, "adopted": adopted,
           "baselines": {p: {c: {k: base[p][c][k] for k in ("scored", "near", "min_dist_m", "rank")} for c in base[p]} for p in base}}
    (folder / "sweep_table.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print("baselines", json.dumps(out["baselines"], default=float))
    for k, v in cells.items():
        print(k, "PASS" if v["passes"] else "    ", v["total"],
              " | ".join(f"{c[:12]} {p['scored']} {'Y' if p['near'] else 'N'} d{p['min_dist_m'] and round(p['min_dist_m'])} r{p['rank']}"
                         for c, p in v["cases"].items()))
    print("adopted:", adopted)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
