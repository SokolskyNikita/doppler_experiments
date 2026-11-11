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

import dataclasses

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.search.grid import Grid
from dopplertrack.components.search.segments import build_segments, clip_box
from dopplertrack.components.search.cpa_table import cpa_table
from dopplertrack.components.assignment.clock_vote import clock_votes
from dopplertrack.components.assignment.pass_window import greedy_assignment
from dopplertrack.components.nulls.window_decoy_null import window_decoy_nulls
from dopplertrack.components.planning.coarse_cells import keep_cells
from dopplertrack.components.planning.modes import modes
from dopplertrack.components.planning.fine_grid import fine_grid
from dopplertrack.components.scoring.event_window_view import EventWindowView
from dopplertrack.components.scoring.log_view import LogView
from dopplertrack.components.scoring.point_score import matched_at, point_scores
from dopplertrack.components.scoring.sweeps import Sweep
from dopplertrack.components.scoring.window_pass_score import pass_zscores
from dopplertrack.components.windows import Window
from dopplertrack.methods.collective.parameters import CollectiveParameters, SweepParameters, check
from dopplertrack.methods.parameters import to_dict


# Historical v4 used sequential pass/window deduplication. The repaired greedy assignment changes Z;
# its positive cases and maximum-over-search null must be calibrated together under this new identity.
STATISTIC = "collective-Z-greedy-v1"

# The collective recipe's method choices: the name in the parameters, and the method it selects.
VIEWS = {"log_view": LogView, "event_window": EventWindowView}      # the curve integral each window scores a pass by
ASSIGNMENTS = {"greedy_assignment": greedy_assignment}              # windows to passes; exact matching joins in G4
# How a result merged from only_cells units takes its modes (merge.merge_units): the winning unit's own list, as the
# dated merge took the best cell's record, or the mode rule applied again across every unit's list.
MODE_MERGES = ("best_unit", "all_units")


def _sweep(s: SweepParameters, params: CollectiveParameters) -> Sweep:
    sc = params.scoring
    return Sweep(s.shift_s, s.shift_step_s, sc.f0_span + s.f0_span_extra, s.f0_step, s.n,
                 log_du=float(np.log1p(sc.log_step)), sub_s=sc.sub_s)


def _shown(sweep: Sweep) -> dict:
    """The sweep as the output has always shown it: its repr fields (log_du and sub_s are in `parameters`)."""
    return {f.name: getattr(sweep, f.name) for f in dataclasses.fields(sweep) if f.repr}


def statistic_identity(params: CollectiveParameters) -> dict:
    """What a collective Z is a value of: the statistic's name, the hash of the code that computes and merges it
    (cache.code_sha256 of collective_detection and merge_units: every dopplertrack module they import, runtime
    left out), the hash of the fully resolved parameters, and `id`, the hash of those three. Two results are values
    of one statistic, and so may be merged or set against one another as own day and null, only when their
    identities are equal. Written into every output."""
    from dopplertrack.methods.collective.merge import merge_units
    from dopplertrack.runtime.cache import code_sha256, entry_key
    ident = {"name": STATISTIC, "code_sha256": code_sha256(collective_detection, merge_units),
             "parameters_sha256": entry_key(to_dict(check(params)))}
    return {**ident, "id": entry_key(ident)}


def statistic_label(identity: dict) -> str:
    """The identity as a launcher label (a run topic, a unit name): the name and the first 12 digits of its id."""
    return f"{identity['name']}-{identity['id'][:12]}"


def search_domain(wins: list[Window], bbox, elevation) -> dict:
    """What a search ran over besides the recording and the traffic: the box, whether the grids sit on terrain, and
    the windows. An own-day search and its null draws must share it."""
    from dopplertrack.runtime.cache import entry_key
    return {"bbox": [float(x) for x in bbox], "terrain": elevation is not None,
            "windows_sha256": entry_key({"windows": [dataclasses.asdict(w) for w in wins]})}


