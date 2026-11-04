"""The parallel CPA build against the serial one it replaced (PLAN Phase 1, item 1).

build: time cached_cpa_table into a fresh path, as `search --cpa-cache` would on a cold cache, and
       record wall and CPU seconds (pool workers included) in <out>.json.
       --rev old imports the package from <old_src>/dopplertrack (an export of the previous revision);
       --rev new uses the installed one. Both build the same grid and segments, as run_search does.
compare: load two saved tables and compare column names and order, dtypes, row order and values exactly.

usage:
  python cpa_parallel.py build --rev old|new --box ny|swfl [--workers N] [--old-src DIR] --out PATH.npz
  python cpa_parallel.py compare A.npz B.npz"""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
BOXES = {
    "ny": ((40.4, 41.3, -74.4, -72.6), DATA / "derived/oyster_bay/traces_ny.npz"),
    "swfl": ((26.1, 27.3, -82.5, -81.2), DATA / "derived/swfl/traces_swfl.npz"),
}
SPACING_M, MAX_RANGE_M = 200.0, 12000.0
COLUMNS = ["gidx", "seg", "t_emit", "t_heard", "d", "v"]


def cpu():
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


def build(a):
    if a.rev == "old":
        sys.path.insert(0, str(Path(a.old_src).resolve()))
    pkg = importlib.import_module("dopplertrack")
    pipeline = importlib.import_module("dopplertrack.pipeline")
    search = importlib.import_module("dopplertrack.search")
    from dopplertrack.adsb import load_traces
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.terrain import Terrain
    bbox, traces_path = BOXES[a.box]
    out = Path(a.out)
    if out.exists():
        sys.exit(f"{out} exists; every timed build needs a fresh cache path")
    c = speed_of_sound()
    grid = search.Grid.make(*bbox, SPACING_M, Terrain().elevation)
    traces = load_traces(traces_path)
    e0, e1 = grid.enu[:, 0].min() - MAX_RANGE_M, grid.enu[:, 0].max() + MAX_RANGE_M
    n0, n1 = grid.enu[:, 1].min() - MAX_RANGE_M, grid.enu[:, 1].max() + MAX_RANGE_M
    segs = search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=(e0, e1, n0, n1))
    kwargs = {} if a.rev == "old" else {"workers": a.workers}
    w0, c0 = time.perf_counter(), cpu()
    cpa = pipeline.cached_cpa_table(grid, segs, MAX_RANGE_M, c, str(out), **kwargs)
    wall, cpu_s = time.perf_counter() - w0, cpu() - c0
    info = {"rev": a.rev, "package": pkg.__file__, "box": a.box, "workers": a.workers if a.rev == "new" else None,
            "grid_points": len(grid), "segments": len(segs), "rows": len(cpa), "wall_s": round(wall, 2),
            "cpu_s": round(cpu_s, 2), "cpa_cache_version": search.CPA_CACHE_VERSION,
            "load_average": os.getloadavg()}
    out.with_suffix(".json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info))


def compare(a):
    with np.load(a.a, allow_pickle=False) as x, np.load(a.b, allow_pickle=False) as y:
        names_x = [k for k in x.files if k != "fingerprint"]
        names_y = [k for k in y.files if k != "fingerprint"]
        out = {"columns_equal": names_x == names_y == COLUMNS, "rows": [len(x["gidx"]), len(y["gidx"])],
               "fingerprint_equal": str(x["fingerprint"]) == str(y["fingerprint"])}
        for k in COLUMNS:
            xa, ya = x[k], y[k]
            same = xa.dtype == ya.dtype and xa.shape == ya.shape and np.array_equal(xa, ya)
            out[k] = {"dtype": [str(xa.dtype), str(ya.dtype)], "identical": bool(same)}
            if not same and xa.shape == ya.shape:
                out[k]["n_differ"] = int((xa != ya).sum())
        out["identical"] = out["columns_equal"] and all(out[k]["identical"] for k in COLUMNS)
    print(json.dumps(out, indent=1))
    return 0 if out["identical"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--rev", choices=["old", "new"], required=True)
    b.add_argument("--box", choices=list(BOXES), required=True)
    b.add_argument("--workers", type=int)
    b.add_argument("--old-src")
    b.add_argument("--out", required=True)
    cm = sub.add_parser("compare")
    cm.add_argument("a"); cm.add_argument("b")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)
    else:
        sys.exit(compare(a))
