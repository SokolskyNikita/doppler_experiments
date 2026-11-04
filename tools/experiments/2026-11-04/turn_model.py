"""Phase 2 item 2 follow-up: the three-parameter turn model against stage 1's model error (design, expectation and
criterion in docs/experiments/2026-11-04-model-error.md, "The turn model", written before any run).

Forward model in emission time u, heard at t = tau + u + r/c, f = f0 / (1 + rdot/c), a constant-rate level turn:
  x = (v/w) sin(wu),  y = d + s (v/w)(1 - cos(wu)),  z = h,  d = R cos(phi),  h = R sin(phi)
so at u = 0 the aircraft is at its horizontal CPA, heading at right angles to the microphone; s = +1 turns away
from it, s = -1 toward it; w = 0 is the straight pass (phi then unidentified). f0 is solved in closed form;
least_squares searches (tau, v, log R, w, phi) on each branch of s, from the straight fit x w {0.5, 1.5, 3} deg/s
x phi {15, 45, 75} deg, and the lower-RSS branch is the fit. The compared R is the fitted path's minimum distance
over the heard span, like the trajectory reference R*. Signed rate sw = s*w (deg/s, + away).

Stages, each a set of units under RUN/units/<id>/ (tools/data/shards.py: finished when unit.json is there; --shard K/N,
--resume DIR..., --merge, --inputs; workers from $DOPPLERTRACK_JOBS, which never change a result):
  synth    synthetic arcs (f0 180 Hz, 65 m/s, 1.5 km; w 0, 1, 3 deg/s; phi 20, 60 deg; both signs): recovery,
           and what a straight fit misses on each
  fit      the 40 Livermore passes on curve A (the trajectory curve; the criterion) and D (the published ridge)
  profile  on A plus stage 1's first noise replicate: profiles of sw (-6..6 deg/s, 25 points) and phi (0..90 deg,
           10 points), Delta = (RSS - RSS_min)/(sigma^2 kappa) against 3.84 (Raue 2009); the six-parameter
           Cramer-Rao bound of R with the pass's ridge noise (phi held fixed where sw's interval includes 0) beside
           the straight model's
  boot     (pass, replicate): A plus a moving-block replicate of the sub-5 s residuals, seed from (pass, replicate);
           refit on both branches. The cloud job
  report   the criterion from a merged fit.csv (and profile.csv)

usage: uv run python tools/experiments/2026-11-04/turn_model.py STAGE [RUN] [--shard K/N] [--resume DIR ...] [--merge]
           [--inputs] [--replicates 200]
"""
import argparse
import csv
import hashlib
import sys
import importlib.util
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import scipy.optimize as so
import scipy.signal as ss

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("model_error", HERE / "model_error.py")
me = importlib.util.module_from_spec(spec); spec.loader.exec_module(me)
spec = importlib.util.spec_from_file_location("crb", HERE / "crb.py")
crb = importlib.util.module_from_spec(spec); spec.loader.exec_module(crb)
sys.path.insert(0, str(HERE.parents[1] / "data"))
import shards  # noqa: E402

ls = me.ls
C = me.C15
V_B, R_B, W_MAX, PHI_B = (10.0, 300.0), (100.0, 30000.0), np.radians(6.0), (0.0, np.radians(90.0))
W_STARTS, PHI_STARTS = np.radians([0.5, 1.5, 3.0]), np.radians([15.0, 45.0, 75.0])
STAGE1 = me.DATA / "runs/2026-11-04-model-error-2"
SW_GRID = np.radians(np.linspace(-6, 6, 25))
PHI_GRID = np.radians(np.linspace(0, 90, 10))


def path(u, v, R, w, phi, s):
    """Horizontal (x, y), height and their emission-time derivatives; smooth through w = 0."""
    d, h = R * np.cos(phi), R * np.sin(phi)
    wu = w * u
    x = v * u * np.sinc(wu / np.pi)                              # (v/w) sin(wu)
    y = d + s * v * (w * u * u / 2) * np.sinc(wu / (2 * np.pi)) ** 2   # d + s (v/w)(1 - cos wu)
    xd, yd = v * np.cos(wu), s * v * np.sin(wu)
    return x, y, h, xd, yd


