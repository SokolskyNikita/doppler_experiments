"""A prototype of the other gap semantics, not adopted: the Nelder-Mead stage of fit_event with the
contrast mean taken over valid samples only (renormalised), and the score then multiplied by the
share of sweep weight on valid samples. Needs the mask to reach the fit window (tracks.local_whiten
keeping it). Same seeds and phases as tests/test_gaps.py."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from scipy.optimize import minimize
import test_gaps as G
from dopplertrack import tracks
from dopplertrack.doppler import ideal_curve

def fit_renorm(sp, t_start, t_end, f_lo, f_hi, c):
    pad = 0.3 * (f_hi - f_lo)
    win = tracks.local_whiten(sp.crop(t_start - 30, t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi + pad, sp.f[-1])))
    _, (f0, v, d, t0) = tracks.grid_search(win, t_start, t_end, f_lo, f_hi, c)
    tt = np.linspace(t_start, t_end, 400)
    ti = (tt - win.t[0]) / win.dt
    i0 = np.clip(np.floor(ti).astype(int), 0, len(win.t) - 1); i1 = np.minimum(i0 + 1, len(win.t) - 1)
    ok = win.valid[i0] & (win.valid[i1] | (ti == i0))
    def parts(p):
        f0_, v_, d_, t0_ = p
        base = ideal_curve(tt, f0_, v_, d_, t0_, c=c)
        w = tracks.sweep_weights(base / f0_, tt)
        cc = tracks.curve_contrast(win, tt, base)
        return w, cc
    def neg(p):
        f0_, v_, d_, t0_ = p
        if not (10 < v_ < 300 and 100 < d_ < 30000): return 1e3
        w, cc = parts(p)
        return -float(np.sum(w[ok] * cc[ok]) / max(np.sum(w[ok]), 1e-12))
    best = minimize(neg, [f0, v, d, t0], method="Nelder-Mead", options={"xatol": 1e-2, "fatol": 1e-4, "maxiter": 4000,
        "initial_simplex": np.array([[f0, v, d, t0], [f0 + 2, v, d, t0], [f0, v + 10, d, t0], [f0, v, d * 1.3, t0], [f0, v, d, t0 + 2]])})
    w, _ = parts(best.x)
    cover = float(np.sum(w[ok]) / np.sum(w))
    f0, v, d, t0 = best.x
    return dict(f0=f0, v=v, d=d, t_cpa=t0 + d / c, score=-best.fun * cover, renorm=-best.fun, cover=cover)

def run(seed):
    x = G._pass_audio(seed)
    f = lambda sp: fit_renorm(sp, G.T_CPA - 45, G.T_CPA + 45, 90, 135, G.C)
    u = f(G._spec([(x, True)]))
    g = f(G._spec(G._gapped(x, G.T_CPA + 12 + 31 * seed / 5)))
    s = f(G._spec(G._gapped(x, G.T_CPA - G.GAP_S / 2)))
    return u, g, s
if __name__ == '__main__':
    with ProcessPoolExecutor(6) as ex: R = list(ex.map(run, range(6)))
    for k in ('f0', 'v', 'd', 't_cpa'):
        u = np.array([r[0][k] for r in R]); g = np.array([r[1][k] for r in R]) - u; s = np.array([r[2][k] for r in R]) - u
        print(f'{k:5s} sd {u.std(ddof=1):.3f} cut shift mean {g.mean():+.3f} max {abs(g).max():.3f} | steep shift mean {s.mean():+.3f} max {abs(s).max():.3f}')
    for r in R: print('score u %.2f cut %.2f (renorm %.2f cover %.2f) steep %.2f (renorm %.2f cover %.2f)' % (r[0]['score'], r[1]['score'], r[1]['renorm'], r[1]['cover'], r[2]['score'], r[2]['renorm'], r[2]['cover']))
