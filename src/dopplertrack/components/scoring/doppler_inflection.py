"""Doppler inflection point: when a Doppler curve falls fastest near a given time, which for a pass lies near the
point of closest approach (USNA 1962, Space Navigation Handbook, scan page 58: "inflection point (point of closest
approach)", where d(f)/dt is a maximum)."""
# old module: dopplertrack.components.scoring.steepest_fall
from __future__ import annotations

import numpy as np

# old name: SF_FLAT_RATIO
INFLECTION_FLAT_RATIO = 1.03   # the ideal curve at 9 km and 40 m/s peaks at 1.027 times its median slope over ±60 s


# old name: steepest_fall
def doppler_inflection(t, ratio, center: float, window_s: float = 60.0, smooth_s: float = 3.0,
                  flat_ratio: float = INFLECTION_FLAT_RATIO) -> float | None:
    """When a Doppler curve (times t, frequency ratio) falls fastest within ±window_s of center, or None
    if that can't be placed.

    The curve is resampled to 1 s, averaged over ±smooth_s, differentiated, and the most negative slope
    refined by a parabola through its neighbours. Fitted and modelled curves go through this same
    function, so the two are compared like for like. None when fewer than half the window's slopes are
    finite (holes or the ends of a track), when the inflection is at the edge of what is finite (it
    lies outside the window), or when the curve is too flat to place: its peak slope is under flat_ratio
    times its median slope over the window, or the median isn't a fall."""
    k = max(0, int(round(smooth_s)))
    tq = center + np.arange(-window_s - k, window_s + k + 1, 1.0)
    t = np.asarray(t, float); ratio = np.asarray(ratio, float)
    ok = np.isfinite(t)
    if np.count_nonzero(ok) < 2:
        return None
    r = np.interp(tq, t[ok], ratio[ok], left=np.nan, right=np.nan)   # invalid samples stay NaN
    if k:
        r = np.convolve(r, np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
        tq = tq[k:-k]
    g = -np.gradient(r, tq)
    fin = np.flatnonzero(np.isfinite(g))
    if len(fin) < len(g) / 2:
        return None
    i = int(fin[np.argmax(g[fin])])
    med = float(np.median(g[fin]))
    if i in (fin[0], fin[-1]) or med <= 0 or g[i] < flat_ratio * med:
        return None
    a, b, cc = g[i - 1], g[i], g[i + 1]
    den = a - 2 * b + cc
    return float(tq[i] + (0.5 * (a - cc) / den if np.isfinite(den) and den != 0 else 0.0))
