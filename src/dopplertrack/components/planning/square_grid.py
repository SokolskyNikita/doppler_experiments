"""Refinement grid of a coarse-to-fine search (Harvey 2018 §5.3.1): a square grid around one point, the fine grid a
candidate is refined on."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.search.grid import Grid


def square_grid(lat: float, lon: float, half_m: float, spacing_m: float, elevation=None) -> Grid:
    """Points every spacing_m within half_m of (lat, lon) north-south and east-west, on terrain from elevation."""
    dlat = half_m / 111320.0
    dlon = half_m / (111320.0 * np.cos(np.radians(lat)))
    return Grid.make(lat - dlat, lat + dlat, lon - dlon, lon + dlon, spacing_m, elevation)
