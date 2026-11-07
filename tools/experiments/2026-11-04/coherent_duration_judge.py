"""Judge coherent_duration.py's gates and test (docs/experiments/designs/2026-11-04-coherent-duration.md), all fixed before
any result was read.

Thresholds: per pass, method and candidate set, 1 false alarm per hour, P = 18/3600 = 1/200 per window, the empirical
1 - P point of the calibration windows' maxima (each the best candidate of the set, clock and pitch); the retune
replaced the Gumbel fit, whose KS on real background was 0.11-0.35.
A trial recovers when the set's winner is the true flight and clears its threshold. L80 is the lowest level at which
the trials recover at least 80 % of the time at that level and at every higher one.

  gate 1 (synthetic, true flight and clock supplied): median over the 8 passes of L80(C1) - L80(C9) within 4.8 +- 1 dB
         and of L80(C3) - L80(C9) within 3.0 +- 1 dB
  gate 2 (the real clips, true flight and clock supplied): median of L80(C9) - L80(C1) within +-1 dB
  test   (19 passes, blind; set A, the real traffic, decides; set B, the 26 other tracks, is reported): C3 or C9 wins
         if its L80 over all trials is at least 3 dB below the better of C1's and T's

usage: coherent_duration_judge.py gates|test RUN [DIR ...]   (units are read from RUN and the DIRs; writes
       RUN/judge-<stage>.json)"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

METHODS = ["C1", "C3", "C9", "T"]
P_WINDOW = 18.0 / 3600.0
BOOT = 1000


def gamma(x, seed):
    """The threshold: the empirical 1 - P point of the calibration maxima (the retune: real background maxima are
    heavier-tailed than a Gumbel), with a bootstrap interval; the Gumbel fit's KS is kept as the diagnostic."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    g = float(np.quantile(x, 1 - P_WINDOW, method="higher"))
    rng = np.random.default_rng(seed)
    boot = [np.quantile(rng.choice(x, len(x)), 1 - P_WINDOW, method="higher") for _ in range(BOOT)]
    loc, scale = stats.gumbel_r.fit(x)
    return {"gamma": g, "gamma_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "estimator": "empirical", "n": int(len(x)),
            "gumbel": {"mu": float(loc), "beta": float(scale),
                       "gamma": float(stats.gumbel_r.ppf(1 - P_WINDOW, loc, scale)),
                       "ks": float(stats.kstest(x, "gumbel_r", (loc, scale)).statistic)}}


def l80(levels, rate):
    """Lowest level with rate >= 0.8 there and at every higher level; None if the top level fails."""
    order = np.argsort(-levels)
    best = None
    for i in order:
        if rate[i] >= 0.8:
            best = float(levels[i])
        else:
            break
    return best


def load(roots, mode, pid, kind):
    out = []
    for r in roots:
        for d in sorted((r / "units").glob(f"{mode}--{pid}--{kind}--*")):
            if (d / "unit.json").exists() and d.name not in {o[0] for o in out}:
                z = np.load(d / "stats.npz")
                out.append((d.name, z["stats"], [str(s) for s in z["sets"]], z["levels"]))
    return out


def judge_mode(roots, mode, pids, set_name=None):
    res = {}
    for k, pid in enumerate(pids):
        cal = load(roots, mode, pid, "cal")
        ev = load(roots, mode, pid, "eval")
        if not cal or not ev:
            res[pid] = {"missing": True}
            continue
        sets, levels = ev[0][2], ev[0][3]
        cols = [i for i, s in enumerate(sets) if s == "true" or set_name is None or s == set_name]
        calmax = np.concatenate([c[1][:, :, cols].max(axis=2) for c in cal])          # (segments, method)
        th = {m: gamma(calmax[:, j], 1000 + 10 * k + j) for j, m in enumerate(METHODS)}
        evs = np.concatenate([e[1] for e in ev])                                       # (windows, method, level, cand)
        sub = evs[..., cols]
        win = np.nanargmax(np.where(np.isfinite(sub), sub, -np.inf), axis=3)           # index within cols
        best = np.nanmax(np.where(np.isfinite(sub), sub, -np.inf), axis=3)
        true_won = win == cols.index(0)
        rows = {}
        for j, m in enumerate(METHODS):
            clear = best[:, j, :] > th[m]["gamma"]
            rec = (true_won[:, j, :] & clear).mean(0)
            wrong = (~true_won[:, j, :] & clear).mean(0)
            rows[m] = {"threshold": th[m], "recovery": rec.tolist(), "wrong_flight_clears": wrong.tolist(),
                       "L80": l80(levels, rec), "trials": int(evs.shape[0])}
        res[pid] = {"levels": levels.tolist(), "candidates": len(cols), **rows}
    return res


def pooled_l80(res, method):
    recs = [np.array(r[method]["recovery"]) * r[method]["trials"] for r in res.values() if "missing" not in r]
    n = sum(r[method]["trials"] for r in res.values() if "missing" not in r)
    levels = np.array(next(r["levels"] for r in res.values() if "missing" not in r))
    rate = np.sum(recs, axis=0) / n
    return l80(levels, rate), rate.tolist()


def main():
    stage, run = sys.argv[1], Path(sys.argv[2])
    roots = [run, *map(Path, sys.argv[3:])]
    plan = json.loads((Path(__file__).with_name("coherent_duration_plan.json")).read_text())
    out = {"stage": stage}
    if stage == "gates":
        for mode in ("synthetic", "assisted"):
            out[mode] = judge_mode(roots, mode, plan["verify"])
        def med(mode, a, b):
            v = [r[a]["L80"] - r[b]["L80"] for r in out[mode].values()
                 if "missing" not in r and r[a]["L80"] is not None and r[b]["L80"] is not None]
            return (float(np.median(v)) if v else None), len(v)
        g1a, n1 = med("synthetic", "C1", "C9")
        g1b, _ = med("synthetic", "C3", "C9")
        g2, n2 = med("assisted", "C9", "C1")
        out["gate1"] = {"C1_minus_C9": g1a, "C3_minus_C9": g1b, "passes_judged": n1,
                        "pass": g1a is not None and g1b is not None and abs(g1a - 4.8) <= 1 and abs(g1b - 3.0) <= 1}
        out["gate2"] = {"C9_minus_C1": g2, "passes_judged": n2, "pass": g2 is not None and abs(g2) <= 1}
    else:
        for set_name in ("A", "B"):
            res = judge_mode(roots, "blind", plan["test"], set_name)
            pooled = {m: dict(zip(("L80", "recovery"), pooled_l80(res, m))) for m in METHODS}
            base = min(x for x in (pooled["C1"]["L80"], pooled["T"]["L80"]) if x is not None) \
                if any(pooled[m]["L80"] is not None for m in ("C1", "T")) else None
            win = {m: (pooled[m]["L80"] is not None and base is not None and pooled[m]["L80"] <= base - 3)
                   for m in ("C3", "C9")}
            out[f"set_{set_name}"] = {"per_pass": res, "pooled": pooled, "baseline_L80": base, "wins": win}
        out["decision_set"] = "A"
    (run / f"judge-{stage}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k in ("gate1", "gate2")} if stage == "gates" else
                     {s: {"pooled_L80": {m: out[s]["pooled"][m]["L80"] for m in METHODS}, "baseline": out[s]["baseline_L80"],
                          "wins": out[s]["wins"]} for s in ("set_A", "set_B")}, indent=1))


if __name__ == "__main__":
    main()
