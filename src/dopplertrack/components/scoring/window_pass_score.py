"""A pass's curve integral in a window: the best over the sweep (shift, f0 scale) of its own heard curve at a point
(maximised over nuisance parameters, Kay 1998 §7.6.4), and each (row, window)'s z against the window's decoy null.
These are the per-window values that point_scores combines (Axelrad 2011's individual correlograms)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dopplertrack.components.scoring.modelled_curve import modelled_curve

CHUNK = 400
_STATE: dict = {}


def _set_state(state):
    _STATE.clear(); _STATE.update(state)


def _score_chunk(task):
    """For each (observer ENU, segment, heard time, window index, clock): the best score over the sweep and the
    clock it implies. The curve is computed once per (observer, segment) and reused for its windows."""
    obs, seg, t_heard, widx, offs = task
    views, segs, c, sw = _STATE["views"], _STATE["segs"], _STATE["c"], _STATE["sweep"]
    shifts, offsets, scales = sw.shifts(), sw.offsets(), sw.f0_scales()
    out_s, out_b, out_f = np.zeros(len(seg)), np.zeros(len(seg)), np.zeros(len(seg))
    cache = {}
    for i in range(len(seg)):
        key = (int(seg[i]), float(obs[i][0]), float(obs[i][1]))
        if key not in cache:
            cache = {key: modelled_curve(segs[int(seg[i])], obs[i], c)}
        to, r = cache[key]
        sc = views[int(widx[i])].sweep_scores(to + offs[i], r, shifts, offsets)
        k, j = np.unravel_index(int(np.argmax(sc)), sc.shape)
        out_s[i], out_b[i], out_f[i] = float(sc.max()), float(offs[i] + shifts[k]), float(scales[j])
    return out_s, out_b, out_f


def run_tasks(tasks, state, workers):
    from dopplertrack.runtime.parallel import ordered_map, resolve_jobs
    jobs = min(resolve_jobs(workers), max(len(tasks), 1))
    try:
        parts = list(ordered_map(_score_chunk, tasks, jobs, _set_state, (state,)))
    finally:
        _STATE.clear()
    if not parts:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def pass_tasks(enu, gidx, seg, t_heard, widx, offs):
    order = np.lexsort((widx, seg, gidx))                  # a (point, segment)'s windows together, for the curve cache
    cols = [enu[gidx[order]], seg[order], t_heard[order], widx[order], offs[order]]
    return order, [tuple(c[a:a + CHUNK] for c in cols) for a in range(0, len(order), CHUNK)]


# old name: collective_scores
def pass_zscores(cand: pd.DataFrame, cpa: pd.DataFrame, views, nulls, segs, enu, c, sweep, workers=None) -> pd.DataFrame:
    """z of each kept (row, window) at its best clock: a robust z-score, (s - median) / sigma of the window's
    decoy null."""
    rows = cand["row"].to_numpy()
    g = cpa["gidx"].to_numpy()[rows]; s = cpa["seg"].to_numpy()[rows]; th = cpa["t_heard"].to_numpy()[rows]
    w = cand["w"].to_numpy(); offs = cand["b"].to_numpy()
    order, tasks = pass_tasks(enu, g, s, th, w, offs)
    used = {int(k) for k in np.unique(s)}
    sc, bb, ff = run_tasks(tasks, {"views": views, "segs": {k: segs[k] for k in used}, "c": c, "sweep": sweep}, workers)
    out = pd.DataFrame({"gidx": g[order], "seg": s[order], "w": w[order], "t_heard": th[order], "s": sc, "b": bb, "f0_scale": ff})
    med = np.array([n["median"] for n in nulls]); sig = np.array([n["sigma"] for n in nulls])
    out["z"] = (out["s"] - med[out["w"]]) / sig[out["w"]]
    return out
