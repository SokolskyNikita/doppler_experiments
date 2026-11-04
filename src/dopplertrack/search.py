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
from .geo import lla_to_enu, enu_to_lla


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


def cpa_table(grid: Grid, segs: list[Segment], max_range_m: float = 10000.0, c: float | None = None,
              chunk: int = 20000) -> pd.DataFrame:
    """For every (grid point, segment) within max_range: CPA emission time, heard time,
    slant distance and ground-track speed at CPA."""
    c = speed_of_sound() if c is None else c
    rows = []
    tree = cKDTree(grid.enu[:, :2])
    for si, s in enumerate(segs):
        # grid points within max_range (horizontally) of the track polyline, via a KD-tree
        # on track samples spaced <= max_range/4 apart (so the union of balls covers the corridor)
        step = max(1, int(max_range_m / 4 / max(np.median(s.speed), 1.0)))
        probes = s.enu[::step, :2]
        hits = tree.query_ball_point(probes, r=max_range_m * 1.05)
        m = np.unique(np.concatenate([np.asarray(h, int) for h in hits])) if len(hits) else np.array([], int)
        if len(m) == 0:
            continue
        for k in range(0, len(m), chunk):
            idx = m[k:k + chunk]
            # |g-p|^2 = |g|^2 + |p|^2 - 2 g.p as one BLAS matmul per block; coordinates are
            # centred on the chunk so the cancellation stays harmless in float64
            ctr = grid.enu[idx].mean(0)
            g = grid.enu[idx] - ctr                                   # (G,3)
            gg = (g ** 2).sum(1)
            nstep = max(1, int(1e7 // max(len(idx), 1)))
            best = np.full(len(idx), np.inf); j = np.zeros(len(idx), int)
            for n0 in range(0, len(s.t), nstep):
                pts = s.enu[n0:n0 + nstep] - ctr
                d2 = gg[:, None] + (pts ** 2).sum(1)[None, :] - 2.0 * (g @ pts.T)    # (G,n)
                jj = np.argmin(d2, axis=1)
                dd = d2[np.arange(len(idx)), jj]
                upd = dd < best
                best[upd] = dd[upd]; j[upd] = jj[upd] + n0
            r = np.sqrt(np.maximum(best, 0.0))
            ok = (r <= max_range_m) & (j > 0) & (j < len(s.t) - 1)     # interior CPA only
            if not ok.any():
                continue
            rows.append(pd.DataFrame({
                "gidx": idx[ok].astype(np.int32), "seg": np.int32(si),
                "t_emit": s.t[j[ok]], "t_heard": s.t[j[ok]] + r[ok] / c,
                "d": r[ok].astype(np.float32), "v": s.speed[j[ok]].astype(np.float32),
            }))
    if not rows:
        return empty_cpa_table()
    return pd.concat(rows, ignore_index=True)


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
    reads a partial table and an interrupted save leaves nothing behind."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
    try:
        np.savez_compressed(tmp, fingerprint=np.array(repr(fingerprint)), **{k: cpa[k].to_numpy() for k in CPA_COLUMNS})
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
                    silence_d_m: float | None = 6000.0, silence_margin_s: float = 40.0) -> pd.DataFrame:
    """Grid points that hear an event-1-like CPA then, dt_offset later, an event-2-like CPA.

    The join is on (grid point, time bucket) rather than grid point alone: a grid point in a
    busy region hears hundreds of flights a day, and the unconstrained per-point cross product
    is billions of rows before the time filter. Buckets of width 2*tol_s with a +-1 bucket
    overlap find exactly the pairs within tol_s."""
    a = cpa[(cpa.v.between(*v1)) & (cpa.d.between(*d1))]
    b = cpa[(cpa.v.between(*v2)) & (cpa.d.between(*d2))]
    w = 2.0 * tol_s
    a = a.assign(key=np.floor(a.t_heard.to_numpy() / w).astype(np.int64))
    kb = np.floor((b.t_heard.to_numpy() - dt_offset) / w).astype(np.int64)
    parts = [a.merge(b.assign(key=kb + off), on=["gidx", "key"], suffixes=("1", "2")) for off in (-1, 0, 1)]
    m = pd.concat(parts, ignore_index=True).drop(columns="key")
    m = m[(m.seg1 != m.seg2) & ((m.t_heard2 - m.t_heard1 - dt_offset).abs() <= tol_s)].copy()
    if silence_d_m is not None and len(m):
        near = cpa[(cpa.d <= silence_d_m) & cpa.gidx.isin(m.gidx.unique())][["gidx", "seg", "t_heard"]]
        x = m[["gidx", "seg1", "seg2", "t_heard1", "t_heard2"]].reset_index().merge(near, on="gidx")
        bad = x[(x.seg != x.seg1) & (x.seg != x.seg2) & (x.t_heard > x.t_heard1 + silence_margin_s) & (x.t_heard < x.t_heard2 - silence_margin_s)]
        m = m.drop(index=bad["index"].unique())
    return m.reset_index(drop=True)


def grid_lla(grid: Grid, gidx):
    return grid.lat[gidx], grid.lon[gidx], grid.elev[gidx]
