"""A gate (Blackman & Popoli 1999 §6.3) on the clock: scored triples whose clock puts the recording's start too far
from its stated start are dropped, as prior bounds on the clock bias limit Axelrad's search (Axelrad 2011,
Acquisition Theory and Methods: warm start)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def clock_gate(res: pd.DataFrame, t_cpa1: float, start_utc: float | None, start_tol_s: float | None,
               tol_s: float) -> pd.DataFrame:
    """res less every triple whose clock puts the recording's start further from start_utc than start_tol_s plus the
    search's own time tolerance tol_s; t_cpa1 is event 1's heard CPA in recording seconds. A triple's score depends
    only on its own events, flights and clock (and the comparable Z on each event's own decoy null), so dropping triples
    after scoring leaves exactly the candidates a gate before scoring would. The counts go into the funnel under
    the key `clock_gate`. With no start_utc, or nothing to gate, res is returned as it is."""
    if start_utc is None or not len(res):
        return res
    start = res["t_heard1"].to_numpy(float) - t_cpa1 - res["shift"].to_numpy(float)
    keep = np.abs(start - start_utc) <= float(start_tol_s or 0.0) + tol_s
    out = res[keep].reset_index(drop=True)
    out.attrs = dict(res.attrs)
    out.attrs["funnel"] = {**res.attrs.get("funnel", {}),
                           "clock_gate": {"before": int(len(res)), "after": int(keep.sum()),
                                          "start_utc": start_utc, "tolerance_s": start_tol_s, "tol_s": tol_s}}
    return out
