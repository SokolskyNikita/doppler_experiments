"""Continuous segment/site intersections and non-overlapping recording bins.

All coordinates and heights are kilometers, time is seconds on a common epoch.
Horizontal xyz has three sphere coordinates at a fixed Earth radius, as in the
preceding snapshot model. Vertical separation is computed separately. The path
is linear within each native valid track segment; its radius is constant there.
No temporal sample grid is used. A zero-duration tangent does not count.
"""
from __future__ import annotations

import numpy as np


def iter_candidate_pairs(tree, start_xyz, end_xyz, max_radius_km, *, chunk_size=20000):
    """Yield conservative (segment, resident) candidate pairs by midpoint balls.

    The cKDTree is built on residential horizontal xyz. The search sphere of
    radius max acoustic radius + half segment length contains the whole swept
    horizontal cylinder, so candidates cannot be missed between track fixes.
    """
    start_xyz = np.asarray(start_xyz, dtype=np.float64)
    end_xyz = np.asarray(end_xyz, dtype=np.float64)
    radii = np.broadcast_to(np.asarray(max_radius_km, dtype=np.float64), len(start_xyz))
    for lo in range(0, len(start_xyz), chunk_size):
        hi = min(lo + chunk_size, len(start_xyz))
        midpoint = (start_xyz[lo:hi] + end_xyz[lo:hi]) / 2
        half_length = np.linalg.norm(end_xyz[lo:hi] - start_xyz[lo:hi], axis=1) / 2
        candidates = tree.query_ball_point(midpoint, radii[lo:hi] + half_length)
        sizes = np.fromiter((len(ids) for ids in candidates), dtype=np.int64, count=hi-lo)
        if not sizes.sum():
            continue
        resident = np.concatenate(candidates[sizes > 0]).astype(np.intp, copy=False)
        segment = np.repeat(np.arange(lo, hi), sizes)
        yield segment, resident


def candidate_pairs(tree, start_xyz, end_xyz, max_radius_km, *, chunk_size=20000):
    """Return all candidate pairs; use the iterator when total size is large."""
    batches = list(iter_candidate_pairs(tree, start_xyz, end_xyz, max_radius_km,
                                       chunk_size=chunk_size))
    if not batches:
        return np.empty(0, np.intp), np.empty(0, np.intp)
    return tuple(np.concatenate([batch[j] for batch in batches]) for j in (0, 1))


