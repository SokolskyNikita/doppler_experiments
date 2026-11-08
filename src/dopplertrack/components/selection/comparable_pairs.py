"""The `comparable` pair rule's candidates (a repo rule; `comparable` is a --pair-rule value): every pair of the top k
events by score, each earlier first."""
from __future__ import annotations

import itertools

from dopplertrack.components.selection.fields import field


def comparable_pairs(events: list, k: int) -> list[tuple]:
    """Every pair of the k highest-scoring events (fits or their dicts), in the order itertools.combinations gives
    over the score ranking, each pair's earlier heard CPA first. The caller searches each and keeps the best."""
    ordered = sorted(events, key=lambda e: field(e, "score"), reverse=True)
    return [tuple(sorted(p, key=lambda e: field(e, "t_cpa"))) for p in itertools.combinations(ordered[:k], 2)]
