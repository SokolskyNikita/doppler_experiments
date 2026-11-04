"""Run benchmark cases through today's pipeline, write each `result.json` and its hash, then score it.

The order is the point (PLAN.md 5.5): `execute_case` sees the case without its labels, `bench_case`
writes the record and `result.json.sha256` before anything reads a label, and `compare_case` refuses a
record whose bytes no longer match the hash written beside it."""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import resource
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

from dopplertrack.result import (CONVENTIONS_V1, KIND, SCHEMA_VERSION, RecordError, file_entry, read_record,
                                 unavailable, write_record)

from .cases import REPO, blind_case, case_labels, resolve

NO_VERDICT = "no verdict or abstention exists before Phase 4"
NO_REGION = "no uncertainty region exists before Phase 4"
PER_GATE = ("pair_candidates applies the speed, distance and time gates in one call and run_search returns no "
            "per-gate counts; filled once run_search returns its funnel")


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


def load_events(case: dict):
    """The case's two search events (and any extras) as EventFit, on the case audio's own timeline."""
    from dopplertrack.tracks import EventFit
    ev = case["events"]
    if ev["mode"] != "saved_fits":
        raise NotImplementedError("detect-mode events arrive with the raw-audio baseline")
    data = [json.loads(resolve(p).read_text()) for p in ev["files"]]
    if ev.get("pick"):
        (lst,) = data
        data = [lst[i - 1] for i in ev["pick"]]
    off = float(ev.get("time_offset_s", 0.0))
    fits = []
    for d in data:
        d = dict(d)
        for k in ("t_cpa", "t_cpa_emit", "t_start", "t_end"):
            d[k] = d[k] + off
        fits.append(EventFit(**d))
    return fits


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


