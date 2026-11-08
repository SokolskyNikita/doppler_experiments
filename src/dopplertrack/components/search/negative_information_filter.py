"""Negative information (Koch 2014 §7.4, pp.164-165: missing but expected detections are informative): a pair is
dropped when its grid point would hear a third flight close by between the two events. Koch includes negative
evidence in the Bayesian likelihood; here it is a hard cut (ours). It assumes no detection lies between the pair:
under the `comparable` pair rule other detected events can, and the cut still drops the pair. The funnel key
`silence` and the flag `--no-silence` keep the old name."""
# old module: dopplertrack.components.search.silence_filter
from __future__ import annotations

import pandas as pd


# old name: silence_filter
def negative_information_filter(m: pd.DataFrame, cpa: pd.DataFrame, silence_d_m: float, silence_margin_s: float) -> pd.DataFrame:
    """The joined triples m (columns gidx, seg1, seg2, t_heard1, t_heard2) less those whose grid point has, in the
    whole CPA table, another segment's CPA within silence_d_m heard more than silence_margin_s after event 1 and
    before event 2: that flight would have been heard between them, and the span is assumed silent."""
    if not len(m):
        return m
    near = cpa[(cpa.d <= silence_d_m) & cpa.gidx.isin(m.gidx.unique())][["gidx", "seg", "t_heard"]]
    x = m[["gidx", "seg1", "seg2", "t_heard1", "t_heard2"]].reset_index().merge(near, on="gidx")
    bad = x[(x.seg != x.seg1) & (x.seg != x.seg2) & (x.t_heard > x.t_heard1 + silence_margin_s)
            & (x.t_heard < x.t_heard2 - silence_margin_s)]
    return m.drop(index=bad["index"].unique())
