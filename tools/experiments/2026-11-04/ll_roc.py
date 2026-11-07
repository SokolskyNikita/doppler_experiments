"""Item 3 round 3 (docs/experiments/designs/2026-11-04-tracker-likelihood.md): the likelihood tracker's constants and its two
knobs, before any Livermore pass is tracked.

1. constants: T_pass, T_run and T_dip from the development events (Oyster Bay ev1/ev2, eagle cam ev1/ev2, ob-e03,
   sw-e01), never Livermore. Along each judged event's reference curve (hmm_livermore.py's dev_references.json,
   the same references as round 2), on the frequency-whitened image, a frame is under the noise when the largest
   z = P / sigma^2 over harmonics 1..3 at the reference is below ln 10 (the noise's 90th percentile). T_pass is
   the median event window; T_run and T_dip the medians of the runs of frames above and under the noise.
2. roc: on a fixed grid, design SNR a in {1, 2, 4, 8} by birth prior beta in 10^{-12, -11, ..., -2} per Hz per
   second, the false-track rate on round 2's noise (2 h of white noise in 12 windows of 10 min, 150-250 Hz) and
   the coverage and fragments on round 2's weak pass (two straight passes, 3 seeds, amplitude 0.03 in 0.4).
3. pick, pre-registered: among the grid points with at most 1 false track per hour per 100 Hz and a median
   weak-pass coverage of at least 0.5, the lowest beta; ties to the fewest fragments, then the higher a. None
   qualifying stops the round before any real recording is tracked.

Units: constants.json; one file per (a, beta, noise window or weak-pass case) under RUN/ll_roc/, written when it
finishes and skipped if present; ll_chosen.json. Workers: DOPPLERTRACK_JOBS; `runs launch --shards n` splits the grid
points across boxes (units.shard).

usage: ll_roc.py RUN constants [retune1]
       ll_roc.py RUN roc [A ...]
       ll_roc.py RUN pick"""
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
import freqtrack_retune as FR                                            # noqa: E402
import hmm_livermore as HL                                               # noqa: E402
import units as U                                                       # noqa: E402

from dopplertrack import audio, freqtrack as ft, lltrack as ll           # noqa: E402

SR, N, HOP = 4000, 8192, 0.25
HOURS, TARGET, MIN_COVERAGE = 2.0, 1.0, 0.5
A_GRID = [1.0, 2.0, 4.0, 8.0]
BETA_GRID = [10.0 ** e for e in range(-12, -1)]
UNDER = np.log(10.0)
_NOISE: dict = {}


# Retune 1 (counted; written after the first ROC, where no grid point qualified: every point, even beta 1e-12, made
# exactly one whole-window track per family in noise). The evidence treated each of the eightfold-overlapping frames
# as independent, so a noise peak persists over about eight frames and adds up like a tone. Retune 1 tempers each
# frame's evidence by Harris's overlap correlation (lltrack.harris_weight); the grid, kernel and pick are unchanged.
RETUNES = {"retune1": lambda: dict(frame_weight=ll.harris_weight(N, int(round(HOP * SR))))}


def params(constants: dict, a: float, beta: float) -> ll.LLParams:
    return ll.with_params(ll.LLParams(), design_snr=a, birth_prior=beta, t_pass_s=constants["t_pass_s"],
                          t_run_s=constants["t_run_s"], t_dip_s=constants["t_dip_s"], **constants.get("overrides", {}))


# ---- 1. constants from the development events ---------------------------------------------------------------

def _runs(mask: np.ndarray, value: bool) -> list[int]:
    out, n = [], 0
    while n < len(mask):
        if mask[n] != value:
            n += 1
            continue
        m = n
        while m + 1 < len(mask) and mask[m + 1] == value:
            m += 1
        out.append(m - n + 1)
        n = m + 1
    return out


def constants(run: Path, retune: str | None = None) -> dict:
    refs_path = run / "dev_references.json"
    if not refs_path.exists():
        HL.references(run)
    refs = json.loads(refs_path.read_text())
    spans, above, under, per = [], [], [], {}
    for ev, ref in zip(HL.DEV, refs):
        if not ref["judged"]:
            continue
        name, src, (a, b), *_ = ev
        x, a0 = HL.dev_audio(ev)
        fref = HL.dev_fref(ev, ref)
        sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1000.0, whiten="frequency")
        z = ll.normalised_power(sp)
        t = sp.t[(sp.t >= a - a0) & (sp.t <= b - a0)]
        k = np.searchsorted(sp.t, t)
        f = fref(t)
        zmax = np.full(len(t), -np.inf)
        for h in (1, 2, 3):
            bins = np.rint((h * f - sp.f[0]) / sp.df)
            ok = np.isfinite(bins) & (bins >= 0) & (bins < len(sp.f))
            zmax[ok] = np.maximum(zmax[ok], z[bins[ok].astype(int), k[ok]])
        ok = np.isfinite(zmax) & sp.valid[k]
        mask = zmax[ok] < UNDER
        spans.append(b - a); above += _runs(mask, False); under += _runs(mask, True)
        per[name] = dict(window_s=b - a, frames=int(ok.sum()), under_frac=float(mask.mean()),
                         runs_above=_runs(mask, False), runs_under=_runs(mask, True))
        print(name, per[name]["under_frac"], flush=True)
    out = dict(t_pass_s=float(np.median(spans)), t_run_s=float(np.median(above) * HOP),
               t_dip_s=float(np.median(under) * HOP), events=per, under_z=float(UNDER),
               retune=retune, overrides=RETUNES[retune]() if retune else {})
    U.write(run / "constants.json", out)
    print({k: out[k] for k in ("t_pass_s", "t_run_s", "t_dip_s")})
    return out


