"""Informational companions to window_length.py (PLAN Phase 2 item 5).

1. Harris 1978 eq. 17: the correlation of a Hann window with itself shifted by k hops, rho_k, and the
   factor by which overlap shrinks the count of independent frames, 1 + 2 sum rho_k^2 (power estimates
   of Gaussian noise correlate as rho^2), at 2.048, 1.024 and 0.512 s with a 0.25 s hop, and 2.048 s
   with a 1 s hop.
2. Noise in the whitened image per window: the SD of whitened cells (dB above the per-bin median), on
   white noise and on Oyster Bay's blind-labelled "absent" stretches (bench/labels), 60-450 Hz; and the
   whitened level of a 200 Hz tone of fixed amplitude, on for 60 s of 600, which shows the window's gain.
3. freqtrack's theta per window: run 1's derivation (white noise, two hours, 100 Hz band, M 8, birth and
   death 6, every rule cutting) repeated at each window, at 1 false track per hour per 100 Hz.
4. freqtrack (run 1's knobs with that window's theta) and ridge() at each window on the 40 Livermore
   passes, scored as in freqtrack_livermore.py.

usage: window_noise_tracker.py RUN LABELS.json"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.signal as ss

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402
import livermore_audit as LA                                            # noqa: E402
import window_length as WL                                              # noqa: E402

from dopplertrack import freqtrack as ft                                 # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402
from dopplertrack.tracks import local_whiten, ridge                      # noqa: E402

SR, NFFT, HOP = WL.SR, WL.NFFT, WL.HOP
# from low to high, stopping at the first theta at the target (a first grid started at 8.5 dB, where the
# shorter windows were already at 0 false tracks, so it could not find their threshold)
THETAS = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.25, 9.5, 9.75, 10.0, 10.5, 11.0]


def harris():
    out = {}
    for n, hop in ((8192, 0.25), (4096, 0.25), (2048, 0.25), (8192, 1.0)):
        w = ss.get_window("hann", n); h = int(hop * SR)
        rho = [float(np.dot(w[:n - k * h], w[k * h:]) / np.dot(w, w)) for k in range(1, n // h + 1) if k * h < n]
        out[f"{n / SR:.3f}s@{hop}s"] = dict(rho=[round(r, 3) for r in rho], factor=1 + 2 * sum(r * r for r in rho))
        print(f"Hann {n / SR:.3f} s, hop {hop} s: rho {[round(r, 2) for r in rho[:5]]}, independent-frame factor {out[f'{n / SR:.3f}s@{hop}s']['factor']:.2f}")
    return out


def noise_sd(labels):
    out = {}
    x = np.random.default_rng(0).standard_normal(600 * SR).astype(np.float32)
    t = np.arange(len(x)) / SR
    tone = (x + 0.05 * np.sin(2 * np.pi * 200.0 * t) * ((t >= 100) & (t < 160))).astype(np.float32)   # on 10 % of the time
    d = json.loads(Path(labels).read_text())
    absent = [(w["start"], w["end"]) for w in d["windows"] if w["class"] == "absent"]
    ob = WL.decode(WL.DATA / d["recording"]["source"], 0, 1200)
    for n in WL.WINDOWS:
        sp = WL.spectrogram(x, n); b = (sp.f >= 60) & (sp.f <= 450)
        sp_t = WL.spectrogram(tone, n); j = int(np.argmin(np.abs(sp_t.f - 200.0)))
        on = (sp_t.t >= 102) & (sp_t.t <= 158)
        so = WL.spectrogram(ob, n); bo = (so.f >= 60) & (so.f <= 450)
        m = np.zeros(len(so.t), bool)
        for a, e in absent:
            m |= (so.t >= a + 1.5) & (so.t <= e - 1.5)
        out[n] = dict(white_sd_db=float(sp.S[b].std()), tone_level_db=float(np.median(sp_t.S[j, on])),
                      oyster_absent_sd_db=float(so.S[np.ix_(bo, m)].std()), oyster_absent_s=float(m.sum() * HOP))
        print(f"{n / SR:.3f} s: whitened SD, white noise {out[n]['white_sd_db']:.2f} dB, Oyster Bay absent stretches "
              f"{out[n]['oyster_absent_sd_db']:.2f} dB ({out[n]['oyster_absent_s']:.0f} s); 0.05 tone at 200 Hz "
              f"{out[n]['tone_level_db']:.1f} dB", flush=True)
    return out


def theta_per_window():
    out = {}
    x = np.random.default_rng(0).standard_normal(2 * 3600 * SR).astype(np.float32)
    for n in WL.WINDOWS:
        off = (NFFT - n) // 2
        sp = WL.spectrogram(x, n)
        st = ft.SampleSTFT(x[off:], SR, n, HOP, nfft=NFFT, t0=off / SR)
        rates = {}
        for th in THETAS:
            p = ft.TrackParams(theta_db=th, birth=6.0, death=6.0)
            k = sum(len(ft.track_window(sp, st, a, a + 600, 150, 250, p, flag=()).tracks) for a in np.arange(0, 7200, 600.0))
            rates[th] = k / 2.0
            print(f"{n / SR:.3f} s theta {th}: {rates[th]:.1f} per hour per 100 Hz", flush=True)
            if rates[th] <= 1.0:
                break
        out[n] = dict(rates=rates, theta=min(t for t, r in rates.items() if r <= 1.0))
    return out


def tracker(run, thetas):
    passes = {p["id"]: p for p in LA.load_passes()}
    rows = {r["id"]: r for r in csv.DictReader(open(FL.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(FL.AUDIT / "sites.json"))["sites"]}
    c = speed_of_sound(15.0)
    res = []
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        th, g, _, _, _ = LA.heard_curve(p, sites[r["site"]], c)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        fref = lambda t, th=th, g=g: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        fs = fref(np.arange(*span, HOP)); band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        x, _ = WL.audio.load_audio(p["dir"] / "audio.wav", SR)
        row = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < FL.GOOD_RMS)
        for n in WL.WINDOWS:
            off = (NFFT - n) // 2
            sp = WL.spectrogram(x, n)
            st = ft.SampleSTFT(x[off:], SR, n, HOP, nfft=NFFT, t0=off / SR)
            w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band))
            row[f"ridge_{n}"] = FL.score([(w.t, ridge(w))], span, fref, sp.df, 0.02)
            t0 = time.perf_counter()
            ev = ft.track_window(sp, st, sp.t[0], sp.t[-1], *band, ft.TrackParams(theta_db=thetas[n]), flag=())
            row[f"time_{n}"] = time.perf_counter() - t0
            row[f"B_{n}"] = FL.score([(tr.t, tr.f) for tr in ev.tracks], span, fref, sp.df, 0.02)
        res.append(row)
        print(pid, " ".join(f"{n}: A {row[f'ridge_{n}']['error']:.4f}/{row[f'ridge_{n}']['fragments']} "
                            f"B {row[f'B_{n}']['error']:.4f}/{row[f'B_{n}']['fragments']}" for n in WL.WINDOWS), flush=True)
    good = [r for r in res if r["good"]]
    lines = ["== tracker at each window, 29 primary passes, 2 % (run 1's knobs, theta per window)"]
    for n in WL.WINDOWS:
        for name in ("ridge", "B"):
            k = f"{name}_{n}"
            lines.append(f"{n / SR:.3f} s {name:5s}: median error {np.median([r[k]['error'] for r in good]):.4f}, bridges "
                         f"{sum(r[k]['bridges'] for r in good)}, fragments {sum(r[k]['fragments'] for r in good)} "
                         f"(3 s: {sum(r[k]['fragments_3s'] for r in good)}), coverage {np.median([r[k]['coverage'] for r in good]):.2f}")
        lines.append(f"{n / SR:.3f} s B runtime per pass: median {np.median([r[f'time_{n}'] for r in res]):.2f} s")
    print("\n".join(lines))
    (run / "window_tracker.json").write_text(json.dumps(res, indent=1, default=float))
    return lines


if __name__ == "__main__":
    run = Path(sys.argv[1])
    out = dict(harris=harris(), noise=noise_sd(sys.argv[2]))
    out["theta"] = theta_per_window()
    lines = tracker(run, {n: v["theta"] for n, v in out["theta"].items()})
    (run / "window_noise_tracker.json").write_text(json.dumps(out, indent=1, default=float))
    (run / "window_tracker_summary.txt").write_text("\n".join(lines) + "\n")
