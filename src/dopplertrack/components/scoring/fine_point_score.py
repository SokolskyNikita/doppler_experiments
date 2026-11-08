"""The fine stage of a coarse-to-fine grid search (Axelrad 2011, Direct Positioning and Fig. 16): at each fine point,
custom_locked_score plus every extra event's curve integral at the same shift, summed non-coherently."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.scoring.trajectory_score import custom_locked_score
from dopplertrack.core.atmosphere import point_sound_speed
from dopplertrack.runtime.pool_state import SCORE_STATE


def score_fine_points(task) -> list[tuple]:
    """refine's row for each fine point of a chunk: (lat, lon, score, s1, s2, s3..., shift), the output keys. The
    sweeps come from the pool state: shifts and f0_scales for the pair, extra_f0_scales for the extra events."""
    from dopplertrack.components.scoring.modelled_curve import modelled_curve
    from dopplertrack.core.geometry import lla_to_enu
    st = SCORE_STATE
    c, seg1, temp = st["c"], st["seg1"], st.get("temperature_c")
    rows = []
    for lat, lon, elev in zip(*task):
        obs = lla_to_enu(lat, lon, elev, *st["origin"])
        d = np.linalg.norm(seg1.enu - obs, axis=1); j = int(np.argmin(d))
        cj = c if temp is None else float(point_sound_speed(temp, seg1.enu[j, 2] - obs[2]))
        t_heard1 = seg1.t[j] + d[j] / cj
        tot, s1, s2, sh = custom_locked_score(st["w1"], st["w2"], seg1, st["seg2"], obs, float(t_heard1), c=c,
                                              shifts=st["shifts"], f0_scales=st["f0_scales"], temperature_c=temp)
        t0_map = st["t_cpa1"] - float(t_heard1)
        xs = []
        for seg, w in zip(st["xsegs"], st["xwins"]):
            to, r = modelled_curve(seg, obs, c, temp)
            xs.append(float(w.sweep_scores(to + t0_map, r, [sh], st["extra_f0_scales"]).max()))
        rows.append((lat, lon, tot + sum(xs), s1, s2, *xs, sh))
    return rows
