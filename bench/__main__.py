"""uv run python -m bench {validate,build,run,merge,inputs,tier1,compare}"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import cases, runner


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="check bench/cases.json against its schema and bench/manifest.json")
    b = sub.add_parser("build", help="make missing derived files from raw/ with their recipes, and check every hash")
    b.add_argument("case", nargs="*", help="case ids (default: all)")
    b.add_argument("--check", action="store_true", help="only check that each derived file exists and matches its hash")
    r = sub.add_parser("run", help="run cases blind, write result.json + hash, then score them into results.json")
    r.add_argument("case", nargs="*", help="case ids (default: all)")
    r.add_argument("--tier", default="t2", help="tier label for the run folder name (default: t2)")
    r.add_argument("--run-dir", type=Path, help="an empty folder made by tools/data/new_run.py (default: make one)")
    r.add_argument("--revision", help="run this commit-ish through its own CLI in its own environment, e.g. a16b700 "
                   "(default: this checkout, in-process)")
    r.add_argument("--profile", choices=sorted(runner.PROFILES), default="saved-fit",
                   help="saved-fit: the case's committed fits; raw-audio: detect's top two by score, earlier first")
    r.add_argument("--parallel", type=int, default=1, help="cases to run at once, each in its own process (default: 1)")
    r.add_argument("--shard", metavar="I/N", help="run only every N-th case from the I-th (1-based, sorted ids), so N "
                   "boxes split one run; `bench merge` puts the shards together")
    r.add_argument("--resume", action="store_true", help="continue the stopped run in --run-dir: cases with an "
                   "entry.json are kept, the rest run (same clean commit and settings only)")
    r.add_argument("--search-param", action="append", default=[], metavar="KEY=VALUE",
                   help="override a search setting for this run (repeatable); VALUE is JSON or a string. tol_s, v_tol, "
                   "d_tol, silence_d_m and harmonics replace the case's; any other key is passed to run_search")
    rc = sub.add_parser("run-case", help="(used by run --parallel) one case into an existing run folder")
    rc.add_argument("case"); rc.add_argument("--run-dir", type=Path, required=True)
    rc.add_argument("--revision"); rc.add_argument("--profile", choices=sorted(runner.PROFILES), default="saved-fit")
    rc.add_argument("--code-json", required=True, help="the code revision the parent read when the run started")
    rc.add_argument("--overrides-json", default="{}")
    t1 = sub.add_parser("tier1", help="Tier 1: detect and fits against the blind labels, and the known point")
    t1.add_argument("--set", action="append", choices=("development", "calibration", "evaluation"),
                    help="span sets to run (default: development only; calibration is for Phase 4)")
    t1.add_argument("--run-dir", type=Path, help="an empty folder made by tools/data/new_run.py (default: make one)")
    t1.add_argument("--workers", type=int, help="processes for detect (default: the performance cores)")
    t1.add_argument("--build", action="store_true", help="only make the spans' missing derived files and check hashes")
    t1.add_argument("--only", action="append", metavar="UNIT", help="run only this span or known-point case blind "
                    "(repeatable); see --shard")
    t1.add_argument("--shard", metavar="I/N", help="run every N-th unit from the I-th (spans, then known-point cases) "
                    "blind, without comparing, so N boxes split Tier 1; then bench merge and one --resume compares")
    t1.add_argument("--resume", action="store_true", help="keep the blind records in --run-dir that match their "
                    "hashes, run the rest, then compare")
    t1.add_argument("--no-compare", action="store_true", help="write the blind records only")
    m = sub.add_parser("merge", help="put shard or stopped runs of one commit and profile together in one run folder")
    m.add_argument("out", type=Path, help="a new run folder (tools/data/new_run.py), or one of the sources")
    m.add_argument("sources", type=Path, nargs="+")
    i = sub.add_parser("inputs", help="list the files a run needs (data root, repo, cache), as JSON, for a cloud box")
    i.add_argument("case", nargs="*", help="case ids (default: every case the profile runs)")
    i.add_argument("--profile", choices=sorted(runner.PROFILES), default="saved-fit")
    i.add_argument("--tier1", action="store_true", help="Tier 1's spans and known-point cases instead of cases")
    i.add_argument("--set", action="append", choices=("development", "calibration", "evaluation"))
    c = sub.add_parser("compare", help="print the difference between two benchmark runs")
    c.add_argument("a", type=Path); c.add_argument("b", type=Path)
    a = ap.parse_args(argv)

    if a.cmd == "validate":
        try:
            doc = cases.load_cases()
        except cases.CaseError as exc:
            sys.exit("\n".join(exc.problems))
        print(f"{len(doc['cases'])} cases valid")
    elif a.cmd == "build":
        bad = []
        # checking covers every case; building, only the runnable ones unless named
        for cid in a.case or cases.case_ids(runnable_only=not a.check):
            bad += cases.build(cases.latest_case(cid), check_only=a.check)
        if bad:
            sys.exit("\n".join(bad))
        print("every derived file matches its recorded hash")
    elif a.cmd == "run":
        run_dir = runner.run_bench(a.case or cases.case_ids(profile=a.profile), tier=a.tier, run_dir=a.run_dir,
                                   revision=a.revision, profile=a.profile, parallel=a.parallel,
                                   overrides=runner.parse_overrides(a.search_param), shard=a.shard,
                                   resume=a.resume)
        print(run_dir)
    elif a.cmd == "merge":
        runner.merge_runs(a.out, a.sources)
    elif a.cmd == "inputs":
        import json
        from . import inputs
        doc = (inputs.tier1_inputs(tuple(a.set or ["development"])) if a.tier1 else
               inputs.run_inputs(a.case or cases.case_ids(profile=a.profile), a.profile))
        print(json.dumps(doc, indent=1))
    elif a.cmd == "run-case":
        import json
        code, execute = runner._executor(a.revision, a.profile, print, code=json.loads(a.code_json),
                                         overrides=json.loads(a.overrides_json))
        runner.run_one(a.case, a.run_dir, execute, code)
    elif a.cmd == "tier1":
        from . import tier1
        if a.build:
            bad = tier1.build_spans(tuple(a.set or ["development"]))
            sys.exit("\n".join(bad) if bad else 0)
        sets = tuple(a.set or ["development"])
        only = runner.shard_of(tier1.unit_ids(sets), a.shard) if a.shard else a.only
        print(tier1.run_tier1(sets, run_dir=a.run_dir, workers=a.workers, only=only, resume=a.resume,
                              compare=not (a.no_compare or a.shard)))
    elif a.cmd == "compare":
        print(runner.compare_runs(a.a, a.b))


if __name__ == "__main__":
    main()
