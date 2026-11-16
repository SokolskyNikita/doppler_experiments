"""A study: a baseline, its variants and their control draws, each an ordinary benchmark run inside one study folder
(research readiness R6.2). Nothing here is a second runner: `run_study` calls `runner.run_bench` once per arm (and
once per arm and control day), and `summary` reads the runs back with `accounting`.

The study file (JSON):
- name: lowercase letters, digits and hyphens;
- cases: the case ids; cases_file (optional): another manifest than bench/cases.json, relative to the study file;
- unit_wall_s: the wall-time cap of one case in one run, in seconds. Required, with no default: a unit past it is
  stopped and counted incomplete;
- seed: the master seed of the null and normalisation draws (an integer), or null for the draws as the recipes make
  them without a study. Required;
- baseline: {"recipe": "grid_pair" or "collective", "profile": one of the recipe's, "parameters": overrides};
- variants: {name: {"parameters": overrides}}: the baseline's parameters with these on top, method choices included;
- controls (collective only, optional): {"days": [YYYY-MM-DD, ...] or {case: [days]}, "traces": where a control
  day's file is (default evaluation/collective.CONTROL_TRACES)}: other days' traffic for the same recordings;
- parallel (optional): cases at once in each run; aws (optional): the fleet's limits and box settings for
  `bench study launch` (max_boxes and max_vcpus are required there).

The study folder: plan.json (every run with its resolved parameters, written before anything runs), arms/<arm>/ and
controls/<arm>/<day>/ (benchmark run folders), nulls/<arm>/<case>.npz (the control draws collected with
methods/collective/null.py), summary.json and summary.txt."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import accounting
from .cases import CASES, REPO, latest_case

RECIPES = {"grid_pair": ("saved-fit", "raw-audio", "locate"), "collective": ("collective",)}
SEED_PARAMETER = {"grid_pair": "scoring.null_seed", "collective": "null.seed"}
NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
KEYS = {"name", "cases", "cases_file", "unit_wall_s", "seed", "baseline", "variants", "controls", "parallel", "aws"}
REQUIRED = ("name", "cases", "unit_wall_s", "seed", "baseline")
BASELINE = "baseline"


class StudyError(ValueError):
    """A study file that can't be run as written; `problems` lists everything wrong with it."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def load_study(path) -> dict:
    """The study file, checked, with cases_file made absolute and `path` added. Raises StudyError."""
    path = Path(path).resolve()
    doc = json.loads(path.read_text())
    problems = []
    if not isinstance(doc, dict):
        raise StudyError([f"{path}: a study is an object"])
    problems += [f"unknown field {k!r}" for k in sorted(set(doc) - KEYS)]
    problems += [f"{k} is missing (it has no default)" for k in REQUIRED if k not in doc]
    if problems:
        raise StudyError(problems)
    if not (isinstance(doc["name"], str) and NAME.fullmatch(doc["name"])):
        problems.append("name: lowercase letters, digits and hyphens")
    if not (isinstance(doc["cases"], list) and doc["cases"] and all(isinstance(c, str) for c in doc["cases"])
            and len(set(doc["cases"])) == len(doc["cases"])):
        problems.append("cases: a non-empty list of distinct case ids")
    cap = doc["unit_wall_s"]
    if not (isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap > 0):
        problems.append("unit_wall_s: the per-unit wall-time cap in seconds, above zero")
    if not (doc["seed"] is None or (isinstance(doc["seed"], int) and not isinstance(doc["seed"], bool))):
        problems.append("seed: an integer, or null for the recipes' own draws")
    base = doc["baseline"]
    if not (isinstance(base, dict) and set(base) <= {"recipe", "profile", "parameters"} and base.get("recipe") in RECIPES
            and base.get("profile") in RECIPES.get(base.get("recipe"), ()) and isinstance(base.get("parameters", {}), dict)):
        problems.append(f"baseline: recipe and profile, one of {RECIPES}, and optional parameters")
    variants = doc.get("variants", {})
    if not (isinstance(variants, dict) and all(isinstance(n, str) and NAME.fullmatch(n) and n != BASELINE
                                               and isinstance(v, dict) and set(v) == {"parameters"}
                                               and isinstance(v["parameters"], dict) for n, v in variants.items())):
        problems.append('variants: {name: {"parameters": {...}}}, names in lowercase letters, digits and hyphens')
    controls = doc.get("controls")
    if controls is not None:
        days = controls.get("days") if isinstance(controls, dict) else None
        per_case = isinstance(days, dict)
        lists = list(days.values()) if per_case else [days]
        if not (isinstance(controls, dict) and set(controls) <= {"days", "traces"} and days
                and all(isinstance(lst, list) and len(set(lst)) == len(lst) and all(_is_day(d) for d in lst) for lst in lists)
                and (not per_case or set(days) <= set(doc["cases"] if isinstance(doc["cases"], list) else []))):
            problems.append("controls: days as a list of distinct YYYY-MM-DD, or {case: [days]} over the study's cases")
        elif isinstance(base, dict) and base.get("recipe") != "collective":
            problems.append("controls: only the collective recipe has control draws")
    if problems:
        raise StudyError(problems)
    out = {"variants": {}, "controls": None, "parallel": 1, "aws": {}, **doc, "path": str(path)}
    out["baseline"] = {"parameters": {}, **base}
    out["cases_file"] = str((path.parent / doc["cases_file"]).resolve()) if doc.get("cases_file") else None
    return out


