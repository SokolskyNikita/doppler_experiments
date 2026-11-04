"""Count nonoverlapping local recording windows intersected by native flight tracks."""
import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from residential_aircraft import xyz
from segment_windows import candidate_pairs, solve_intervals


def daily_schedule(inputs, people, day):
    """One whole diary per resident per local date; availability varies only at diary minute boundaries."""
    states = np.load(inputs / "states.npy")
    weights = np.load(inputs / "original_weights.npy")
    diary_day = pd.read_csv(inputs / "diaries.csv").diaryday.values
    rng = np.random.default_rng(17000 + day.toordinal())
    n = len(people["xyz"])
    uniform = rng.random(n)[:, None]
    local_minute = np.arange(1440)
    # Hours are stored in UTC. U.S. offsets all have whole hours on these dates.
    offsets = []
    for zone in people["zones"]:
        tz = ZoneInfo(str(zone))
        start = day.astimezone(tz).utcoffset()
        end = (day+timedelta(seconds=86399)).astimezone(tz).utcoffset()
        if start != end or start.total_seconds() % 3600:
            raise ValueError("Input date needs subhourly or DST-transition handling")
        offsets.append(int(start.total_seconds()//60))
    offset = np.array(offsets)[people["zone_index"]]
    out = np.zeros((n,1440), dtype=np.uint8)
    for shift in (-1,0):
        date = day + timedelta(days=shift)
        # NHAPS labels Sunday=1. Use weekday/weekend strata to retain stable age weights.
        chosen_day = np.isin(diary_day, [1,7]) == (date.weekday() >= 5)
        chosen = np.empty(n, dtype=np.intp)
        # Re-normalize within each separately weighted age survey and preserve the all-age mix.
        childhood = pd.read_csv(inputs / "diaries.csv").group.values == "child"
        child_draw = rng.random(n) < weights[childhood].sum()
        for kids in (True,False):
            ok = chosen_day & (childhood == kids)
            chosen[child_draw == kids] = rng.choice(np.flatnonzero(ok), (child_draw == kids).sum(),
                                                    p=weights[ok]/weights[ok].sum())
        for utc_offset in np.unique(offset):
            ids = np.flatnonzero(offset == utc_offset)
            local = local_minute + utc_offset
            ix = np.flatnonzero(np.floor_divide(local,1440) == shift)
            minutes = local[ix] % 1440
            raw = states[chosen[ids,None], minutes]
            civil_day = (minutes >= 360) & (minutes < 1320)
            windows_open = uniform[ids] < np.where(civil_day, .266, .259)
            # 0 inactive, 1 indoors closed, 2 indoors open, 3 outdoors.
            env = np.select([raw==0, raw==4, (raw==2)|(raw==3)],
                            [3, 1, np.where(windows_open, 2, 1)], default=0)
            noise_day = (minutes >= 420) & (minutes < 1140)
            out[np.ix_(ids,ix)] = np.where(env>0, env + 3*noise_day + 6*people["region"][ids,None], 0)
    return offset, out


def direct_hits(data, people, radii_file, schedule):
    type_codes = radii_file["types"]
    aircraft = data["aircraft_type"]
    type_idx = np.searchsorted(type_codes, aircraft)
    if np.any(type_idx >= len(type_codes)) or np.any(type_codes[type_idx] != aircraft):
        raise ValueError("Extraction contains unrecognized designators")
    radii = radii_file["radii"].reshape(-1,13)
    max_radius = radii.max(axis=1)
    tree = cKDTree(people["xyz"])
    chunks = []
    shortlist_count = 0
    for base in range(0, len(data["start_s"]), 20000):
        section = slice(base,base+20000)
        alt0, alt1 = data["alt0_m"][section]*.001, data["alt1_m"][section]*.001
        vr = data["vertical_rate_mps"][section]
        mode = np.where(vr>2, 2, np.where(vr < -2, 0, 1))
        type_mode = type_idx[data["aircraft_index"][section]] * 3 + mode
        # Conservative altitude envelope over every sampled site and context.
        available = np.minimum(alt0,alt1) <= max_radius[type_mode] + 5
        if not available.any():
            continue
        def vector(key):
            return data[key][section][available]
        type_mode=type_mode[available]
        alt0, alt1 = alt0[available], alt1[available]
        start, end = vector("start_s").astype(float), vector("end_s").astype(float)
        p0, p1 = xyz(vector("lat0"),vector("lon0")), xyz(vector("lat1"),vector("lon1"))
        seg,res = candidate_pairs(tree,p0,p1,max_radius[type_mode])
        shortlist_count += len(seg)
        if not len(seg):
            continue
        g0, g1 = vector("alt_ref0")==1, vector("alt_ref1")==1
        first_min = (start[seg]//60).astype(np.intp)
        last_min = np.ceil(end[seg]/60).astype(np.intp)-1
        for step in range(1 + int((last_min-first_min).max())):
            minute = first_min + step
            valid = (minute <= last_min) & (minute >= 0) & (minute < 1440)
            ia, ib, minute = seg[valid], res[valid], minute[valid]
            radius = radii[type_mode[ia],schedule[ib,minute]]
            active = radius > 0
            if not active.any():
                continue
            ia, ib, radius = ia[active], ib[active], radius[active]
            # For a given step, recover the UTC minute from the segment's own start.
            hits = solve_intervals(p0, p1, alt0, alt1, start, end, max_radius[type_mode],
                                   people["xyz"], people["height"], people["geoid"], ia, ib,
                                   geometric0=g0, geometric1=g1, pair_radii_km=radius)
            lo = (np.floor(start[hits["segment"]]/60) + step)*60
            left = np.maximum(hits["start_s"],lo)
            right = np.minimum(hits["end_s"],lo+60)
            keep = right > left
            if keep.any():
                chunks.append((hits["resident"][keep],left[keep],right[keep]))
    print(f"KD candidate pairs {shortlist_count}",flush=True)
    if not chunks:
        return np.empty(0,dtype=np.intp),np.empty(0),np.empty(0)
    return tuple(np.concatenate([row[k] for row in chunks]) for k in range(3))


def occupied_union(res, starts, ends):
    if not len(res):
        return res, starts, ends
    order = np.lexsort((starts,res))
    res, starts, ends = res[order], starts[order], ends[order]
    # Separate the ranges numerically by resident before taking a cumulative maximum.
    lifted = 86402. * res
    right_edge = np.maximum.accumulate(ends + lifted)
    first = np.flatnonzero(np.r_[True,(starts+lifted)[1:] > right_edge[:-1]])
    return res[first], starts[first], np.maximum.reduceat(ends,first)


def positive_day(t):
    return np.floor(t/86400)*57600 + np.clip(t%86400-21600,0,57600)


def summarize(res, starts, ends, offset):
    res, starts, ends = occupied_union(res,starts,ends)
    n = len(offset)
    base = np.zeros((n,288),dtype=bool)
    first = (starts//300).astype(np.intp)
    last = np.ceil(ends/300).astype(np.intp)-1
    for k in range(int((last-first).max())+1 if len(res) else 0):
        hits = first+k <= last
        base[res[hits], first[hits]+k] = True
    local_start, local_end = starts + offset[res]*60, ends + offset[res]*60
    daytime = positive_day(local_end)-positive_day(local_start)
    seconds_day=np.bincount(res,weights=daytime,minlength=n)
    seconds_night=np.bincount(res,weights=ends-starts-daytime,minlength=n)
    counts={"unique_seconds_day":seconds_day,"unique_seconds_night":seconds_night}
    for length in [5,10,15,30,60]:
        bins=base.reshape(n,1440//length,length//5).any(axis=2)
        local_time = (np.arange(bins.shape[1])*length + offset[:,None])%1440
        day = (local_time>=360) & (local_time<1320)
        counts[f"day_{length}"]=(bins & day).sum(axis=1).astype(np.uint16)
        counts[f"night_{length}"]=(bins & ~day).sum(axis=1).astype(np.uint16)
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("inputs","track","output"):
        p.add_argument(arg,type=Path)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    clock=time.monotonic()
    day=datetime.fromisoformat(args.track.stem[:10]).replace(tzinfo=timezone.utc)
    def unpack(filename):
        with np.load(filename) as archive:
            return {k:archive[k] for k in archive.files}
    people=unpack(args.inputs/"residents.npz")
    offsets,schedule=daily_schedule(args.inputs,people,day)
    data=unpack(args.track)
    metadata = json.loads(str(data["metadata"]))
    if metadata["date"] != day.date().isoformat():
        raise ValueError("Native archive date does not match its filename")
    print(f"Loaded {len(data['start_s'])} segments in {time.monotonic()-clock:.1f}s",flush=True)
    hits=direct_hits(data,people,unpack(args.inputs/"radii.npz"),schedule)
    counts=summarize(*hits,offsets)
    np.savez_compressed(args.output,**counts)
    summary={k:float(v.sum()) for k,v in counts.items()}
    print(json.dumps(summary),flush=True)
    print(f"Finished in {time.monotonic()-clock:.1f}s",flush=True)


if __name__=="__main__":
    main()
