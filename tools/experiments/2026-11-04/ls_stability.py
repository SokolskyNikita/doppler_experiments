"""Is the least-squares fit on a tracked ridge stable under the sound speed where the brightness fit isn't
(docs/experiments/2026-11-04-case-weather.md, the flat v-d ridge)? Each part a shards.py unit:

  ls-<case>-<T>  the case's two events as tracks.ridge_track + tracks.fit_track (unweighted) in the committed fits'
                 windows: Oyster Bay's README bands (95-200 Hz at harmonic 2, 95-195 Hz), the eagle cam's committed
                 window and a band from its committed curve (0.9 f_post to 1.1 f_pre), at 15 C and at the station
                 temperature; then the case searched with those events, the weather off at 15 C and on at the station
                 temperature.
  lsprof-<T>     Oyster Bay event 2's least-squares objective over the brightness profile's (v, d) grid at 15 C and
                 25.6 C: at each point beta/alpha = -v/c and s = d sqrt(c^2 - v^2)/(v c) are fixed, alpha is solved in
                 closed form and t_c minimised; its local minima counted as the brightness surface's maxima were.

Expectation, written before the run: fit_track solves (alpha, beta, t_c, s) on the track with no c in them, and c only
maps them to v = -beta c/alpha and d = s v c/sqrt(c^2 - v^2), both proportional to c. So on one track, v and d move by
exactly c'/c (1.9 % for Oyster Bay, 2.0 % for the eagle cam) and the criterion (2 +- 1 % on all four events) holds by
construction. The informative parts are the searches and the least-squares surface: one basin against brightness's fifty.

usage: uv run python tools/experiments/2026-11-04/ls_stability.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, inputs as bench_inputs, runner  # noqa: E402

CASES = ("oyster-bay", "eagle-cam-clip-18000s")
OB_TRACKS = [dict(band=(95.0, 200.0), harmonic=2), dict(band=(95.0, 195.0), harmonic=1)]
V_GRID = np.arange(100.0, 170.01, 2.5)
D_GRID = np.arange(3000.0, 8000.01, 125.0)
UNITS = [f"ls-{c}-{t}" for c in CASES for t in ("15C", "T")] + ["lsprof-15C", "lsprof-25.6C"]


def tracks_for(case: dict):
    from dopplertrack.audio import Spectrogram
    from dopplertrack.tracks import ridge_track
    sp = Spectrogram.load(runner.resolve(case["spectrogram"]))
    committed = runner.saved_fit_dicts(case)
    out = []
    for k, ev in enumerate(committed):
        if case["id"] == "oyster-bay":
            s = OB_TRACKS[k]; band, h = s["band"], s["harmonic"]
        else:
            band, h = (0.9 * ev["f_post"], 1.1 * ev["f_pre"]), 1
        out.append(ridge_track(sp, ev["t_start"], ev["t_end"], *band, harmonic=h))
    return out, committed


def ls_unit(cid: str, which: str, out_dir: Path) -> dict:
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.tracks import fit_track
    blind = cases.blind_case(cid)
    t = 15.0 if which == "15C" else blind["weather"]["temperature_c"]
    trs, committed = tracks_for(blind)
    files, fits = [], []
    for k, (tr, ev) in enumerate(zip(trs, committed), 1):
        fit = fit_track(tr, c=speed_of_sound(t))
        e = fit.event(score=ev["score"]).to_dict()
        p = out_dir / f"ev{k}_{t:g}C.json"; p.write_text(json.dumps(e, indent=1) + "\n"); files.append(str(p))
        fits.append(dict(f0=fit.f0, v=fit.v, d=fit.d, t_cpa=fit.t_cpa, n_optima=fit.n_optima, identified=fit.identified,
                         second_optimum_ratio=fit.second_optimum_ratio, rms_hz=fit.rms_hz, z_span=fit.z_span, n=fit.n,
                         committed=dict(f0=ev["f0"], v=ev["v"], d=ev["d"], t_cpa=ev["t_cpa"])))
    over = {runner.WEATHER_KEY: True} if which == "T" else {}

    def execute(case, case_dir, **kw):
        c = copy.deepcopy(case)
        c["events"] = {"mode": "saved_fits", "files": files, "pick": None, "time_offset_s": 0.0}
        return runner.execute_case(c, case_dir, overrides=over, **kw)
    entry = runner.bench_case(cid, out_dir / "bench", execute=execute, code=runner.code_revision(), log=lambda m: None)
    return dict(temperature_c=t, fits=fits,
                entry={k: entry.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m", "top_error_m", "flight_pairs")})


def ls_surface(t: float) -> dict:
    from scipy.optimize import minimize_scalar
    from dopplertrack.doppler import speed_of_sound
    c = speed_of_sound(t)
    trs, _ = tracks_for(cases.blind_case("oyster-bay"))
    tt, g, _ = trs[1].usable()
    tt = tt - tt[0]

    def rss_at(v, d, tc):
        s = d * np.sqrt(c * c - v * v) / (v * c)
        z = (tt - tc) / np.sqrt(s * s + (tt - tc) ** 2)
        h = 1 - (v / c) * z
        a = float(np.dot(g, h) / np.dot(h, h))
        r = g - a * h
        return float(r @ r)

    span = tt[-1] - tt[0]
    S = np.zeros((len(V_GRID), len(D_GRID)))
    for i, v in enumerate(V_GRID):
        for j, d in enumerate(D_GRID):
            grid = np.linspace(tt[0] - 0.5 * span, tt[-1] + 0.5 * span, 121)
            k = int(np.argmin([rss_at(v, d, x) for x in grid]))
            lo, hi = grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]
            S[i, j] = minimize_scalar(lambda x: rss_at(v, d, x), bounds=(lo, hi), method="bounded").fun
    mins = []
    for i in range(len(V_GRID)):
        for j in range(len(D_GRID)):
            nb = S[max(0, i - 1):i + 2, max(0, j - 1):j + 2]
            if S[i, j] <= nb.min():
                mins.append(dict(v=float(V_GRID[i]), d=float(D_GRID[j]), rss=float(S[i, j])))
    mins.sort(key=lambda m: m["rss"])
    return dict(c=c, n_minima=len(mins), minima=mins[:10], min=float(S.min()), surface=S.round(6).tolist(),
                v_grid=V_GRID.tolist(), d_grid=D_GRID.tolist())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        doc = bench_inputs.run_inputs(list(CASES), "saved-fit")
        shards.print_inputs(doc["cases"], doc["inputs"], doc["cpa_tables"], tuple(doc["cache_kinds"]))
        return
    params = dict(units=UNITS, ob_tracks=OB_TRACKS, eagle_band="0.9 f_post to 1.1 f_pre of the committed fit",
                  v_grid=[100, 170, 2.5], d_grid=[3000, 8000, 125], weighted=False)
    run = shards.open_run(a.run, "ls-stability", {"script": "tools/experiments/2026-11-04/ls_stability.py", "params": params})
    units = shards.Units(run, UNITS, params, a.shard, a.resume)
    if not a.merge:
        for uid in units.todo():
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            if uid.startswith("lsprof-"):
                r = ls_surface(float(uid.split("-")[1][:-1]))
                summary = dict(n_minima=r["n_minima"], minima=r["minima"][:3])
            else:
                _, rest = uid.split("-", 1)
                cid, which = rest.rsplit("-", 1)
                r = ls_unit(cid, which, d)
                summary = r["entry"]
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")
            units.finish(uid, summary)
            print(uid, json.dumps(summary, default=float)[:600], flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    out = {u: json.loads((d / "result.json").read_text()) for u, d in units.all().items()}
    for u in out:
        out[u].pop("surface", None)
    moves = {}
    for cid in CASES:
        f15, fT = out[f"ls-{cid}-15C"]["fits"], out[f"ls-{cid}-T"]["fits"]
        for k, (x, y) in enumerate(zip(f15, fT), 1):
            moves[f"{cid}-ev{k}"] = dict(v_pct=100 * (y["v"] / x["v"] - 1), d_pct=100 * (y["d"] / x["d"] - 1))
    out["moves"] = moves
    out["criterion"] = {"all_four_move_2_pm_1_pct": all(1.0 <= m["v_pct"] <= 3.0 and 1.0 <= m["d_pct"] <= 3.0 for m in moves.values())}
    (run / "ls_stability.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float)[:8000])


if __name__ == "__main__":
    main()
