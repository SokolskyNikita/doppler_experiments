"""Track segmentation: each trace's airborne runs resampled to 1 Hz in ENU, with their 3-D speed (climb included),
optionally clipped to a box."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.search.types import Segment
from dopplertrack.data.trajectories import Trace


def clip_box(enu: np.ndarray, pad_m: float) -> tuple[float, float, float, float]:
    """(e_min, e_max, n_min, n_max): the ENU extent of the points enu (N, 3) padded by pad_m on every side, the box
    build_segments clips to so that every segment within pad_m of a point is kept."""
    return (enu[:, 0].min() - pad_m, enu[:, 0].max() + pad_m, enu[:, 1].min() - pad_m, enu[:, 1].max() + pad_m)


def build_segments(traces: list[Trace], lat0: float, lon0: float, dt: float = 1.0, min_len: int = 20,
                   clip_enu: tuple[float, float, float, float] | None = None) -> list[Segment]:
    """1 Hz ENU segments. clip_enu=(e_min, e_max, n_min, n_max) keeps only the parts of a
    track inside that box (split where it leaves), which bounds memory in cpa_table.
    Geometry keeps the trace's 90 s gap bound for CPA proposals; valid retains
    the stricter 30 s ADS-B observation support through resampling and clipping. speed is the 3-D
    speed from the ENU gradient, climb included, not the ground-track speed."""
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