def _is_day(d) -> bool:
    import datetime
    try:
        return isinstance(d, str) and datetime.date.fromisoformat(d).isoformat() == d
    except ValueError:
        return False


def _flat(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        out.update(_flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}": v})
    return out


def arm_overrides(study: dict, arm: str) -> dict:
    """An arm's overrides: the baseline's parameters, the variant's on top, then the master seed. A study whose own
    parameters set the seed parameter is refused: the seed has one place."""
    recipe = study["baseline"]["recipe"]
    out = dict(study["baseline"]["parameters"])
    if arm != BASELINE:
        out.update(study["variants"][arm]["parameters"])
    seed_key = SEED_PARAMETER[recipe]
    if any(k in (seed_key, seed_key.rsplit(".", 1)[-1]) for k in out):
        raise StudyError([f"{arm}: {seed_key} is set by the study's seed, not by a parameter"])
    if study["seed"] is not None:
        out[seed_key] = study["seed"]
    return out


def resolved(study: dict, arm: str) -> dict:
    """What an arm runs with, as flat names: its resolved parameters (the recipe's defaults, the profile's, the
    arm's overrides; a case adds its own layer the same way in every arm) and the run settings that are not
    parameters. An unknown name is refused here, before anything runs."""
    from dopplertrack.methods.parameters import to_dict
    recipe, profile = study["baseline"]["recipe"], study["baseline"]["profile"]
    overrides = arm_overrides(study, arm)
    if recipe == "collective":
        from .collective import resolved_parameters, split_overrides
        params, detection = resolved_parameters(None, overrides)
        settings = split_overrides(overrides)[2]
        flat = {**_flat(to_dict(params)), **_flat({"detection": to_dict(detection)["detection"]})}
    else:
        from dopplertrack.methods.grid_pair.parameters import resolve
        from .runner import LOCATE_CASE_KEYS, WEATHER_KEY, check_overrides
        check_overrides(profile, overrides)
        run_keys = {WEATHER_KEY} | (LOCATE_CASE_KEYS if profile == "locate" else set())
        settings = {k: v for k, v in overrides.items() if k in run_keys}
        flat = _flat(to_dict(resolve(profile, None, {k: v for k, v in overrides.items() if k not in run_keys})))
    return {"parameters": flat, "settings": settings}


def differences(base: dict, other: dict) -> list[str]:
    """Each name whose value differs between two arms' resolved sets, as "name: baseline -> arm"."""
    out = []
    for part in ("parameters", "settings"):
        for k in sorted(set(base[part]) | set(other[part])):
            a, b = base[part].get(k, "(unset)"), other[part].get(k, "(unset)")
            if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
                out.append(f"{k}: {json.dumps(a)} -> {json.dumps(b)}")
    return out


def control_days(study: dict, case: str) -> list[str]:
    controls = study["controls"]
    if not controls:
        return []
    days = controls["days"]
    return list(days.get(case, [])) if isinstance(days, dict) else list(days)


def plan(study: dict) -> dict:
    """Every run of the study: {"arms": {arm: {"resolved", "differences"}}, "runs": [{"arm", "day" (None for the
    arm's own run), "dir", "cases", "profile", "overrides"}]}. Raises StudyError for an arm that changes nothing."""
    ckw = {"path": study["cases_file"]} if study["cases_file"] else {}
    groups = {c: latest_case(c, **ckw).get("group") for c in study["cases"]}
    arms, runs, problems = {}, [], []
    base = resolved(study, BASELINE)
    for arm in [BASELINE, *study["variants"]]:
        res = base if arm == BASELINE else resolved(study, arm)
        diff = [] if arm == BASELINE else differences(base, res)
        if arm != BASELINE and not diff:
            problems.append(f"variant {arm} changes nothing from the baseline")
        arms[arm] = {"resolved": res, "differences": diff}
        overrides = arm_overrides(study, arm)
        common = {"arm": arm, "profile": study["baseline"]["profile"]}
        runs.append({**common, "day": None, "dir": f"arms/{arm}", "cases": list(study["cases"]), "overrides": overrides})
        days = sorted({d for c in study["cases"] for d in control_days(study, c)})
        for day in days:
            extra = {"control_day": day, **({"control_traces": study["controls"]["traces"]}
                                            if study["controls"].get("traces") else {})}
            runs.append({**common, "day": day, "dir": f"controls/{arm}/{day}", "overrides": {**overrides, **extra},
                         "cases": [c for c in study["cases"] if day in control_days(study, c)]})
    if problems:
        raise StudyError(problems)
    return {"name": study["name"], "recipe": study["baseline"]["recipe"], "seed": study["seed"],
            "unit_wall_s": study["unit_wall_s"], "cases_file": study["cases_file"], "groups": groups,
            "arms": arms, "runs": runs}


def announce(planned: dict) -> list[str]:
    """What the study will run, before it runs: each variant's differences from the baseline, and the unit counts."""
    lines = [f"study {planned['name']}: {planned['recipe']}, seed {planned['seed']}, "
             f"{planned['unit_wall_s']:g} s wall-time cap per unit"]
    for arm, a in planned["arms"].items():
        own = sum(len(r["cases"]) for r in planned["runs"] if r["arm"] == arm and r["day"] is None)
        draws = sum(len(r["cases"]) for r in planned["runs"] if r["arm"] == arm and r["day"] is not None)
        lines.append(f"  {arm}: {own} cases" + (f", {draws} control draws" if draws else ""))
        lines += [f"    {d}" for d in a["differences"]] if arm != BASELINE else ["    the baseline"]
    return lines


def run_study(study_path, out_dir: Path | None = None, arms: list[str] | None = None, shard: str | None = None,
              controls: bool = True, log=print) -> Path:
    """Run the study (or only `arms` of it) into out_dir, a new run folder by default, each run through run_bench
    with the study's wall-time cap, resuming whatever is already finished there. The differences from the baseline
    are printed, and plan.json written, before the first run starts. Returns the study folder."""
    from . import runner
    study = load_study(study_path)
    planned = plan(study)
    unknown = sorted(set(arms or []) - set(planned["arms"]))
    if unknown:
        raise StudyError([f"no arm {unknown} in the study; it has {list(planned['arms'])}"])
    for line in announce(planned):
        log(line)
    out_dir = Path(out_dir) if out_dir else runner.new_run(f"study-{study['name']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != json.loads(json.dumps(planned)):
        raise StudyError([f"{out_dir} holds another study's plan (or this one before an edit); use a new folder"])
    plan_path.write_text(json.dumps(planned, indent=1, sort_keys=True) + "\n")
    for run in planned["runs"]:
        if (arms and run["arm"] not in arms) or (run["day"] is not None and not controls):
            continue
        log(f"-- {run['dir']}: {len(run['cases'])} cases")
        runner.run_bench(run["cases"], tier="study", run_dir=out_dir / run["dir"], log=log, profile=run["profile"],
                         parallel=study["parallel"], overrides=run["overrides"], shard=shard, resume=True,
                         unit_wall_s=study["unit_wall_s"], cases_path=study["cases_file"])
    log(summary(out_dir))
    return out_dir


def _entries(run_dir: Path) -> dict:
    path = run_dir / "results.json"
    return {e["case"]: e for e in json.loads(path.read_text())["cases"]} if path.exists() else {}


def collect_null(study_dir: Path, planned: dict, arm: str, case: str, own_class: str, draw_classes: dict) -> dict:
    """The arm's control draws for one case, collected with the R5 null tooling into nulls/<arm>/<case>.npz. Returns
    {"draws": n, "own_Z", "max_draw_Z", "file"} or {"refused": why}: an own-day search or a draw that is missing,
    failed or of another statistic stops the collection, never thins it. own_class and draw_classes ({day: class})
    are the accounting's."""
    from dopplertrack.methods.collective.null import collect_units, save_draws
    from dopplertrack.methods.collective.units import IncompleteUnit
    from .collective import case_unit
    days = list(draw_classes)
    if not days:
        return {"draws": 0}
    if own_class not in accounting.COMPLETE:
        return {"refused": f"the own-day search is {own_class}"}
    short = {d: c for d, c in draw_classes.items() if c not in accounting.COMPLETE}
    if short:
        return {"refused": f"{len(short)} of {len(days)} draws did not finish: "
                           + ", ".join(f"{d} {c}" for d, c in sorted(short.items()))}
    try:
        own = case_unit(study_dir / "arms" / arm / case)
        table = collect_units(own, [case_unit(study_dir / "controls" / arm / d / case) for d in days], days)
    except IncompleteUnit as exc:
        return {"refused": str(exc).replace(f"{study_dir}/", "")}
    out = study_dir / "nulls" / arm / f"{case}.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.tmp.npz")
    save_draws(tmp, table)
    tmp.replace(out)
    zs = [r["max_Z"] for r in table["draws"] if r["max_Z"] == r["max_Z"]]
    return {"draws": len(days), "own_Z": table["own"]["max_Z"], "max_draw_Z": max(zs) if zs else None,
            "draws_without_a_winner": len(days) - len(zs), "file": str(out.relative_to(study_dir))}


def summary(study_dir) -> str:
    """The study's accounting and comparisons from what is on disk, written to summary.json and summary.txt and
    returned as text: per arm and case group, every scheduled case in one class (the control draws likewise, a unit
    per case and day); the control draws collected per case; and each variant's paired differences from the
    baseline over the cases complete in both. The denominators come from the plan, so an arm that never ran is all
    missing."""
    study_dir = Path(study_dir)
    planned = json.loads((study_dir / "plan.json").read_text())
    groups = planned["groups"]
    doc: dict = {"name": planned["name"], "arms": {}}
    lines = [f"study {planned['name']} in {study_dir}"]
    accts = {}
    for arm, a in planned["arms"].items():
        own = next(r for r in planned["runs"] if r["arm"] == arm and r["day"] is None)
        acct = accounting.account(study_dir / own["dir"], [{"case": c, "group": groups.get(c)} for c in own["cases"]])
        accts[arm] = acct
        lines += ["", f"arm {arm}" + ("" if arm == BASELINE else ": " + "; ".join(a["differences"]))]
        lines += accounting.table(acct)
        entry = {"differences": a["differences"], "counts": accounting.counts(acct), "classes": acct["classes"],
                 "why": acct["why"]}
        draws = [r for r in planned["runs"] if r["arm"] == arm and r["day"] is not None]
        if draws:
            merged = {"scheduled": [], "classes": {}, "groups": {}, "why": {}}
            for r in draws:
                one = accounting.account(study_dir / r["dir"], [{"case": c, "group": groups.get(c)} for c in r["cases"]])
                for c in r["cases"]:
                    unit = f"{c}@{r['day']}"
                    merged["scheduled"].append({"case": unit, "group": groups.get(c)})
                    merged["classes"][unit], merged["groups"][unit] = one["classes"][c], groups.get(c)
                    if c in one["why"]:
                        merged["why"][unit] = one["why"][c]
            lines += ["  control draws (a unit is a case on a control day):", *accounting.table(merged, indent="    ")]
            nulls = {c: collect_null(study_dir, planned, arm, c, acct["classes"][c],
                                     {r["day"]: merged["classes"][f"{c}@{r['day']}"] for r in draws if c in r["cases"]})
                     for c in own["cases"]}
            for c, n in nulls.items():
                if "refused" in n:
                    lines.append(f"    null {c}: not collected: {n['refused']}")
                elif n["draws"]:
                    lines.append(f"    null {c}: {n['draws']} draws in {n['file']}; own-day Z {_num(n['own_Z'])}, "
                                 f"highest draw Z {_num(n['max_draw_Z'])}")
            entry.update(control_counts=accounting.counts(merged), control_classes=merged["classes"], nulls=nulls)
        doc["arms"][arm] = entry
    base_entries = _entries(study_dir / "arms" / BASELINE)
    for arm in planned["arms"]:
        if arm == BASELINE:
            continue
        paired = accounting.paired_cases(accts[BASELINE], accts[arm])
        diffs = accounting.paired_differences(base_entries, _entries(study_dir / "arms" / arm), paired)
        doc["arms"][arm]["paired"] = {"cases": paired, "differences": diffs}
        lines += ["", f"{arm} against the baseline:",
                  *accounting.paired_lines(diffs, len(paired), indent="  ")]
    text = "\n".join(lines)
    (study_dir / "summary.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    (study_dir / "summary.txt").write_text(text + "\n")
    return text


def _num(v) -> str:
    return "none" if v is None or v != v else f"{v:.2f}"


def merge_study(out_dir, sources, log=print) -> Path:
    """One study folder from several of the same study (the shards a fleet brought back): each run's folders merged
    with runner.merge_runs, then the summary. Every source must hold the same plan."""
    from . import runner
    out_dir, sources = Path(out_dir), [Path(s) for s in sources]
    plans = [json.loads((s / "plan.json").read_text()) for s in sources]
    if any(p != plans[0] for p in plans[1:]):
        raise StudyError(["the sources are not one study: their plan.json differ"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / "plan.json").exists() and json.loads((out_dir / "plan.json").read_text()) != plans[0]:
        raise StudyError([f"{out_dir} holds another study's plan"])
    (out_dir / "plan.json").write_text(json.dumps(plans[0], indent=1, sort_keys=True) + "\n")
    for run in plans[0]["runs"]:
        have = [s / run["dir"] for s in sources if (s / run["dir"] / "run.json").exists()]
        if have:
            (out_dir / run["dir"]).mkdir(parents=True, exist_ok=True)
            runner.merge_runs(out_dir / run["dir"], have, log)
    log(summary(out_dir))
    return out_dir


def study_inputs(study_path, arms: list[str] | None = None) -> dict:
    """What the study's runs read, in `bench inputs`' shape, for `runs launch --inputs-from`. A fixture whose cases
    name absolute paths brings its own files, so it lists none."""
    from . import inputs
    study = load_study(study_path)
    planned = plan(study)
    ckw = {"path": study["cases_file"]} if study["cases_file"] else {}
    out = inputs._Lists()
    for run in planned["runs"]:
        if arms and run["arm"] not in arms:
            continue
        for cid in run["cases"]:
            inputs._case_files(out, latest_case(cid, **ckw), run["profile"], cid, overrides=run["overrides"])
    cases_file = Path(study["cases_file"] or CASES)
    if cases_file.is_relative_to(REPO):
        out.add("repo", str(cases_file.relative_to(REPO)), "cases and their labels", "all")
    out.add("cache", inputs.SMALL_CACHES[0]["path"], inputs.SMALL_CACHES[0]["role"], "all")
    return out.doc(study["cases"], kind="bench study", study=study["name"])


def launch_commands(study_path, arms: list[str] | None = None) -> list[str]:
    """The `tools/aws/runs launch` command of each arm, for the owner to run after `--check` and `--rehearse`: the arm
    and its control draws on `aws.shards` boxes under the study's limit on concurrent boxes and vCPUs (aws.max_boxes
    and aws.max_vcpus, required). A collective arm's topic is its statistic label (R5), not a hand-kept version."""
    import shlex
    study = load_study(study_path)
    planned = plan(study)
    aws = study["aws"]
    missing = [k for k in ("max_boxes", "max_vcpus") if not isinstance(aws.get(k), int) or aws[k] < 1]
    if missing:
        raise StudyError([f"aws.{k}: the study-wide limit is needed to launch" for k in missing])
    unknown = sorted(set(aws) - {"max_boxes", "max_vcpus", "size", "shards", "max_hours", "on_demand"})
    if unknown:
        raise StudyError([f"aws: unknown fields {unknown}"])
    path = Path(study["path"])
    shown = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)
    out = []
    for arm in planned["arms"]:
        if arms and arm not in arms:
            continue
        cmd = ["tools/aws/runs", "launch", arm_topic(study, arm), "--study", study["name"],
               "--max-boxes", str(aws["max_boxes"]), "--max-vcpus", str(aws["max_vcpus"])]
        cmd += ["--shards", str(aws["shards"])] if aws.get("shards", 1) > 1 else []
        cmd += ["--size", aws["size"]] if aws.get("size") else []
        cmd += ["--max-hours", str(aws["max_hours"])] if aws.get("max_hours") else []
        cmd += ["--on-demand"] if aws.get("on_demand") else []
        cmd += ["--inputs-from", f"uv run python -m bench study inputs {shlex.quote(shown)} --arm {arm}", "--",
                "uv", "run", "python", "-m", "bench", "study", "run", shown, "--arm", arm, "--out", "$RUN"]
        out.append(" ".join(c if c == "$RUN" else shlex.quote(c) for c in cmd))
    return out


def arm_topic(study: dict, arm: str) -> str:
    """The arm's launch topic: for the collective recipe the statistic label of the arm's parameters (the name and
    the first 12 digits of the identity, lowercase as a topic must be), so the launch names exactly what it computes;
    for grid_pair the study and arm names."""
    if study["baseline"]["recipe"] != "collective":
        return f"study-{study['name']}-{arm}"
    from dopplertrack.methods.collective.search import statistic_identity, statistic_label
    from .collective import resolved_parameters
    return statistic_label(statistic_identity(resolved_parameters(None, arm_overrides(study, arm))[0])).lower()
