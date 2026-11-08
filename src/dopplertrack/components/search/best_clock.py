"""Maximisation over a nuisance parameter, the clock, as in the GLRT (Kay 1998 §6.4.2): one row per (grid point,
flight 1, flight 2) triple, the best of the clocks it was scored at."""
from __future__ import annotations

import pandas as pd


def best_clock(res: pd.DataFrame) -> pd.DataFrame:
    """The highest-scoring row of each triple (ties keep the earlier row), in descending score."""
    return res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["gidx", "seg1", "seg2"])
