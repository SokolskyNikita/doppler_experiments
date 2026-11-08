"""Association hypotheses (Blackman & Popoli 1999 §1.3.2) for every pair of two events' fit hypotheses: triples from
the rectangular gates and the time-difference gate, each pair joined at its own time offset."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.fitting.hypothesis import TAU_REACH_S, admitted
from dopplertrack.components.search.pair_join import join_pairs, stage_triples


def pair_hypotheses(cpa: pd.DataFrame, hyps: list, tol_s: float, emission: bool, silence_d_m, funnel: dict,
                     triples: dict | None) -> pd.DataFrame:
    """Triples for every pair of the two events' hypotheses: each pair's admitted rows, joined at its own time
    offset (and at the window's reach when either tau profile was flat), then the negative-information filter. A
    triple is kept once per event-1 hypothesis, since that sets the clock it is scored at; pair_grid_search keeps each triple's
    best clock after scoring. The funnel counts distinct triples."""
    time_col = "t_emit" if emission else "t_heard"
    gate = "emission_gate" if emission else "time_join"
    funnel.update(cpa_rows=len(cpa), event1_gates=int(admitted(cpa, hyps[0]).sum()),
                  event2_gates=int(admitted(cpa, hyps[1]).sum()),
                  event1_hypotheses=len(hyps[0]), event2_hypotheses=len(hyps[1]))
    parts, gated = [], []
    for i, h1 in enumerate(hyps[0]):
        a = cpa[h1.admits(cpa)]
        for j, h2 in enumerate(hyps[1]):
            b = cpa[h2.admits(cpa)]
            dt = h2.t_cpa_emit - h1.t_cpa_emit if emission else h2.t_cpa - h1.t_cpa
            tol = max(tol_s, TAU_REACH_S) if "tau" in set(h1.weak) | set(h2.weak) else tol_s
            sub: dict = {}
            m = join_pairs(a, b, cpa, dt, tol, time_col=time_col, silence_d_m=silence_d_m, funnel={}, triples=sub)
            gated.append(sub[gate])
            parts.append(m.assign(h1=i, h2=j))
    cols = list(cpa.columns)
    empty = pd.DataFrame({**{f"{k}{n}": pd.Series(dtype=cpa[k].dtype) for k in cols if k != "gidx" for n in (1, 2)},
                          "gidx": pd.Series(dtype=cpa.gidx.dtype), "h1": pd.Series(dtype=int), "h2": pd.Series(dtype=int)})
    pairs = (pd.concat(parts, ignore_index=True) if parts else empty).drop_duplicates(["gidx", "seg1", "seg2", "h1"]).reset_index(drop=True)
    distinct = pairs.drop_duplicates(["gidx", "seg1", "seg2"])
    g = pd.DataFrame({k: np.concatenate([x[k] for x in gated]) if gated else np.zeros(0, np.int32) for k in ("gidx", "seg1", "seg2")})
    g = g.drop_duplicates()
    funnel[gate] = len(g)
    funnel["silence"] = len(distinct)
    if triples is not None:
        triples[gate] = {k: g[k].to_numpy(np.int32) for k in ("gidx", "seg1", "seg2")}
        triples["silence"] = stage_triples(distinct)
    return pairs
