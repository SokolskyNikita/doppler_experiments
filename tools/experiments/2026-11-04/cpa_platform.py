"""Why does a case's CPA table have one row more when built on Linux (the fleet) than on macOS?

Stage A's fleet rerun found the eagle-cam clip's table at 35,861,817 rows on the box against 35,861,816 on the Mac,
from the same inputs, which moved the comparable score's null (docs/experiments/2026-11-04-comparable-score.md).

usage:
  cpa_platform.py build CASE OUT.npz     build CASE's table as the benchmark runner does (its grid, DEM, flight data,
                                         max range and the default sound speed) and save it with its fingerprint
  cpa_platform.py diff A.npz B.npz       the rows only one table has, and how the rows both have differ, with each
                                         differing row's distance against max range"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from bench import cases                                            # noqa: E402
from dopplertrack import search                                    # noqa: E402
from bench.runner import trace_paths                               # noqa: E402
from dopplertrack.adsb import join_days                            # noqa: E402
from dopplertrack.doppler import speed_of_sound                    # noqa: E402
from dopplertrack.terrain import Terrain                           # noqa: E402

DATA = Path(__import__("os").environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))


def build(cid: str, out: Path):
    case = cases.latest_case(cid)
    s = case["search"]
    grid = search.Grid.make(*s["bbox"], s["spacing_m"], Terrain().elevation if s["dem"] else None)
    traces, _ = join_days(trace_paths(case))         # as the runner reads them
    r, c = s["max_range_m"], speed_of_sound()
    clip = (grid.enu[:, 0].min() - r, grid.enu[:, 0].max() + r, grid.enu[:, 1].min() - r, grid.enu[:, 1].max() + r)
    segs = search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip)
    cpa = search.cpa_table(grid, segs, r, c)
    search.save_cpa_table(out, cpa, search.cpa_fingerprint(grid, segs, r, c))
    print(json.dumps({"case": cid, "rows": len(cpa), "max_range_m": r, "out": str(out)}))


def load(path: Path):
    with np.load(path, allow_pickle=False) as z:
        return str(z["fingerprint"]), {k: z[k] for k in search.CPA_COLUMNS}


def diff(a: Path, b: Path, max_range_m: float | None = None):
    fa, ta = load(a)
    fb, tb = load(b)
    ka = ta["seg"].astype(np.int64) << 32 | ta["gidx"].astype(np.int64)
    kb = tb["seg"].astype(np.int64) << 32 | tb["gidx"].astype(np.int64)
    only_a, only_b = np.setdiff1d(ka, kb), np.setdiff1d(kb, ka)
    common, ia, ib = np.intersect1d(ka, kb, return_indices=True)
    out = {"same_fingerprint": fa == fb, "rows": [len(ka), len(kb)], "only_in_a": len(only_a), "only_in_b": len(only_b)}
    for name, t, keys, ks in (("a", ta, ka, only_a), ("b", tb, kb, only_b)):
        rows = np.flatnonzero(np.isin(keys, ks))
        out[f"rows_only_in_{name}"] = [{k: float(t[k][i]) for k in search.CPA_COLUMNS} for i in rows[:20]]
    for k in ("t_emit", "t_heard", "d", "v"):
        dv = ta[k][ia] != tb[k][ib]
        out[f"common_rows_differing_in_{k}"] = int(dv.sum())
        if dv.any():
            i = np.flatnonzero(dv)[:5]
            out[f"examples_{k}"] = [{"seg": int(ta["seg"][ia[x]]), "gidx": int(ta["gidx"][ia[x]]),
                                     "a": float(ta[k][ia[x]]), "b": float(tb[k][ib[x]])} for x in i]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2], Path(sys.argv[3]))
    elif sys.argv[1] == "diff":
        diff(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(__doc__)
