"""Does the pre-f890572 fit objective, ported onto the current helpers with the grid-search
comparison quirk fixed (it compared a harmonic sum against a stored mean), reproduce the
committed Oyster Bay fits on this spectrogram?"""
import json
import sys

import numpy as np
from scipy.optimize import minimize

from dopplertrack.audio import Spectrogram
from dopplertrack.doppler import ideal_curve, speed_of_sound
from dopplertrack.tracks import _shape, local_whiten


def grid_brightness(sp, t_start, t_end, f_lo, f_hi, c, harmonics=1):
    v_grid = np.arange(30, 170, 10.0); d_grid = np.geomspace(300, 9000, 14)
    f0s = np.arange(f_lo * 1.15, f_hi * 0.85, 1.0); t0s = np.arange(t_start, t_end, 1.0)
    tq = np.linspace(t_start, t_end, 120)
    best = (-np.inf, None)
    for v in v_grid:
        for d in d_grid:
            dto, ratio = _shape(v, d, c)
            rat = np.interp(tq[None, :] - t0s[:, None], dto, ratio, left=np.nan, right=np.nan)
            total = np.zeros((len(t0s), len(f0s)))
            for h in range(1, harmonics + 1):
                F = h * f0s[None, None, :] * rat[:, :, None]
                vals = sp.sample(np.broadcast_to(tq[None, :, None], F.shape).ravel(), F.ravel()).reshape(F.shape)
                total += np.nanmean(vals, axis=1)
            total /= harmonics
            i, j = np.unravel_index(np.argmax(total), total.shape)
            if total[i, j] > best[0]:
                best = (float(total[i, j]), (float(f0s[j]), float(v), float(d), float(t0s[i])))
    return best


def fit_brightness(sp, t_start, t_end, f_lo, f_hi, harmonics=1):
    c = speed_of_sound()
    pad = 0.3 * (f_hi - f_lo)
    win = local_whiten(sp.crop(t_start - 30, t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1])))
    _, (f0, v, d, t0) = grid_brightness(win, t_start, t_end, f_lo, f_hi, c, harmonics)
    tt = np.linspace(t_start, t_end, 400)

    def neg(p):
        f0_, v_, d_, t0_ = p
        if not (10 < v_ < 300 and 100 < d_ < 30000):
            return 1e3
        return -sum(float(np.nanmean(win.sample(tt, ideal_curve(tt, h * f0_, v_, d_, t0_, c=c)))) for h in range(1, harmonics + 1)) / harmonics

    r = minimize(neg, [f0, v, d, t0], method="Nelder-Mead",
                 options={"xatol": 1e-2, "fatol": 1e-4, "maxiter": 4000,
                          "initial_simplex": np.array([[f0, v, d, t0], [f0 + 2, v, d, t0], [f0, v + 10, d, t0],
                                                       [f0, v, d * 1.3, t0], [f0, v, d, t0 + 2]])})
    f0, v, d, t0 = r.x
    return {"t_cpa": t0 + d / c, "f0": f0, "v": v, "d": d}


data = sys.argv[1]
sp = Spectrogram.load(f"{data}/rec.npz")
for name, args in (("ev1", (2090, 2200, 95, 200, 2)), ("ev2", (3020, 3130, 95, 195, 1))):
    got = fit_brightness(sp, *args)
    ref = json.load(open(f"{data}/{name}_docs.json"))
    print(name, "  ".join(f"{k} {got[k]:.3f} (committed {ref[k]:.3f})" for k in ("t_cpa", "f0", "v", "d")))
