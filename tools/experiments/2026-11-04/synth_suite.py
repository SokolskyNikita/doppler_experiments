"""A known-answer suite for the collective find (docs/experiments/2026-11-04-collective-find.md, "A known-answer suite":
design and criterion written before the run). One shards.py unit per case, a (shape, amplitude):
  - synthesise a 30 min recording at a synthetic observer with three target passes of the shape;
  - the flight data: the real 2026-09-08 Oyster Bay traffic plus the three synthetic flights;
  - run locate (pair rule `comparable`) and the collective find (+-10 % f0) on the same spectrogram and detections.

usage: uv run python tools/experiments/2026-11-04/synth_suite.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import datetime
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import runner  # noqa: E402

OBS = (40.78, -73.40)
BOX = (OBS[0] - 0.18, OBS[0] + 0.18, OBS[1] - 0.22, OBS[1] + 0.22)
T0 = datetime.datetime(2026, 9, 8, 19, 0, tzinfo=datetime.timezone.utc).timestamp()
DUR, SR, NOISE = 1800.0, 4000, 0.4
TRACES = "derived/traces/2026-09-08/ny_margin12_v2.npz"
# (f0 Hz, speed m/s, horizontal offset m, height m, heard CPA about, heading at CPA deg)
PASSES = [(110.0, 120.0, 3500.0, 1200.0, 450.0, 70.0), (125.0, 100.0, 4500.0, 1500.0, 1000.0, 200.0),
          (140.0, 140.0, 5500.0, 1000.0, 1500.0, 320.0)]
SHAPES = {"straight": (0.0, 0.0), "turn": (25.0, 0.0), "climb": (0.0, 300.0), "both": (25.0, 300.0)}
AMPS = (0.02, 0.03, 0.05)
RAMP_S = 60.0
UNITS = [f"{s}-a{int(round(a * 100)):02d}" for s in SHAPES for a in AMPS]


def trajectory(k, shape, c):
    """ENU positions (m, about the observer) at 1 Hz over +-600 s of the pass's emission CPA, and its truth."""
    f0, v, off, h0, t_heard, psi0 = PASSES[k]
    dpsi, dh = SHAPES[shape]
    r0 = float(np.hypot(off, h0))
    tc = T0 + t_heard - r0 / c                         # the straight pass's emission CPA; the shape bends about it
    t = tc + np.arange(-600.0, 600.01, 1.0)
    u = np.clip((t - tc) / (2 * RAMP_S), -0.5, 0.5)
    psi = np.radians(psi0 + dpsi * u)
    vx, vy = v * np.sin(psi), v * np.cos(psi)
    i0 = 600
    x = np.cumsum(np.r_[0.0, vx[:-1]]); y = np.cumsum(np.r_[0.0, vy[:-1]])
    x -= x[i0]; y -= y[i0]
    nx, ny = np.cos(np.radians(psi0)), -np.sin(np.radians(psi0))       # perpendicular to the CPA heading
    x += off * nx; y += off * ny
    z = h0 + dh * u
    enu = np.stack([x, y, z], 1)
    rng = np.linalg.norm(enu, axis=1)
    j = int(np.argmin(rng))
    return t, enu, dict(f0=f0, v=v, slant_min=float(rng[j]), t_emit_cpa=float(t[j]), t_heard_cpa_audio=float(t[j] + rng[j] / c - T0))


def synthesise(shape, amp, out_dir):
    from dopplertrack.adsb import Trace, load_trace_metadata, load_traces, save_traces
    from dopplertrack.audio import compute_spectrogram
    from dopplertrack.doppler import curve_from_trajectory, speed_of_sound
    from dopplertrack.geo import enu_to_lla
    c = speed_of_sound(15.0)
    tt = np.arange(0, DUR, 1 / SR)
    x = (NOISE * np.random.default_rng(20261104).standard_normal(len(tt))).astype(np.float32)
    synth, truth = [], []
    for k in range(len(PASSES)):
        t, enu, tr = trajectory(k, shape, c)
        to, ratio, _ = curve_from_trajectory(t, enu, np.zeros(3), f0=1.0, c=c)
        fi = np.interp(tt + T0, to, ratio, left=np.nan, right=np.nan) * tr["f0"]
        m = np.isfinite(fi)
        ph = 2 * np.pi * np.cumsum(np.nan_to_num(fi, nan=0.0)) / SR
        x[m] += (amp * np.sin(ph) + 0.5 * amp * np.sin(2 * ph))[m].astype(np.float32)
        lat, lon, alt = enu_to_lla(enu[:, 0], enu[:, 1], enu[:, 2], *OBS)
        icao = f"5yn{k:03d}"
        sp_ = np.full(len(t), tr["v"])
        synth.append(Trace(icao, None, "C172", "synthetic", t, lat, lon, alt, sp_, np.zeros(len(t), bool),
                           np.array(["geometric"] * len(t))))
        truth.append(dict(tr, icao=icao))
    sp = compute_spectrogram(x, SR)
    spec = out_dir / "rec.npz"; sp.save(spec)
    real = runner.resolve(TRACES)
    traces = load_traces(real) + synth
    tpath = out_dir / "traces.npz"
    save_traces(traces, tpath, metadata=load_trace_metadata(real))
    return spec, tpath, truth


