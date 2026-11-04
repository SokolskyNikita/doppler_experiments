"""Tier 1 (PLAN 5.4): detection and fits against the blind labels on development spans, and the known point.

A span is a labelled stretch of a recording's timeline (bench/labels/), not a case. `execute_span` sees only a
label file's inputs: each window's start, end and labelled lines, by position. From them it writes
span_result.json: every detection detect makes on the span and a fit of every labelled line, per objective.
That record and its hash are written before anything reads a window's class, an association or a trajectory
reference; `compare_span` reads those only after the hash check, as compare_case does for cases.

The knobs below were set before any detection was matched against a label."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import numpy as np

from dopplertrack.result import (CONVENTIONS_V1, ListOf, Maybe, OneOf, RecordError, _check, dumps, sha256_bytes,
                                 unavailable)

from .cases import REPO, resolve

TIER1 = REPO / "bench" / "tier1.json"
SPAN_KIND = "dopplertrack.span_result"
SPAN_SCHEMA_VERSION = 1
SPAN_FILE, SPAN_HASH = "span_result.json", "span_result.json.sha256"
DETECT_TOP = 200                 # more than detect can propose on a crop, so none is dropped before matching

KNOBS = {
    "crop_margin_s": 240.0,      # detect sees the span plus this either side; a detection belongs to the span by its
                                 # heard CPA, so one whose window straddles an edge is judged on partial evidence
    "cpa_slack_s": 5.0,          # a detection's heard CPA may lie this far outside a window: labels are read to seconds
    "line_tolerance": 0.10,      # f0 * k within this fraction of a labelled line's entry-exit band
    "harmonic_ratios": [0.5, 1.0, 2.0],  # f0 * k on exactly one line for one k, and with two or more lines its next
                                 # harmonic on another (see _line_match); tightened before the full spans were matched
    "fit_band_margin": 0.10,     # a labelled line is fitted in its band widened by this fraction
    "association_dt_s": 10.0,    # a detection agrees with its associated flight within this heard-CPA difference
    "association_df": 0.10,      # and this fraction of f0
}
RISING = "rising line, no straight-pass model"
COUNTED = ("clear", "overlapping")           # matched or missed
EXCLUDED = ("uncertain", "masked")           # in neither count, nor are detections inside them

NUMBER = (int, float)
FIT = {"t_cpa": NUMBER, "t_cpa_emit": NUMBER, "f0": NUMBER, "v": NUMBER, "d": NUMBER, "t_start": NUMBER,
       "t_end": NUMBER, "score": NUMBER, "f_pre": NUMBER, "f_post": NUMBER}
SPAN_SCHEMA_V1 = {
    "schema_version": int,
    "kind": OneOf(SPAN_KIND),
    "span": {"id": str, "labels": str, "start": NUMBER, "end": NUMBER},
    "conventions": dict,
    "provenance": {"created": str, "code": dict, "parameters": dict,
                   "inputs": ListOf({"role": str, "path": str, "bytes": int, "sha256": str})},
    "detections": Maybe(ListOf(FIT)),
    "window_fits": Maybe(ListOf({"window": int, "line": int, "band_hz": ListOf(NUMBER), "objective": str,
                                 "fit": Maybe(FIT)})),
    "execution": {"errors": ListOf(str), "warnings": ListOf(str),
                  "stages": ListOf({"name": str, "wall_s": NUMBER, "cpu_s": NUMBER})},
}


def validate_span(record) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SPAN_SCHEMA_VERSION:
        raise RecordError([f"span record: schema_version must be {SPAN_SCHEMA_VERSION}"])
    problems: list[str] = []
    _check(record, SPAN_SCHEMA_V1, "span_record", problems)
    if problems:
        raise RecordError(problems)


def load_tier1(path=TIER1) -> dict:
    doc = json.loads(Path(path).read_text())
    problems = []
    for s in doc.get("spans", []):
        for k in ("id", "labels", "set", "group", "family", "spectrogram", "reference_case"):
            if k not in s:
                problems.append(f"span {s.get('id', '?')}: {k} is missing")
        if s.get("set") not in ("development", "calibration", "evaluation"):
            problems.append(f"span {s.get('id', '?')}: set must be development, calibration or evaluation")
    if problems:
        raise RecordError(problems)
    return doc


def span_inputs(labels: dict) -> tuple[list[float], list[dict]]:
    """What the run may see of a label file: the span and, by position, each window's extent and lines.
    Window ids, classes, notes and associations stay out: they are the truth the comparison uses."""
    windows = [{"window": i, "start": float(w["start"]), "end": float(w["end"]),
                "lines": [[float(a), float(b)] for a, b in w["lines"]]} for i, w in enumerate(labels["windows"])]
    return [float(x) for x in labels["span"]], windows


def execute_span(span: dict, out_dir: Path, code: dict, log=print, workers: int | None = None) -> dict:
    """detect and window fits on one span, as a span record. Reads no class, association or reference."""
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections
    from dopplertrack.result import file_entry
    from dopplertrack.tracks import detect_events

    from .runner import PROFILES, Stages
    stage, errors = Stages(log), []
    labels_path = resolve(span["labels"])
    (a, b), windows = span_inputs(json.loads(labels_path.read_text()))
    d = PROFILES["raw-audio"]["detect"]
    params = {"knobs": KNOBS, "detect": {**d, "top": DETECT_TOP, "min_score": 0.0}, "objectives": ["brightness", "contrast"]}
    spec = resolve(span["spectrogram"]["path"])
    detections, fits = unavailable("the span did not run"), unavailable("the span did not run")
    inputs = []
    try:
        with stage("spectrogram"):
            sp = Spectrogram.load(spec)
            crop = sp.crop(a - KNOBS["crop_margin_s"], b + KNOBS["crop_margin_s"])
        inputs.append(file_entry("spectrogram", spec))
        with stage("detect"):
            found = cached_detections(crop, detect_events, f_lo=d["band_hz"][0], f_hi=d["band_hz"][1],
                                      harmonics=d["harmonics"], top=DETECT_TOP, window_s=d["window_s"], min_score=0.0,
                                      workers=workers)
            detections = [e.to_dict() for e in found if a <= e.t_cpa <= b]
        slots, tasks = [], []
        m = KNOBS["fit_band_margin"]
        for w in windows:
            for j, (f_in, f_out) in enumerate(w["lines"]):
                lo, hi = min(f_in, f_out) * (1 - m), max(f_in, f_out) * (1 + m)
                for objective in params["objectives"]:
                    if rising([f_in, f_out]):
                        slots.append({"window": w["window"], "line": j, "band_hz": [lo, hi], "objective": objective,
                                      "fit": unavailable(RISING)})
                    else:
                        slots.append(None)
                        tasks.append((w["window"], j, w["start"], w["end"], lo, hi, objective))
        with stage("window_fits"):
            from dopplertrack.parallel import ordered_map, resolve_jobs
            jobs = min(resolve_jobs(workers), max(len(tasks), 1))
            from dopplertrack.cache import spectrogram_sha256
            done = iter(list(ordered_map(_fit_window, tasks, jobs, _set_fit_crop, (crop, spectrogram_sha256(crop)))))
            fits = [x if x is not None else next(done) for x in slots]
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        log(f"ERROR: {type(exc).__name__}: {exc}")
    return {"schema_version": SPAN_SCHEMA_VERSION, "kind": SPAN_KIND,
            "span": {"id": span["id"], "labels": span["labels"], "start": a, "end": b},
            "conventions": CONVENTIONS_V1,
            "provenance": {"created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                           "code": code, "parameters": params, "inputs": inputs},
            "detections": detections, "window_fits": fits,
            "execution": {"errors": errors, "warnings": stage.warnings, "stages": stage.stages}}


_FIT_CROP = {}


def _set_fit_crop(crop, crop_sha256):
    _FIT_CROP.update(sp=crop, sha256=crop_sha256)


def _fit_window(task) -> dict:
    """One labelled line fitted in its window and band; a line the fitter can't follow is a missing fit. Cached
    on the crop's contents, the window, the band, the objective and fit_event's source, under the cache rules."""
    import scipy

    from dopplertrack.cache import DETECTOR_CODE, cached, code_sha256
    from dopplertrack.tracks import fit_event
    window, line, t0, t1, lo, hi, objective = task

    def produce():
        try:
            return fit_event(_FIT_CROP["sp"], t0, t1, lo, hi, objective=objective).to_dict()
        except Exception as exc:
            return unavailable(f"{type(exc).__name__}: {exc}")
    parts = {"spectrogram": _FIT_CROP["sha256"], "window_s": [t0, t1], "band_hz": [lo, hi], "objective": objective,
             "producer": "tracks.fit_event", "code": code_sha256(DETECTOR_CODE),
             "versions": {"numpy": np.__version__, "scipy": scipy.__version__}}
    fit = cached("window_fits", parts, produce)
    if "unavailable" not in fit and fit.get("weak"):
        fit = unavailable(f"fit_event's weak fit: {fit['weak']}")
    elif "unavailable" not in fit and not all(np.isfinite(v) for v in fit.values() if not isinstance(v, str)):
        fit = unavailable("fit_event returned a non-finite fit: no curve to follow in this window and band")
    return {"window": window, "line": line, "band_hz": [lo, hi], "objective": objective, "fit": fit}


def write_span(out_dir: Path, record: dict) -> str:
    validate_span(record)
    data = dumps(record)
    tmp = out_dir / f".{SPAN_FILE}.{os.getpid()}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, out_dir / SPAN_FILE)
    sha = sha256_bytes(data)
    (out_dir / SPAN_HASH).write_text(f"{sha}  {SPAN_FILE}\n")
    return sha


def rising(line) -> bool:
    """A labelled line whose exit frequency is above its entry: no straight pass makes that."""
    return float(line[1]) > float(line[0])


def outside_model(w: dict) -> bool:
    """A counted window none of whose lines a straight pass could make: it can't be a flyover, so it is
    neither matched nor missed, and detections inside it count nowhere."""
    return not any(not rising(line) for line in w["lines"])


def _in_band(f: float, line) -> bool:
    tol = KNOBS["line_tolerance"]
    return min(line) * (1 - tol) <= f <= max(line) * (1 + tol)


def _line_match(f0: float, lines: list[list[float]]) -> bool:
    """Whether a detection's f0 is a window's fundamental: for some k in harmonic_ratios, f0 * k lies in
    exactly one line's band, and no other k puts it on that line; and when the window has two or more falling
    lines, the next harmonic, 2 * f0 * k, lies in another line's band. Rising lines take no part."""
    falling = [line for line in lines if not rising(line)]
    ks = KNOBS["harmonic_ratios"]
    for k in ks:
        on = [j for j, line in enumerate(falling) if _in_band(f0 * k, line)]
        if len(on) != 1:
            continue
        j = on[0]
        if any(_in_band(f0 * k2, falling[j]) for k2 in ks if k2 != k):
            continue                      # the line's band spans a factor of two: which harmonic is ambiguous
        if len(falling) < 2 or any(_in_band(2 * f0 * k, line) for i, line in enumerate(falling) if i != j):
            return True
    return False


