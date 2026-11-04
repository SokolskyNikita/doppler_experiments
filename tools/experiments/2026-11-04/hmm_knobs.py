"""Knobs of dopplertrack.hmmtrack (item 3 round 2), on synthetic cases only, before any real recording is
tracked: the (theta_cont, theta_birth) pairs, then the pick.

1. Noise: two hours of white noise, the package STFT (4 kHz, 2.048 s Hann, 0.25 s hop), WHITEN whitening
   (time or frequency, task 1's outcome), a 150-250 Hz fundamental band, 3 harmonics, two families, birth
   and death 6, n_born 4, 10 min windows. For each theta_cont on a grid, the smallest theta_birth (by
   bisection to 0.25 dB on 6-18 dB) giving at most 1 false track per hour per 100 Hz, round 1's rate.
2. Pick: on round 1's synthetic weak pass (two straight passes, 3 seeds each, amplitude 0.03 in 0.4 noise,
   the lowest at which ridge() covers 95 % of every span; freqtrack_retune.py), the pair with the fewest
   fragments, then the most coverage, then the highest theta_cont, scored as in freqtrack_livermore.py.

usage: hmm_knobs.py RUN time|frequency"""
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

from dopplertrack import audio, freqtrack as ft, hmmtrack as hm          # noqa: E402

SR, N, HOP = 4000, 8192, 0.25
HOURS, TARGET = 2.0, 1.0
THETA_CONT = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
_NOISE = {}


def _init(whiten):
    x = np.random.default_rng(0).standard_normal(int(HOURS * 3600 * SR)).astype(np.float32)
    _NOISE["sp"] = audio.compute_spectrogram(x, SR, fmax=1000.0, whiten_window_s=None, whiten=whiten)
    _NOISE["st"] = ft.SampleSTFT(x, SR, N, HOP)


def _window(job):
    a, tc, tb = job
    p = hm.with_params(hm.HMMParams(), theta_cont=tc, theta_birth=tb)
    return len(hm.hmm_track(_NOISE["sp"], _NOISE["st"], a, a + 600, 150.0, 250.0, p).tracks)


def rate(ex, tc, tb):
    jobs = [(a, tc, tb) for a in np.arange(0, HOURS * 3600, 600.0)]
    return sum(ex.map(_window, jobs)) / HOURS


def pairs(whiten):
    out, table = {}, {}
    with ProcessPoolExecutor(int(os.environ.get("JOBS", "2")), initializer=_init, initargs=(whiten,)) as ex:
        for tc in THETA_CONT:
            lo, hi = max(tc, 6.0), 18.0
            if rate(ex, tc, hi) > TARGET:
                print(f"theta_cont {tc}: even theta_birth {hi} exceeds the target", flush=True)
                table[tc] = None; continue
            while hi - lo > 0.25:
                mid = 0.5 * (lo + hi)
                r = rate(ex, tc, mid); table[f"{tc}/{mid}"] = r
                print(f"theta_cont {tc} theta_birth {mid:.2f}: {r:.1f} per hour per 100 Hz", flush=True)
                if r <= TARGET:
                    hi = mid
                else:
                    lo = mid
            out[tc] = hi
            print(f"theta_cont {tc}: theta_birth {hi:.2f}", flush=True)
    return out, table


def pick(chosen, whiten):
    scores = {}
    for tc, tb in chosen.items():
        p = hm.with_params(hm.HMMParams(), theta_cont=tc, theta_birth=tb)
        tot = dict(fragments=0, bridges=0, coverage=[], error=[])
        for f0, v, d in FR.PASSES:
            for seed in range(3):
                x, sp, fref, span, band = FR.weak_pass(f0, v, d, 0.03, seed)
                if whiten != "time":
                    sp = audio.compute_spectrogram(x.astype(np.float32), SR, fmin=40, fmax=1900, whiten=whiten)
                ev = hm.hmm_track(sp, ft.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], *band, p)
                m = FL.score([(tr.t, tr.f) for tr in ev.tracks], span, fref, sp.df, 0.02)
                tot["fragments"] += m["fragments"]; tot["bridges"] += m["bridges"]
                tot["coverage"].append(m["coverage"]); tot["error"].append(m["error"])
        scores[tc] = dict(theta_birth=tb, fragments=tot["fragments"], bridges=tot["bridges"],
                          coverage=float(np.median(tot["coverage"])), error=float(np.median(tot["error"])))
        print(f"theta_cont {tc}, theta_birth {tb}: {scores[tc]}", flush=True)
    best = min(scores, key=lambda tc: (scores[tc]["fragments"], -scores[tc]["coverage"], -tc))
    return scores, (best, scores[best]["theta_birth"])


if __name__ == "__main__":
    run, whiten = Path(sys.argv[1]), sys.argv[2]
    chosen, table = pairs(whiten)
    scores, best = pick(chosen, whiten)
    print("chosen theta_cont, theta_birth:", best)
    (run / f"hmm_knobs_{whiten}.json").write_text(json.dumps(dict(pairs=chosen, rates=table, weak_pass=scores,
                                                                   chosen=best), indent=1, default=str))
