"""Run benchmark cases through today's pipeline, write each `result.json` and its hash, then score it.

The order is the point (PLAN.md 5.5): `execute_case` sees the case without its labels, `bench_case`
writes the record and `result.json.sha256` before anything reads a label, and `compare_case` refuses a
record whose bytes no longer match the hash written beside it."""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import math
import os
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

from dopplertrack.result import (CONVENTIONS_V1, KIND, SCHEMA_VERSION, RecordError, file_entry, read_record,
                                 unavailable, write_record)

from .cases import REPO, blind_case, case_labels, case_profiles, data_root, latest_case, resolve

NO_VERDICT = "no verdict or abstention exists before Phase 4"
NO_REGION = "no uncertainty region exists before Phase 4"
PER_GATE = ("pair_candidates applies the speed, distance and time gates in one call and run_search returns no "
            "per-gate counts; filled once run_search returns its funnel")
PER_EVENT_GATE = ("run_search gates speed and distance together for each event; see funnel.pipeline's event1_gates "
                  "and event2_gates")
NEAR_REFERENCE_M = 250.0     # the nearest 200 m grid point and its neighbours (Phase 2 item 1's criterion)
TRIPLES_FILE = "funnel_triples.npz"
# Overrides change how a run searches, never the CPA table a case's cache file holds, so the inputs of
# cpa_table (the grid, the range, the terrain) and the cache path itself can't be overridden.
FIXED_BY_CASE = ("bbox", "spacing_m", "dem", "max_range_m", "cpa_cache")
SEARCH_ARGS = ("tol_s", "v_tol", "d_tol", "silence_d_m", "harmonics")


def git(*args) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _cpu() -> float:
    a, b = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime


class _Tee(io.StringIO):
    """Keeps what a stage prints and passes each complete line on to the log as it arrives."""

    def __init__(self, log):
        super().__init__()
        self.forward, self.pending, self.stdout = log, "", sys.stdout

    def write(self, s):
        self.pending += s
        *lines, self.pending = self.pending.split("\n")
        with contextlib.redirect_stdout(self.stdout):    # the log may print; it must not print into itself
            for ln in lines:
                self.forward(ln)
        return super().write(s)


class Stages:
    """Wall and CPU time per pipeline stage, with the stage's log lines kept for the record."""

    def __init__(self, log):
        self.log, self.stages, self.warnings = log, [], []

    @contextlib.contextmanager
    def __call__(self, name):
        buf = _Tee(self.log)
        w0, c0 = time.perf_counter(), _cpu()
        try:
            with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(buf):
                warnings.simplefilter("always")
                yield
        finally:
            self.stages.append({"name": name, "wall_s": round(time.perf_counter() - w0, 3),
                                "cpu_s": round(_cpu() - c0, 3)})
            if buf.pending:
                buf.write("\n")
            text = buf.getvalue()
            self.warnings += [f"{name}: {ln.strip()}" for ln in text.splitlines() if "WARNING" in ln]
            self.warnings += [f"{name}: {w.category.__name__}: {w.message}" for w in caught]


# The two baseline profiles of PLAN 5.5. saved-fit takes each case's committed fits and isolates search and
# physics; raw-audio runs detect with no hand-picked windows and takes its top two by score, earlier first
# (trying every pair is Phase 3's job). Detection searches with one harmonic per event: nothing says which
# harmonic a detected tone is.
PROFILES = {
    "saved-fit": {"events": "the case's saved fits", "harmonics": "the case's"},
    "raw-audio": {"events": "detect, top two by score, earlier first", "detect": {"band_hz": [60.0, 300.0], "top": 10,
                  "harmonics": 1, "window_s": 240.0}, "harmonics": [1, 1]},
    # dopplertrack locate (PLAN Phase 3 step A) on the case's audio, date, box and flight data, nothing else of the
    # case's: its own detection, pair rule ("pair_rule" override; top2 by default) and silence filter (off by default)
    "locate": {"events": "detect, then locate's pair rule", "harmonics": [1, 1]},
}


def load_events(case: dict):
    """The case's two search events (and any extras) as EventFit, on the case audio's own timeline."""
    from dopplertrack.tracks import EventFit
    return [EventFit(**d) for d in saved_fit_dicts(case)]


def saved_fit_dicts(case: dict) -> list[dict]:
    ev = case["events"]
    if ev["mode"] != "saved_fits":
        raise ValueError(f"{case['id']}: events.mode {ev['mode']!r} has no saved fits")
    data = [json.loads(resolve(p).read_text()) for p in ev["files"]]
    if ev.get("pick"):
        (lst,) = data
        data = [lst[i - 1] for i in ev["pick"]]
    off = float(ev.get("time_offset_s", 0.0))
    out = []
    for d in data:
        d = dict(d)
        for k in ("t_cpa", "t_cpa_emit", "t_start", "t_end"):
            d[k] = d[k] + off
        out.append(d)
    return out


def pick_detected(detected: list[dict]) -> list[dict]:
    """The raw-audio profile's rule: the two highest-scoring detections, the earlier one first."""
    if len(detected) < 2:
        raise ValueError(f"detect returned {len(detected)} events; the two-event search needs two")
    top = sorted(detected, key=lambda d: d["score"], reverse=True)[:2]
    return sorted(top, key=lambda d: d["t_cpa"])


WEATHER_KEY = "use_case_weather"     # the run setting (`bench run --weather`) that applies a case's station reading


def sound_speed(case: dict, use_weather: bool = False) -> tuple[dict, dict]:
    """The case's speed of sound for the event fits and detection, as keyword arguments ({} keeps the pipeline's
    15 C default untouched), and the record's account of it. A case's station temperature is used only when the
    run asks for it (use_weather, `bench run --weather`); otherwise it is recorded and the 15 C default stands. With
    it, the geometry gives each flight its own speed from its height (geometry_kw)."""
    from dopplertrack.doppler import speed_of_sound
    w = case.get("weather") or {}
    t = w.get("temperature_c")
    if t is None or not use_weather:
        rec = {"c_m_s": speed_of_sound(), "temperature_c": None, "basis": "the pipeline's default, 15 C"}
        if t is not None:
            rec.update(basis="the pipeline's default, 15 C: the case's station reading is not used unless the run "
                             "sets use_case_weather (bench run --weather)", case_temperature_c=t, use_case_weather=False)
        return {}, rec
    c = speed_of_sound(t)
    return {"c": c}, {"c_m_s": c, "temperature_c": t,
                      "basis": "the ground temperature for the fits; for the geometry each flight's own speed at its "
                               "mid-height temperature (ground - 3.25 C per km, atmosphere.point_sound_speed)",
                      "source": w.get("source"), "station": w.get("station"),
                      "station_distance_km": w.get("station_distance_km"), "observed_utc": w.get("observed_utc")}


def cpa_cache_path(case: dict, use_weather: bool = False) -> Path:
    """The case's CPA table. A run that applies the case's temperature builds a different table (the sound speed is in
    its fingerprint), so it gets its own file, <name>_weather.npz, and switching the setting never rebuilds either."""
    p = resolve(case["search"]["cpa_cache"])
    return p.with_name(f"{p.stem}_weather{p.suffix}") if sound_speed(case, use_weather)[0] else p


