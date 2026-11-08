"""Harmonic sets (Eddy 1980 §§I, III) from tracks: overlapping tracks whose frequency ratio holds near p/q are linked,
and each connected group gets the smallest consistent harmonic orders. Ours: sets are built from measured tracks
by ratio tests, not by Eddy's likelihood-ratio receiver."""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np

from dopplertrack.components.tracking.types import HarmonicLink, Track, TrackParams


def harmonic_links(tracks: list[Track], p: TrackParams, min_overlap_s: float = 2.0) -> list[HarmonicLink]:
    ratios = sorted({Fraction(a, b) for a in range(1, p.max_order + 1) for b in range(1, a + 1)})
    out = []
    for i, a in enumerate(tracks):
        for j, b in enumerate(tracks):
            if j <= i:
                continue
            common, ia, ib = np.intersect1d(a.t[a.measured], b.t[b.measured], return_indices=True)
            if len(common) < 2 or common[-1] - common[0] < min_overlap_s:
                continue
            fa, fb = a.f[a.measured][ia], b.f[b.measured][ib]
            lo, hi, swap = (fa, fb, False) if np.median(fb) >= np.median(fa) else (fb, fa, True)
            r = hi / lo
            med = float(np.median(r)); iqr = float(np.subtract(*np.percentile(r, [75, 25]))) / med
            fr = min(ratios, key=lambda x: abs(med / float(x) - 1))
            if fr == 1 or abs(med / float(fr) - 1) > p.harmonic_tol or iqr > p.harmonic_iqr:
                continue
            pp, qq = fr.numerator, fr.denominator
            if swap:
                pp, qq = qq, pp
            out.append(HarmonicLink(i, j, pp, qq, med if not swap else 1 / med, iqr, float(common[-1] - common[0])))
    return out


def harmonic_groups(tracks: list[Track], links: list[HarmonicLink]) -> list[dict]:
    """Connected tracks with their orders: f_j/f_i = p/q fixes order_j/order_i; orders are scaled
    to the smallest integers, so lines at 2, 4 and 6 read 1, 2 and 3. A link inconsistent with its
    group's orders is dropped."""
    adj: dict[int, list[tuple[int, Fraction]]] = {i: [] for i in range(len(tracks))}
    for lk in links:
        adj[lk.i].append((lk.j, Fraction(lk.p, lk.q)))
        adj[lk.j].append((lk.i, Fraction(lk.q, lk.p)))
    seen, groups = set(), []
    for root in range(len(tracks)):
        if root in seen:
            continue
        order = {root: Fraction(1)}
        stack = [root]
        while stack:
            i = stack.pop()
            for j, r in adj[i]:
                if j not in order:
                    order[j] = order[i] * r
                    stack.append(j)
        seen |= set(order)
        den = math.lcm(*(o.denominator for o in order.values()))
        ints = {i: int(o * den) for i, o in order.items()}
        g = math.gcd(*ints.values())
        ints = {i: o // g for i, o in ints.items()}
        strength = float(sum(np.nansum(np.maximum(tracks[i].level, 0)) for i in ints))
        groups.append({"tracks": sorted(ints), "orders": ints, "strength": strength})
    return groups