def match(detections: list[dict], windows: list[dict], min_score: float = 0.0) -> dict:
    """Matched, missed and extra per window class for the detections scoring at least min_score.
    A detection matches a counted window when its heard CPA lies in the window (with slack) and its f0, or a
    harmonic ratio of it, lies on one of the window's lines. One that matches none is excluded if its heard
    CPA lies in an uncertain or masked window, and extra otherwise."""
    slack = KNOBS["cpa_slack_s"]
    dets = [d for d in detections if d["score"] >= min_score]
    hit, extra_by = set(), {}
    excluded = 0
    for d in dets:
        inside = [w for w in windows if w["start"] - slack <= d["t_cpa"] <= w["end"] + slack]
        matches = [w for w in inside if w["class"] in COUNTED and not outside_model(w) and _line_match(d["f0"], w["lines"])]
        if matches:
            hit.update(w["index"] for w in matches)
        elif any(w["class"] in EXCLUDED or (w["class"] in COUNTED and outside_model(w)) for w in inside):
            excluded += 1
        else:
            home = min(inside, key=lambda w: abs((w["start"] + w["end"]) / 2 - d["t_cpa"]))["class"] if inside else "outside"
            extra_by[home] = extra_by.get(home, 0) + 1
    out = {}
    for cls in COUNTED:
        ws = [w for w in windows if w["class"] == cls and not outside_model(w)]
        out[cls] = {"windows": len(ws), "matched": sum(w["index"] in hit for w in ws),
                    "missed": sum(w["index"] not in hit for w in ws),
                    "outside_model": sum(1 for w in windows if w["class"] == cls and outside_model(w))}
    out["extra"] = {"total": sum(extra_by.values()), "by_window_class": extra_by}
    out["excluded_detections"] = excluded
    out["detections"] = len(dets)
    return out