def geometry_kw(case: dict, use_weather: bool = False) -> dict:
    """run_search, refine and pick_flight's speed-of-sound keywords: the fits' c, and with a station temperature
    the run uses, temperature_c, so each flight's propagation uses its own height."""
    c_kw, rec = sound_speed(case, use_weather)
    return {**c_kw, "temperature_c": rec["temperature_c"]} if c_kw else {}


def trace_paths(case: dict, key: str = "traces") -> list[Path]:
    """A case's flight data: one trace file, or consecutive days of one box."""
    t = case["flight_data"][key]
    return [resolve(p) for p in ([t] if isinstance(t, str) else t)]


def locate_cpa_cache(case: dict, cpa_cache: str) -> str:
    """The locate profile's CPA table: the case's own, or with locate_traces a file of its own beside it."""
    if "locate_traces" not in case["flight_data"]:
        return cpa_cache
    c = Path(cpa_cache)
    return str(c.with_name(f"{c.stem}-locate{c.suffix}"))


def locate_flight_data(case: dict, cpa_cache: str) -> tuple[list[Path], list[list[float]] | None, str]:
    """The locate profile's trace files, declared envelopes and CPA cache. A case's flight_data.locate_traces, cut
    with extraction metadata and the search-range margin, replaces its legacy traces for locate alone, so the other
    profiles' baselines stay on the files they were measured with; it gets a CPA cache file of its own so the two
    never rebuild each other's."""
    from dopplertrack.adsb import load_trace_metadata
    paths = trace_paths(case, "locate_traces" if "locate_traces" in case["flight_data"] else "traces")
    cpa_cache = locate_cpa_cache(case, cpa_cache)
    # a file's own measured envelope wins; the case's declared boxes stand in only for legacy files
    measured = all(p.exists() and load_trace_metadata(p).get("coverage_bbox") for p in paths)
    return paths, None if measured else day_boxes(case), cpa_cache


def day_boxes(case: dict) -> list[list[float]]:
    """The box each trace file was cut to: one box for every day, or one per day."""
    b = case["flight_data"]["extraction_box"]
    return [list(x) for x in b] if isinstance(b[0], list) else [list(b)] * len(trace_paths(case))


def search_harmonics(case: dict, profile: str) -> list[int]:
    return list(case["search"]["harmonics"]) if profile == "saved-fit" else list(PROFILES[profile]["harmonics"])


def _flight_pairs(df, segs=None) -> list[list[str]]:
    if segs is not None:
        icao = np.array([s.icao for s in segs])
        pairs = set(zip(icao[df.seg1.to_numpy()], icao[df.seg2.to_numpy()]))
    else:
        pairs = set(zip(df.icao1, df.icao2))
    return sorted([str(a), str(b)] for a, b in pairs)


def _altitude_sources(traces) -> dict:
    counts = dict(geometric=0, barometric=0, none=0, unknown=0)
    for tr in traces:
        if tr.alt_source is None:
            counts["unknown"] += len(tr)
            continue
        for source, n in zip(*np.unique(tr.alt_source, return_counts=True)):
            counts[source if source in counts else "unknown"] += int(n)
    return counts


def code_revision() -> dict:
    commit = git("rev-parse", "HEAD")
    return {"package_version": _package_version(), "git_commit": commit or unavailable("not a git checkout"),
            "git_dirty": bool(git("status", "--porcelain")) if commit else unavailable("not a git checkout")}


