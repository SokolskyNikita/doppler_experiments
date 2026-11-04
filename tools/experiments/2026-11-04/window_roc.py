"""Item 5 round 2 (docs/proposals/2026-11-04-window.md): the synthetic ROC of the window candidates, before any real
recording is read.

Candidates (window, hop, taper), every one on the 0.488 Hz grid (nfft 8192; the 4.096 s window is read at that
grid's frequencies):
  C0 2.048 s, 0.25 s, Hann (today)      C1 2.048 s, 1 s, Hann        C2 1.024 s, 0.512 s, Hann
  C3h 1.024 s, 1.024 s, Hann            C3r 1.024 s, 1.024 s, rectangular
  C4 the pair 4.096 s / 2.048 s Hann (tails) and 0.512 s / 0.512 s Hann (steep middle): each short frame takes
     the window whose matched sweep rate 1/T^2 is nearer, in log, to |df/dt| of ridge() on the long image (the
     short one where |df/dt| > 1 / (4.096 * 0.512) = 0.477 Hz/s); detect uses the long image.
ridge()'s per-frame step limit is scaled with the hop (3 bins at 0.25 s), so every candidate allows the same Hz/s.

Data: 2 h of white noise; passes synthesised from the propagation delay alone (x(t) = A sin(2 pi f0 t_e(t)),
t = t_e + r(t_e)/c, constant amplitude) at three geometries (f0, v, d) = (200, 55, 600), (120, 65, 1500) and Oyster
Bay event 2's fit (140, 79, 1590), three seeds, amplitudes 0.06, 0.03 and 0.015 in noise of std 0.4, 240 s each
with the heard CPA at the middle.

Measures per candidate: detect's scores on the noise (false alarms per hour by threshold) and on each pass (a
detection within 10 s of the heard CPA); ridge()'s error, bridges and coverage at 2 % against the true curve
(freqtrack_livermore.score); fit_event's f0, v and d errors under contrast and brightness.
Gate (fixed in the proposal): a candidate goes on to real data if, at 1 false alarm per hour, its detection
probability on the 0.03 passes is no lower than C0's and its ridge() median error on them is at most 1.05x C0's.

Units: noise.json and pass_<geometry>_<amp>_<seed>.json per candidate under RUN/window_roc/<candidate>/, written
when finished and skipped if present; `runs launch --shards n` splits the candidates (units.shard). gate.json from
`gate`. Workers: DOPPLERTRACK_JOBS.

usage: window_roc.py RUN roc [CANDIDATE ...]
       window_roc.py RUN gate"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
import numpy as np                                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402
import units as U                                                       # noqa: E402

from dopplertrack import audio, doppler                                  # noqa: E402
from dopplertrack.audio import Spectrogram                               # noqa: E402
from dopplertrack.tracks import detect_events, fit_event, local_whiten, ridge   # noqa: E402

SR, NFFT, C = 4000, 8192, 340.0
CANDIDATES = {"C0": (2.048, 0.25, "hann"), "C1": (2.048, 1.0, "hann"), "C2": (1.024, 0.512, "hann"),
              "C3h": (1.024, 1.024, "hann"), "C3r": (1.024, 1.024, "boxcar"), "C4": None}
C4_LONG, C4_SHORT = (4.096, 2.048, "hann"), (0.512, 0.512, "hann")
GEOMETRIES = {"g600": (200.0, 55.0, 600.0), "g1500": (120.0, 65.0, 1500.0), "ob-ev2": (140.0, 79.0, 1590.0)}
AMPS, SEEDS, DUR, NOISE = (0.06, 0.03, 0.015), (0, 1, 2), 240.0, 0.4
HOURS, DET_F = 2.0, (90.0, 230.0)                                        # detect's fundamental band covers every f0
MATCH_S, TARGET_FA, GATE_AMP = 10.0, 1.0, 0.03


def _sp(x, spec, fmax=1000.0):
    T, hop, win = spec
    n = int(round(T * SR))
    return audio.compute_spectrogram(x, SR, nperseg=n, hop_s=hop, fmax=fmax, nfft=max(NFFT, n), window=win)


def _on_grid(sp: Spectrogram, f: np.ndarray) -> Spectrogram:
    """sp's values at the frequencies f (sp's grid is finer or equal)."""
    i = np.clip(np.searchsorted(sp.f, f), 0, len(sp.f) - 1)
    return Spectrogram(sp.t, sp.f[i], sp.S[i])


def images(x, cand, band=None):
    """(detect's image, ridge's and the fits' image) for a candidate; band (f_lo, f_hi) is the fundamental band
    C4's rule reads its ridge in."""
    if cand != "C4":
        sp = _sp(x, CANDIDATES[cand])
        return sp, sp
    long = _sp(x, C4_LONG); short = _sp(x, C4_SHORT)
    long = _on_grid(long, short.f)
    if band is None:
        return long, long
    w = local_whiten(long.crop(long.t[0], long.t[-1], *band))
    r = ridge(w, max_step_bins=_step(C4_LONG[1]))
    slope = np.abs(np.gradient(r, w.t))
    use_short = np.interp(short.t, w.t, slope) > 1.0 / (C4_LONG[0] * C4_SHORT[0])
    k = np.clip(np.searchsorted(long.t, short.t), 0, len(long.t) - 1)
    S = np.where(use_short[None, :], short.S, long.S[:, k])
    return long, Spectrogram(short.t, short.f, S.astype(np.float32))


def _step(hop):
    return max(3, int(round(3 * hop / 0.25)))


def hop_of(cand):
    return (C4_SHORT if cand == "C4" else CANDIDATES[cand])[1]


# ---- synthetic data --------------------------------------------------------------------------------------------

def synth(geom, amp, seed):
    f0, v, d = GEOMETRIES[geom]
    t_emit_cpa = DUR / 2 - d / C
    te = np.arange(-60.0, DUR + 60.0, 1e-3)
    r = np.sqrt(d ** 2 + (v * (te - t_emit_cpa)) ** 2)
    t = np.arange(0, DUR, 1 / SR)
    t_e = np.interp(t, te + r / C, te)
    x = amp * np.sin(2 * np.pi * f0 * t_e) + NOISE * np.random.default_rng(seed).standard_normal(len(t))
    fref = lambda tt: doppler.ideal_curve(tt, f0, v, d, t_emit_cpa, c=C)
    return x.astype(np.float32), fref, DUR / 2, (f0, v, d)


# ---- units -----------------------------------------------------------------------------------------------------

def noise_unit(cand, out):
    if out.exists():
        return
    x = np.random.default_rng(10).standard_normal(int(HOURS * 3600 * SR)).astype(np.float32) * NOISE
    sp, _ = images(x, cand)
    dets = detect_events(sp, *DET_F, c=C, top=50, workers=U.jobs())
    U.write(out, dict(candidate=cand, hours=HOURS, scores=sorted((float(e.score) for e in dets), reverse=True)))


def pass_unit(job):
    cand, geom, amp, seed, out = job
    if out.exists():
        return json.loads(out.read_text())
    x, fref, t_heard, (f0, v, d) = synth(geom, amp, seed)
    tt = np.arange(5.0, DUR - 5.0, 0.25)
    fs = fref(tt)
    band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
    det_sp, sp = images(x, cand, band)
    dets = detect_events(det_sp, *DET_F, c=C, top=5, workers=1)
    near = [float(e.score) for e in dets if abs(e.t_cpa - t_heard) <= MATCH_S]
    w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band))
    span = (tt[0], tt[-1])
    rid = FL.score([(w.t, ridge(w, max_step_bins=_step(hop_of(cand))))], span, fref, sp.df, 0.02)
    fits = {}
    for obj in ("contrast", "brightness"):
        e = fit_event(sp, span[0], span[1], band[0], band[1], c=C, objective=obj)
        err = dict(f0=abs(e.f0 / f0 - 1), v=abs(e.v / v - 1), d=abs(e.d / d - 1), t_cpa=abs(e.t_cpa - t_heard))
        fits[obj] = {q: (float(x) if np.isfinite(x) else 1.0) for q, x in err.items()}      # a weak fit counts as 100 %
        fits[obj]["weak"] = e.weak
    row = dict(candidate=cand, geometry=geom, amp=amp, seed=seed, detect_score=max(near) if near else None,
               ridge=rid, fits=fits)
    U.write(out, row)
    print(cand, geom, amp, seed, row["detect_score"], f"ridge err {rid['error']:.4f} br {rid['bridges']}", flush=True)
    return row


