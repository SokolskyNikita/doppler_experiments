"""The other days' flight data for the "located" verdict's null (docs/proposals/2026-11-04-verdict-null.md).

Each unit is one UTC day, streamed once from adsb.lol's GitHub release (extract_boxes.py --stream, as fetch-day
streams) and cut into every box its recording group needs, with the same margin and extraction metadata as the
cases' own cuts, whose recipes give the boxes. Nothing of the day is kept but the boxes.

usage, from the repo root:
  verdict_null_days.py plan [N]          choose N days per group (default 50), seeded, from the 120 days around each
                                         recording, skipping +-2 days, days not yet released, and days whose boxes
                                         are already in derived/; writes verdict_null_days.json beside this file
  verdict_null_days.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
                                         cut the planned days (units of tools/data/shards.py), one stream at a time
  verdict_null_days.py publish DIR ...   copy the pulled shards' boxes into derived/traces/<day>/, never over a file
                                         already there, read-only, and print the manifest lines

NULL_SET picks the recordings, in every mode: saved-fit (default; the saved-fit arm, plan verdict_null_days.json) or
essex (SDE-D's jets-only negative xenocanto-xc990819, plan verdict_null_days-essex.json)."""
import argparse
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "data"))
import shards                                                      # noqa: E402
from bench import cases                                            # noqa: E402

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
SEED = 20261104
TYPES = "raw/aux/opensky/doc8643AircraftTypes.csv"       # the aircraft-type table AircraftTypes would download
# each group's cases share a date and are cut from one stream per day
SETS = {"saved-fit": {"2026-09-08": ["oyster-bay", "oyster-bay-moved-wsw150", "oyster-bay-moved-north150"],
                      "2024-12-28": ["eagle-cam-clip-18000s"]},
        "essex": {"2025-04-20": ["xenocanto-xc990819"]}}
SET = os.environ.get("NULL_SET", "saved-fit")
GROUPS = SETS[SET]
PLAN = Path(__file__).with_name("verdict_null_days.json" if SET == "saved-fit" else f"verdict_null_days-{SET}.json")


def box_of(cid: str) -> tuple[str, str, float]:
    """(name, LATMIN,LATMAX,LONMIN,LONMAX, max range) from the case's traces recipe."""
    case = cases.latest_case(cid)
    d = next(d for d in case["derived"] if d["path"] == case["flight_data"]["traces"])
    args = d["recipe"][0]
    rng = float(args[args.index("--max-range") + 1])
    name, box = next(a for a in args if "=" in a and not a.startswith("{")).split("=")
    return name, box, rng


def plan(n: int):
    rng = np.random.default_rng(SEED)
    today = datetime.date.today()
    out = {"seed": SEED, "groups": []}
    for centre, cids in GROUPS.items():
        c = datetime.date.fromisoformat(centre)
        boxes = [box_of(cid) for cid in cids]
        assert len({b[2] for b in boxes}) == 1, "one margin per group"
        pool = [c + datetime.timedelta(days=k) for k in range(-60, 61) if abs(k) > 2
                and c + datetime.timedelta(days=k) < today]
        pool = [d for d in pool if not all((DATA / "derived/traces" / d.isoformat() / f"{b[0]}.npz").exists() for b in boxes)]
        days = sorted(rng.choice(len(pool), size=min(n, len(pool)), replace=False))
        out["groups"].append({"centre": centre, "cases": cids, "max_range_m": boxes[0][2],
                              "boxes": {b[0]: b[1] for b in boxes}, "days": [pool[i].isoformat() for i in days]})
    PLAN.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{sum(len(g['days']) for g in out['groups'])} days -> {PLAN}")


def run():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    p = json.loads(PLAN.read_text())
    if a.inputs:
        shards.print_inputs([], [TYPES], [], ())
        return
    cached = Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack")) / Path(TYPES).name
    if not cached.exists():       # extract_boxes's prop filter reads it from the cache, and boxes can't reach OpenSky
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DATA / TYPES, cached)
    units = {d: g for g in p["groups"] for d in g["days"]}
    run_dir = shards.open_run(a.run, "verdict-null-days" + ("" if SET == "saved-fit" else f"-{SET}"), {"script": "tools/experiments/2026-11-04/verdict_null_days.py",
                                                          "params": p, "invocation": {"shard": "%d/%d" % a.shard,
                                                          "resume": [str(r) for r in a.resume], "merge": a.merge}})
    u = shards.Units(run_dir, list(units), p, a.shard, a.resume)
    if not a.merge:
        for day in u.todo():          # one stream at a time per box, as fetch-day
            g, d = units[day], u.dir(day)
            part = d / f"attempt-{int(time.time())}"      # a stopped attempt's boxes stay in their own folder
            part.mkdir(parents=True)
            t0 = time.time()
            cmd = [sys.executable, str(REPO / "tools/data/extract_boxes.py"), "--max-range", str(g["max_range_m"]),
                   "--stream", day, str(part), *[f"{k}={v}" for k, v in g["boxes"].items()]]
            with open(part / "extract.log", "w") as log:
                code = subprocess.run(cmd, cwd=REPO, stdout=log, stderr=subprocess.STDOUT).returncode
            ok = code == 0 and all((part / f"{k}.npz").exists() for k in g["boxes"])
            if ok:
                for f in [*part.glob("*.npz"), part / "extract.log"]:
                    f.rename(d / f.name)
            print(f"{day}: exit {code} in {time.time() - t0:.0f} s", flush=True)
            if ok:
                u.finish(day, {"seconds": round(time.time() - t0), "boxes": sorted(g["boxes"])})
    try:
        u.all()
        print("every planned day is cut", flush=True)
    except SystemExit as e:
        print(f"not all days cut yet: {e}", flush=True)


def publish(dirs: list[Path]):
    p = json.loads(PLAN.read_text())
    for g in p["groups"]:
        for day in g["days"]:
            src = next((d / "units" / day for d in dirs if (d / "units" / day / "unit.json").exists()), None)
            if src is None:
                print(f"{day}: not cut")
                continue
            for name in g["boxes"]:
                dest = DATA / "derived/traces" / day / f"{name}.npz"
                if dest.exists():
                    print(f"{day}/{name}: already in derived/, kept")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / f"{name}.npz", dest)
                dest.chmod(dest.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
                print(f"derived/traces/{day}/{name}.npz")


if __name__ == "__main__":
    if sys.argv[1:2] == ["plan"]:
        plan(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    elif sys.argv[1:2] == ["publish"]:
        publish([Path(x) for x in sys.argv[2:]])
    else:
        run()
