"""`dopplertrack locate`, PLAN Phase 3 step A: from audio, a date and a box to a verdict, with explicit failures.

One pass over today's pieces: spectrogram, `detect`, a usability check (S6), flight data with its margin, the CPA
table, one search on a pair of detected flyovers chosen by a pluggable rule, refinement of the winner with the other
flyovers, and a verdict. Step A refines only the winner, so it can't rule out a competing mode: its verdict is
"ambiguous" at best; a "located" verdict requires competitor handling and calibration that are not implemented.
Insufficient-evidence failures (verdict `insufficient_evidence`) have stated reasons: no usable flyovers, flight data missing over the box or over the recording's
time, a clock past UTC midnight with only one day loaded, and no surviving candidate. Execution errors can raise.

Every setting is a field of GridPairParameters (parameters.py); the locate profile holds what LocateConfig's
defaults were. The event sources (event_source.source, EVENT_SOURCES; the record's `pair_rules` keep the rule names
"top2" and "comparable"):
- "top2": detect's two highest-scoring usable events, earlier first. The raw-audio profile's rule; its failure on
  the development recordings is measured (docs/experiments/2026-11-04-bench-baselines.md).
- "comparable_pairs": every pair of the top event_source.top_k usable events, each searched with the pair_zscore
  normalisation, the pair whose top candidate has the highest comparable score winning. Up to ten searches, so about
  ten times top2's time.

The locate profile, comparable pairs with the negative-information filter (key `silence`) on at 6 km, follows Tier 2 on
the development set (docs/experiments/2026-11-04-locate.md): it found Oyster Bay where top2 and the filter off found no
seed case, and lost none. The filter rests on one recording and is judged again on the next positive.
event_source.report_top2 (`--pair-rule both`) refines the source's answer and reports top2's beside it.
"""
from __future__ import annotations

import datetime
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from dopplertrack.components.search.best_per_pair import best_per_pair
from dopplertrack.components.search.clock_gate import clock_gate
from dopplertrack.components.selection.comparable_pairs import comparable_pairs
from dopplertrack.components.selection.top2 import top2
from dopplertrack.components.selection.usability import usable_events, valid_share
from dopplertrack.methods.grid_pair.parameters import GridPairParameters, check, resolve
from dopplertrack.methods.parameters import to_dict
from dopplertrack.runtime.records import CONVENTIONS_V1, KIND, SCHEMA_VERSION, file_entry, unavailable

# The event sources, a method choice (event_source.source): the name, and the rule that picks the searched pairs from
# the usable detections. saved_fits takes no detection, so locate refuses it. The record names the rules by their
# pair_rules names, top2 and comparable.
EVENT_SOURCES = {"saved_fits": None, "top2": lambda usable, k: [top2(usable)], "comparable_pairs": comparable_pairs}
RULE_NAMES = {"top2": "top2", "comparable_pairs": "comparable"}
SCORE_KINDS = {"contrast": "detect's sweep-weighted ridge contrast", "custom_rescore_zscore": "S1 (custom_contrast_zscore)",
               "rescore_surrogate": "D against the time-reversed window (rescore_surrogate)"}


@dataclass(frozen=True)
class RunSettings:
    """What locate needs beyond its parameters and can't change a result: processes, the CPA cache file, and the
    declared coverage box per trace file for files without metadata (a description of the input data)."""
    workers: int | None = None
    cpa_cache: str | None = None
    envelope: list | None = None


@dataclass
class Outcome:
    """What locate found: the result record's content, ready for result.write_record."""
    record: dict
    summary: list[str]


def _log(log, msg):
    if log:
        log(msg)


def _day_bounds(date: str) -> tuple[float, float]:
    d = datetime.datetime.fromisoformat(date).replace(tzinfo=datetime.timezone.utc)
    return d.timestamp(), d.timestamp() + 86400.0


def _covered_days(paths, metas: list[dict], traces, declared_date=None) -> tuple[float, float]:
    """The UTC span the flight data declares it covers: each file's covered_utc if it states one, else the UTC day
    of its archive (metadata date, or the archive folder's name), else declared_date for a file without metadata
    whose envelope was declared, else the span of its traces' own times."""
    spans = []
    for p, m in zip(paths, metas):
        if m.get("covered_utc"):
            spans.append(tuple(m["covered_utc"]))
            continue
        day = m.get("date") or Path(str(m.get("archive_dir", ""))).name or (declared_date if not m else "")
        try:
            spans.append(_day_bounds(day))
        except ValueError:
            ts = [float(t.t[0]) for t in traces if len(t)] + [float(t.t[-1]) for t in traces if len(t)]
            if ts:
                spans.append((min(ts), max(ts)))
    if not spans:
        return (np.inf, -np.inf)
    return min(a for a, _ in spans), max(b for _, b in spans)


