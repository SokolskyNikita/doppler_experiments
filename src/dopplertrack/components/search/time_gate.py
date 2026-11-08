"""A gate on absolute time (a one-dimensional rectangular gate, Blackman & Popoli 1999 §6.3.1): CPA rows heard within
a tolerance of a known absolute event time."""
from __future__ import annotations

import pandas as pd


def heard_near(cpa: pd.DataFrame, t_unix: float, tol_s: float) -> pd.DataFrame:
    """The CPA rows whose heard time lies within tol_s of t_unix (unix seconds)."""
    return cpa[(cpa.t_heard - t_unix).abs() <= tol_s]
