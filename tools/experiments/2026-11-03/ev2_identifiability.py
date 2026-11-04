"""Is event 2's geometry identifiable from its window? Compare objective values of the free
fits with the best ideal curve whose speed and distance are pinned to the ADS-B truth, under the
current (sweep-weighted ridge contrast) and the pre-f890572 (mean brightness) objectives."""
import sys

import numpy as np
from scipy.optimize import minimize

from dopplertrack.audio import Spectrogram
from dopplertrack.doppler import ideal_curve, speed_of_sound
from dopplertrack.tracks import curve_contrast, local_whiten, sweep_weights

data = sys.argv[1]
sp = Spectrogram.load(f"{data}/rec.npz")
c = speed_of_sound()
t_start, t_end, f_lo, f_hi = 3020.0, 3130.0, 95.0, 195.0
pad = 0.3 * (f_hi - f_lo)
win = local_whiten(sp.crop(t_start - 30, t_end + 30, max(f_lo - pad, sp.f[0]), min(f_hi + pad, sp.f[-1])))
tt = np.linspace(t_start, t_end, 400)


def new_obj(f0, v, d, t0):
    base = ideal_curve(tt, f0, v, d, t0, c=c)
    w = sweep_weights(base / f0, tt)
    return float(np.sum(w * curve_contrast(win, tt, base)) / np.sum(w))


def old_obj(f0, v, d, t0):
    return float(np.nanmean(win.sample(tt, ideal_curve(tt, f0, v, d, t0, c=c))))


V, D, T_HEARD = 103.5, 3638.0, 3078.4          # ADS-B truth at the known point, audio clock
fits = {"committed (old fitter)": (132.41, 141.20, 5920.4, 3056.54),
        "fresh (current fitter)": (137.97, 81.51, 1658.3, 3064.90),
        "truth geometry, f0 125.8": (125.8, V, D, T_HEARD - D / c)}
for name, obj in (("current objective", new_obj), ("old objective", old_obj)):
    print(name)
    for k, p in fits.items():
        print(f"  {k:28s} {obj(*p):6.2f}")
    r = minimize(lambda q: -obj(q[0], V, D, q[1]), [125.8, T_HEARD - D / c], method="Nelder-Mead",
                 options={"xatol": 1e-2, "fatol": 1e-4, "initial_simplex": [[125.8, 3067.7], [128.8, 3067.7], [125.8, 3070.7]]})
    print(f"  {'truth v, d; best f0, t0':28s} {-r.fun:6.2f}  (f0 {r.x[0]:.1f}, heard CPA {r.x[1] + D / c:.1f} s)")
