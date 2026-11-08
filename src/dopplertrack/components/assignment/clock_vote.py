"""Hough-transform voting on the clock (Blackman & Popoli 1999 §17.5.1: a mapping into a parameter space whose cells
collect votes): at each grid point, every (CPA row, window) votes for the clock it implies, and the votes kept are
those whose accumulator bin, with its two neighbours, holds votes of at least two windows."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.windows import Window

# old name: CLUSTER_S
CLOCK_BIN_S = 20.0              # the clock vote's accumulator bin; votes in the same or adjacent bins agree, so two
                                #   windows' clocks within CLOCK_BIN_S always agree and up to 2 x CLOCK_BIN_S may


# old name: candidates
def clock_votes(cpa: pd.DataFrame, wins: list[Window]) -> pd.DataFrame:
    """The clock vote: every (row, window) whose clock b = t_cpa(w) - t_heard lies near another window's vote at the
    same point. Clocks are binned at CLOCK_BIN_S; a (row, window) is kept when its bin and the two beside it hold votes
    of at least two windows: any two within CLOCK_BIN_S of each other are kept, and two up to 2 x CLOCK_BIN_S apart
    can be."""
    g = cpa["gidx"].to_numpy(); th = cpa["t_heard"].to_numpy()
    parts = []
    for w, win in enumerate(wins):
        b = win.t_cpa - th
        parts.append(pd.DataFrame({"row": np.arange(len(cpa)), "gidx": g, "w": np.full(len(cpa), w, np.int16), "b": b,
                                   "bin": np.floor(b / CLOCK_BIN_S).astype(np.int64)}))
    df = pd.concat(parts, ignore_index=True)
    u = df[["gidx", "bin", "w"]].drop_duplicates()
    near = pd.concat([u.assign(bin=u["bin"] + d) for d in (-1, 0, 1)], ignore_index=True).drop_duplicates()
    support = near.groupby(["gidx", "bin"]).size()
    keep = support[support >= 2].reset_index()[["gidx", "bin"]]
    return df.merge(keep, on=["gidx", "bin"], how="inner").reset_index(drop=True)
