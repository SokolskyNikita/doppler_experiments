"""Item 3 round 2: the hysteresis-in-states tracker (dopplertrack.hmmtrack) against tracks.ridge() and round 1's run,
on the Livermore passes and the development events. Definitions and criterion are round 1's
(freqtrack_livermore.py), fixed before this runs:
  Livermore, the 29 primary passes, 2 %, the fixed reference per pass: H's median error below ridge()'s, its false
  bridges no more and its fragments no more. Reported beside: round 1's run 1, fragments at >= 3 s, coverage, the
  flagged 11, the tracker over 40-450 Hz with no oracle band, runtime per pass.
Development events (reported only, not in the pass/fail): Oyster Bay ev1/ev2, eagle cam ev1/ev2, ob-e03 on its
345-255 Hz line, and sw-e01 (overlapping). Each event's reference is the trajectory curve at the true point with f0
and clock shift chosen by today's curve score (EventWindow.sweep_scores) over 0.85-1.15 x f0 and +-15 s, written
to dev_references.json before any tracker runs on the events; its f0 is reported beside item 8's warp estimates,
and an event where they disagree by more than 2 % is judged on nothing.

Units: the references (one file, RUN/dev_references.json), one per Livermore pass and one per development event
under RUN/hmm/<whiten>_tc<theta_cont>_tb<theta_birth>/, each written when it finishes and skipped if present, so
the same command resumes a stopped job and boxes split it by naming passes or events. Workers: DOPPLERTRACK_JOBS.

usage: hmm_livermore.py RUN references
       hmm_livermore.py RUN livermore|dev WHITEN THETA_CONT THETA_BIRTH [PASS or EVENT ...]
       hmm_livermore.py RUN merge WHITEN THETA_CONT THETA_BIRTH"""
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
import numpy as np                                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402
import livermore_audit as LA                                            # noqa: E402
import units as U                                                       # noqa: E402

from dopplertrack import audio, freqtrack as ft, hmmtrack as hm          # noqa: E402
from dopplertrack.adsb import load_traces                                # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402
from dopplertrack.geo import lla_to_enu                                  # noqa: E402
from dopplertrack.score import EventWindow, modelled_curve               # noqa: E402
from dopplertrack.search import build_segments                           # noqa: E402
from dopplertrack.terrain import Terrain                                 # noqa: E402
from dopplertrack.tracks import EventFit, local_whiten, ridge            # noqa: E402

DATA = LA.DATA
REPO = Path(__file__).resolve().parents[3]
SR, N, HOP = 4000, 8192, 0.25
C = speed_of_sound()
WARP_F0 = {"oyster ev1": 114.3, "oyster ev2": 127.7}                     # item 8, the warp at the reference
# (name, source, window, band, traces, truth point, icao, heard (approx, recording s), audio zero UTC, f0 seed:
#  the saved fit's for the README events, the labelled line's straight-pass f0, 2 f_in f_out / (f_in + f_out), otherwise)
DEV = [("oyster ev1", "raw/audio/youtube/oyster_bay.webm", (2090, 2200), (95, 200), "derived/oyster_bay/traces_ny.npz",
        (40.876466, -73.524951), "a1dfeb", 2155.6, "2026-09-08T20:17:30.72Z", 112.62),
       ("oyster ev2", "raw/audio/youtube/oyster_bay.webm", (3020, 3130), (95, 195), "derived/oyster_bay/traces_ny.npz",
        (40.876466, -73.524951), "ace391", 3068.4, "2026-09-08T20:17:30.72Z", 132.41),
       ("eagle ev1", "raw/audio/youtube/swfl_2024-12-28.webm", (20117.024, 20357.024), (60, 300), "derived/swfl/traces_swfl.npz",
        (26.702359, -81.847766), "a2baea", 20247.5, "2024-12-28T14:21:08.49Z", 108.14),
       ("eagle ev2", "raw/audio/youtube/swfl_2024-12-28.webm", (20457.024, 20697.024), (60, 300), "derived/swfl/traces_swfl.npz",
        (26.702359, -81.847766), "a336e4", 20585.3, "2024-12-28T14:21:08.49Z", 133.15),
       ("ob-e03", "raw/audio/youtube/oyster_bay.webm", (105, 200), (0.85 * 255, 1.15 * 345), "derived/oyster_bay/traces_ny.npz",
        (40.876466, -73.524951), "a40d8f", 130.5, "2026-09-08T20:17:30.72Z", 2 * 345 * 255 / 600),
       ("sw-e01 (overlapping)", "raw/audio/youtube/swfl_2024-12-28.webm", (3600, 3775), (0.85 * 105, 1.15 * 165),
        "derived/swfl/traces_swfl.npz", (26.702359, -81.847766), "a625e2", 3701.4, "2024-12-28T14:21:08.49Z", 2 * 165 * 105 / 270)]


