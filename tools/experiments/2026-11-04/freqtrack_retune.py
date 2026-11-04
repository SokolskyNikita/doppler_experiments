"""The one recorded retune of dopplertrack.freqtrack (after Livermore run 1), on synthetic cases only;
Livermore is not opened here.

Hysteresis through costs (Kay II 7.6: a tone persisting for N frames is detectable at a per-frame level
well below a single-cell threshold, because the path sums over N): a lower per-frame threshold theta with
a higher birth cost, death staying at 6 dB, rise and hop flagging instead of cutting.
1. Noise: two hours of white noise, the package STFT, a 100 Hz band, M = 8, 10 min windows. For each
   theta, the smallest birth whose rate is at most 1 false track per hour per 100 Hz (run 1's target).
2. Weak pass: straight passes in white noise (f0 200 Hz, v 55 m/s, d 600 m; f0 120 Hz, v 65 m/s,
   d 1500 m; 70 s, tone throughout, scored over all but 5 s at each end as the Livermore span is),
   3 seeds each. The check amplitude is the lowest at which ridge() covers at least 95 % of every span
   at 2 %. At it, each (theta, birth) pair from step 1 is scored with freqtrack_livermore.score; the pair
   with the fewest fragments wins, then the highest coverage, then the highest theta.

usage: freqtrack_retune.py RUN"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freqtrack_livermore as FL                                         # noqa: E402

from dopplertrack import audio, doppler, freqtrack as ft                 # noqa: E402
from dopplertrack.tracks import local_whiten, ridge                      # noqa: E402

SR, N, HOP = FL.SR, FL.N, FL.HOP
# A first grid (theta 5, 6, 7; birth 6-80) was stopped: below about 8 dB no birth reached the target, since
# the best path through noise then gains on average and repays any birth (runs/.../retune_grid1_stopped.log).
THETAS = [7.5, 8.0, 8.5, 9.0, 9.5]
BIRTHS = [6.0, 12.0, 20.0, 30.0, 45.0, 65.0, 90.0, 130.0, 180.0]
TARGET, HOURS = 1.0, 2.0
PASSES = [(200.0, 55.0, 600.0), (120.0, 65.0, 1500.0)]
AMPS = [0.06, 0.04, 0.03, 0.02, 0.015, 0.01, 0.007, 0.005]
C = 340.0


def params(theta, birth):
    return ft.TrackParams(theta_db=theta, birth=birth, death=6.0)


def noise_rates():
    x = np.random.default_rng(0).standard_normal(int(HOURS * 3600 * SR)).astype(np.float32)
    sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, whiten_window_s=None)
    st = ft.SampleSTFT(x, SR, N, HOP)
    table, chosen = {}, {}
    for th in THETAS:
        for b in BIRTHS:
            n = sum(len(ft.track_window(sp, st, a, a + 600, 150, 250, params(th, b), flag=("rise", "hop")).tracks)
                    for a in np.arange(0, HOURS * 3600, 600.0))
            table[f"{th}/{b}"] = n / HOURS
            print(f"theta {th} birth {b}: {n / HOURS:.1f} per hour per 100 Hz", flush=True)
            if n / HOURS <= TARGET:
                chosen[th] = b
                break
    return table, chosen


def weak_pass(f0, v, d, amp, seed, dur=70.0):
    t = np.arange(0, dur, 1 / SR)
    fi = doppler.ideal_curve(t, f0, v, d, dur / 2 - d / C, c=C)
    fi = np.where(np.isfinite(fi), fi, np.nan_to_num(fi, nan=f0))
    x = amp * np.sin(2 * np.pi * np.cumsum(fi) / SR) + 0.4 * np.random.default_rng(seed).standard_normal(len(t))
    sp = audio.compute_spectrogram(x.astype(np.float32), SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900)
    fref = lambda tt: np.interp(tt, t, fi, left=np.nan, right=np.nan)
    span = (sp.t[0] + 5, sp.t[-1] - 5)
    fs = fref(np.arange(*span, HOP))
    band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
    return x, sp, fref, span, band


def main(run):
    table, chosen = noise_rates()
    print("pairs at the target:", chosen, flush=True)
    amp_ok = None
    for amp in AMPS:
        covs = []
        for f0, v, d in PASSES:
            for seed in range(3):
                x, sp, fref, span, band = weak_pass(f0, v, d, amp, seed)
                w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band))
                covs.append(FL.score([(w.t, ridge(w))], span, fref, sp.df, 0.02)["coverage"])
        print(f"amplitude {amp}: ridge() coverage min {min(covs):.2f}", flush=True)
        if min(covs) >= 0.95:
            amp_ok = amp
        else:
            break
    scores = {}
    for th, b in chosen.items():
        tot = dict(fragments=0, coverage=[], error=[], bridges=0)
        for f0, v, d in PASSES:
            for seed in range(3):
                x, sp, fref, span, band = weak_pass(f0, v, d, amp_ok, seed)
                ev = ft.track_window(sp, ft.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], *band, params(th, b), flag=("rise", "hop"))
                m = FL.score([(tr.t, tr.f) for tr in ev.tracks], span, fref, sp.df, 0.02)
                tot["fragments"] += m["fragments"]; tot["bridges"] += m["bridges"]
                tot["coverage"].append(m["coverage"]); tot["error"].append(m["error"])
        scores[f"{th}/{b}"] = dict(fragments=tot["fragments"], bridges=tot["bridges"],
                                   coverage=float(np.median(tot["coverage"])), error=float(np.median(tot["error"])))
        print(f"theta {th} birth {b}: {scores[f'{th}/{b}']}", flush=True)
    best = min(chosen.items(), key=lambda kv: (scores[f"{kv[0]}/{kv[1]}"]["fragments"],
                                               -scores[f"{kv[0]}/{kv[1]}"]["coverage"], -kv[0]))
    print("chosen theta, birth:", best)
    (run / "freqtrack_retune.json").write_text(json.dumps(dict(noise_rates=table, pairs=chosen, check_amplitude=amp_ok,
                                                               weak_pass=scores, chosen=best), indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