def solve_intervals(start_xyz, end_xyz, alt0_km, alt1_km, t0_s, t1_s,
                    radii_km, bg_xyz, bg_orthometric_km, bg_geoid_km,
                    segment, resident, *, geometric0=None, geometric1=None, pair_radii_km=None):
    """Solve analytic intersections for supplied conservative candidate pairs.

    radii_km has shape (n_segment, n_scenario), or one radius per segment.
    pair_radii_km optionally overrides it with shape (n_pair, n_scenario), for
    different indoor or outdoor spectra by the resident's geographic class.
    For time-varying conditions, split the candidate interval at the local
    condition boundary before invoking this solver.
    geometric0/1 are endpoint flags saying that altitude is ellipsoidal. For
    such endpoints the resident's EGM96 geoid separation is subtracted before
    comparing to its orthometric ground elevation. If heights are already MSL,
    leave both flags omitted. Different endpoint conventions interpolate after
    this local correction. Times must increase and radii must be nonnegative.

    Returns arrays scenario/resident/segment/start_s/end_s, one per positive
    duration intersection. Different aircraft and adjacent segments may overlap;
    these rows must be unioned or binned before summing population/time.
    """
    start_xyz = np.asarray(start_xyz, dtype=np.float64)
    end_xyz = np.asarray(end_xyz, dtype=np.float64)
    segment = np.asarray(segment, dtype=np.intp)
    resident = np.asarray(resident, dtype=np.intp)
    radius = np.asarray(radii_km, dtype=np.float64)
    if radius.ndim == 1:
        radius = radius[:, None]
    if radius.ndim != 2 or len(radius) != len(start_xyz):
        raise ValueError('Radius must have one row per segment')
    if np.any(radius < 0) or not np.isfinite(radius).all():
        raise ValueError('Radius must be finite and nonnegative')
    t0_s, t1_s = np.asarray(t0_s, dtype=np.float64), np.asarray(t1_s, dtype=np.float64)
    if np.any(t1_s <= t0_s):
        raise ValueError('Each native segment must have increasing time')
    geometric0 = np.zeros(len(start_xyz), bool) if geometric0 is None else np.asarray(geometric0)
    geometric1 = geometric0 if geometric1 is None else np.asarray(geometric1)
    delta = end_xyz[segment] - start_xyz[segment]
    offset = start_xyz[segment] - np.asarray(bg_xyz)[resident]
    ground = np.asarray(bg_orthometric_km)[resident]
    geoid = np.asarray(bg_geoid_km)[resident]
    z0 = np.asarray(alt0_km)[segment] - ground - geoid * geometric0[segment]
    z1 = np.asarray(alt1_km)[segment] - ground - geoid * geometric1[segment]
    dz = z1 - z0
    a = np.einsum('ij,ij->i', delta, delta) + dz*dz
    dot = np.einsum('ij,ij->i', offset, delta) + z0*dz
    moving = a > np.finfo(float).tiny
    center = np.zeros(len(segment))
    np.divide(-dot, a, out=center, where=moving)
    closest_xyz = offset + center[:, None]*delta
    closest_z = z0 + center*dz
    closest2 = np.einsum('ij,ij->i', closest_xyz, closest_xyz) + closest_z*closest_z
    result = {name: [] for name in ('scenario', 'resident', 'segment', 'start_s', 'end_s')}
    paired = None if pair_radii_km is None else np.asarray(pair_radii_km, dtype=np.float64)
    if paired is not None:
        if paired.ndim == 1:
            paired = paired[:, None]
        if paired.ndim != 2 or len(paired) != len(segment) or not np.isfinite(paired).all() or np.any(paired < 0):
            raise ValueError('Pair radii must have one finite nonnegative row per candidate pair')
    scenarios = radius.shape[1] if paired is None else paired.shape[1]
    for scenario in range(scenarios):
        rr = radius[segment, scenario] if paired is None else paired[:, scenario]
        remain = rr*rr - closest2
        half_width = np.zeros(len(segment))
        possible = (remain > 0) & moving & (rr > 0)
        np.sqrt(np.divide(remain, a, out=np.zeros_like(a), where=possible),
                out=half_width, where=possible)
        first = np.maximum(0, center-half_width)
        last = np.minimum(1, center+half_width)
        stationary = ~moving & (remain >= 0) & (rr > 0)
        first[stationary], last[stationary] = 0, 1
        valid = (possible | stationary) & (last > first)
        if not valid.any():
            continue
        ix = segment[valid]
        duration = t1_s[ix]-t0_s[ix]
        result['scenario'].append(np.full(valid.sum(), scenario, dtype=np.int16))
        result['resident'].append(resident[valid])
        result['segment'].append(ix)
        result['start_s'].append(t0_s[ix]+first[valid]*duration)
        result['end_s'].append(t0_s[ix]+last[valid]*duration)
    return {name: np.concatenate(parts) if parts else np.empty(0, np.int16 if name == 'scenario'
            else np.intp if name in ('resident', 'segment') else np.float64)
            for name, parts in result.items()}


def bins_from_intervals(resident, start_s, end_s, *, offsets_s=0, width_s=300):
    """Map positive-duration half-open intersections to inclusive recording bins.

    offsets_s is scalar or one value per interval, converting source time to
    the fixed bin clock. For example, pass resident_utc_offsets[resident] to
    align recording bins with local midnight. The last
    occupied bin is ceil(end/width)-1, so a pass ending exactly on a boundary
    does not count the following recording. Returns arrays without expanding
    them; parent can merge ranges or pack a base 5-minute bitmap.
    """
    resident = np.asarray(resident, dtype=np.intp)
    start_s, end_s = np.asarray(start_s), np.asarray(end_s)
    if width_s <= 0:
        raise ValueError('Bin width must be positive')
    if np.any(end_s <= start_s):
        raise ValueError('Intervals must have strictly positive duration')
    offset = np.asarray(offsets_s)
    if offset.ndim and offset.shape != start_s.shape:
        raise ValueError('Offsets must be scalar or have one value per interval')
    first = np.floor((start_s+offset)/width_s).astype(np.int64)
    last = (np.ceil((end_s+offset)/width_s)-1).astype(np.int64)
    return resident, first, last


def merge_intervals(resident, start_s, end_s):
    """Union intervals by resident for unique occupied duration checks."""
    resident = np.asarray(resident, dtype=np.intp)
    start_s, end_s = np.asarray(start_s), np.asarray(end_s)
    if len(resident) == 0:
        return resident, start_s, end_s
    order = np.lexsort((end_s, start_s, resident))
    ids, starts, ends = resident[order], start_s[order], end_s[order]
    out_ids, out_starts, out_ends = [], [], []
    rid, lo, hi = ids[0], starts[0], ends[0]
    for new_id, begin, end in zip(ids[1:], starts[1:], ends[1:]):
        if new_id == rid and begin <= hi:
            hi = max(hi, end)
        else:
            out_ids.append(rid); out_starts.append(lo); out_ends.append(hi)
            rid, lo, hi = new_id, begin, end
    out_ids.append(rid); out_starts.append(lo); out_ends.append(hi)
    return np.array(out_ids, dtype=np.intp), np.array(out_starts), np.array(out_ends)