def heard(tau, v, R, w, phi, s, span=400.0, n=8001):
    u = np.linspace(-span, span, n)
    x, y, h, xd, yd = path(u, v, R, w, phi, s)
    r = np.sqrt(x * x + y * y + h * h)
    rd = (x * xd + y * yd) / r
    th = tau + u + r / C
    g = 1.0 / (1.0 + rd / C)
    ok = np.r_[True, np.diff(th) > 0] & (C + rd > 0)
    return th[ok], g[ok], r[ok]


def model_curve(t, f0, tau, v, R, w, phi, s):
    th, g, _ = heard(tau, v, R, w, phi, s)
    return f0 * np.interp(t, th, g, left=np.nan, right=np.nan)


def r_min(t, tau, v, R, w, phi, s):
    """The fitted path's minimum distance over the heard span (+-30 s)."""
    th, _, r = heard(tau, v, R, w, phi, s)
    m = (th >= t[0] - 30) & (th <= t[-1] + 30)
    return float(r[m].min()) if m.any() else float(R)


def fit_branch(tt, f, s, start, fixed=None, multi=True):
    """One branch of s. fixed: {"w": x} or {"phi": x} to profile. Returns dict or None."""
    fw, fp = (fixed or {}).get("w"), (fixed or {}).get("phi")
    free = [k for k in ("w", "phi") if (k == "w" and fw is None) or (k == "phi" and fp is None)]

    def unpack(x):
        tau, v, lr = x[:3]; rest = dict(zip(free, x[3:]))
        return tau, v, np.exp(lr), rest.get("w", fw), rest.get("phi", fp)

    def res(x):
        tau, v, R, w, phi = unpack(x)
        th, g, _ = heard(tau, v, R, w, phi, s)
        g0 = np.interp(tt, th, g, left=np.nan, right=np.nan)
        if not np.all(np.isfinite(g0)):
            return np.full(len(tt), 1e3)
        f0 = float(np.dot(g0, f) / np.dot(g0, g0))
        return f - f0 * g0

    lo = [tt[0] - 300, V_B[0], np.log(R_B[0])] + [{"w": 0.0, "phi": PHI_B[0]}[k] for k in free]
    hi = [tt[-1] + 300, V_B[1], np.log(R_B[1])] + [{"w": W_MAX, "phi": PHI_B[1]}[k] for k in free]
    ws = ([start.get("w", W_STARTS[0])] + (list(W_STARTS) if multi else [])) if "w" in free else [None]
    ps = ([start.get("phi", PHI_STARTS[1])] + (list(PHI_STARTS) if multi else [])) if "phi" in free else [None]
    best = None
    for w0 in dict.fromkeys(ws):
        for p0 in dict.fromkeys(ps):
            x0 = [start["tau"], float(np.clip(start["v"], V_B[0] + 1, V_B[1] - 1)),
                  float(np.log(np.clip(start["R"], R_B[0] * 1.01, R_B[1] * 0.99)))]
            x0 += [float(np.clip({"w": w0, "phi": p0}[k], lo[3 + i] + 1e-4, hi[3 + i] - 1e-4)) for i, k in enumerate(free)]
            try:
                r = so.least_squares(res, x0, bounds=(lo, hi), x_scale=[1.0, 5.0, 0.05] + [0.01] * len(free),
                                     xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=300)
            except ValueError:
                continue
            if best is None or r.cost < best.cost:
                best = r
    if best is None:
        return None
    tau, v, R, w, phi = unpack(best.x)
    rr = res(best.x)
    th, g, _ = heard(tau, v, R, w, phi, s)
    g0 = np.interp(tt, th, g)
    return dict(f0=float(np.dot(g0, f) / np.dot(g0, g0)), tau=float(tau), v=float(v), R=float(R), w=float(w), phi=float(phi),
                s=int(s), rss=float(rr @ rr), rmin=r_min(tt, tau, v, R, w, phi, s),
                at_bound=bool(np.any(np.isclose(best.x, lo)) or np.any(np.isclose(best.x, hi))))


