"""Item 3 round 3: the likelihood tracker (dopplertrack.lltrack, L) against tracks.ridge() (A) and round 1's run 1
(B1) on the Livermore passes and the development events, at the knobs ll_roc.py picked on synthetic data. A and
B1 run on today's image (whitened over time, as shipped); L on the image whitened across frequency, which its
noise level needs. Definitions and criterion are round 1's (freqtrack_livermore.py): on the 29 primary passes at
2 %, L's median error below A's, its false bridges and fragments no more. The flagged 11, L over 40-450 Hz with no
oracle band, the development events (round 2's references, dev_references.json) and runtimes are reported.

Units: one per Livermore pass and one per development event under RUN/ll/a<a>_b<beta>/, written when finished and
skipped if present. Workers: DOPPLERTRACK_JOBS.

usage: ll_livermore.py RUN livermore|dev [PASS or EVENT ...]       (the knobs from RUN/ll_chosen.json)
       ll_livermore.py RUN merge"""
import csv
import json
import os
import sys
import time
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
import numpy as np                                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402
import hmm_livermore as HL                                               # noqa: E402
import livermore_audit as LA                                            # noqa: E402
import ll_roc as LR                                                      # noqa: E402
import units as U                                                       # noqa: E402

from dopplertrack import audio, freqtrack as ft, lltrack as ll           # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402
from dopplertrack.tracks import local_whiten, ridge                     # noqa: E402

SR, N, HOP = 4000, 8192, 0.25
KEYS = ("A", "L", "B1")


def knobs(run: Path) -> tuple[ll.LLParams, Path]:
    c = json.loads((run / "constants.json").read_text())
    ch = json.loads((run / "ll_chosen.json").read_text())["chosen"]
    if ch is None:
        sys.exit("ll_chosen.json has no pick: the round stops before any real recording")
    return LR.params(c, ch["a"], ch["beta"]), run / "ll" / f"a{ch['a']:g}_b{ch['beta']:.0e}"