def _envelopes(metas, run: RunSettings):
    if run.envelope:
        return [list(e) for e in run.envelope]
    return [m.get("coverage_bbox") for m in metas]


def _search(sp, ev1, ev2, traces, grid, params: GridPairParameters, run: RunSettings, meta, bbox, triples=None):
    import dopplertrack.methods.grid_pair.pipeline as pipeline
    if run.cpa_cache:             # a fresh cache root (a fleet box) has no folder for the table or its lock yet
        Path(run.cpa_cache).parent.mkdir(parents=True, exist_ok=True)
    res, segs = pipeline.pair_grid_search(sp, ev1, ev2, traces, grid, params, progress=False, cpa_cache=run.cpa_cache,
                                          trace_metadata=meta, search_bbox=tuple(bbox), workers=run.workers,
                                          triples=triples)
    es = params.event_source
    return clock_gate(res, ev1.t_cpa, es.start_utc, es.start_tol_s, params.gates.time_gate_s), segs


def _rule_parameters(params: GridPairParameters, source: str) -> GridPairParameters:
    """The parameters one pair rule searches with: comparable pairs are ranked on the comparable score, so their
    searches use the pair_zscore normalisation; top2's use the scoring stage's own."""
    if source == "comparable_pairs":
        return replace(params, scoring=replace(params.scoring, normalisation="pair_zscore"))
    return params


def _usable_extras(sp, row, extras, segs, params: GridPairParameters, elevation):
    """The extra flyovers refine can place: a flight near the candidate at each one's time (pipeline.pick_flight,
    as refine chooses them); the rest are dropped with the reason, so refine never fails on one."""
    from dopplertrack.core.geometry import lla_to_enu
    from dopplertrack.components.assignment.pick_flight import pick_flight
    lat, lon = float(row.lat), float(row.lon)
    el0 = float(elevation(np.array([lat]), np.array([lon]))[0]) if elevation else 0.0
    obs0 = lla_to_enu(lat, lon, el0 if np.isfinite(el0) else 0.0, row.lat0, row.lon0)
    t0_map0 = float(row["_t_cpa1"]) - float(row.t_heard1)        # audio = unix + t0_map0, as refine maps it
    keep, dropped = [], []
    from dopplertrack.methods.parameters import inclusive_grid
    r, sc = params.refinement, params.scoring
    hs = list(params.gates.harmonics[2:]) + [1] * len(extras)
    for ev, h in zip(extras, hs):
        k, _ = pick_flight(sp, ev, segs, obs0, t0_map0, float(row["shift"]), int(h), params.speed_of_sound(),
                           max_range_m=params.gates.max_range_m, alive_pad_s=r.alive_pad_s,
                           temperature_c=params.air.temperature_c, f0_scales=inclusive_grid(r.extra_f0_scale_grid),
                           pad_s=sc.crop_pad_s, n=sc.curve_samples, spectral_floor=params.spectrogram.spectral_floor)
        (keep if k >= 0 else dropped).append(ev)
    return keep, dropped


