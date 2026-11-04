"""Two follow-ups to the refit test (docs/experiments/2026-11-04-case-weather.md), each a shards.py unit:

  profile-<T>C   Oyster Bay's event 2 (3020-3130 s, 95-195 Hz, harmonics 1, the brightness objective its committed fit
                 used): the objective's best value over (f0, t0) at each (v, d) of a grid, v 100-170 m/s by 2.5, d 3-8 km
                 by 125 m, at 15 C and at 25.6 C. Reports every local optimum of that surface (8-neighbour) with its
                 depth, and the objective at each temperature's fitted optimum on the other temperature's surface: are
                 the 15 C optimum (141 m/s, 5.9 km) and the 25.6 C one (121 m/s, 4.3 km) two basins of comparable depth?
  remake-<T>C    the eagle cam's two events remade as they were made: tracks.detect_events on the full 12 h spectrogram
                 (derived/swfl/rec.npz; 60-300 Hz, harmonics 1, top 40, the defaults otherwise), at 15 C (the control)
                 and at 26.1 C; the two events matched to the committed ranks 5 and 13 by t_cpa (within 30 s), moved to
                 the clip's time (-18000 s), and searched as the case on dev with the weather off (15 C) or on (26.1 C).
                 Criterion (fixed before the run): the 15 C remake gives the true pair rank 1, and the 26.1 C one keeps
                 it at rank 1.

usage: uv run python tools/experiments/2026-11-04/basin_profile.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, inputs as bench_inputs, runner  # noqa: E402

V_GRID = np.arange(100.0, 170.01, 2.5)
D_GRID = np.arange(3000.0, 8000.01, 125.0)
OB_EV2 = dict(window=(3020.0, 3130.0), band=(95.0, 195.0), committed=(132.41, 141.20, 5920.4, 3056.54),
              refit=(129.91, 121.49, 4272.07, 3076.08 - 4272.07 / 346.48))
UNITS = ["profile-15C", "profile-25.6C", "remake-15C", "remake-26.1C"]
EAGLE = "eagle-cam-clip-18000s"
FULL = "derived/swfl/rec.npz"
CLIP_OFFSET = -18000.0


def brightness_surface(c):
    from dopplertrack.audio import Spectrogram
    from dopplertrack.doppler import ideal_curve
    from dopplertrack.tracks import local_whiten
    sp = Spectrogram.load(runner.resolve(cases.latest_case("oyster-bay")["spectrogram"]))
    (t0w, t1w), (f_lo, f_hi) = OB_EV2["window"], OB_EV2["band"]
    pad = 0.3 * (f_hi - f_lo)
    win = local_whiten(sp.crop(t0w - 30, t1w + 30, max(f_lo - pad, sp.f[0]), min(f_hi + pad, sp.f[-1])))
    tt = np.linspace(t0w, t1w, 400)

    def score(f0, v, d, t0):
        return float(np.mean(win.sample(tt, ideal_curve(tt, f0, v, d, t0, c=c))))

    def best_at(v, d, starts):
        best = None
        for f0s, t0s in starts:
            r = minimize(lambda p: -score(p[0], v, d, p[1]), [f0s, t0s], method="Nelder-Mead",
                         options={"xatol": 1e-2, "fatol": 1e-5, "maxiter": 400})
            if best is None or r.fun < best.fun:
                best = r
        return -best.fun, best.x

    starts = [(f0, t0) for f0 in (OB_EV2["committed"][0], OB_EV2["refit"][0]) for t0 in (OB_EV2["committed"][3], OB_EV2["refit"][3])]
    S = np.zeros((len(V_GRID), len(D_GRID))); X = np.zeros((len(V_GRID), len(D_GRID), 2))
    for i, v in enumerate(V_GRID):
        for j, d in enumerate(D_GRID):
            S[i, j], X[i, j] = best_at(v, d, starts)
    peaks = []
    for i in range(len(V_GRID)):
        for j in range(len(D_GRID)):
            nb = S[max(0, i - 1):i + 2, max(0, j - 1):j + 2]
            if S[i, j] >= nb.max():
                peaks.append(dict(v=float(V_GRID[i]), d=float(D_GRID[j]), score=float(S[i, j]), f0=float(X[i, j, 0]), t0=float(X[i, j, 1])))
    peaks.sort(key=lambda p: -p["score"])
    at = {name: best_at(p[1], p[2], [(p[0], p[3])])[0] for name, p in (("committed_15C_optimum", OB_EV2["committed"]),
                                                                       ("refit_25.6C_optimum", OB_EV2["refit"]))}
    return dict(c=c, peaks=peaks[:10], n_peaks=len(peaks), max=float(S.max()), at_optima=at,
                surface=S.round(5).tolist(), v_grid=V_GRID.tolist(), d_grid=D_GRID.tolist())


def remake(t, out_dir):
    from dopplertrack.audio import Spectrogram
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.parallel import default_jobs
    from dopplertrack.tracks import detect_events
    sp = Spectrogram.load(runner.resolve(FULL))
    det = [e.to_dict() for e in detect_events(sp, 60.0, 300.0, c=speed_of_sound(t), harmonics=1, top=40, workers=default_jobs())]
    (out_dir / f"detected_{t:g}C.json").write_text(json.dumps(det, indent=1) + "\n")
    committed = json.loads((REPO / "docs/results/swfl_detected.json").read_text())
    picks = [committed[i - 1] for i in (5, 13)]
    files, matched = [], []
    for k, ev in enumerate(picks, 1):
        near = min(det, key=lambda e: abs(e["t_cpa"] - ev["t_cpa"]))
        if abs(near["t_cpa"] - ev["t_cpa"]) > 30:
            return dict(error=f"no detection within 30 s of committed event {k} at {ev['t_cpa']:.1f} s"), det
        e = dict(near)
        for key in ("t_cpa", "t_cpa_emit", "t_start", "t_end"):
            e[key] += CLIP_OFFSET
        p = out_dir / f"ev{k}_{t:g}C.json"; p.write_text(json.dumps(e, indent=1) + "\n")
        files.append(str(p)); matched.append(dict(committed=ev, remade=near, rank=det.index(near) + 1))
    over = {runner.WEATHER_KEY: True} if t != 15.0 else {}

    def execute(case, case_dir, **kw):
        c = copy.deepcopy(case)
        c["events"] = {"mode": "saved_fits", "files": files, "pick": None, "time_offset_s": 0.0}
        return runner.execute_case(c, case_dir, overrides=over, **kw)
    entry = runner.bench_case(EAGLE, out_dir / "bench", execute=execute, code=runner.code_revision(), log=lambda m: None)
    return dict(entry={k: entry.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m", "top_error_m", "flight_pairs")},
                matched=matched), det


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        doc = bench_inputs.run_inputs([EAGLE, "oyster-bay"], "saved-fit")
        shards.print_inputs(doc["cases"], doc["inputs"] + [FULL, "derived/oyster_bay/rec.npz"], doc["cpa_tables"],
                            tuple(doc["cache_kinds"]))
        return
    params = dict(units=UNITS, v_grid=[100, 170, 2.5], d_grid=[3000, 8000, 125], ob_ev2=OB_EV2, eagle_detect=dict(band=[60, 300], top=40))
    run = shards.open_run(a.run, "basin-profile", {"script": "tools/experiments/2026-11-04/basin_profile.py", "params": params})
    units = shards.Units(run, UNITS, params, a.shard, a.resume)
    if not a.merge:
        from dopplertrack.doppler import speed_of_sound
        for uid in units.todo():
            kind, t = uid.split("-"); t = float(t[:-1])
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            if kind == "profile":
                r = brightness_surface(speed_of_sound(t))
                summary = dict(peaks=r["peaks"][:3], at_optima=r["at_optima"])
            else:
                r, _ = remake(t, d)
                summary = r.get("entry") or r
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")
            units.finish(uid, summary)
            print(uid, json.dumps(summary, default=float)[:600], flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    out = {u: json.loads((d / "result.json").read_text()) for u, d in units.all().items()}
    for u in out:
        out[u].pop("surface", None)
    e15, eT = out["remake-15C"].get("entry", {}), out["remake-26.1C"].get("entry", {})
    out["criterion"] = {"eagle_15C_remake_rank_1": e15.get("true_pair_rank") == 1, "eagle_26.1C_remake_rank_1": eT.get("true_pair_rank") == 1}
    (run / "basin_profile.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
