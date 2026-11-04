"""Knobs of dopplertrack.hmmtrack (item 3 round 2), on synthetic cases only, before any real recording is
tracked: the (theta_cont, theta_birth) pairs, then the pick.

1. Noise: two hours of white noise, the package STFT (4 kHz, 2.048 s Hann, 0.25 s hop), WHITEN whitening
   (time or frequency, task 1's outcome), a 150-250 Hz fundamental band, 3 harmonics, two families, birth
   and death 6, n_born 4, 10 min windows. For each theta_cont on a grid, the smallest theta_birth (by
   bisection to 0.25 dB on 6-18 dB) giving at most 1 false track per hour per 100 Hz, round 1's rate.
2. Pick: on round 1's synthetic weak pass (two straight passes, 3 seeds each, amplitude 0.03 in 0.4 noise,
   the lowest at which ridge() covers 95 % of every span; freqtrack_retune.py), the pair with the fewest
   fragments, then the most coverage, then the highest theta_cont, scored as in freqtrack_livermore.py.

Units: one per theta_cont (pairs), each written to RUN/hmm_knobs/<whiten>/pair_<theta_cont>.json when its
bisection ends and skipped if present; `pick` reads every pair file. Workers (noise windows): DOPPLERTRACK_JOBS.

usage: hmm_knobs.py RUN pairs time|frequency [THETA_CONT ...]
       hmm_knobs.py RUN pick time|frequency"""
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
import units as U                                                       # noqa: E402

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


def pairs(run, whiten, chosen):
    root = run / "hmm_knobs" / whiten
    todo = [tc for tc in THETA_CONT if (not chosen or tc in chosen) and not U.done(U.path(root, f"pair_{tc:g}"))]
    if not todo:
        return
    with ProcessPoolExecutor(U.jobs(), initializer=_init, initargs=(whiten,)) as ex:
        for tc in todo:
            lo, hi, table = max(tc, 6.0), 18.0, {}
            r = rate(ex, tc, hi); table[f"{hi:g}"] = r
            if r > TARGET:
                print(f"theta_cont {tc}: even theta_birth {hi} exceeds the target", flush=True)
                U.write(U.path(root, f"pair_{tc:g}"), dict(theta_cont=tc, theta_birth=None, rates=table)); continue
            while hi - lo > 0.25:
                mid = 0.5 * (lo + hi)
                r = rate(ex, tc, mid); table[f"{mid:g}"] = r
                print(f"theta_cont {tc} theta_birth {mid:.2f}: {r:.1f} per hour per 100 Hz", flush=True)
                if r <= TARGET:
                    hi = mid
                else:
                    lo = mid
            U.write(U.path(root, f"pair_{tc:g}"), dict(theta_cont=tc, theta_birth=hi, rates=table))
            print(f"theta_cont {tc}: theta_birth {hi:.2f}", flush=True)


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
    run, step, whiten = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if step == "pairs":
        pairs(run, whiten, [float(x) for x in sys.argv[4:]])
    elif step == "pick":
        found = U.read_all(run / "hmm_knobs" / whiten, "pair_*.json")
        chosen = {d["theta_cont"]: d["theta_birth"] for d in found if d["theta_birth"] is not None}
        scores, best = pick(chosen, whiten)
        print("chosen theta_cont, theta_birth:", best)
        U.write(run / "hmm_knobs" / whiten / "chosen.json", dict(pairs=chosen, rates={d["theta_cont"]: d["rates"] for d in found},
                                                                  weak_pass=scores, chosen=best))
    else:
        sys.exit(__doc__)
