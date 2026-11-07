"""The other-day null for the model-error study's collective find (docs/proposals/2026-11-04-collective-find.md), judged with the
verdict null's machinery (docs/experiments/2026-11-04-verdict-null.md). Written before any draw was read.

Inputs:
- the model-error study's draw units, "<case>--null--<day>/null_draws.npz", in the run folders given. Each holds day, max_S (the
  map's maximum collective Z over the box and clocks), second_S (the best distinct second mode), lat, lon, n_matched
  and clock_audio_minus_utc_s.
- OWN.json: {case: {"max_S", "second_S", "lat", "lon", "clock_audio_minus_utc_s"}}, from the own-day runs at the
  draws' commit.

Per case:
- The estimator is fixed now. verdict_null.gumbel() at P_FA = 0.01, unless its KS statistic exceeds the 5 % point
  1.36/sqrt(n); then the empirical 1 % point (the `higher` quantile) with a bootstrap interval. The Gumbel failed on
  background-audio maxima in the coherence run; it behaved on other-day traffic.
- Verdict: "located" iff the own day's max_S > gamma and its second_S <= gamma; otherwise "ambiguous", with
  `competing_mode` when both clear and `below_null_threshold` when neither does.
- The null block uses result schema v3's names. verdicts.json is written and hashed before any label is read; then
  reveal.json gives each case's expected outcome and, for a located positive, the distance from the reference.

oyster-bay-sources-removed takes oyster-bay's draws (ALIASES): it differs from oyster-bay only in its own day's traces
(the true pair removed), so on another day its search is the same computation (the model-error study, 2026-11-04).

usage: collective_null.py OUT_RUN OWN.json OWN_COMMIT DRAWS_COMMIT DIR [DIR ...]
(the commits are recorded; the model-error study showed 40454ae and 661c10f run the same search)"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
_spec = importlib.util.spec_from_file_location("verdict_null", Path(__file__).with_name("verdict_null.py"))
vn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vn)

P_FA = 0.01
RESOLUTION_M = 2000.0
FIELDS = ["day", "max_S", "second_S", "lat", "lon", "n_matched", "clock_audio_minus_utc_s"]
M = "10"                      # the statistic's m key: k = 10 windows
ALIASES = {"oyster-bay-sources-removed": "oyster-bay"}


def draws(dirs):
    out = {}
    for d in dirs:
        for u in sorted((d / "units").glob("*--null--*")):
            f = u / "null_draws.npz"
            if not f.exists() or not (u / "unit.json").exists():
                continue
            case, _, day = u.name.split("--")
            if day in out.setdefault(case, {}):
                continue
            z = np.load(f)
            out[case][day] = {k: (z[k].item() if z[k].ndim == 0 else z[k].ravel()[0]) for k in FIELDS}
    return out


def null_block(case, rows, own, seed):
    x = np.array([r["max_S"] for r in rows], float)
    ok = np.isfinite(x)
    xs = x[ok]
    g = vn.gumbel(xs, seed)
    crit = 1.36 / np.sqrt(len(xs))
    if g["fit_check"]["ks"] <= crit:
        estimator, gamma, ci = "gumbel", g["gamma"], g["gamma_ci95"]
    else:
        estimator = "empirical"
        gamma = float(np.quantile(xs, 1 - P_FA, method="higher"))
        rng = np.random.default_rng(seed)
        boot = [np.quantile(rng.choice(xs, len(xs)), 1 - P_FA, method="higher") for _ in range(1000)]
        ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    return {"statistic": "collective_Z_max: max over the box and clocks of the summed per-window comparable z, zero floor, k = 10",
            "kind": "other_day_traffic", "p_fa": P_FA, "draws": int(len(x)), "draws_without_candidate": {M: int((~ok).sum())},
            "days_seed": 20261104, "days": [r["day"] for r in rows], "estimator": estimator,
            "gumbel": {M: {"mu": g["mu"], "beta": g["beta"]}}, "gamma": {M: gamma}, "gamma_ci95": {M: ci},
            "bootstrap": g["bootstrap"], "fit_check": {M: {**g["fit_check"], "ks_5pct": float(crit)}},
            "exceedances_at_gamma": {M: int((xs > gamma).sum())},
            "exceedances_at_observed": {M: int((xs >= own["max_S"]).sum())}, "bound_3_over_B": 3.0 / len(xs),
            "kappa": None, "kappa_mdl": None, "day_shift": "none (no clock gate)", "own_day": {"max_S": own["max_S"]}}


def main():
    out, own_path = Path(sys.argv[1]), Path(sys.argv[2])
    own_commit, draws_commit, dirs = sys.argv[3], sys.argv[4], [Path(x) for x in sys.argv[5:]]
    own = json.loads(own_path.read_text())
    alld = draws(dirs)
    for case, src in ALIASES.items():
        if case in own and src in alld and case not in alld:
            alld[case] = alld[src]
    verdicts, arrays = {}, {}
    for k, case in enumerate(sorted(alld)):
        rows = [alld[case][d] for d in sorted(alld[case])]
        if case not in own:
            print(f"{case}: no own-day value; skipped", flush=True)
            continue
        nb = null_block(case, rows, own[case], 20261104 + k)
        o = own[case]
        gam = nb["gamma"][M]
        above = [s for s in (o["max_S"], o.get("second_S")) if s is not None and np.isfinite(s) and s > gam]
        outcome = "located" if len(above) == 1 and o["max_S"] > gam else "ambiguous"
        codes = [] if outcome == "located" else ["competing_mode" if len(above) > 1 else "below_null_threshold"]
        nb["commits"] = {"own_day": own_commit, "draws": draws_commit}
        if case in ALIASES:
            nb["draws_from"] = ALIASES[case]
        verdicts[case] = {"null": nb, "outcome": outcome, "reason_codes": codes,
                          "winner": {"m": int(M), "S_m": o["max_S"], "gamma_m": gam, "margin": o["max_S"] - gam,
                                     "lat": o.get("lat"), "lon": o.get("lon")}}
        for f in FIELDS:
            arrays[f"{case}__{f}"] = np.array([r[f] for r in rows])
    out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "null_draws.npz", **arrays)
    sha = hashlib.sha256((out / "null_draws.npz").read_bytes()).hexdigest()
    for v in verdicts.values():
        v["null"]["draws_file"] = {"path": "null_draws.npz", "sha256": sha}
    data = (json.dumps(verdicts, indent=1, sort_keys=True, default=float) + "\n").encode()
    (out / "verdicts.json").write_bytes(data)
    (out / "verdicts.json.sha256").write_text(f"{hashlib.sha256(data).hexdigest()}  verdicts.json\n")
    print("verdicts written and hashed; reading labels", flush=True)
    from bench import cases
    reveal = {}
    for case, v in verdicts.items():
        base = cases.latest_case(case)
        lab = cases.case_labels(case, base["version"])
        r = {"expected": base.get("expected_outcome"), "outcome": v["outcome"], "reason_codes": v["reason_codes"],
             "own_max_S": v["winner"]["S_m"], "gamma": v["winner"]["gamma_m"], "estimator": v["null"]["estimator"],
             "beaten_by": v["null"]["exceedances_at_observed"][M], "draws": v["null"]["draws"]}
        if v["outcome"] == "located" and lab.get("reference") and v["winner"]["lat"] is not None:
            ref = lab["reference"]
            dy = (v["winner"]["lat"] - ref["lat"]) * 111320.0
            dx = (v["winner"]["lon"] - ref["lon"]) * 111320.0 * np.cos(np.radians(ref["lat"]))
            r["error_m"] = float(np.hypot(dx, dy))
        exp = base.get("expected_outcome") or ""
        r["as_expected"] = ((r["outcome"] == "located" and r.get("error_m", 1e9) <= RESOLUTION_M) if exp == "located"
                            else r["outcome"] != "located" if exp == "not_located" else None)
        reveal[case] = r
        print(case, json.dumps(r, default=float), flush=True)
    (out / "reveal.json").write_text(json.dumps(reveal, indent=1, sort_keys=True, default=float) + "\n")


if __name__ == "__main__":
    main()
