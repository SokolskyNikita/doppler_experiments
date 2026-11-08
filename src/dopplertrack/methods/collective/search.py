"""Collective detection and direct positioning (Axelrad et al. 2011, Combining Satellites and Direct Positioning), with
departures marked (ours): every detected window against every flight's own heard curve, combined non-coherently at each
grid point and shared clock. Design: docs/experiments/designs/2026-11-04-collective-find.md.

For a grid point x and a clock b (audio = unix + b), each window w scores the best pass near it:
    z(x, b, w) = (s - median_w) / sigma_w,  s = sweep_scores of the pass's own heard curve at x in w,
with f0 free over the window's coarse tone and a residual shift; the point's score is
    Z(x, b) = sum over w of max(z, 0),  Z(x) = max over b.
A window no pass explains adds 0, so it can't veto a point. Windows keep only their bounds, a coarse tone and a coarse
heard CPA (the clock prior); the straight-pass v and d are not used.

Departures from Axelrad (ours): z is standardised on each window's decoy null (median and MADN), where Axelrad shifts by
the noise floor and scales by the noise level; each window's term is floored at 0, where Axelrad sums unclipped
correlation powers; windows are matched to passes by greedy assignment, which Axelrad's known satellite codes don't
need; a coarse cell takes the maximum over its span, where Axelrad's averaged correlogram sums over it; and the fine
stage visits every coarse cell within a margin of the maximum, where Axelrad re-centres on the one peak.

The search is coarse to fine (the proposal's section 4, corrected): a COARSE_M grid scored as the maximum over its
cell's span (the residual shift and the f0 sweep widened to cover it), then the FINE_M grid inside the coarse cells
within MARGIN_SIGMA x the coarse map's spread of its maximum, at most MAX_CELLS of them (the second design step: a fixed
top 5 pruned Oyster Bay's true cell). Each candidate takes its own tone over +-F0_SPAN of detection's coarse tone,
scored through a LogView over its best SUB_S stretch of the window (the third design step, with COARSE_M at 1 km: a
diagnostic at Oyster Bay's true cell found that position, not the sweep's density, is what a 2 km cell's span missed, and
that a 240 s window's mean halves a line about 110 s long). The fine stage's window nulls are drawn over the whole box (the coarse CPA table), so a fine
cell's scores depend on no other cell, and `only_cells` runs a subset of the kept cells as one fleet unit.
"""
from __future__ import annotations



from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.core.propagation import speed_of_sound
from dopplertrack.components.search.grid import Grid
from dopplertrack.components.search.segments import build_segments, clip_box
from dopplertrack.components.search.cpa_table import cpa_table
from dopplertrack.components.assignment.clock_vote import clock_votes
from dopplertrack.components.nulls.window_decoy_null import NULL_N, window_decoy_nulls
from dopplertrack.components.planning.coarse_cells import MARGIN_SIGMA, keep_cells
from dopplertrack.components.planning.modes import modes
from dopplertrack.components.planning.fine_grid import COARSE_M, fine_grid
from dopplertrack.components.scoring.log_view import LogView
from dopplertrack.components.scoring.point_score import matched_at, point_scores
from dopplertrack.components.scoring.sweeps import F0_SPAN, coarse_sweep, fine_sweep
from dopplertrack.components.scoring.window_pass_score import pass_zscores
from dopplertrack.components.windows import Window


# Historical v4 used sequential pass/window deduplication. The repaired greedy assignment changes Z;
# its positive cases and maximum-over-search null must be calibrated together under this new identity.
STATISTIC = "collective-Z-greedy-v1"


