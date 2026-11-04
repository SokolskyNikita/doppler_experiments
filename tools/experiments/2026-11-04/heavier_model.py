"""Phase 2 item 2 follow-up: does one extra parameter in the pass model cut the model error of stage 1?

Models, each a forward model in emission time u = t_e - tau (heard at t_e + r/c, f = f0(t_e) dt_e/dt_h):
  straight  x = v u                               f0 constant                        (straight_pass_ls)
  drift     x = v u                               f0 (1 + eta u / T), T the ridge span
  accel     x = v u + a u^2 / 2                   f0 constant
  both      x = v u + a u^2 / 2                   f0 (1 + eta u / T)
with r = sqrt(R^2 + x^2), so v is the speed and R the slant range at the CPA. f0 and f0*eta enter
linearly and are solved in closed form; least_squares searches (tau, v, log R[, a]) in track-relative
time. Bounds: v 10-300 m/s, R 100 m-30 km, eta within +-5 % over the span, a within +-3 m/s^2.

Per Livermore pass (primary 29 and flagged 11), against stage 1's references:
  - fits on curve A (the trajectory curve; its true eta is 0, so a fitted eta there is a nuisance term
    absorbing kinematic error, not drift) and on D (the published ridge, where eta is read as drift)
  - identifiability of the new parameter (Raue 2009): its profile on A + one stage-1 noise replicate,
    Delta = (RSS(p) - RSS_min) / (sigma^2 kappa), sigma^2 the sub-5 s noise variance and kappa the
    pass's (bootstrap SD / classical SD)^2 of R from stage 1; identified if Delta <= 3.84 is a finite
    interval inside the bounds; plus its bootstrap SD and correlations with v and R over N_BOOT replicates
  - the trajectory's own along-track acceleration and largest turn rate within +-30 s of the CPA
Criterion, fixed before running: a model enters if on curve A it cuts the primary passes' median |R - R*|
from 229 m to <= 160 m, doesn't worsen the flagged passes' median, and its extra parameter is identified
on at least two thirds of the primary passes.

Run from the repo root:  uv run python tools/experiments/2026-11-04/heavier_model.py "$RUN" [--models drift accel] [--boot 200]
"""
import argparse
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import scipy.optimize as so
import scipy.signal as ss

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("model_error", HERE / "model_error.py")
me = importlib.util.module_from_spec(spec); spec.loader.exec_module(me)
ls = me.ls
C = me.C15
V_B, R_B, ETA_B, A_B = (10.0, 300.0), (100.0, 30000.0), 0.05, 3.0
STAGE1 = me.DATA / "runs/2026-11-04-model-error-2"


def basis(t, tau, v, R, a, T, span=400.0, n=8001):
    """g0(t) = dt_e/dt_h and g1(t) = g0 * u/T at heard times t, for x = v u + a u^2 / 2."""
    u = np.linspace(-span, span, n)
    x = v * u + 0.5 * a * u * u
    xd = v + a * u
    r = np.sqrt(R * R + x * x)
    rd = x * xd / r
    th = tau + u + r / C
    g = 1.0 / (1.0 + rd / C)
    ok = np.r_[True, np.diff(th) > 0] & (C + rd > 0)
    th, g, uu = th[ok], g[ok], u[ok]
    g0 = np.interp(t, th, g, left=np.nan, right=np.nan)
    ue = np.interp(t, th, uu, left=np.nan, right=np.nan)
    return g0, g0 * ue / T


def model_curve(t, f0, v, R, tau, eta=0.0, a=0.0, T=60.0):
    g0, g1 = basis(t, tau, v, R, a, T)
    return f0 * g0 + f0 * eta * g1


def solve_linear(f, g0, g1, drift):
    A = np.stack([g0, g1], 1) if drift else g0[:, None]
    coef, *_ = np.linalg.lstsq(A, f, rcond=None)
    f0 = coef[0]
    return f0, (coef[1] / f0 if drift else 0.0), f - A @ coef


