"""Candidate observer generation: who could have heard which flight, when, how far."""
from __future__ import annotations

import hashlib
import os
import threading
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .adsb import Trace
from .doppler import speed_of_sound
from .geo import lla_to_enu


@dataclass
class Grid:
    lat: np.ndarray
    lon: np.ndarray
    elev: np.ndarray
    enu: np.ndarray        # (G,3) relative to (lat0, lon0, 0)
    lat0: float
    lon0: float

    @classmethod
    def make(cls, lat_min, lat_max, lon_min, lon_max, spacing_m, elevation_fn=None):
        lat0, lon0 = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
        dlat = spacing_m / 111320.0
        dlon = spacing_m / (111320.0 * np.cos(np.radians(lat0)))
        la, lo = np.meshgrid(np.arange(lat_min, lat_max, dlat), np.arange(lon_min, lon_max, dlon), indexing="ij")
        la, lo = la.ravel(), lo.ravel()
        el = elevation_fn(la, lo) if elevation_fn else np.zeros_like(la)
        valid = np.isfinite(el)
        if not valid.all():
            warnings.warn(f"excluding {np.count_nonzero(~valid)} grid points with unavailable terrain elevation",
                          RuntimeWarning, stacklevel=2)
            la, lo, el = la[valid], lo[valid], np.asarray(el)[valid]
        if not len(la):
            raise ValueError("no grid points with valid terrain elevation; use --no-dem to explicitly assume sea level")
        el = np.maximum(el, 0.0)
        return cls(la, lo, el, lla_to_enu(la, lo, el, lat0, lon0), lat0, lon0)

    @classmethod
    def points(cls, lat, lon, elev, lat0=None, lon0=None):
        lat = np.atleast_1d(np.asarray(lat, float)); lon = np.atleast_1d(np.asarray(lon, float)); elev = np.atleast_1d(np.asarray(elev, float))
        if not np.all(np.isfinite(elev)):
            raise ValueError("terrain elevation is unavailable at the point; use --no-dem to explicitly assume sea level")
        lat0 = float(lat.mean()) if lat0 is None else lat0; lon0 = float(lon.mean()) if lon0 is None else lon0
        return cls(lat, lon, elev, lla_to_enu(lat, lon, elev, lat0, lon0), lat0, lon0)

    def __len__(self):
        return len(self.lat)


@dataclass
class Segment:
    trace_idx: int
    icao: str
    t: np.ndarray       # emission times (unix s), 1 Hz
    enu: np.ndarray     # (N,3)
    speed: np.ndarray   # (N,) m/s
    valid: np.ndarray | None = None  # original trace supports acoustic evidence here; geometry may interpolate a hole