def unix(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def decode(src, t0, dur):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-t", f"{dur}", "-i", str(src), "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, check=True, capture_output=True).stdout, np.float32).copy()


def spectrogram(x, whiten, fmax=1900.0):
    return audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=fmax, whiten=whiten)


def params(tc, tb):
    return hm.with_params(hm.HMMParams(), theta_cont=tc, theta_birth=tb)


# ---- development references, before any tracker --------------------------------------------------

def dev_audio(ev, pad=300.0):
    name, src, (a, b), *_ = ev
    a0 = max(a - pad, 0.0)
    return decode(DATA / src, a0, b - a0 + pad), a0


def references(run):
    out = []
    for ev in DEV:
        name, src, (a, b), (lo, hi), trp, (lat, lon), icao, heard, clock, f0_seed = ev
        x, a0 = dev_audio(ev)
        sp = spectrogram(x, "time", fmax=1000.0)                          # today's curve score on today's image
        lat0, lon0 = lat, lon
        el = Terrain().elevation(np.array([lat]), np.array([lon]))
        obs = lla_to_enu(np.array([lat]), np.array([lon]), el, lat0, lon0)[0]
        segs = [s for s in build_segments(load_traces(DATA / trp), lat0, lon0) if s.icao == icao]
        T0 = -unix(clock) - a0                                            # segment audio = unix + T0
        seg = min(segs, key=lambda s: np.min(np.abs(s.t + np.linalg.norm(s.enu - obs, axis=1) / C + T0 - (heard - a0))))
        to, r = modelled_curve(seg, obs, C)
        f0_guess = f0_seed
        fit = EventFit(t_cpa=0.5 * (a + b) - a0, t_cpa_emit=0.5 * (a + b) - a0, f0=f0_guess, v=0, d=0,
                       t_start=a - a0, t_end=b - a0, score=0, f_pre=hi, f_post=lo)
        w = EventWindow.from_fit(sp, fit, 1)
        shifts = np.arange(-15, 15.001, 0.1); scales = np.arange(0.85, 1.1501, 0.0025)
        sc = w.sweep_scores(to + T0, r, shifts, scales)
        i, j = np.unravel_index(int(np.argmax(sc)), sc.shape)
        f0 = float(f0_guess * scales[j]); shift = float(shifts[i])
        warp = WARP_F0.get(name)
        agree = None if warp is None else abs(f0 / warp - 1) <= 0.02
        out.append(dict(event=name, f0=f0, shift_s=shift, clock_T0=T0, a0=a0, seg_t0=float(seg.t[0]), icao=icao,
                        score=float(sc[i, j]), warp_f0=warp, agrees_with_warp=agree,
                        judged=agree is not False, at_scale_edge=j in (0, len(scales) - 1),
                        at_shift_edge=i in (0, len(shifts) - 1)))
        print(out[-1], flush=True)
    U.write(run / "dev_references.json", out)
    return out


# ---- the trackers on one span -------------------------------------------------------------------

