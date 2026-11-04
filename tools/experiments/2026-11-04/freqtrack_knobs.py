"""Knobs of dopplertrack.freqtrack, set on synthetic cases only (PLAN Phase 2 item 3), before any real
recording is tracked.

1. theta_db, the off-state threshold: white noise only, the package STFT (4 kHz, 2.048 s Hann, 0.25 s
   hop, global whitening, the window's own local_whiten), a 100 Hz band, birth = death = 6 dB,
   M = 8 peaks per frame, min_track_s = 1 s, two hours of noise. For each theta, the rate of tracks per audio hour after
   all segment rules. The chosen theta is the smallest giving at most TARGET tracks per hour per
   100 Hz. It holds for these settings only: the rate grows with the cells searched (band, M, hop).
2. The sub-bin estimator: RMS error of quadratic, Candan (Hann, iterated) and Quinn FTI(2) on tones
   and linear chirps at 0.5-20 Hz/s, at a given SNR, on the frame-centre instantaneous frequency.

usage: freqtrack_knobs.py RUN [theta|estimators|all]"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from dopplertrack import audio, freqtrack as ft

SR, NPERSEG, HOP = 4000, 8192, 0.25
TARGET = 1.0                              # false tracks per audio hour per 100 Hz of band
THETAS = [6, 7, 8, 9, 9.25, 9.5, 9.75, 10, 11, 12]
HOURS = 2.0


def noise(hours=1.0, seed=0):
    x = np.random.default_rng(seed).standard_normal(int(hours * 3600 * SR)).astype(np.float32)
    return audio.compute_spectrogram(x, SR, nperseg=NPERSEG, hop_s=HOP, whiten_window_s=None), ft.SampleSTFT(x, SR, NPERSEG, HOP)


def noise_rate(theta, sp, st, hours=1.0, band=(150.0, 250.0)):
    p = ft.with_params(ft.TrackParams(), theta_db=theta)
    n, t0 = 0, time.time()
    for a in np.arange(0, hours * 3600, 600.0):              # 10 min windows, as an event window would be
        ev = ft.track_window(sp, st, a, a + 600, *band, p)
        n += len(ev.tracks)
    return n / hours, time.time() - t0


def chirp(f0, g, dur, snr_db, seed):
    t = np.arange(0, dur, 1 / SR)
    f = f0 + g * (t - dur / 2)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR)
    sigma = np.sqrt(0.5 / 10 ** (snr_db / 10))              # SNR per sample
    return t, f, x + sigma * np.random.default_rng(seed).standard_normal(len(t))


def estimators(snr_db=-10.0):
    out = {}
    for g in (0.0, 0.5, 2.0, 5.0, 10.0, 20.0):
        errs = {e: [] for e in ("quadratic", "candan", "quinn2")}
        for seed in range(5):
            f0 = 200.0 + 0.37 * seed
            t, f, x = chirp(f0, g, 20.0, snr_db, seed)
            st = ft.SampleSTFT(x, SR, NPERSEG, HOP)
            for k in range(2, int((20.0 * SR - NPERSEG) / st.hop) - 2, 4):
                tc = (NPERSEG / 2 + k * st.hop) / SR
                fc = np.interp(tc, t, f)
                b = int(round(fc / st.df))
                for e in errs:
                    errs[e].append(ft.refine(st, k, b, e)[0] - fc)
        out[g] = {e: float(np.sqrt(np.mean(np.square(v)))) for e, v in errs.items()}
        print(f"chirp {g:5.1f} Hz/s:", {e: round(v, 4) for e, v in out[g].items()}, flush=True)
    return out


if __name__ == "__main__":
    run = Path(sys.argv[1]); what = sys.argv[2] if len(sys.argv) > 2 else "all"
    res = {}
    if what in ("estimators", "all"):
        res["estimators_rms_hz"] = {str(k): v for k, v in estimators().items()}
    if what in ("theta", "all"):
        rates = {}
        sp, st = noise(HOURS)
        for th in THETAS:
            r, s = noise_rate(th, sp, st, HOURS)
            rates[th] = r
            print(f"theta {th} dB: {r:.0f} tracks per hour per 100 Hz ({s:.1f} s)", flush=True)
        res["noise_tracks_per_hour_per_100hz"] = rates
        ok = [th for th in THETAS if rates[th] <= TARGET]
        res["theta_db"] = min(ok) if ok else None
        print("chosen theta", res["theta_db"])
    (run / f"freqtrack_knobs_{what}.json").write_text(json.dumps(res, indent=1))