def countable_hours(span: tuple[float, float], windows: list[dict]) -> float:
    """The audio that can hold a false alarm: the span less its uncertain, masked and outside-model windows."""
    gone = sorted((max(w["start"], span[0]), min(w["end"], span[1])) for w in windows
                  if w["class"] in EXCLUDED or (w["class"] in COUNTED and outside_model(w)))
    lost, reach = 0.0, span[0]
    for a, b in gone:
        a = max(a, reach)
        if b > a:
            lost += b - a
            reach = b
    return max(span[1] - span[0] - lost, 0.0) / 3600.0


def pooled_curve(units: list[tuple[list[dict], list[dict], float]]) -> list[dict]:
    """The false-alarm table over several spans: at each detection score taken as the threshold, the summed
    matches, misses and extras, and extras per countable hour of all of them. Matched and missed are None
    when the pool has no counted window."""
    hours = sum(h for _, _, h in units)
    counted = any(w["class"] in COUNTED and not outside_model(w) for _, ws, _ in units for w in ws)
    rows = []
    for s in sorted({0.0, *(d["score"] for dets, _, _ in units for d in dets)}):
        ms = [match(dets, ws, s) for dets, ws, _ in units]
        extra = sum(m["extra"]["total"] for m in ms)
        rows.append({"min_score": s, "extra": extra, "extra_per_hour": extra / hours if hours else None,
                     "matched": sum(m[c]["matched"] for m in ms for c in COUNTED) if counted else None,
                     "missed": sum(m[c]["missed"] for m in ms for c in COUNTED) if counted else None})
    return rows