# old name: collective_find
def collective_detection(sp: Spectrogram, wins: list[Window], traces, bbox, params: CollectiveParameters | None = None,
                         *, elevation=None, workers=None, log=print, cpa_cache=None, only_cells=None) -> dict:
    """Coarse-to-fine collective detection over a box. Returns the coarse map (every cell with Z > 0), the kept cells and
    the margin rule's numbers, the fine map's winner, its clock and each window's matched pass, the distinct peaks (key
    `modes`) and the stages' counts, with the fully resolved parameters under `parameters`. Every setting is a field of
    params (CollectiveParameters; the defaults when None). With only_cells (ranks into the kept cells, 0 the highest),
    the fine stage visits just those cells: the coarse stage and every null are the same as the full run's, so the
    cells' results combine by maximum (merge.merge_units).

    Empty inputs end in winner None with a reason, never an exception: no windows, no flight pass within range of
    the box, no point with two windows' clocks agreeing, and no fine point with terrain elevation. A fine point
    without terrain elevation is left out and counted (counts.fine_points_without_terrain)."""
    import time
    from dopplertrack.runtime.cpa_cache import cached_cpa_table
    p = check(params or CollectiveParameters())
    pl, sc, a = p.planning, p.scoring, p.assignment
    c = p.speed_of_sound()
    view = VIEWS[sc.view]
    assign = dict(agree_s=a.agree_s, pass_fallback=a.pass_fallback, assign=ASSIGNMENTS[a.method])
    log_du = float(np.log1p(sc.log_step))

    def views(sweep):
        return [view(w, sp, sweep.n_for(w.t_end - w.t_start), pad_s=sc.crop_pad_s, f_lo=sc.crop_f_lo,
                     f_hi=sc.crop_f_hi, log_du=log_du, sub_s=sc.sub_s, spectral_floor=p.spectrogram.spectral_floor)
                for w in wins]
    counts, walls = {}, {}
    sw_c, sw_f = _sweep(sc.coarse_sweep, p), _sweep(sc.fine_sweep, p)
    base = dict(statistic=STATISTIC, statistic_identity=statistic_identity(p), domain=search_domain(wins, bbox, elevation),
                coarse_map=dict(lat=[], lon=[], Z=[], clock=[], n_matched=[]), counts=counts, walls=walls,
                windows=[w.__dict__ for w in wins], sweeps={"coarse": _shown(sw_c), "fine": _shown(sw_f)},
                parameters=to_dict(p))
    if not wins:
        return dict(base, winner=None, reason="no windows were given")
    t = time.perf_counter()
    coarse = Grid.make(*bbox, pl.coarse_m, elevation)
    segs = build_segments(traces, coarse.lat0, coarse.lon0, clip_enu=clip_box(coarse.enu, p.max_range_m + pl.coarse_m))
    cpa_c = cached_cpa_table(coarse, segs, p.max_range_m, c, cpa_cache, workers=workers)
    walls["coarse_cpa"] = time.perf_counter() - t; counts["coarse_points"] = len(coarse); counts["coarse_cpa_rows"] = len(cpa_c)
    if not len(cpa_c):                      # no traffic, or none near: there is no row to draw a window's null from
        return dict(base, winner=None, reason="no flight pass within range of the box")
    views_c = views(sw_c)
    t = time.perf_counter()
    nulls_c = window_decoy_nulls(views_c, wins, cpa_c, segs, coarse.enu, c, sw_c, workers, p.null.null_n)
    cand = clock_votes(cpa_c, wins, a.clock_bin_s)
    counts["coarse_candidates"] = len(cand)
    if not len(cand):
        counts["coarse_max_without_pass_rule"] = 0.0
        return dict(base, winner=None, reason="no point has two windows whose clocks agree")
    scored_c = pass_zscores(cand, cpa_c, views_c, nulls_c, segs, coarse.enu, c, sw_c, workers)
    pts_c = point_scores(scored_c, len(wins), **assign)
    counts["coarse_max_without_pass_rule"] = (float(point_scores(scored_c, len(wins), one_pass=False, **assign).Z.max())
                                              if len(pts_c) else 0.0)
    walls["coarse"] = time.perf_counter() - t
    log(f"coarse: {len(coarse)} points, {len(cand)} candidates, best Z {pts_c.Z.max() if len(pts_c) else 0:.2f}")
    base["coarse_map"] = dict(lat=[float(coarse.lat[g]) for g in pts_c.gidx], lon=[float(coarse.lon[g]) for g in pts_c.gidx],
                              Z=pts_c.Z.astype(float).tolist(), clock=pts_c.b.astype(float).tolist(),
                              n_matched=pts_c.n_matched.astype(int).tolist())
    if not len(pts_c):
        return dict(base, winner=None, reason="no point has a window above its null")
    keep, margin = keep_cells(pts_c, pl.margin_sigma, pl.max_cells)
    base["margin"] = margin
    base["kept"] = [dict(rank=i, lat=float(coarse.lat[int(r.gidx)]), lon=float(coarse.lon[int(r.gidx)]), Z=float(r.Z))
                    for i, r in enumerate(keep.itertuples())]
    ranks = list(range(len(keep))) if only_cells is None else [int(k) for k in only_cells if int(k) < len(keep)]
    base["fine_ranks"] = ranks
    log(f"margin: {margin['margin_cells']} cells within {pl.margin_sigma} sigma ({margin['coarse_sigma']:.2f}) of "
        f"{margin['coarse_max']:.2f}, {margin['kept_cells']} kept; fine stage on ranks {ranks}")
    if not ranks:
        return dict(base, winner=None, reason="no kept cell in only_cells")
    t = time.perf_counter()
    views_f = views(sw_f)
    nulls_f = window_decoy_nulls(views_f, wins, cpa_c, segs, coarse.enu, c, sw_f, workers, p.null.null_n)  # over the whole box
    fine, cell_of = fine_grid(coarse, keep.gidx.to_numpy()[ranks], elevation, coarse.lat0, coarse.lon0, pl.coarse_m,
                              pl.fine_m)
    asked = len(ranks) * int(round(pl.coarse_m / pl.fine_m)) ** 2
    counts.update(fine_points=len(fine), fine_cells=len(ranks), fine_points_without_terrain=asked - len(fine))
    base["nulls"] = {"coarse": nulls_c, "fine": nulls_f}
    if not len(fine):
        return dict(base, winner=None, reason="no fine point has terrain elevation")
    cpa_f = cpa_table(fine, segs, max_range_m=p.max_range_m, c=c, workers=workers)
    cand_f = clock_votes(cpa_f, wins, a.clock_bin_s)
    scored_f = (pass_zscores(cand_f, cpa_f, views_f, nulls_f, segs, fine.enu, c, sw_f, workers) if len(cand_f)
                else None)
    pts_f = point_scores(scored_f, len(wins), **assign) if scored_f is not None else []
    walls["fine"] = time.perf_counter() - t
    counts.update(fine_cpa_rows=len(cpa_f), fine_candidates=len(cand_f))
    log(f"fine: {len(fine)} points in {len(ranks)} cells, {len(cand_f)} candidates, best Z {pts_f.Z.max() if len(pts_f) else 0:.2f}")
    if not len(pts_f):
        return dict(base, winner=None, reason="no fine point has a window above its null")
    pts_f = pts_f.sort_values("Z", ascending=False).reset_index(drop=True)
    w0 = pts_f.iloc[0]
    matched, voters = matched_at(scored_f, int(w0.gidx), float(w0.b), segs, wins, **assign)
    winner = dict(lat=float(fine.lat[int(w0.gidx)]), lon=float(fine.lon[int(w0.gidx)]), Z=float(w0.Z), clock_audio_minus_unix=float(w0.b),
                  n_matched=int(w0.n_matched), windows=matched, voters=voters)
    offered = pts_f if pl.clocks_per_point == 1 else point_scores(scored_f, len(wins), clocks=pl.clocks_per_point, **assign)
    found = modes(offered, fine.lat, fine.lon, pl.mode_separation_m, pl.max_modes, pl.mode_clock_separation_s)
    cell_best = pts_f.assign(cell=cell_of[pts_f.gidx.to_numpy()]).drop_duplicates("cell")
    base["fine_cells"] = [dict(coarse_lat=float(coarse.lat[int(r.cell)]), coarse_lon=float(coarse.lon[int(r.cell)]),
                               lat=float(fine.lat[int(r.gidx)]), lon=float(fine.lon[int(r.gidx)]), Z=float(r.Z))
                          for r in cell_best.itertuples()]
    return dict(base, winner=winner, modes=found, coarse_max=margin["coarse_max"])