def fit(t, f, straight, fixed_sw=None, fixed_phi=None, start=None, multi=True):
    """Both branches (or the one a fixed signed rate implies); the lower-RSS one, with the other's RSS."""
    ok = np.isfinite(f); t, f = t[ok], f[ok]
    t_ref = float(t[0]); tt = t - t_ref
    st = dict(tau=(start or straight)["tau"] - t_ref, v=(start or straight)["v"], R=(start or straight)["R"])
    if start:
        st.update(w=start["w"], phi=start["phi"])
    if fixed_sw is not None:
        branches = [1 if fixed_sw >= 0 else -1]; fixed = {"w": abs(fixed_sw)}
    else:
        branches = [1, -1] if not start else [start["s"], -start["s"]]; fixed = None
    if fixed_phi is not None:
        fixed = dict(fixed or {}, phi=fixed_phi)
    out = [r for r in (fit_branch(tt, f, s, st, fixed, multi) for s in branches) if r]
    if not out:
        return None
    best = min(out, key=lambda r: r["rss"])
    best["tau"] += t_ref
    best["sw_dps"] = float(np.degrees(best["s"] * best["w"]))
    best["rss_other_branch"] = float(max(out, key=lambda r: r["rss"])["rss"]) if len(out) > 1 else None
    best["n"] = int(len(tt))
    return best


# ---------------------------------------------------------------- the passes
def turn_reference(te, pos, tau):
    """The trajectory's mean turn rate within +-30 s (deg/s, counter-clockwise +), its largest |rate|, and the
    turn's sign relative to the microphone in the model's convention (+1 away, -1 toward)."""
    m = np.abs(te - tau) <= 30
    vel = np.gradient(pos, te, axis=0)
    hd = np.unwrap(np.arctan2(vel[:, 1], vel[:, 0]))
    w = max(3, int(round(5.0 / np.median(np.diff(te)))) | 1)
    rate = np.degrees(np.gradient(ss.savgol_filter(hd, w, 2), te))
    k = int(np.argmin(np.abs(te - tau)))
    to_mic = -pos[k, :2]
    mic_left = vel[k, 0] * to_mic[1] - vel[k, 1] * to_mic[0] > 0
    mean = float(np.mean(rate[m]))
    toward = (mean > 0) == mic_left
    return dict(traj_turn_mean_dps=mean, traj_turn_max_dps=float(np.max(np.abs(rate[m]))), traj_s=-1 if toward else 1,
                traj_sw_dps=(-1 if toward else 1) * abs(mean))


