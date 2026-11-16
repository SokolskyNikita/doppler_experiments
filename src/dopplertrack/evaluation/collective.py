"""The benchmark's `collective` profile (research readiness R6.1): a case end to end through the collective recipe.

Detection (the grid_pair recipe's `locate` detection settings: 60-300 Hz, one harmonic, the top 10 of 240 s windows)
gives the windows, and `collective_detection` searches the case's box with its flight data. The run's overrides are
`CollectiveParameters` names; a name starting `detection.` sets a detection parameter instead. Two more change the
case, not a parameter: `control_day` (YYYY-MM-DD) swaps in that day's traffic for the same recording, mapped onto the
recording's day (the null's control draw, R5), and `control_traces` says where a control day's file is (default
CONTROL_TRACES). The record is runtime/records' COLLECTIVE_V1 with the benchmark's case, provenance and execution.

A control draw is scored without its labels: there is nothing of the truth to compare another day's traffic with."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from dopplertrack.runtime.records import (COLLECTIVE_KIND, COLLECTIVE_VERSION, file_entry, read_record, unavailable)

from .cases import resolve

RECIPE = "collective"
CONTROL_KEYS = ("control_day", "control_traces")
# A control day's trace file: the case's own file name under that day's folder (the layout tools/data writes).
CONTROL_TRACES = "derived/traces/{day}/{name}"
DETECTION_PREFIX = "detection."
METRICS = ("Z", "n_matched", "modes", "top_error_m")


def split_overrides(overrides: dict | None) -> tuple[dict, dict, dict]:
    """The run's overrides as (collective parameter names, detection parameter names, the control keys)."""
    overrides = dict(overrides or {})
    control = {k: overrides.pop(k) for k in CONTROL_KEYS if k in overrides}
    detection = {k: overrides.pop(k) for k in list(overrides) if k.startswith(DETECTION_PREFIX)}
    return overrides, detection, control


def resolved_parameters(case: dict | None, overrides: dict | None):
    """(CollectiveParameters, the detection's GridPairParameters) for a case and a run's overrides: the defaults, the
    case's search range, then the overrides. Unknown names are refused. With no case, the defaults and the overrides."""
    from dopplertrack.methods.collective.parameters import resolve_collective
    from dopplertrack.methods.grid_pair.parameters import resolve as resolve_grid_pair
    named, detection, _ = split_overrides(overrides)
    base = resolve_collective({"max_range_m": case["search"]["max_range_m"]}) if case else None
    params = resolve_collective(named, base)
    shared = {} if params.speed_of_sound_m_s is None else {"speed_of_sound_m_s": params.speed_of_sound_m_s}
    return params, resolve_grid_pair("locate", shared, detection)


def control_block(case: dict, overrides: dict | None) -> dict | None:
    """The run's control: None for the own-day search, else the traffic day, the recording's day and the shift."""
    from dopplertrack.data.day_mapping import day_shift_s
    day = split_overrides(overrides)[2].get("control_day")
    if day is None:
        return None
    recording = str(case["flight_data"]["date"])
    return {"traffic_day": str(day), "recording_day": recording, "shift_s": day_shift_s(str(day), recording)}


def trace_files(case: dict, overrides: dict | None) -> list[str]:
    """The run's trace files as case paths: the case's own, or with control_day the same file names on that day and,
    for a case of several consecutive days, the days after it."""
    t = case["flight_data"]["traces"]
    own = [t] if isinstance(t, str) else list(t)
    control = split_overrides(overrides)[2]
    if "control_day" not in control:
        return own
    first = datetime.date.fromisoformat(str(control["control_day"]))
    pattern = control.get("control_traces", CONTROL_TRACES)
    return [pattern.format(day=(first + datetime.timedelta(days=i)).isoformat(), name=Path(p).name)
            for i, p in enumerate(own)]


def cpa_cache(case: dict, overrides: dict | None, coarse_m: float) -> str:
    """The coarse CPA table's cache file: one per case table, coarse spacing and traffic day."""
    day = split_overrides(overrides)[2].get("control_day")
    stem = Path(case["search"]["cpa_cache"]).stem
    return f"cpa/collective/{stem}_{coarse_m:g}m{f'_control-{day}' if day else ''}.npz"


def _plain(value):
    return json.loads(json.dumps(value, default=float))