class Draft:
    """The parts of one result record as a run fills them in; `record()` assembles it."""

    def __init__(self, case: dict, code: dict, profile: str, log, overrides: dict | None = None):
        from dopplertrack.coverage import padded_bbox
        assert "labels" not in case, "the runner must be given the blind case"
        self.case, self.code, self.stage, self.errors = case, code, Stages(log), []
        overrides = dict(overrides or {})
        weather = bool(overrides.pop(WEATHER_KEY, False))
        fixed = sorted(set(overrides) & set(FIXED_BY_CASE))
        if fixed:
            raise ValueError(f"--search-param can't override {fixed}: they define the case's CPA table")
        # known settings replace the case's; anything else is a run_search keyword of its own
        self.search = {**case["search"], **{k: v for k, v in overrides.items() if k in SEARCH_ARGS}}
        self.extra_kwargs = {k: v for k, v in overrides.items() if k not in SEARCH_ARGS}
        s = self.search
        self.harmonics = list(overrides["harmonics"]) if "harmonics" in overrides else search_harmonics(case, profile)
        self.params = {"profile": profile, "profile_settings": PROFILES[profile], "search": s, "refine": case["refine"],
                       "search_overrides": {**overrides, **({WEATHER_KEY: True} if weather else {})},
                       "events": case["events"], "search_harmonics": self.harmonics,
                       "speed_of_sound_m_s": sound_speed(case, weather)[1]["c_m_s"],
                       "speed_of_sound": sound_speed(case, weather)[1]}
        self.c_kw, self.geo_kw = sound_speed(case, weather)[0], geometry_kw(case, weather)
        self.cpa_cache = cpa_cache_path(case, weather)
        self.inputs, self.caches, self.events, self.candidates = [], [], [], []
        self.refined = unavailable("the search did not run")
        self.funnel = {k: unavailable("the search did not run") for k in (
            "cpa_records", "before_silence_filter", "after_silence_filter", "flight_pairs_before_silence_filter",
            "flight_pairs_after_silence_filter", "scored", "unevaluated_budget")}
        self.funnel.update({k: unavailable(PER_GATE) for k in ("after_speed_gate", "after_distance_gate", "after_time_gate")})
        need = padded_bbox(tuple(s["bbox"]), s["max_range_m"])
        boxes = day_boxes(case)
        self.flight = {"traces": case["flight_data"]["traces"], "declared_extraction_box": boxes if len(boxes) > 1 else boxes[0],
                       "search_box_plus_range": [round(x, 6) for x in need],
                       "declared_box_covers_search_range": all(e[0] <= need[0] and e[1] >= need[1] and e[2] <= need[2]
                                                               and e[3] >= need[3] for e in boxes),
                       "extraction_note": case["flight_data"].get("extraction_note", "")}
        self.limits = {"altitude_sources": unavailable("the flight data was not loaded"),
                       "candidate_gaps": unavailable("the search did not run"),
                       "possible_edits": unavailable("edit detection does not exist yet (L4, S6)")}

    def add_events(self, fits: list[dict], harmonics: list[int], source: str, score_kind: str):
        hs = harmonics + [1] * (len(fits) - len(harmonics))
        for k, (f, h) in enumerate(zip(fits, hs), 1):
            self.events.append({
                "id": f"ev{k}", "source": source, "harmonics": int(h),
                "fit": {"t_heard_cpa_audio_s": f["t_cpa"], "t_emission_cpa_audio_s": f["t_cpa_emit"],
                        "t_steepest_fall_audio_s": f["t_cpa_emit"], "f0_hz": f["f0"], "speed_m_s": f["v"],
                        "slant_range_m": f["d"], "window_s": [f["t_start"], f["t_end"]], "f_pre_hz": f["f_pre"],
                        "f_post_hz": f["f_post"]},
                "diagnostics": {"score": f["score"], "score_kind": score_kind,
                                "covariance": unavailable("fits report no covariance yet (Phase 2)")},
                "assignment": unavailable("the search did not run"),
                "utc": unavailable("the search did not run")})

    def load_flight_data(self):
        """Read the case's traces, one file or consecutive days joined across midnight (adsb.join_days)."""
        from dopplertrack.adsb import join_days
        paths = trace_paths(self.case)
        traces, meta = join_days(paths)
        self.inputs += [file_entry("traces", p) for p in paths]
        if len(paths) > 1:
            self.flight["seams"] = meta.get("seams", [])
        legacy = "legacy trace file: malformed traces skipped at extraction were not counted"
        self.flight.update(traces_loaded=len(traces),
                           metadata=meta or unavailable("legacy trace file without extraction metadata (pre-Phase 0)"),
                           skipped_malformed=meta.get("scan", {}).get("malformed", unavailable(legacy)) if meta else unavailable(legacy))
        self.limits["altitude_sources"] = _altitude_sources(traces)
        return traces, meta

    def add_candidates(self, res, t_cpa1: float):
        """Best row per flight pair, ranked by score, from a search result table."""
        best = res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
        for i, row in enumerate(best.itertuples(), 1):
            offset = t_cpa1 - float(row.t_heard1) + float(row.shift)
            self.candidates.append({"rank": i, "lat": float(row.lat), "lon": float(row.lon),
                                    "flights": [str(row.icao1), str(row.icao2)],
                                    "clock": {"audio_minus_utc_s": offset, "shift_s": float(row.shift),
                                              "drift": unavailable("the clock model has no drift term yet")},
                                    "score": float(row.score), "event_scores": [float(row.s1), float(row.s2)],
                                    "mode": unavailable("candidates are not grouped into modes yet (Phase 3)")})
        if self.candidates:
            top = self.candidates[0]
            off = top["clock"]["audio_minus_utc_s"]
            for k, e in enumerate(self.events):
                e["assignment"] = ({"flight": top["flights"][k], "basis": "flight pair of the top-ranked candidate"}
                                   if k < 2 else unavailable("extra events are assigned only by refine"))
                e["utc"] = {"t_heard_cpa": e["fit"]["t_heard_cpa_audio_s"] - off,
                            "t_emission_cpa": e["fit"]["t_emission_cpa_audio_s"] - off,
                            "basis": "the top-ranked candidate's clock"}
        else:
            self.refined = unavailable("no candidate survived the search")
            for e in self.events:
                e["assignment"] = unavailable("no candidate survived the search")
                e["utc"] = unavailable("no candidate survived the search, so there is no clock")
        return best

    def write_triples(self, case_dir: Path, stages: dict):
        """Every hypothesis each stage kept, with its location, into a sidecar whose hash goes in the
        record: the comparison reads it after the hash check to see how near the truth they came.
        stages: name -> DataFrame with icao1, icao2, gidx, lat, lon (and score at the scored stage)."""
        from dopplertrack.result import sha256_file
        arrays = {}
        for name, df in stages.items():
            arrays[f"{name}__icao1"] = df["icao1"].to_numpy(str)
            arrays[f"{name}__icao2"] = df["icao2"].to_numpy(str)
            arrays[f"{name}__gidx"] = df["gidx"].to_numpy(np.int32)
            arrays[f"{name}__lat"] = df["lat"].to_numpy(np.float64)
            arrays[f"{name}__lon"] = df["lon"].to_numpy(np.float64)
            if "score" in df:
                arrays[f"{name}__score"] = df["score"].to_numpy(np.float64)
        path = case_dir / TRIPLES_FILE
        tmp = case_dir / f".{TRIPLES_FILE}.{os.getpid()}.tmp.npz"
        np.savez_compressed(tmp, **arrays)
        os.replace(tmp, path)
        self.funnel["triples_file"] = {"path": TRIPLES_FILE, "sha256": sha256_file(path), "stages": list(stages),
                                       "rows": {k: len(v) for k, v in stages.items()}}

    def add_pipeline_funnel(self, funnel: dict, flight_pairs: dict):
        """The funnel run_search reports (res.attrs["funnel"]), kept as-is and mapped onto v1's fields."""
        gate = "emission_gate" if "emission_gate" in funnel else "time_join"
        self.funnel.update(pipeline=funnel, cpa_records=funnel["cpa_rows"],
                           after_speed_gate=unavailable(PER_EVENT_GATE), after_distance_gate=unavailable(PER_EVENT_GATE),
                           after_time_gate=funnel[gate], before_silence_filter=funnel[gate],
                           after_silence_filter=funnel["silence"], scored=funnel["scored"], unevaluated_budget=0,
                           flight_pairs_before_silence_filter=flight_pairs[gate],
                           flight_pairs_after_silence_filter=flight_pairs["silence"])

    def add_refined(self, fine, extra_flights: list[str]):
        rf = self.case["refine"]
        b = fine.iloc[0]
        self.refined = {"lat": float(b.lat), "lon": float(b.lon), "score": float(b.score),
                        "event_scores": [float(b[c]) for c in fine.columns if c.startswith("s") and c[1:].isdigit()],
                        "shift_s": float(b["shift"]), "spacing_m": float(rf["spacing_m"]),
                        "half_width_m": float(rf["half_m"]), "from_rank": int(rf["rank"]), "extra_flights": extra_flights}

    def record(self) -> dict:
        from dopplertrack.coverage import ADS_B_LIMITATION
        case = self.case
        return {
            "schema_version": SCHEMA_VERSION, "kind": KIND,
            "case": {"id": case["id"], "version": case["version"]},
            "conventions": CONVENTIONS_V1,
            "provenance": {
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "code": self.code, "parameters": self.params, "inputs": self.inputs, "caches": self.caches,
                "lineage": {"raw": case["source"]["raw"], "flight_data_assets": case["flight_data"]["archive_assets"],
                            "derived": [{"path": d["path"], "sha256": d["sha256"]} for d in case["derived"]]},
            },
            "events": self.events, "candidates": self.candidates, "refined": self.refined, "funnel": self.funnel,
            "verdict": unavailable(NO_VERDICT), "region": unavailable(NO_REGION),
            "pair_rules": unavailable("a benchmark profile chooses its events (saved fits or detect's top two)"),
            "data_limitations": {"flight_data": self.flight, **self.limits, "ads_b": ADS_B_LIMITATION},
            "execution": {"errors": self.errors, "warnings": self.stage.warnings, "stages": self.stage.stages},
        }


