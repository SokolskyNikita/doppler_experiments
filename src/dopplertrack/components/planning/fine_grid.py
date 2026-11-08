"""Coarse-to-fine grid search, the fine level (Harvey 2018 §5.3.1; Axelrad 2011 Table 1): FINE_M points inside each
kept COARSE_M cell. Axelrad re-centres one smaller grid on the peak; subdividing every kept cell is ours."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.search.grid import Grid

COARSE_M, FINE_M = 1000.0, 200.0   # the third design step (collective/search.py): 1 km, as position is what a 2 km cell's span missed


def fine_grid(grid: Grid, gidx, elevation, lat0, lon0, coarse_m: float = COARSE_M,
              fine_m: float = FINE_M) -> tuple[Grid, np.ndarray]:
    """Points fine_m apart (FINE_M) inside each coarse_m (COARSE_M) cell, and each point's coarse cell."""
    k = int(round(coarse_m / fine_m))
    offs = (np.arange(k) - (k - 1) / 2) * fine_m
    lat, lon, cell = [], [], []
    for gi in gidx:
        la0, lo0 = float(grid.lat[gi]), float(grid.lon[gi])
        dla = offs / 111320.0; dlo = offs / (111320.0 * np.cos(np.radians(la0)))
        LA, LO = np.meshgrid(la0 + dla, lo0 + dlo, indexing="ij")
        lat.append(LA.ravel()); lon.append(LO.ravel()); cell.append(np.full(LA.size, int(gi)))
    lat, lon = np.concatenate(lat), np.concatenate(lon)
    elev = elevation(lat, lon) if elevation else np.zeros_like(lat)
    return Grid.points(lat, lon, np.where(np.isfinite(elev), elev, 0.0), lat0=lat0, lon0=lon0), np.concatenate(cell)
