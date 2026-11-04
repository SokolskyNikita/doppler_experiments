"""Stage 3's table from a model_error_alaska.py run: fit_event at each sound-speed setting and the authors' own fits,
against FR24, plus how a change of c moves the fitted speed and slant range (d ln v / d ln c, d ln R / d ln c,
per crossing between two settings, median over crossings).

usage: uv run python tools/experiments/2026-11-04/model_error_alaska_summary.py "$RUN"
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

from dopplertrack.doppler import speed_of_sound

C15 = speed_of_sound(15.0)


def _num(v):
    try:
        return float(v)
    except ValueError:
        return v


def stats(rows, R, v, tau=None):
    e = np.array([R(r) / r["R_fr24"] - 1 for r in rows]); ev = np.array([v(r) / r["v_fr24"] - 1 for r in rows])
    q = np.percentile(e, [25, 50, 75])
    out = dict(n=len(rows), R_median=q[1], R_iqr=(q[0], q[2]), R_abs=float(np.median(np.abs(e))), R_over20=float(np.mean(np.abs(e) > 0.2)),
               v_abs=float(np.median(np.abs(ev))), v_median=float(np.median(ev)))
    if tau:
        out["tau_abs"] = float(np.median([abs(tau(r) - r["t_fr24"]) for r in rows]))
    return out


def main(run: Path):
    if (run / "alaska.jsonl").exists():
        rows = [json.loads(line) for line in open(run / "alaska.jsonl")]
    else:                        # a merged shards.py run: alaska.csv, numbers as text
        rows = [{k: _num(v) for k, v in r.items() if v != ""} for r in csv.DictReader(open(run / "alaska.csv"))]
    c = {"c15": lambda r: C15, "cauth": lambda r: r["c_authors"], "ctemp": lambda r: r["c_temp"]}
    ok = [r for r in rows if all(isinstance(r.get(f"R_{t}"), float) and np.isfinite(r[f"R_{t}"]) for t in c)]
    out_weak = {t: sum(1 for r in rows if f"weak_{t}" in r) for t in c}
    out = {"n_rows": len(rows), "n_all_three": len(ok), "weak": out_weak,
           "errors": {t: sum(1 for r in rows if f"error_{t}" in r) for t in c}}
    for t in c:
        out[t] = stats(ok, lambda r: r[f"R_{t}"], lambda r: r[f"v_{t}"], lambda r: r[f"tau_{t}"])
        out[t]["c_median"] = float(np.median([c[t](r) for r in ok]))
    out["authors"] = stats(ok, lambda r: r["R_authors"], lambda r: r["v_authors"])
    for a, b in (("c15", "ctemp"), ("c15", "cauth"), ("ctemp", "cauth")):
        dc = np.array([np.log(c[b](r) / c[a](r)) for r in ok])
        use = np.abs(dc) > 0.005            # a c change under 0.5 % says nothing about the slope
        for q in ("v", "R"):
            s = np.array([np.log(r[f"{q}_{b}"] / r[f"{q}_{a}"]) for r in ok])[use] / dc[use]
            out[f"dln{q}_dlnc_{a}_{b}"] = dict(n=int(use.sum()), median=float(np.median(s)), iqr=list(np.percentile(s, [25, 75])))
    print(json.dumps(out, indent=1, default=float))
    json.dump(out, open(run / "summary.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