def execute_case(case: dict, case_dir: Path, log=print, code: dict | None = None, profile: str = "saved-fit",
                 overrides: dict | None = None) -> dict:
    """Run one blind case through this revision's pipeline in-process (spectrogram, events, flight data,
    CPA table, search, refine) and return its result record. It never sees the case's labels."""
    import pandas as pd
    from dopplertrack import pipeline
    from dopplertrack.audio import Spectrogram
    from dopplertrack.search import Grid
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import EventFit

    try:
        draft = Draft(case, code or code_revision(), profile, log, overrides)
    except ValueError as exc:
        draft = Draft(case, code or code_revision(), profile, log)
        draft.errors.append(f"ValueError: {exc}")
        return draft.record()
    stage, s, rf = draft.stage, draft.search, case["refine"]
    harmonics = draft.harmonics
    terrain = Terrain() if s["dem"] else None
    try:
        with stage("spectrogram"):
            spec_path = resolve(case["spectrogram"])
            sp = Spectrogram.load(spec_path)
        draft.inputs.append(file_entry("spectrogram", spec_path))
        if profile == "saved-fit":
            with stage("events"):
                fits = saved_fit_dicts(case)
            draft.inputs += [file_entry("saved_fits", resolve(p)) for p in case["events"]["files"]]
            draft.add_events(fits, harmonics, "saved_fit", "fit objective value as saved with the fit")
        else:
            from dopplertrack.cache import cached_detections
            from dopplertrack.tracks import detect_events
            d = PROFILES[profile]["detect"]
            with stage("detect"):
                # cached on the spectrogram, the parameters and the detector's source
                detected = [e.to_dict() for e in cached_detections(sp, detect_events, f_lo=d["band_hz"][0],
                                                                   f_hi=d["band_hz"][1], harmonics=d["harmonics"],
                                                                   top=d["top"], window_s=d["window_s"], **draft.c_kw)]
            (case_dir / "detected.json").write_text(json.dumps(detected, indent=1) + "\n")
            fits = pick_detected(detected)
            draft.add_events(fits, harmonics, "detect", "detect's sweep-weighted ridge contrast")
        ev = [EventFit(**f) for f in fits]
        ev1, ev2 = ev[0], ev[1]
        with stage("flight_data"):
            traces, meta = draft.load_flight_data()
        with stage("grid"):
            grid = Grid.make(*s["bbox"], s["spacing_m"], terrain.elevation if terrain else None)
        cache_path = draft.cpa_cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        triples: dict = {}
        with stage("search"):
            res, segs = pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=tuple(harmonics[:2]),
                                            tol_s=s["tol_s"], v_tol=s["v_tol"], d_tol=tuple(s["d_tol"]),
                                            silence_d_m=s["silence_d_m"], max_range_m=s["max_range_m"],
                                            progress=False, cpa_cache=str(cache_path),
                                            trace_metadata=meta, search_bbox=tuple(s["bbox"]), triples=triples,
                                            **draft.geo_kw, **draft.extra_kwargs)
        draft.caches.append(file_entry("cpa_table", cache_path))
        draft.stage.stages += [{"name": f"search.{k}", "wall_s": round(v["wall_s"], 3), "cpu_s": round(v["cpu_s"], 3)}
                               for k, v in res.attrs.get("stages", {}).items()]
        icao = np.array([sg.icao for sg in segs])
        frames = {k: pd.DataFrame({"icao1": icao[t["seg1"]], "icao2": icao[t["seg2"]], "gidx": t["gidx"],
                                   "lat": grid.lat[t["gidx"]], "lon": grid.lon[t["gidx"]]}) for k, t in triples.items()}
        frames["scored"] = res[["icao1", "icao2", "gidx", "lat", "lon", "score"]]
        draft.add_pipeline_funnel(res.attrs["funnel"], {k: _flight_pairs(f) for k, f in frames.items()})
        draft.write_triples(case_dir, frames)
        best = draft.add_candidates(res, ev1.t_cpa)
        draft.limits["candidate_gaps"] = [w.split("search: ", 1)[1] for w in stage.warnings
                                          if w.startswith("search: ") and "candidate" in w]
        if draft.candidates:
            with stage("refine"):
                row = best.iloc[rf["rank"] - 1].copy()
                row["lat0"], row["lon0"] = grid.lat0, grid.lon0
                hs = harmonics + [1] * (len(ev) - len(harmonics))
                fine = pipeline.refine(sp, ev1, ev2, segs, row, spacing_m=rf["spacing_m"], half_m=rf["half_m"],
                                       harmonics=tuple(harmonics[:2]), elevation=terrain.elevation if terrain else None,
                                       extra=ev[2:], extra_harmonics=hs[2:], max_range_m=s["max_range_m"],
                                       **draft.geo_kw)
            draft.add_refined(fine, list(fine.attrs.get("extra_icao", [])))
    except Exception as exc:          # kept apart from the verdict: a failed run is not an abstention
        draft.errors.append(f"{type(exc).__name__}: {exc}")
        log(f"ERROR: {type(exc).__name__}: {exc}")
    if terrain is not None:
        draft.caches += [file_entry("terrain_tile", terrain._path(x, y)) for (x, y) in sorted(terrain._mem)]
    return draft.record()


# What a16b700's CLI hard-codes and so can't be given; a case asking for anything else is refused. The
# silence filter is the third fixed setting: its CLI offers 6000 m or none (--no-silence), nothing else.
FIXED_IN_CLI = {"v_tol": 0.35, "d_tol": [0.4, 2.5], "max_range_m": 12000.0}


def _stream(cmd: list[str], cwd: Path) -> str:
    """Run a command, printing its output line by line as it arrives, and return all of it."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = []
    for line in proc.stdout:
        lines.append(line)
        print(line.rstrip("\n").split("\r")[-1])
    if proc.wait():
        raise RuntimeError(f"{' '.join(cmd[:6])} ... exited with {proc.returncode}: {''.join(lines[-5:]).strip()}")
    return "".join(lines)


def _tiles_covering(bbox, zoom=12) -> list[Path]:
    """The terrain tiles a grid over bbox reads: the revision doesn't report them, so they are derived."""
    from dopplertrack.terrain import Terrain
    t = Terrain(zoom)
    n = 2 ** zoom
    def tx(lon): return int((lon + 180.0) / 360.0 * n)
    def ty(lat):
        r = np.radians(lat)
        return int((1 - np.log(np.tan(r) + 1 / np.cos(r)) / np.pi) / 2 * n)
    return [t._path(x, y) for x in range(tx(bbox[2]), tx(bbox[3]) + 1) for y in range(ty(bbox[1]), ty(bbox[0]) + 1)
            if t._path(x, y).exists()]