def passes():
    rows_a = {r["id"]: r for r in csv.DictReader(open(me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(me.AUDIT / "sites.json"))["sites"]}
    st1 = {(r["id"], r["kind"]): r for r in csv.DictReader(open(STAGE1 / "fits.csv"))}
    out = {}
    for p in me.audit.load_passes():
        ar = rows_a[p["id"]]; site = sites[ar["site"]]
        grp = "flagged" if 100 * float(ar["fit_rms_hz_15C"]) / float(ar["f0_15C"]) >= 1.6 else "primary"
        shift, f0s = float(ar["shift_15C"]), float(ar["f0_15C"])
        t = p["ridge"][:, 0] - shift; fD = p["ridge"][:, 1]
        te, pos = me.trajectory(p, site)
        ref = me.reference(te, pos, C)
        th, g, _ = me.heard(te, pos, C)
        fA = f0s * me.at(t, th, g)
        ok = np.isfinite(fA)
        res = (fD - fA)[ok]; dt = float(np.median(np.diff(t)))
        fast = res - ss.medfilt(res, max(3, int(round(me.SLOW_S / dt)) | 1))
        L = max(1, int(round(me.BLOCK_S / dt)))
        ac = np.array([np.corrcoef(fast[:-k], fast[k:])[0, 1] if k else 1.0 for k in range(L + 1)])
        ac *= 1 - np.arange(L + 1) / (L + 1)
        B1 = st1[(p["id"], "B")]
        out[p["id"]] = dict(id=p["id"], group=grp, t=t, fA=fA, fD=fD, f0=f0s, ref=ref, fast=fast, dt=dt, ac=ac,
                            sigma2=float(np.var(fast)), kappa=(float(B1["sd_R"]) / float(B1["cov_A+noise_classical_R"])) ** 2,
                            e0=me.block_noise(fast, len(t), dt, np.random.default_rng(1)), **turn_reference(te, pos, ref["tau"]))
    return out


_P = None


def P():
    global _P
    if _P is None:
        _P = passes()
    return _P


def straight(t, f):
    ok = np.isfinite(f)
    s0 = ls.fit(t[ok], f[ok], c=C)
    return dict(f0=s0["f0"], tau=s0["tau"], v=s0["v"], R=s0["R"], rss=float(s0["rms"] ** 2 * s0["n"]))


def base(p):
    return {k: p[k] for k in ("id", "group", "traj_turn_mean_dps", "traj_turn_max_dps", "traj_s", "traj_sw_dps", "sigma2", "kappa")} | \
        dict(ref_R=p["ref"]["R"], ref_v=p["ref"]["v"], ref_tau=p["ref"]["tau"], ref_f0=p["f0"], turning=p["traj_turn_max_dps"] > 1.0)


# ---------------------------------------------------------------- units
def unit_synth(key):
    w_dps, phi_deg, s = key
    f0, v, R, tau = 180.0, 65.0, 1500.0, 0.0
    t = np.arange(-60.0, 60.0, 0.25) + tau + R / C
    w, phi = np.radians(w_dps), np.radians(phi_deg)
    f = model_curve(t, f0, tau, v, R, w, phi, s)
    truth_rmin = r_min(t, tau, v, R, w, phi, s)
    st = straight(t, f)
    tr = fit(t, f, st)
    return dict(unit=f"synth:{w_dps}:{phi_deg}:{s}", w_dps=w_dps, phi_deg=phi_deg, s=s, truth_rmin=truth_rmin,
                straight_R=st["R"], straight_err_pct=100 * (st["R"] / truth_rmin - 1), straight_v_err_pct=100 * (st["v"] / v - 1),
                turn_rmin=tr["rmin"], turn_err_pct=100 * (tr["rmin"] / truth_rmin - 1), turn_sw_dps=tr["sw_dps"],
                turn_phi_deg=float(np.degrees(tr["phi"])), turn_v=tr["v"], turn_rss=tr["rss"], straight_rss=st["rss"],
                straight_model_check=(float(np.nanmax(np.abs(model_curve(t, st["f0"], st["tau"], st["v"], st["R"], 0.0, 0.5, 1)
                                                                - ls.model(t, st["f0"], st["v"], st["R"], st["tau"], C)))) if w_dps == 0 else None))


def unit_fit(key):
    pid, curve = key
    p = P()[pid]
    f = p["fA"] if curve == "A" else p["fD"]
    st = straight(p["t"], f)
    tr = fit(p["t"], f, st)
    ref = p["ref"]
    return dict(unit=f"fit:{pid}:{curve}", curve=curve, **base(p),
                straight_R=st["R"], straight_v=st["v"], straight_rss=st["rss"], straight_err_R=st["R"] - ref["R"],
                **{f"turn_{k}": v for k, v in tr.items()}, turn_err_R=tr["rmin"] - ref["R"],
                turn_err_R_pct=100 * (tr["rmin"] / ref["R"] - 1), turn_err_v_pct=100 * (tr["v"] / ref["v"] - 1),
                straight_err_R_pct=100 * (st["R"] / ref["R"] - 1))


def interval(grid, delta):
    inside = delta <= 3.84
    ident = bool(inside.any() and not inside[0] and not inside[-1])
    return ident, (float(grid[inside][0]) if inside.any() else None), (float(grid[inside][-1]) if inside.any() else None)


def jac(t, par, s, fixed_phi):
    """Numerical Jacobian of the curve in (f0, tau, v, R, sw[, phi]) at par = (f0, tau, v, R, sw, phi)."""
    names = ["f0", "tau", "v", "R", "sw"] + ([] if fixed_phi else ["phi"])
    h = dict(f0=1e-5 * par[0], tau=1e-3, v=1e-4 * par[2], R=1e-4 * par[3], sw=1e-4, phi=1e-4)
    idx = dict(f0=0, tau=1, v=2, R=3, sw=4, phi=5)

    def curve(q):
        sw = q[4]
        return model_curve(t, q[0], q[1], q[2], q[3], abs(sw), q[5], 1 if sw >= 0 else -1)
    cols = []
    for n in names:
        e = np.zeros(6); e[idx[n]] = h[n]
        a, b = np.array(par, float) + e, np.array(par, float) - e
        if n == "sw" and abs(par[4]) < h["sw"]:      # through w = 0 the curve is even in sw at fixed s; use the branch's side
            a[4], b[4] = s * 2 * h["sw"], s * h["sw"]
            cols.append((curve(a) - curve(b)) / (h["sw"]) * s); continue
        cols.append((curve(a) - curve(b)) / (2 * h[n]))
    return np.stack(cols, 1)


def bound_R(t, par, s, sigma, rho, fixed_phi):
    import scipy.linalg as sl
    J = jac(t, par, s, fixed_phi)
    ok = np.all(np.isfinite(J), axis=1)
    J, n = J[ok], int(ok.sum())
    col = np.zeros(n); col[:len(rho)] = rho[:n]
    S = sigma ** 2 * sl.toeplitz(col)
    I = J.T @ sl.solve(S, J, assume_a="sym")
    return float(np.sqrt(np.linalg.inv(I)[3, 3]))


# ---------------------------------------------------------------- the identifiable form
# For this path r(u)^2 = R^2 + 2K(1 - cos wu), K = (v/w)(v/w + s R cos phi): one microphone hears the range history only,
# so the curve fixes R, w and K and nothing else (record: "the synthetic check finds the design over-parametrized").
# Written with Q = K w^2, which is v^2 for a straight pass: r^2 = R^2 + Q u^2 sinc^2(wu / 2pi), w >= 0.
Q_B = (-300.0 ** 2, 300.0 ** 2)
W_GRID = np.radians(np.linspace(0, 6, 13))


def heard_q(tau, R, Q, w, span=400.0, n=8001):
    u = np.linspace(-span, span, n)
    S = np.sinc(w * u / (2 * np.pi))
    r2 = R * R + Q * u * u * S * S
    if np.any(r2 <= 0):
        return None
    r = np.sqrt(r2)
    rd = Q * u * np.sinc(w * u / np.pi) / r          # d(r^2)/du / 2r = Q sin(wu)/w / r
    th = tau + u + r / C
    g = 1.0 / (1.0 + rd / C)
    ok = np.r_[True, np.diff(th) > 0] & (C + rd > 0)
    return th[ok], g[ok], r[ok]


def fit_q(t, f, start, w_fixed=None):
    """(tau, log R, Q[, w]) by least squares, f0 in closed form; from the straight fit and (w free) w starts."""
    ok = np.isfinite(f); t, f = t[ok], f[ok]
    t_ref = float(t[0]); tt = t - t_ref

    def unpack(x):
        return x[0], np.exp(x[1]), x[2], (w_fixed if w_fixed is not None else x[3])

    def res(x):
        h = heard_q(*unpack(x))
        if h is None:
            return np.full(len(tt), 1e3)
        g0 = np.interp(tt, h[0], h[1], left=np.nan, right=np.nan)
        if not np.all(np.isfinite(g0)):
            return np.full(len(tt), 1e3)
        return f - float(np.dot(g0, f) / np.dot(g0, g0)) * g0

    lo = [tt[0] - 300, np.log(R_B[0]), Q_B[0]] + ([] if w_fixed is not None else [0.0])
    hi = [tt[-1] + 300, np.log(R_B[1]), Q_B[1]] + ([] if w_fixed is not None else [W_MAX])
    best = None
    q0 = float(np.clip(start["v"] ** 2, Q_B[0] + 1, Q_B[1] - 1))
    for w0 in ([None] if w_fixed is not None else [start.get("w", 0.0), *W_STARTS]):
        x0 = [start["tau"] - t_ref, float(np.log(np.clip(start["R"], R_B[0] * 1.01, R_B[1] * 0.99))), q0] + \
             ([] if w0 is None else [float(np.clip(w0, 1e-4, W_MAX - 1e-4))])
        try:
            r = so.least_squares(res, x0, bounds=(lo, hi), x_scale=[1.0, 0.05, 100.0] + ([] if w0 is None else [0.01]),
                                 xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=300)
        except ValueError:
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None:                    # every start failed: a result, recorded, not a crash
        nan = float("nan")
        return dict(tau=nan, R=nan, Q=nan, w=nan, rss=nan, n=int(len(tt)), rmin=nan, error="no start converged")
    tau, R, Q, w = unpack(best.x)
    rr = res(best.x)
    h = heard_q(tau, R, Q, w)
    m = (h[0] >= tt[0] - 30) & (h[0] <= tt[-1] + 30)
    return dict(tau=float(tau + t_ref), R=float(R), Q=float(Q), w=float(w), rss=float(rr @ rr), n=int(len(tt)),
                rmin=float(h[2][m].min()) if m.any() else float(R))


def curve_q(t, f0, tau, R, Q, w):
    h = heard_q(tau, R, Q, w)
    return f0 * np.interp(t, h[0], h[1], left=np.nan, right=np.nan)


def bound_R_q(t, par, sigma, rho, fix_w):
    """CRB of R in (f0, tau, R, Q[, w]) with the pass's ridge noise; w fixed where its interval includes 0."""
    import scipy.linalg as sl
    names = ["f0", "tau", "R", "Q"] + ([] if fix_w else ["w"])
    h = dict(f0=1e-5 * par[0], tau=1e-3, R=1e-4 * par[2], Q=1e-4 * max(abs(par[3]), 100.0), w=1e-4)
    idx = dict(f0=0, tau=1, R=2, Q=3, w=4)
    cols = []
    for n in names:
        e = np.zeros(5); e[idx[n]] = h[n]
        a, b = np.array(par, float) + e, np.array(par, float) - e
        if n == "w" and b[4] < 0:
            b[4] = 0.0; cols.append((curve_q(t, *a) - curve_q(t, *b)) / (a[4] - b[4])); continue
        cols.append((curve_q(t, *a) - curve_q(t, *b)) / (2 * h[n]))
    J = np.stack(cols, 1); ok = np.all(np.isfinite(J), axis=1); J = J[ok]
    col = np.zeros(len(J)); col[:len(rho)] = rho[:len(J)]
    I = J.T @ sl.solve(sigma ** 2 * sl.toeplitz(col), J, assume_a="sym")
    return float(np.sqrt(np.linalg.inv(I)[2, 2]))


def unit_profile(key):
    """On A plus stage 1's first noise replicate: the profile of the turn rate w >= 0 (0-6 deg/s, 13 points), Delta against
    3.84; identified if Delta <= 3.84 only on an interval with both ends inside (0, 6) deg/s. Plus the CRB of R in the
    identifiable form at the A fit, beside the straight model's."""
    pid = key
    p = P()[pid]
    t, fN = p["t"], p["fA"] + p["e0"]
    st = straight(t, fN)
    best = fit_q(t, fN, st)
    sc = p["sigma2"] * p["kappa"]
    prof = []
    for w in W_GRID:
        r1 = fit_q(t, fN, dict(tau=best["tau"], R=best["R"], v=np.sqrt(abs(best["Q"]))), w_fixed=float(w))
        r2 = fit_q(t, fN, st, w_fixed=float(w))
        prof.append(min(r1["rss"], r2["rss"]))
    rmin = min(best["rss"], min(prof))
    delta = (np.array(prof) - rmin) / sc
    ident, lo, hi = interval(np.degrees(W_GRID), delta)
    includes0 = lo is not None and lo <= 0.0
    sA = straight(t, p["fA"])
    fa = fit_q(t, p["fA"], sA)
    tb = t[np.isfinite(p["fA"])]
    sig = float(np.sqrt(p["sigma2"]))
    b_turn = bound_R_q(tb, [sA["f0"], fa["tau"], fa["R"], fa["Q"], fa["w"]], sig, p["ac"], includes0)
    b_straight = float(crb.bound(tb, np.array([sA["f0"], sA["v"], sA["R"], sA["tau"]]), sig, p["ac"])[2])
    ref = p["ref"]
    return dict(unit=f"profile:{pid}", **base(p), w_best_dps=float(np.degrees(best["w"])), Q_best=best["Q"],
                w_identified=ident, w_lo_dps=lo, w_hi_dps=hi, w_interval_includes_0=includes0,
                profile_w=[round(float(x), 3) for x in delta],
                A_fit_w_dps=float(np.degrees(fa["w"])), A_fit_Q=fa["Q"], A_fit_rmin=fa["rmin"], A_fit_err_R_pct=100 * (fa["rmin"] / ref["R"] - 1),
                bound_R_turn_m=b_turn, bound_R_turn_pct=100 * b_turn / fa["R"], bound_w_fixed=includes0,
                bound_R_straight_m=b_straight, bound_R_straight_pct=100 * b_straight / sA["R"])


def seed(pid, rep):
    return int.from_bytes(hashlib.sha256(f"{pid}:{rep}".encode()).digest()[:8], "little")


def unit_boot(key):
    """One replicate of one pass in the identifiable form: A plus a moving-block replicate of the sub-5 s residuals."""
    pid, rep = key
    p = P()[pid]
    e = me.block_noise(p["fast"], len(p["t"]), p["dt"], np.random.default_rng(seed(pid, rep)))
    f = p["fA"] + e
    st = straight(p["t"], f)
    r = fit_q(p["t"], f, st)
    return dict(unit=f"boot:{pid}:{rep}", id=pid, rep=rep, seed=seed(pid, rep), straight_R=st["R"], straight_v=st["v"],
                rmin=r["rmin"], R=r["R"], Q=r["Q"], w_dps=float(np.degrees(r["w"])), rss=r["rss"], straight_rss=st["rss"])


def unit_flag(key):
    """The weave flag's fit: the identifiable form on the published ridge D, beside the straight fit on D."""
    pid = key
    p = P()[pid]
    st = straight(p["t"], p["fD"])
    r = fit_q(p["t"], p["fD"], st)
    return dict(unit=f"flag:{pid}", **base(p), w_D_dps=float(np.degrees(r["w"])), Q_D=r["Q"], rmin_D=r["rmin"],
                straight_R_D=st["R"], straight_err_R_D=st["R"] - p["ref"]["R"], straight_err_R_D_pct=100 * (st["R"] / p["ref"]["R"] - 1))


UNITS = {"synth": unit_synth, "fit": unit_fit, "profile": unit_profile, "boot": unit_boot, "flag": unit_flag}
SYNTH = [(w, ph, s) for w in (0.0, 1.0, 3.0) for ph in (20.0, 60.0) for s in (1, -1) if not (w == 0 and s == -1)]


def unit_keys(stage, reps):
    """(unit id, key) in a fixed order."""
    if stage == "synth":
        return [(f"synth-w{w:g}-phi{ph:g}-s{s:+d}", (w, ph, s)) for w, ph, s in SYNTH]
    ids = sorted(P())
    if stage == "fit":
        return [(f"fit-{i}-{c}", (i, c)) for i in ids for c in ("A", "D")]
    if stage in ("profile", "flag"):
        return [(f"{stage}-{i}", i) for i in ids]
    return [(f"boot-{i}-{r:03d}", (i, r)) for i in ids for r in range(reps)]


def params(stage, reps):
    """Everything that decides a unit's result; merging refuses units run with other values."""
    return dict(stage=stage, c=C, v_bounds=V_B, R_bounds=R_B, w_max_dps=6.0, w_starts_dps=[0.5, 1.5, 3.0],
                phi_starts_deg=[15.0, 45.0, 75.0], w_grid_dps=[0.0, 6.0, 13], q_bounds=Q_B,
                stage1=str(STAGE1.relative_to(me.DATA)), replicates=reps if stage == "boot" else None)


def inputs():
    corpus = sorted(str(f.relative_to(me.DATA)) for f in (me.DATA / "derived/livermore").glob("*/*/*")
                    if f.suffix == ".kml" or f.name == "frequency_vs_time_used.csv")
    return ["raw/audio/livermore/zenodo-23424278/final_results_40_cases.csv", "runs/2026-11-04-livermore-audit/passes.csv",
            "runs/2026-11-04-livermore-audit/sites.json", f"{STAGE1.relative_to(me.DATA)}/fits.csv", *corpus]


def _run(item):
    uid, key, stage = item
    return uid, UNITS[stage](key)


def run_stage(run, stage, units, todo_keys):
    from dopplertrack.parallel import default_jobs
    print(f"{stage}: {len(units.ids)} units, {len(todo_keys)} to run in this shard", flush=True)
    with ProcessPoolExecutor(default_jobs()) as ex:
        for uid, r in ex.map(_run, [(u, k, stage) for u, k in todo_keys]):
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            (d / "result.json").write_text(json.dumps(r, default=float) + "\n")
            units.finish(uid, {k: r[k] for k in ("turn_err_R_pct", "turn_sw_dps", "sw_identified", "turn_err_pct", "rmin") if k in r})
            print("  ", uid, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()
                              if k in ("turn_err_R_pct", "straight_err_R_pct", "turn_sw_dps", "turn_err_pct", "straight_err_pct",
                                       "sw_identified", "phi_identified", "best_sw_dps", "traj_sw_dps", "rmin")}, flush=True)


