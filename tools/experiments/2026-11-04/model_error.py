"""Phase 2 item 2, stage 1: model error of the straight-pass least-squares fit on the Livermore corpus.

Per pass, at the reconstructed microphone (runs/2026-11-04-livermore-audit/sites.json) and on the ADS-B
clock (the published ridge moved by the audit's per-pass shift):
  reference  R*, v*, tau*, t_heard* from the trajectory (PCHIP, 15 C); f0* is the audit's fitted rest
             frequency, a model quantity, not an observation
  C          the ideal straight pass with (f0*, v*, R*, tau*) at the ridge's sample times
  A          the trajectory curve f0* g(t), noiseless
  B, C+n     A and C plus noise: a moving-block bootstrap (2 s blocks) of the ridge's residuals about A,
             less their 5 s running median, so the noise model is the sub-5 s part only
  D          the published ridge
each fitted with straight_pass_ls.fit. The fit's spread is the bootstrap SD over B.
Perturbations of A, one at a time: f0 drift (+-0.5, 1, 2 % over the ridge span), sound speed from the
KLVK temperature, wind from the OAK sounding, linear and smoothing-spline interpolation, the track's
height shifted by the EGM96 undulation, the recorder at Terrarium + 1.5 m, and the full +-150 s window.
Approach and recede halves of A, D and B are fitted separately. Criterion, fixed before running: a
perturbation enters the model if it moves a fitted parameter on A by more than that pass's bootstrap SD
on the median primary pass.

Run from the repo root:  uv run python tools/experiments/2026-11-04/model_error.py "$RUN"
"""
import csv
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.signal as ss
from PIL import Image
from scipy.interpolate import PchipInterpolator, make_smoothing_spline

from dopplertrack.doppler import speed_of_sound
from dopplertrack.geo import lla_to_enu

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
AUDIT = DATA / "runs/2026-11-04-livermore-audit"
N_BOOT = 200
BLOCK_S, SLOW_S = 2.0, 5.0
DRIFTS = (-0.02, -0.01, -0.005, 0.005, 0.01, 0.02)
PARAMS = ("f0", "v", "R", "tau")
C15 = speed_of_sound(15.0)


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


ls = load("straight_pass_ls")
audit = load("livermore_audit")


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()


def geoid(lat, lon):
    im = Image.open(DATA / "raw/aux/geoid/us_nga_egm96_15.tif")
    a = np.array(im, float)
    r, c = (90.0 - lat) / 0.25, (lon + 180.0) / 0.25     # 721 x 1440 grid points from (90, -180)
    r0, c0 = int(r), int(c); fr, fc = r - r0, c - c0
    return float((1 - fr) * (1 - fc) * a[r0, c0] + (1 - fr) * fc * a[r0, c0 + 1]
                 + fr * (1 - fc) * a[r0 + 1, c0] + fr * fc * a[r0 + 1, c0 + 1])


def metar_temp(t):
    best = None
    for p in sorted((DATA / "raw/aux/metar").glob("KLVK_*.csv")):
        for row in csv.DictReader(open(p)):
            if row["tmpf"] in ("M", ""):
                continue
            dt = abs(utc(row["valid"].replace(" ", "T") + "Z") - t)
            if best is None or dt < best[0]:
                best = (dt, (float(row["tmpf"]) - 32) / 1.8)
    return best[1], best[0]


def sounding_wind(t, h):
    """(u east, v north) m/s at height h m MSL from the OAK sounding nearest in time, and its age in s."""
    rows = []
    for p in sorted((DATA / "raw/aux/metar").glob("RAOB_KOAK_*.csv")):
        rows += list(csv.DictReader(open(p)))
    times = sorted({r["validUTC"] for r in rows})
    tv = min(times, key=lambda s: abs(utc(s.replace(" ", "T") + "Z") - t))
    lev = [(float(r["height_m"]), float(r["drct"]), float(r["speed_kts"])) for r in rows
           if r["validUTC"] == tv and "M" not in (r["height_m"], r["drct"], r["speed_kts"])]
    lev.sort()
    z, d, sp = (np.array(x) for x in zip(*lev))
    u = -sp * 0.514444 * np.sin(np.radians(d)); v = -sp * 0.514444 * np.cos(np.radians(d))   # wind toward
    return float(np.interp(h, z, u)), float(np.interp(h, z, v)), abs(utc(tv.replace(" ", "T") + "Z") - t)


