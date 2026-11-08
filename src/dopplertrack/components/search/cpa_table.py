"""Closest point of approach (CPA) table (Ferguson & Quinn 1994 §III, t_c): for every grid point and segment, the 1 Hz
sample nearest the point, if within range and interior to the segment, with its emission and heard times, slant range
and speed."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from dopplertrack.components.search.grid import Grid
from dopplertrack.components.search.types import Segment
from dopplertrack.core.atmosphere import point_sound_speed
from dopplertrack.core.propagation import speed_of_sound

CPA_TILE_M = 4000.0      # side of the tiles a chunk's grid points are split into to prune track samples


def _corridor(tree: cKDTree, s: Segment, max_range_m: float) -> np.ndarray:
    """Grid points within max_range (horizontally) of the track polyline, via a KD-tree on track
    samples spaced <= max_range/4 apart (so the union of balls covers the corridor). Sorted."""
    step = max(1, int(max_range_m / 4 / max(np.median(s.speed), 1.0)))
    hits = tree.query_ball_point(s.enu[::step, :2], r=max_range_m * 1.05, return_sorted=False)
    mask = np.zeros(tree.n, bool)
    for h in hits:
        mask[h] = True
    return np.flatnonzero(mask)


def _nearest_samples(g, gg, p, pp, max_range_m, tile_m):
    """For each centred grid point g (G,3), the smallest squared distance to the centred samples p (n,3)
    and the first sample index attaining it, wherever that distance can be <= max_range_m.

    The points are split into tiles of tile_m metres, and each tile is compared only with the samples
    within max_range_m + 1 m (horizontally) of its bounding box.

    Invariant: a sample left out is farther than max_range_m from every point of the tile, so it can't
    be the nearest sample of any kept row (kept rows need r <= max_range_m), and every sample at a kept
    row's minimum distance is within max_range_m and therefore retained. argmin's first-index rule
    picks the same sample. Horizontal distance to the tile's bounding box is a lower bound on slant
    range, so the test is conservative, and the 1 m margin covers rounding in the expression below.
    Points with no sample in reach get best = inf. The kept entries use the same expression and chunk
    centre as comparing every point with every sample, so the kept CPAs are bit for bit the same."""
    best = np.full(len(g), np.inf)
    j = np.zeros(len(g), int)
    key = np.floor(g[:, :2] / tile_m).astype(np.int64)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks = key[order]
    cuts = np.flatnonzero(np.any(ks[1:] != ks[:-1], axis=1)) + 1
    reach2 = (max_range_m + 1.0) ** 2
    for pos in np.split(order, cuts):
        gt = g[pos]
        lo, hi = gt[:, :2].min(0), gt[:, :2].max(0)
        out = np.maximum(np.maximum(lo - p[:, :2], p[:, :2] - hi), 0.0)
        near = np.flatnonzero((out ** 2).sum(1) <= reach2)
        if len(near) == 0:
            continue
        nstep = max(1, int(1e7 // len(pos)))
        for n0 in range(0, len(near), nstep):
            k = near[n0:n0 + nstep]
            d2 = gg[pos][:, None] + pp[k][None, :] - 2.0 * (gt @ p[k].T)       # (G,n)
            jj = np.argmin(d2, axis=1)
            dd = d2[np.arange(len(pos)), jj]
            upd = dd < best[pos]
            best[pos[upd]] = dd[upd]; j[pos[upd]] = k[jj[upd]]
    return best, j


def _segment_cpa(enu: np.ndarray, tree: cKDTree, s: Segment, max_range_m: float, c: float, chunk: int,
                 tile_m: float = CPA_TILE_M, temperature_c: float | None = None):
    """CPA rows for one segment (interior CPAs only), in grid-index order: (gidx, t_emit, t_heard, d, v) arrays, or None. With a
    ground temperature, t_heard uses each CPA's own sound speed (atmosphere.point_sound_speed) instead of c."""
    m = _corridor(tree, s, max_range_m)
    # Each distinct position once, as its earliest sample. Samples at the same position (an aircraft
    # stopped, or a lap flown again) tie exactly, and BLAS rounds the tied columns differently on
    # different platforms (Accelerate and OpenBLAS picked different samples of one stopped aircraft),
    # so argmin's first-index rule would no longer pick the earliest one.
    first = np.sort(np.unique(s.enu, axis=0, return_index=True)[1])
    out = []
    for k in range(0, len(m), chunk):
        idx = m[k:k + chunk]
        # |g-p|^2 = |g|^2 + |p|^2 - 2 g.p with one BLAS matmul per block; coordinates are centred on
        # the chunk so the cancellation stays harmless in float64. The centre is the chunk's mean, so
        # which points share a chunk is part of the result's bits.
        ctr = enu[idx].mean(0)
        g = enu[idx] - ctr                                        # (G,3)
        p = s.enu[first] - ctr
        best, jf = _nearest_samples(g, (g ** 2).sum(1), p, (p ** 2).sum(1), max_range_m, tile_m)
        j = first[jf]
        r = np.sqrt(np.maximum(best, 0.0))
        ok = (r <= max_range_m) & (j > 0) & (j < len(s.t) - 1)     # interior CPA only
        if ok.any():
            cc = c if temperature_c is None else point_sound_speed(temperature_c, s.enu[j[ok], 2] - enu[idx[ok], 2])
            out.append((idx[ok].astype(np.int32), s.t[j[ok]], s.t[j[ok]] + r[ok] / cc,
                        r[ok].astype(np.float32), s.speed[j[ok]].astype(np.float32)))
    if not out:
        return None
    return tuple(np.concatenate(col) for col in zip(*out))


