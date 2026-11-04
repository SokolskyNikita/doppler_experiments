"""Phase 2 item 2 follow-up: the three-parameter turn model against stage 1's model error (design, expectation and
criterion in docs/experiments/2026-11-04-model-error.md, "The turn model", written before any run).

Forward model in emission time u, heard at t = tau + u + r/c, f = f0 / (1 + rdot/c), a constant-rate level turn:
  x = (v/w) sin(wu),  y = d + s (v/w)(1 - cos(wu)),  z = h,  d = R cos(phi),  h = R sin(phi)
so at u = 0 the aircraft is at its horizontal CPA, heading at right angles to the microphone; s = +1 turns away
from it, s = -1 toward it; w = 0 is the straight pass (phi then unidentified). f0 is solved in closed form;
least_squares searches (tau, v, log R, w, phi) on each branch of s, from the straight fit x w {0.5, 1.5, 3} deg/s
x phi {15, 45, 75} deg, and the lower-RSS branch is the fit. The compared R is the fitted path's minimum distance
over the heard span, like the trajectory reference R*. Signed rate sw = s*w (deg/s, + away).

Stages, each a set of units written one jsonl line per unit to RUN/<stage>[_<k>of<n>].jsonl, so a stopped or split
run resumes (units already in any of the stage's files are skipped) and merges to the same numbers:
  synth    synthetic arcs (f0 180 Hz, 65 m/s, 1.5 km; w 0, 1, 3 deg/s; phi 20, 60 deg; both signs): recovery,
           and what a straight fit misses on each
  fit      the 40 Livermore passes on curve A (the trajectory curve; the criterion) and D (the published ridge)
  profile  on A plus stage 1's first noise replicate: profiles of sw (-6..6 deg/s, 25 points) and phi (0..90 deg,
           10 points), Delta = (RSS - RSS_min)/(sigma^2 kappa) against 3.84 (Raue 2009); the six-parameter
           Cramer-Rao bound of R with the pass's ridge noise (phi held fixed where sw's interval includes 0) beside
           the straight model's
  boot     (pass, replicate): A plus a moving-block replicate of the sub-5 s residuals, seed from (pass, replicate);
           refit on both branches. The cloud part
  merge    the CSVs, summary.json and the criterion

usage: uv run python tools/experiments/2026-11-04/turn_model.py RUN STAGE [--workers 2] [--shard K/N] [--replicates 200]
"""
import argparse
import csv
import hashlib
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


