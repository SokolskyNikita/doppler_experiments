"""Track stitching across UTC midnight (track segment association, Blackman & Popoli 1999 §9.6.4): one flight's
traces from consecutive days joined where a kinematic gate on the seam (gap, position jump against ground speed,
altitude change) passes."""
from __future__ import annotations

import numpy as np

from dopplertrack.data.region_loading import load_trace_metadata, load_traces
from dopplertrack.data.trajectories import Trace

# Joining day files (PLAN 5.6: recordings that cross UTC midnight). Each day's archive ends at midnight,
# so a flight in the air then becomes two traces with a short seam between them. A seam is joined only
# when the aircraft is plainly the same flight across it; the four limits are judgement, set before any
# audio was looked at.
SEAM_MAX_GAP_S = 90.0          # the segmenter's geometry bound
SEAM_SPEED_FACTOR = 1.5        # horizontal jump <= factor * mean ground speed * gap + slack
SEAM_JUMP_SLACK_M = 500.0
SEAM_CLIMB_M_S = 8.0           # altitude change <= rate * gap + slack: a propeller climb is 2.5-7.5 m/s
SEAM_ALT_SLACK_M = 100.0


def _seam(a: Trace, b: Trace) -> dict:
    """Whether trace b continues trace a across a day boundary, and the numbers that decided it."""
    from dopplertrack.core.geometry import haversine_m
    va, vb = np.flatnonzero(a.valid_positions()), np.flatnonzero(b.valid_positions())
    out = {"icao": a.icao, "gap_s": float(b.t[0] - a.t[-1]), "joined": False}
    if not len(va) or not len(vb):
        return {**out, "reason": "no usable position on one side of the seam"}
    i, j = va[-1], vb[0]
    gap = float(b.t[j] - a.t[i])
    jump = float(haversine_m(a.lat[i], a.lon[i], b.lat[j], b.lon[j]))
    climb = float(abs(b.alt[j] - a.alt[i]))
    gs = np.nanmean([a.gs[i], b.gs[j]]) if np.isfinite([a.gs[i], b.gs[j]]).any() else np.nan
    out.update(gap_s=gap, jump_m=round(jump, 1), altitude_change_m=round(climb, 1),
               ground_speed_m_s=None if not np.isfinite(gs) else round(float(gs), 1))
    if gap > SEAM_MAX_GAP_S:
        return {**out, "reason": f"gap over {SEAM_MAX_GAP_S:g} s"}
    if not np.isfinite(gs):
        return {**out, "reason": "no ground speed at the seam"}
    if jump > SEAM_SPEED_FACTOR * gs * max(gap, 0.0) + SEAM_JUMP_SLACK_M:
        return {**out, "reason": "position jump too large for the speed"}
    if climb > SEAM_CLIMB_M_S * max(gap, 0.0) + SEAM_ALT_SLACK_M:
        return {**out, "reason": "altitude change too large for the gap"}
    return {**out, "joined": True, "reason": "continuous"}


def _concat(a: Trace, b: Trace) -> Trace:
    n_a, n_b = len(a), len(b)

    def provenance(name, fill):
        x, y = getattr(a, name), getattr(b, name)
        if x is None and y is None:
            return None
        return np.concatenate([np.full(n_a, fill) if x is None else x, np.full(n_b, fill) if y is None else y])

    flags_b = None if b.flags is None else b.flags.copy()
    if flags_b is not None and n_b:
        flags_b[0] &= ~2       # the later file's first point starts that file, not a new leg
    b = Trace(b.icao, b.reg, b.typ, b.desc, b.t, b.lat, b.lon, b.alt, b.gs, b.on_ground, b.alt_source,
              b.position_source, flags_b)
    t = np.concatenate([a.t, b.t])
    keep = np.r_[True, np.diff(t) > 0]          # day files don't overlap; a repeated time keeps the first
    cat = {k: np.concatenate([getattr(a, k), getattr(b, k)])[keep] for k in ("t", "lat", "lon", "alt", "gs", "on_ground")}
    prov = {k: (None if v is None else v[keep]) for k, v in (("alt_source", provenance("alt_source", "unknown")),
                                                               ("position_source", provenance("position_source", "unknown")),
                                                               ("flags", provenance("flags", np.int32(0))))}
    return Trace(a.icao, a.reg or b.reg, a.typ or b.typ, a.desc or b.desc, **cat, **prov)


def join_days(paths) -> tuple[list[Trace], dict]:
    """Traces and extraction metadata from one or more consecutive day files of the same box. One file is
    exactly load_traces and load_trace_metadata. With several, a flight that continues across a day
    boundary becomes one trace (see _seam), and the metadata lists every day's own metadata, the
    intersection of their coverage envelopes when all are known, and every seam with what decided it."""
    paths = [str(p) for p in paths]
    if len(paths) == 1:
        return load_traces(paths[0]), load_trace_metadata(paths[0])
    days = [(p, load_traces(p), load_trace_metadata(p)) for p in paths]
    days.sort(key=lambda d: min((float(t.t[0]) for t in d[1] if len(t)), default=np.inf))
    open_: dict[str, Trace] = {}
    done: list[Trace] = []
    seams = []
    for k, (_, traces, _) in enumerate(days):
        carried = open_
        open_ = {}
        for tr in traces:
            prev = carried.pop(tr.icao, None)
            if prev is not None:
                seam = _seam(prev, tr)
                seams.append(seam)
                if seam["joined"]:
                    tr = _concat(prev, tr)
                else:
                    done.append(prev)
            if tr.icao in open_:          # two traces of one aircraft in one day file: keep both, join the later
                done.append(open_[tr.icao])
            open_[tr.icao] = tr
        done.extend(carried.values())
    done.extend(open_.values())
    metas = [m for _, _, m in days]
    meta = {"version": 1, "joined_days": [{"path": p, "metadata": m or "legacy: no extraction metadata"} for p, _, m in days],
            "seams": seams}
    if all(m.get("coverage_bbox") for m in metas):
        boxes = np.array([m["coverage_bbox"] for m in metas], float)
        meta["coverage_bbox"] = [float(boxes[:, 0].max()), float(boxes[:, 1].min()),
                                 float(boxes[:, 2].max()), float(boxes[:, 3].min())]
        meta["max_range_m"] = min(float(m.get("max_range_m", 0.0)) for m in metas)
    if all(m.get("scan") for m in metas):
        meta["scan"] = {k: sum(int(m["scan"][k]) for m in metas) for k in metas[0]["scan"]}
    if metas[0].get("height_datums"):
        meta["height_datums"] = metas[0]["height_datums"]
    return done, meta