# ---- 2. the ROC on synthetic data -----------------------------------------------------------------------------

def _init():
    x = np.random.default_rng(0).standard_normal(int(HOURS * 3600 * SR)).astype(np.float32)
    _NOISE["sp"] = audio.compute_spectrogram(x, SR, fmax=1000.0, whiten="frequency")
    _NOISE["st"] = ft.SampleSTFT(x, SR, N, HOP)


def _unit(job):
    kind, i, a, beta, c, out = job
    if out.exists():
        return json.loads(out.read_text())
    p = params(c, a, beta)
    if kind == "noise":
        if not _NOISE:
            _init()
        a0 = 600.0 * i
        row = dict(n_tracks=len(ll.ll_track(_NOISE["sp"], _NOISE["st"], a0, a0 + 600, 150.0, 250.0, p).tracks))
    else:
        f0, v, d = FR.PASSES[i // 3]
        x, _, fref, span, band = FR.weak_pass(f0, v, d, 0.03, i % 3)
        sp = audio.compute_spectrogram(x.astype(np.float32), SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900, whiten="frequency")
        ev = ll.ll_track(sp, ft.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], *band, p)
        row = FL.score([(tr.t, tr.f) for tr in ev.tracks], span, fref, sp.df, 0.02)
    row.update(kind=kind, i=i, a=a, beta=beta)
    U.write(out, row)
    return row


def roc(run: Path, chosen_a: list[float]) -> None:
    c = json.loads((run / "constants.json").read_text())
    jobs = []
    points = [(a, beta) for a in A_GRID if not chosen_a or a in chosen_a for beta in BETA_GRID]
    for a, beta in U.shard(points):                                       # runs launch --shards: grid points per box
        root = run / "ll_roc" / f"a{a:g}_b{beta:.0e}"
        jobs += [("noise", i, a, beta, c, U.path(root, f"noise_{i}")) for i in range(int(HOURS * 6))]
        jobs += [("weak", i, a, beta, c, U.path(root, f"weak_{i}")) for i in range(3 * len(FR.PASSES))]
    jobs = [j for j in jobs if not j[-1].exists()]
    jobs.sort(key=lambda j: j[0] != "noise")                              # noise first: its workers share one image
    with ProcessPoolExecutor(U.jobs()) as ex:
        for row in ex.map(_unit, jobs, chunksize=1):
            print(row["kind"], row["i"], row["a"], row["beta"], row.get("n_tracks", row.get("coverage")), flush=True)


# ---- 3. the pick ------------------------------------------------------------------------------------------------

def pick(run: Path) -> dict:
    table = {}
    for d in sorted((run / "ll_roc").iterdir()):
        rows = U.read_all(d)
        noise = [r for r in rows if r["kind"] == "noise"]; weak = [r for r in rows if r["kind"] == "weak"]
        if len(noise) < HOURS * 6 or len(weak) < 3 * len(FR.PASSES):
            sys.exit(f"{d.name}: unfinished ({len(noise)} noise, {len(weak)} weak)")
        a, beta = noise[0]["a"], noise[0]["beta"]
        table[d.name] = dict(a=a, beta=beta, false_per_hour_per_100hz=sum(r["n_tracks"] for r in noise) / HOURS,
                             coverage=float(np.median([r["coverage"] for r in weak])),
                             fragments=int(sum(r["fragments"] for r in weak)), bridges=int(sum(r["bridges"] for r in weak)),
                             error=float(np.median([r["error"] for r in weak])))
    ok = [k for k, v in table.items() if v["false_per_hour_per_100hz"] <= TARGET and v["coverage"] >= MIN_COVERAGE]
    best = min(ok, key=lambda k: (table[k]["beta"], table[k]["fragments"], -table[k]["a"])) if ok else None
    out = dict(table=table, eligible=ok, chosen=None if best is None else dict(a=table[best]["a"], beta=table[best]["beta"]),
               rule="lowest beta at <= 1 false track per hour per 100 Hz and weak-pass coverage >= 0.5; "
                    "ties: fewest fragments, then higher a")
    U.write(run / "ll_chosen.json", out)
    for k, v in sorted(table.items(), key=lambda kv: (kv[1]["a"], kv[1]["beta"])):
        print(f"a {v['a']:g} beta {v['beta']:.0e}: {v['false_per_hour_per_100hz']:.1f}/h, coverage {v['coverage']:.2f}, "
              f"fragments {v['fragments']}, bridges {v['bridges']}{'  <- eligible' if k in ok else ''}")
    print("chosen:", out["chosen"] or "NONE: the round stops before any real recording")
    return out


if __name__ == "__main__":
    run, step = Path(sys.argv[1]), sys.argv[2]
    if step == "constants":
        constants(run, sys.argv[3] if len(sys.argv) > 3 else None)
    elif step == "roc":
        roc(run, [float(x) for x in sys.argv[3:]])
    elif step == "pick":
        pick(run)
    else:
        sys.exit(__doc__)
