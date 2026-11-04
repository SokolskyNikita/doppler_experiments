"""Where the cold-cache Oyster Bay build's wall time goes: cpa_table alone, then saving the table
compressed (as save_cpa_table does) and uncompressed. usage: python cpa_split.py <out_dir> [workers]"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from dopplertrack import search
from dopplertrack.adsb import load_traces
from dopplertrack.doppler import speed_of_sound
from dopplertrack.terrain import Terrain

if __name__ == "__main__":
    out, workers = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10
    data = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
    grid = search.Grid.make(40.4, 41.3, -74.4, -72.6, 200.0, Terrain().elevation)
    traces = load_traces(data / "derived/oyster_bay/traces_ny.npz")
    e0, e1, n0, n1 = grid.enu[:, 0].min() - 12000, grid.enu[:, 0].max() + 12000, grid.enu[:, 1].min() - 12000, grid.enu[:, 1].max() + 12000
    segs = search.build_segments(traces, grid.lat0, grid.lon0, clip_enu=(e0, e1, n0, n1))
    res = {"load_before": os.getloadavg()}
    t = time.perf_counter(); cpa = search.cpa_table(grid, segs, 12000.0, speed_of_sound(), workers=workers)
    res["cpa_table_s"] = time.perf_counter() - t
    arrays = {k: cpa[k].to_numpy() for k in search.CPA_COLUMNS}
    for name, save in (("savez_compressed_s", np.savez_compressed), ("savez_s", np.savez)):
        path = out / f"split_{name}.npz"
        t = time.perf_counter(); save(path, **arrays); res[name] = time.perf_counter() - t
        res[name.replace("_s", "_bytes")] = path.stat().st_size
        path.unlink()
    res["load_after"] = os.getloadavg()
    print(json.dumps(res))
