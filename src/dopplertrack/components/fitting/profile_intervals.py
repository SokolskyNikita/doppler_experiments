"""Pointwise profile-likelihood intervals (Raue 2009, eqs. 8 and 10): for one optimum of an event's fit, the
interval of v, k = v^2/d, tau and f0 over which the objective, re-optimised over the other parameters, stays
within a threshold Delta; and the box they make. The threshold is heuristic and neither objective is a calibrated
likelihood (ours), so these are not confidence intervals."""
# old module: dopplertrack.components.fitting.profile_hypotheses
from __future__ import annotations


import numpy as np
from scipy.optimize import minimize

from dopplertrack.components.fitting.hypothesis import Hypothesis, K_BOUNDS, TAU_REACH_S, V_BOUNDS


_FREE = {"v": (0, 2, 3), "k": (0, 1, 3), "tau": (0, 1, 2), "f0": (1, 2, 3)}


def _theta(which: str, value: float, x: np.ndarray, base: np.ndarray) -> np.ndarray:
    th = base.copy()
    free = _FREE[which]
    for i, xi in zip(free, x):
        th[i] = np.exp(xi) if i in (1, 2) else xi
    if which == "v":
        th[1] = value
    elif which == "k":
        th[2] = th[1] ** 2 / value
    elif which == "tau":
        th[3] = value
    else:
        th[0] = value
    return th


def _x0(which: str, theta: np.ndarray) -> np.ndarray:
    return np.array([np.log(theta[i]) if i in (1, 2) else theta[i] for i in _FREE[which]])


def _profile_value(obj, which, value, theta_opt, x_start):
    r = minimize(lambda x: obj(_theta(which, value, x, theta_opt)), x_start, method="Nelder-Mead",
                 options={"maxiter": 80, "xatol": 1e-3, "fatol": 1e-9})
    return float(r.fun), r.x


# old name: profile_range
def profile_interval(obj, theta_opt: np.ndarray, which: str, threshold: float, bounds: tuple,
                     tau_reach_s: float = TAU_REACH_S) -> tuple[float, float, bool]:
    """(lo, hi, weak): the profile interval of one parameter (v, k, tau or f0), over which obj, re-optimised over
    the others (Raue 2009, eq. 10), stays within threshold of its value at theta_opt. A side that reaches its bound
    first is practically non-identifiable (Raue 2009, Def. 1), flagged weak, and set to the bound. A tau profile
    steps out at most tau_reach_s."""
    f_opt = obj(theta_opt)
    p0 = {"v": theta_opt[1], "k": theta_opt[1] ** 2 / theta_opt[2], "tau": theta_opt[3], "f0": theta_opt[0]}[which]
    additive = which == "tau"
    steps = [1, 2, 4, 8, 16, 32, tau_reach_s] if additive else [1.02, 1.05, 1.1, 1.2, 1.35, 1.6, 2.0, 3.0, 5.0]
    ends, weak = [], False
    for sign in (-1, 1):
        x = _x0(which, theta_opt)
        inside, outside = p0, None
        for st in steps:
            val = p0 + sign * st if additive else p0 * st ** sign
            if not (bounds[0] <= val <= bounds[1]):
                break
            f, x = _profile_value(obj, which, val, theta_opt, x)
            if f - f_opt > threshold:
                outside = val
                break
            inside = val
        if outside is None:
            ends.append(bounds[0] if sign < 0 else bounds[1])
            weak = True
            continue
        for _ in range(3):                          # bisect between the last inside and the first outside
            mid = 0.5 * (inside + outside) if additive else float(np.sqrt(inside * outside))
            f, _ = _profile_value(obj, which, mid, theta_opt, x)
            if f - f_opt > threshold:
                outside = mid
            else:
                inside = mid
        ends.append(inside)
    return min(ends), max(ends), weak


# old name: hypothesis_region
def profile_box(obj, theta, threshold, tau_bounds, f0_bounds, sources, corr=None, identified=None, c=343.0,
                v_bounds: tuple = V_BOUNDS, k_bounds: tuple = K_BOUNDS, tau_reach_s: float = TAU_REACH_S):
    """The Hypothesis at theta: the box of its pointwise profile intervals in v, k, tau and f0 (Raue 2009, df = 1),
    not a joint likelihood-based region (Raue 2009, eq. 8). v and k are bounded by v_bounds and k_bounds."""
    f0, v, d, tau = theta
    ranges, weak = {}, []
    for which, bounds in (("v", tuple(v_bounds)), ("k", tuple(k_bounds)), ("tau", tau_bounds), ("f0", f0_bounds)):
        lo, hi, wk = profile_interval(obj, np.asarray(theta, float), which, threshold, bounds, tau_reach_s)
        ranges[which] = (lo, hi)
        if wk:
            weak.append(which)
    return Hypothesis(sources=list(sources), f0=float(f0), v=float(v), d=float(d), t_cpa_emit=float(tau),
                      t_cpa=float(tau + d / c), v_range=ranges["v"], k_range=ranges["k"], tau_range=ranges["tau"],
                      f0_range=ranges["f0"], weak=weak, corr_v_d=corr, identified=identified)
