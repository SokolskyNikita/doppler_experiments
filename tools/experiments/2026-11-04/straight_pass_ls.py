"""Least-squares fit of the straight, constant-speed pass to a frequency track (Ferguson & Lo 2000 §I.C;
Ferguson & Quinn 1994 eq. 20; Ferguson 2016 eqs. 11-17), as an independent implementation beside
Phase 2 item 4's fit in tracks.py.

    f(t) = alpha + beta * z(t; tau, s),  z = (t - tau) / sqrt(s^2 + (t - tau)^2)

t is the time the sound is heard and tau the emission-time CPA. At each (tau, s), alpha and beta are the
weighted linear least-squares solution (variable projection), so the search is over (tau, log s) only.
Starts: Ferguson & Lo's eqs. 10-14 from the track itself, plus a 7 x 7 grid around them (tau +-15 s,
s x 0.3 to x 3); starts_mode="wide" (the default) adds tau across the whole track and 30 s beyond, every
2 s, against 25 values of s over its bounds, because on short or one-sided tracks the narrow starts end
in local minima. The best starts are refined with scipy.optimize.least_squares within the bounds that
v in [10, 300] m/s and R in [100, 30000] m imply for s.

Usage, from the repo root:
    import importlib.util
    spec = importlib.util.spec_from_file_location("ls", "tools/experiments/2026-11-04/straight_pass_ls.py")
    ls = importlib.util.module_from_spec(spec); spec.loader.exec_module(ls)
    fit = ls.fit(times, freqs, weights=None, c=340.3)
    fit["f0"], fit["v"], fit["R"], fit["tau"], fit["t_heard"]
"""
import numpy as np
import scipy.optimize as so

V_BOUNDS = (10.0, 300.0)
R_BOUNDS = (100.0, 30000.0)


def z(t, tau, s):
    u = t - tau
    return u / np.sqrt(s * s + u * u)


def model(t, f0, v, R, tau, c):
    """The straight-pass curve in physical parameters (Ferguson & Lo eqs. 1a-1e)."""
    alpha = f0 * c * c / (c * c - v * v)
    beta = -f0 * c * v / (c * c - v * v)
    s = R * np.sqrt(c * c - v * v) / (v * c)
    return alpha + beta * z(t, tau, s)


def _ab(t, f, w, tau, s):
    """Weighted linear LS for alpha, beta at fixed (tau, s); returns (alpha, beta, weighted residuals)."""
    x = z(t, tau, s)
    sw = np.sqrt(w)
    A = np.stack([sw, sw * x], axis=1)
    coef, *_ = np.linalg.lstsq(A, sw * f, rcond=None)
    return coef[0], coef[1], sw * f - A @ coef


def _grid_cost(t, f, w, cands):
    """Weighted residual sum of squares after the closed-form alpha, beta, for every (tau, s) row at once."""
    u = t[None, :] - cands[:, :1]
    x = u / np.sqrt(cands[:, 1:2] ** 2 + u * u)
    W = w.sum()
    mx, mf = (x * w).sum(1) / W, (w * f).sum() / W
    sxx = (w * (x - mx[:, None]) ** 2).sum(1)
    sxf = (w * (x - mx[:, None]) * (f - mf)).sum(1)
    sff = (w * (f - mf) ** 2).sum()
    return sff - sxf ** 2 / np.maximum(sxx, 1e-300)


def physical(alpha, beta, s, tau, c):
    v = -beta / alpha * c                      # eq. 7
    f0 = alpha * (1 - v * v / (c * c))         # eq. 8
    R = s * v * c / np.sqrt(c * c - v * v)     # eq. 9
    return f0, v, R