def threshold_curve(detections: list[dict], windows: list[dict], hours: float) -> list[dict]:
    """The match counts at each detection score taken as the threshold: the false-alarm curve, as a table."""
    rows = []
    for s in sorted({0.0, *(d["score"] for d in detections)}):
        m = match(detections, windows, s)
        rows.append({"min_score": s, "matched": sum(m[c]["matched"] for c in COUNTED),
                     "missed": sum(m[c]["missed"] for c in COUNTED), "extra": m["extra"]["total"],
                     "extra_per_hour": m["extra"]["total"] / hours if hours else None})
    return rows


def line_f0(line) -> float:
    """A straight pass's rest frequency from its entry and exit frequencies: f_in = f0 c/(c - v) and
    f_out = f0 c/(c + v) give f0 = 2 f_in f_out / (f_in + f_out). Read from a picture, so good to about 5 %."""
    a, b = float(line[0]), float(line[1])
    return 2 * a * b / (a + b)


def trajectory_reference(traces, icao: str, observer_enu, lat0, lon0, t0_unix: float, near_audio_s: float, c: float):
    """Layer 3 for one flight (PLAN 5.3): what the observer should hear from its trace, in audio seconds.
    The heard CPA, the steepest fall of the modelled curve, and the slant range and ground speed at CPA, from
    the segment whose heard CPA lies nearest near_audio_s. None if the flight has no segment in range."""
    from dopplertrack.score import modelled_curve, steepest_fall
    from dopplertrack.search import build_segments
    best = None
    for seg in build_segments([t for t in traces if t.icao == icao], lat0, lon0):
        r = np.linalg.norm(seg.enu - observer_enu, axis=1)
        j = int(np.argmin(r))
        if j == 0 or j == len(r) - 1:
            continue
        heard = seg.t[j] + r[j] / c - t0_unix
        if best is None or abs(heard - near_audio_s) < abs(best["t_heard_cpa_s"] - near_audio_s):
            # placed like the search's own steepest-fall check: within ±60 s of the emission CPA, smoothed
            t_obs, ratio = modelled_curve(seg, observer_enu, c)
            sf = steepest_fall(t_obs, ratio, float(seg.t[j]))
            steep = None if sf is None else float(sf - t0_unix)
            best = {"t_heard_cpa_s": float(heard), "t_steepest_fall_s": steep, "slant_range_m": float(r[j]),
                    "ground_speed_m_s": float(seg.speed[j])}
    return best


def fit_errors(fit: dict, ref: dict, c: float) -> dict:
    """A fit against layer 3; steepest falls are placed by the same function on both sides."""
    from dopplertrack.pipeline import fitted_steepest_fall
    from dopplertrack.tracks import EventFit
    sf = fitted_steepest_fall(EventFit(**fit), c)
    return {"dt_heard_s": fit["t_cpa"] - ref["t_heard_cpa_s"],
            "dt_steepest_s": None if ref["t_steepest_fall_s"] is None or sf is None else sf - ref["t_steepest_fall_s"],
            "df0_pct": 100 * (fit["f0"] - ref["f0_hz"]) / ref["f0_hz"],
            "dv_m_s": fit["v"] - ref["ground_speed_m_s"], "dd_m": fit["d"] - ref["slant_range_m"]}


def score_fits(record: dict, windows: list[dict], associations: list[dict], reference_context) -> tuple:
    """Fit errors against layer 3 for every probable association, per objective and for its window's matching
    detection, and the association share. reference_context() gives (traces, observer_enu, lat0, lon0, t0_unix, c)."""
    probable = [a for a in associations if a.get("confidence") == "probable" and isinstance(a.get("flight"), dict)]
    if not probable:
        return [], unavailable("no probable association in this span")
    if any(a.get("line") is None for a in probable):
        return unavailable("an association has no line index"), unavailable("an association has no line index")
    traces, obs, lat0, lon0, t0_unix, c = reference_context()
    by_id = {w["id"]: w for w in windows}
    fits = record["window_fits"] if isinstance(record["window_fits"], list) else []
    dets = record["detections"] if isinstance(record["detections"], list) else []
    rows, consistent = [], 0
    slack = KNOBS["cpa_slack_s"]
    for a in probable:
        w = by_id[a["window"]]
        line = w["lines"][a["line"]]
        ref = trajectory_reference(traces, a["flight"]["icao"], obs, lat0, lon0, t0_unix,
                                   float(a["flight"].get("heard_cpa_s", (w["start"] + w["end"]) / 2)), c)
        row = {"window": a["window"], "line": a["line"], "flight": a["flight"]["icao"], "reference": ref}
        if ref is None:
            rows.append({**row, "errors": unavailable("the flight has no segment with a CPA in range")})
            continue
        ref["f0_hz"] = line_f0(line)
        row["objectives"] = {f["objective"]: (fit_errors(f["fit"], ref, c) if "unavailable" not in f["fit"] else f["fit"])
                             for f in fits if f["window"] == w["index"] and f["line"] == a["line"]}
        on_line = [d for d in dets if w["start"] - slack <= d["t_cpa"] <= w["end"] + slack
                   and _line_match(d["f0"], [line])]
        if on_line:
            d = max(on_line, key=lambda d: d["score"])
            e = fit_errors(d, ref, c)
            row["detection"] = e
            # agreement with the flight: f0 checked against the line at any harmonic ratio, like matching
            ratio_ok = any(abs(d["f0"] * k - ref["f0_hz"]) <= KNOBS["association_df"] * ref["f0_hz"]
                           for k in KNOBS["harmonic_ratios"])
            consistent += abs(e["dt_heard_s"]) <= KNOBS["association_dt_s"] and ratio_ok
        else:
            row["detection"] = unavailable("no detection on this line")
        rows.append(row)
    return rows, {"probable": len(probable), "consistent": consistent, "share": consistent / len(probable)}


