"""Decoy null after the target-decoy strategy (Elias & Gygi 2007, p. 1): an event's custom_single_score against
uniformly drawn CPA rows, each wrong flight anchored on the event and scored by the same scorer. Not Efron's
empirical null, which is fitted to the tested statistics themselves."""
# old module: dopplertrack.components.nulls.event_null
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.nulls.robust import draw_rows, null_seed, median_madn, sample_sha256
from dopplertrack.components.scoring.curve_integral import EventWindow
from dopplertrack.components.scoring.trajectory_score import custom_single_score
from dopplertrack.components.search.types import Segment
from dopplertrack.runtime.parallel import ordered_map, resolve_jobs
from dopplertrack.runtime.pool_state import SCORE_CHUNK, SCORE_STATE, set_score_state

NULL_N = 1000          # CPA rows per event in the comparable score's null


def _null_scores(task) -> list[float]:
    """custom_single_score of one event against a chunk of (observer ENU, segment, heard time) rows: each wrong
    flight anchored on the event's heard CPA, as custom_locked_score anchors event 1, with the same sweeps."""
    obs, seg, t_heard = task
    w, segs, c, sweep = SCORE_STATE["w"], SCORE_STATE["segs"], SCORE_STATE["c"], SCORE_STATE.get("f0_scales")
    kw = {} if sweep is None else {"f0_scales": sweep}
    if SCORE_STATE.get("shifts") is not None:
        kw["shifts"] = SCORE_STATE["shifts"]
    if SCORE_STATE.get("temperature_c") is not None:
        kw["temperature_c"] = SCORE_STATE["temperature_c"]
    return [custom_single_score(w, segs[int(k)], o, float(t), c=c, **kw) for o, k, t in zip(obs, seg, t_heard)]


# old name: event_null
def event_decoy_null(w: EventWindow, cpa: pd.DataFrame, segs: list[Segment], enu: np.ndarray, c: float,
               n: int = NULL_N, workers: int | None = None, f0_scales=None, temperature_c: float | None = None,
               shifts=None) -> dict:
    """The comparable score's decoy null for one event: its custom_single_score against n (grid point, flight) rows
    drawn uniformly, with replacement, from the CPA table, each anchored on the event. Nearly all are wrong
    flights (decoys; ours: real wrong flights, rarely the true one, summarised by median and MADN rather than
    counted above a threshold as Elias & Gygi do), so the median and MADN are the event's own floor and spread
    for a robust z-score. The draw's seed comes from the event's fit,
    so every search containing the event uses the same null. f0_scales, if given, is the f0 sweep the event's
    candidates get, so that the null has the same chances to match; shifts likewise (custom_single_score's by default).
    The null's record keeps its keys whatever the sweep."""
    f = w.fit
    seed = null_seed((round(f.t_cpa, 6), round(f.f0, 6), round(f.v, 6), round(f.d, 3), w.harmonics))
    idx = draw_rows(len(cpa), n, seed)
    rows = cpa.iloc[idx]
    cols = [rows[k].to_numpy() for k in ("gidx", "seg", "t_heard")]
    used = np.unique(cols[1])
    tasks = [(enu[cols[0][a:a + SCORE_CHUNK]], cols[1][a:a + SCORE_CHUNK], cols[2][a:a + SCORE_CHUNK])
             for a in range(0, n, SCORE_CHUNK)]
    state = {"w": w, "segs": {int(k): segs[k] for k in used}, "c": c, "f0_scales": f0_scales, "temperature_c": temperature_c,
             "shifts": shifts}
    try:
        s = np.array([x for part in ordered_map(_null_scores, tasks, min(resolve_jobs(workers), max(len(tasks), 1)),
                                                set_score_state, (state,)) for x in part])
    finally:
        SCORE_STATE.clear()
    med, sigma = median_madn(s)
    return {"median": med, "sigma": sigma, "n": n, "seed": seed,
            "f0_sweep": None if f0_scales is None else [float(f0_scales[0]), float(f0_scales[-1]), len(f0_scales)],
            "sample_sha256": sample_sha256(idx)}