# old name: collective_find
def collective_detection(sp: Spectrogram, wins: list[Window], traces, bbox, *, max_range_m=12000.0, c=None, elevation=None,
                    f0_span=F0_SPAN, workers=None, log=print, cpa_cache=None, null_n=NULL_N, only_cells=None) -> dict:
    """Coarse-to-fine collective detection over a box. Returns the coarse map (every cell with Z > 0), the kept cells and
    the margin rule's numbers, the fine map's winner, its clock and each window's matched pass, the distinct peaks (key
    `modes`) and the
    stages' counts. With only_cells (ranks into the kept cells, 0 the highest), the fine stage visits just those cells:
    the coarse stage and every null are the same as the full run's, so the cells' results combine by maximum."""
    import time
    from dopplertrack.runtime.cpa_cache import cached_cpa_table
    c = speed_of_sound() if c is None else c
    counts, walls = {}, {}
    t = time.perf_counter()
    coarse = Grid.make(*bbox, COARSE_M, elevation)
    segs = build_segments(traces, coarse.lat0, coarse.lon0, clip_enu=clip_box(coarse.enu, max_range_m + COARSE_M))
    cpa_c = cached_cpa_table(coarse, segs, max_range_m, c, cpa_cache, workers=workers)
    sw_c, sw_f = coarse_sweep(f0_span), fine_sweep(f0_span)
    views_c = [LogView(w, sp, sw_c.n_for(w.t_end - w.t_start)) for w in wins]
    walls["coarse_cpa"] = time.perf_counter() - t; counts["coarse_points"] = len(coarse); counts["coarse_cpa_rows"] = len(cpa_c)
    t = time.perf_counter()
    nulls_c = window_decoy_nulls(views_c, wins, cpa_c, segs, coarse.enu, c, sw_c, workers, null_n)
    cand = clock_votes(cpa_c, wins)
    counts["coarse_candidates"] = len(cand)
    scored_c = pass_zscores(cand, cpa_c, views_c, nulls_c, segs, coarse.enu, c, sw_c, workers)
    pts_c = point_scores(scored_c, len(wins))
    counts["coarse_max_without_pass_rule"] = float(point_scores(scored_c, len(wins), one_pass=False).Z.max()) if len(scored_c) else 0.0
    walls["coarse"] = time.perf_counter() - t
    log(f"coarse: {len(coarse)} points, {len(cand)} candidates, best Z {pts_c.Z.max() if len(pts_c) else 0:.2f}")
    coarse_map = dict(lat=[float(coarse.lat[g]) for g in pts_c.gidx], lon=[float(coarse.lon[g]) for g in pts_c.gidx],
                      Z=pts_c.Z.astype(float).tolist(), clock=pts_c.b.astype(float).tolist(),
                      n_matched=pts_c.n_matched.astype(int).tolist())
    base = dict(statistic=STATISTIC, coarse_map=coarse_map, counts=counts, walls=walls, windows=[w.__dict__ for w in wins],
                sweeps={"coarse": sw_c.__dict__, "fine": sw_f.__dict__})
    if not len(pts_c):
        return dict(base, winner=None, reason="no point has a window above its null")
    keep, margin = keep_cells(pts_c)
    base["margin"] = margin
    base["kept"] = [dict(rank=i, lat=float(coarse.lat[int(r.gidx)]), lon=float(coarse.lon[int(r.gidx)]), Z=float(r.Z))
                    for i, r in enumerate(keep.itertuples())]
    ranks = list(range(len(keep))) if only_cells is None else [int(k) for k in only_cells if int(k) < len(keep)]
    base["fine_ranks"] = ranks
    log(f"margin: {margin['margin_cells']} cells within {MARGIN_SIGMA} sigma ({margin['coarse_sigma']:.2f}) of {margin['coarse_max']:.2f}, "
        f"{margin['kept_cells']} kept; fine stage on ranks {ranks}")
    if not ranks:
        return dict(base, winner=None, reason="no kept cell in only_cells")
    t = time.perf_counter()
    views_f = [LogView(w, sp, sw_f.n_for(w.t_end - w.t_start)) for w in wins]
    nulls_f = window_decoy_nulls(views_f, wins, cpa_c, segs, coarse.enu, c, sw_f, workers, null_n)     # over the whole box
    fine, cell_of = fine_grid(coarse, keep.gidx.to_numpy()[ranks], elevation, coarse.lat0, coarse.lon0)
    cpa_f = cpa_table(fine, segs, max_range_m=max_range_m, c=c, workers=workers)
    cand_f = clock_votes(cpa_f, wins)
    scored_f = pass_zscores(cand_f, cpa_f, views_f, nulls_f, segs, fine.enu, c, sw_f, workers)
    pts_f = point_scores(scored_f, len(wins))
    walls["fine"] = time.perf_counter() - t
    counts.update(fine_points=len(fine), fine_cells=len(ranks), fine_cpa_rows=len(cpa_f), fine_candidates=len(cand_f))
    log(f"fine: {len(fine)} points in {len(ranks)} cells, {len(cand_f)} candidates, best Z {pts_f.Z.max() if len(pts_f) else 0:.2f}")
    base["nulls"] = {"coarse": nulls_c, "fine": nulls_f}
    if not len(pts_f):
        return dict(base, winner=None, reason="no fine point has a window above its null")
    pts_f = pts_f.sort_values("Z", ascending=False).reset_index(drop=True)
    w0 = pts_f.iloc[0]
    matched, voters = matched_at(scored_f, int(w0.gidx), float(w0.b), segs, wins)
    winner = dict(lat=float(fine.lat[int(w0.gidx)]), lon=float(fine.lon[int(w0.gidx)]), Z=float(w0.Z), clock_audio_minus_unix=float(w0.b),
                  n_matched=int(w0.n_matched), windows=matched, voters=voters)
    found = modes(pts_f, fine.lat, fine.lon)
    cell_best = pts_f.assign(cell=cell_of[pts_f.gidx.to_numpy()]).drop_duplicates("cell")
    base["fine_cells"] = [dict(coarse_lat=float(coarse.lat[int(r.cell)]), coarse_lon=float(coarse.lon[int(r.cell)]),
                               lat=float(fine.lat[int(r.gidx)]), lon=float(fine.lon[int(r.gidx)]), Z=float(r.Z))
                          for r in cell_best.itertuples()]
    return dict(base, winner=winner, modes=found, coarse_max=margin["coarse_max"])
