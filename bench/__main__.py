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
        run_dir = runner.run_bench(a.case or cases.case_ids(), tier=a.tier, run_dir=a.run_dir)
        print(run_dir)
    elif a.cmd == "compare":
        print(runner.compare_runs(a.a, a.b))


if __name__ == "__main__":
    main()
