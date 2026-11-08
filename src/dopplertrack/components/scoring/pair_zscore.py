"""Robust z-scores summed: each event's score standardised against its own decoy null (target-decoy, Elias & Gygi
2007), z_k = (s_k - median_k) / sigma_k, then z1 + z2: Stouffer's combination without its 1/sqrt(k) (ours; Stouffer
1949 is not in the folder)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pair_zscore(res: pd.DataFrame, nulls: list[dict]) -> pd.DataFrame:
    """res (keys score, s1, s2) with the key raw_score = the old s1 + s2, z1 and z2 from the two events' nulls
    (NaN where a null's sigma is not positive), and score = z1 + z2. Changes res in place and returns it."""
    res["raw_score"] = res["score"]
    for k, nl in ((1, nulls[0]), (2, nulls[1])):
        res[f"z{k}"] = (res[f"s{k}"] - nl["median"]) / nl["sigma"] if nl["sigma"] > 0 else np.nan
    res["score"] = res["z1"] + res["z2"]
    return res