def trajectory(p, site, interp="pchip", alt_shift=0.0, site_alt=None, dt=0.05, span=300.0):
    """Dense emission times and ENU positions (m) relative to the microphone."""
    tr = p["track"]
    mid = p["ridge"][:, 0].mean()
    m = np.abs(tr[:, 0] - mid) <= span
    t, lat, lon, alt = tr[m].T
    obs_alt = site["alt_msl"] if site_alt is None else site_alt
    enu = lla_to_enu(lat, lon, alt + alt_shift, site["lat"], site["lon"], obs_alt)
    te = np.arange(t[0], t[-1], dt)
    if interp == "pchip":
        pos = PchipInterpolator(t, enu.T, axis=1)(te).T
    elif interp == "linear":
        pos = np.stack([np.interp(te, t, enu[:, j]) for j in range(3)], axis=1)
    else:
        pos = np.stack([make_smoothing_spline(t, enu[:, j])(te) for j in range(3)], axis=1)
    return te, pos


def heard(te, pos, c, wind=None, f0=1.0, drift=None):
    """Heard times and frequencies by travel time: t_h = t_e + r / c_eff, f = f0(t_e) dt_e/dt_h, with
    c_eff = c + w . n (n the unit vector from source to microphone) when a wind (u, v) is given."""
    r = np.linalg.norm(pos, axis=1)
    ce = np.full_like(r, c)
    if wind is not None:
        n = -pos / r[:, None]
        ce = c + wind[0] * n[:, 0] + wind[1] * n[:, 1]
    th = te + r / ce
    ratio = np.gradient(te) / np.gradient(th)
    f = f0 * ratio if drift is None else drift(te) * ratio
    return th, f, r


def reference(te, pos, c):
    r = np.linalg.norm(pos, axis=1)
    k = int(np.argmin(r))
    vel = np.gradient(pos, te, axis=0)
    return dict(f0=np.nan, v=float(np.linalg.norm(vel[k])), R=float(r[k]), tau=float(te[k]),
                t_heard=float(te[k] + r[k] / c))


def at(t, th, f):
    order = np.argsort(th)
    return np.interp(t, th[order], f[order], left=np.nan, right=np.nan)


def fit(t, f, c=C15):
    ok = np.isfinite(f)
    return ls.fit(t[ok], f[ok], c=c)


def halves(t, f, full, c=C15):
    """Approach and recede halves, split at the full fit's tau. "fixed": tau and s held at the full fit, so
    each half gives its own alpha and beta, hence f0 and v (a straight pass gives the same from both);
    "free": all four parameters fitted per half."""
    ok = np.isfinite(f)
    t, f = t[ok], f[ok]
    out = {}
    for name, m in (("approach", t < full["tau"]), ("recede", t > full["tau"])):
        if m.sum() < 12:
            out[name] = out[f"{name}_free"] = None
            continue
        al, be, _ = ls._ab(t[m], f[m], np.ones(m.sum()), full["tau"], full["s"])
        f0, v, R = ls.physical(al, be, full["s"], full["tau"], c)
        out[name] = dict(f0=float(f0), v=float(v), R=float(R), tau=full["tau"])
        out[f"{name}_free"] = ls.fit(t[m], f[m], c=c)
    return out


def block_noise(res, n, dt, rng):
    L = max(2, int(round(BLOCK_S / dt)))
    starts = rng.integers(0, len(res), size=int(np.ceil(n / L)))
    idx = (starts[:, None] + np.arange(L)[None, :]) % len(res)
    return res[idx.ravel()[:n]]


def pick(d):
    return {k: d[k] for k in PARAMS} if d else {k: np.nan for k in PARAMS}