def locate_config(params: GridPairParameters, run: RunSettings) -> dict:
    """The record's `parameters.config`, the key LocateConfig's fields filled before R2, from the parameters: each
    key is the old field's name, mapped from its field (band_hz detection.band_hz, detect_top detection.top,
    window_s detection.window_s, spacing_m grid.spacing_m, max_range_m gates.max_range_m, tol_s gates.time_gate_s,
    v_tol gates.speed_gate_fraction, d_tol gates.slant_range_gate_factors, silence_d_m
    gates.negative_information_distance_m, pair_rule event_source.source (and report_top2: both), refine_spacing_m
    refinement.spacing_m, refine_half_m refinement.half_width_m, dem grid.dem, c air.speed_of_sound_m_s or the
    temperature's, temperature_c air.temperature_c, start_utc and start_tol_s event_source's), plus the run settings
    it held. The full set is `parameters.resolved`."""
    from dopplertrack.core.propagation import speed_of_sound
    a, es = params.air, params.event_source
    rule = "both" if es.report_top2 else RULE_NAMES.get(es.source, es.source)
    c = a.speed_of_sound_m_s if a.speed_of_sound_m_s is not None else (
        None if a.temperature_c is None else speed_of_sound(a.temperature_c))
    return {"band_hz": tuple(params.detection.band_hz), "detect_top": params.detection.top,
            "window_s": params.detection.window_s, "spacing_m": params.grid.spacing_m,
            "max_range_m": params.gates.max_range_m, "tol_s": params.gates.time_gate_s,
            "v_tol": params.gates.speed_gate_fraction, "d_tol": tuple(params.gates.slant_range_gate_factors),
            "silence_d_m": params.gates.negative_information_distance_m, "pair_rule": rule,
            "refine_spacing_m": params.refinement.spacing_m, "refine_half_m": params.refinement.half_width_m,
            "dem": params.grid.dem, "c": c, "temperature_c": a.temperature_c, "workers": run.workers,
            "cpa_cache": run.cpa_cache, "envelope": run.envelope, "start_utc": es.start_utc,
            "start_tol_s": es.start_tol_s}