def track_all(x, span, band, p, fmax=1900.0):
    sp_t = HL.spectrogram(x, "time", fmax); sp_f = HL.spectrogram(x, "frequency", fmax)
    st = ft.SampleSTFT(x, SR, N, HOP)
    res = {}
    t0 = time.perf_counter()
    w = local_whiten(sp_t.crop(sp_t.t[0], sp_t.t[-1], *band)); res["A"] = [(w.t, ridge(w))]
    res["time_A"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    ev = ll.ll_track(sp_f, st, sp_f.t[0], sp_f.t[-1], *band, p)
    res["L"] = [(tr.t, tr.f) for tr in ev.tracks]; res["time_L"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    ev1 = ft.track_window(sp_t, st, sp_t.t[0], sp_t.t[-1], *band, ft.TrackParams(), flag=())
    res["B1"] = [(tr.t, tr.f) for tr in ev1.tracks]; res["time_B1"] = time.perf_counter() - t0
    return res, sp_t, sp_f, st


def livermore_one(job):
    pid, p, out_path = job
    if out_path.exists():
        return json.loads(out_path.read_text())
    if not HL._LIV:
        HL._liv_init()
    r, q = HL._LIV["rows"][pid], HL._LIV["passes"][pid]
    th, g, _, _, _ = LA.heard_curve(q, HL._LIV["sites"][r["site"]], speed_of_sound(15.0))
    shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
    fref = lambda t: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
    span = (q["ridge"][0, 0] - start, q["ridge"][-1, 0] - start)
    fs = fref(np.arange(*span, HOP)); band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
    x, _ = audio.load_audio(q["dir"] / "audio.wav", SR)
    res, sp_t, sp_f, st = track_all(x, span, band, p)
    row = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < FL.GOOD_RMS, band=band,
               **{f"time_{k}": res[f"time_{k}"] for k in KEYS})
    for k in KEYS:
        row[k] = FL.score(res[k], span, fref, sp_t.df, 0.02)
    t0 = time.perf_counter()
    ev = ll.ll_track(sp_f, st, sp_f.t[0], sp_f.t[-1], 40.0, 450.0, p)      # no oracle band
    row["time_L450"] = time.perf_counter() - t0
    if float(np.nanmax(fs)) <= 450:
        grp = ev.event_track()
        row["L450_contains"] = bool(grp) and any(FL.score([(ev.tracks[i].t, ev.tracks[i].f)], span, fref, sp_f.df, 0.02)["n_pass_tracks"]
                                                  for i in grp["tracks"])
    U.write(out_path, row)
    print(pid, "good" if row["good"] else "flag", " | ".join(f"{k} err {row[k]['error']:.4f} br {row[k]['bridges']} fr {row[k]['fragments']} cov {row[k]['coverage']:.2f}"
                                                                for k in KEYS), f"L {row['time_L']:.2f}s", flush=True)
    return row


def dev_one(job):
    ev, ref, p, out_path = job
    if out_path.exists():
        return json.loads(out_path.read_text())
    name, src, (a, b), band, *_ = ev
    x, a0 = HL.dev_audio(ev)
    fref = HL.dev_fref(ev, ref)
    res, sp_t, _, _ = track_all(x, (a - a0, b - a0), band, p, fmax=1000.0)
    row = dict(event=name, judged=ref["judged"], **{k: FL.score(res[k], (a - a0, b - a0), fref, sp_t.df, 0.02) for k in KEYS},
               **{f"time_{k}": res[f"time_{k}"] for k in KEYS})
    U.write(out_path, row)
    print(name, " | ".join(f"{k} err {row[k]['error']:.4f} br {row[k]['bridges']} fr {row[k]['fragments']}" for k in KEYS), flush=True)
    return row


def summarise(root: Path, liv, devs) -> str:
    lines = []
    if liv:
        for title, rows in (("primary (29)", [r for r in liv if r["good"]]), ("flagged (11)", [r for r in liv if not r["good"]])):
            lines.append(f"== Livermore {title}")
            for k in KEYS:
                lines.append(f"{k:3s} median error {np.median([r[k]['error'] for r in rows]):.4f}  bridges {sum(r[k]['bridges'] for r in rows)}  "
                             f"fragments {sum(r[k]['fragments'] for r in rows)} (3 s: {sum(r[k]['fragments_3s'] for r in rows)})  "
                             f"coverage {np.median([r[k]['coverage'] for r in rows]):.2f}  tails {np.median([r[k]['tails'] for r in rows]):.2f}  "
                             f"runtime median {np.median([r[f'time_{k}'] for r in rows]):.2f} s")
        good = [r for r in liv if r["good"]]
        crit = (np.median([r["L"]["error"] for r in good]) < np.median([r["A"]["error"] for r in good]),
                sum(r["L"]["bridges"] for r in good) <= sum(r["A"]["bridges"] for r in good),
                sum(r["L"]["fragments"] for r in good) <= sum(r["A"]["fragments"] for r in good))
        lines.append(f"CRITERION (error, bridges, fragments): {tuple(bool(c) for c in crit)} -> {'MET' if all(crit) else 'NOT MET'}")
        inb = [r for r in liv if "L450_contains" in r]
        lines.append(f"L over 40-450 Hz: strongest group holds the published line on {sum(r['L450_contains'] for r in inb)} of {len(inb)}")
    if devs:
        lines.append("== development events (reported only)")
        for r in devs:
            lines.append(f"{r['event']:22s} {'judged' if r['judged'] else 'NOT judged'}  " +
                         "  ".join(f"{k}: err {r[k]['error']:.4f} br {r[k]['bridges']} fr {r[k]['fragments']}" for k in KEYS))
        j = [r for r in devs if r["judged"]]
        lines.append("summed over judged events: " + "  ".join(f"{k}: bridges {sum(r[k]['bridges'] for r in j)} fragments {sum(r[k]['fragments'] for r in j)}"
                                                                for k in KEYS))
    txt = "\n".join(lines)
    (root / "ll_summary.txt").write_text(txt + "\n")
    return txt


if __name__ == "__main__":
    run, step, chosen = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    p, root = knobs(run)
    if step == "livermore":
        pids = U.select(sorted(r["id"] for r in csv.DictReader(open(FL.AUDIT / "passes.csv"))), chosen)
        HL._pool(livermore_one, [(pid, p, U.path(root, "livermore", pid)) for pid in pids], HL._liv_init)
    elif step == "dev":
        refs = json.loads((run / "dev_references.json").read_text())
        names = U.select([e[0] for e in HL.DEV], chosen)
        HL._pool(dev_one, [(e, r, p, U.path(root, "dev", e[0].replace(" ", "_"))) for e, r in zip(HL.DEV, refs) if e[0] in names])
    elif step == "merge":
        print(summarise(root, U.read_all(root / "livermore") or None, U.read_all(root / "dev") or None))
    else:
        sys.exit(__doc__)