def main(run: Path):
    rows = {r["id"]: r for r in csv.DictReader(open(AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(AUDIT / "sites.json"))["sites"]}
    flagged = {k for k, r in rows.items() if 100 * float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) >= 1.6}
    N = geoid(sites["main"]["lat"], sites["main"]["lon"])
    rng = np.random.default_rng(20261104)
    out_fits, out_pert, out_half, out_noise = [], [], [], []
    for p in audit.load_passes():
        a = rows[p["id"]]; site = sites[a["site"]]
        shift, f0s = float(a["shift_15C"]), float(a["f0_15C"])
        t = p["ridge"][:, 0] - shift
        fD = p["ridge"][:, 1]
        te, pos = trajectory(p, site)
        ref = reference(te, pos, C15); ref["f0"] = f0s
        th, g, _ = heard(te, pos, C15)
        fA = f0s * at(t, th, g)
        fC = ls.model(t, f0s, ref["v"], ref["R"], ref["tau"], C15)
        grp = "flagged" if p["id"] in flagged else "primary"
        base = dict(id=p["id"], group=grp, category=p["cat"])
        fits = {"C": fit(t, fC), "A": fit(t, fA), "D": fit(t, fD)}
        # noise: ridge residuals about A, less their 5 s running median, block-bootstrapped
        ok = np.isfinite(fA)
        res = (fD - fA)[ok]
        dt = float(np.median(np.diff(t)))
        k = max(3, int(round(SLOW_S / dt)) | 1)
        fast = res - ss.medfilt(res, k)
        out_noise.append(dict(**base, sigma_mad=float(1.4826 * np.median(np.abs(fast - np.median(fast)))),
                              rho1=float(np.corrcoef(fast[:-1], fast[1:])[0, 1]), slow_rms=float(np.sqrt(np.mean((res - fast) ** 2))),
                              dt=dt, n=int(ok.sum())))
        B, Cn, Bh = [], [], []
        for _ in range(N_BOOT):
            e = block_noise(fast, len(t), dt, rng)
            fb = fit(t, fA + e); B.append(pick(fb))
            Cn.append(pick(fit(t, fC + e)))
            h = halves(t, fA + e, fb)
            Bh.append({s: pick(h[s]) for s in h})
        sd = {q: float(np.nanstd([b[q] for b in B], ddof=1)) for q in PARAMS}
        n_failed = int(sum(not np.isfinite(b["R"]) for b in B))
        e0 = block_noise(fast, len(t), dt, np.random.default_rng(1))
        covs = {}
        for name, ff, fd in (("A+noise", fA + e0, None), ("D", fD, fits["D"])):
            fd = fd or fit(t, ff)
            okf = np.isfinite(ff)
            cl, hac = ls.covariances(t[okf], ff[okf], fd, C15, lags=8)
            covs[name] = dict(classical=np.sqrt(np.diag(cl)).tolist(), hac8=np.sqrt(np.diag(hac)).tolist())
        for kind in ("C", "A", "D"):
            out_fits.append(dict(**base, kind=kind, **{f"ref_{q}": ref[q] for q in PARAMS}, **pick(fits[kind]),
                                 rms=fits[kind]["rms"], cond=fits[kind]["cond"], at_bound=fits[kind]["at_bound"]))
        for kind, reps in (("B", B), ("C+noise", Cn)):
            out_fits.append(dict(**base, kind=kind, **{f"ref_{q}": ref[q] for q in PARAMS},
                                 **{q: float(np.nanmean([r[q] for r in reps])) for q in PARAMS},
                                 **{f"sd_{q}": float(np.nanstd([r[q] for r in reps], ddof=1)) for q in PARAMS},
                                 n_failed=int(sum(not np.isfinite(r["R"]) for r in reps))))
        out_fits[-2].update({f"cov_{n}_{w}_{q}": covs[n][w][i] for n in covs for w in covs[n] for i, q in enumerate(PARAMS)})
        # halves
        for kind, ff in (("A", fA), ("D", fD)):
            h = halves(t, ff, fits[kind])
            row = dict(**base, kind=kind)
            for s in h:
                row.update({f"{s}_{q}": pick(h[s])[q] for q in PARAMS})
            for sfx in ("", "_free"):
                row.update({f"sd_diff{sfx}_{q}": float(np.nanstd([b[f"recede{sfx}"][q] - b[f"approach{sfx}"][q] for b in Bh], ddof=1))
                            for q in ("f0", "v")})
            out_half.append(row)
        # perturbations of A
        tmid = 0.5 * (t[0] + t[-1]); span = t[-1] - t[0]
        T, tT = metar_temp(ref["tau"])
        h_ray = 0.5 * (site["alt_msl"] + float(np.interp(ref["tau"], p["track"][:, 0], p["track"][:, 3])))
        wind = sounding_wind(ref["tau"], h_ray)
        variants = [(f"drift_{d:+.3f}", dict(drift=lambda x, d=d: f0s * (1 + d * (x - tmid) / span)), {}) for d in DRIFTS]
        variants += [("sound_speed_metar", dict(c=speed_of_sound(T)), dict(T=T, age=tT)),
                     ("wind_sounding", dict(wind=wind[:2]), dict(u=wind[0], v=wind[1], age=wind[2], h=h_ray)),
                     ("interp_linear", dict(interp="linear"), {}), ("interp_spline", dict(interp="spline"), {}),
                     ("track_height_plus_N", dict(alt_shift=N), dict(N=N)),
                     ("recorder_terrarium_1p5", dict(site_alt=site["ground_terrarium_m"] + 1.5), {}),
                     ("window_150", dict(window=150.0), {})]
        fA_fit = fits["A"]
        for name, kw, info in variants:
            te2, pos2 = trajectory(p, site, interp=kw.get("interp", "pchip"), alt_shift=kw.get("alt_shift", 0.0),
                                   site_alt=kw.get("site_alt"))
            c2 = kw.get("c", C15)
            ref2 = reference(te2, pos2, c2); ref2["f0"] = f0s
            th2, g2, _ = heard(te2, pos2, c2, wind=kw.get("wind"), f0=f0s, drift=kw.get("drift"))
            if "window" in kw:
                tt = np.arange(ref["tau"] - kw["window"], ref["tau"] + kw["window"], dt)
            else:
                tt = t
            f2 = at(tt, th2, g2)
            r2 = fit(tt, f2)
            row = dict(**base, variant=name, **{f"info_{k}": v for k, v in info.items()})
            for q in PARAMS:
                row[f"fit_{q}"] = r2[q]; row[f"ref_{q}"] = ref2[q]
                row[f"dfit_{q}"] = r2[q] - fA_fit[q]
                row[f"dref_{q}"] = ref2[q] - ref[q]
                row[f"ratio_{q}"] = abs(r2[q] - fA_fit[q]) / sd[q] if sd[q] > 0 else np.nan
                row[f"err_{q}"] = r2[q] - ref2[q]
            out_pert.append(row)
        print(f"{p['id']:12s} {grp:8s} failed {n_failed:3d} A: R {100 * (fA_fit['R'] / ref['R'] - 1):+6.1f} %  v {100 * (fA_fit['v'] / ref['v'] - 1):+6.1f} %  "
              f"f0 {100 * (fA_fit['f0'] / f0s - 1):+5.2f} %  | D: R {100 * (fits['D']['R'] / ref['R'] - 1):+6.1f} %  | sd R {sd['R']:.0f} m", flush=True)
    for name, data in (("fits", out_fits), ("perturbations", out_pert), ("halves", out_half), ("noise", out_noise)):
        keys = sorted({k for r in data for k in r}, key=lambda k: (k not in ("id", "group", "category", "kind", "variant"), k))
        with open(run / f"{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(data)
    json.dump(dict(n_boot=N_BOOT, block_s=BLOCK_S, slow_s=SLOW_S, c15=C15, geoid_N=N, drifts=DRIFTS,
                   flagged=sorted(flagged)), open(run / "settings.json", "w"), indent=1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
