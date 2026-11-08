"""Collective detection after Axelrad 2011 (Direct Positioning: per-window values added non-coherently at each point
of a position/clock grid): Z(x) = max over clocks of the sum over windows of max(z, 0), and the matches it used.
Axelrad sums unclipped correlation powers; the z-standardisation and the floor at 0 are ours."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.assignment.pass_window import AGREE_S, greedy_assignment


def point_scores(scored: pd.DataFrame, n_windows: int, one_pass: bool = True) -> pd.DataFrame:
    """Z(x) = max over clocks of sum over windows of max(z, 0) (key Z), the windows' best clocks agreeing within
    +-AGREE_S: clocks are binned at AGREE_S / 2, and a window's z at a bin is its best within two bins either side.
    With one_pass (the design's section 1, enforced from the fourth step), a pass, a segment's CPA at the point,
    explains only its best window at a point and clock, by greedy assignment (Blackman & Popoli 1999 p. 46); a
    window whose best pass is taken falls back to its next (of PASS_FALLBACK)."""
    per = greedy_assignment(scored, one_pass)
    if not len(per):
        return pd.DataFrame(columns=["gidx", "Z", "b", "n_matched"])
    step = AGREE_S / 2
    tot = per.groupby(["gidx", "bin"]).agg(Z=("z", "sum"), n_matched=("w", "nunique")).reset_index()
    top = tot.sort_values("Z", ascending=False).drop_duplicates("gidx")
    top["b"] = (top["bin"] + 0.5) * step
    return top[["gidx", "Z", "b", "n_matched"]].reset_index(drop=True)


def matched_at(scored: pd.DataFrame, gidx: int, b: float, segs, wins) -> tuple[list, list]:
    """The matches used by point_scores at the winning clock bin, plus all windows with a candidate there."""
    step = AGREE_S / 2
    b0 = int(np.floor(b / step))
    here = scored[(scored["gidx"] == gidx)]
    here = here[np.abs(np.floor(here["b"] / step).astype(np.int64) - b0) <= 2]
    voters = sorted({int(w) for w in here["w"]})
    taken = greedy_assignment(here, clock_bin=b0)
    here = pd.concat([taken, here[~here["w"].isin(taken["w"]) & (here["z"] <= 0)]])
    out = []
    for w, win in enumerate(wins):
        m = here[here["w"] == w]
        if not len(m):
            out.append(None); continue
        r = m.loc[m["z"].idxmax()]
        if r.z <= 0:
            out.append({"z": float(r.z), "score": float(r.s)}); continue
        out.append({"flight": segs[int(r.seg)].icao, "icao": segs[int(r.seg)].icao, "segment": int(r.seg),
                    "pass_cpa_utc": float(r.t_heard), "harmonic": 1, "f0_hz": float(win.f0 * r.f0_scale),
                    "shift_s": float(r.b - b), "clock": float(r.b), "score": float(r.s), "z": float(r.z)})
    return out, voters
