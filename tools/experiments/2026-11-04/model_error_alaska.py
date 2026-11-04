"""Phase 2 item 2, stage 3: the straight-pass fit on the Alaska geophone crossings (Seppi, Tape & Fee 2025),
an independent check of total error. There are no trajectories, only Flightradar24's CPA parameters, so
the model-error split of stage 1 isn't possible; what this measures is fit against reference.

For each of the authors' non-jet fitted crossings (nodal_flight_inversion_results_ngt.txt: date, flight,
node, FR24 CPA time, fitted speed, fitted slant range, source frequency, fitted CPA time, fitted sound
speed, overtones, standard deviations) with its DPZ waveform in derived/alaska/:
  spectrogram  2.048 s Hann every 0.25 s, 40-240 Hz (Nyquist 250 Hz), from the raw counts
  fit          tracks.fit_event, contrast objective, one harmonic, over the FR24 CPA time +-60 s, at
               c = 340.3 m/s (the package's 15 C) and at the authors' fitted c for that crossing, in a band:
               --band wide is 40-240 Hz; --band narrow is --band-factors (default 0.85-1.15) x the authors'
               best-determined fitted tone in 40-240 Hz (smallest fitted SD; their table has no amplitudes),
               which only places the search and never enters the comparison. The band must hold a pass's own
               Doppler span (about 0.75-1.45 x at 100 m/s, c 310 m/s): 0.85-1.15 doesn't, and fit_event's
               grid_search then raises "attempt to get argmax of an empty sequence"
  reference    FR24 slant range sqrt(horizontal distance^2 + (altitude - node elevation)^2) and speed;
               beside it the authors' fitted speed and slant range
Speed and slant range don't depend on which harmonic the fit locks to; f0 does, so it isn't compared.

Run from the repo root:  uv run python tools/experiments/2026-11-04/model_error_alaska.py "$RUN" [--workers 3]
"""
import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from dopplertrack.audio import compute_spectrogram
from dopplertrack.doppler import speed_of_sound
from dopplertrack.tracks import fit_event

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
Z = DATA / "raw/seismic/alaska-ze2019/zenodo-16997158"
NPZ = DATA / "derived/alaska"
C15 = speed_of_sound(15.0)
HALF = 60.0


def crossings():
    nodes = {}
    for row in csv.reader(open(Z / "parkshwy_nodes.txt"), delimiter="|"):
        if row[0] == "ZE":
            nodes[row[1]] = float(row[4])
    fr24 = {}
    for r in csv.reader(open(Z / "node_crossings_db_UTM.txt")):
        fr24[(r[1], r[9])] = dict(dist_h=float(r[4]), t_cpa=float(r[5]), alt=float(r[6]), speed=float(r[7]), type=r[10])
    files = {}
    for f in NPZ.glob("*.npz"):
        node = f.name.split("_")[0]
        files.setdefault(node, []).append(f)
    out = []
    for line in open(Z / "nodal_flight_inversion_results_ngt.txt"):
        p = line.strip().split(",")
        date, flight, node = p[0], p[1], p[2]
        t_fr, v_a, d_a, t_a, c_a = float(p[3]), float(p[4]), float(p[5]), float(p[7]), float(p[8])
        tones = [float(x) for x in p[9].strip("[]").split()]
        sds = [float(x) for x in p[10].strip("[]").split()][4:]      # v, d, t0, c, then one per tone
        inband = [(sd, f) for sd, f in zip(sds, tones) if 40.0 <= f <= 240.0] if len(sds) == len(tones) else []
        near100 = [f for f in tones if 40.0 <= f <= 240.0]
        band_tone = min(inband)[1] if inband else (min(near100, key=lambda f: abs(f - 100.0)) if near100 else None)
        ref = fr24.get((flight, node))
        if ref is None or node not in nodes:
            continue
        out.append(dict(date=date, flight=flight, node=node, type=ref["type"], t_fr24=t_fr, v_fr24=ref["speed"],
                        R_fr24=float(np.hypot(ref["dist_h"], ref["alt"] - nodes[node])), alt=ref["alt"], elev=nodes[node],
                        dist_h=ref["dist_h"], v_authors=v_a, R_authors=abs(d_a), t_authors=t_a, c_authors=c_a,
                        band_tone=band_tone, band_tone_basis="smallest fitted SD in 40-240 Hz" if inband else "nearest 100 Hz in 40-240 Hz",
                        files=[str(f) for f in files.get(node, [])]))
    return out


