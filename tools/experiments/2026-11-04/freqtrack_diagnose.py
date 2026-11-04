"""Diagnosis after the single Livermore run, not tuning: (1) ssqueezepy's extract_ridges on a synthetic
tone, to check the call; (2) on the primary Livermore passes, B's coverage with each segment rule
switched off in turn, and the share of reference-span frames whose whitened level at the reference
cell is below theta (which no rule can recover).

usage: freqtrack_diagnose.py RUN"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402
import livermore_audit as LA                                            # noqa: E402

from dopplertrack import audio, freqtrack as ft                          # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402
from dopplertrack.tracks import local_whiten                             # noqa: E402

SR, N, HOP = FL.SR, FL.N, FL.HOP


def ssq_check():
    import ssqueezepy
    t = np.arange(0, 30, 1 / SR)
    f = 300 - 3 * t
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.random.default_rng(0).standard_normal(len(t))
    _, _, Z = ss.stft(x, SR, nperseg=N, noverlap=N - int(HOP * SR), window="hann", boundary=None, padded=False)
    fz = np.fft.rfftfreq(N, 1 / SR); bm = (fz >= 150) & (fz <= 350)
    tz = (N / 2 + np.arange(Z.shape[1]) * int(HOP * SR)) / SR
    idx = np.asarray(ssqueezepy.extract_ridges(np.abs(Z[bm]), fz[bm], n_ridges=1, transform="stft")).reshape(len(tz), -1)[:, 0]
    err = np.abs(fz[bm][idx] - np.interp(tz, t, f))
    print(f"ssqueezepy on a 300 -> 210 Hz chirp: median |error| {np.median(err):.2f} Hz, max {err.max():.1f} Hz")
    return float(np.median(err))


def main(run):
    out = {"ssqueezepy_synthetic_median_err_hz": ssq_check()}
    passes = {p["id"]: p for p in LA.load_passes()}
    rows = {r["id"]: r for r in csv.DictReader(open(FL.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(FL.AUDIT / "sites.json"))["sites"]}
    c = speed_of_sound(15.0)
    variants = {"all rules": ("weak", "rise", "hop", "link", "crossing"), "no rules": (),
                "no weak": ("rise", "hop", "link", "crossing"), "no rise": ("weak", "hop", "link", "crossing"),
                "no hop": ("weak", "rise", "link", "crossing"), "no link": ("weak", "rise", "hop", "crossing")}
    cov = {k: [] for k in variants}; frag = {k: [] for k in variants}; below = []
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        if float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) * 100 >= FL.GOOD_RMS:
            continue
        th, g, _, _, _ = LA.heard_curve(p, sites[r["site"]], c)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        fref = lambda t, th=th, g=g: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        x, _ = audio.load_audio(p["dir"] / "audio.wav", SR)
        sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900)
        st = ft.SampleSTFT(x, SR, N, HOP)
        fs = fref(np.arange(*span, HOP)); band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        w = local_whiten(sp.crop(sp.t[0], sp.t[-1]), floor=-np.inf)
        ins = (w.t >= span[0]) & (w.t <= span[1])
        fr = fref(w.t[ins]); j = np.round((fr - w.f[0]) / w.df).astype(int)
        lev = np.array([w.S[max(jj - 1, 0):jj + 2, k].max() for jj, k in zip(j, np.nonzero(ins)[0])])
        below.append(float(np.mean(lev < ft.TrackParams().theta_db)))
        for name, rules in variants.items():
            ev = ft.track_window(sp, st, sp.t[0], sp.t[-1], *band, rules=rules)
            m = FL.score([(tr.t, tr.f) for tr in ev.tracks], span, fref, sp.df, 0.02)
            cov[name].append(m["coverage"]); frag[name].append(m["fragments"])
    out["share_of_span_below_theta"] = dict(median=float(np.median(below)), per_pass=below)
    print(f"share of reference-span frames with whitened level < theta at the reference: median {np.median(below):.2f}")
    for name in variants:
        out[name] = dict(coverage=float(np.median(cov[name])), fragments=int(sum(frag[name])))
        print(f"{name:10s}: median coverage {np.median(cov[name]):.2f}, fragments {sum(frag[name])}")
    (run / "freqtrack_diagnose.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