_WORKER: dict = {}


def _init_cpa_worker(enu):
    _WORKER["enu"], _WORKER["tree"] = enu, cKDTree(enu[:, :2])


def _cpa_task(args):
    s, max_range_m, c, chunk, temperature_c = args
    return _segment_cpa(_WORKER["enu"], _WORKER["tree"], s, max_range_m, c, chunk, temperature_c=temperature_c)


def cpa_table(grid: Grid, segs: list[Segment], max_range_m: float = 10000.0, c: float | None = None,
              chunk: int = 20000, workers: int | None = None, temperature_c: float | None = None) -> pd.DataFrame:
    """For every (grid point, segment) within max_range: CPA emission time, heard time,
    slant distance and speed at CPA. The CPA is the nearest 1 Hz sample, not the continuous minimum, and
    only interior CPAs are kept: a point whose nearest sample is a segment end has no row. The speed is
    the segment's 3-D speed (climb included), not its ground-track speed.

    temperature_c: the ground temperature. If given, each heard time uses the sound speed at that CPA's
    mid-height temperature (its emission point's height above the grid point), not c.

    Rows are ordered by segment, then grid index. Segments run in `workers` processes
    (parallel.default_jobs() by default); the table is the same, byte for byte, for any number."""
    from dopplertrack.runtime.parallel import process_pool, resolve_jobs
    c = speed_of_sound() if c is None else c
    workers = min(resolve_jobs(workers), max(len(segs), 1))    # no idle workers for a short list
    if workers == 1:
        tree = cKDTree(grid.enu[:, :2])
        parts = [_segment_cpa(grid.enu, tree, s, max_range_m, c, chunk, temperature_c=temperature_c) for s in segs]
    else:
        # longest segments first, so no long one starts last and keeps the others waiting
        order = sorted(range(len(segs)), key=lambda i: -len(segs[i].t))
        parts = [None] * len(segs)
        with process_pool(workers, _init_cpa_worker, (grid.enu,)) as ex:
            for i, part in zip(order, ex.map(_cpa_task, ((segs[i], max_range_m, c, chunk, temperature_c) for i in order))):
                parts[i] = part
    cols: dict[str, list[np.ndarray]] = {"gidx": [], "seg": [], "t_emit": [], "t_heard": [], "d": [], "v": []}
    for si, part in enumerate(parts):
        if part is None:
            continue
        for k, a in zip(("gidx", "t_emit", "t_heard", "d", "v"), part):
            cols[k].append(a)
        cols["seg"].append(np.full(len(part[0]), si, np.int32))
    if not cols["gidx"]:
        return empty_cpa_table()
    return pd.DataFrame({k: np.concatenate(v) for k, v in cols.items()})


CPA_COLUMNS = ["gidx", "seg", "t_emit", "t_heard", "d", "v"]


def empty_cpa_table() -> pd.DataFrame:
    return pd.DataFrame({"gidx": np.zeros(0, np.int32), "seg": np.zeros(0, np.int32),
                         "t_emit": np.zeros(0), "t_heard": np.zeros(0),
                         "d": np.zeros(0, np.float32), "v": np.zeros(0, np.float32)})