def fit(t, f, model, start, T, fixed=None, multi=True):
    """start: dict with tau, v, R (a, eta optional). fixed: {"eta": x} or {"a": x} to profile.
    Returns dict f0, v, R, tau, eta, a, rss."""
    ok = np.isfinite(f); t, f = t[ok], f[ok]
    t_ref = float(t[0]); tt = t - t_ref
    drift = model in ("drift", "both") and not (fixed and "eta" in fixed)
    accel = model in ("accel", "both") and not (fixed and "a" in fixed)
    eta_fix = fixed.get("eta", 0.0) if fixed else 0.0
    a_fix = fixed.get("a", 0.0) if fixed else 0.0

    def unpack(x):
        tau, v, lr = x[:3]
        return tau, v, np.exp(lr), (x[3] if accel else a_fix)

    def res(x):
        tau, v, R, a = unpack(x)
        g0, g1 = basis(tt, tau, v, R, a, T)
        if not np.all(np.isfinite(g0)):
            return np.full(len(tt), 1e3)
        if drift:
            return solve_linear(f, g0, g1, True)[2]
        base = g0 + eta_fix * g1
        f0 = float(np.dot(base, f) / np.dot(base, base))
        return f - f0 * base

    lo = [tt[0] - 300, V_B[0], np.log(R_B[0])] + ([-A_B] if accel else [])
    hi = [tt[-1] + 300, V_B[1], np.log(R_B[1])] + ([A_B] if accel else [])
    best = None
    # the straight fit's (tau, v, R) with a grid of accelerations, or (multi=False) only the given start
    a_starts = ([start.get("a") or 0.0] + (list(np.linspace(-A_B, A_B, 7)) if multi else [])) if accel else [None]
    for a0 in a_starts:
        x0 = [start["tau"] - t_ref, min(max(start["v"], V_B[0] + 1), V_B[1] - 1), np.log(min(max(start["R"], R_B[0] * 1.01), R_B[1] * 0.99))]
        if accel:
            x0.append(float(np.clip(a0, -A_B + 1e-3, A_B - 1e-3)))
        r = so.least_squares(res, x0, bounds=(lo, hi), x_scale=[1.0, 5.0, 0.05] + ([0.2] if accel else []),
                             xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=400)
        if best is None or r.cost < best.cost:
            best = r
    tau, v, R, a = unpack(best.x)
    g0, g1 = basis(tt, tau, v, R, a, T)
    if drift:
        f0, eta, rr = solve_linear(f, g0, g1, True)
    else:
        base = g0 + eta_fix * g1
        f0 = float(np.dot(base, f) / np.dot(base, base)); eta = eta_fix; rr = f - f0 * base
    return dict(f0=float(f0), v=float(v), R=float(R), tau=float(tau + t_ref), eta=float(eta), a=float(a),
                rss=float(rr @ rr), n=int(len(tt)), at_bound=bool(np.any(np.isclose(best.x, lo)) or np.any(np.isclose(best.x, hi))))


