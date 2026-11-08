"""A time-difference gate (a one-dimensional rectangular gate, Blackman & Popoli 1999 §6.3.1) done as a band join:
(grid point, segment 1, segment 2) triples whose CPA times are dt_offset apart within tol_s, found through time
buckets of width 2 tol_s with a +-1 bucket overlap."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.search.negative_information_filter import negative_information_filter


def join_pairs(a: pd.DataFrame, b: pd.DataFrame, cpa: pd.DataFrame, dt_offset: float, tol_s: float,
               time_col: str = "t_heard", silence_d_m: float | None = 6000.0, silence_margin_s: float = 40.0,
               funnel: dict | None = None, triples: dict | None = None) -> pd.DataFrame:
    """The time-difference gate |t2 - t1 - dt_offset| <= tol_s as a band join, then the negative-information
    filter (negative_information_filter; silence_d_m None skips it), on rows already admitted for event 1 (a) and
    event 2 (b); cpa is the whole table, which the filter needs. The funnel keys are `time_join` (`emission_gate`
    for emission times) and `silence`."""
    funnel = {} if funnel is None else funnel
    w = 2.0 * tol_s
    a = a.assign(key=np.floor(a[time_col].to_numpy() / w).astype(np.int64))
    kb = np.floor((b[time_col].to_numpy() - dt_offset) / w).astype(np.int64)
    parts = [a.merge(b.assign(key=kb + off), on=["gidx", "key"], suffixes=("1", "2")) for off in (-1, 0, 1)]
    m = pd.concat(parts, ignore_index=True).drop(columns="key")
    m = m[(m.seg1 != m.seg2) & ((m[time_col + "2"] - m[time_col + "1"] - dt_offset).abs() <= tol_s)].copy()
    gate = "time_join" if time_col == "t_heard" else "emission_gate"
    funnel[gate] = len(m)
    if triples is not None:
        triples[gate] = stage_triples(m)
    if silence_d_m is not None:
        m = negative_information_filter(m, cpa, silence_d_m, silence_margin_s)
    funnel["silence"] = len(m)
    if triples is not None:
        triples["silence"] = stage_triples(m)
    return m.reset_index(drop=True)


def stage_triples(m: pd.DataFrame) -> dict:
    """The (grid point, segment 1, segment 2) columns of a set of triples, as int32 arrays."""
    return {k: m[k].to_numpy(np.int32) for k in ("gidx", "seg1", "seg2")}