def nearest(truth, t_heard):
    k = int(np.argmin([abs(tr["t_heard_cpa_audio"] - t_heard) for tr in truth]))
    return truth[k] if abs(truth[k]["t_heard_cpa_audio"] - t_heard) <= 30 else None


def run_unit(uid, out_dir, keep_dir):
    from dopplertrack import locate as loc
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections
    from dopplertrack.collective import Window, collective_find
    from dopplertrack.geo import haversine_m
    from dopplertrack.tracks import detect_events
    shape, a = uid.split("-a"); amp = int(a) / 100
    spec, tpath, truth = synthesise(shape, amp, out_dir)
    cfg = loc.LocateConfig(pair_rule="comparable", dem=False, cpa_cache=str(out_dir / "cpa_locate.npz"))
    o = loc.locate(spec, "2026-09-08", list(BOX), [tpath], cfg, out_dir=keep_dir / "locate", log=lambda m: None)
    rec = o.record
    ref = rec.get("refined") if isinstance(rec.get("refined"), dict) and "lat" in rec.get("refined", {}) else None
    cand = rec["candidates"][0] if rec.get("candidates") else None
    chosen = next((r for r in rec.get("pair_rules", []) if r.get("chosen")), None)
    evs = [rec["events"][i - 1] for i in (chosen or {}).get("events", [])] if chosen else []
    basins = []
    for e in evs:
        f = e["fit"]; tru = nearest(truth, f["t_heard_cpa_audio_s"])
        basins.append(dict(t=f["t_heard_cpa_audio_s"], v=f["speed_m_s"], d=f["slant_range_m"], truth=tru,
                           wrong=(tru is None or abs(f["speed_m_s"] / tru["v"] - 1) > 0.2 or abs(f["slant_range_m"] / tru["slant_min"] - 1) > 0.2)))
    pair = dict(verdict=rec.get("verdict"), refined=ref, top=cand, events=basins, wrong_basin=any(b["wrong"] for b in basins) or not basins,
                distance_m=float(haversine_m(ref["lat"], ref["lon"], *OBS)) if ref else
                (float(haversine_m(cand["lat"], cand["lon"], *OBS)) if cand else None))
    sp = Spectrogram.load(spec)
    found = cached_detections(sp, detect_events, f_lo=60.0, f_hi=300.0, harmonics=1, top=10, window_s=240.0)
    usable = sorted([e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)], key=lambda e: -e.score)[:10]
    wins = [Window.from_detection(e) for e in usable]
    traces, _ = join_days([str(tpath)])
    col = collective_find(sp, wins, traces, BOX, f0_span=0.10, cpa_cache=str(out_dir / "cpa_collective.npz"), log=lambda m: None)
    w = col.get("winner")
    coll = dict(winner=w and {k: w[k] for k in ("lat", "lon", "Z", "n_matched", "clock_audio_minus_unix")},
                distance_m=float(haversine_m(w["lat"], w["lon"], *OBS)) if w else None,
                matched=[m for m in (w or {}).get("windows", []) if m and m["z"] > 0], walls=col.get("walls"), counts=col.get("counts"))
    return dict(case=uid, truth=truth, windows=[x.__dict__ for x in wins], pair=pair, collective=coll)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        shards.print_inputs([], [TRACES], [], ())
        return
    params = dict(units=UNITS, obs=OBS, box=BOX, t0=T0, dur=DUR, noise=NOISE, passes=PASSES, shapes=SHAPES, amps=AMPS,
                  ramp_s=RAMP_S, pair_rule="comparable", f0_span=0.10)
    run = shards.open_run(a.run, "synth-suite", {"script": "tools/experiments/2026-11-04/synth_suite.py", "params": params})
    units = shards.Units(run, UNITS, params, a.shard, a.resume)
    if not a.merge:
        for uid in units.todo():
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmp:        # the synthetic audio's spectrogram, traces and CPA tables:
                r = run_unit(uid, Path(tmp), d)               # regenerable and large, so kept off the run folder
            (d / "result.json").write_text(json.dumps(r, indent=1, default=float) + "\n")
            units.finish(uid, {"pair_m": r["pair"]["distance_m"], "collective_m": r["collective"]["distance_m"]})
            print(uid, json.dumps({"pair": r["pair"]["distance_m"], "wrong_basin": r["pair"]["wrong_basin"],
                                   "collective": r["collective"]["distance_m"]}, default=float), flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    rows = {u: json.loads((d / "result.json").read_text()) for u, d in units.all().items()}
    summary = {}
    for u, r in rows.items():
        shape = u.split("-a")[0]
        p, c = r["pair"], r["collective"]
        within = lambda d: d is not None and d <= 2000  # noqa: E731
        summary[u] = dict(shape=shape, pair_m=p["distance_m"], pair_wrong_basin=p["wrong_basin"], collective_m=c["distance_m"],
                          crit=(within(c["distance_m"]) if shape != "straight" and p["wrong_basin"] else
                                (within(c["distance_m"]) or not within(p["distance_m"])) if shape == "straight" else None))
    crit1 = all(v["crit"] for v in summary.values() if v["shape"] != "straight" and v["crit"] is not None)
    crit2 = all(v["crit"] for v in summary.values() if v["shape"] == "straight")
    out = dict(summary=summary, criterion={"1_non_straight": crit1, "2_straight_no_worse": crit2})
    (run / "synth_suite.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
