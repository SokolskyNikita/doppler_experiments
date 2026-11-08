"""What every task of a scoring pool shares, sent once per worker by the pool's initializer."""
from __future__ import annotations

SCORE_CHUNK = 250       # triples (or fine points) per task when scoring across a pool
SCORE_STATE: dict = {}


def set_score_state(state: dict):
    """Pool initializer: what every scoring task shares, sent once per worker instead of with each task."""
    SCORE_STATE.clear()
    SCORE_STATE.update(state)