def execute_case_at(case: dict, case_dir: Path, rev, log=print, code: dict | None = None,
                    profile: str = "saved-fit", overrides: dict | None = None) -> dict:
    """Run one blind case through another revision's own CLI in its own environment, and turn what it
    writes into a result record. No code of that revision is imported here."""
    import re
    import pandas as pd
    from dopplertrack.result import sha256_file
    from .revisions import file_lock, verify

    draft = Draft(case, code or rev.provenance(), profile, log)
    stage, s, rf = draft.stage, case["search"], case["refine"]
    harmonics = search_harmonics(case, profile)
    try:
        weather = bool((overrides or {}).get(WEATHER_KEY, False))
        if set(overrides or {}) - {"tol_s", WEATHER_KEY}:
            raise ValueError(f"{rev.short}'s CLI takes only tol_s of the search overrides, not "
                             f"{sorted(set(overrides) - {'tol_s'})}")
        if overrides:
            draft = Draft(case, draft.code, profile, log, overrides)
            stage, s = draft.stage, draft.search
        verify(rev)
        if sound_speed(case, weather)[0]:
            raise ValueError(f"{rev.short}'s CLI has no temperature input; this run applies the case's")
        bad = {k: s[k] for k, v in FIXED_IN_CLI.items() if s[k] != v}
        if bad or s["silence_d_m"] not in (6000.0, None):
            raise ValueError(f"{rev.short}'s CLI can't take {bad or {'silence_d_m': s['silence_d_m']}}")
        with stage("spectrogram"):
            audio = resolve(case["audio"]["path"])
            spec = rev.root / "spec" / f"{case['id']}-v{case['version']}.npz"
            with file_lock(spec.with_name(spec.name + ".lock")):
                if not spec.exists():
                    tmp = spec.with_name(f".{spec.stem}.{os.getpid()}.tmp.npz")
                    try:
                        _stream(rev.cli("spectrogram", str(audio), str(tmp)), case_dir)
                        os.replace(tmp, spec)
                    finally:
                        tmp.unlink(missing_ok=True)
        draft.inputs.append(file_entry("audio", audio))
        draft.caches.append(file_entry(f"spectrogram built by {rev.short}", spec))
        case_spec = next((d for d in case["derived"] if d["path"] == case["spectrogram"]), None)
        draft.params["spectrogram_equal_to_case_spectrogram"] = (sha256_file(spec) == case_spec["sha256"]) if case_spec \
            else unavailable("the case's spectrogram has no recorded hash")
        if profile == "saved-fit":
            fits = saved_fit_dicts(case)
            draft.inputs += [file_entry("saved_fits", resolve(p)) for p in case["events"]["files"]]
            draft.add_events(fits, harmonics, "saved_fit", "fit objective value as saved with the fit")
        else:
            d = PROFILES[profile]["detect"]
            with stage("detect"):
                _stream(rev.cli("detect", str(spec), "--band", *map(str, d["band_hz"]), "--top", str(d["top"]),
                                "--harmonics", str(d["harmonics"]), "--window", str(d["window_s"]),
                                "--out", str(case_dir / "detected.json")), case_dir)
            fits = pick_detected(json.loads((case_dir / "detected.json").read_text()))
            draft.add_events(fits, harmonics, "detect", "detect's sweep-weighted ridge contrast")
        evfiles = []
        for k, f in enumerate(fits, 1):
            evfiles.append(case_dir / f"ev{k}.json")
            evfiles[-1].write_text(json.dumps(f, indent=1) + "\n")
        with stage("flight_data"):
            draft.load_flight_data()
        if len(trace_paths(case)) != 1:
            raise ValueError(f"{rev.short}'s CLI takes one trace file; this case joins {len(trace_paths(case))} days")
        tpath = trace_paths(case)[0]
        cpa = rev.root / "cpa" / f"{case['id']}-v{case['version']}.npz"
        cpa.parent.mkdir(parents=True, exist_ok=True)
        box = [str(x) for x in s["bbox"]]
        common = ["--traces", str(tpath), "--bbox", *box, "--harmonics", *map(str, harmonics[:2])] + \
                 ([] if s["dem"] else ["--no-dem"])
        with stage("search"):
            # the revision writes its CPA cache in place and keys it on sizes only: one writer per file
            with file_lock(cpa.with_name(cpa.name + ".lock")):
                out = _stream(rev.cli("search", str(spec), "--events", *map(str, evfiles[:2]), "--out",
                                      str(case_dir / "search.csv"), "--spacing", str(s["spacing_m"]), "--tol",
                                      str(s["tol_s"]), "--cpa-cache", str(cpa), *common,
                                      *([] if s["silence_d_m"] else ["--no-silence"])), case_dir)
        draft.caches.append(file_entry(f"cpa_table built by {rev.short}", cpa))
        res = pd.read_csv(case_dir / "search.csv")
        rows = re.search(r"(\d+) \(point, flight\) CPA records", out)
        unreported = f"{rev.short}'s CLI reports only the count after the silence filter"
        draft.funnel.update(cpa_records=int(rows.group(1)) if rows else unavailable(f"{rev.short} did not log it"),
                            before_silence_filter=unavailable(unreported),
                            flight_pairs_before_silence_filter=unavailable(unreported),
                            after_silence_filter=len(res), flight_pairs_after_silence_filter=_flight_pairs(res),
                            scored=len(res), unevaluated_budget=0)
        draft.limits["candidate_gaps"] = unavailable(f"{rev.short} has no candidate-gap diagnostic")
        draft.write_triples(case_dir, {"scored": res[["icao1", "icao2", "gidx", "lat", "lon", "score"]]})
        draft.add_candidates(res, fits[0]["t_cpa"])
        if draft.candidates:
            with stage("refine"):
                out = _stream(rev.cli("refine", str(spec), str(case_dir / "search.csv"), "--events",
                                      *map(str, evfiles[:2]), "--out", str(case_dir / "refine.csv"), "--rank",
                                      str(rf["rank"]), "--spacing", str(rf["spacing_m"]), "--half", str(rf["half_m"]),
                                      *common, *(["--extra", *map(str, evfiles[2:])] if len(evfiles) > 2 else [])),
                              case_dir)
            m = re.search(r"extra flights (\[.*\])", out)
            import ast
            draft.add_refined(pd.read_csv(case_dir / "refine.csv"), ast.literal_eval(m.group(1)) if m else [])
        draft.caches += [file_entry("terrain_tile", p) for p in _tiles_covering(s["bbox"])]
    except Exception as exc:          # kept apart from the verdict: a failed run is not an abstention
        draft.errors.append(f"{type(exc).__name__}: {exc}")
        log(f"ERROR: {type(exc).__name__}: {exc}")
    return draft.record()


def _package_version() -> str:
    from importlib.metadata import version
    return version("dopplertrack")


HASH_FILE = "result.json.sha256"


@contextlib.contextmanager
def private_cache(case: dict):
    """For a private case, every cache (detections, window fits, CPA tables) under the data root's private/cache/
    while it runs, and the shared root back afterwards; worker pools started inside inherit it."""
    from .cases import is_private, private_cache_root
    if not is_private(case):
        yield
        return
    before = os.environ.get("DOPPLERTRACK_CACHE")
    os.environ["DOPPLERTRACK_CACHE"] = str(private_cache_root())
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("DOPPLERTRACK_CACHE", None)
        else:
            os.environ["DOPPLERTRACK_CACHE"] = before


def bench_case(case_id: str, case_dir: Path, execute=execute_case, labels=case_labels, cases_path=None,
               log=print, code: dict | None = None, reveal: bool = False) -> dict:
    """Run one case blind, write result.json and its hash, and only then read the labels and score it. A private
    case (bench/private.py) is resolved from $DOPPLERTRACK_DATA/private/, run with its caches there, and its record
    written in the site's frame unless reveal, after a check that no position near the site is left in it."""
    from .cases import is_private
    kw = {} if cases_path is None else {"path": cases_path}
    case = blind_case(case_id, **kw)
    private = is_private(case)
    if private:
        from . import private as priv
        case = priv.resolve_case(case)
    case_dir.mkdir(parents=True, exist_ok=True)
    with private_cache(case):
        record = execute(case, case_dir, log=log, code=code or code_revision())
    if private and not reveal:
        site = priv.load_site(case["site"])
        record = priv.to_site_relative(record, case["site"], site, case_dir)
        priv.assert_no_site(record, site)
    elif private:
        record["provenance"]["parameters"]["revealed"] = "absolute coordinates, by the owner's --reveal"
    sha = write_record(case_dir / "result.json", record)
    (case_dir / HASH_FILE).write_text(f"{sha}  result.json\n")
    meta = {k: case[k] for k in ("id", "version", "group", "set", "expected_outcome")}
    return compare_case(case_dir, meta, lambda: labels(case_id, case["version"], **kw))


def _distance_m(lat1, lon1, lat2, lon2) -> float:
    from dopplertrack.geo import haversine_m
    return float(haversine_m(lat1, lon1, lat2, lon2))


def _distances_m(lat, lon, lat0, lon0) -> np.ndarray:
    from dopplertrack.geo import haversine_m
    return np.atleast_1d(np.asarray(haversine_m(np.asarray(lat), np.asarray(lon), lat0, lon0), float))


