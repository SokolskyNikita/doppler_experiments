"""Item 6 (docs/proposals/2026-11-04-detector-threshold.md): the synthetic ROC of detect's statistic and band, before
any real recording is read.

Settings (S2 is retune 1, docs/proposals/2026-11-04-detector-threshold.md): statistic S0 (today: the sweep-weighted mean contrast) or S1 (tracks.rescore_z over every event detect
proposes: curve_zscore, a z-score over the curve's frames with Harris's overlap weight), by band:
  B0 fundamentals 60-300 Hz on the 40-450 Hz image (today's raw-audio profile)
  B1 fundamentals 60-900 Hz on a 40-1000 Hz image, one search
  B2 60-300 and 300-900 Hz searched apart on the 40-1000 Hz image, each at 0.5 false alarms per hour
Data: 2 h of white noise (std 0.4); passes synthesised from the propagation delay alone (window_roc.synth's method)
at (f0, v, d) = (120, 65, 1500), (200, 55, 600), (140, 79, 1590), (500, 60, 1000), (800, 60, 1500), three seeds,
amplitudes 0.06, 0.03 and 0.015, 240 s each. A detection counts within 10 s of the heard CPA.
Gate (fixed in the proposal): at 1 false alarm per hour, detection of the 0.03 passes with f0 <= 300 Hz no lower
than S0/B0's; for B1 and B2 also at least half of the 0.03 passes above 300 Hz.

Units: per setting, noise_<band part>.json and pass_<geometry>_<amp>_<seed>.json under RUN/detector_roc/<setting>/;
`runs launch --shards 6` takes one setting per box (units.shard). gate.json from `gate`. Workers: DOPPLERTRACK_JOBS.

usage: detector_roc.py RUN roc [SETTING ...]
       detector_roc.py RUN gate"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
import numpy as np                                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units as U                                                       # noqa: E402

from dopplertrack import audio                                           # noqa: E402
from dopplertrack.tracks import detect_events, rescore_null, rescore_z   # noqa: E402
from scipy.stats import norm                                             # noqa: E402

SR, C = 4000, 340.0
BANDS = {"B0": (450.0, [(60.0, 300.0)]), "B1": (1000.0, [(60.0, 900.0)]), "B2": (1000.0, [(60.0, 300.0), (300.0, 900.0)])}
STATS = {"S0": "contrast", "S1": "z", "S2": "null"}
SETTINGS = [f"{s}{b}" for s in STATS for b in BANDS]
GEOMETRIES = {"g1500": (120.0, 65.0, 1500.0), "g600": (200.0, 55.0, 600.0), "ob-ev2": (140.0, 79.0, 1590.0),
              "h500": (500.0, 60.0, 1000.0), "h800": (800.0, 60.0, 1500.0)}
AMPS, SEEDS, DUR, NOISE, HOURS = (0.06, 0.03, 0.015), (0, 1, 2), 240.0, 0.4, 2.0
MATCH_S, TARGET_FA, GATE_AMP, LOW_F0 = 10.0, 1.0, 0.03, 300.0


def parse(setting):
    return STATS[setting[:2]], BANDS[setting[2:]]


def synth(geom, amp, seed):
    f0, v, d = GEOMETRIES[geom]
    t_emit_cpa = DUR / 2 - d / C
    te = np.arange(-60.0, DUR + 60.0, 1e-3)
    r = np.sqrt(d ** 2 + (v * (te - t_emit_cpa)) ** 2)
    t = np.arange(0, DUR, 1 / SR)
    t_e = np.interp(t, te + r / C, te)
    x = amp * np.sin(2 * np.pi * f0 * t_e) + NOISE * np.random.default_rng(seed).standard_normal(len(t))
    return x.astype(np.float32), DUR / 2


def detect(x, setting, workers, top):
    stat, (fmax, parts) = parse(setting)
    sp = audio.compute_spectrogram(x, SR, fmax=fmax)
    out, diag, n = [], [], []
    for i, (lo, hi) in enumerate(parts):
        if stat in ("z", "null"):                                         # every event detect proposes, then S1/S2 rank
            cands = detect_events(sp, lo, hi, c=C, top=200, workers=workers)
            n.append(len(cands))
            if stat == "z":
                found = rescore_z(sp, cands, lo, hi, c=C, top=top, diagnostics=diag)
            else:                                                         # D; S2 = D / sigma_null in summarise
                found = sorted((e for e in rescore_null(sp, cands, lo, hi, c=C, diagnostics=diag) if np.isfinite(e.score)),
                               key=lambda e: -e.score)[:top]
        else:
            found = detect_events(sp, lo, hi, c=C, top=top, workers=workers)
        for e in found:
            out.append(dict(part=i, score=float(e.score), t_cpa=float(e.t_cpa), f0=float(e.f0)))
    return out, diag, n


def noise_unit(setting, out):
    if out.exists():
        return
    x = (NOISE * np.random.default_rng(10).standard_normal(int(HOURS * 3600 * SR))).astype(np.float32)
    dets, diag, n = detect(x, setting, U.jobs(), 50)
    U.write(out, dict(setting=setting, hours=HOURS, detections=dets, diagnostics=diag, n_candidates=n))


def pass_unit(job):
    setting, geom, amp, seed, out = job
    if out.exists():
        return json.loads(out.read_text())
    x, t_heard = synth(geom, amp, seed)
    dets, diag, _ = detect(x, setting, 1, 5)
    near = [d for d in dets if abs(d["t_cpa"] - t_heard) <= MATCH_S]
    row = dict(setting=setting, geometry=geom, f0=GEOMETRIES[geom][0], amp=amp, seed=seed,
               best=max(near, key=lambda d: d["score"]) if near else None, detections=dets, diagnostics=diag)
    U.write(out, row)
    print(setting, geom, amp, seed, row["best"] and round(row["best"]["score"], 2), flush=True)
    return row


def roc(run: Path, chosen: list[str]):
    for setting in U.shard(U.select(SETTINGS, chosen)):
        root = run / "detector_roc" / setting
        noise_unit(setting, U.path(root, "noise"))
        jobs = [(setting, g, a, s, U.path(root, f"pass_{g}_{a:g}_{s}")) for g in GEOMETRIES for a in AMPS for s in SEEDS]
        with ProcessPoolExecutor(U.jobs()) as ex:
            list(ex.map(pass_unit, [j for j in jobs if not j[-1].exists()]))


def thresholds(noise: dict, n_parts: int) -> list[float]:
    """Per band part, the score above which at most TARGET_FA / n_parts noise detections per hour remain."""
    out = []
    for i in range(n_parts):
        sc = sorted((d["score"] for d in noise["detections"] if d["part"] == i), reverse=True)
        k = int(TARGET_FA / n_parts * noise["hours"])
        out.append(sc[k] if len(sc) > k else 0.0)
    return out


def summarise(root: Path, setting: str) -> dict:
    _, (_, parts) = parse(setting)
    noise = json.loads((root / "noise.json").read_text())
    mu, sigma = 0.0, 1.0
    if setting.startswith("S2"):                  # S2 = (D - mu_null) / sigma_null over every noise candidate's D
        ds = [x["d"] for x in noise["diagnostics"] if np.isfinite(x.get("d", np.nan))]
        mu, sigma = float(np.mean(ds)), float(np.std(ds, ddof=1))
    rows = U.read_all(root, "pass_*.json")
    for doc in [noise] + rows:
        for d in doc["detections"]:
            d["score"] = (d["score"] - mu) / sigma
    thr = thresholds(noise, len(parts))
    out_sigma = dict(mu=mu, sigma=sigma)

    def hit(r):                                                           # any detection near the CPA above its part's threshold
        return any(abs(d["t_cpa"] - DUR / 2) <= MATCH_S and d["score"] > thr[d["part"]] for d in r["detections"])
    out = dict(thresholds=thr, by={}, sigma_null=out_sigma)
    for a in AMPS:
        for name, sel in (("low", lambda r: r["f0"] <= LOW_F0), ("high", lambda r: r["f0"] > LOW_F0)):
            rs = [r for r in rows if r["amp"] == a and sel(r)]
            out["by"][f"{name}_{a:g}"] = dict(n=len(rs), detected=float(np.mean([hit(r) for r in rs])) if rs else None)
    if noise.get("n_candidates"):                                         # S2's unit-spread prediction per part
        out["prediction"] = [float(norm.ppf(1 - (TARGET_FA / len(parts)) / (k / noise["hours"]))) if k else None
                             for k in noise["n_candidates"]]
    diag = noise["diagnostics"] + [d for r in rows for d in r["diagnostics"]]
    rel = [abs(d["sigma_c"] / d["sigma_c_cross_window"] - 1) for d in diag
           if d.get("sigma_c_cross_window") and np.isfinite(d.get("sigma_c", np.nan))]
    out["sigma_robust_vs_cross_window_over_20pct"] = float(np.mean([x > 0.2 for x in rel])) if rel else None
    return out


def gate(run: Path) -> dict:
    table = {s: summarise(run / "detector_roc" / s, s) for s in SETTINGS if (run / "detector_roc" / s).exists()}
    base = table["S0B0"]["by"][f"low_{GATE_AMP:g}"]["detected"]
    passed = {}
    for s, t in table.items():
        low = t["by"][f"low_{GATE_AMP:g}"]["detected"]
        high = t["by"][f"high_{GATE_AMP:g}"]["detected"]
        if s.startswith("S2"):                                            # retune 1's criterion
            s0 = table["S0" + s[2:]]["by"][f"high_{GATE_AMP:g}"]["detected"]
            calib = all(p is not None and p / 1.5 <= th <= 1.5 * p for th, p in zip(t["thresholds"], t["prediction"]))
            t["calibrated"] = calib
            passed[s] = calib and low >= base and (s.endswith("B0") or (high or 0) >= (s0 or 0))
        else:
            passed[s] = s == "S0B0" or (low >= base and (s.endswith("B0") or (high or 0) >= 0.5))
    out = dict(table=table, passed=passed)
    U.write(run / "detector_gate.json", out)
    for s, t in table.items():
        print(s, "thr", [round(x, 2) for x in t["thresholds"]], "prediction", t.get("prediction"),
              {k: v["detected"] for k, v in t["by"].items()},
              "sigma >20 %:", t["sigma_robust_vs_cross_window_over_20pct"], "PASSES" if passed[s] else "stops")
    return out


if __name__ == "__main__":
    run, step = Path(sys.argv[1]), sys.argv[2]
    if step == "roc":
        roc(run, sys.argv[3:])
    elif step == "gate":
        gate(run)
    else:
        sys.exit(__doc__)
