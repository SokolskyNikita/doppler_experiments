"""Greedy assignment (Blackman & Popoli 1999 §1.3.2, p.46) of windows to passes: candidate matches ranked by z and
accepted in turn, each window and each pass used at most once at a grid point and clock bin."""
from __future__ import annotations

import numpy as np
import pandas as pd

AGREE_S = 6.0                 # windows sum at a point only where their best clocks agree within +-AGREE_S
PASS_FALLBACK = 3              # a window's best passes per clock bin offered to the greedy assignment (its alternates)


# old name: clock_matches
def greedy_assignment(scored: pd.DataFrame, one_pass: bool = True, clock_bin: int | None = None,
                      agree_s: float = AGREE_S, pass_fallback: int = PASS_FALLBACK) -> pd.DataFrame:
    """Greedy assignment (Blackman & Popoli 1999 p.46): the positive-z matches in descending z, each accepted only when
    neither its window nor its pass is already taken at that grid point and clock bin. Each window offers its
    pass_fallback (PASS_FALLBACK) best passes per bin; clocks are binned at agree_s (AGREE_S) / 2 and each match spread over +-2 bins. Like any
    greedy assignment it need not reach the best total (ibid.). With one_pass=False there is no assignment: each
    window's best match per bin. Shared by scoring and reporting."""
    pos = scored[scored["z"] > 0].copy()
    pos["bin"] = np.floor(pos["b"] / (agree_s / 2)).astype(np.int64)
    pos["pass"] = np.round(pos["t_heard"].to_numpy(float)).astype(np.int64)
    pos = pos.sort_values("z", ascending=False, kind="stable")
    best = pos.groupby(["gidx", "w", "bin"]).head(pass_fallback if one_pass else 1)
    spread = pd.concat([best.assign(bin=best["bin"] + d) for d in range(-2, 3)], ignore_index=True)
    if clock_bin is not None:
        spread = spread[spread["bin"] == clock_bin]
    spread = spread.sort_values("z", ascending=False, kind="stable")
    if not one_pass:
        return spread.drop_duplicates(["gidx", "w", "bin"])
    # A rejected alternate must not reserve its pass: both the window and the pass are taken only on acceptance.
    used_windows, used_passes, keep = set(), set(), []
    columns = (spread[k].to_numpy() for k in ("gidx", "bin", "w", "seg", "pass"))
    for i, (g, b, w, seg, heard) in enumerate(zip(*columns)):
        window, flight_pass = (g, b, w), (g, b, seg, heard)
        if window not in used_windows and flight_pass not in used_passes:
            used_windows.add(window)
            used_passes.add(flight_pass)
            keep.append(i)
    return spread.iloc[keep]
