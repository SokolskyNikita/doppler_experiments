"""Is A1 decided, or inside the null's sampling noise? Written before the stage B A1/A3 rerun's result was read.

A1 (docs/experiments/2026-11-04-comparable-score.md): the eagle cam's true pair (detect ranks 2 + 5) is first of
its ten pairs by top Z. Each event's z = (s - median) / sigma uses its null's median and 1.4826 * MAD from n draws,
so Z carries those estimates' sampling error. This redraws them and re-ranks the pairs:
- median ~ Normal(median, 1.2533 sigma / sqrt(n)), sigma ~ sigma * Normal(1, 1.1664 / sqrt(n)), the asymptotic
  errors of a sample median and a normal MAD; one draw per null, shared by every pair whose search used it (a null
  is its seed and f0 sweep);
- each pair's top Z is the best of its top TOP_CANDIDATES candidates, from their event scores;
- 20,000 draws, seeded.

Decision, fixed before the result:
- met: the true pair is first as run, and first in at least 95 % of draws;
- not met: it isn't first as run, and is first in at most 5 % of draws;
- otherwise inside the null's noise at this n. Then the follow-up is the same search at the n that would put the
  observed gap at 2 standard errors (the gap's spread falls as 1 / sqrt(n)), reported here as n_needed.

usage: a1_noise.py RUN [UNIT_FOLDER_ROOT ...]   (RUN holds plan.json; units are looked up in RUN, the others and
the --resume folders RUN's run.json records, so a merged run of shards needs nothing more)
Writes RUN/a1_noise.json and prints it."""
import json
import sys
from pathlib import Path

import numpy as np

CASE, TRUE_EVENTS = "eagle-cam-clip-18000s", [2, 5]
TOP_CANDIDATES = 20
DRAWS = 20_000
SEED = 20261104


def unit(roots: list[Path], vid: str) -> Path:
    for r in roots:
        d = r / "units" / vid
        if (d / "null.json").exists():
            return d
    raise SystemExit(f"no null.json for {vid} in {', '.join(map(str, roots))}")


def main(run: Path, roots: list[Path]):
    plan = json.loads((run / "plan.json").read_text())[CASE]
    pairs, keys = [], {}
    for r in plan:
        d = unit(roots, r["variant"])
        nulls = json.loads((d / "null.json").read_text())
        rec = json.loads((d / "result.json").read_text())
        ids = []
        for k in ("event1", "event2"):
            nl = nulls[k]
            key = json.dumps([nl["seed"], nl.get("f0_sweep")])
            keys.setdefault(key, nl)
            ids.append(list(keys).index(key))
        cand = rec["candidates"][:TOP_CANDIDATES]
        s = np.array([c["event_scores"] for c in cand], float)
        z = np.array([c["score"] for c in cand], float)
        pairs.append({"events": r["events"], "ids": ids, "s": s, "z": z})
    nl = list(keys.values())
    med = np.array([x["median"] for x in nl])
    sig = np.array([x["sigma"] for x in nl])
    n = np.array([x["n"] for x in nl], float)
    # the run's own Z, from the nulls as kept: must match each record's score
    for p in pairs:
        z = (p["s"][:, 0] - med[p["ids"][0]]) / sig[p["ids"][0]] + (p["s"][:, 1] - med[p["ids"][1]]) / sig[p["ids"][1]]
        if not np.allclose(z, p["z"], atol=1e-9):
            raise SystemExit(f"the kept nulls don't reproduce the scores of {p['events']}")
    rng = np.random.default_rng(SEED)
    m_d = med + rng.standard_normal((DRAWS, len(nl))) * 1.2533 * sig / np.sqrt(n)
    s_d = sig * (1 + rng.standard_normal((DRAWS, len(nl))) * 1.1664 / np.sqrt(n))
    top = np.empty((DRAWS, len(pairs)))
    for j, p in enumerate(pairs):
        a, b = p["ids"]
        zz = ((p["s"][None, :, 0] - m_d[:, a, None]) / s_d[:, a, None]
              + (p["s"][None, :, 1] - m_d[:, b, None]) / s_d[:, b, None])
        top[:, j] = zz.max(axis=1)
    t = next(j for j, p in enumerate(pairs) if sorted(p["events"]) == sorted(TRUE_EVENTS))
    as_run = np.array([p["z"].max() for p in pairs])
    others = np.delete(np.arange(len(pairs)), t)
    best_other = others[np.argmax(as_run[others])]
    first_as_run = bool(as_run[t] > as_run[others].max())
    p_first = float(np.mean(top[:, t] > np.delete(top, t, axis=1).max(axis=1)))
    gap = float(as_run[t] - as_run[best_other])
    sd_gap = float(np.std(top[:, t] - top[:, best_other]))
    if first_as_run and p_first >= 0.95:
        decision = "met"
    elif not first_as_run and p_first <= 0.05:
        decision = "not met"
    else:
        decision = "inside the null's noise"
    n_now = int(n.max())
    n_needed = int(np.ceil(n_now * (2 * sd_gap / abs(gap)) ** 2)) if gap else None
    out = {"case": CASE, "true_events": TRUE_EVENTS, "null_n": n_now, "true_pair_first_as_run": first_as_run,
           "true_pair_top_z": float(as_run[t]), "best_other": pairs[best_other]["events"],
           "best_other_top_z": float(as_run[best_other]), "gap": gap, "gap_sd": sd_gap,
           "p_true_pair_first": p_first, "decision": decision,
           "n_needed_for_gap_at_2_sd": n_needed if decision == "inside the null's noise" else None,
           "draws": DRAWS, "seed": SEED, "nulls": len(nl)}
    (run / "a1_noise.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


def roots_of(run: Path, extra: list[str]) -> list[Path]:
    info = json.loads((run / "run.json").read_text()) if (run / "run.json").exists() else {}
    resumed = [Path(r) for inv in info.get("invocations", []) for r in inv.get("resume", [])]
    return list(dict.fromkeys([run, *map(Path, extra), *resumed]))


if __name__ == "__main__":
    run = Path(sys.argv[1])
    main(run, roots_of(run, sys.argv[2:]))
