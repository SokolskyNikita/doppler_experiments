"""uv run python -m bench {validate,build,run,merge,inputs,tier1,report,prepare,compare,study}"""
from __future__ import annotations

import argparse
import os
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
                   help="saved-fit: the case's committed fits; raw-audio: detect's top two by score, earlier first; "
                   "locate: the locate command; collective: detection's windows through the collective search")
    r.add_argument("--unit-wall-s", type=float, metavar="S", help="stop a case still running after S seconds and "
                   "count it incomplete, never a result; every case then runs in its own process")
    r.add_argument("--cases", type=Path, metavar="FILE", help="read the cases from this manifest instead of "
                   "bench/cases.json (a synthetic fixture)")
    r.add_argument("--parallel", type=int, default=1, help="cases to run at once, each in its own process (default: 1)")
    r.add_argument("--shard", metavar="I/N", help="run only every N-th case from the I-th (1-based, sorted ids), so N "
                   "boxes split one run; `bench merge` puts the shards together")
    r.add_argument("--reveal", action="store_true", help="private cases only: write the records in absolute coordinates "
                   "(the owner's choice, for a local look) instead of offsets from the site")
    r.add_argument("--resume", action="store_true", help="continue the stopped run in --run-dir: cases with an "
                   "entry.json are kept, the rest run (same clean commit and settings only)")
    r.add_argument("--weather", action="store_true", help="apply each case's station temperature (its weather block): "
                   "the fits at the ground temperature, each flight at its own mid-height speed. Off by default: the 15 C "
                   "path, the case's reading recorded but not used")
    r.add_argument("--search-param", action="append", default=[], metavar="KEY=VALUE",
                   help="override a grid_pair parameter for this run (repeatable; methods/grid_pair/parameters.py), as "
                   "stage.field or a field name one stage alone has, after the profile's and the case's; VALUE is JSON "
                   "or a string. Unknown names are refused. Under --profile locate, clock_gate and the private cases' "
                   "box_m, box_offset_m, spacing_m, traces and extraction_box change the case instead")
    rc = sub.add_parser("run-case", help="(used by run --parallel) one case into an existing run folder")
    rc.add_argument("case"); rc.add_argument("--run-dir", type=Path, required=True)
    rc.add_argument("--revision"); rc.add_argument("--profile", choices=sorted(runner.PROFILES), default="saved-fit")
    rc.add_argument("--code-json", required=True, help="the code revision the parent read when the run started")
    rc.add_argument("--overrides-json", default="{}")
    rc.add_argument("--cases", type=Path)
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
    rp = sub.add_parser("report", help="the Phase 5 HTML page of each case's result.json, and an index.html, in a new "
                        "run folder (or --out)")
    rp.add_argument("run_dir", type=Path)
    rp.add_argument("--out", type=Path, help="the folder for the pages (default: a new runs/<date>-report-<RUN>/)")
    rp.add_argument("case", nargs="*", help="case ids (default: every case folder with a result.json)")
    pp = sub.add_parser("prepare", help="build a case's CPA table ahead of any search (blocked sets too; no label, "
                        "audio or event is read); a JSON line per case, also in --out")
    pp.add_argument("case", nargs="+")
    pp.add_argument("--weather", action="store_true", help="the table for runs that apply the case's station temperature")
    pp.add_argument("--out", type=Path, help="write the cases' summaries here as JSON")
    c = sub.add_parser("compare", help="print each run's accounting and the difference between two benchmark runs")
    c.add_argument("a", type=Path); c.add_argument("b", type=Path)
    st = sub.add_parser("study", help="a baseline, variants and control draws from a study file (evaluation/study.py)")
    ssub = st.add_subparsers(dest="study_cmd", required=True)
    sr = ssub.add_parser("run", help="print each variant's differences from the baseline, then run every arm (and "
                         "its control draws) as a benchmark run in one study folder, and summarise it")
    sr.add_argument("study", type=Path)
    sr.add_argument("--out", type=Path, help="the study folder (default: a new run folder; a box's $RUN); what is "
                    "finished there is kept")
    sr.add_argument("--arm", action="append", help="only this arm (repeatable; baseline is the baseline's name)")
    sr.add_argument("--no-controls", action="store_true", help="skip the control draws")
    sr.add_argument("--shard", metavar="I/N", help="every N-th case from the I-th of each run, as bench run --shard")
    sp_ = ssub.add_parser("plan", help="print what the study would run and each variant's differences; run nothing")
    sp_.add_argument("study", type=Path)
    ss = ssub.add_parser("summary", help="the accounting and paired differences of a study folder, from what is on disk")
    ss.add_argument("dir", type=Path)
    sm = ssub.add_parser("merge", help="one study folder from several of the same study (the fleet's shards)")
    sm.add_argument("out", type=Path); sm.add_argument("sources", type=Path, nargs="+")
    si = ssub.add_parser("inputs", help="the files the study's runs read, as JSON, for runs launch --inputs-from")
    si.add_argument("study", type=Path); si.add_argument("--arm", action="append")
    sl = ssub.add_parser("launch", help="print each arm's tools/aws/runs launch command; start nothing")
    sl.add_argument("study", type=Path); sl.add_argument("--arm", action="append")
    a = ap.parse_args(argv)
    # on a fleet box `runs launch` sets $RUN (the job's run folder) and, with --shards, this box's shard
    env_shard = (f"{os.environ['DOPPLERTRACK_SHARD']}/{os.environ['DOPPLERTRACK_SHARDS']}"
                 if os.environ.get("DOPPLERTRACK_SHARD") and os.environ.get("DOPPLERTRACK_SHARDS") else None)
    if a.cmd in ("run", "tier1"):
        a.run_dir = a.run_dir or (Path(os.environ["RUN"]) if os.environ.get("RUN") else None)
        a.shard = a.shard or env_shard
    if a.cmd == "study" and a.study_cmd == "run":
        a.out = a.out or (Path(os.environ["RUN"]) if os.environ.get("RUN") else None)
        a.shard = a.shard or env_shard

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
        ids = a.case or cases.case_ids(profile=a.profile, **({"path": a.cases} if a.cases else {}))
        run_dir = runner.run_bench(ids, tier=a.tier, run_dir=a.run_dir, unit_wall_s=a.unit_wall_s, cases_path=a.cases,
                                   revision=a.revision, profile=a.profile, parallel=a.parallel,
                                   overrides={**runner.parse_overrides(a.search_param),
                                              **({runner.WEATHER_KEY: True} if a.weather else {})}, shard=a.shard,
                                   resume=a.resume, reveal=a.reveal)
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
        runner.run_one(a.case, a.run_dir, execute, code, cases_path=a.cases)
    elif a.cmd == "tier1":
        from . import tier1
        if a.build:
            bad = tier1.build_spans(tuple(a.set or ["development"]))
            sys.exit("\n".join(bad) if bad else 0)
        sets = tuple(a.set or ["development"])
        only = runner.shard_of(tier1.unit_ids(sets), a.shard) if a.shard else a.only
        print(tier1.run_tier1(sets, run_dir=a.run_dir, workers=a.workers, only=only, resume=a.resume,
                              compare=not (a.no_compare or a.shard)))
    elif a.cmd == "report":
        from .report import report_run
        print(report_run(a.run_dir, a.case or None, out_dir=a.out))
    elif a.cmd == "prepare":
        import json
        from .prepare import prepare_case
        done = [prepare_case(c, use_weather=a.weather) for c in a.case]
        if a.out:
            a.out.write_text(json.dumps(done, indent=1) + "\n")
    elif a.cmd == "compare":
        print(runner.compare_runs(a.a, a.b))
    elif a.cmd == "study":
        import json
        from . import study
        try:
            if a.study_cmd == "run":
                print(study.run_study(a.study, out_dir=a.out, arms=a.arm, shard=a.shard, controls=not a.no_controls))
            elif a.study_cmd == "plan":
                print("\n".join(study.announce(study.plan(study.load_study(a.study)))))
            elif a.study_cmd == "summary":
                print(study.summary(a.dir))
            elif a.study_cmd == "merge":
                print(study.merge_study(a.out, a.sources))
            elif a.study_cmd == "inputs":
                print(json.dumps(study.study_inputs(a.study, a.arm), indent=1))
            elif a.study_cmd == "launch":
                print("\n".join(study.launch_commands(a.study, a.arm)))
        except study.StudyError as exc:
            sys.exit("\n".join(exc.problems))


if __name__ == "__main__":
    main()