def roc(run: Path, chosen: list[str]):
    for cand in U.shard(U.select(list(CANDIDATES), chosen)):
        root = run / "window_roc" / cand
        noise_unit(cand, U.path(root, "noise"))
        jobs = [(cand, g, a, s, U.path(root, f"pass_{g}_{a:g}_{s}")) for g in GEOMETRIES for a in AMPS for s in SEEDS]
        with ProcessPoolExecutor(U.jobs()) as ex:
            list(ex.map(pass_unit, [j for j in jobs if not j[-1].exists()]))


# ---- the gate --------------------------------------------------------------------------------------------------

def summarise(root: Path) -> dict:
    noise = json.loads((root / "noise.json").read_text())
    scores = noise["scores"]
    k = int(TARGET_FA * noise["hours"])                                   # at most this many noise detections allowed
    thr = scores[k] if len(scores) > k else 0.0                           # detections must score above it
    passes = U.read_all(root, "pass_*.json")
    out = dict(threshold=thr, noise_scores=scores[:10], by_amp={})
    for a in AMPS:
        rows = [r for r in passes if r["amp"] == a]
        out["by_amp"][f"{a:g}"] = dict(
            n=len(rows), detected=float(np.mean([r["detect_score"] is not None and r["detect_score"] > thr for r in rows])),
            ridge_error=float(np.median([r["ridge"]["error"] for r in rows])),
            ridge_bridges=int(sum(r["ridge"]["bridges"] for r in rows)),
            ridge_coverage=float(np.median([r["ridge"]["coverage"] for r in rows])),
            **{f"{o}_{q}": float(np.median([r["fits"][o][q] for r in rows])) for o in ("contrast", "brightness") for q in ("f0", "v", "d")})
    return out