def unit_profile(key):
    pid = key
    p = P()[pid]
    t, fN = p["t"], p["fA"] + p["e0"]
    st = straight(t, fN)
    best = fit(t, fN, st)
    sc = p["sigma2"] * p["kappa"]
    start = dict(tau=best["tau"], v=best["v"], R=best["R"], w=best["w"], phi=best["phi"], s=best["s"])
    prof_sw = []
    for sw in SW_GRID:
        r = fit(t, fN, st, fixed_sw=float(sw), start=start, multi=False)
        r2 = fit(t, fN, st, fixed_sw=float(sw), multi=True)
        prof_sw.append(min(x["rss"] for x in (r, r2) if x))
    prof_phi = []
    for ph in PHI_GRID:
        r = fit(t, fN, st, fixed_phi=float(ph), start=start, multi=False)
        r2 = fit(t, fN, st, fixed_phi=float(ph), multi=True)
        prof_phi.append(min(x["rss"] for x in (r, r2) if x))
    rmin = min(best["rss"], min(prof_sw), min(prof_phi))
    d_sw = (np.array(prof_sw) - rmin) / sc; d_phi = (np.array(prof_phi) - rmin) / sc
    id_sw, lo_sw, hi_sw = interval(np.degrees(SW_GRID), d_sw)
    id_phi, lo_phi, hi_phi = interval(np.degrees(PHI_GRID), d_phi)
    includes0 = lo_sw is not None and lo_sw <= 0 <= hi_sw
    # bounds on curve A at the A fit (the criterion's curve), with the pass's ridge noise
    fa = fit(t, p["fA"], straight(t, p["fA"]))
    sig = float(np.sqrt(p["sigma2"]))
    tb = t[np.isfinite(p["fA"])]
    par = [fa["f0"], fa["tau"], fa["v"], fa["R"], fa["s"] * fa["w"], fa["phi"]]
    b_turn = bound_R(tb, par, fa["s"], sig, p["ac"], fixed_phi=includes0)
    sA = straight(t, p["fA"])
    b_straight = float(crb.bound(tb, np.array([sA["f0"], sA["v"], sA["R"], sA["tau"]]), sig, p["ac"])[2])
    return dict(unit=f"profile:{pid}", **base(p), best_sw_dps=best["sw_dps"], best_phi_deg=float(np.degrees(best["phi"])),
                sw_identified=id_sw, sw_lo_dps=lo_sw, sw_hi_dps=hi_sw, sw_interval_includes_0=includes0,
                phi_identified=id_phi, phi_lo_deg=lo_phi, phi_hi_deg=hi_phi,
                profile_sw=[round(float(x), 3) for x in d_sw], profile_phi=[round(float(x), 3) for x in d_phi],
                bound_R_turn_m=b_turn, bound_R_turn_pct=100 * b_turn / fa["R"], bound_phi_fixed=includes0,
                bound_R_straight_m=b_straight, bound_R_straight_pct=100 * b_straight / sA["R"])


def seed(pid, rep):
    return int.from_bytes(hashlib.sha256(f"{pid}:{rep}".encode()).digest()[:8], "little")


def unit_boot(key):
    pid, rep = key
    p = P()[pid]
    e = me.block_noise(p["fast"], len(p["t"]), p["dt"], np.random.default_rng(seed(pid, rep)))
    f = p["fA"] + e
    st = straight(p["t"], f)
    r = fit(p["t"], f, st)
    return dict(unit=f"boot:{pid}:{rep}", id=pid, rep=rep, seed=seed(pid, rep), straight_R=st["R"], straight_v=st["v"],
                rmin=r["rmin"], R=r["R"], v=r["v"], sw_dps=r["sw_dps"], phi_deg=float(np.degrees(r["phi"])), s=r["s"], rss=r["rss"])


UNITS = {"synth": unit_synth, "fit": unit_fit, "profile": unit_profile, "boot": unit_boot}


def keys(stage, reps):
    if stage == "synth":
        return [(w, ph, s) for w in (0.0, 1.0, 3.0) for ph in (20.0, 60.0) for s in (1, -1) if not (w == 0 and s == -1)]
    ids = sorted(P())
    if stage == "fit":
        return [(i, c) for i in ids for c in ("A", "D")]
    if stage == "profile":
        return ids
    return [(i, r) for i in ids for r in range(reps)]


def unit_name(stage, k):
    return f"{stage}:" + ":".join(map(str, k if isinstance(k, tuple) else (k,)))


def done_units(run, stage):
    out = set()
    for f in run.glob(f"{stage}*.jsonl"):
        for line in open(f):
            if line.strip():
                out.add(json.loads(line)["unit"])
    return out


def run_stage(run, stage, workers, shard, reps):
    ks = keys(stage, reps)
    k, n = shard
    ks = [x for i, x in enumerate(ks) if i % n == k - 1]
    done = done_units(run, stage)
    todo = [x for x in ks if unit_name(stage, x) not in done]
    out = run / (f"{stage}.jsonl" if n == 1 else f"{stage}_{k}of{n}.jsonl")
    print(f"{stage}: {len(ks)} units in this shard, {len(ks) - len(todo)} done, {len(todo)} to go", flush=True)
    with ProcessPoolExecutor(workers) as ex, open(out, "a") as fh:
        for r in ex.map(UNITS[stage], todo):
            fh.write(json.dumps(r, default=float) + "\n"); fh.flush()
            print("  ", r["unit"], {k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in r.items()
                                     if k2 in ("turn_err_R_pct", "straight_err_R_pct", "turn_sw_dps", "turn_err_pct", "straight_err_pct",
                                               "sw_identified", "phi_identified", "best_sw_dps", "traj_sw_dps")}, flush=True)


