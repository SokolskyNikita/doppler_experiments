"""The numbers behind docs/experiments/2026-11-04-locate.md: Tier 2 of `dopplertrack locate` on the fleet.

usage: locate_tier2.py OFF_RUN ON_RUN > table.md

Each run is a merged bench run folder (silence filter off, then on). Every record is checked against the hash written
beside it before its case's labels are read, as `bench compare` does. For each case and run: the verdict and reason
codes, the true pair's rank among the candidates, the top candidate's and the refined point's distance from the
reference, and each pair rule's top flights (marked when they are the true pair), its search time, and which rule
the record chose."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bench import cases  # noqa: E402
from bench.runner import HASH_FILE  # noqa: E402
from dopplertrack.geo import haversine_m  # noqa: E402
from dopplertrack.result import read_record  # noqa: E402


def rows(run: Path):
    res = json.loads((run / "results.json").read_text())
    for e in res["cases"]:
        cid = e["case"]
        sha = (run / cid / HASH_FILE).read_text().split()[0]
        rec = read_record(run / cid / "result.json", expected_sha256=sha)        # before the labels
        lab = cases.case_labels(cid, e["version"])
        ref, tp = lab["reference"], lab.get("true_pair")
        v = rec["verdict"]
        cands = rec["candidates"]
        rank = next((c["rank"] for c in cands if tp and c["flights"] == list(tp)), None)
        top_km = haversine_m(cands[0]["lat"], cands[0]["lon"], ref["lat"], ref["lon"]) / 1e3 if cands else None
        rf = rec["refined"]
        ref_km = haversine_m(rf["lat"], rf["lon"], ref["lat"], ref["lon"]) / 1e3 if isinstance(rf, dict) and "lat" in rf else None
        rules = {}
        for p in rec.get("pair_rules") or []:
            if isinstance(p, dict):
                rules[p["rule"]] = (p.get("top_flights"), tp is not None and p.get("top_flights") == list(tp), p["wall_s"])
        clock = cands[0]["clock"]["audio_minus_utc_s"] if cands else None
        yield {"case": cid, "status": e["status"], "errors": rec["execution"]["errors"],
               "outcome": v.get("outcome") if isinstance(v, dict) else None,
               "codes": v.get("reason_codes", []) if isinstance(v, dict) else [], "as_expected": e.get("verdict_as_expected"),
               "true_pair": tp, "rank": rank, "n_cands": len(cands), "top_km": top_km, "refined_km": ref_km,
               "rules": rules, "start_utc": -clock if clock is not None else None,
               "reference_start": (cases.latest_case(cid).get("reference_clock_utc") or {}).get("audio_zero_utc_unix_s")}


def km(x):
    return "–" if x is None else f"{x:.2f}"


def main():
    import datetime
    print("| Run | Case | Verdict | Expected | True-pair rank | Top (km) | Refined (km) | top2 pick | comparable pick | top2 / comparable (s) | Start (UTC) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, run in (("off", Path(sys.argv[1])), ("on", Path(sys.argv[2]))):
        for r in rows(run):
            pick = lambda rule: ("**true pair**" if r["rules"][rule][1] else " + ".join(r["rules"][rule][0] or ["–"])) \
                if rule in r["rules"] else "–"                                    # noqa: E731
            t = " / ".join(f"{r['rules'][k][2]:.0f}" for k in ("top2", "comparable") if k in r["rules"]) or "–"
            start = datetime.datetime.fromtimestamp(r["start_utc"], datetime.timezone.utc).strftime("%H:%M:%SZ") \
                if r["start_utc"] else "–"
            verdict = f"{r['outcome']} {' '.join(r['codes'])}" if r["outcome"] else f"error: {r['errors'][:1]}"
            exp = {True: "yes", False: "**no**", None: "–"}[r["as_expected"]]
            print(f"| {name} | {r['case']} | {verdict} | {exp} | {r['rank'] if r['rank'] else ('none' if r['true_pair'] else '–')}"
                  f" of {r['n_cands']} | {km(r['top_km'])} | {km(r['refined_km'])} | {pick('top2')} | {pick('comparable')}"
                  f" | {t} | {start} |")


if __name__ == "__main__":
    main()
