"""Greedy non-maximum suppression (Nixon & Aguado 2012 p.171) by distance: the peaks of a score map, as of an ambiguity
surface (Baggeroer 1993 §II, §V), that lie at least a separation apart. The record key is `modes`."""
from __future__ import annotations

import pandas as pd

from dopplertrack.core.geometry import haversine_m

MODE_SEPARATION_M = 2000.0
MAX_MODES = 5


def modes(pts: pd.DataFrame, lat, lon, separation_m: float = MODE_SEPARATION_M, max_modes: int = MAX_MODES) -> list[dict]:
    """Walking pts (columns gidx, Z, b, n_matched) in its order, every point farther than separation_m from each
    peak kept so far is kept, up to max_modes; lat and lon map gidx to coordinates. pts must be sorted by descending Z
    (collective_detection sorts it); in any other order this is not non-maximum suppression."""
    out, seen = [], []
    for r in pts.itertuples():
        la, lo = float(lat[int(r.gidx)]), float(lon[int(r.gidx)])
        if all(haversine_m(la, lo, a, b) > separation_m for a, b in seen):
            seen.append((la, lo))
            out.append(dict(lat=la, lon=lo, Z=float(r.Z), clock_audio_minus_unix=float(r.b), n_matched=int(r.n_matched)))
        if len(out) == max_modes:
            break
    return out