def load(run, stage):
    rows = {}
    for f in sorted(run.glob(f"{stage}*.jsonl")):
        for line in open(f):
            if line.strip():
                r = json.loads(line); rows[r["unit"]] = r
    return [rows[k] for k in sorted(rows)]


def merge(run):
    out = {}
    for stage in UNITS:
        rows = load(run, stage)
        if rows:
            keys_ = list(dict.fromkeys(k for r in rows for k in r))
            with open(run / f"{stage}.csv", "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys_); w.writeheader()
                w.writerows({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows)
            out[f"n_{stage}"] = len(rows)
    fits = [r for r in load(run, "fit") if r["curve"] == "A"]
    med = lambda xs: float(np.median(xs)) if len(xs) else None
    if fits:
        turn = [r for r in fits if r["turning"]]; non = [r for r in fits if not r["turning"]]; prim = [r for r in fits if r["group"] == "primary"]
        for name, g in (("turning", turn), ("non_turning", non), ("primary", prim), ("flagged", [r for r in fits if r["group"] == "flagged"])):
            out[name] = dict(n=len(g), straight_m=med([abs(r["straight_err_R"]) for r in g]), turn_m=med([abs(r["turn_err_R"]) for r in g]),
                             straight_pct=med([abs(r["straight_err_R_pct"]) for r in g]), turn_pct=med([abs(r["turn_err_R_pct"]) for r in g]),
                             turn_v_pct=med([abs(r["turn_err_v_pct"]) for r in g]),
                             rss_ratio=med([r["turn_rss"] / r["straight_rss"] for r in g]))
        sign_ok = [r for r in turn if r["turn_s"] == r["traj_s"] and np.sign(r["turn_sw_dps"]) == np.sign(r["traj_sw_dps"])]
        x = np.array([r["turn_sw_dps"] for r in turn]); y = np.array([r["traj_sw_dps"] for r in turn])
        corr = float(np.corrcoef(x, y)[0, 1]) if len(turn) > 2 and x.std() > 0 and y.std() > 0 else None
        prof = {r["id"]: r for r in load(run, "profile")}
        ident = [r for r in turn if prof.get(r["id"], {}).get("sw_identified")]
        out["criterion"] = {
            "1_turning_le_201m": out["turning"]["turn_m"] <= 201.0,
            "2_non_turning_le_182m": out["non_turning"]["turn_m"] <= 182.0,
            "3_primary_le_160m": out["primary"]["turn_m"] <= 160.0,
            "4_sw_identified_ge_11_of_16": (len(ident) >= 11) if prof else None, "n_identified": len(ident) if prof else None,
            "5_sign_ge_11_and_corr_ge_0.5": (len(sign_ok) >= 11 and corr is not None and corr >= 0.5), "n_sign": len(sign_ok), "corr": corr}
        out["criterion"]["enters"] = all(v for k2, v in out["criterion"].items() if k2[0].isdigit())
    json.dump(out, open(run / "summary.json", "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run", type=Path); ap.add_argument("stage", choices=list(UNITS) + ["merge"])
    ap.add_argument("--workers", type=int, default=2); ap.add_argument("--shard", default="1/1"); ap.add_argument("--replicates", type=int, default=200)
    a = ap.parse_args()
    if a.stage == "merge":
        merge(a.run); return
    k, n = map(int, a.shard.split("/"))
    run_stage(a.run, a.stage, a.workers, (k, n), a.replicates)


if __name__ == "__main__":
    main()
