"""The event fit as brightness to find, gated least squares to measure (docs/experiments/2026-11-04-event-fit.md: method,
criteria and expectation written before the run). Each part a shards.py unit:

  gated-<case>-<15C|T>  the case's two events: a track gated +-GATE_BINS bins around the committed brightness fit's curve
                        (h x ideal_curve at 15 C, h = 2 for Oyster Bay event 1) on the original STFT of the case's audio
                        (Hann 8192 at 4 kHz, 0.25 s hop, dB, not whitened), each frame's in-gate peak by quadratic
                        interpolation, dropped when under MARGIN_DB above the frame's local noise (median over +-20 bins
                        around the gate centre, outside +-5); fit by tracks.fit_track at 15 C or the station temperature;
                        then the case searched with those events, the weather off (15 C) or on (station temperature)
  gprof-<T>             Oyster Bay event 2's least-squares objective on its gated track over the brightness profile's v-d
                        grid, at 15 C and 25.6 C, and its local minima

usage: uv run python tools/experiments/2026-11-04/gated_track.py [RUN] [--gate-bins 3] [--shard K/N] [--resume DIR ...] [--merge]
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
HARMONIC = {"oyster-bay": [2, 1], "eagle-cam-clip-18000s": [1, 1]}
SR, NPERSEG, HOP_S = 4000, 8192, 0.25
MARGIN_DB, NOISE_HALF, NOISE_EXCL = 6.0, 20, 5
# truth-side values and the package bound (c^2 correlation, provisional) of the four development events: crb.py's DEV
# and runs/2026-11-04-crb-2/crb.csv
TRUTH = {("oyster-bay", 1): dict(v=136.8, R=6090.0, sd_v=0.7668, sd_R=102.83),
         ("oyster-bay", 2): dict(v=103.5, R=3638.0, sd_v=0.6720, sd_R=72.42),
         ("eagle-cam-clip-18000s", 1): dict(v=99.4, R=2536.0, sd_v=0.1545, sd_R=19.56),
         ("eagle-cam-clip-18000s", 2): dict(v=102.8, R=5986.0, sd_v=0.2962, sd_R=59.14)}
V_GRID = np.arange(100.0, 170.01, 2.5)
D_GRID = np.arange(3000.0, 8000.01, 125.0)
UNITS = [f"gated-{c}-{t}" for c in CASES for t in ("15C", "T")] + ["gprof-15C", "gprof-25.6C"]
_AUDIO = {}


def audio(case):
    from dopplertrack.audio import load_audio
    p = case["audio"]["path"]
    if p not in _AUDIO:
        _AUDIO[p] = load_audio(runner.resolve(p), sr=SR)[0]
    return _AUDIO[p]


def gated_track(case: dict, ev: dict, h: int, gate_bins: int):
    """The track of one event gated around its committed curve, on the original STFT; plus its frame statistics."""
    from dopplertrack.audio import _band, _stft_db
    from dopplertrack.doppler import ideal_curve, speed_of_sound
    from dopplertrack.tracks import Track
    x = audio(case)
    hop = int(round(HOP_S * SR))
    k0 = int(np.ceil((ev["t_start"] * SR - NPERSEG / 2) / hop)); k1 = int(np.floor((ev["t_end"] * SR - NPERSEG / 2) / hop)) + 1
    f, band = _band(SR, NPERSEG, 40.0, 450.0)
    L = _stft_db(x[k0 * hop:(k1 - 1) * hop + NPERSEG], SR, NPERSEG, hop, band)
    t = (NPERSEG / 2 + np.arange(k0, k1) * hop) / SR
    gate = h * ideal_curve(t, ev["f0"], ev["v"], ev["d"], ev["t_cpa_emit"], c=speed_of_sound(15.0))
    df = float(f[1] - f[0])
    out_f, amp, keep, snr = np.full(len(t), np.nan), np.zeros(len(t)), np.zeros(len(t), bool), np.full(len(t), np.nan)
    for k in range(len(t)):
        j = int(round((gate[k] - f[0]) / df))
        lo, hi = max(1, j - gate_bins), min(len(f) - 2, j + gate_bins)
        if hi <= lo:
            continue
        col = L[:, k]
        p = lo + int(np.argmax(col[lo:hi + 1]))
        a, b, cc = col[p - 1], col[p], col[p + 1]
        den = a - 2 * b + cc
        off = 0.5 * (a - cc) / den if den < 0 else 0.0
        out_f[k] = f[p] + np.clip(off, -0.5, 0.5) * df
        idx = np.r_[max(0, j - NOISE_HALF):max(0, j - NOISE_EXCL), min(len(f), j + NOISE_EXCL + 1):min(len(f), j + NOISE_HALF + 1)]
        noise = float(np.median(col[idx])) if len(idx) else np.nan
        snr[k] = b - noise
        keep[k] = snr[k] >= MARGIN_DB
        amp[k] = 10 ** (b / 20)
    track = Track(t, out_f, amp, keep, h)
    return track, dict(frames=len(t), kept=int(keep.sum()), median_snr_db=float(np.nanmedian(snr)),
                       rms_to_gate_hz=float(np.sqrt(np.nanmean(((out_f - gate)[keep]) ** 2))) if keep.any() else None)


def tracks(case: dict, gate_bins: int):
    committed = runner.saved_fit_dicts(case)
    return [(gated_track(case, ev, h, gate_bins), ev) for ev, h in zip(committed, HARMONIC[case["id"]])]


def gated_unit(cid, which, out_dir, gate_bins):
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.tracks import fit_track
    blind = cases.blind_case(cid)
    t = 15.0 if which == "15C" else blind["weather"]["temperature_c"]
    files, fits = [], []
    for k, ((tr, stats), ev) in enumerate(tracks(blind, gate_bins), 1):
        fit = fit_track(tr, c=speed_of_sound(t))
        e = fit.event(score=ev["score"]).to_dict()
        p = out_dir / f"ev{k}_{t:g}C.json"; p.write_text(json.dumps(e, indent=1) + "\n"); files.append(str(p))
        tru = TRUTH[(cid, k)]
        fits.append(dict(f0=fit.f0, v=fit.v, d=fit.d, t_cpa=fit.t_cpa, n_optima=fit.n_optima, identified=fit.identified,
                         rms_hz=fit.rms_hz, z_span=fit.z_span, n=fit.n, track=stats,
                         v_minus_true_in_sd=(fit.v - tru["v"]) / tru["sd_v"], d_minus_true_in_sd=(fit.d - tru["R"]) / tru["sd_R"],
                         committed=dict(v=ev["v"], d=ev["d"]), truth=tru))
    over = {runner.WEATHER_KEY: True} if which == "T" else {}

    def execute(case, case_dir, **kw):
        c = copy.deepcopy(case)
        c["events"] = {"mode": "saved_fits", "files": files, "pick": None, "time_offset_s": 0.0}
        return runner.execute_case(c, case_dir, overrides=over, **kw)
    entry = runner.bench_case(cid, out_dir / "bench", execute=execute, code=runner.code_revision(), log=lambda m: None)
    return dict(temperature_c=t, fits=fits,
                entry={k: entry.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m", "top_error_m", "flight_pairs")})


def surface(t, gate_bins):
    from scipy.optimize import minimize_scalar
    from dopplertrack.doppler import speed_of_sound
    c = speed_of_sound(t)
    (tr, _), _ = tracks(cases.blind_case("oyster-bay"), gate_bins)[1]
    tt, g, _ = tr.usable(); tt = tt - tt[0]
    span = tt[-1] - tt[0]

    def rss_at(v, d, tc):
        s = d * np.sqrt(c * c - v * v) / (v * c)
        z = (tt - tc) / np.sqrt(s * s + (tt - tc) ** 2)
        h = 1 - (v / c) * z
        a = float(np.dot(g, h) / np.dot(h, h)); r = g - a * h
        return float(r @ r)
    S = np.zeros((len(V_GRID), len(D_GRID)))
    grid = np.linspace(tt[0] - 0.5 * span, tt[-1] + 0.5 * span, 121)
    for i, v in enumerate(V_GRID):
        for j, d in enumerate(D_GRID):
            k = int(np.argmin([rss_at(v, d, x) for x in grid]))
            S[i, j] = minimize_scalar(lambda x: rss_at(v, d, x), bounds=(grid[max(k - 1, 0)], grid[min(k + 1, 120)]), method="bounded").fun
    mins = [dict(v=float(V_GRID[i]), d=float(D_GRID[j]), rss=float(S[i, j])) for i in range(len(V_GRID)) for j in range(len(D_GRID))
            if S[i, j] <= S[max(0, i - 1):i + 2, max(0, j - 1):j + 2].min()]
    mins.sort(key=lambda m: m["rss"])
    edge = [m for m in mins if m["v"] in (V_GRID[0], V_GRID[-1]) or m["d"] in (D_GRID[0], D_GRID[-1])]
    return dict(c=c, n_minima=len(mins), n_on_grid_edge=len(edge), minima=mins[:10], n_points=int(len(tt)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--gate-bins", type=int, default=3, help="the gate's half-width in STFT bins (the one counted retune)")
    a = ap.parse_args()
    if a.inputs:
        doc = bench_inputs.run_inputs(list(CASES), "saved-fit")
        extra = [cases.latest_case(c)["audio"]["path"] for c in CASES]
        shards.print_inputs(doc["cases"], list(dict.fromkeys(doc["inputs"] + extra)), doc["cpa_tables"], tuple(doc["cache_kinds"]))
        return
    params = dict(units=UNITS, gate_bins=a.gate_bins, margin_db=MARGIN_DB, noise=[NOISE_HALF, NOISE_EXCL], stft=[SR, NPERSEG, HOP_S],
                  harmonic=HARMONIC, truth={f"{k[0]}-{k[1]}": v for k, v in TRUTH.items()})
    run = shards.open_run(a.run, "gated-track", {"script": "tools/experiments/2026-11-04/gated_track.py", "params": params})
    units = shards.Units(run, UNITS, params, a.shard, a.resume)
    if not a.merge:
        for uid in units.todo():
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            if uid.startswith("gprof-"):
                r = surface(float(uid.split("-")[1][:-1]), a.gate_bins); summary = dict(n_minima=r["n_minima"], minima=r["minima"][:3])
            else:
                cid, which = uid[len("gated-"):].rsplit("-", 1)
                r = gated_unit(cid, which, d, a.gate_bins); summary = r["entry"]
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")
            units.finish(uid, summary)
            print(uid, json.dumps(summary, default=float)[:600], flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    out = {u: json.loads((d / "result.json").read_text()) for u, d in units.all().items()}
    c1 = all(abs(f["v_minus_true_in_sd"]) <= 2 and abs(f["d_minus_true_in_sd"]) <= 2 for cid in CASES for f in out[f"gated-{cid}-15C"]["fits"])
    c1s = out["gprof-15C"]["n_minima"] == 1 and out["gprof-25.6C"]["n_minima"] == 1
    moves = {f"{cid}-ev{k}": dict(v_pct=100 * (y["v"] / x["v"] - 1), d_pct=100 * (y["d"] / x["d"] - 1))
             for cid in CASES for k, (x, y) in enumerate(zip(out[f"gated-{cid}-15C"]["fits"], out[f"gated-{cid}-T"]["fits"]), 1)}
    c2 = all(1 <= m["v_pct"] <= 3 and 1 <= m["d_pct"] <= 3 for m in moves.values())
    base = {"oyster-bay": 4.9, "eagle-cam-clip-18000s": 2.5}
    c3 = all(out[f"gated-{cid}-{w}"]["entry"]["true_pair_rank"] == 1 and (out[f"gated-{cid}-{w}"]["entry"]["margin_pct"] or 0) >= base[cid]
             for cid in CASES for w in ("15C", "T"))
    out["moves"] = moves
    out["criterion"] = {"1_within_2sd_of_truth": c1, "1_one_minimum": c1s, "2_moves_2pm1_pct": c2, "3_rank1_and_margins": c3,
                        "met": c1 and c1s and c2 and c3}
    (run / "gated_track.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float)[:9000])


if __name__ == "__main__":
    main()
