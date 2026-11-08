"""The grid-search peak per flight pair (grid search: Amar & Weiss 2008 §IV): one row per flight pair, its
best-scoring candidate."""
from __future__ import annotations

import pandas as pd


def best_per_pair(res: pd.DataFrame) -> pd.DataFrame:
    """The highest-scoring row of each (icao1, icao2) flight pair (ties keep the earlier row), in descending score."""
    return res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