def starts(t, f, c):
    """Ferguson & Lo eqs. 10-14, from the track's ends and the slope at its midpoint frequency."""
    k = max(3, len(t) // 20)
    f1, fK = np.median(f[:k]), np.median(f[-k:])
    k0 = int(np.argmin(np.abs(f - 0.5 * (f1 + fK))))
    k0 = min(max(k0, 1), len(t) - 2)
    lo, hi = max(0, k0 - k), min(len(t) - 1, k0 + k)
    g = abs((f[hi] - f[lo]) / (t[hi] - t[lo])) if t[hi] > t[lo] else np.nan
    v = c * (f1 - fK) / (f1 + fK)
    f0 = 2 * f1 * fK / (f1 + fK)
    if not (np.isfinite(g) and g > 0 and V_BOUNDS[0] <= v <= V_BOUNDS[1]):
        v = min(max(v if np.isfinite(v) else 60.0, V_BOUNDS[0]), V_BOUNDS[1])
        g = max(g if np.isfinite(g) else 1.0, 1e-3)
    R = f0 * (c * v) ** 2 / ((c * c - v * v) ** 1.5 * g)    # eq. 14
    R = min(max(R, R_BOUNDS[0]), R_BOUNDS[1])
    s = R * np.sqrt(c * c - v * v) / (v * c)                  # eq. 1d
    return t[k0], s


def fit(times, freqs, weights=None, c=340.3, starts_mode="wide", tau_span=15.0, n_grid=7):
    """Fit the straight pass. Returns f0, v, R, tau (emission CPA), t_heard (= tau + R/c), alpha, beta, s,
    rms (unweighted residual RMS, Hz), cond (condition number of the 2-parameter Jacobian at the optimum),
    at_bound (the optimum lies on an s bound) and in_bounds (v and R inside V_BOUNDS and R_BOUNDS)."""
    t = np.asarray(times, float); f = np.asarray(freqs, float)
    w = np.ones_like(t) if weights is None else np.asarray(weights, float)
    ok = np.isfinite(t) & np.isfinite(f) & (w > 0)
    t, f, w = t[ok], f[ok], w[ok]
    t_ref = float(t[0])     # optimise in time relative to the track: absolute (unix) times wreck the
    t = t - t_ref           # finite-difference steps and step tolerance, which scale with |x|
    s_lo = R_BOUNDS[0] * np.sqrt(c * c - V_BOUNDS[1] ** 2) / (V_BOUNDS[1] * c)
    s_hi = R_BOUNDS[1] * np.sqrt(c * c - V_BOUNDS[0] ** 2) / (V_BOUNDS[0] * c)
    tau0, s0 = starts(t, f, c)
    cands = [(tau0, s0)] + [(tau0 + dt, s0 * m) for dt in np.linspace(-tau_span, tau_span, n_grid)
                            for m in np.geomspace(0.3, 3.0, n_grid)]
    if starts_mode == "wide":   # tau across the whole track and 30 s beyond, every 2 s; s over its bounds
        cands += [(a, b) for a in np.arange(t[0] - 30.0, t[-1] + 30.0, 2.0) for b in np.geomspace(s_lo, s_hi, 25)]
    cands = [(a, min(max(b, s_lo * 1.0001), s_hi * 0.9999)) for a, b in cands]
    cost = _grid_cost(t, f, w, np.array(cands))
    best = None
    for i in np.argsort(cost)[:10 if starts_mode == "wide" else 3]:
        a, b = cands[i]
        r = so.least_squares(lambda x: _ab(t, f, w, x[0], np.exp(x[1]))[2], [a, np.log(b)],
                             bounds=([t[0] - 300, np.log(s_lo)], [t[-1] + 300, np.log(s_hi)]), x_scale=[1.0, 0.1],
                             xtol=1e-12, ftol=1e-12, gtol=1e-12)
        if best is None or r.cost < best.cost:
            best = r
    tau, s = best.x[0], float(np.exp(best.x[1]))
    alpha, beta, _ = _ab(t, f, w, tau, s)
    f0, v, R = physical(alpha, beta, s, tau, c)
    res = f - (alpha + beta * z(t, tau, s))
    sv = np.linalg.svd(best.jac, compute_uv=False)
    tau += t_ref
    return dict(f0=float(f0), v=float(v), R=float(R), tau=float(tau), t_heard=float(tau + R / c),
                alpha=float(alpha), beta=float(beta), s=s, rms=float(np.sqrt(np.mean(res ** 2))),
                cond=float(sv[0] / max(sv[-1], 1e-300)),
                at_bound=bool(np.isclose(s, s_lo, rtol=1e-3) or np.isclose(s, s_hi, rtol=1e-3)),
                in_bounds=bool(V_BOUNDS[0] <= v <= V_BOUNDS[1] and R_BOUNDS[0] <= R <= R_BOUNDS[1]), n=int(len(t)))


def covariances(t, f, fitd, c, lags=8):
    """Classical sigma^2 (J'J)^-1 and a Newey-West sandwich (Bartlett weights over `lags` samples) for
    (f0, v, R, tau), from the Jacobian of the physical-parameter model at the fit. Returns two 4x4 arrays."""
    t = np.asarray(t, float); f = np.asarray(f, float)
    p = np.array([fitd["f0"], fitd["v"], fitd["R"], fitd["tau"]])
    m = model(t, *p, c)
    r = f - m
    h = np.array([1e-4 * p[0], 1e-3 * p[1], 1e-3 * p[2], 1e-2])
    J = np.stack([(model(t, *(p + h[k] * np.eye(4)[k]), c) - model(t, *(p - h[k] * np.eye(4)[k]), c)) / (2 * h[k])
                  for k in range(4)], axis=1)
    A = J.T @ J
    Ai = np.linalg.pinv(A)
    n = len(t)
    classical = Ai * float(r @ r) / max(n - 4, 1)
    g = J * r[:, None]
    S = g.T @ g
    for L in range(1, lags + 1):
        wL = 1 - L / (lags + 1)
        G = g[L:].T @ g[:-L]
        S += wL * (G + G.T)
    return classical, Ai @ S @ Ai