def locate(spec_path, date: str, bbox, trace_paths, params: GridPairParameters | None = None,
           run: RunSettings | None = None, out_dir: Path | None = None, code: dict | None = None, log=None,
           extra: dict | None = None, spectrogram_input: str = "file") -> Outcome:
    """Run step A on a spectrogram file and return the result record. Writes funnel_triples.npz into out_dir. params
    defaults to the locate profile; extra goes into the record's parameters beside the resolved ones, and
    spectrogram_input says whether the spectrogram was built here from audio ("audio") or given ("file")."""
    from dopplertrack.data.day_seams import join_days
    from dopplertrack.components.spectrogram import Spectrogram
    from dopplertrack.data.coverage import ADS_B_LIMITATION, padded_bbox
    from dopplertrack.components.search.grid import Grid
    from dopplertrack.data.terrain import Terrain
    import dopplertrack.methods.grid_pair.pipeline as pipeline

    p = check(params if params is not None else resolve("locate"))
    run = run or RunSettings()
    es, g = p.event_source, p.gates
    if EVENT_SOURCES[es.source] is None:
        raise ValueError(f"locate detects its own events: event_source.source must be one of "
                         f"{sorted(k for k, v in EVENT_SOURCES.items() if v is not None)}, not {es.source!r}")
    bbox = [float(x) for x in bbox]
    stages, summary, errors = [], [], []
    inputs, caches = [], []
    params = {"date": date, "bbox": bbox, "config": locate_config(p, run), "speed_of_sound_m_s": p.speed_of_sound(),
              **(extra or {}), "resolved": to_dict(p), "spectrogram_input": spectrogram_input}
    rec = {"schema_version": SCHEMA_VERSION, "kind": KIND, "case": None, "conventions": CONVENTIONS_V1,
           "provenance": {"created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                          "code": code or {"package_version": _version(), "git_commit": unavailable("not recorded by locate"),
                                           "git_dirty": unavailable("not recorded by locate")},
                          "parameters": params, "inputs": inputs, "caches": caches},
           "events": [], "candidates": [], "refined": unavailable("the search did not run"),
           "funnel": {k: unavailable("the search did not run") for k in (
               "cpa_records", "after_speed_gate", "after_distance_gate", "after_time_gate", "before_silence_filter",
               "after_silence_filter", "flight_pairs_before_silence_filter", "flight_pairs_after_silence_filter",
               "scored", "unevaluated_budget")},
           "verdict": unavailable("not reached"), "region": unavailable("no uncertainty region exists before Phase 4"),
           "pair_rules": [],
           "data_limitations": {"flight_data": {}, "altitude_sources": unavailable("not computed by locate"),
                                "candidate_gaps": unavailable("not collected by locate"),
                                "possible_edits": unavailable("edit detection does not exist yet (L4, S6)"),
                                "ads_b": ADS_B_LIMITATION},
           "execution": {"errors": errors, "warnings": [], "stages": stages}}

    def cpu():
        t = os.times()
        return t.user + t.system + t.children_user + t.children_system
    clock = {}

    def stage(name, t0):
        stages.append({"name": name, "wall_s": round(time.perf_counter() - t0, 3),
                       "cpu_s": round(cpu() - clock.pop(t0, cpu()), 3)})

    def start():
        t0 = time.perf_counter()
        clock[t0] = cpu()
        return t0

    def finish(outcome: str, codes: list[str], reasons: list[str]) -> Outcome:
        rec["verdict"] = {"outcome": outcome, "reason_codes": codes, "reasons": reasons}
        summary.append(f"verdict: {outcome} ({'; '.join(reasons)})")
        return Outcome(rec, summary)

    # 1. spectrogram and detection, and the usability check (S6)
    t0 = start()
    sp = Spectrogram.load(spec_path)
    inputs.append(file_entry("spectrogram", spec_path))
    found, params["detection_key"] = pipeline.detect(sp, p, workers=run.workers)
    stage("detect", t0)
    usable = usable_events(found)
    share = valid_share(sp)
    for k, e in enumerate(usable, 1):
        rec["events"].append({
            "id": f"d{k}", "source": "detect", "harmonics": p.detection.harmonics,
            "fit": {"t_heard_cpa_audio_s": e.t_cpa, "t_emission_cpa_audio_s": e.t_cpa_emit,
                    "t_steepest_fall_audio_s": e.t_cpa_emit, "f0_hz": e.f0, "speed_m_s": e.v, "slant_range_m": e.d,
                    "window_s": [e.t_start, e.t_end], "f_pre_hz": e.f_pre, "f_post_hz": e.f_post},
            "diagnostics": {"score": e.score, "score_kind": SCORE_KINDS[p.detection.statistic],
                            "covariance": unavailable("fits report no covariance yet (Phase 2)")},
            "assignment": unavailable("not assigned"), "utc": unavailable("no clock yet")})
    summary.append(f"{len(found)} detections, {len(usable)} usable; {100 * share:.0f} % of frames valid")
    if len(usable) < 2 or share < es.usable_valid_share:
        why = (f"{len(usable)} usable flyover(s); the search needs two" if len(usable) < 2 else
               f"only {100 * share:.0f} % of the recording's frames are valid")
        return finish("insufficient_evidence", ["no_usable_flyovers"], [why])

    # 2. flight data, its coverage over the box plus the search range and over the stated day
    t0 = start()
    paths = [str(p) for p in trace_paths]
    if not paths:
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      ["no flight data was given; pass --traces, or --fetch to download the day"])
    traces, meta = join_days(paths)
    from dopplertrack.data.region_loading import load_trace_metadata
    metas = [load_trace_metadata(p) for p in paths]
    inputs += [file_entry("traces", p) for p in paths]
    need = padded_bbox(tuple(bbox), g.max_range_m)
    envs = _envelopes(metas, run)
    flight = {"traces": paths, "envelopes": envs, "search_box_plus_range": [round(x, 6) for x in need],
              "traces_loaded": len(traces), "seams": meta.get("seams", [])}
    if run.envelope:
        flight["declared"] = "envelopes declared by the caller; a file without metadata is taken as a whole-day cut of the stated date"
    rec["data_limitations"]["flight_data"] = flight
    stage("flight_data", t0)
    if any(e is None for e in envs):
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      ["a trace file has no measured coverage envelope (legacy file); declare its box or re-extract it"])
    if not all(e[0] <= need[0] and e[1] >= need[1] and e[2] <= need[2] and e[3] >= need[3] for e in envs):
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      [f"the flight data's envelope doesn't cover the box plus {g.max_range_m:g} m"])
    covered = _covered_days(paths, metas, traces, declared_date=date if run.envelope else None)
    flight["covered_utc"] = list(covered)
    day0, day1 = _day_bounds(date)
    need_t, what = (day0 + es.day_slack_s, day1 - es.day_slack_s), f"the whole of {date}"
    if es.start_utc is not None:   # the clock gate keeps only clocks near the stated start: the data need cover just
        pad = float(es.start_tol_s or 0.0) + g.time_gate_s + es.gate_pad_s   # those, and never more than the whole day
        need_t = (max(es.start_utc + float(sp.t[0]) - pad, need_t[0]), min(es.start_utc + float(sp.t[-1]) + pad, need_t[1]))
        what = f"the recording at its stated start, {_iso(need_t[0])} to {_iso(need_t[1])}"
    flight["needed_utc"] = list(need_t)
    if covered[0] > need_t[0] or covered[1] < need_t[1]:
        return finish("insufficient_evidence", ["flight_data_missing_time"],
                      [f"the flight data covers {_iso(covered[0])} to {_iso(covered[1])}, not {what}"])

    # 3. the grid, then each pair rule's search
    elevation = Terrain().elevation if p.grid.dem else None
    grid = Grid.make(*bbox, p.grid.spacing_m, elevation)
    runs = {}
    sources = ["top2", es.source] if es.report_top2 and es.source != "top2" else [es.source]   # top2 first, as before
    for source in sources:
        rule = RULE_NAMES[source]
        t0 = start()
        pairs = EVENT_SOURCES[source](usable, es.top_k)
        rp = _rule_parameters(p, source)
        best = None
        for ev1, ev2 in pairs:
            triples = {}
            res, segs = _search(sp, ev1, ev2, traces, grid, rp, run, meta, bbox, triples=triples)
            top = float(res.score.iloc[0]) if len(res) else -np.inf
            if best is None or top > best[0]:
                best = (top, ev1, ev2, res, segs, triples)
        wall = time.perf_counter() - t0
        stage(f"search {rule}", t0)
        top, ev1, ev2, res, segs, triples = best
        bp = best_per_pair(res) if len(res) else res
        idx = [usable.index(ev1) + 1, usable.index(ev2) + 1]
        margin = (100 * (bp.score.iloc[0] - bp.score.iloc[1]) / bp.score.iloc[1]
                  if len(bp) > 1 and bp.score.iloc[1] > 0 else None)
        runs[rule] = (ev1, ev2, res, segs, triples, bp)
        rec["pair_rules"].append({
            "rule": rule, "events": idx, "chosen": False, "wall_s": round(wall, 2),
            "top_flights": [str(bp.icao1.iloc[0]), str(bp.icao2.iloc[0])] if len(bp) else unavailable("no candidate"),
            "top_score": float(bp.score.iloc[0]) if len(bp) else unavailable("no candidate"),
            "margin_pct": margin if margin is not None else unavailable("fewer than two flight pairs")})
        summary.append(f"rule {rule}: events d{idx[0]}+d{idx[1]}, "
                       + (f"top {bp.icao1.iloc[0]}/{bp.icao2.iloc[0]} {bp.score.iloc[0]:.2f}" if len(bp) else "no candidate")
                       + (f", margin {margin:.1f} %" if margin is not None else "") + f", {wall:.0f} s")
    chosen = RULE_NAMES[es.source]
    next(r for r in rec["pair_rules"] if r["rule"] == chosen)["chosen"] = True
    ev1, ev2, res, segs, triples, bp = runs[chosen]
    funnel = res.attrs.get("funnel", {})
    gate = "emission_gate" if "emission_gate" in funnel else "time_join"
    if funnel:
        rec["funnel"].update(pipeline=funnel, cpa_records=funnel.get("cpa_rows"), after_time_gate=funnel.get(gate),
                             before_silence_filter=funnel.get(gate), after_silence_filter=funnel.get("silence"),
                             scored=funnel.get("scored"), unevaluated_budget=0,
                             after_speed_gate=unavailable("speed and distance are gated together per event"),
                             after_distance_gate=unavailable("speed and distance are gated together per event"))
    if out_dir is not None:
        rec["funnel"]["triples_file"] = write_triples(Path(out_dir), segs, grid, triples, res)
    if not len(bp):
        rec["refined"] = unavailable("no candidate survived the search")
        return finish("insufficient_evidence", ["no_surviving_candidate"],
                      [f"no candidate survived the gates"
                       f"{'' if g.negative_information_distance_m is None else ', the silence filter'}"
                       f"{'' if es.start_utc is None else ' and the stated start time'}"])

    # 4. candidates, the clock, and the recording's UTC span against the flight data's
    for i, row in enumerate(bp.itertuples(), 1):
        offset = ev1.t_cpa - float(row.t_heard1) + float(row.shift)
        rec["candidates"].append({"rank": i, "lat": float(row.lat), "lon": float(row.lon),
                                  "flights": [str(row.icao1), str(row.icao2)],
                                  "clock": {"audio_minus_utc_s": offset, "shift_s": float(row.shift),
                                            "drift": unavailable("the clock model has no drift term yet")},
                                  "score": float(row.score), "event_scores": [float(row.s1), float(row.s2)],
                                  "mode": unavailable("step A refines only the winner")})
    top = rec["candidates"][0]
    off = top["clock"]["audio_minus_utc_s"]
    for ef, icao in ((ev1, top["flights"][0]), (ev2, top["flights"][1])):
        e = rec["events"][usable.index(ef)]
        e["assignment"] = {"flight": icao, "basis": "flight pair of the top-ranked candidate"}
    for e in rec["events"]:
        e["utc"] = {"t_heard_cpa": e["fit"]["t_heard_cpa_audio_s"] - off,
                    "t_emission_cpa": e["fit"]["t_emission_cpa_audio_s"] - off, "basis": "the top-ranked candidate's clock"}
    span = (float(sp.t[0]) - off, float(sp.t[-1]) - off)
    flight["recording_utc"] = list(span)
    if span[1] > covered[1] + 1.0:
        if covered[1] <= day1 + 1.0:
            return finish("insufficient_evidence", ["past_utc_midnight"],
                          [f"the matched clock puts the recording's end at {_iso(span[1])}, past UTC midnight; "
                           "rerun with --days 1 for the next day's flight data"])
        return finish("insufficient_evidence", ["flight_data_missing_time"],
                      [f"the matched clock puts the recording at {_iso(span[0])}–{_iso(span[1])}, past the flight data"])
    if span[0] < covered[0] - 1.0:
        return finish("insufficient_evidence", ["flight_data_missing_time"],
                      [f"the matched clock puts the recording's start at {_iso(span[0])}, before the flight data"])

    # 5. refine the winner with the other usable flyovers it can place
    t0 = start()
    row = bp.iloc[0].copy()
    row["lat0"], row["lon0"], row["_t_cpa1"] = grid.lat0, grid.lon0, ev1.t_cpa
    others = [e for e in usable if e is not ev1 and e is not ev2]
    keep, dropped = _usable_extras(sp, row, others, segs, p, elevation)
    fine = pipeline.refine(sp, ev1, ev2, segs, row, p, elevation=elevation, extra=keep, workers=run.workers)
    stage("refine", t0)
    b = fine.iloc[0]
    rec["refined"] = {"lat": float(b.lat), "lon": float(b.lon), "score": float(b.score),
                      "event_scores": [float(b[c]) for c in fine.columns if c.startswith("s") and c[1:].isdigit()],
                      "shift_s": float(b["shift"]), "spacing_m": p.refinement.spacing_m,
                      "half_width_m": p.refinement.half_width_m,
                      "from_rank": 1, "extra_flights": list(fine.attrs.get("extra_icao", []))}
    flight["extras_dropped"] = [e.t_cpa for e in dropped]
    summary.append(f"refined {b.lat:.5f}, {b.lon:.5f} with {len(keep)} extra flyover(s) ({len(dropped)} without a flight near)")
    reasons = ["step A refines only the winner, so a competing mode isn't ruled out"]
    codes = ["winner_only_refined"]
    if g.negative_information_distance_m is None:
        codes.append("silence_filter_off")
        reasons.append("the silence filter was turned off")
    return finish("ambiguous", codes, reasons)


