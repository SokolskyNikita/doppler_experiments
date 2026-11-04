"""Cramer-Rao bound for (f0, v, R, tau) of the ideal straight-pass curve (Kay I ch. 3: for Gaussian noise
of covariance Sigma, I = J' Sigma^-1 J and the bound is I^-1), with J the numerical Jacobian of
straight_pass_ls.model at the pass's own parameters.

Two noise structures:
  package  the package's grid (2.048 s Hann, 0.25 s hop) over the same span, sigma = 0.45 % of f0 (the
           measured error of tracks.ridge). PROVISIONAL: the frame correlation is modelled, not measured.
           c(r) is the Hann window's own autocorrelation at multiples of the hop (Harris 1978 eq. 17,
           every lag: 1, 0.906, 0.672, 0.400, 0.183, 0.058, 0.010, 0.0005, 0), the correlation of the
           complex transform coefficients; a frequency estimate from their magnitudes correlates to first
           order as c(r)^2. Both Toeplitz matrices are positive semi-definite (a truncation to lags 0-4
           isn't: smallest eigenvalue -0.095). package_c2 is the model, package_c the conservative bound,
           and package_indep the independent form over the c^2 sum (3.94) as a check
  ridge    Livermore only: the published ridge's own sample times, with sigma and the autocorrelation
           (lags up to 2 s, Bartlett-tapered) of that pass's residuals about the trajectory curve, less
           their 5 s running median: the same noise model_error.py bootstraps, so this bound is the one
           to set beside the bootstrap SD of curve C+noise

Each bound is given in units, as a percentage of the parameter, and as position errors: the slant range
(metres across the track, a circle about it), the ground range from the track (R/L times the slant-range
bound, L the horizontal distance at CPA, from the ADS-B height above the microphone), and v times the tau
bound (along the track, which the straight-pass fit only fixes when the clock is known).

Run from the repo root:  uv run python tools/experiments/2026-11-04/crb.py "$RUN" [MODEL_ERROR_RUN]
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import scipy.linalg as sl
import scipy.signal as ss

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("model_error", HERE / "model_error.py")
me = importlib.util.module_from_spec(spec); spec.loader.exec_module(me)
ls = me.ls
C = me.C15
_W = ss.get_window("hann", 8192)
HANN_C = np.array([np.dot(_W[:len(_W) - r * 1000], _W[r * 1000:]) / np.dot(_W, _W) for r in range(9)])
N_EFF = float((HANN_C ** 2)[0] + 2 * (HANN_C ** 2)[1:].sum())     # 3.94 frames per independent sample
RIDGE_SIGMA_PCT = 0.45
PARAMS = ("f0", "v", "R", "tau")
# the four development events: true slant range and speed at the true point (timing-conventions record),
# the fitted f0 (event 2 of Oyster Bay at its trajectory-matched 126 Hz, PLAN 6.1), and the fit window
# relative to the emission CPA
DEV = [("oyster_bay_ev1_a1dfeb", 112.6, 136.8, 6090.0, -47.0, 63.0),
       ("oyster_bay_ev2_ace391", 126.0, 103.5, 3638.0, -36.5, 73.5),
       ("eagle_cam_ev1_a2baea", 108.1, 99.4, 2536.0, -123.7, 116.3),
       ("eagle_cam_ev2_a336e4", 133.2, 102.8, 5986.0, -119.3, 120.7)]


def jacobian(t, p):
    h = np.array([1e-5 * p[0], 1e-4 * p[1], 1e-4 * p[2], 1e-3])
    return np.stack([(ls.model(t, *(p + h[k] * np.eye(4)[k]), C) - ls.model(t, *(p - h[k] * np.eye(4)[k]), C)) / (2 * h[k])
                     for k in range(4)], axis=1)


def bound(t, p, sigma, rho):
    J = jacobian(t, p)
    col = np.zeros(len(t)); col[:len(rho)] = rho[:len(t)]
    S = sigma ** 2 * sl.toeplitz(col)
    I = J.T @ sl.solve(S, J, assume_a="sym")
    return np.sqrt(np.diag(np.linalg.inv(I)))


def bound_indep(t, p, sigma, factor):
    J = jacobian(t, p)
    return np.sqrt(np.diag(np.linalg.inv(J.T @ J / sigma ** 2 / factor)))


def describe(name, group, p, sd, H=None, extra=None):
    f0, v, R, tau = p
    L = np.sqrt(max(R * R - H * H, 1.0)) if H is not None else np.nan
    row = dict(id=name, group=group, f0=f0, v=v, R=R, H=H if H is not None else np.nan, L=L)
    for kind, s in sd.items():
        for q, x, ref in zip(PARAMS, s, p):
            row[f"{kind}_{q}"] = float(x)
            if q != "tau":
                row[f"{kind}_{q}_pct"] = float(100 * x / ref)
        row[f"{kind}_ground_m"] = float(R / L * s[2]) if np.isfinite(L) else np.nan
        row[f"{kind}_along_m"] = float(v * s[3])
    row.update(extra or {})
    return row


def main(run: Path, me_run: Path | None):
    rows_a = {r["id"]: r for r in csv.DictReader(open(me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(me.AUDIT / "sites.json"))["sites"]}
    flagged = {k for k, r in rows_a.items() if 100 * float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) >= 1.6}
    out = []
    for p in me.audit.load_passes():
        a = rows_a[p["id"]]; site = sites[a["site"]]
        t = p["ridge"][:, 0] - float(a["shift_15C"])
        te, pos = me.trajectory(p, site)
        ref = me.reference(te, pos, C)
        par = np.array([float(a["f0_15C"]), ref["v"], ref["R"], ref["tau"]])
        H = float(pos[int(np.argmin(np.linalg.norm(pos, axis=1))), 2])
        th, g, _ = me.heard(te, pos, C)
        res = p["ridge"][:, 1] - par[0] * me.at(t, th, g)
        ok = np.isfinite(res); res = res[ok]
        dt = float(np.median(np.diff(t)))
        fast = res - ss.medfilt(res, max(3, int(round(me.SLOW_S / dt)) | 1))
        L = max(1, int(round(me.BLOCK_S / dt)))
        ac = np.array([np.corrcoef(fast[:-k], fast[k:])[0, 1] if k else 1.0 for k in range(L + 1)])
        ac *= 1 - np.arange(L + 1) / (L + 1)           # Bartlett taper keeps the Toeplitz matrix positive definite
        tg = np.arange(t[0], t[-1], 0.25)
        sig_pkg = RIDGE_SIGMA_PCT / 100 * par[0]
        sd = dict(package_c2=bound(tg, par, sig_pkg, HANN_C ** 2), package_c=bound(tg, par, sig_pkg, HANN_C),
                  package_indep=bound_indep(tg, par, sig_pkg, N_EFF), ridge=bound(t[ok], par, float(np.std(fast)), ac))
        out.append(describe(p["id"], "flagged" if p["id"] in flagged else "primary", par, sd, H,
                            dict(ridge_sigma=float(np.std(fast)), ridge_rho1=float(ac[1] / (1 - 1 / (L + 1))), span_s=float(t[-1] - t[0]),
                                 tau_in_span=float((ref["tau"] - t[0]) / (t[-1] - t[0])))))
    for name, f0, v, R, a, b in DEV:
        tg = np.arange(a, b, 0.25)
        par = np.array([f0, v, R, 0.0])
        sig = RIDGE_SIGMA_PCT / 100 * f0
        out.append(describe(name, "development", par, dict(package_c2=bound(tg, par, sig, HANN_C ** 2),
                                                           package_c=bound(tg, par, sig, HANN_C),
                                                           package_indep=bound_indep(tg, par, sig, N_EFF)),
                            None, dict(span_s=b - a, tau_in_span=-a / (b - a))))
    if me_run is not None:          # the bootstrap SDs of curves C+noise and B from model_error.py
        fits = {(r["id"], r["kind"]): r for r in csv.DictReader(open(me_run / "fits.csv"))}
        for row in out:
            for kind in ("C+noise", "B"):
                f = fits.get((row["id"], kind))
                if f:
                    for q in PARAMS:
                        row[f"boot_{kind}_{q}"] = float(f[f"sd_{q}"])
                        row[f"boot_{kind}_over_ridge_{q}"] = float(f[f"sd_{q}"]) / row[f"ridge_{q}"]
    keys = list(dict.fromkeys(k for r in out for k in r))
    with open(run / "crb.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(out)
    summ = {}
    for grp in ("primary", "flagged", "development"):
        g = [r for r in out if r["group"] == grp]
        summ[grp] = {k: dict(median=float(np.nanmedian([r[k] for r in g])), q25=float(np.nanpercentile([r[k] for r in g], 25)),
                             q75=float(np.nanpercentile([r[k] for r in g], 75)), max=float(np.nanmax([r[k] for r in g])))
                     for k in keys if k not in ("id", "group") and all(k in r for r in g)}
    json.dump(dict(hann_c=HANN_C.tolist(), n_eff=N_EFF, ridge_sigma_pct=RIDGE_SIGMA_PCT, provisional="package_*", summary=summ),
              open(run / "crb_summary.json", "w"), indent=1)
    for r in out:
        print(f"{r['id']:24s} {r['group']:11s} R {r['R']:6.0f} m  pkg c2..c: R {r['package_c2_R_pct']:5.1f}..{r['package_c_R_pct']:5.1f} %  "
              f"ground {r['package_c2_ground_m']:6.0f} m  v {r['package_c2_v_pct']:4.1f} %  f0 {r['package_c2_f0_pct']:.2f} %  tau {r['package_c2_tau']:.2f} s"
              + (f"  | ridge: R {r['ridge_R_pct']:5.1f} %  boot C+n/ridge R {r.get('boot_C+noise_over_ridge_R', float('nan')):.2f}" if "ridge_R_pct" in r else ""))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