def compare_case(case_dir: Path, meta: dict, read_labels) -> dict:
    """Score one record against its labels. The record must still hash to what was written beside it
    before the labels were read; if it doesn't, it is discarded and the labels are never opened."""
    entry = {"case": meta["id"], "version": meta["version"], "group": meta["group"], "set": meta["set"],
             "expected_outcome": meta["expected_outcome"]}
    try:
        expected = (case_dir / HASH_FILE).read_text().split()[0]
        record = read_record(case_dir / "result.json", expected_sha256=expected)
    except (OSError, IndexError, RecordError, ValueError) as exc:
        return {**entry, "status": "discarded", "reason": f"record does not match the hash written before the "
                f"truth was read: {exc}"}
    # a run that failed is reported as an error, never scored as if it had abstained or found nothing
    tf = record["funnel"].get("triples_file")
    triples = None
    if tf:
        from dopplertrack.result import sha256_file
        try:
            ok = sha256_file(case_dir / tf["path"]) == tf["sha256"]
        except OSError:
            ok = False
        if not ok:
            return {**entry, "status": "discarded", "reason": f"{tf['path']} does not match the hash in the record"}
        with np.load(case_dir / tf["path"]) as z:
            triples = {k: z[k] for k in z.files}
    entry.update(status="error" if record["execution"]["errors"] else "scored", record_sha256=expected,
                 stages=record["execution"]["stages"], errors=record["execution"]["errors"],
                 search_overrides=record["provenance"]["parameters"].get("search_overrides", {}))
    lab = read_labels()
    ref = lab["reference"]
    relative = record.get("frame") == "site-relative"     # a private case: offsets from the site, the reference
    if "site" in ref and not relative:                   # a revealed private record: the site, read in place
        from .private import load_site
        ref = load_site(ref["site"])

    def err(item):
        if relative:
            return math.hypot(item["offset_m"]["east"], item["offset_m"]["north"])
        return _distance_m(item["lat"], item["lon"], ref["lat"], ref["lon"])
    box = record["provenance"]["parameters"]["search"]["bbox"]
    if relative:
        s_, n_, w_, e_ = box["offset_box_m"]
        entry["box_centre_error_m"] = math.hypot((w_ + e_) / 2, (s_ + n_) / 2)
    else:
        entry["box_centre_error_m"] = _distance_m((box[0] + box[1]) / 2, (box[2] + box[3]) / 2, ref["lat"], ref["lon"])
    cands = record["candidates"]
    pair = lab.get("true_pair")
    if cands:
        entry["top_error_m"] = err(cands[0])
        entry["top_pair"] = cands[0]["flights"]
        entry["margin_pct"] = (100.0 * (cands[0]["score"] - cands[1]["score"]) / cands[1]["score"]
                               if len(cands) > 1 and cands[1]["score"] > 0 else unavailable("fewer than two flight pairs"))
    else:
        entry["top_error_m"] = entry["margin_pct"] = unavailable("no candidates")
    entry["flight_pairs"] = len(cands)
    v = record["verdict"]
    if isinstance(v, dict) and "outcome" in v:
        entry["verdict"] = {"outcome": v["outcome"], "reason_codes": v["reason_codes"]}
        want = lab.get("expected_verdict")    # a failure case's labels name the verdict it should end in
        if want:
            entry["verdict_as_expected"] = (v["outcome"] == want["outcome"]
                                            and set(want["reason_codes"]) <= set(v["reason_codes"]))
    ref_ = record["refined"]
    entry["refined_error_m"] = (err(ref_) if isinstance(ref_, dict) and ("lat" in ref_ or "offset_m" in ref_)
                                else unavailable("no refinement"))
    if pair:
        ranks = [c["rank"] for c in cands if c["flights"] == list(pair)]
        entry["true_pair_rank"] = ranks[0] if ranks else None
        f = record["funnel"]
        entry["true_pair_survived"] = {
            stage: (list(pair) in f[key] if isinstance(f[key], list) else f[key])
            for stage, key in (("speed_distance_time_gates", "flight_pairs_before_silence_filter"),
                               ("silence_filter", "flight_pairs_after_silence_filter"))}
        if triples is None:
            for k in ("true_pair_near_reference", "true_pair_within_refine_reach", "true_pair_min_distance_m"):
                entry[k] = unavailable("the record has no triples file")
        else:
            reach = record["provenance"]["parameters"].get("refine", {}).get("half_m")
            nearest = {}
            for stg in tf["stages"]:
                m = (triples[f"{stg}__icao1"] == pair[0]) & (triples[f"{stg}__icao2"] == pair[1])
                d = (np.hypot(triples[f"{stg}__east"][m], triples[f"{stg}__north"][m]) if relative else
                     _distances_m(triples[f"{stg}__lat"][m], triples[f"{stg}__lon"][m], ref["lat"], ref["lon"]))
                nearest[stg] = float(d.min()) if len(d) else None
            # decided at the stage that reaches scoring; the earlier stages say where it was lost
            near = nearest.get("scored")
            entry["true_pair_min_distance_m"] = nearest
            entry["true_pair_near_reference"] = near is not None and near <= NEAR_REFERENCE_M
            entry["true_pair_within_refine_reach"] = (near is not None and near <= float(reach)) if reach is not None \
                else unavailable("the record has no refine half-width")
    else:
        entry["true_pair_rank"] = entry["true_pair_survived"] = unavailable("the case has no true flight pair in its box")
        for k in ("true_pair_near_reference", "true_pair_within_refine_reach", "true_pair_min_distance_m"):
            entry[k] = unavailable("the case has no true flight pair in its box")
    entry["outcome_met"] = unavailable(NO_VERDICT)
    for k in ("detection", "association", "fits", "verdicts", "region_coverage"):
        entry[k] = unavailable("not produced by today's pipeline")
    return entry


