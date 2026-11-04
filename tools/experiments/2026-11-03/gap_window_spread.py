"""The uncut fit's own spread: the synthetic pass of tests/test_gaps.py, 8 noise seeds, each fitted
with its window moved by -10, -5, 0, 5 and 10 s."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import numpy as np
from dopplertrack.parallel import default_jobs
from concurrent.futures import ProcessPoolExecutor
import test_gaps as G
from dopplertrack import tracks
SH = [-10, -5, 0, 5, 10]
def job(a):
    seed, sh = a
    sp = G._spec([(G._pass_audio(seed), True)])
    e = tracks.fit_event(sp, G.T_CPA - 45 + sh, G.T_CPA + 45 + sh, 90, 135, c=G.C)
    return seed, sh, e.v, e.d, e.t_cpa, e.f0
if __name__ == '__main__':
    with ProcessPoolExecutor(default_jobs()) as ex: R = list(ex.map(job, [(s, h) for s in range(8) for h in SH]))
    R = np.array(R)
    for j, k in ((2, 'v'), (3, 'd'), (4, 't_cpa'), (5, 'f0')):
        per_seed = [R[R[:, 0] == s, j] for s in range(8)]
        print(k, 'within-seed spread over window shifts: mean sd %.3f, max range %.3f' % (np.mean([np.std(p, ddof=1) for p in per_seed]), max(np.ptp(p) for p in per_seed)),
              '| over seeds at shift 0: sd %.3f' % np.std(R[R[:, 1] == 0, j], ddof=1))