def build_segments(traces: list[Trace], lat0: float, lon0: float, dt: float = 1.0, min_len: int = 20,
                   clip_enu: tuple[float, float, float, float] | None = None) -> list[Segment]:
    """1 Hz ENU segments. clip_enu=(e_min, e_max, n_min, n_max) keeps only the parts of a
    track inside that box (split where it leaves), which bounds memory in cpa_table.
    Geometry keeps the trace's 90 s gap bound for CPA proposals; valid retains
    the stricter 30 s evidence support through resampling and clipping."""
    segs = []
    for i, tr in enumerate(traces):
        for sl in tr.segments():
            t, enu, valid = tr.enu(sl, lat0, lon0, dt, return_valid=True)
            if len(t) < min_len or not np.all(np.isfinite(enu)):
                continue
            vel = np.gradient(enu, t, axis=0)
            spd = np.linalg.norm(vel, axis=1)
            if clip_enu is None:
                segs.append(Segment(i, tr.icao, t, enu, spd, valid))
                continue
            inside = (enu[:, 0] >= clip_enu[0]) & (enu[:, 0] <= clip_enu[1]) & (enu[:, 1] >= clip_enu[2]) & (enu[:, 1] <= clip_enu[3])
            if not inside.any():
                continue
            edges = np.flatnonzero(np.diff(inside.astype(int))) + 1
            for a, b in zip(np.r_[0, edges], np.r_[edges, len(t)]):
                if inside[a] and b - a >= min_len:
                    segs.append(Segment(i, tr.icao, t[a:b], enu[a:b], spd[a:b], valid[a:b]))
    return segs


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
                 tile_m: float = CPA_TILE_M):
    """CPA rows for one segment, in grid-index order: (gidx, t_emit, t_heard, d, v) arrays, or None."""
    m = _corridor(tree, s, max_range_m)
    out = []
    for k in range(0, len(m), chunk):
        idx = m[k:k + chunk]
        # |g-p|^2 = |g|^2 + |p|^2 - 2 g.p with one BLAS matmul per block; coordinates are centred on
        # the chunk so the cancellation stays harmless in float64. The centre is the chunk's mean, so
        # which points share a chunk is part of the result's bits.
        ctr = enu[idx].mean(0)
        g = enu[idx] - ctr                                        # (G,3)
        p = s.enu - ctr
        best, j = _nearest_samples(g, (g ** 2).sum(1), p, (p ** 2).sum(1), max_range_m, tile_m)
        r = np.sqrt(np.maximum(best, 0.0))
        ok = (r <= max_range_m) & (j > 0) & (j < len(s.t) - 1)     # interior CPA only
        if ok.any():
            out.append((idx[ok].astype(np.int32), s.t[j[ok]], s.t[j[ok]] + r[ok] / c,
                        r[ok].astype(np.float32), s.speed[j[ok]].astype(np.float32)))
    if not out:
        return None
    return tuple(np.concatenate(col) for col in zip(*out))


_WORKER: dict = {}


def _init_cpa_worker(enu):
    _WORKER["enu"], _WORKER["tree"] = enu, cKDTree(enu[:, :2])


def _cpa_task(args):
    s, max_range_m, c, chunk = args
    return _segment_cpa(_WORKER["enu"], _WORKER["tree"], s, max_range_m, c, chunk)


def cpa_table(grid: Grid, segs: list[Segment], max_range_m: float = 10000.0, c: float | None = None,
              chunk: int = 20000, workers: int | None = None) -> pd.DataFrame:
    """For every (grid point, segment) within max_range: CPA emission time, heard time,
    slant distance and ground-track speed at CPA.

    Rows are ordered by segment, then grid index. Segments run in `workers` processes
    (parallel.default_jobs() by default); the table is the same, byte for byte, for any number."""
    from .parallel import process_pool, resolve_jobs
    c = speed_of_sound() if c is None else c
    workers = min(resolve_jobs(workers), max(len(segs), 1))    # no idle workers for a short list
    if workers == 1:
        tree = cKDTree(grid.enu[:, :2])
        parts = [_segment_cpa(grid.enu, tree, s, max_range_m, c, chunk) for s in segs]
    else:
        # longest segments first, so no long one starts last and keeps the others waiting
        order = sorted(range(len(segs)), key=lambda i: -len(segs[i].t))
        parts = [None] * len(segs)
        with process_pool(workers, _init_cpa_worker, (grid.enu,)) as ex:
            for i, part in zip(order, ex.map(_cpa_task, ((segs[i], max_range_m, c, chunk) for i in order))):
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


CPA_CACHE_VERSION = 1      # bump when cpa_table's output changes for the same inputs


def cpa_fingerprint(grid: Grid, segs: list[Segment], max_range_m: float, c: float) -> str:
    """SHA-256 of everything cpa_table depends on: the grid's coordinates and elevations, every segment's
    times, positions and speeds, max_range, the speed of sound and the format version. Changing any of
    them, e.g. running with and without a DEM, changes the fingerprint even when no array changes size."""
    h = hashlib.sha256(f"cpa-table v{CPA_CACHE_VERSION} {float(max_range_m)!r} {float(c)!r} "
                       f"{float(grid.lat0)!r} {float(grid.lon0)!r} {len(grid)} {len(segs)}".encode())
    for a in (grid.lat, grid.lon, grid.elev, grid.enu):
        h.update(np.ascontiguousarray(a, np.float64).tobytes())
    for s in segs:
        h.update(f"{s.icao} {len(s.t)}".encode())
        for a in (s.t, s.enu, s.speed):
            h.update(np.ascontiguousarray(a, np.float64).tobytes())
    return h.hexdigest()


