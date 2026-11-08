"""Rectangular gates (Blackman & Popoli 1999 §6.3.1) on speed and CPA distance: the CPA rows admitted for each event
of a pair, then joined. The bounds are relative to the fitted values (a fraction of v, a factor range on d) rather
than multiples of a standard deviation (ours)."""
from __future__ import annotations

import pandas as pd

from dopplertrack.components.search.pair_join import join_pairs


# old name: tolerance_box
def rectangular_gate(ev, v_tol: float, d_tol: tuple) -> tuple[tuple[float, float], tuple[float, float]]:
    """The rectangular gate an event admits, (speed range, distance range): its fitted speed within +-v_tol (a fraction) and its CPA
    distance between d_tol[0] and d_tol[1] times the fitted one."""
    return (ev.v * (1 - v_tol), ev.v * (1 + v_tol)), (ev.d * d_tol[0], ev.d * d_tol[1])


# old name: in_box
def in_gate(cpa: pd.DataFrame, v, d) -> pd.DataFrame:
    """The CPA rows inside a rectangular gate: speed in v and distance in d (closed ranges)."""
    return cpa[(cpa.v.between(*v)) & (cpa.d.between(*d))]


def pair_candidates(cpa: pd.DataFrame, dt_offset: float, tol_s: float = 6.0,
                    v1=(0, 1e9), d1=(0, 1e9), v2=(0, 1e9), d2=(0, 1e9),
                    silence_d_m: float | None = 6000.0, silence_margin_s: float = 40.0,
                    funnel: dict | None = None, time_col: str = "t_heard",
                    triples: dict | None = None) -> pd.DataFrame:
    """Grid points that hear an event-1-like CPA then, dt_offset later, an event-2-like CPA: each event's
    rectangular gate, then the time-difference gate (join_pairs).

    time_col is the CPA time the gate compares with dt_offset: "t_heard" (heard CPA, the default) or
    "t_emit" (emission CPA). The negative-information filter always uses heard times.

    The join is on (grid point, time bucket) rather than grid point alone: a grid point in a
    busy region hears hundreds of flights a day, and the unconstrained per-point cross product
    is billions of rows before the time filter. Buckets of width 2*tol_s with a +-1 bucket
    overlap find exactly the pairs within tol_s.

    funnel, if given, receives the row counts after each step: "cpa_rows", "event1_gates",
    "event2_gates", "time_join" ("emission_gate" when time_col is "t_emit") and "silence" (see
    pipeline.pair_grid_search). triples, if given, receives the surviving triples after the time gate and
    after the negative-information filter, under the same keys, as {"gidx", "seg1", "seg2"} int32 arrays."""
    if time_col not in ("t_heard", "t_emit"):
        raise ValueError(f"time_col must be t_heard or t_emit, got {time_col!r}")
    funnel = {} if funnel is None else funnel
    a = in_gate(cpa, v1, d1)
    b = in_gate(cpa, v2, d2)
    funnel.update(cpa_rows=len(cpa), event1_gates=len(a), event2_gates=len(b))
    return join_pairs(a, b, cpa, dt_offset, tol_s, time_col=time_col, silence_d_m=silence_d_m,
                      silence_margin_s=silence_margin_s, funnel=funnel, triples=triples)
