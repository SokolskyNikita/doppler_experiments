"""The synthetic pass of tests/test_gaps.py, 8 noise seeds, with AudioMoth's 5 s/min gap at 20
phases (the gap starting every 3 s from CPA-30 to CPA+27 s): how far each gapped fit moves from the
uncut one, how often it lands off the optimum (|dv| > 0.5 m/s) and what it does to the score."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import test_gaps as G
PH = list(range(-30, 30, 3))
def job(a):
    seed, ph = a
    x = G._pass_audio(seed)
    e = G._fit(G._spec([(x, True)]) if ph is None else G._spec(G._gapped(x, G.T_CPA + ph)))
    return seed, ph, e.f0, e.v, e.d, e.t_cpa, e.score
if __name__ == '__main__':
    jobs = [(s, None) for s in range(8)] + [(s, p) for s in range(8) for p in PH]
    with ProcessPoolExecutor(10) as ex: R = list(ex.map(job, jobs))
    U = {r[0]: r for r in R if r[1] is None}
    print('uncut v', [round(U[s][3], 2) for s in range(8)], 'd', [round(U[s][4]) for s in range(8)])
    for p in PH:
        rows = [r for r in R if r[1] == p]
        dv = [r[3] - U[r[0]][3] for r in rows]; dd = [r[4] - U[r[0]][4] for r in rows]; dt = [r[5] - U[r[0]][5] for r in rows]
        bad = sum(abs(a) > 0.5 for a in dv)
        print(f'gap starts CPA{p:+3d}s: max|dv| {max(map(abs,dv)):.2f} max|dd| {max(map(abs,dd)):5.1f} max|dt| {max(map(abs,dt)):.2f} off-optimum {bad}/8  score ratio {np.mean([r[6]/U[r[0]][6] for r in rows]):.2f}')