def save_cpa_table(path, cpa: pd.DataFrame, fingerprint):
    """Written under a temporary name in the same folder and renamed into place, so another process never
    reads a partial table and an interrupted save leaves nothing behind.

    Uncompressed: compressing Oyster Bay's 86M rows took 69 s on one core against 1.5 s to write them
    (874 MB against 2.76 GB), longer than building the table. load_cpa_table reads either kind."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
    try:
        np.savez(tmp, fingerprint=np.array(repr(fingerprint)), **{k: cpa[k].to_numpy() for k in CPA_COLUMNS})
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_cpa_table(path, fingerprint) -> pd.DataFrame | None:
    """Return the cached table if it was built from the same inputs, else None. A file that can't be read,
    such as one cut short by an older version, also counts as a miss."""
    try:
        with np.load(path, allow_pickle=False) as z:
            if str(z["fingerprint"]) != repr(fingerprint):
                return None
            return pd.DataFrame({k: z[k] for k in CPA_COLUMNS})
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None


def pair_candidates(cpa: pd.DataFrame, dt_offset: float, tol_s: float = 6.0,
                    v1=(0, 1e9), d1=(0, 1e9), v2=(0, 1e9), d2=(0, 1e9),
                    silence_d_m: float | None = 6000.0, silence_margin_s: float = 40.0,
                    funnel: dict | None = None) -> pd.DataFrame:
    """Grid points that hear an event-1-like CPA then, dt_offset later, an event-2-like CPA.

    The join is on (grid point, time bucket) rather than grid point alone: a grid point in a
    busy region hears hundreds of flights a day, and the unconstrained per-point cross product
    is billions of rows before the time filter. Buckets of width 2*tol_s with a +-1 bucket
    overlap find exactly the pairs within tol_s.

    funnel, if given, receives the row counts after each step: "cpa_rows", "event1_gates",
    "event2_gates", "time_join" and "silence" (see pipeline.run_search)."""
    funnel = {} if funnel is None else funnel
    a = cpa[(cpa.v.between(*v1)) & (cpa.d.between(*d1))]
    b = cpa[(cpa.v.between(*v2)) & (cpa.d.between(*d2))]
    funnel.update(cpa_rows=len(cpa), event1_gates=len(a), event2_gates=len(b))
    w = 2.0 * tol_s
    a = a.assign(key=np.floor(a.t_heard.to_numpy() / w).astype(np.int64))
    kb = np.floor((b.t_heard.to_numpy() - dt_offset) / w).astype(np.int64)
    parts = [a.merge(b.assign(key=kb + off), on=["gidx", "key"], suffixes=("1", "2")) for off in (-1, 0, 1)]
    m = pd.concat(parts, ignore_index=True).drop(columns="key")
    m = m[(m.seg1 != m.seg2) & ((m.t_heard2 - m.t_heard1 - dt_offset).abs() <= tol_s)].copy()
    funnel["time_join"] = len(m)
    if silence_d_m is not None and len(m):
        near = cpa[(cpa.d <= silence_d_m) & cpa.gidx.isin(m.gidx.unique())][["gidx", "seg", "t_heard"]]
        x = m[["gidx", "seg1", "seg2", "t_heard1", "t_heard2"]].reset_index().merge(near, on="gidx")
        bad = x[(x.seg != x.seg1) & (x.seg != x.seg2) & (x.t_heard > x.t_heard1 + silence_margin_s) & (x.t_heard < x.t_heard2 - silence_margin_s)]
        m = m.drop(index=bad["index"].unique())
    funnel["silence"] = len(m)
    return m.reset_index(drop=True)


def grid_lla(grid: Grid, gidx):
    return grid.lat[gidx], grid.lon[gidx], grid.elev[gidx]
