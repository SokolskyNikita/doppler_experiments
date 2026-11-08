"""Track post-processing applied after a tracker. The cuts have no standard name: custom_cut_weak, custom_cut_rise
and custom_cut_hop split a track at a weak run, a rise and a frequency jump (nearest standard idea: Iatsenko 2016
§3.1's penalisation of frequency jumps, which acts inside the path optimisation, not after it). link_gaps joins
broken tracks across short gaps (track segment association; Streit & Barrett 1990 §III leaves reinitiated tracks
open), and resolve_crossings re-pairs tracks at crossings by slope continuity."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.tracking.types import Track, TrackParams


def _split(tr: Track, cut: np.ndarray, p: TrackParams) -> list[Track]:
    """Pieces of tr between the cut points (indices dropped), keeping those of min_track_s."""
    out, i = [], 0
    for j in list(np.nonzero(cut)[0]) + [len(tr.t)]:
        if j > i and tr.t[j - 1] - tr.t[i] >= p.min_track_s and tr.measured[i:j].any():
            pc = tr.piece(i, j)
            m = np.nonzero(pc.measured)[0]
            out.append(pc.piece(int(m[0]), int(m[-1]) + 1))
        i = j + 1
    return out


# old name: cut_weak
def custom_cut_weak(tr: Track, p: TrackParams) -> list[Track]:
    """Drop runs whose whitened level stays below weak_db for longer than weak_run_s."""
    weak = ~(np.nan_to_num(tr.level, nan=-np.inf) >= p.weak_db)
    cut = np.zeros(len(tr.t), bool)
    i = 0
    while i < len(weak):
        if weak[i]:
            j = i
            while j + 1 < len(weak) and weak[j + 1]:
                j += 1
            if tr.t[j] - tr.t[i] > p.weak_run_s:
                cut[i:j + 1] = True
            i = j
        i += 1
    return _split(tr, cut, p)


# old name: rise_points
def custom_rise_points(tr: Track, p: TrackParams, df: float) -> np.ndarray:
    """Indices where the track has risen by more than rise_bins within rise_window_s: a straight
    pass only falls."""
    m = np.nonzero(tr.measured)[0]
    out = []
    lo = 0
    for hi in range(len(m)):
        while tr.t[m[hi]] - tr.t[m[lo]] > p.rise_window_s:
            lo += 1
        seg = tr.f[m[lo:hi + 1]]
        if len(seg) > 1 and tr.f[m[hi]] - np.min(seg) > p.rise_bins * df:
            out.append(int(m[hi]))
    return np.array(out, int)


# old name: cut_rise
def custom_cut_rise(tr: Track, p: TrackParams, df: float, flag_only: bool = False) -> list[Track]:
    """Cut at the first point of each rise (custom_rise_points); with flag_only, keep the track whole and
    record the rise in tr.flags["rise"] instead."""
    r = custom_rise_points(tr, p, df)
    if flag_only or len(r) == 0:
        if len(r):
            tr.flags["rise"] = tr.t[r].tolist()
        return [tr]
    cut = np.zeros(len(tr.t), bool)
    starts = r[np.r_[True, np.diff(r) > 1]]
    cut[starts] = True
    return _split(tr, cut, p)


# old name: cut_hop
def custom_cut_hop(tr: Track, p: TrackParams, df: float, flag_only: bool = False) -> list[Track]:
    """Cut at a step more than hop_factor times the track's own slope over the neighbouring
    hop_window_s (and at least two bins): a jump onto another line. With flag_only, keep the
    track whole and record the steps in tr.flags["hop"] instead."""
    m = np.nonzero(tr.measured)[0]
    if len(m) < 3:
        return [tr]
    tm, fm = tr.t[m], tr.f[m]
    step = np.abs(np.diff(fm)) / np.diff(tm)
    cut = np.zeros(len(tr.t), bool)
    for i in range(len(step)):
        near = (np.abs(tm[1:] - tm[i + 1]) <= p.hop_window_s) & (np.arange(len(step)) != i)
        local = np.median(step[near]) if near.any() else 0.0
        if abs(fm[i + 1] - fm[i]) > max(2 * df, p.hop_factor * local * (tm[i + 1] - tm[i])):
            cut[m[i + 1]] = True
    if not cut.any():
        return [tr]
    if flag_only:
        tr.flags["hop"] = tr.t[cut].tolist()
        return [tr]
    pieces, i = [], 0
    for j in [int(k) for k in np.nonzero(cut)[0]] + [len(tr.t)]:   # keep the cut point as the next piece's start
        if j > i and tr.t[j - 1] - tr.t[i] >= p.min_track_s and tr.measured[i:j].any():
            pieces.append(tr.piece(i, j))
        i = j
    return pieces


def _extrapolate(tr: Track, t: float, span: float, from_end: bool) -> float:
    m = tr.measured & np.isfinite(tr.f)
    sel = m & ((tr.t >= tr.end - span) if from_end else (tr.t <= tr.start + span))
    tt, ff = tr.t[sel], tr.f[sel]
    if len(tt) < 2:
        return float(ff[-1] if from_end else ff[0]) if len(ff) else np.nan
    a, b = np.polyfit(tt - tt.mean(), ff, 1)
    return float(a * (t - tt.mean()) + b)


def link_gaps(tracks: list[Track], p: TrackParams, df: float, dt: float) -> list[Track]:
    """Join a track to the next one that starts within link_gap_s of its end and within
    link_tol_bins of its linear extrapolation (fitted over its last 2 s); the result has an
    explicit gap."""
    tracks = sorted(tracks, key=lambda tr: tr.start)
    used = [False] * len(tracks)
    out = []
    for i, a in enumerate(tracks):
        if used[i]:
            continue
        cur = a
        while True:
            best = None
            for j, b in enumerate(tracks):
                if used[j] or b is a or b.start <= cur.end or b.start - cur.end > p.link_gap_s:
                    continue
                err = abs(_extrapolate(cur, b.start, 2.0, True) - b.f[b.measured][0])
                if err <= p.link_tol_bins * df and (best is None or err < best[0]):
                    best = (err, j)
            if best is None:
                break
            j = best[1]; b = tracks[j]; used[j] = True
            n_gap = max(int(round((b.start - cur.end) / dt)) - 1, 0)
            gap_t = cur.end + dt * np.arange(1, n_gap + 1)
            nan = np.full(n_gap, np.nan)
            cur = Track(np.r_[cur.t, gap_t, b.t], np.r_[cur.f, nan, b.f], np.r_[cur.amp, nan, b.amp],
                        np.r_[cur.level, nan, b.level], np.r_[cur.measured, np.zeros(n_gap, bool), b.measured],
                        np.r_[cur.bins, np.full(n_gap, -1), b.bins], {**cur.flags, "linked": cur.flags.get("linked", 0) + 1})
        used[i] = True
        out.append(cur)
    return out


def resolve_crossings(tracks: list[Track], p: TrackParams, df: float, span: float = 2.0) -> list[Track]:
    """Where two tracks overlapping in time come within crossing_bins, re-pair their four ends
    by slope continuity if swapping the tails fits better than keeping them."""
    tracks = list(tracks)
    changed = True
    while changed:
        changed = False
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                a, b = tracks[i], tracks[j]
                common = np.intersect1d(a.t[a.measured], b.t[b.measured])
                if len(common) == 0:
                    continue
                fa = np.interp(common, a.t[a.measured], a.f[a.measured])
                fb = np.interp(common, b.t[b.measured], b.f[b.measured])
                close = np.abs(fa - fb) <= p.crossing_bins * df
                if not close.any() or close.all():
                    continue
                tc = float(common[np.argmin(np.abs(fa - fb))])
                if tc - max(a.start, b.start) < span or min(a.end, b.end) - tc < span:
                    continue
                def slope(tr, lo, hi):
                    sel = tr.measured & (tr.t >= lo) & (tr.t <= hi)
                    return np.polyfit(tr.t[sel], tr.f[sel], 1)[0] if sel.sum() >= 2 else np.nan
                sa0, sa1 = slope(a, tc - span, tc - span / 4), slope(a, tc + span / 4, tc + span)
                sb0, sb1 = slope(b, tc - span, tc - span / 4), slope(b, tc + span / 4, tc + span)
                keep = abs(sa0 - sa1) + abs(sb0 - sb1)
                swap = abs(sa0 - sb1) + abs(sb0 - sa1)
                if np.isfinite(swap) and swap < keep:
                    ka, kb = a.t <= tc, b.t <= tc
                    na = _concat(a, ka, b, ~kb); nb = _concat(b, kb, a, ~ka)
                    na.flags["crossing"] = nb.flags["crossing"] = tc
                    tracks[i], tracks[j] = na, nb
                    changed = True
    return tracks


def _concat(a: Track, ma: np.ndarray, b: Track, mb: np.ndarray) -> Track:
    return Track(np.r_[a.t[ma], b.t[mb]], np.r_[a.f[ma], b.f[mb]], np.r_[a.amp[ma], b.amp[mb]],
                 np.r_[a.level[ma], b.level[mb]], np.r_[a.measured[ma], b.measured[mb]],
                 np.r_[a.bins[ma], b.bins[mb]], dict(a.flags))