def execute_case(case: dict, case_dir: Path, log=print, code: dict | None = None) -> dict:
    """Run one blind case through spectrogram, events, flight data, CPA table, search and refine, and
    return its result record. It never sees the case's labels."""
    from dopplertrack import pipeline
    from dopplertrack.adsb import load_trace_metadata, load_traces
    from dopplertrack.audio import Spectrogram
    from dopplertrack.coverage import ADS_B_LIMITATION, padded_bbox
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.search import Grid, pair_candidates
    from dopplertrack.terrain import Terrain

    assert "labels" not in case, "the runner must be given the blind case"
    code = code or code_revision()
    s, rf = case["search"], case["refine"]
    stage = Stages(log)
    errors: list[str] = []
    params = {"search": s, "refine": rf, "events": case["events"], "speed_of_sound_m_s": speed_of_sound()}
    inputs, caches = [], []
    events, candidates, refined = [], [], unavailable("the search did not run")
    funnel = {k: unavailable("the search did not run") for k in (
        "cpa_records", "before_silence_filter", "after_silence_filter", "flight_pairs_before_silence_filter",
        "flight_pairs_after_silence_filter", "scored", "unevaluated_budget")}
    funnel.update({k: unavailable(PER_GATE) for k in ("after_speed_gate", "after_distance_gate", "after_time_gate")})
    bbox = tuple(s["bbox"])
    envelope = tuple(case["flight_data"]["extraction_box"])
    need = padded_bbox(bbox, s["max_range_m"])
    flight = {"traces": case["flight_data"]["traces"], "declared_extraction_box": list(envelope),
              "search_box_plus_range": [round(x, 6) for x in need],
              "declared_box_covers_search_range": bool(envelope[0] <= need[0] and envelope[1] >= need[1]
                                                       and envelope[2] <= need[2] and envelope[3] >= need[3]),
              "extraction_note": case["flight_data"].get("extraction_note", "")}
    limits = {"altitude_sources": unavailable("the flight data was not loaded"),
              "candidate_gaps": unavailable("the search did not run"),
              "possible_edits": unavailable("edit detection does not exist yet (L4, S6)")}
    terrain = Terrain() if s["dem"] else None
    try:
        with stage("spectrogram"):
            spec_path = resolve(case["spectrogram"])
            sp = Spectrogram.load(spec_path)
        inputs.append(file_entry("spectrogram", spec_path))
        with stage("events"):
            fits = load_events(case)
        for p in case["events"].get("files", []):
            inputs.append(file_entry("saved_fits", resolve(p)))
        harmonics = list(s["harmonics"])
        hs = harmonics + [1] * (len(fits) - len(harmonics))
        for k, (f, h) in enumerate(zip(fits, hs), 1):
            events.append({
                "id": f"ev{k}", "source": "saved_fit", "harmonics": int(h),
                "fit": {"t_heard_cpa_audio_s": f.t_cpa, "t_emission_cpa_audio_s": f.t_cpa_emit,
                        "t_steepest_fall_audio_s": f.t_cpa_emit, "f0_hz": f.f0, "speed_m_s": f.v,
                        "slant_range_m": f.d, "window_s": [f.t_start, f.t_end], "f_pre_hz": f.f_pre, "f_post_hz": f.f_post},
                "diagnostics": {"score": f.score, "score_kind": "fit objective value as saved with the fit",
                                "covariance": unavailable("fits report no covariance yet (Phase 2)")},
                "assignment": unavailable("the search did not run"),
                "utc": unavailable("the search did not run")})
        with stage("flight_data"):
            tpath = resolve(case["flight_data"]["traces"])
            traces = load_traces(tpath)
            meta = load_trace_metadata(tpath)
        inputs.append(file_entry("traces", tpath))
        flight["traces_loaded"] = len(traces)
        flight["metadata"] = meta or unavailable("legacy trace file without extraction metadata (pre-Phase 0)")
        flight["skipped_malformed"] = meta.get("scan", {}).get("malformed", unavailable(
            "legacy trace file: malformed traces skipped at extraction were not counted")) if meta else unavailable(
            "legacy trace file: malformed traces skipped at extraction were not counted")
        limits["altitude_sources"] = _altitude_sources(traces)
        with stage("grid"):
            grid = Grid.make(*bbox, s["spacing_m"], terrain.elevation if terrain else None)
        cache_path = resolve(s["cpa_cache"])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        ev1, ev2 = fits[0], fits[1]
        with stage("search"):
            res, segs = pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=tuple(harmonics[:2]),
                                            tol_s=s["tol_s"], v_tol=s["v_tol"], d_tol=tuple(s["d_tol"]),
                                            silence_d_m=s["silence_d_m"], max_range_m=s["max_range_m"],
                                            progress=False, cpa_cache=str(cache_path),
                                            trace_metadata=meta, search_bbox=bbox)
        caches.append(file_entry("cpa_table", cache_path))
        with stage("funnel"):
            # run_search keeps its intermediate counts to itself; the cached table makes recounting cheap
            cpa = pipeline.cached_cpa_table(grid, segs, s["max_range_m"], speed_of_sound(), str(cache_path))
            v_tol, (dlo, dhi) = s["v_tol"], s["d_tol"]
            gated = pair_candidates(cpa, ev2.t_cpa - ev1.t_cpa, tol_s=s["tol_s"],
                                    v1=(ev1.v * (1 - v_tol), ev1.v * (1 + v_tol)), d1=(ev1.d * dlo, ev1.d * dhi),
                                    v2=(ev2.v * (1 - v_tol), ev2.v * (1 + v_tol)), d2=(ev2.d * dlo, ev2.d * dhi),
                                    silence_d_m=None)
            funnel.update(cpa_records=len(cpa), before_silence_filter=len(gated), after_silence_filter=len(res),
                          flight_pairs_before_silence_filter=_flight_pairs(gated, segs),
                          flight_pairs_after_silence_filter=_flight_pairs(res), scored=len(res), unevaluated_budget=0)
            del cpa, gated
        best = res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
        for i, row in enumerate(best.itertuples(), 1):
            offset = ev1.t_cpa - float(row.t_heard1) + float(row.shift)
            candidates.append({"rank": i, "lat": float(row.lat), "lon": float(row.lon),
                               "flights": [str(row.icao1), str(row.icao2)],
                               "clock": {"audio_minus_utc_s": offset, "shift_s": float(row.shift),
                                         "drift": unavailable("the clock model has no drift term yet")},
                               "score": float(row.score), "event_scores": [float(row.s1), float(row.s2)],
                               "mode": unavailable("candidates are not grouped into modes yet (Phase 3)")})
        limits["candidate_gaps"] = [w.split("search: ", 1)[1] for w in stage.warnings
                                    if w.startswith("search: ") and "candidate" in w]
        if candidates:
            top = candidates[0]
            for e, icao in zip(events, top["flights"]):
                e["assignment"] = {"flight": icao, "basis": "flight pair of the top-ranked candidate"}
            for e in events:
                off = top["clock"]["audio_minus_utc_s"]
                e["utc"] = {"t_heard_cpa": e["fit"]["t_heard_cpa_audio_s"] - off,
                            "t_emission_cpa": e["fit"]["t_emission_cpa_audio_s"] - off,
                            "basis": "the top-ranked candidate's clock"}
            for e in events[2:]:
                e["assignment"] = unavailable("extra events are assigned only by refine")
            with stage("refine"):
                row = best.iloc[rf["rank"] - 1].copy()
                row["lat0"], row["lon0"] = grid.lat0, grid.lon0
                fine = pipeline.refine(sp, ev1, ev2, segs, row, spacing_m=rf["spacing_m"], half_m=rf["half_m"],
                                       harmonics=tuple(harmonics[:2]), elevation=terrain.elevation if terrain else None,
                                       extra=fits[2:], extra_harmonics=hs[2:], max_range_m=s["max_range_m"])
            b = fine.iloc[0]
            refined = {"lat": float(b.lat), "lon": float(b.lon), "score": float(b.score),
                       "event_scores": [float(b[c]) for c in fine.columns if c.startswith("s") and c[1:].isdigit()],
                       "shift_s": float(b["shift"]), "spacing_m": float(rf["spacing_m"]), "half_width_m": float(rf["half_m"]),
                       "from_rank": int(rf["rank"]), "extra_flights": list(fine.attrs.get("extra_icao", []))}
        else:
            refined = unavailable("no candidate survived the search")
            for e in events:
                e["assignment"] = unavailable("no candidate survived the search")
                e["utc"] = unavailable("no candidate survived the search, so there is no clock")
    except Exception as exc:          # kept apart from the verdict: a failed run is not an abstention
        errors.append(f"{type(exc).__name__}: {exc}")
        log(f"ERROR: {type(exc).__name__}: {exc}")
    if terrain is not None:
        for (x, y) in sorted(terrain._mem):
            caches.append(file_entry("terrain_tile", terrain._path(x, y)))
    return {
        "schema_version": SCHEMA_VERSION, "kind": KIND,
        "case": {"id": case["id"], "version": case["version"]},
        "conventions": CONVENTIONS_V1,
        "provenance": {
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "code": code,
            "parameters": params, "inputs": inputs, "caches": caches,
            "lineage": {"raw": case["source"]["raw"], "flight_data_assets": case["flight_data"]["archive_assets"],
                        "derived": [{"path": d["path"], "sha256": d["sha256"]} for d in case["derived"]]},
        },
        "events": events, "candidates": candidates, "refined": refined, "funnel": funnel,
        "verdict": unavailable(NO_VERDICT), "region": unavailable(NO_REGION),
        "data_limitations": {"flight_data": flight, **limits, "ads_b": ADS_B_LIMITATION},
        "execution": {"errors": errors, "warnings": stage.warnings, "stages": stage.stages},
    }