def compare_span(out_dir: Path, read_labels, reference_context=None) -> dict:
    """Score a span record against its labels, only once its bytes still match the hash written beside it."""
    from dopplertrack.result import sha256_bytes as _sha
    try:
        expected = (out_dir / SPAN_HASH).read_text().split()[0]
        data = (out_dir / SPAN_FILE).read_bytes()
        if _sha(data) != expected:
            raise RecordError([f"{SPAN_FILE} does not match its hash"])
        record = json.loads(data)
        validate_span(record)
    except (OSError, IndexError, RecordError, ValueError) as exc:
        return {"span": out_dir.name, "status": "discarded", "reason": f"record does not match the hash written "
                f"before the labels were read: {exc}"}
    entry = {"span": record["span"]["id"], "record_sha256": expected, "stages": record["execution"]["stages"],
             "errors": record["execution"]["errors"], "status": "error" if record["execution"]["errors"] else "scored"}
    labels = read_labels()
    windows = [{"index": i, "class": w["class"], "start": float(w["start"]), "end": float(w["end"]),
                "lines": w["lines"]} for i, w in enumerate(labels["windows"])]
    dets = record["detections"] if isinstance(record["detections"], list) else []
    hours = countable_hours((record["span"]["start"], record["span"]["end"]), windows)
    entry["detection"] = match(dets, windows)
    entry["detection"].update(countable_hours=hours, span_hours=(record["span"]["end"] - record["span"]["start"]) / 3600,
                              extra_per_hour=entry["detection"]["extra"]["total"] / hours if hours else None)
    entry["detection_curve"] = threshold_curve(dets, windows, hours)
    entry["_pool"] = (dets, windows, hours)          # for run_tier1's pooled curves; not written
    if reference_context is None:
        entry["fits"] = entry["association"] = unavailable("no trajectory reference was given for this span")
    else:
        idw = [{"id": w["id"], "index": i, "start": float(w["start"]), "end": float(w["end"]), "lines": w["lines"]}
               for i, w in enumerate(labels["windows"])]
        entry["fits"], entry["association"] = score_fits(record, idw, labels.get("associations", []), reference_context)
    return entry


# The known point (PLAN 5.4's known-point check): a case's two events scored at the reference coordinate only.
# The events are chosen blind and written with their hash first; the search at the reference runs in the
# comparison step, because the reference is truth, and its table is truth-conditioned, never a blind result.
EVENTS_FILE, EVENTS_HASH = "events.json", "events.json.sha256"
KP_PROFILES = ("saved-fit", "raw-audio-windows", "raw-audio")
KP_RULES = {"saved-fit": "the case's saved fits",
            "raw-audio-windows": "detect on each saved event's window ± crop_margin_s; the best-scoring detection whose "
                                 "heard CPA lies inside that window (Tier 1's cheap raw-audio rule)",
            "raw-audio": "detect over the whole recording; its top two by score, earlier first (the raw-audio profile)"}
KP_FILE, KP_HASH = "known_point.json", "known_point.json.sha256"