def kinematics(te, pos, tau):
    """Along-track acceleration (mean dv/dt) and the largest turn rate (deg/s, 5 s smoothing) within +-30 s."""
    m = np.abs(te - tau) <= 30
    vel = np.gradient(pos, te, axis=0)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    acc = np.gradient(sp, te)
    hd = np.unwrap(np.arctan2(vel[:, 0], vel[:, 1]))
    w = max(3, int(round(5.0 / np.median(np.diff(te)))) | 1)
    rate = np.degrees(np.gradient(ss.savgol_filter(hd, w, 2), te))
    return float(np.mean(acc[m])), float(np.max(np.abs(rate[m])))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--models", nargs="+", default=["drift", "accel"])
    ap.add_argument("--boot", type=int, default=200); ap.add_argument("--only")
    a = ap.parse_args(); run = Path(a.run)
    rows_a = {r["id"]: r for r in csv.DictReader(open(me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(me.AUDIT / "sites.json"))["sites"]}
    st1 = {(r["id"], r["kind"]): r for r in csv.DictReader(open(STAGE1 / "fits.csv"))}
    rng = np.random.default_rng(20261104)
    out_fit, out_prof = [], []
    for p in me.audit.load_passes():
        if a.only and p["id"] != a.only:
            continue
        ar = rows_a[p["id"]]; site = sites[ar["site"]]
        grp = "flagged" if 100 * float(ar["fit_rms_hz_15C"]) / float(ar["f0_15C"]) >= 1.6 else "primary"
        shift, f0s = float(ar["shift_15C"]), float(ar["f0_15C"])
        t = p["ridge"][:, 0] - shift; fD = p["ridge"][:, 1]; T = float(t[-1] - t[0])
        te, pos = me.trajectory(p, site)
        ref = me.reference(te, pos, C); ref["f0"] = f0s
        acc, turn = kinematics(te, pos, ref["tau"])
        th, g, _ = me.heard(te, pos, C)
        fA = f0s * me.at(t, th, g)
        ok = np.isfinite(fA)
        res = (fD - fA)[ok]; dt = float(np.median(np.diff(t)))
        fast = res - ss.medfilt(res, max(3, int(round(me.SLOW_S / dt)) | 1))
        sigma2 = float(np.var(fast))
        B1 = st1[(p["id"], "B")]
        kappa = (float(B1["sd_R"]) / float(B1["cov_A+noise_classical_R"])) ** 2
        e0 = me.block_noise(fast, len(t), dt, np.random.default_rng(1))
        base = dict(id=p["id"], group=grp, ref_R=ref["R"], ref_v=ref["v"], ref_tau=ref["tau"], ref_f0=f0s,
                    traj_accel=acc, traj_turn_dps=turn, kappa=kappa, sigma2=sigma2, span=T)
        for curve, ff in (("A", fA), ("D", fD)):
            s0 = ls.fit(t[np.isfinite(ff)], ff[np.isfinite(ff)], c=C)
            start = dict(tau=s0["tau"], v=s0["v"], R=s0["R"])
            fits = {"straight": dict(f0=s0["f0"], v=s0["v"], R=s0["R"], tau=s0["tau"], eta=0.0, a=0.0,
                                     rss=float(s0["rms"] ** 2 * s0["n"]), n=s0["n"], at_bound=s0["at_bound"])}
            for m in a.models:
                fits[m] = fit(t, ff, m, start, T)
            for m, r in fits.items():
                out_fit.append(dict(**base, curve=curve, model=m, **r,
                                    err_R=r["R"] - ref["R"], err_R_pct=100 * (r["R"] / ref["R"] - 1),
                                    err_v_pct=100 * (r["v"] / ref["v"] - 1), err_f0_pct=100 * (r["f0"] / f0s - 1),
                                    err_tau=r["tau"] - ref["tau"]))
        # identifiability on A + one noise replicate: profile, then bootstrap
        fN = fA + e0
        s0 = ls.fit(t[np.isfinite(fN)], fN[np.isfinite(fN)], c=C)
        start = dict(tau=s0["tau"], v=s0["v"], R=s0["R"])
        for m in a.models:
            par, bound = ("eta", ETA_B) if m == "drift" else ("a", A_B)
            if m == "both":
                continue
            best = fit(t, fN, m, start, T)
            grid = np.linspace(-bound, bound, 15)
            prof = [fit(t, fN, m, dict(tau=best["tau"], v=best["v"], R=best["R"], a=best["a"]), T, fixed={par: float(x)}, multi=False)["rss"]
                    for x in grid]
            rmin = min(best["rss"], min(prof))
            delta = (np.array(prof) - rmin) / (sigma2 * kappa)
            inside = delta <= 3.84
            identified = bool(inside.any() and not inside[0] and not inside[-1])
            boots = []
            for _ in range(a.boot):
                e = me.block_noise(fast, len(t), dt, rng)
                r = fit(t, fA + e, m, dict(tau=best["tau"], v=best["v"], R=best["R"], a=best["a"]), T, multi=False)
                boots.append((r[par], r["v"], r["R"]))
            b = np.array(boots)
            corr = np.corrcoef(b.T) if np.all(np.std(b, axis=0) > 0) else np.full((3, 3), np.nan)
            out_prof.append(dict(**base, model=m, par=par, best=best[par], identified=identified,
                                 lo=float(grid[inside][0]) if inside.any() else np.nan, hi=float(grid[inside][-1]) if inside.any() else np.nan,
                                 delta_at_lo=float(delta[0]), delta_at_hi=float(delta[-1]), boot_sd=float(np.std(b[:, 0], ddof=1)),
                                 corr_v=float(corr[0, 1]), corr_R=float(corr[0, 2]), profile=json.dumps([round(x, 3) for x in delta])))
        print(p["id"], grp, " ".join(f"{r['model']}:{r['curve']} R {r['err_R_pct']:+6.1f}%" for r in out_fit[-2 * (1 + len(a.models)):]),
              " | ", " ".join(f"{q['model']} {q['par']}={q['best']:+.3f} id={q['identified']}" for q in out_prof[-len([m for m in a.models if m != 'both']):]) if out_prof else "",
              flush=True)
    for name, data in (("heavier_fits", out_fit), ("heavier_profiles", out_prof)):
        if data:
            keys = list(dict.fromkeys(k for r in data for k in r))
            with open(run / f"{name}.csv", "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(data)


if __name__ == "__main__":
    main()