def track_all(x, sp, st, span, band, fref, p):
    res = {}
    t0 = time.perf_counter()
    w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band)); res["A"] = [(w.t, ridge(w))]
    res["time_A"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    ev = hm.hmm_track(sp, st, sp.t[0], sp.t[-1], *band, p)
    res["H"] = [(tr.t, tr.f) for tr in ev.tracks]; res["time_H"] = time.perf_counter() - t0
    res["H_groups"] = ev.groups
    t0 = time.perf_counter()
    ev1 = ft.track_window(sp, st, sp.t[0], sp.t[-1], *band, ft.TrackParams(), flag=())
    res["B1"] = [(tr.t, tr.f) for tr in ev1.tracks]; res["time_B1"] = time.perf_counter() - t0
    return res


_LIV: dict = {}


def _liv_init():
    _LIV["passes"] = {q["id"]: q for q in LA.load_passes()}
    _LIV["rows"] = {r["id"]: r for r in csv.DictReader(open(FL.AUDIT / "passes.csv"))}
    _LIV["sites"] = {s["name"]: s for s in json.load(open(FL.AUDIT / "sites.json"))["sites"]}


def livermore_one(job):
    pid, whiten, tc, tb, out_path = job
    if out_path.exists():
        return json.loads(out_path.read_text())
    if not _LIV:
        _liv_init()
    p = params(tc, tb)
    r, q = _LIV["rows"][pid], _LIV["passes"][pid]
    th, g, _, _, _ = LA.heard_curve(q, _LIV["sites"][r["site"]], speed_of_sound(15.0))
    shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
    fref = lambda t: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
    span = (q["ridge"][0, 0] - start, q["ridge"][-1, 0] - start)
    fs = fref(np.arange(*span, HOP)); band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
    x, _ = audio.load_audio(q["dir"] / "audio.wav", SR)
    sp = spectrogram(x, whiten); st = ft.SampleSTFT(x, SR, N, HOP)
    res = track_all(x, sp, st, span, band, fref, p)
    row = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < FL.GOOD_RMS, band=band,
               **{f"time_{k}": res[f"time_{k}"] for k in ("A", "H", "B1")})
    for k in ("A", "H", "B1"):
        row[k] = FL.score(res[k], span, fref, sp.df, 0.02)
    t0 = time.perf_counter()
    ev = hm.hmm_track(sp, st, sp.t[0], sp.t[-1], 40.0, 450.0, p)           # no oracle band
    row["time_H450"] = time.perf_counter() - t0
    if float(np.nanmax(fs)) <= 450:
        grp = ev.event_track()
        row["H450_contains"] = bool(grp) and any(FL.score([(ev.tracks[i].t, ev.tracks[i].f)], span, fref, sp.df, 0.02)["n_pass_tracks"]
                                                  for i in grp["tracks"])
    U.write(out_path, row)
    print(pid, "good" if row["good"] else "flag", " | ".join(f"{k} err {row[k]['error']:.4f} br {row[k]['bridges']} fr {row[k]['fragments']} cov {row[k]['coverage']:.2f}"
                                                                for k in ("A", "H", "B1")), f"H {row['time_H']:.2f}s", flush=True)
    return row


def dev_one(job):
    ev, ref, whiten, tc, tb, out_path = job
    if out_path.exists():
        return json.loads(out_path.read_text())
    p = params(tc, tb)
    name, src, (a, b), band, trp, (lat, lon), icao, heard, clock, _ = ev
    x, a0 = dev_audio(ev)
    el = Terrain().elevation(np.array([lat]), np.array([lon]))
    obs = lla_to_enu(np.array([lat]), np.array([lon]), el, lat, lon)[0]
    seg = next(s for s in build_segments(load_traces(DATA / trp), lat, lon) if s.icao == icao and s.t[0] == ref["seg_t0"])
    to, r = modelled_curve(seg, obs, C)
    T = ref["clock_T0"] + ref["shift_s"]
    fref = lambda t: ref["f0"] * np.interp(np.asarray(t), to + T, r, left=np.nan, right=np.nan)
    sp = spectrogram(x, whiten, fmax=1000.0); st = ft.SampleSTFT(x, SR, N, HOP)
    res = track_all(x, sp, st, (a - a0, b - a0), band, fref, p)
    row = dict(event=name, judged=ref["judged"], **{k: FL.score(res[k], (a - a0, b - a0), fref, sp.df, 0.02) for k in ("A", "H", "B1")},
               **{f"time_{k}": res[f"time_{k}"] for k in ("A", "H", "B1")})
    U.write(out_path, row)
    print(name, " | ".join(f"{k} err {row[k]['error']:.4f} br {row[k]['bridges']} fr {row[k]['fragments']}" for k in ("A", "H", "B1")), flush=True)
    return row