def _write_hashed(path: Path, obj: dict) -> str:
    data = (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n").encode()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    sha = sha256_bytes(data)
    path.with_name(path.name + ".sha256").write_text(f"{sha}  {path.name}\n")
    return sha


def _read_hashed(path: Path) -> dict:
    data = path.read_bytes()
    if sha256_bytes(data) != path.with_name(path.name + ".sha256").read_text().split()[0]:
        raise RecordError([f"{path.name} does not match its hash"])
    return json.loads(data)


def case_events(case: dict, profile: str, out_dir: Path, code: dict, workers: int | None = None) -> dict:
    """The case's two search events under a profile, chosen without the labels, written with their hash."""
    from dopplertrack.audio import Spectrogram
    from dopplertrack.cache import cached_detections, detection_key
    from dopplertrack.result import file_entry
    from dopplertrack.tracks import detect_events

    from .runner import PROFILES, pick_detected, saved_fit_dicts, search_harmonics, sound_speed
    assert "labels" not in case, "the known point's events must be chosen blind"
    if profile not in KP_PROFILES:
        raise ValueError(f"known-point profile must be one of {KP_PROFILES}")
    spec = resolve(case["spectrogram"])
    out = {"case": {"id": case["id"], "version": case["version"]}, "profile": profile, "code": code,
           "rule": KP_RULES[profile], "inputs": [file_entry("spectrogram", spec)], "detection_key": None,
           "harmonics": search_harmonics(case, "saved-fit") if profile == "saved-fit" else [1, 1]}
    if profile == "saved-fit":
        out["events"] = saved_fit_dicts(case)[:2]
        out["inputs"] += [file_entry("saved_fits", resolve(p)) for p in case["events"]["files"]]
    elif profile == "raw-audio-windows":
        # detect around each saved event's window, so a cold run costs two short crops, not the recording
        d, margin = PROFILES["raw-audio"]["detect"], KNOBS["crop_margin_s"]
        sp = Spectrogram.load(spec)
        out["events"], out["detection_key"] = [], []
        for fit in saved_fit_dicts(case)[:2]:
            crop = sp.crop(fit["t_start"] - margin, fit["t_end"] + margin)
            params = dict(f_lo=d["band_hz"][0], f_hi=d["band_hz"][1], harmonics=d["harmonics"], top=DETECT_TOP,
                          window_s=d["window_s"], min_score=0.0)
            found = [e.to_dict() for e in cached_detections(crop, detect_events, workers=workers, **params,
                                                            **sound_speed(case)[0])
                     if fit["t_start"] <= e.t_cpa <= fit["t_end"]]
            out["detection_key"].append(detection_key(crop, detect_events, **params))
            if not found:
                raise ValueError(f"detect found nothing inside the saved window {fit['t_start']:.0f}-{fit['t_end']:.0f} s")
            out["events"].append(max(found, key=lambda e: e["score"]))
    else:
        d = PROFILES[profile]["detect"]
        sp = Spectrogram.load(spec)
        params = dict(f_lo=d["band_hz"][0], f_hi=d["band_hz"][1], harmonics=d["harmonics"], top=d["top"],
                      window_s=d["window_s"])
        out["events"] = pick_detected([e.to_dict() for e in cached_detections(sp, detect_events, workers=workers,
                                                                                **params, **sound_speed(case)[0])])
        out["detection_key"] = detection_key(sp, detect_events, **params)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_hashed(out_dir / EVENTS_FILE, out)
    return out


def known_point(case: dict, out_dir: Path, reference: dict, true_pair, log=print) -> dict:
    """After the events' hash check: every flight pair scored at the reference, written as a truth-conditioned
    table with its own hash, and the scoreboard's summary of it."""
    from dopplertrack import pipeline
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.search import Grid
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import EventFit

    from .runner import geometry_kw, trace_paths
    try:
        ev = _read_hashed(out_dir / EVENTS_FILE)
    except (OSError, IndexError, RecordError, ValueError) as exc:
        return {"status": "discarded", "reason": f"events do not match the hash written before the truth: {exc}"}
    s = case["search"]
    lat, lon = float(reference["lat"]), float(reference["lon"])
    el = Terrain().elevation(np.array([lat]), np.array([lon])) if s["dem"] else np.zeros(1)
    grid = Grid.points([lat], [lon], el)
    traces, meta = join_days(trace_paths(case))
    ev1, ev2 = (EventFit(**e) for e in ev["events"])
    sp = Spectrogram.load(resolve(case["spectrogram"]))
    res, _ = pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=tuple(ev["harmonics"][:2]), tol_s=s["tol_s"],
                                 v_tol=s["v_tol"], d_tol=tuple(s["d_tol"]), silence_d_m=s["silence_d_m"],
                                 max_range_m=s["max_range_m"], progress=False, trace_metadata=meta,
                                 search_bbox=(lat, lat, lon, lon), workers=1, **geometry_kw(case))
    best = res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["icao1", "icao2"])
    pairs = [{"flights": [str(r.icao1), str(r.icao2)], "score": float(r.score), "event_scores": [float(r.s1), float(r.s2)],
              "shift_s": float(r.shift)} for r in best.itertuples()]
    _write_hashed(out_dir / KP_FILE, {
        "truth_conditioned": True,
        "note": "scored at the reference coordinate, which is truth: a diagnostic of the events and the physics, "
                "never a blind result",
        "case": ev["case"], "profile": ev["profile"], "events_used": ev["events"], "harmonics": ev["harmonics"],
        "detection_key": ev["detection_key"], "events_sha256": sha256_bytes((out_dir / EVENTS_FILE).read_bytes()),
        "reference": {"lat": lat, "lon": lon}, "pairs": pairs, "funnel": res.attrs.get("funnel", {})})
    rank = next((k for k, p in enumerate(pairs, 1) if true_pair and p["flights"] == list(true_pair)), None)
    second = pairs[1]["score"] if len(pairs) > 1 else None
    return {"status": "scored", "profile": ev["profile"], "pairs_at_point": len(pairs),
            "true_pair_rank_at_point": rank, "true_pair_first": rank == 1,
            "margin_pct": ((100 * (pairs[0]["score"] - second) / second) if second else
                           unavailable(f"n/a: the true pair is the only one of {len(pairs)} pair(s) at the point"))
                          if rank == 1 else None}


