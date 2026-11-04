"""Tables for the model-error record from model_error.py's run folder: errors by curve kind, the fit's
spread against the classical and Newey-West covariances, each perturbation's |delta|/SD, the half-fits,
and dopplerprint's slant-range hypothesis. Writes summary.json and prints the tables.

usage: uv run python tools/experiments/2026-11-04/model_error_summary.py "$RUN"
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PARAMS = ("f0", "v", "R", "tau")


def q(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if not len(x):
        return dict(n=0)
    return dict(n=int(len(x)), median=float(np.median(x)), q25=float(np.percentile(x, 25)), q75=float(np.percentile(x, 75)),
                median_abs=float(np.median(np.abs(x))))


def main(run: Path):
    fits = pd.read_csv(run / "fits.csv"); pert = pd.read_csv(run / "perturbations.csv")
    halves = pd.read_csv(run / "halves.csv"); noise = pd.read_csv(run / "noise.csv")
    out = {}
    # errors by kind, in units and % of the reference (tau in s)
    err = {}
    for grp in ("primary", "flagged", "all"):
        g = fits if grp == "all" else fits[fits.group == grp]
        err[grp] = {}
        for kind in ("C", "A", "B", "C+noise", "D"):
            k = g[g.kind == kind]
            err[grp][kind] = {p: dict(units=q(k[p] - k[f"ref_{p}"]),
                                      pct=q(100 * (k[p] / k[f"ref_{p}"] - 1)) if p != "tau" else None) for p in PARAMS}
    out["errors"] = err
    # is D inside B's spread? z = (fit(D) - mean(B)) / sd(B)
    B = fits[fits.kind == "B"].set_index("id"); D = fits[fits.kind == "D"].set_index("id")
    out["D_vs_B_z"] = {grp: {p: q(((D[p] - B[p]) / B[f"sd_{p}"])[B.group == grp if grp != "all" else B.index == B.index])
                             for p in PARAMS} for grp in ("primary", "flagged", "all")}
    # covariance: classical and HAC(8) SD against the bootstrap SD
    cov = {}
    for p in PARAMS:
        cov[p] = {f"{n}_{w}": q(B[f"cov_{n}_{w}_{p}"] / B[f"sd_{p}"])
                  for n in ("A+noise", "D") for w in ("classical", "hac8")}
    out["covariance_over_bootstrap_sd"] = cov
    # perturbations
    pr = {}
    for var, g in pert.groupby("variant"):
        pr[var] = {}
        for grp in ("primary", "flagged"):
            k = g[g.group == grp]
            pr[var][grp] = {p: dict(ratio=q(k[f"ratio_{p}"]), n_over_1=int((k[f"ratio_{p}"] > 1).sum()), n=int(len(k)),
                                    dfit=q(k[f"dfit_{p}"]), dref=q(k[f"dref_{p}"]),
                                    dfit_pct=q(100 * k[f"dfit_{p}"] / k[f"ref_{p}"]) if p != "tau" else None,
                                    err_pct=q(100 * k[f"err_{p}"] / k[f"ref_{p}"]) if p != "tau" else None)
                            for p in PARAMS}
            pr[var][grp]["enters"] = any(pr[var]["primary"][p]["ratio"].get("median", 0) > 1 for p in PARAMS) if grp == "primary" else None
    out["perturbations"] = pr
    # halves: recede minus approach, against the bootstrap spread of that difference
    hv = {}
    for kind in ("A", "D"):
        for grp in ("primary", "flagged"):
            k = halves[(halves.kind == kind) & (halves.group == grp)]
            hv[f"{kind}_{grp}"] = {f"{p}{sfx}": dict(diff_pct=q(100 * (k[f"recede{sfx}_{p}"] / k[f"approach{sfx}_{p}"] - 1)),
                                                     z=q((k[f"recede{sfx}_{p}"] - k[f"approach{sfx}_{p}"]) / k[f"sd_diff{sfx}_{p}"]))
                                   for p in ("f0", "v") for sfx in ("", "_free")}
    out["halves"] = hv
    # dopplerprint: straight-pass fit to the noise-free trajectory curve misses R by a median 14 %
    A = fits[fits.kind == "A"]
    w150 = pert[pert.variant == "window_150"]
    out["dopplerprint"] = dict(ridge_span=q(100 * (A.R / A.ref_R - 1)),
                               window_150=q(100 * (w150.fit_R / w150.ref_R - 1)))
    out["noise"] = {c: q(noise[c]) for c in ("sigma_mad", "rho1", "slow_rms", "dt")}
    out["bootstrap_failures"] = {k: int(fits[fits.kind == k].n_failed.sum()) for k in ("B", "C+noise")}
    json.dump(out, open(run / "summary.json", "w"), indent=1)
    print(json.dumps(out, indent=1)[:20000])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
