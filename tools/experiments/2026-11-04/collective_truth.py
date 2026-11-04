"""A diagnostic, not a judged result: the second design's fine stage at a case's true point, which reads the labels on
purpose (docs/experiments/2026-11-04-collective-find.md, "The second design's first read"). Oyster Bay's true coarse
cell ranks 1,698 of 3,852 at +-25 %; is the coarse span too sparse to see the true pair there, or do the windows not
hold it?

One unit per case: the same detection, windows, coarse CPA table and whole-box fine nulls as collective_run.py, then the
fine stage on the true coarse cell's 100 points plus the reference point itself, two ways:
- clock free: the run's own clock vote, sum and matched windows at the reference point;
- true clock: every CPA row at the reference point scored for every window at the case's reference clock (the
  residual shift +-8 s free), without the vote, so a window's best flight there is whatever its own evidence prefers.
Per window: the best flight, its f0 and z, and the true pair's own best z.

Unit truth2 adds pair_detail: the true flights' segments, coverage and the find test's brightness per window.

usage: uv run python tools/experiments/2026-11-04/collective_truth.py [RUN] [--shard K/N] [--resume DIR ...] [--inputs]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data")); sys.path.insert(0, str(HERE))
import shards  # noqa: E402
from bench import cases, runner  # noqa: E402
from collective_run import DETECT  # noqa: E402

UNITS = ["oyster-bay--truth2"]


def per_window(rows, wins, segs, pair):
    """For each window: its best row (flight, f0, z, shift) and the true pair's best z."""
    out = []
    for w, win in enumerate(wins):
        m = rows[rows["w"] == w]
        if not len(m):
            out.append(dict(t_cpa=win.t_cpa, f0_coarse=win.f0, best=None, pair_z={p: None for p in pair})); continue
        r = m.loc[m["z"].idxmax()]
        icao = m["seg"].map(lambda s: segs[int(s)].icao)
        out.append(dict(t_cpa=win.t_cpa, f0_coarse=win.f0,
                        best=dict(icao=segs[int(r.seg)].icao, f0_hz=float(win.f0 * r.f0_scale), z=float(r.z), score=float(r.s),
                                  clock=float(r.b)),
                        pair_z={p: (float(m["z"][icao == p].max()) if (icao == p).any() else None) for p in pair}))
    return out


def pair_detail(case, sp, wins, views, nulls, segs, obs, c, b_true, sweep, pair):
    """Why a true flight scores what it does in each window: its segments' coverage of the window's times and their own
    scores (the collective find scores each segment as its own CPA row), the joined curve's score through the same
    LogView, and the find test's brightness (objective_fn) on this window and on the saved-fit window, with f0 and the
    clock free as the find test had them."""
    import importlib.util
    from dopplertrack.score import modelled_curve
    spec = importlib.util.spec_from_file_location("find_test", HERE / "find_test.py")
    ft = importlib.util.module_from_spec(spec); spec.loader.exec_module(ft)
    clock0 = -b_true
    shifts, offsets = sweep.shifts(), sweep.offsets()
    saved = runner.saved_fit_dicts(cases.blind_case(case["id"]))
    out = {}
    for p in pair:
        parts = [(i, modelled_curve(s, obs, c)) for i, s in enumerate(segs) if s.icao == p]
        if not parts:
            out[p] = None; continue
        t_all = np.concatenate([q[1][0] for q in parts]); r_all = np.concatenate([q[1][1] for q in parts])
        o = np.argsort(t_all); t_all, r_all = t_all[o], r_all[o]
        rows = []
        for w, (win, view, nl) in enumerate(zip(wins, views, nulls)):
            seg_rows = []
            for i, (to, r) in parts:
                cov = float(np.isfinite(np.interp(view.tq - b_true, to, r, left=np.nan, right=np.nan)).mean())
                if cov == 0:
                    continue
                s = float(view.sweep_scores(to + b_true, r, shifts, offsets).max())
                seg_rows.append(dict(segment=i, coverage=cov, score=s, z=(s - nl["median"]) / nl["sigma"]))
            if not seg_rows:
                continue
            cov_j = float(np.isfinite(np.interp(view.tq - b_true, t_all, r_all, left=np.nan, right=np.nan)).mean())
            s_j = float(view.sweep_scores(t_all + b_true, r_all, shifts, offsets).max())
            tt, score = ft.objective_fn(sp, win.t_start, win.t_end, 0.45 * win.f0, 2.0 * win.f0, "brightness")
            best = -np.inf
            for dlt in np.arange(-30.0, 30.01, 0.5):
                rr = np.interp(tt + clock0 + dlt, t_all, r_all, left=np.nan, right=np.nan)
                if np.all(np.isfinite(rr)):
                    for f0 in np.arange(0.75 * win.f0, 1.25 * win.f0, 0.25):
                        best = max(best, score(f0 * rr))
            rows.append(dict(window=w, t_cpa=win.t_cpa, segments=seg_rows, joined=dict(coverage=cov_j, score=s_j,
                             z=(s_j - nl["median"]) / nl["sigma"]), find_test_brightness_this_window=float(best)))
        sv = []
        for k, ev in enumerate(saved):
            tt, score = ft.objective_fn(sp, ev["t_start"], ev["t_end"], 95.0, 195.0, "brightness")
            best = -np.inf
            for dlt in np.arange(-30.0, 30.01, 0.5):
                rr = np.interp(tt + clock0 + dlt, t_all, r_all, left=np.nan, right=np.nan)
                if np.all(np.isfinite(rr)):
                    for f0 in np.arange(95.0, 195.01, 0.25):
                        best = max(best, score(f0 * rr))
            if np.isfinite(best):
                sv.append(dict(saved_event=k + 1, t_start=ev["t_start"], t_end=ev["t_end"], find_test_brightness=float(best)))
        out[p] = dict(n_segments=len(parts), windows=rows, saved_fit=sv)
    return out


