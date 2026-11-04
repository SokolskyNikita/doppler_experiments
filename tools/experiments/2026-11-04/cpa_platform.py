"""Why does a case's CPA table have one row more when built on Linux (the fleet) than on macOS?

Stage A's fleet rerun found the eagle-cam clip's table at 35,861,817 rows on the box against 35,861,816 on the Mac,
from the same inputs, which moved the comparable score's null (docs/experiments/2026-11-04-comparable-score.md).

usage:
  cpa_platform.py build CASE OUT.npz [VERSION]   build the table of CASE's VERSION (default 1, the version
                                         event_pairs_z.py's variants copy) as the benchmark runner does (its grid, DEM,
                                         flight data, max range, default sound speed), saved with its fingerprint
  cpa_platform.py chunks CASE A B        the table at chunk sizes A and B: the same rows and emission times?
  cpa_platform.py explain CASE GIDX SEG   one grid point and segment: the segment's nearest samples, exactly
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


def inputs(cid: str, version: int):
    case = next(c for c in cases.load_cases()["cases"] if c["id"] == cid and c["version"] == version)
    s = case["search"]
    grid = search.Grid.make(*s["bbox"], s["spacing_m"], Terrain().elevation if s["dem"] else None)
    traces, _ = join_days(trace_paths(case))         # as the runner reads them
    r, c = s["max_range_m"], speed_of_sound()
    clip = (grid.enu[:, 0].min() - r, grid.enu[:, 0].max() + r, grid.enu[:, 1].min() - r, grid.enu[:, 1].max() + r)
    return grid, search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip), r, c


def build(cid: str, out: Path, version: int = 1):
    grid, segs, r, c = inputs(cid, version)
    cpa = search.cpa_table(grid, segs, r, c)
    search.save_cpa_table(out, cpa, search.cpa_fingerprint(grid, segs, r, c))
    print(json.dumps({"case": cid, "rows": len(cpa), "max_range_m": r, "out": str(out)}))


def chunks(cid: str, a: int, b: int, version: int = 1):
    """The table at two chunk sizes. The chunk sets each block's centre and so every matmul's rounding: the row
    set and the emission times must not depend on it, which is what decides rows on different platforms too."""
    grid, segs, r, c = inputs(cid, version)
    ta, tb = (search.cpa_table(grid, segs, r, c, chunk=k) for k in (a, b))
    ka = ta.seg.to_numpy().astype(np.int64) << 32 | ta.gidx.to_numpy()
    kb = tb.seg.to_numpy().astype(np.int64) << 32 | tb.gidx.to_numpy()
    same_rows = len(ka) == len(kb) and bool(np.array_equal(ka, kb))
    row = ta[(ta.gidx == 286222) & (ta.seg == 899)] if cid == "eagle-cam-clip-18000s" and version == 1 else None
    print(json.dumps({"case": cid, "chunks": [a, b], "rows": [len(ta), len(tb)], "same_rows": same_rows,
                      "same_t_emit": same_rows and bool(np.array_equal(ta.t_emit.to_numpy(), tb.t_emit.to_numpy())),
                      "max_abs_d_diff_m": float(np.abs(ta.d.to_numpy() - tb.d.to_numpy()).max()) if same_rows else None,
                      "row_286222_899": None if row is None else row.to_dict("records")}, indent=1, default=float))


def explain(cid: str, gidx: int, seg: int, version: int = 1):
    """One (grid point, segment): the segment's samples nearest the point, by exact float64 distance."""
    grid, segs, r, c = inputs(cid, version)
    sg = segs[seg]
    d = np.sqrt(((sg.enu - grid.enu[gidx]) ** 2).sum(1))
    near = np.argsort(d, kind="stable")[:6]
    print(json.dumps({"segment_samples": len(sg.t), "icao": sg.icao,
                      "nearest": [{"j": int(j), "d_m": float(d[j]), "t": float(sg.t[j]), "enu": sg.enu[j].tolist(),
                                   "speed": float(sg.speed[j])} for j in near],
                      "first_samples": [{"j": j, "d_m": float(d[j]), "enu": sg.enu[j].tolist()} for j in range(min(4, len(d)))],
                      "last_samples": [{"j": j, "d_m": float(d[j]), "enu": sg.enu[j].tolist()} for j in range(max(0, len(d) - 3), len(d))]},
                     indent=1))


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
        build(sys.argv[2], Path(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 1)
    elif sys.argv[1] == "chunks":
        chunks(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif sys.argv[1] == "explain":
        explain(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif sys.argv[1] == "diff":
        diff(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(__doc__)
