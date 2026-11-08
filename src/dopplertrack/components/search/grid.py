"""Search grid over position (Axelrad 2011, Combining Satellites; grid search: Amar & Weiss 2008 §IV): candidate
observer points over a box (or given points), with terrain elevation and ENU."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from dopplertrack.core.geometry import lla_to_enu


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


def grid_lla(grid: Grid, gidx):
    return grid.lat[gidx], grid.lon[gidx], grid.elev[gidx]