def one(x):
    band = x.pop("band")
    for f in x.pop("files"):
        z = np.load(f)
        sr, t0, data = float(z["sr"]), float(z["t0"]), z["data"]
        if t0 + 5 <= x["t_fr24"] <= t0 + len(data) / sr - 5:
            break
    else:
        return dict(x, error="no waveform covers the CPA")
    a = int(max(0, (x["t_fr24"] - HALF - 40 - t0) * sr)); b = int(min(len(data), (x["t_fr24"] + HALF + 40 - t0) * sr))
    seg = np.nan_to_num(data[a:b] - np.nanmedian(data[a:b]))
    sp = compute_spectrogram(seg, int(sr), nperseg=int(round(2.048 * sr)), hop_s=0.25, fmin=40.0, fmax=240.0, whiten_window_s=None)
    tc = x["t_fr24"] - (t0 + a / sr)
    if band == "narrow":
        if x["band_tone"] is None:
            return dict(x, band=band, error="no fitted tone in 40-240 Hz")
        lo, hi = max(40.0, x["band_lo"] * x["band_tone"]), min(240.0, x["band_hi"] * x["band_tone"])
    else:
        lo, hi = 40.0, 240.0
    x.update(band=band, f_lo=lo, f_hi=hi)
    for tag, c in (("c15", C15), ("cauth", x["c_authors"])):
        try:
            fe = fit_event(sp, tc - HALF, tc + HALF, lo, hi, c=c, objective="contrast")
            x.update({f"v_{tag}": fe.v, f"R_{tag}": fe.d, f"tau_{tag}": fe.t_cpa_emit + t0 + a / sr, f"f0_{tag}": fe.f0,
                      f"score_{tag}": fe.score})
        except Exception as e:      # a failed fit is a result, recorded, not a crash
            x[f"error_{tag}"] = repr(e)
    return x


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--band", choices=("wide", "narrow"), default="wide")
    ap.add_argument("--band-factors", nargs=2, type=float, default=(0.85, 1.15), metavar=("LO", "HI"),
                    help="narrow band as multiples of the authors' tone; must hold the Doppler span, about 0.75-1.45 at 100 m/s")
    ap.add_argument("--sample", type=int, help="a seeded random subset of this size; crossings already done count first")
    ap.add_argument("--seed", type=int, default=20261104)
    a = ap.parse_args()
    xs = crossings()
    for x in xs:
        x["band"] = a.band
        x["band_lo"], x["band_hi"] = a.band_factors
    part = Path(a.run) / "alaska.jsonl"       # one row per finished crossing, so a stopped run resumes
    done = {(r["flight"], r["node"]) for r in map(json.loads, open(part))} if part.exists() else set()
    if a.sample:
        rest = [x for x in xs if (x["flight"], x["node"]) not in done]
        pick = np.random.default_rng(a.seed).choice(len(rest), size=max(0, a.sample - len(done)), replace=False)
        xs = [x for x in xs if (x["flight"], x["node"]) in done] + [rest[i] for i in sorted(pick)]
    todo = [x for x in xs if (x["flight"], x["node"]) not in done]
    print(f"{len(xs)} crossings with FR24 rows, {len(done)} done, {len(todo)} to go", flush=True)
    with ProcessPoolExecutor(a.workers) as ex, open(part, "a") as fh:
        for k, r in enumerate(ex.map(one, todo, chunksize=2)):
            fh.write(json.dumps(r, default=float) + "\n"); fh.flush()
            if k % 50 == 0:
                print(f"  {len(done) + k + 1} / {len(xs)}", flush=True)
    rows = [json.loads(line) for line in open(part)]
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(Path(a.run) / "alaska.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