def reference_context(span: dict, labels: dict):
    """For the comparison step only: the span's flight data, observer and clock, from its reference case's
    labels and the label file's own clock (both truth)."""
    from dopplertrack.adsb import join_days
    from dopplertrack.terrain import Terrain

    from .cases import case_labels, latest_case
    from .runner import sound_speed, trace_paths
    case = latest_case(span["reference_case"])
    ref = case_labels(case["id"], case["version"])["reference"]
    lat, lon = float(ref["lat"]), float(ref["lon"])
    elev = float(Terrain().elevation(np.array([lat]), np.array([lon]))[0]) if case["search"]["dem"] else 0.0
    traces, _ = join_days(trace_paths(case))
    t0 = datetime.datetime.fromisoformat(labels["recording"]["t0_utc"].replace("Z", "+00:00")).timestamp()
    return traces, np.array([0.0, 0.0, elev]), lat, lon, t0, sound_speed(case)[1]["c_m_s"]


BACKGROUND_FAMILIES = ("essex", "aerosonicdb")      # recordings with nothing to find (PLAN 5.1 negatives)
BUDGET_S = 180.0      # PLAN 5.4: Tier 1 under 3 min; a span or case joins only if the whole run stays under it


def build_spans(sets=("development",), log=print) -> list[str]:
    """Make each missing derived file of the spans in these sets from its recipe, and check every hash."""
    from .cases import build
    bad = []
    for s in load_tier1()["spans"]:
        if s["set"] in sets and s.get("derived"):
            bad += build(s, log=log)
    return bad


def _blind_done(path: Path, hash_name: str) -> bool:
    """Whether a blind record was finished: it exists and matches the hash written beside it."""
    try:
        return sha256_bytes(path.read_bytes()) == (path.parent / hash_name).read_text().split()[0]
    except (OSError, IndexError):
        return False


def unit_ids(sets=("development",)) -> list[str]:
    """Tier 1's units of work, the ids `--only` and `--shard` choose from: its spans, then its known-point cases."""
    doc = load_tier1()
    return [s["id"] for s in doc["spans"] if s["set"] in sets] + list(doc["known_point"])