def _package_version() -> str:
    from importlib.metadata import version
    return version("dopplertrack")


HASH_FILE = "result.json.sha256"


def bench_case(case_id: str, case_dir: Path, execute=execute_case, labels=case_labels, cases_path=None,
               log=print, code: dict | None = None) -> dict:
    """Run one case blind, write result.json and its hash, and only then read the labels and score it."""
    kw = {} if cases_path is None else {"path": cases_path}
    case = blind_case(case_id, **kw)
    case_dir.mkdir(parents=True, exist_ok=True)
    record = execute(case, case_dir, log=log, code=code or code_revision())
    sha = write_record(case_dir / "result.json", record)
    (case_dir / HASH_FILE).write_text(f"{sha}  result.json\n")
    meta = {k: case[k] for k in ("id", "version", "group", "set", "expected_outcome")}
    return compare_case(case_dir, meta, lambda: labels(case_id, case["version"], **kw))


def _distance_m(lat1, lon1, lat2, lon2) -> float:
    from dopplertrack.geo import haversine_m
    return float(haversine_m(lat1, lon1, lat2, lon2))


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
    entry.update(status="scored", record_sha256=expected,
                 stages=record["execution"]["stages"], errors=record["execution"]["errors"])
    lab = read_labels()
    ref = lab["reference"]
    box = record["provenance"]["parameters"]["search"]["bbox"]
    entry["box_centre_error_m"] = _distance_m((box[0] + box[1]) / 2, (box[2] + box[3]) / 2, ref["lat"], ref["lon"])
    cands = record["candidates"]
    pair = lab.get("true_pair")
    if cands:
        entry["top_error_m"] = _distance_m(cands[0]["lat"], cands[0]["lon"], ref["lat"], ref["lon"])
        entry["top_pair"] = cands[0]["flights"]
        entry["margin_pct"] = (100.0 * (cands[0]["score"] - cands[1]["score"]) / cands[1]["score"]
                               if len(cands) > 1 and cands[1]["score"] > 0 else unavailable("fewer than two flight pairs"))
    else:
        entry["top_error_m"] = entry["margin_pct"] = unavailable("no candidates")
    entry["flight_pairs"] = len(cands)
    ref_ = record["refined"]
    entry["refined_error_m"] = (_distance_m(ref_["lat"], ref_["lon"], ref["lat"], ref["lon"])
                                if isinstance(ref_, dict) and "lat" in ref_ else unavailable("no refinement"))
    if pair:
        ranks = [c["rank"] for c in cands if c["flights"] == list(pair)]
        entry["true_pair_rank"] = ranks[0] if ranks else None
        f = record["funnel"]
        entry["true_pair_survived"] = {
            stage: (list(pair) in f[key] if isinstance(f[key], list) else f[key])
            for stage, key in (("speed_distance_time_gates", "flight_pairs_before_silence_filter"),
                               ("silence_filter", "flight_pairs_after_silence_filter"))}
    else:
        entry["true_pair_rank"] = entry["true_pair_survived"] = unavailable("the case has no true flight pair in its box")
    entry["outcome_met"] = unavailable(NO_VERDICT)
    for k in ("detection", "association", "fits", "verdicts", "region_coverage"):
        entry[k] = unavailable("not produced by today's pipeline")
    return entry