def run_unit(cid):
    from dopplertrack import collective as col
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.geo import haversine_m
    from dopplertrack.pipeline import cached_cpa_table
    from dopplertrack.search import Grid, build_segments, cpa_table
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import detect_events
    case = cases.latest_case(cid)
    lab = cases.case_labels(cid, case["version"])
    ref, pair = lab["reference"], lab.get("true_pair") or []
    b_true = -float(case["reference_clock_utc"]["audio_zero_utc_unix_s"])
    sp = Spectrogram.load(runner.resolve(case["spectrogram"]))
    found = cached_detections(sp, detect_events, **DETECT)
    usable = sorted([e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)], key=lambda e: -e.score)[:10]
    wins = [col.Window.from_detection(e) for e in usable]
    traces, _ = join_days(runner.trace_paths(case))
    elevation = Terrain().elevation if case["search"]["dem"] else None
    c, rng = speed_of_sound(), case["search"]["max_range_m"]
    coarse = Grid.make(*case["search"]["bbox"], col.COARSE_M, elevation)
    e0, e1 = coarse.enu[:, 0].min() - rng - col.COARSE_M, coarse.enu[:, 0].max() + rng + col.COARSE_M
    n0, n1 = coarse.enu[:, 1].min() - rng - col.COARSE_M, coarse.enu[:, 1].max() + rng + col.COARSE_M
    segs = build_segments(traces, coarse.lat0, coarse.lon0, clip_enu=(e0, e1, n0, n1))
    cache = runner.resolve(f"cpa/collective/{Path(case['search']['cpa_cache']).stem}_2km.npz"); cache.parent.mkdir(parents=True, exist_ok=True)
    cpa_c = cached_cpa_table(coarse, segs, rng, c, str(cache))
    sw_f = col.fine_sweep()
    views_f = [col.LogView(w, sp, sw_f.n) for w in wins]
    nulls_f = col.window_nulls(views_f, wins, cpa_c, segs, coarse.enu, c, sw_f)          # the run's own fine nulls
    d = np.array([haversine_m(la, lo, ref["lat"], ref["lon"]) for la, lo in zip(coarse.lat, coarse.lon)])
    gi = int(np.argmin(d))
    cell, _ = col.fine_grid(coarse, [gi], elevation, coarse.lat0, coarse.lon0)
    el = elevation(np.array([ref["lat"]]), np.array([ref["lon"]])) if elevation else np.zeros(1)
    lat = np.r_[cell.lat, ref["lat"]]; lon = np.r_[cell.lon, ref["lon"]]
    elev = np.r_[elevation(cell.lat, cell.lon) if elevation else np.zeros(len(cell)), el]
    fine = Grid.points(lat, lon, np.where(np.isfinite(elev), elev, 0.0), lat0=coarse.lat0, lon0=coarse.lon0)
    g_ref = len(fine) - 1
    cpa_f = cpa_table(fine, segs, max_range_m=rng, c=c)
    # clock free: the run's own vote and sum
    cand = col.candidates(cpa_f, wins)
    scored = col.collective_scores(cand, cpa_f, views_f, nulls_f, segs, fine.enu, c, sw_f)
    pts = col.point_scores(scored, len(wins)).sort_values("Z", ascending=False)
    at_ref = pts[pts.gidx == g_ref]
    free = dict(cell_best_Z=float(pts.Z.max()) if len(pts) else None, ref_Z=float(at_ref.Z.iloc[0]) if len(at_ref) else None,
                ref_clock=float(at_ref.b.iloc[0]) if len(at_ref) else None)
    if len(at_ref):
        free["matched"], _ = col.matched_at(scored, g_ref, float(at_ref.b.iloc[0]), segs, wins)
    free["windows"] = per_window(scored[scored.gidx == g_ref], wins, segs, pair)
    # true clock: every row at the reference point, every window, the clock fixed
    rows = cpa_f[cpa_f["gidx"] == g_ref].reset_index(drop=True)
    import pandas as pd
    tc = pd.DataFrame({"row": np.tile(np.arange(len(rows)), len(wins)), "gidx": g_ref,
                       "w": np.repeat(np.arange(len(wins)), len(rows)).astype(np.int16), "b": b_true})
    scored_t = col.collective_scores(tc, rows, views_f, nulls_f, segs, fine.enu, c, sw_f)
    wt = per_window(scored_t, wins, segs, pair)
    true = dict(b_true=b_true, windows=wt, Z_sum=float(sum(max(w["best"]["z"], 0.0) for w in wt if w["best"])),
                Z_pair=float(sum(max(v or 0.0, 0.0) for w in wt for v in w["pair_z"].values())))
    detail = pair_detail(case, sp, wins, views_f, nulls_f, segs, fine.enu[g_ref], c, b_true, sw_f, pair)
    return dict(case=cid, reference=ref, true_pair=pair, true_cell=dict(lat=float(coarse.lat[gi]), lon=float(coarse.lon[gi]), d_m=float(d[gi])),
                windows=[w.__dict__ for w in wins], clock_free=free, true_clock=true, pair_detail=detail,
                nulls=[{k: n[k] for k in ("median", "sigma")} for n in nulls_f])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        from bench import inputs as bench_inputs
        doc = bench_inputs.run_inputs(sorted({u.split("--")[0] for u in UNITS}), "locate")
        shards.print_inputs(doc["cases"], doc["inputs"], [], tuple(doc["cache_kinds"]))     # the saved fits are repo files
        return
    run = shards.open_run(a.run, "collective-truth", {"script": "tools/experiments/2026-11-04/collective_truth.py",
                                                      "params": dict(units=UNITS, detect=DETECT)})
    units = shards.Units(run, UNITS, dict(units=UNITS, detect=DETECT), a.shard, a.resume)
    for uid in units.todo():
        d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
        r = run_unit(uid.split("--")[0])
        (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")
        units.finish(uid, {"ref_Z_free": r["clock_free"]["ref_Z"], "Z_true_clock": r["true_clock"]["Z_sum"]})
        print(uid, json.dumps({"free": {k: r["clock_free"][k] for k in ("cell_best_Z", "ref_Z", "ref_clock")},
                               "true": {k: r["true_clock"][k] for k in ("b_true", "Z_sum", "Z_pair")},
                               "per_window_true": [(w["t_cpa"], w["f0_coarse"], w["best"], w["pair_z"]) for w in r["true_clock"]["windows"]]},
                              default=float), flush=True)


if __name__ == "__main__":
    main()
