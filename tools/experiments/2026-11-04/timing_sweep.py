"""PLAN Phase 2 item 1's deciding sweep (sweep.sh and sweep2.sh in runs/2026-11-04-timing-convention/, ran at
51f59ce) as one command: each of its 45 cells is one `bench run` into its own unit folder (tools/data/shards.py),
so the cells split across machines with --shard, a stopped sweep resumes with --resume, and once every cell is
finished timing_sweep_table.py's table is written to RUN/sweep_table.json.

Each cell runs its cases at once (`bench run --parallel`), each case with an equal share of $DOPPLERTRACK_JOBS.

usage, from the repo root:
  timing_sweep.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]"""
import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "data"))
import shards  # noqa: E402

POS = ["oyster-bay", "eagle-cam-clip-18000s", "oyster-bay-hp150-aac32k"]
NEG = ["oyster-bay-moved-wsw150", "oyster-bay-moved-north150"]
E = ["time_convention=emission"]


def cells() -> dict:
    """label -> (profile, search params, cases), in sweep.sh's then sweep2.sh's order."""
    out = {"raw-defaults": ("raw-audio", [], POS + NEG)}
    for g in (8, 12, 16, 20):
        out[f"raw-g{g}-off"] = ("raw-audio", E + [f"tol_s={g}"], POS)
        for t in (2, 3, 4, 6):
            out[f"raw-g{g}-t{t}"] = ("raw-audio", E + [f"tol_s={g}", f"sf_tol_s={t}"], POS)
    out["raw-g16-t4-steepest"] = ("raw-audio", E + ["tol_s=16", "sf_tol_s=4", "clock_anchor=steepest"], POS)
    out["raw-g16-t4-negatives"] = ("raw-audio", E + ["tol_s=16", "sf_tol_s=4"], NEG)
    out["saved-defaults"] = ("saved-fit", [], POS)
    out["saved-g16-t4"] = ("saved-fit", E + ["tol_s=16", "sf_tol_s=4"], POS)
    for g in (8, 12, 16, 20):
        out[f"saved-eagle-g{g}-off"] = ("saved-fit", E + [f"tol_s={g}"], ["eagle-cam-clip-18000s"])
        for t in (2, 3, 4, 6):
            out[f"saved-eagle-g{g}-t{t}"] = ("saved-fit", E + [f"tol_s={g}", f"sf_tol_s={t}"], ["eagle-cam-clip-18000s"])
    return out


def table_module():
    spec = importlib.util.spec_from_file_location("timing_sweep_table", Path(__file__).with_name("timing_sweep_table.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    cc = cells()
    if a.inputs:
        sys.path.insert(0, str(REPO))
        from bench import cases
        caches = sorted({cases.latest_case(c)["search"]["cpa_cache"] for c in POS + NEG})
        shards.print_inputs(POS + NEG, [], caches, ("detections", "window_fits", "terrarium"))
        return
    params = {"cells": {k: [p, s, c] for k, (p, s, c) in cc.items()}}
    run = shards.open_run(a.run, "timing-sweep", {"script": "tools/experiments/2026-11-04/timing_sweep.py",
                                                 "params": params,
                                                 "invocation": {"shard": "%d/%d" % a.shard,
                                                                "resume": [str(r) for r in a.resume], "merge": a.merge}})
    units = shards.Units(run, list(cc), params, a.shard, a.resume)
    if not a.merge:
        for label in units.todo():
            profile, sp, case_ids = cc[label]
            d = units.dir(label)
            d.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, "-m", "bench", "run", "--tier", "t2", "--run-dir", str(d), "--profile", profile,
                   "--parallel", str(len(case_ids)), *[x for p in sp for x in ("--search-param", p)], *case_ids]
            t0 = time.time()
            with open(run / f"sweep_{label}.log", "w") as log:
                code = subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, env=os.environ).returncode
            print(f"{label}: exit {code} in {time.time() - t0:.0f} s", flush=True)
            if code == 0 and (d / "results.json").exists():
                units.finish(label, {"seconds": round(time.time() - t0)})
    try:
        folders = units.all()
    except SystemExit as e:
        if a.merge:
            raise
        print(f"this shard is done; not merging yet: {e}", flush=True)
        return
    table_module().main(run, {label: (0, d) for label, d in folders.items()})


if __name__ == "__main__":
    main()