def new_run(topic: str) -> Path:
    out = subprocess.run([sys.executable, str(REPO / "tools" / "data" / "new_run.py"), topic], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout.strip()
    return Path(out)


def run_bench(case_ids: list[str], tier: str = "t2", run_dir: Path | None = None, log=print) -> Path:
    """Run cases into a new run folder (or `run_dir`) and collect their scoreboard entries in results.json."""
    # the code revision is read once, before anything runs, so an edit during a long run can't relabel it
    code = code_revision()
    commit, dirty = code["git_commit"], code["git_dirty"]
    if run_dir is None:
        run_dir = new_run(f"bench-{(commit or 'nogit')[:7]}-{tier}")
    info_path = run_dir / "run.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    info.update(command=sys.argv, cases=case_ids, tier=tier)
    info_path.write_text(json.dumps(info, indent=1) + "\n")
    entries = []
    for cid in case_ids:
        case_dir = run_dir / cid
        case_dir.mkdir(parents=True, exist_ok=True)
        with open(case_dir / "run.log", "w") as fh:
            def case_log(msg, fh=fh):
                print(msg, file=fh, flush=True)
                log(msg)
            w0 = time.perf_counter()
            entry = bench_case(cid, case_dir, log=case_log, code=code)
            log(f"{cid}: {entry['status']} in {time.perf_counter() - w0:.0f} s")
        entries.append(entry)
    doc = {"schema": 1, "tier": tier, "git_commit": commit, "git_dirty": dirty,
           "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "cases": entries}
    (run_dir / "results.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return run_dir


METRICS = ("true_pair_rank", "flight_pairs", "margin_pct", "top_error_m", "refined_error_m", "box_centre_error_m")


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
    lines = [f"a: {a} ({(ra.get('git_commit') or '?')[:9]}{' dirty' if ra.get('git_dirty') else ''})",
             f"b: {b} ({(rb.get('git_commit') or '?')[:9]}{' dirty' if rb.get('git_dirty') else ''})", ""]
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
