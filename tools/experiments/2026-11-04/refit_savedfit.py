"""Are the 15 C saved fits the mismatch? The two positive seed cases' events refitted at the ground temperature's c, in the
committed fits' windows and bands, then searched through the per-flight path (docs/experiments/2026-11-04-case-weather.md).

Refits, per case, with tracks.fit_event as the committed fits were made:
  oyster-bay   the README's `dopplertrack fit` commands: 2090-2200 s in 95-200 Hz at harmonics 2, and 3020-3130 s in 95-195 Hz,
               brightness objective (the CLI's)
  eagle cam    detect's refine step (tracks.detect_events): t0 +-120 s in 60-300 Hz at harmonics 1, contrast objective,
               init the committed fit's (f0, v, d, t_cpa), v within 35-200 m/s, d within 200 m-15 km
each at c = 340.3 m/s (15 C: the procedure's check against the committed fits) and at the case's ground temperature.

Searches, each a unit (tools/data/shards.py), the case as on dev with only its events and its run switch changed:
  committed-off   the committed fits, weather off: today's default
  committed-on    the committed fits, weather on (bench run --weather): the per-flight result
  refit15-off     the 15 C refits, weather off: the refit procedure's control
  refitT-on       the ground-temperature refits, weather on: the test
Criterion (fixed before the run): with refitT-on the eagle cam's true pair is at rank 1, and Oyster Bay's margin is within
1 point of 4.9 %.

usage: uv run python tools/experiments/2026-11-04/refit_savedfit.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, inputs as bench_inputs, runner  # noqa: E402

CASES = ("oyster-bay", "eagle-cam-clip-18000s")
VARIANTS = ("committed-off", "refit15-off", "committed-on", "refitT-on")
FITS = {"oyster-bay": [dict(window=(2090.0, 2200.0), band=(95.0, 200.0), harmonics=2, objective="brightness"),
                       dict(window=(3020.0, 3130.0), band=(95.0, 195.0), harmonics=1, objective="brightness")],
        "eagle-cam-clip-18000s": "detect-refine"}


def refits(case: dict, c: float) -> list[dict]:
    """The case's two events refitted at c, as saved-fit dicts in the case spectrogram's own time."""
    from dopplertrack.audio import Spectrogram
    from dopplertrack.tracks import fit_event
    sp = Spectrogram.load(runner.resolve(case["spectrogram"]))
    committed = runner.saved_fit_dicts(case)          # already in the spectrogram's time (time_offset_s applied)
    out = []
    for k, ev in enumerate(committed):
        spec = FITS[case["id"]]
        if spec == "detect-refine":
            t0 = ev["t_cpa"]
            ef = fit_event(sp, max(t0 - 120, sp.t[0]), min(t0 + 120, sp.t[-1]), 60.0, 300.0, c=c, harmonics=1,
                           init=(ev["f0"], ev["v"], ev["d"], t0), v_bounds=(35.0, 200.0), d_bounds=(200.0, 15000.0))
        else:
            s = spec[k]
            ef = fit_event(sp, *s["window"], *s["band"], c=c, harmonics=s["harmonics"], objective=s["objective"])
        out.append(ef.to_dict())
    return out


def variant_case(case: dict, files: list[str] | None) -> dict:
    c = copy.deepcopy(case)
    if files:
        c["events"] = {"mode": "saved_fits", "files": files, "pick": None, "time_offset_s": 0.0}
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        doc = bench_inputs.run_inputs(list(CASES), "saved-fit")
        shards.print_inputs(doc["cases"], doc["inputs"], doc["cpa_tables"], tuple(doc["cache_kinds"]))
        return
    params = dict(cases=list(CASES), variants=list(VARIANTS), fits=FITS)
    run = shards.open_run(a.run, "refit-savedfit", {"script": "tools/experiments/2026-11-04/refit_savedfit.py", "params": params})
    ids = [f"{cid}--{v}" for cid in CASES for v in VARIANTS]
    units = shards.Units(run, ids, params, a.shard, a.resume)
    if not a.merge:
        from dopplertrack.doppler import speed_of_sound
        code = runner.code_revision()
        for uid in units.todo():
            cid, var = uid.split("--")
            blind = cases.blind_case(cid)
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            files = None
            if var.startswith("refit"):
                t = blind["weather"]["temperature_c"] if var == "refitT-on" else 15.0
                fits = refits(blind, speed_of_sound(t))
                files = []
                for k, f in enumerate(fits, 1):
                    p = d / f"ev{k}_{t:g}C.json"
                    p.write_text(json.dumps(f, indent=1) + "\n"); files.append(str(p))
            over = {runner.WEATHER_KEY: True} if var.endswith("-on") else {}

            def execute(case, case_dir, files=files, over=over, **kw):
                return runner.execute_case(variant_case(case, files), case_dir, overrides=over, **kw)
            entry = runner.bench_case(cid, d / "bench", execute=execute, code=code, log=lambda m: None)
            (d / "entry.json").write_text(json.dumps(entry, indent=1, default=str) + "\n")
            units.finish(uid, {k: entry.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m", "top_error_m")})
            print(uid, {k: entry.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m")}, flush=True)
        if a.shard != (1, 1) or units.todo():
            return
    rows = {}
    for uid, d in units.all().items():
        e = json.loads((d / "entry.json").read_text())
        rows[uid] = {k: e.get(k) for k in ("true_pair_rank", "margin_pct", "refined_error_m", "top_error_m", "flight_pairs")}
        for f in sorted(d.glob("ev*_*C.json")):
            rows[uid][f.stem] = {k: json.loads(f.read_text())[k] for k in ("f0", "v", "d", "t_cpa", "score")}
    ok_eagle = rows["eagle-cam-clip-18000s--refitT-on"]["true_pair_rank"] == 1
    m = rows["oyster-bay--refitT-on"]["margin_pct"]
    ok_ob = m is not None and abs(m - 4.9) <= 1.0
    out = dict(rows=rows, criterion={"eagle_true_pair_rank_1": ok_eagle, "oyster_bay_margin_within_1_point_of_4.9": ok_ob,
                                     "passes": ok_eagle and ok_ob})
    (run / "refit.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
