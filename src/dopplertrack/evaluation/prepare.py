"""`bench prepare CASE`: a case's CPA table, built ahead of any search, for a set that may not be searched yet.

The table is the one a search of the case would build or load: the case's grid (search box, spacing, DEM), its flight
data joined across days, the search range, and the sound speed the run would use (the 15 C default, or with
`--weather` the case's station temperature), keyed and saved by `pipeline.cached_cpa_table` to `search.cpa_cache`
(or its `_weather` twin). The segments are built exactly as `run_search` builds them, so the fingerprint matches.
Nothing reads the case's labels, its audio or its events: the case is taken without its labels, and blocked cases
(evaluation, calibration) are allowed, since this is not a run.
"""
from __future__ import annotations

import time


def prepare_case(case_id: str, use_weather: bool = False, workers: int | None = None, log=print) -> dict:
    from .cases import latest_case
    from .runner import private_cache
    from .cases import is_private
    case = latest_case(case_id)
    case.pop("labels", None)                       # never read: this is preparation, not a run
    if is_private(case):
        from .private import resolve_case
        case = resolve_case(case)
    with private_cache(case):
        return _prepare(case, use_weather, workers, log)


def _prepare(case: dict, use_weather: bool, workers: int | None, log) -> dict:
    from dopplertrack.data.day_seams import join_days
    from dopplertrack.core.propagation import speed_of_sound
    from dopplertrack.methods.grid_pair.pipeline import cached_cpa_table
    from dopplertrack.components.search.grid import Grid
    from dopplertrack.components.search.segments import build_segments
    from dopplertrack.data.terrain import Terrain

    from .runner import cpa_cache_path, geometry_kw, trace_paths
    case_id = case["id"]
    s = case["search"]
    t0 = time.perf_counter()
    terrain = Terrain() if s["dem"] else None
    grid = Grid.make(*s["bbox"], s["spacing_m"], terrain.elevation if terrain else None)
    traces, _ = join_days(trace_paths(case))
    rng = s["max_range_m"]
    e0, e1 = grid.enu[:, 0].min() - rng, grid.enu[:, 0].max() + rng
    n0, n1 = grid.enu[:, 1].min() - rng, grid.enu[:, 1].max() + rng
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(e0, e1, n0, n1))
    kw = geometry_kw(case, use_weather)
    c = kw.get("c", speed_of_sound())               # run_search's own default when no c is given
    path = cpa_cache_path(case, use_weather)
    path.parent.mkdir(parents=True, exist_ok=True)
    t1 = time.perf_counter()
    cpa = cached_cpa_table(grid, segs, rng, c, str(path), workers=workers, temperature_c=kw.get("temperature_c"))
    out = {"case": case_id, "version": case["version"], "cpa_table": str(path), "grid_points": len(grid),
           "segments": len(segs), "cpa_records": len(cpa), "c_m_s": c, "temperature_c": kw.get("temperature_c"),
           "grid_and_segments_s": round(t1 - t0, 1), "cpa_s": round(time.perf_counter() - t1, 1)}
    log(str(out))
    return out
