"""uv run python -m bench {validate,build,run,compare}"""
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
    r.add_argument("--search-param", action="append", default=[], metavar="KEY=VALUE",
                   help="override a search setting for this run (repeatable); VALUE is JSON or a string. tol_s, v_tol, "
                   "d_tol, silence_d_m and harmonics replace the case's; any other key is passed to run_search")
    rc = sub.add_parser("run-case", help="(used by run --parallel) one case into an existing run folder")
    rc.add_argument("case"); rc.add_argument("--run-dir", type=Path, required=True)
    rc.add_argument("--revision"); rc.add_argument("--profile", choices=sorted(runner.PROFILES), default="saved-fit")
    rc.add_argument("--code-json", required=True, help="the code revision the parent read when the run started")
    rc.add_argument("--overrides-json", default="{}")
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
        for cid in a.case or cases.case_ids():
            bad += cases.build(cases.blind_case(cid), check_only=a.check)
        if bad:
            sys.exit("\n".join(bad))
        print("every derived file matches its recorded hash")
    elif a.cmd == "run":
        run_dir = runner.run_bench(a.case or cases.case_ids(), tier=a.tier, run_dir=a.run_dir,
                                   revision=a.revision, profile=a.profile, parallel=a.parallel,
                                   overrides=runner.parse_overrides(a.search_param))
        print(run_dir)
    elif a.cmd == "run-case":
        import json
        code, execute = runner._executor(a.revision, a.profile, print, code=json.loads(a.code_json),
                                         overrides=json.loads(a.overrides_json))
        runner.run_one(a.case, a.run_dir, execute, code)
    elif a.cmd == "compare":
        print(runner.compare_runs(a.a, a.b))


if __name__ == "__main__":
    main()
