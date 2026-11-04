"""The fits behind tests/test_gaps.py's two fit tests, printed: per parameter the uncut mean and
spread, the shift with the gaps away from the steep part and with a gap centred on CPA, and the
score ratios."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import numpy as np
from dopplertrack.parallel import default_jobs
from concurrent.futures import ProcessPoolExecutor
import test_gaps as G
if __name__ == '__main__':
    with ProcessPoolExecutor(default_jobs()) as ex: R = list(ex.map(G._three_fits, G.SEEDS))
    for k in ('f0', 'v', 'd', 't_cpa'):
        u = np.array([getattr(r[0], k) for r in R]); g = np.array([getattr(r[1], k) for r in R]) - u; s = np.array([getattr(r[2], k) for r in R]) - u
        print(f'{k:5s} uncut mean {u.mean():.3f} sd {u.std(ddof=1):.3f} | cut shift mean {g.mean():+.3f} max {abs(g).max():.3f} {np.round(g,3)} | steep mean {s.mean():+.3f} max {abs(s).max():.3f}')
    for r in R: print('score u %.2f cut %.2f steep %.2f invalid %.3f  ratios %.3f %.3f' % (r[0].score, r[1].score, r[2].score, r[3], r[1].score/r[0].score, r[2].score/r[0].score))
