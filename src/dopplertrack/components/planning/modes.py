"""Greedy non-maximum suppression (Nixon & Aguado 2012 p.171) by distance: the peaks of a score map, as of an ambiguity
surface (Baggeroer 1993 §II, §V), that lie at least a separation apart. The record key is `modes`. With a clock
separation, a peak at a kept one's place is still distinct when its clock differs by more than that (ours)."""
from __future__ import annotations

import pandas as pd

from dopplertrack.core.geometry import haversine_m

MODE_SEPARATION_M = 2000.0
MAX_MODES = 5


def distinct_modes(peaks, separation_m: float = MODE_SEPARATION_M, max_modes: int = MAX_MODES,
                   clock_separation_s: float | None = None) -> list[dict]:
    """Walking peaks (dicts with lat, lon and clock_audio_minus_unix) in their order, every peak farther than
    separation_m from each peak kept so far, or, with clock_separation_s, more than that from its clock, is kept, up
    to max_modes. The peaks must come by descending Z; in any other order this is not non-maximum suppression."""
    out: list[dict] = []
    for m in peaks:
        if all(haversine_m(m["lat"], m["lon"], k["lat"], k["lon"]) > separation_m
               or (clock_separation_s is not None
                   and abs(m["clock_audio_minus_unix"] - k["clock_audio_minus_unix"]) > clock_separation_s)
               for k in out):
            out.append(m)
        if len(out) == max_modes:
            break
    return out


def modes(pts: pd.DataFrame, lat, lon, separation_m: float = MODE_SEPARATION_M, max_modes: int = MAX_MODES,
          clock_separation_s: float | None = None) -> list[dict]:
    """distinct_modes over pts (columns gidx, Z, b, n_matched) in its order; lat and lon map gidx to coordinates. pts
    must be sorted by descending Z (collective_detection sorts it). Each mode keeps its point's gidx, which the
    caller uses to look up the mode's matched passes."""
    peaks = (dict(lat=float(lat[int(r.gidx)]), lon=float(lon[int(r.gidx)]), Z=float(r.Z),
                  clock_audio_minus_unix=float(r.b), n_matched=int(r.n_matched), gidx=int(r.gidx))
             for r in pts.itertuples())
    return distinct_modes(peaks, separation_m, max_modes, clock_separation_s)