def run_tier1(sets=("development",), run_dir: Path | None = None, log=print, workers: int | None = None,
              only: list[str] | None = None, resume: bool = False, compare: bool = True) -> Path:
    """Every span of the given sets and every known-point case, blind first, then compared, into one run folder.
    only: run just these units (span ids, known-point case ids) blind; a shard of boxes each takes some with
    compare=False, `merge_tier1` puts them together, and one resumed run compares. resume: keep every blind record
    that matches its hash and run the rest. The comparison needs every unit's blind record."""
    import sys
    import time

    from .cases import blind_case, case_labels, latest_case
    from .runner import check_resumable, code_revision, new_run
    code = code_revision()
    t0 = time.perf_counter()
    if resume and run_dir is None:
        raise ValueError("resume needs the stopped run's --run-dir")
    if run_dir is None:
        run_dir = new_run(f"bench-{str(code['git_commit'])[:7]}-t1")
    info_path = run_dir / "run.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    want = {"tier": "t1", "profile": "tier1", "search_overrides": {}, "code": code}
    if resume and any((run_dir / d).exists() for d in ("spans", "known_point")):
        check_resumable(info, want, run_dir)
    unknown = sorted(set(only or []) - set(unit_ids(sets)))
    if unknown:
        raise ValueError(f"{unknown} are not Tier 1 units of the sets {list(sets)}")
    info.update(want, command=sys.argv, sets=list(sets), only=only)
    info_path.write_text(json.dumps(info, indent=1) + "\n")
    doc = load_tier1()
    spans = [s for s in doc["spans"] if s["set"] in sets]
    skipped = [{"span": s["id"], "set": s["set"], "reason": f"not in the requested sets {list(sets)}"}
               for s in doc["spans"] if s["set"] not in sets]
    ready = []
    for s in spans:
        if not s["spectrogram"].get("sha256"):
            skipped.append({"span": s["id"], "set": s["set"], "reason": "its spectrogram is not built yet"})
        else:
            ready.append(s)
    timings = {}
    # blind: every span record and every case's events are written and hashed before any label is read
    chosen = set(only) if only else set(unit_ids(sets))
    for s in ready:
        out = run_dir / "spans" / s["id"]
        if s["id"] not in chosen or (resume and _blind_done(out / SPAN_FILE, SPAN_HASH)):
            continue
        w = time.perf_counter()
        out.mkdir(parents=True, exist_ok=True)
        write_span(out, execute_span(s, out, code, log=log, workers=workers))
        timings[f"span {s['id']}"] = time.perf_counter() - w
    for cid in doc["known_point"]:
        for profile in ("saved-fit", "raw-audio-windows"):
            out = run_dir / "known_point" / cid / profile
            if cid not in chosen or (resume and _blind_done(out / EVENTS_FILE, EVENTS_HASH)):
                continue
            w = time.perf_counter()
            case_events(blind_case(cid), profile, out, code, workers=workers)
            timings[f"events {cid} {profile}"] = time.perf_counter() - w
    if not compare:
        (run_dir / "timings.json").write_text(json.dumps({k: round(v, 2) for k, v in timings.items()}, indent=1) + "\n")
        return run_dir
    missing = [s["id"] for s in ready if not _blind_done(run_dir / "spans" / s["id"] / SPAN_FILE, SPAN_HASH)] + \
        [f"{cid} {pr}" for cid in doc["known_point"] for pr in ("saved-fit", "raw-audio-windows")
         if not _blind_done(run_dir / "known_point" / cid / pr / EVENTS_FILE, EVENTS_HASH)]
    if missing:
        raise ValueError(f"the comparison needs every unit's blind record; missing {missing}. Merge the shards "
                         "or resume the run first")
    # truth: labels, references and the known-point searches
    span_entries = []
    for s in ready:
        labels = json.loads(resolve(s["labels"]).read_text())
        ref = (lambda s=s, labels=labels: reference_context(s, labels)) if s.get("reference_case") else None
        span_entries.append({**compare_span(run_dir / "spans" / s["id"], lambda labels=labels: labels, ref),
                             "set": s["set"], "group": s["group"], "family": s["family"]})
    # pooled false-alarm tables: per group, per family, and over the background families together
    pools, units = {}, {e["span"]: e.pop("_pool") for e in span_entries if "_pool" in e}
    for kind, key in (("group", "group"), ("family", "family")):
        for name in sorted({e[key] for e in span_entries}):
            members = [e["span"] for e in span_entries if e[key] == name and e["span"] in units]
            pools[f"{kind} {name}"] = {"spans": members, "curve": pooled_curve([units[m] for m in members])}
    background = [e["span"] for e in span_entries if e["family"] in BACKGROUND_FAMILIES and e["span"] in units]
    if background:
        pools["background"] = {"spans": background, "curve": pooled_curve([units[m] for m in background])}
    kp_entries = []
    for cid in doc["known_point"]:
        case = latest_case(cid)
        lab = case_labels(cid, case["version"])
        del case["labels"]
        for profile in ("saved-fit", "raw-audio-windows"):
            w = time.perf_counter()
            e = known_point(case, run_dir / "known_point" / cid / profile, lab["reference"], lab.get("true_pair"), log)
            timings[f"known point {cid} {profile}"] = time.perf_counter() - w
            kp_entries.append({"case": cid, **e})
    wall = time.perf_counter() - t0
    results = {"schema": 1, "tier": "t1", "code": code, "knobs": KNOBS, "sets": list(sets),
               "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "spans": span_entries, "pooled": pools, "known_point": kp_entries, "skipped": skipped,
               "timings_s": {k: round(v, 2) for k, v in timings.items()}, "wall_s": round(wall, 2),
               "within_budget": wall < BUDGET_S, "budget_s": BUDGET_S}
    (run_dir / "results.json").write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")
    return run_dir


def merge_tier1(out_dir: Path, sources: list[Path], log=print) -> None:
    """Copy the blind records of Tier 1 shards (spans/<id>, known_point/<case>/<profile>) into out_dir, from one
    clean commit only; then `bench tier1 --run-dir OUT --resume` compares them. A unit two shards both finished
    must match byte for byte."""
    import shutil

    from .runner import check_resumable
    infos = [(src, json.loads((src / "run.json").read_text())) for src in sources]
    want = {k: infos[0][1].get(k) for k in ("tier", "profile", "search_overrides", "code")}
    for src, info in infos:
        check_resumable(info, want, src)
    copied = 0
    for src, _ in infos:
        for unit, rec, h in [(d, d / SPAN_FILE, SPAN_HASH) for d in sorted((src / "spans").glob("*/"))] + \
                [(d, d / EVENTS_FILE, EVENTS_HASH) for d in sorted((src / "known_point").glob("*/*/"))]:
            if not _blind_done(rec, h) or src.resolve() == out_dir.resolve():
                continue
            dest = out_dir / unit.relative_to(src)
            if dest.exists():
                if not _blind_done(dest / rec.name, h) or (dest / rec.name).read_bytes() != rec.read_bytes():
                    raise ValueError(f"{dest} already holds a different or unfinished record")
                continue
            shutil.copytree(unit, dest)
            copied += 1
    info_path = out_dir / "run.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    info.update(want, merged_from=[str(s) for s in sources])
    info_path.write_text(json.dumps(info, indent=1) + "\n")
    log(f"copied {copied} blind records into {out_dir}; compare with bench tier1 --run-dir {out_dir} --resume")
