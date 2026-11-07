"""The "located" verdict's null of the maximum, saved-fit arm (docs/experiments/designs/2026-11-04-verdict-null.md).

For each case run under the saved-fit profile, one search per day: the case's committed fits, box, grid and gates
with run_search(comparable=True), against the flight data of each null day verdict_null_days.py cut for its box,
and once against its own day. The fits are on the audio's own timeline and the search finds the clock, so another
day's flights need no time shift. Each search is a unit of tools/data/shards.py.

The merge, per case: the null days' maximum Z (the top candidate's score) is fitted with a Gumbel distribution;
gamma is its 1 % point, with a bootstrap interval over days and the probability plot's points. The case's own day
is then split into distinct modes (farther apart than RESOLUTION_M, or clocks more than CLOCK_RES_S apart), and the
verdict is "located" when exactly one mode clears gamma, else "ambiguous" with competing_mode or
below_null_threshold. verdicts.json is written and hashed before any label is read; reveal.json comes after.
Matched-flight count m is 2 throughout this arm (no extras), so kappa doesn't enter yet.

gumbel(x, seed) fits one m's null maxima; its keys follow result schema v3's verdict.null.

usage, from the repo root:
  verdict_null.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs] [--workers N]"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "data"))
import shards                                                      # noqa: E402
from bench import cases, runner                                    # noqa: E402
from dopplertrack.parallel import resolve_jobs                     # noqa: E402
from dopplertrack.result import read_record, sha256_bytes, write_record   # noqa: E402

PLAN = Path(__file__).with_name("verdict_null_days.json")
CASES = ["oyster-bay", "oyster-bay-hp150-aac32k", "eagle-cam-clip-18000s", "oyster-bay-moved-wsw150",
         "oyster-bay-moved-north150"]
P_FA = 0.01
RESOLUTION_M = 2000.0        # the locate record's 2 km
CLOCK_RES_S = 15.0           # the extra-flyover gate: clocks closer than this aren't told apart
BOOT = 1000


def box_name(case: dict) -> str:
    d = next(d for d in case["derived"] if d["path"] == case["flight_data"]["traces"])
    return next(a for a in d["recipe"][0] if "=" in a and not a.startswith("{")).split("=")[0]


def variants(plan: dict) -> tuple[list[dict], dict]:
    out, meta = [], {}
    for cid in CASES:
        base = cases.latest_case(cid)
        g = next(g for g in plan["groups"] if base["flight_data"]["date"] == g["centre"])
        name = box_name(base)
        for day in ["own", *g["days"]]:
            v = json.loads(json.dumps(base))
            vid = f"{cid}--{day}"
            v.update(id=vid, version=1)
            if day != "own":
                v["flight_data"] = {**v["flight_data"], "traces": f"derived/traces/{day}/{name}.npz", "date": day}
                v["derived"] = [d for d in v["derived"] if "traces" not in d["path"]]
            v["search"]["cpa_cache"] = f"cpa/verdict-null/{vid}.npz"
            out.append(v)
            meta[vid] = {"case": cid, "day": day}
    return out, meta


def one(run: Path, vid: str, workers: int):
    case = cases.blind_case(vid, run / "cases.json")
    out = run / "units" / vid
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "run.log", "w") as fh:
        record = runner.execute_case(case, out, log=lambda m: print(m, file=fh, flush=True), code=CODE,
                                     overrides={"workers": workers, "comparable": True})
    sha = write_record(out / "result.json", record)
    (out / runner.HASH_FILE).write_text(f"{sha}  result.json\n")


def modes(cands: list[dict]) -> list[dict]:
    """Candidates (best row per flight pair, by score) grouped greedily into distinct modes."""
    out: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        for m in out:
            dy = (c["lat"] - m["lat"]) * 111320.0
            dx = (c["lon"] - m["lon"]) * 111320.0 * np.cos(np.radians(m["lat"]))
            if np.hypot(dx, dy) <= RESOLUTION_M and abs(c["clock"]["audio_minus_utc_s"] - m["clock"]) <= CLOCK_RES_S:
                break
        else:
            out.append({"lat": c["lat"], "lon": c["lon"], "clock": c["clock"]["audio_minus_utc_s"],
                        "score": c["score"], "flights": c["flights"]})
    return out


def gumbel(x: np.ndarray, seed: int) -> dict:
    from scipy import stats
    loc, scale = stats.gumbel_r.fit(x)
    g = float(stats.gumbel_r.ppf(1 - P_FA, loc, scale))
    rng = np.random.default_rng(seed)
    boot = [stats.gumbel_r.ppf(1 - P_FA, *stats.gumbel_r.fit(rng.choice(x, len(x)))) for _ in range(BOOT)]
    xs = np.sort(x)
    pp = [[float((i + 0.5) / len(xs)), float(stats.gumbel_r.cdf(v, loc, scale))] for i, v in enumerate(xs)]
    # names as in result schema v3's verdict.null (B, 2026-11-04), for one m
    return {"mu": float(loc), "beta": float(scale), "gamma": g,
            "gamma_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "bootstrap": {"n": BOOT, "seed": seed},
            "fit_check": {"ks": float(stats.kstest(x, "gumbel_r", (loc, scale)).statistic), "n": len(x)},
            "exceedances_at_gamma": int((x > g).sum()), "bound_3_over_B": 3.0 / len(x), "max": float(x.max()), "pp": pp}


def merge(run: Path, folders: dict, meta: dict):
    tops, own = {}, {}
    for vid, d in folders.items():
        rec = read_record(d / "result.json", (d / runner.HASH_FILE).read_text().split()[0])
        c, m = meta[vid]["case"], meta[vid]
        if m["day"] == "own":
            own[c] = rec["candidates"]
        else:
            tops.setdefault(c, []).append(rec["candidates"][0]["score"] if rec["candidates"] else -np.inf)
    verdicts = {}
    for k, c in enumerate(CASES):
        x = np.array([t for t in tops[c] if np.isfinite(t)])
        fit = gumbel(x, 20261104 + k)
        ms = modes(own[c])
        above = [m for m in ms if m["score"] > fit["gamma"]]
        outcome = "located" if len(above) == 1 else "ambiguous"
        codes = [] if outcome == "located" else ["competing_mode" if above else "below_null_threshold"]
        fit["draws"], fit["draws_without_candidate"] = len(tops[c]), len(tops[c]) - len(x)
        verdicts[c] = {"null": fit, "modes": ms[:5],
                       "modes_above_gamma": len(above), "outcome": outcome, "reason_codes": codes,
                       "located_at": above[0] if outcome == "located" else None}
    data = (json.dumps(verdicts, indent=1, sort_keys=True) + "\n").encode()
    (run / "verdicts.json").write_bytes(data)
    (run / "verdicts.json.sha256").write_text(f"{sha256_bytes(data)}  verdicts.json\n")
    print("verdicts written and hashed; reading labels", flush=True)
    reveal = {}
    for c, v in verdicts.items():
        base = cases.latest_case(c)
        lab = cases.case_labels(c, base["version"])
        r = {"expected": base.get("expected_outcome"), "outcome": v["outcome"], "gamma": v["null"]["gamma"],
             "gamma_ci95": v["null"]["gamma_ci95"], "top_mode_score": v["modes"][0]["score"] if v["modes"] else None}
        if v["located_at"] and lab.get("reference"):
            m, ref = v["located_at"], lab["reference"]
            dy = (m["lat"] - ref["lat"]) * 111320.0
            dx = (m["lon"] - ref["lon"]) * 111320.0 * np.cos(np.radians(ref["lat"]))
            r.update(error_m=float(np.hypot(dx, dy)), true_pair=sorted(m["flights"]) == sorted(lab.get("true_pair", [])))
        r["calibrated_case"] = ((r["outcome"] == "located" and r.get("true_pair") and r.get("error_m", 1e9) <= RESOLUTION_M)
                                if base.get("expected_outcome", "").startswith("located") else r["outcome"] != "located")
        reveal[c] = r
        print(c, json.dumps(r), flush=True)
    (run / "reveal.json").write_text(json.dumps(reveal, indent=1, sort_keys=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--workers", type=int, help="run_search's pool (default $DOPPLERTRACK_JOBS, else the cores)")
    a = ap.parse_args()
    plan = json.loads(PLAN.read_text())
    vs, meta = variants(plan)
    if a.inputs:
        # the cases' own inputs come with --case; the null days' cuts are listed here
        shards.print_inputs(CASES, sorted({v["flight_data"]["traces"] for v in vs} - {cases.latest_case(c)["flight_data"]["traces"]
                                                                                    for c in CASES}), [])
        return
    params = {"cases": CASES, "plan": plan, "p_fa": P_FA, "resolution_m": RESOLUTION_M, "clock_res_s": CLOCK_RES_S}
    run = shards.open_run(a.run, "verdict-null", {"script": "tools/experiments/2026-11-04/verdict_null.py", "params": params,
                                                 "invocation": {"shard": "%d/%d" % a.shard, "resume": [str(r) for r in a.resume],
                                                                "merge": a.merge}})
    (run / "cases.json").write_text(json.dumps({"schema": 1, "cases": vs}, indent=1) + "\n")
    units = shards.Units(run, list(meta), params, a.shard, a.resume)
    if not a.merge:
        workers = resolve_jobs(a.workers)
        for vid in units.todo():          # one search at a time: memory decides
            t0 = time.time()
            try:
                one(run, vid, workers)
                units.finish(vid, {"seconds": round(time.time() - t0)})
                print(f"{vid}: {time.time() - t0:.0f} s", flush=True)
            except Exception as e:        # recorded; the unit stays unfinished and a resume reruns it
                print(f"{vid}: failed: {e!r}", flush=True)
    try:
        folders = units.all()
    except SystemExit as e:
        if a.merge:
            raise
        print(f"this shard is done; not merging yet: {e}", flush=True)
        return
    merge(run, folders, meta)


if __name__ == "__main__":         # run_search may start spawn pools, which re-import this file
    CODE = runner.code_revision()
    main()