def execute_case_collective(case: dict, case_dir: Path, log=print, code: dict | None = None,
                            overrides: dict | None = None) -> dict:
    """One blind case through detection, its windows and the collective search, as a collective record. It never
    sees the case's labels."""
    from dopplertrack.components.spectrogram import Spectrogram
    from dopplertrack.components.windows import windows_from_detections
    from dopplertrack.data.day_mapping import map_to_day
    from dopplertrack.data.day_seams import join_days
    from dopplertrack.data.terrain import Terrain
    from dopplertrack.methods.collective.search import STATISTIC, collective_detection
    from dopplertrack.methods.grid_pair import pipeline
    from dopplertrack.methods.parameters import to_dict

    from .runner import Stages, code_revision
    assert "labels" not in case, "the runner must be given the blind case"
    stage, errors = Stages(log), []
    record = {"schema_version": COLLECTIVE_VERSION, "kind": COLLECTIVE_KIND,
              "case": {"id": case["id"], "version": case["version"]},
              "provenance": {"created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                             "code": code or code_revision(),
                             "parameters": {"profile": RECIPE, "search_overrides": dict(overrides or {}),
                                            "search": {k: case["search"][k] for k in ("bbox", "dem")}},
                             "inputs": [], "caches": []},
              "statistic": STATISTIC, "statistic_identity": unavailable("the search did not run"),
              "domain": unavailable("the search did not run"), "windows": [], "winner": None,
              "reason": "the search did not run", "modes": [], "control": None, "parameters": unavailable(
                  "the parameters did not resolve"),
              "execution": {"errors": errors, "warnings": stage.warnings, "stages": stage.stages}}
    prov = record["provenance"]
    try:
        params, detection = resolved_parameters(case, overrides)
        control = control_block(case, overrides)
        record.update(parameters=to_dict(params), control=control)
        prov["parameters"]["detection"] = to_dict(detection)["detection"]
        with stage("spectrogram"):
            spec_path = resolve(case["spectrogram"])
            sp = Spectrogram.load(spec_path)
        prov["inputs"].append(file_entry("spectrogram", spec_path))
        with stage("detect"):
            found, _ = pipeline.detect(sp, detection)
            wins = windows_from_detections(found)
        (case_dir / "detected.json").write_text(json.dumps([e.to_dict() for e in found], indent=1) + "\n")
        with stage("flight_data"):
            paths = [resolve(p) for p in trace_files(case, overrides)]
            traces, _ = join_days(paths)
            if control is not None:
                traces = map_to_day(traces, control["traffic_day"], control["recording_day"])
        prov["inputs"] += [file_entry("traces", p) for p in paths]
        cache_path = resolve(cpa_cache(case, overrides, params.planning.coarse_m))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with stage("search"):
            out = collective_detection(sp, wins, traces, tuple(case["search"]["bbox"]), params,
                                       elevation=Terrain().elevation if case["search"]["dem"] else None,
                                       cpa_cache=str(cache_path), log=print)
        if cache_path.exists():
            prov["caches"].append(file_entry("cpa_table", cache_path))
        stage.stages += [{"name": f"search.{k}", "wall_s": round(float(v), 3), "cpu_s": 0.0}
                         for k, v in out.get("walls", {}).items()]
        keep = ("statistic", "statistic_identity", "domain", "windows", "winner", "modes", "kept", "fine_ranks",
                "margin", "counts", "coarse_max")
        record.update(_plain({k: out[k] for k in keep if k in out}), reason=out.get("reason"),
                      modes=_plain(out.get("modes", [])))
    except Exception as exc:          # a failed run is an execution error, never a search that found nothing
        errors.append(f"{type(exc).__name__}: {exc}")
        log(f"ERROR: {type(exc).__name__}: {exc}")
    return record


def compare_collective(record: dict, entry: dict, read_labels) -> dict:
    """The scoreboard entry of a collective record whose hash is already checked: the winner's Z and matched windows,
    and, for the own-day search only, its distance from the reference and whether the true flights are matched."""
    from .runner import _distance_m
    w = record["winner"]
    control = record.get("control")
    entry.update(status="error" if record["execution"]["errors"] else "scored", recipe=RECIPE,
                 stages=record["execution"]["stages"], errors=record["execution"]["errors"],
                 search_overrides=record["provenance"]["parameters"].get("search_overrides", {}),
                 statistic_id=(record["statistic_identity"] or {}).get("id"), candidates=1 if w else 0,
                 reason=record.get("reason"), Z=w["Z"] if w else None, n_matched=w["n_matched"] if w else 0,
                 modes=len(record.get("modes") or []), control_day=control["traffic_day"] if control else None)
    if control:
        entry["top_error_m"] = entry["true_flights_matched"] = unavailable("a control draw has no reference")
        return entry
    lab = read_labels()
    ref, pair = lab.get("reference") or {}, lab.get("true_pair")
    matched = sorted({m["icao"] for m in (w or {}).get("windows", []) if m and m.get("z", 0) > 0 and "icao" in m})
    entry["matched_flights"] = matched
    entry["top_error_m"] = (_distance_m(w["lat"], w["lon"], ref["lat"], ref["lon"]) if w and "lat" in ref
                            else unavailable("no winner" if not w else "the case has no reference point"))
    entry["true_flights_matched"] = (all(f in matched for f in pair) if pair
                                     else unavailable("the case has no true flight pair in its box"))
    return entry


def case_unit(case_dir: Path) -> dict:
    """A finished benchmark case folder as a unit for the null's collection (methods/collective/null.collect_units):
    its record, checked against the hash written beside it, and the recording it read."""
    from dopplertrack.methods.collective.units import IncompleteUnit
    from dopplertrack.runtime.records import RecordError

    from .runner import HASH_FILE
    case_dir = Path(case_dir)
    try:
        sha = (case_dir / HASH_FILE).read_text().split()[0]
        record = read_record(case_dir / "result.json", expected_sha256=sha)
    except (OSError, IndexError, RecordError, ValueError) as exc:
        raise IncompleteUnit(f"{case_dir}: no record matching its hash ({exc})") from None
    if record.get("kind") != COLLECTIVE_KIND or record["execution"]["errors"] or not isinstance(
            record["statistic_identity"], dict) or "id" not in record["statistic_identity"]:
        raise IncompleteUnit(f"{case_dir}: not a collective search that ran to its end")
    files = {f["role"]: f["sha256"] for f in record["provenance"]["inputs"]}
    return {"path": str(case_dir), "request": {"inputs": {"spectrogram": files.get("spectrogram")}}, "result": record,
            "result_sha256": sha}
