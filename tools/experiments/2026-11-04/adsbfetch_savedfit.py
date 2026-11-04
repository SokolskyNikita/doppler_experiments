"""Part 3 of the adsbfetch comparison: the saved-fit search of the oyster-bay and eagle-cam-clip-18000s cases
on our adsb.lol cut and on the windowed mirror union, side by side, with today's runner.

Each variant is the case as committed with two fields changed in memory only: flight_data.traces (the
mirror-union npz for "mirror") and search.cpa_cache (a private cpa/adsbfetch/<case>_<variant>.npz, so no
shared cache is read or written). bench.runner.bench_case runs it blind, writes result.json and its hash,
and only then scores it against the case's labels; bench/cases.json is not touched.

usage: uv run python tools/experiments/2026-11-04/adsbfetch_savedfit.py "$RUN" ADSBFETCH_RUN [CASE:NAME=NPZ ...]
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))      # the repo root, for bench/
from bench import runner  # noqa: E402

CASES = {"oyster-bay": "ny_mirror_union.npz", "eagle-cam-clip-18000s": "swfl_mirror_union.npz"}


def variant(name, traces):
    def execute(case, case_dir, **kw):
        c = copy.deepcopy(case)
        if traces is not None:
            c["flight_data"]["traces"] = str(traces)
            c["flight_data"]["extraction_note"] = "adsbfetch mirror union (adsbfi + airplaneslive), windowed; see the run folder"
        c["search"]["cpa_cache"] = f"cpa/adsbfetch/{case['id']}_{name}.npz"
        return runner.execute_case(c, case_dir, **kw)
    return execute


def main(run: Path, fetch_run: Path, extra: list[str]):
    """extra: CASE:NAME=NPZ entries to run instead of the default cut and mirror pairs (diagnostics)."""
    code = runner.code_revision()
    out = {}
    plan = [(cid, name, traces) for cid, npz in CASES.items() for name, traces in (("cut", None), ("mirror", fetch_run / npz))]
    if extra:
        plan = [(e.split(":", 1)[0], *e.split(":", 1)[1].split("=", 1)) for e in extra]
        plan = [(cid, name, fetch_run / npz) for cid, name, npz in plan]
    for cid, name, traces in plan:
        if True:
            d = run / f"{cid}_{name}"
            entry = runner.bench_case(cid, d, execute=variant(name, traces), code=code, log=lambda m: None)
            out[f"{cid}/{name}"] = entry
            print(cid, name, json.dumps({k: entry.get(k) for k in ("status", "outcome", "true_pair_rank", "n_pairs", "refined_error_m",
                                                                  "top_error_m", "margin_pct", "margin") if k in entry}), flush=True)
    json.dump(out, open(run / "savedfit.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
