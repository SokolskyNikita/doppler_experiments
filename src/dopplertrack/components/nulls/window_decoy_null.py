"""Window decoy nulls after the target-decoy strategy (Elias & Gygi 2007, p. 1): each window scored by the same
scorer against uniformly drawn CPA rows anchored on its coarse CPA; their median and MADN. Not Efron's empirical
null, which is fitted to the tested statistics themselves."""
# old module: dopplertrack.components.nulls.window_null
from __future__ import annotations

import numpy as np

from dopplertrack.components.nulls.robust import draw_rows, null_seed, median_madn, sample_sha256
from dopplertrack.components.scoring.window_pass_score import pass_tasks, run_tasks

NULL_N = 1000


# old name: window_nulls
def window_decoy_nulls(views, wins, cpa, segs, enu, c, sweep, workers=None, n=NULL_N) -> list[dict]:
    """Each window's decoy null: NULL_N CPA rows drawn uniformly (seeded by the window), each pass anchored on the
    window's coarse CPA and scored with the same sweep. Nearly all are wrong passes, so the median and MADN are the
    window's floor and spread, as in the comparable score's event_decoy_null."""
    out = []
    for w, win in enumerate(wins):
        seed = null_seed((round(win.t_start, 3), round(win.t_end, 3), round(win.f0, 4), round(win.t_cpa, 4), sweep))
        idx = draw_rows(len(cpa), n, seed)
        g, s, th = (cpa[k].to_numpy()[idx] for k in ("gidx", "seg", "t_heard"))
        offs = win.t_cpa - th
        _, tasks = pass_tasks(enu, g, s, th, np.full(len(idx), w), offs)
        used = {int(k) for k in np.unique(s)}
        sc, _, _ = run_tasks(tasks, {"views": views, "segs": {k: segs[k] for k in used}, "c": c, "sweep": sweep}, workers)
        med, sig = median_madn(sc)
        out.append({"median": med, "sigma": max(sig, 1e-9), "n": n, "seed": seed,
                    "sample_sha256": sample_sha256(idx),
                    "f0_sweep": [1 - sweep.f0_span, 1 + sweep.f0_span], "anchor_s": win.t_cpa})
    return out
