"""Frequency tracks on the Livermore passes against the trajectory-derived reference (PLAN Phase 2 item 3).
The criterion and every definition below were fixed before this ran.

Reference, per pass: the curve heard at the reconstructed microphone from the KML trajectory (PCHIP,
15 deg C), with the clock shift and f0 the Livermore audit fitted to the published ridge
(runs/2026-11-04-livermore-audit/passes.csv). One curve per pass, the same for every tracker. Its span
is the published ridge's span.

Spectrogram: the package STFT at 4 kHz (2.048 s Hann, 0.25 s hop), default whitening, 40-1900 Hz.
Band per pass (oracle, for the criterion): the reference's range over its span, 0.85x to 1.15x.

Trackers:
  A   tracks.ridge() on local_whiten over the whole clip (today's; the criterion baseline)
  A*  tracks.ridge() on the published span only (its oracle best case; reported only)
  B   freqtrack.track_window over the whole clip, all segment rules
  C   ssqueezepy.extract_ridges on |original STFT| over the whole clip, defaults, n_ridges=1
  B450  B over the package band 40-450 Hz, no oracle band (informational)

Metrics, per pass, on frames inside the reference span unless said otherwise:
  on:        |f - f_ref| <= max(2 bins, TOL f_ref), TOL = 2 % (1 % and 4 % reported)
  pass tracks: tracks with at least half their in-span points on (A, A*, C: their one path always)
  error:     median |f - f_ref| / f_ref over all in-span points of the pass tracks; with no pass track,
             over all in-span points; with no point, 1.0
  bridges:   off-runs of >= 1 s in any track that holds an on-run of >= 1 s (over the track's whole
             extent where the reference is defined)
  fragments: holes of >= 1 s in the union of on points between the first and last on frame
  tails:     the span's fraction before the first and after the last on point; coverage: on frames / span
Criterion, on the 29 passes with audit fit RMS < 1.6 % of f0:
  median over passes of B's error < A's; B's total bridges <= A's; B's total fragments <= A's.

usage: freqtrack_livermore.py RUN [rise-flag|run2]"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.signal as ss

sys.path.insert(0, str(Path(__file__).resolve().parent))
import livermore_audit as LA                                            # noqa: E402

from dopplertrack import audio, freqtrack as ft                          # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402
from dopplertrack.tracks import local_whiten, ridge                      # noqa: E402

AUDIT = LA.DATA / "runs/2026-11-04-livermore-audit"
SR, N, HOP = 4000, 8192, 0.25
TOLS = (0.01, 0.02, 0.04)
GOOD_RMS = 1.6
# Run 1 (the pre-registered run): theta 9.5 dB, birth 6, every rule cutting. Run 2 (the one recorded
# retune): TrackParams()'s defaults, derived on noise and a synthetic weak pass, rise and hop as flags.
RUN1 = ft.TrackParams(theta_db=9.5, birth=6.0, death=6.0, estimator="quinn2")
MODES = {"": (RUN1, ()), "_rise_flag": (RUN1, ("rise",)), "_run2": (ft.TrackParams(), ("rise", "hop"))}


def on_mask(f, fref, df, tol):
    return np.abs(f - fref) <= np.maximum(2 * df, tol * fref)


def runs(mask):
    """(start, stop) index pairs of the True runs."""
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def score(tracks, t_span, fref_fn, df, tol, hop=HOP):
    """tracks: list of (t, f) arrays. Returns the metrics above for one pass."""
    lo, hi = t_span
    frames = np.arange(lo, hi + 1e-9, hop)
    need = int(round(1.0 / hop))
    pass_pts, all_pts, bridges = [], [], 0
    on_frames = np.zeros(len(frames), bool)
    for t, f in tracks:
        ok = np.isfinite(f)
        t, f = t[ok], f[ok]
        fr = fref_fn(t)
        defined = np.isfinite(fr)
        on = np.zeros(len(t), bool); on[defined] = on_mask(f[defined], fr[defined], df, tol)
        ins = (t >= lo) & (t <= hi) & defined
        rel = np.abs(f[ins] - fr[ins]) / fr[ins]
        all_pts.append(rel)
        if ins.any() and on[ins].mean() >= 0.5:
            pass_pts.append(rel)
        if any(b - a >= need for a, b in runs(on & defined)):
            bridges += sum(1 for a, b in runs(~on & defined) if b - a >= need)
        idx = np.round((t[ins & on] - lo) / hop).astype(int)
        on_frames[idx[(idx >= 0) & (idx < len(frames))]] = True
    pts = pass_pts or all_pts
    pts = np.concatenate(pts) if pts and sum(len(p) for p in pts) else np.array([])
    err = float(np.median(pts)) if len(pts) else 1.0
    if on_frames.any():
        k = np.nonzero(on_frames)[0]
        inner = ~on_frames[k[0]:k[-1] + 1]
        frags = sum(1 for a, b in runs(inner) if b - a >= need)
        frags3 = sum(1 for a, b in runs(inner) if b - a >= 3 * need)
        tails = (k[0] + len(frames) - 1 - k[-1]) / len(frames)
    else:
        frags, frags3, tails = 0, 0, 1.0
    return dict(error=err, bridges=bridges, fragments=frags, fragments_3s=frags3, tails=float(tails), coverage=float(on_frames.mean()),
                n_tracks=len(tracks), n_pass_tracks=len(pass_pts))


def main(run: Path, tag: str = ""):
    params, flag = MODES[tag]
    import ssqueezepy
    passes = {p["id"]: p for p in LA.load_passes()}
    rows = {r["id"]: r for r in csv.DictReader(open(AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(AUDIT / "sites.json"))["sites"]}
    c = speed_of_sound(15.0)
    out, rise_report = [], []
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        th, g, _, _, _ = LA.heard_curve(p, sites[r["site"]], c)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        fref = lambda t: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        x, _ = audio.load_audio(p["dir"] / "audio.wav", SR)
        sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900)
        st = ft.SampleSTFT(x, SR, N, HOP)
        fs = fref(np.arange(*span, HOP))
        band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        res = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < GOOD_RMS, rms_pct=float(r["fit_rms_hz_15C"]) / f0 * 100,
                   band=band, span=span, f_ref_max=float(np.nanmax(fs)))
        trk = {}
        t0 = time.perf_counter()
        w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band)); trk["A"] = [(w.t, ridge(w))]
        res["time_A"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        w = local_whiten(sp.crop(*span, *band)); trk["Astar"] = [(w.t, ridge(w))]
        res["time_Astar"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        ev = ft.track_window(sp, st, sp.t[0], sp.t[-1], *band, params, flag=flag)
        trk["B"] = [(tr.t, tr.f) for tr in ev.tracks]
        res["time_B"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        _, _, Z = ss.stft(x, SR, nperseg=N, noverlap=N - int(HOP * SR), window="hann", boundary=None, padded=False)
        fz = np.fft.rfftfreq(N, 1 / SR); bm = (fz >= band[0]) & (fz <= band[1])
        tz = (N / 2 + np.arange(Z.shape[1]) * int(HOP * SR)) / SR
        idx = ssqueezepy.extract_ridges(np.abs(Z[bm]), fz[bm], n_ridges=1, transform="stft")
        trk["C"] = [(tz, fz[bm][np.asarray(idx).reshape(len(tz), -1)[:, 0]])]
        res["time_C"] = time.perf_counter() - t0
        for name, tr in trk.items():
            for tol in TOLS:
                res[f"{name}_{tol:g}"] = score(tr, span, fref, sp.df, tol)
        # rise and hop rules as flags: count the flagged points, and those that lie on the reference
        evf = ft.track_window(sp, st, sp.t[0], sp.t[-1], *band, params, flag=("rise", "hop"))
        rep = dict(id=pid)
        for rule in ("rise", "hop"):
            flagged = on_flagged = 0
            for tr in evf.tracks:
                for tt in tr.flags.get(rule, []):
                    flagged += 1
                    fr = fref(tt); k = int(np.argmin(np.abs(tr.t - tt)))
                    on_flagged += int(np.isfinite(fr) and on_mask(tr.f[k], fr, sp.df, 0.02))
            rep[rule] = dict(flagged=flagged, on_reference=on_flagged)
        rep["points"] = int(sum(tr.measured.sum() for tr in evf.tracks))
        rise_report.append(rep)
        # B over the package band, no oracle
        t0 = time.perf_counter()
        ev450 = ft.track_window(sp, st, sp.t[0], sp.t[-1], 40, 450, params, flag=flag)
        res["time_B450"] = time.perf_counter() - t0
        grp = ev450.event_track()
        contains = None
        if res["f_ref_max"] <= 450:
            contains = bool(grp) and any(score([(ev450.tracks[i].t, ev450.tracks[i].f)], span, fref, sp.df, 0.02)["n_pass_tracks"]
                                         for i in grp["tracks"])
        res["B450_contains_published"] = contains
        res["B450_any_track_on_published"] = (None if res["f_ref_max"] > 450 else any(
            score([(tr.t, tr.f)], span, fref, sp.df, 0.02)["n_pass_tracks"] for tr in ev450.tracks))
        out.append(res)
        b, a = res["B_0.02"], res["A_0.02"]
        print(f"{pid:12s} {'good' if res['good'] else 'flag'} err A {a['error']:.4f} B {b['error']:.4f} "
              f"C {res['C_0.02']['error']:.4f} | bridges A {a['bridges']} B {b['bridges']} | frags A {a['fragments']} "
              f"B {b['fragments']} | cov A {a['coverage']:.2f} B {b['coverage']:.2f} | B {res['time_B']:.2f}s "
              f"| rise {rep['rise']['flagged']}/{rep['rise']['on_reference']} hop {rep['hop']['flagged']}/{rep['hop']['on_reference']} "
              f"| 450 {contains}", flush=True)
    (run / f"livermore_tracks{tag}.json").write_text(json.dumps(dict(passes=out, rise=rise_report), indent=1, default=float))
    summarise(run, out, rise_report, tag)


def summarise(run, out, rise_report, tag=""):
    good = [r for r in out if r["good"]]
    lines = []
    for subset, rows in (("primary (29)", good), ("flagged (11)", [r for r in out if not r["good"]]), ("all (40)", out)):
        lines.append(f"== {subset}, n={len(rows)}")
        for tol in TOLS:
            for name in ("A", "Astar", "B", "C"):
                k = f"{name}_{tol:g}"
                e = np.median([r[k]["error"] for r in rows])
                lines.append(f"tol {tol:g} {name:5s} median error {e:.4f}  bridges {sum(r[k]['bridges'] for r in rows):3d}  "
                             f"fragments {sum(r[k]['fragments'] for r in rows):3d}  (3 s: {sum(r[k]['fragments_3s'] for r in rows):3d})  coverage {np.median([r[k]['coverage'] for r in rows]):.2f}  "
                             f"tails {np.median([r[k]['tails'] for r in rows]):.2f}")
            wins = sum(r[f"B_{tol:g}"]["error"] < r[f"A_{tol:g}"]["error"] for r in rows)
            lines.append(f"tol {tol:g}: B beats A on {wins} of {len(rows)} passes")
        for name in ("A", "Astar", "B", "C", "B450"):
            lines.append(f"runtime {name}: median {np.median([r['time_' + name] for r in rows]):.3f} s, max {max(r['time_' + name] for r in rows):.3f} s")
    a, b = good, [r["B_0.02"] for r in good]
    crit = (np.median([x["error"] for x in b]) < np.median([r["A_0.02"]["error"] for r in a]),
            sum(x["bridges"] for x in b) <= sum(r["A_0.02"]["bridges"] for r in a),
            sum(x["fragments"] for x in b) <= sum(r["A_0.02"]["fragments"] for r in a))
    lines.append(f"CRITERION (error, bridges, fragments): {crit} -> {'MET' if all(crit) else 'NOT MET'}")
    for rule in ("rise", "hop"):
        lines.append(f"{rule} rule: {sum(x[rule]['flagged'] for x in rise_report)} points flagged of {sum(x['points'] for x in rise_report)}, "
                     f"{sum(x[rule]['on_reference'] for x in rise_report)} on the reference, in {sum(x[rule]['on_reference'] > 0 for x in rise_report)} passes")
    inb = [r for r in out if r["B450_contains_published"] is not None]
    lines.append(f"B450: published line within 40-450 Hz on {len(inb)} passes; strongest group contains it on "
                 f"{sum(r['B450_contains_published'] for r in inb)}, any track on it on {sum(r['B450_any_track_on_published'] for r in inb)}")
    txt = "\n".join(lines)
    print(txt)
    (run / f"livermore_summary{tag}.txt").write_text(txt + "\n")


if __name__ == "__main__":
    # second argument: "rise-flag" (run 1's knobs, the rise rule flagging: the agreed fallback) or "run2"
    mode = {"rise-flag": "_rise_flag", "run2": "_run2"}.get(sys.argv[2] if len(sys.argv) > 2 else "", "")
    main(Path(sys.argv[1]), mode)