def _pool(fn, jobs, init=None):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(U.jobs(), initializer=init) as ex:
        return list(ex.map(fn, jobs))


def unit_root(run, whiten, tc, tb):
    return run / "hmm" / f"{whiten}_tc{tc:g}_tb{tb:g}"


def summarise(run, liv, devs):
    lines = []
    if liv:
        for title, rows in (("primary (29)", [r for r in liv if r["good"]]), ("flagged (11)", [r for r in liv if not r["good"]])):
            lines.append(f"== Livermore {title}")
            for k in ("A", "H", "B1"):
                lines.append(f"{k:3s} median error {np.median([r[k]['error'] for r in rows]):.4f}  bridges {sum(r[k]['bridges'] for r in rows)}  "
                             f"fragments {sum(r[k]['fragments'] for r in rows)} (3 s: {sum(r[k]['fragments_3s'] for r in rows)})  "
                             f"coverage {np.median([r[k]['coverage'] for r in rows]):.2f}  tails {np.median([r[k]['tails'] for r in rows]):.2f}  "
                             f"runtime median {np.median([r[f'time_{k}'] for r in rows]):.2f} s")
        good = [r for r in liv if r["good"]]
        crit = (np.median([r["H"]["error"] for r in good]) < np.median([r["A"]["error"] for r in good]),
                sum(r["H"]["bridges"] for r in good) <= sum(r["A"]["bridges"] for r in good),
                sum(r["H"]["fragments"] for r in good) <= sum(r["A"]["fragments"] for r in good))
        lines.append(f"CRITERION (error, bridges, fragments): {tuple(bool(c) for c in crit)} -> {'MET' if all(crit) else 'NOT MET'}")
        inb = [r for r in liv if "H450_contains" in r]
        lines.append(f"H over 40-450 Hz: strongest group holds the published line on {sum(r['H450_contains'] for r in inb)} of {len(inb)}")
    if devs:
        lines.append("== development events (reported only)")
        for r in devs:
            lines.append(f"{r['event']:22s} {'judged' if r['judged'] else 'NOT judged (reference disagrees with the warp)'}  " +
                         "  ".join(f"{k}: err {r[k]['error']:.4f} br {r[k]['bridges']} fr {r[k]['fragments']}" for k in ("A", "H", "B1")))
        j = [r for r in devs if r["judged"]]
        lines.append("summed over judged events: " + "  ".join(f"{k}: bridges {sum(r[k]['bridges'] for r in j)} fragments {sum(r[k]['fragments'] for r in j)}"
                                                                for k in ("A", "H", "B1")))
    txt = "\n".join(lines); print(txt)
    (run / "hmm_summary.txt").write_text(txt + "\n")


if __name__ == "__main__":
    run, step = Path(sys.argv[1]), sys.argv[2]
    if step == "references":                                              # once, before any tracker runs on the events
        if not (run / "dev_references.json").exists():
            references(run)
        sys.exit(0)
    whiten, tc, tb, chosen = sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), sys.argv[6:]
    root = unit_root(run, whiten, tc, tb)
    if step == "livermore":
        pids = U.select(sorted(r["id"] for r in csv.DictReader(open(FL.AUDIT / "passes.csv"))), chosen)
        _pool(livermore_one, [(pid, whiten, tc, tb, U.path(root, "livermore", pid)) for pid in pids], _liv_init)
    elif step == "dev":
        refs = json.loads((run / "dev_references.json").read_text())
        names = U.select([e[0] for e in DEV], chosen)
        _pool(dev_one, [(e, r, whiten, tc, tb, U.path(root, "dev", e[0].replace(" ", "_")))
                        for e, r in zip(DEV, refs) if e[0] in names])
    elif step == "merge":
        summarise(root, U.read_all(root / "livermore") or None, U.read_all(root / "dev") or None)
    else:
        sys.exit(__doc__)
