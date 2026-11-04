"""Do the four gated tracks follow their true flights' heard curves? (docs/experiments/2026-11-04-event-fit.md, "Is the line
the true aircraft's?": method and criterion written before the run.) One shards.py unit:

  overlay   for each event, the gated track (gated_track.py, gate +-3 bins) against score.modelled_curve of the true flight's
            1 Hz segment at the reference point on the terrain, 15 C: f0 in closed form and the audio-to-UTC offset free
            (+-120 s around the case's clock, 0.5 s grid, then refined); its RSS and RMS on the track's points beside the
            straight-pass least-squares fit's on the same points. Criterion: RMS to the true curve <= 2 x RMS to the gate.

usage: uv run python tools/experiments/2026-11-04/overlay_truth.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import datetime
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, runner  # noqa: E402

spec = importlib.util.spec_from_file_location("gated_track", HERE / "gated_track.py")
gt = importlib.util.module_from_spec(spec); spec.loader.exec_module(gt)
GATE_BINS = 3


def audio_zero(case):
    rc = (case.get("reference_clock_utc") or {}).get("audio_zero_utc_unix_s")
    if rc is not None:
        return float(rc)
    return datetime.datetime.fromisoformat(case["start_time"]["utc"].replace("Z", "+00:00")).timestamp()


def true_curve(case, icao):
    from dopplertrack.adsb import join_days
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.score import modelled_curve
    from dopplertrack.search import build_segments
    from dopplertrack.terrain import Terrain
    ref = cases.case_labels(case["id"], case["version"])["reference"]
    lat, lon = float(ref["lat"]), float(ref["lon"])
    elev = float(Terrain().elevation(np.array([lat]), np.array([lon]))[0]) if case["search"]["dem"] else 0.0
    traces, _ = join_days(runner.trace_paths(case))
    segs = [s for s in build_segments([tr for tr in traces if tr.icao == icao], lat, lon)]
    parts = [modelled_curve(s, np.array([0.0, 0.0, elev]), speed_of_sound(15.0)) for s in segs]
    t = np.concatenate([p[0] for p in parts]); r = np.concatenate([p[1] for p in parts])
    o = np.argsort(t)
    return t[o], r[o], len(segs)


def fit_to_curve(tt, g, t_curve, ratio, t0):
    from scipy.optimize import minimize_scalar

    def rss(delta):
        rr = np.interp(tt + t0 + delta, t_curve, ratio, left=np.nan, right=np.nan)
        ok = np.isfinite(rr)
        if ok.sum() < 0.8 * len(tt):
            return np.inf, np.nan, int(ok.sum())
        f0 = float(np.dot(g[ok], rr[ok]) / np.dot(rr[ok], rr[ok]))
        e = g[ok] - f0 * rr[ok]
        return float(e @ e) * len(tt) / ok.sum(), f0, int(ok.sum())
    grid = np.arange(-120.0, 120.01, 0.5)
    vals = [rss(x)[0] for x in grid]
    k = int(np.argmin(vals))
    if not np.isfinite(vals[k]):
        return None
    r = minimize_scalar(lambda x: rss(x)[0], bounds=(grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]), method="bounded")
    s, f0, n = rss(r.x)
    return dict(rss=s, rms_hz=float(np.sqrt(s / len(tt))), f0=f0, clock_offset_s=float(r.x), n_matched=n)


def unit():
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.tracks import fit_track
    out = []
    for cid in gt.CASES:
        blind = cases.blind_case(cid)
        full = cases.latest_case(cid)
        pair = cases.case_labels(cid, full["version"])["true_pair"]
        for k, ((tr, stats), ev) in enumerate(gt.tracks(blind, GATE_BINS), 1):
            icao = pair[k - 1]
            tt, g, _ = tr.usable()
            sfit = fit_track(tr, c=speed_of_sound(15.0))
            t_curve, ratio, nseg = true_curve(full, icao)
            tf = fit_to_curve(tt, g, t_curve, ratio, audio_zero(full))
            straight_rss = sfit.rms_hz ** 2 * sfit.n
            row = dict(case=cid, event=k, icao=icao, n_points=int(len(tt)), segments=nseg, rms_to_gate_hz=stats["rms_to_gate_hz"],
                       straight=dict(v=sfit.v, d=sfit.d, rss=straight_rss, rms_hz=sfit.rms_hz), trajectory=tf)
            if tf:
                row["trajectory_over_straight_rss"] = tf["rss"] / straight_rss
                row["criterion_rms_le_2x_gate"] = tf["rms_hz"] <= 2 * stats["rms_to_gate_hz"]
            out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        from bench import inputs as bench_inputs
        doc = bench_inputs.run_inputs(list(gt.CASES), "saved-fit")
        extra = [cases.latest_case(c)["audio"]["path"] for c in gt.CASES]
        shards.print_inputs(doc["cases"], list(dict.fromkeys(doc["inputs"] + extra)), [], tuple(doc["cache_kinds"]))
        return
    params = dict(gate_bins=GATE_BINS, c="15 C", clock_search_s=[-120, 120, 0.5])
    run = shards.open_run(a.run, "overlay-truth", {"script": "tools/experiments/2026-11-04/overlay_truth.py", "params": params})
    units = shards.Units(run, ["overlay"], params, a.shard, a.resume)
    if not a.merge and units.todo():
        d = units.dir("overlay"); d.mkdir(parents=True, exist_ok=True)
        rows = unit()
        (d / "result.json").write_text(json.dumps(rows, indent=1, default=float) + "\n")
        units.finish("overlay", {"criterion": [r.get("criterion_rms_le_2x_gate") for r in rows]})
    rows = json.loads((units.all()["overlay"] / "result.json").read_text())
    (run / "overlay.json").write_text(json.dumps(rows, indent=1, default=float) + "\n")
    print(json.dumps(rows, indent=1, default=float))


if __name__ == "__main__":
    main()
