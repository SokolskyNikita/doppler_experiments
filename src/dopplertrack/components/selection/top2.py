"""The `top2` pair rule (a repo rule; `top2` is a --pair-rule value): the two highest-scoring events, the earlier one
first."""
from __future__ import annotations

from dopplertrack.components.selection.fields import field


def top2(events: list) -> tuple:
    """The two highest-scoring events (fits or their dicts), earlier heard CPA first. Equal scores keep the
    events' order. Raises ValueError with fewer than two."""
    if len(events) < 2:
        raise ValueError(f"{len(events)} events; a pair needs two")
    best = sorted(events, key=lambda e: field(e, "score"), reverse=True)[:2]
    return tuple(sorted(best, key=lambda e: field(e, "t_cpa")))