def gate(run: Path) -> dict:
    table = {c: summarise(run / "window_roc" / c) for c in CANDIDATES}
    base = table["C0"]["by_amp"][f"{GATE_AMP:g}"]
    passed = {}
    for c, t in table.items():
        g = t["by_amp"][f"{GATE_AMP:g}"]
        passed[c] = c == "C0" or (g["detected"] >= base["detected"] and g["ridge_error"] <= 1.05 * base["ridge_error"])
    out = dict(table=table, passed=passed, rule=f"at {TARGET_FA:g} false alarm per hour, detection on the {GATE_AMP:g} passes "
                                               f"no lower than C0's and ridge() median error at most 1.05x C0's")
    U.write(run / "window_gate.json", out)
    for c, t in table.items():
        for a, g in t["by_amp"].items():
            print(f"{c:4s} amp {a:5s} thr {t['threshold']:.2f} detected {g['detected']:.2f} ridge err {g['ridge_error']:.4f} "
                  f"br {g['ridge_bridges']} cov {g['ridge_coverage']:.2f}  contrast f0/v/d {g['contrast_f0']:.3f}/{g['contrast_v']:.3f}/"
                  f"{g['contrast_d']:.3f}  brightness {g['brightness_f0']:.3f}/{g['brightness_v']:.3f}/{g['brightness_d']:.3f}")
        print(f"{c}: {'PASSES the gate' if passed[c] else 'stops at the gate'}")
    return out


if __name__ == "__main__":
    run, step = Path(sys.argv[1]), sys.argv[2]
    if step == "roc":
        roc(run, sys.argv[3:])
    elif step == "gate":
        gate(run)
    else:
        sys.exit(__doc__)