def new_run(topic: str) -> Path:
    out = subprocess.run([sys.executable, str(REPO / "tools" / "data" / "new_run.py"), topic], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout.strip()
    return Path(out)


def execute_case_locate(case: dict, case_dir: Path, log=print, code: dict | None = None,
                        overrides: dict | None = None) -> dict:
    """The case through dopplertrack locate: its spectrogram, flight-data date, box and trace files, and nothing of
    its fits. Overrides: pair_rule (default locate's, comparable), silence_d_m (default the case's; null turns the
    filter off) and clock_gate (default true: the case's stated start time and its uncertainty gate each pair's
    clock; false turns it off)."""
    from dopplertrack import locate as loc
    assert "labels" not in case, "the runner must be given the blind case"
    overrides = dict(overrides or {})
    weather = bool(overrides.get(WEATHER_KEY, False))
    unknown = set(overrides) - {"pair_rule", "silence_d_m", "clock_gate", WEATHER_KEY}
    st = case["start_time"]
    gate = overrides.get("clock_gate", True)
    start_utc = (datetime.datetime.fromisoformat(str(st["utc"]).replace("Z", "+00:00")).timestamp()
                 if gate else None)
    s = case["search"]
    paths, envelope, cpa_cache = locate_flight_data(case, str(cpa_cache_path(case, weather)))
    cfg = loc.LocateConfig(spacing_m=s["spacing_m"], max_range_m=s["max_range_m"], tol_s=s["tol_s"], v_tol=s["v_tol"],
                           d_tol=tuple(s["d_tol"]), silence_d_m=overrides.get("silence_d_m", s["silence_d_m"]),
                           pair_rule=overrides.get("pair_rule", loc.LocateConfig.pair_rule), dem=s["dem"], c=sound_speed(case, weather)[0].get("c"),
                           temperature_c=sound_speed(case, weather)[1]["temperature_c"],
                           refine_spacing_m=case["refine"]["spacing_m"], refine_half_m=case["refine"]["half_m"],
                           cpa_cache=cpa_cache, envelope=envelope, start_utc=start_utc,
                           start_tol_s=float(st["uncertainty_s"]) if gate else None,
                           extra={"search_overrides": overrides, "speed_of_sound": sound_speed(case, weather)[1]})
    record = None
    try:
        if unknown:
            raise ValueError(f"the locate profile takes only pair_rule and silence_d_m overrides, not {sorted(unknown)}")
        out = loc.locate(resolve(case["spectrogram"]), case["flight_data"]["date"], s["bbox"], paths, cfg,
                         out_dir=case_dir, code=code or code_revision(), log=log)
        record = out.record
        (case_dir / "summary.txt").write_text("\n".join(out.summary) + "\n")
        for line in out.summary:
            log(line)
    except Exception as exc:          # a crash is an execution error, never a verdict
        log(f"ERROR: {type(exc).__name__}: {exc}")
        draft = Draft(case, code or code_revision(), "locate", log)
        draft.errors.append(f"{type(exc).__name__}: {exc}")
        return draft.record()
    record["case"] = {"id": case["id"], "version": case["version"]}
    record["provenance"]["parameters"]["search"] = s        # compare_case reads the box and refine width from here
    record["provenance"]["parameters"]["refine"] = case["refine"]
    return record


def _executor(revision: str | None, profile: str, log, code: dict | None = None, overrides: dict | None = None):
    import functools
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    if profile == "locate":
        if revision is not None:
            raise ValueError("the locate profile runs this checkout only")
        return code or code_revision(), functools.partial(execute_case_locate, overrides=overrides)
    if revision is None:
        return code or code_revision(), functools.partial(execute_case, profile=profile, overrides=overrides)
    from .revisions import ensure_revision
    rev = ensure_revision(revision, log=log)
    return rev.provenance(), functools.partial(execute_case_at, rev=rev, profile=profile, overrides=overrides)


def parse_overrides(items: list[str]) -> dict:
    """KEY=VALUE pairs, each value read as JSON when it parses (12, null, [0.4, 2.5]) and as a string otherwise."""
    out = {}
    for item in items:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise ValueError(f"--search-param {item!r} is not KEY=VALUE")
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            out[key] = raw
    return out


def overrides_tag(overrides: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()[:8]


def run_one(cid: str, run_dir: Path, execute, code: dict, log=print, reveal: bool = False) -> dict:
    """One case into run_dir/<cid>/, with its log beside it; the scoreboard entry also goes to entry.json."""
    case_dir = run_dir / cid
    case_dir.mkdir(parents=True, exist_ok=True)
    with open(case_dir / "run.log", "w") as fh:
        def case_log(msg, fh=fh):
            print(msg, file=fh, flush=True)
            log(msg)
        w0 = time.perf_counter()
        entry = bench_case(cid, case_dir, execute=execute, log=case_log, code=code, reveal=reveal)
        log(f"{cid}: {entry['status']} in {time.perf_counter() - w0:.0f} s")
    tmp = case_dir / ".entry.json.tmp"
    tmp.write_text(json.dumps(entry, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, case_dir / "entry.json")
    return entry


def shard_of(case_ids: list[str], shard: str | None) -> list[str]:
    """Shard "i/n" (1-based) of the cases: every n-th of them in sorted order, so n boxes split one run."""
    if not shard:
        return list(case_ids)
    i, sep, n = shard.partition("/")
    if not (sep and i.isdigit() and n.isdigit() and 1 <= int(i) <= int(n)):
        raise ValueError(f"--shard must be i/n with 1 <= i <= n, not {shard!r}")
    return sorted(case_ids)[int(i) - 1::int(n)]


RUN_KEYS = ("tier", "profile", "search_overrides", "code")


def check_resumable(info: dict, want: dict, where) -> None:
    """A stopped run continues, or several runs merge, only from one clean commit with the same settings."""
    diff = [k for k in RUN_KEYS if info.get(k) != want.get(k)]
    if diff:
        raise ValueError(f"{where}: its run.json differs in {diff}, so its cases can't be combined with this run")
    if want["code"].get("git_dirty") is not False:
        raise ValueError(f"{where}: the code had uncommitted changes, so a stopped run can't be told apart from an "
                         "edited one; commit and start a new run")


def write_results(run_dir: Path, info: dict, case_ids: list[str], crashed: dict | None = None) -> dict:
    """results.json from every case of the run that has an entry.json; `complete` says whether all of them have.
    A case whose process died has no entry, so a resumed run runs it again; `crashed` says why it died."""
    entries = [json.loads((run_dir / c / "entry.json").read_text()) for c in case_ids
               if (run_dir / c / "entry.json").exists()]
    doc = {"schema": 1, "tier": info["tier"], "profile": info["profile"], "search_overrides": info["search_overrides"],
           "code": info["code"], "git_commit": info["code"]["git_commit"], "git_dirty": info["code"]["git_dirty"],
           "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "complete": len(entries) == len(case_ids),
           "missing": [c for c in case_ids if not (run_dir / c / "entry.json").exists()], "cases": entries,
           "crashed": dict(crashed or {})}
    tmp = run_dir / ".results.json.tmp"
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, run_dir / "results.json")
    return doc


def run_bench(case_ids: list[str], tier: str = "t2", run_dir: Path | None = None, log=print,
              revision: str | None = None, profile: str = "saved-fit", parallel: int = 1,
              overrides: dict | None = None, shard: str | None = None, resume: bool = False,
              reveal: bool = False) -> Path:
    """Run cases into a new run folder (or `run_dir`) and collect their scoreboard entries in results.json.
    revision: None runs this checkout in-process; any other commit-ish is exported, verified and run
    through its own CLI (bench/revisions.py). parallel > 1 runs that many cases at once, each in its own
    process (`bench run-case`), so stage logs and timings never mix. shard "i/n" runs only that share of the
    cases, for n boxes; `merge_runs` puts the shards together. resume continues a stopped run in run_dir: a case
    with an entry.json is kept, and the rest run. results.json is rewritten as each case finishes."""
    # the code revision is read once, before anything runs, so an edit during a long run can't relabel it
    overrides = dict(overrides or {})
    case_ids = shard_of(case_ids, shard)
    excluded = [c for c in case_ids if profile not in case_profiles(latest_case(c))]
    if excluded:
        raise ValueError(f"{excluded} don't run under the {profile} profile (their cases' profiles field)")
    code, execute = _executor(revision, profile, log, overrides=overrides)
    commit = code["git_commit"]
    from .cases import is_private
    private = [c for c in case_ids if is_private(latest_case(c))]
    if private and len(private) != len(case_ids):
        raise ValueError(f"{private} are private and can't share a run folder with public cases")
    if private and (revision is not None or parallel > 1):
        raise ValueError("private cases run in-process from this checkout only")
    if resume and run_dir is None:
        raise ValueError("resume needs the stopped run's --run-dir")
    if private and run_dir is not None and not Path(run_dir).resolve().is_relative_to(
            (data_root() / "private").resolve()):
        raise ValueError(f"a private case's run folder must be under {data_root() / 'private'}")
    if private and run_dir is None:
        from .private import new_private_run
        run_dir = new_private_run(f"bench-{(commit if isinstance(commit, str) else 'nogit')[:7]}-{profile}-{tier}")
    if run_dir is None:
        tag = f"-o{overrides_tag(overrides)}" if overrides else ""
        sh = f"-s{shard.replace('/', 'of')}" if shard else ""
        run_dir = new_run(f"bench-{(commit if isinstance(commit, str) else 'nogit')[:7]}-{profile}-{tier}{tag}{sh}")
    info_path = run_dir / "run.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    want = {"tier": tier, "profile": profile, "search_overrides": overrides, "code": code}
    done = [c for c in case_ids if (run_dir / c / "entry.json").exists()]
    if resume and done:      # with nothing finished yet a resume is a fresh start, so one command serves both
        check_resumable(info, want, run_dir)
        log(f"resuming {run_dir}: {len(done)} of {len(case_ids)} cases already have entries")
    elif done:
        raise ValueError(f"{run_dir} already has entries for {done}; pass --resume to continue it")
    info.update(command=sys.argv, cases=case_ids, shard=shard, parallel=parallel, **want)
    info.setdefault("attempts", []).append(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    todo = [c for c in case_ids if c not in done]
    if parallel <= 1:
        info_path.write_text(json.dumps(info, indent=1) + "\n")
        for cid in todo:
            run_one(cid, run_dir, execute, code, log, reveal=reveal)
            write_results(run_dir, info, case_ids)
    else:
        # each case's own pools get an equal share of the cores, so N cases never start N full-size pools
        from dopplertrack.parallel import JOBS_ENV, default_jobs
        child_env = {**os.environ, JOBS_ENV: os.environ.get(JOBS_ENV) or str(max(1, default_jobs() // parallel))}
        info["jobs_per_case"] = int(child_env[JOBS_ENV])
        info_path.write_text(json.dumps(info, indent=1) + "\n")
        pending, running, crashed = list(todo), {}, {}
        while pending or running:
            while pending and len(running) < parallel:
                cid = pending.pop(0)
                (run_dir / cid).mkdir(parents=True, exist_ok=True)
                cmd = [sys.executable, "-m", "bench", "run-case", "--run-dir", str(run_dir), "--profile", profile,
                       "--code-json", json.dumps(code), "--overrides-json", json.dumps(overrides), cid] + \
                    (["--revision", revision] if revision else [])
                out = open(run_dir / cid / "process.log", "w")
                running[cid] = (subprocess.Popen(cmd, cwd=REPO, stdout=out, stderr=subprocess.STDOUT, env=child_env), out)
                log(f"{cid}: started")
            for cid, (proc, out) in list(running.items()):
                if proc.poll() is not None:
                    out.close()
                    del running[cid]
                    if (run_dir / cid / "entry.json").exists():
                        log(f"{cid}: {json.loads((run_dir / cid / 'entry.json').read_text())['status']}")
                    else:
                        tail = (run_dir / cid / "process.log").read_text().strip().splitlines()[-3:]
                        crashed[cid] = f"bench run-case exited with {proc.returncode}: " + " | ".join(tail)
                        log(f"{cid}: crashed: {crashed[cid]}")
                    write_results(run_dir, info, case_ids, crashed)
            time.sleep(2)
        write_results(run_dir, info, case_ids, crashed)
        return run_dir
    write_results(run_dir, info, case_ids)
    return run_dir


def merge_runs(out_dir: Path, sources: list[Path], log=print) -> dict:
    """Copy the case folders of shard or stopped runs into out_dir (a new run folder, or one of them) and write its
    results.json over all of them. Every source must be the same clean commit, profile, tier and overrides; a case
    two sources both finished must have the same record hash, or the merge refuses."""
    import shutil
    infos = [(src, json.loads((src / "run.json").read_text())) for src in sources]
    if infos[0][1].get("tier") == "t1":
        from .tier1 import merge_tier1
        merge_tier1(out_dir, sources, log)
        return {}
    want = {k: infos[0][1].get(k) for k in RUN_KEYS}
    for src, info in infos:
        check_resumable(info, want, src)
    cases, sha = [], {}
    for src, info in infos:
        for cid in info.get("cases", []):
            if cid not in cases:
                cases.append(cid)
            ep = src / cid / "entry.json"
            if not ep.exists():
                continue
            entry = json.loads(ep.read_text())
            if cid in sha:
                if sha[cid] != entry.get("record_sha256"):
                    raise ValueError(f"{cid}: {src} and an earlier source finished it with different records")
                continue
            sha[cid] = entry.get("record_sha256")
            if src.resolve() != out_dir.resolve():
                if (out_dir / cid).exists():
                    raise ValueError(f"{out_dir} has an unfinished folder for {cid}; merge into a new run folder")
                shutil.copytree(src / cid, out_dir / cid)
    info_path = out_dir / "run.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    info.update(want, cases=cases, merged_from=[str(s) for s in sources])
    info_path.write_text(json.dumps(info, indent=1) + "\n")
    doc = write_results(out_dir, info, cases)
    log(f"merged {len(doc['cases'])} of {len(cases)} cases into {out_dir}" +
        (f"; missing {doc['missing']}" if doc["missing"] else ""))
    return doc


METRICS = ("true_pair_rank", "true_pair_near_reference", "true_pair_within_refine_reach", "flight_pairs", "margin_pct",
           "top_error_m", "refined_error_m", "box_centre_error_m")


def _fmt(v) -> str:
    if isinstance(v, dict) and "unavailable" in v:
        return "n/a"
    if v is None:
        return "absent"
    return f"{v:.1f}" if isinstance(v, float) else str(v)


def compare_runs(a: Path, b: Path) -> str:
    """A table of each case's scoreboard numbers in run a and run b, with b − a where both are numbers."""
    ra, rb = (json.loads((Path(p) / "results.json").read_text()) for p in (a, b))
    ca, cb = ({e["case"]: e for e in r["cases"]} for r in (ra, rb))
    def head(name, path, r):
        return (f"{name}: {path} ({str(r.get('git_commit') or '?')[:9]}{' dirty' if r.get('git_dirty') is True else ''}, "
                f"{r.get('profile', 'saved-fit')}{', overrides ' + json.dumps(r['search_overrides']) if r.get('search_overrides') else ''})")
    lines = [head("a", a, ra), head("b", b, rb), ""]
    for cid in sorted(set(ca) | set(cb)):
        ea, eb = ca.get(cid, {}), cb.get(cid, {})
        lines.append(f"{cid}  [{ea.get('status', 'missing')} -> {eb.get('status', 'missing')}]"
                     + ("  record changed" if ea.get("record_sha256") != eb.get("record_sha256") else "  record identical"))
        for m in METRICS + ("stage_wall_s",):
            va = sum(s["wall_s"] for s in ea.get("stages", [])) if m == "stage_wall_s" else ea.get(m)
            vb = sum(s["wall_s"] for s in eb.get("stages", [])) if m == "stage_wall_s" else eb.get(m)
            delta = ""
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (va, vb)):
                delta = f"  {vb - va:+.1f}"
            lines.append(f"  {m:<20} {_fmt(va):>12} {_fmt(vb):>12}{delta}")
    return "\n".join(lines)