def write_triples(out_dir: Path, segs, grid, triples: dict, res) -> dict:
    """Every hypothesis each stage kept, with its location, into funnel_triples.npz, for the comparison step."""
    import os

    from dopplertrack.runtime.records import sha256_file
    icao = np.array([s.icao for s in segs])
    arrays = {}
    for name, t in triples.items():
        arrays.update({f"{name}__icao1": icao[t["seg1"]].astype(str), f"{name}__icao2": icao[t["seg2"]].astype(str),
                       f"{name}__gidx": t["gidx"], f"{name}__lat": grid.lat[t["gidx"]], f"{name}__lon": grid.lon[t["gidx"]]})
    arrays.update({"scored__icao1": res.icao1.to_numpy(str), "scored__icao2": res.icao2.to_numpy(str),
                   "scored__gidx": res.gidx.to_numpy(np.int32), "scored__lat": res.lat.to_numpy(float),
                   "scored__lon": res.lon.to_numpy(float), "scored__score": res.score.to_numpy(float)})
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "funnel_triples.npz"
    tmp = out_dir / f".funnel_triples.{os.getpid()}.tmp.npz"
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)
    stages = [*triples, "scored"]
    return {"path": path.name, "sha256": sha256_file(path), "stages": stages,
            "rows": {k: int(len(arrays[f"{k}__gidx"])) for k in stages}}


def _iso(t: float) -> str:
    if not np.isfinite(t):
        return "nothing"
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _version() -> str:
    from importlib.metadata import version
    return version("dopplertrack")