def write_csv(path, rows):
    keys_ = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys_); w.writeheader()
        w.writerows({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows)


def merge(run, stage, units):
    rows = [json.loads((d / "result.json").read_text()) for d in units.all().values()]
    write_csv(run / f"{stage}.csv", rows)
    print(f"{stage}: {len(rows)} units merged into {run / (stage + '.csv')}")
    if stage == "boot":
        b = {}
        for r in rows:
            b.setdefault(r["id"], []).append(r)
        out = []
        for pid, rs in sorted(b.items()):
            m = np.array([[x["rmin"], x["Q"], x["w_dps"], x["straight_R"]] for x in rs])
            sd = m.std(axis=0, ddof=1)
            cc = np.corrcoef(m.T) if np.all(sd > 0) else np.full((4, 4), np.nan)
            out.append(dict(id=pid, n=len(rs), sd_rmin=sd[0], sd_Q=sd[1], sd_w_dps=sd[2], sd_straight_R=sd[3],
                            corr_w_R=cc[2, 0], corr_w_Q=cc[2, 1], corr_Q_R=cc[1, 0]))
        write_csv(run / "boot_summary.csv", out)


def report(fit_run, profile_run):
    """The criterion (fixed before running) from the merged fit.csv and profile.csv."""
    fits = [r for r in csv.DictReader(open(fit_run / "fit.csv")) if r["curve"] == "A"]
    prof = {r["id"]: r for r in csv.DictReader(open(profile_run / "profile.csv"))} if (profile_run / "profile.csv").exists() else {}
    f = lambda r, k: float(r[k])
    turning = lambda r: r["turning"] == "True"
    med = lambda xs: float(np.median(xs)) if len(xs) else None
    out = {}
    for curve in ("A", "D"):
        rows = [r for r in csv.DictReader(open(fit_run / "fit.csv")) if r["curve"] == curve]
        groups = (("turning", [r for r in rows if turning(r)]), ("non_turning", [r for r in rows if not turning(r)]),
                  ("primary", [r for r in rows if r["group"] == "primary"]), ("flagged", [r for r in rows if r["group"] == "flagged"]))
        out[curve] = {name: dict(n=len(g), straight_m=med([abs(f(r, "straight_err_R")) for r in g]), turn_m=med([abs(f(r, "turn_err_R")) for r in g]),
                                 straight_pct=med([abs(f(r, "straight_err_R_pct")) for r in g]), turn_pct=med([abs(f(r, "turn_err_R_pct")) for r in g]),
                                 turn_v_pct=med([abs(f(r, "turn_err_v_pct")) for r in g]),
                                 rss_ratio=med([f(r, "turn_rss") / f(r, "straight_rss") for r in g])) for name, g in groups}
    turn = [r for r in fits if turning(r)]
    sign_ok = [r for r in turn if int(r["turn_s"]) == int(r["traj_s"]) and np.sign(f(r, "turn_sw_dps")) == np.sign(f(r, "traj_sw_dps"))]
    x = np.array([f(r, "turn_sw_dps") for r in turn]); y = np.array([f(r, "traj_sw_dps") for r in turn])
    corr = float(np.corrcoef(x, y)[0, 1]) if len(turn) > 2 and x.std() > 0 and y.std() > 0 else None
    ident = [r for r in turn if prof.get(r["id"], {}).get("w_identified") == "True"]
    A = out["A"]
    c = {"1_turning_le_201m": A["turning"]["turn_m"] <= 201.0, "2_non_turning_le_182m": A["non_turning"]["turn_m"] <= 182.0,
         "3_primary_le_160m": A["primary"]["turn_m"] <= 160.0,
         "4_w_identified_ge_11_of_16": len(ident) >= 11 if prof else None, "n_w_identified": len(ident) if prof else None,
         "5_sign_ge_11_and_corr_ge_0.5": len(sign_ok) >= 11 and corr is not None and corr >= 0.5, "n_sign": len(sign_ok), "corr": corr}
    c["enters"] = all(v for k, v in c.items() if k[0].isdigit()) if prof else None
    out["criterion"] = c
    json.dump(out, open(fit_run / "summary.json", "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=list(UNITS) + ["report"])
    shards.add_args(ap)
    ap.add_argument("--replicates", type=int, default=200, help="boot: replicates per pass")
    ap.add_argument("--profile-run", type=Path, help="report: the run folder holding profile.csv (default: RUN)")
    a = ap.parse_args()
    if a.stage == "report":
        report(a.run, a.profile_run or a.run); return
    if a.inputs:
        shards.print_inputs([], inputs(), [], ()); return
    run = shards.open_run(a.run, f"turn-model-{a.stage}", {"script": "tools/experiments/2026-11-04/turn_model.py",
                                                            "params": params(a.stage, a.replicates)})
    ks = unit_keys(a.stage, a.replicates)
    units = shards.Units(run, [u for u, _ in ks], params(a.stage, a.replicates), a.shard, a.resume)
    if a.merge:
        merge(run, a.stage, units); return
    todo = set(units.todo())
    run_stage(run, a.stage, units, [(u, k) for u, k in ks if u in todo])
    if not units.todo() and a.shard == (1, 1):
        merge(run, a.stage, units)


if __name__ == "__main__":
    main()
