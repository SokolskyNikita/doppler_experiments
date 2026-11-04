"""`dopplertrack locate`, PLAN Phase 3 step A: from audio, a date and a box to a verdict, with explicit failures.

One pass over today's pieces: spectrogram, `detect`, a usability check (S6), flight data with its margin, the CPA
table, one search on a pair of detected flyovers chosen by a pluggable rule, refinement of the winner with the other
flyovers, and a verdict. Step A refines only the winner, so it can't rule out a competing mode: its verdict is
"ambiguous" at best, and "located" waits for step B. Every failure is an outcome with a stated reason, never an
exception: no usable flyovers, flight data missing over the box or over the recording's time, a clock that puts the
recording past UTC midnight with only one day loaded, and no surviving candidate.

The pair rules:
- "top2": detect's two highest-scoring usable events, earlier first. The raw-audio profile's rule; its failure on
  the development recordings is measured (docs/experiments/2026-11-04-bench-baselines.md).
- "comparable": every pair of the top TOP_K usable events, each searched with run_search(comparable=True), the pair
  whose top candidate has the highest comparable score winning. Up to ten searches, so about ten times top2's time.
"""
from __future__ import annotations

import datetime
import itertools
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .result import CONVENTIONS_V1, KIND, SCHEMA_VERSION, file_entry, unavailable

TOP_K = 5
USABLE_VALID_SHARE = 0.5      # a recording more than half gaps is not searched (S6)
DAY_SLACK_S = 600.0           # flight data counts as covering a day if it reaches within this of each end
RULES = ("top2", "comparable")


@dataclass
class LocateConfig:
    band_hz: tuple[float, float] = (60.0, 300.0)
    detect_top: int = 10
    window_s: float = 240.0
    spacing_m: float = 200.0
    max_range_m: float = 12000.0
    tol_s: float = 6.0
    v_tol: float = 0.35
    d_tol: tuple[float, float] = (0.4, 2.5)
    silence_d_m: float | None = None          # off by default in locate (S4)
    pair_rule: str = "top2"                   # "top2", "comparable", or "both" (top2's result, comparable reported)
    refine_spacing_m: float = 50.0
    refine_half_m: float = 600.0
    dem: bool = True
    c: float | None = None                    # the speed of sound; None is the pipeline's 15 C default
    workers: int | None = None
    cpa_cache: str | None = None
    envelope: list[list[float]] | None = None  # a declared coverage box per trace file, for files without metadata
    extra: dict = field(default_factory=dict)  # anything else for the record's parameters


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


def _envelopes(metas, cfg: LocateConfig):
    if cfg.envelope:
        return [list(e) for e in cfg.envelope]
    return [m.get("coverage_bbox") for m in metas]


def _best_per_pair(res):
    return res.sort_values("score", ascending=False, kind="stable").drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)


def _search(sp, ev1, ev2, traces, grid, cfg: LocateConfig, meta, bbox, comparable=False, triples=None):
    from . import pipeline
    c_kw = {} if cfg.c is None else {"c": cfg.c}
    return pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=(1, 1), tol_s=cfg.tol_s, v_tol=cfg.v_tol,
                               d_tol=tuple(cfg.d_tol), silence_d_m=cfg.silence_d_m, max_range_m=cfg.max_range_m,
                               progress=False, cpa_cache=cfg.cpa_cache, trace_metadata=meta, search_bbox=tuple(bbox),
                               workers=cfg.workers, triples=triples, comparable=comparable, **c_kw)


def _usable_extras(sp, row, extras, segs, cfg: LocateConfig, elevation):
    """The extra flyovers refine can place: a flight near the candidate at each one's time (pipeline.pick_flight,
    as refine chooses them); the rest are dropped with the reason, so refine never fails on one."""
    from .geo import lla_to_enu
    from .pipeline import pick_flight
    lat, lon = float(row.lat), float(row.lon)
    el0 = float(elevation(np.array([lat]), np.array([lon]))[0]) if elevation else 0.0
    obs0 = lla_to_enu(lat, lon, el0 if np.isfinite(el0) else 0.0, row.lat0, row.lon0)
    t0_map0 = float(row["_t_cpa1"]) - float(row.t_heard1)        # audio = unix + t0_map0, as refine maps it
    keep, dropped = [], []
    for ev in extras:
        k, _ = pick_flight(sp, ev, segs, obs0, t0_map0, float(row["shift"]), 1, cfg.c, max_range_m=cfg.max_range_m)
        (keep if k >= 0 else dropped).append(ev)
    return keep, dropped


def locate(spec_path, date: str, bbox, trace_paths, cfg: LocateConfig | None = None, out_dir: Path | None = None,
           code: dict | None = None, log=None) -> Outcome:
    """Run step A on a spectrogram file and return the result record. Writes funnel_triples.npz into out_dir."""
    from .adsb import join_days
    from .audio import Spectrogram
    from .cache import cached_detections, detection_key
    from .coverage import ADS_B_LIMITATION, padded_bbox
    from .doppler import speed_of_sound
    from .search import Grid
    from .terrain import Terrain
    from .tracks import detect_events

    cfg = cfg or LocateConfig()
    if cfg.pair_rule not in (*RULES, "both"):
        raise ValueError(f"pair_rule must be one of {RULES} or 'both'")
    bbox = [float(x) for x in bbox]
    stages, summary, errors = [], [], []
    inputs, caches = [], []
    params = {"date": date, "bbox": bbox, "config": {k: v for k, v in cfg.__dict__.items() if k != "extra"},
              "speed_of_sound_m_s": cfg.c if cfg.c is not None else speed_of_sound(), **cfg.extra}
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
    d_params = dict(f_lo=cfg.band_hz[0], f_hi=cfg.band_hz[1], harmonics=1, top=cfg.detect_top, window_s=cfg.window_s)
    if cfg.c is not None:
        d_params["c"] = cfg.c
    found = [e for e in cached_detections(sp, detect_events, workers=cfg.workers, **d_params)]
    params["detection_key"] = detection_key(sp, detect_events, **d_params)
    stage("detect", t0)
    usable = [e for e in found if not getattr(e, "weak", None) and np.isfinite(e.f0)]
    valid_share = float(np.mean(sp.valid)) if sp.valid is not None else 1.0
    for k, e in enumerate(usable, 1):
        rec["events"].append({
            "id": f"d{k}", "source": "detect", "harmonics": 1,
            "fit": {"t_heard_cpa_audio_s": e.t_cpa, "t_emission_cpa_audio_s": e.t_cpa_emit,
                    "t_steepest_fall_audio_s": e.t_cpa_emit, "f0_hz": e.f0, "speed_m_s": e.v, "slant_range_m": e.d,
                    "window_s": [e.t_start, e.t_end], "f_pre_hz": e.f_pre, "f_post_hz": e.f_post},
            "diagnostics": {"score": e.score, "score_kind": "detect's sweep-weighted ridge contrast",
                            "covariance": unavailable("fits report no covariance yet (Phase 2)")},
            "assignment": unavailable("not assigned"), "utc": unavailable("no clock yet")})
    summary.append(f"{len(found)} detections, {len(usable)} usable; {100 * valid_share:.0f} % of frames valid")
    if len(usable) < 2 or valid_share < USABLE_VALID_SHARE:
        why = (f"{len(usable)} usable flyover(s); the search needs two" if len(usable) < 2 else
               f"only {100 * valid_share:.0f} % of the recording's frames are valid")
        return finish("insufficient_evidence", ["no_usable_flyovers"], [why])

    # 2. flight data, its coverage over the box plus the search range and over the stated day
    t0 = start()
    paths = [str(p) for p in trace_paths]
    if not paths:
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      ["no flight data was given; pass --traces, or --fetch to download the day"])
    traces, meta = join_days(paths)
    from .adsb import load_trace_metadata
    metas = [load_trace_metadata(p) for p in paths]
    inputs += [file_entry("traces", p) for p in paths]
    need = padded_bbox(tuple(bbox), cfg.max_range_m)
    envs = _envelopes(metas, cfg)
    flight = {"traces": paths, "envelopes": envs, "search_box_plus_range": [round(x, 6) for x in need],
              "traces_loaded": len(traces), "seams": meta.get("seams", [])}
    if cfg.envelope:
        flight["declared"] = "envelopes declared by the caller; a file without metadata is taken as a whole-day cut of the stated date"
    rec["data_limitations"]["flight_data"] = flight
    stage("flight_data", t0)
    if any(e is None for e in envs):
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      ["a trace file has no measured coverage envelope (legacy file); declare its box or re-extract it"])
    if not all(e[0] <= need[0] and e[1] >= need[1] and e[2] <= need[2] and e[3] >= need[3] for e in envs):
        return finish("insufficient_evidence", ["flight_data_missing_box"],
                      [f"the flight data's envelope doesn't cover the box plus {cfg.max_range_m:g} m"])
    covered = _covered_days(paths, metas, traces, declared_date=date if cfg.envelope else None)
    flight["covered_utc"] = list(covered)
    day0, day1 = _day_bounds(date)
    if covered[0] > day0 + DAY_SLACK_S or covered[1] < day1 - DAY_SLACK_S:
        return finish("insufficient_evidence", ["flight_data_missing_time"],
                      [f"the flight data covers {_iso(covered[0])} to {_iso(covered[1])}, not the whole of {date}"])

    # 3. the grid, then each pair rule's search
    elevation = Terrain().elevation if cfg.dem else None
    grid = Grid.make(*bbox, cfg.spacing_m, elevation)
    ordered = sorted(usable, key=lambda e: e.score, reverse=True)
    runs = {}
    rules = RULES if cfg.pair_rule == "both" else (cfg.pair_rule,)
    for rule in rules:
        t0 = start()
        if rule == "top2":
            pairs = [tuple(sorted(ordered[:2], key=lambda e: e.t_cpa))]
        else:
            pairs = [tuple(sorted(p, key=lambda e: e.t_cpa)) for p in itertools.combinations(ordered[:TOP_K], 2)]
        best = None
        for ev1, ev2 in pairs:
            triples = {}
            res, segs = _search(sp, ev1, ev2, traces, grid, cfg, meta, bbox, comparable=(rule == "comparable"),
                                triples=triples)
            top = float(res.score.iloc[0]) if len(res) else -np.inf
            if best is None or top > best[0]:
                best = (top, ev1, ev2, res, segs, triples)
        wall = time.perf_counter() - t0
        stage(f"search {rule}", t0)
        top, ev1, ev2, res, segs, triples = best
        bp = _best_per_pair(res) if len(res) else res
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
    chosen = "top2" if cfg.pair_rule == "both" else cfg.pair_rule
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
                      [f"no candidate survived the gates{'' if cfg.silence_d_m is None else ' and the silence filter'}"])

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
    from . import pipeline
    t0 = start()
    row = bp.iloc[0].copy()
    row["lat0"], row["lon0"], row["_t_cpa1"] = grid.lat0, grid.lon0, ev1.t_cpa
    others = [e for e in usable if e is not ev1 and e is not ev2]
    keep, dropped = _usable_extras(sp, row, others, segs, cfg, elevation)
    c_kw = {} if cfg.c is None else {"c": cfg.c}
    fine = pipeline.refine(sp, ev1, ev2, segs, row, spacing_m=cfg.refine_spacing_m, half_m=cfg.refine_half_m,
                           harmonics=(1, 1), elevation=elevation, extra=keep, extra_harmonics=[1] * len(keep),
                           max_range_m=cfg.max_range_m, workers=cfg.workers, **c_kw)
    stage("refine", t0)
    b = fine.iloc[0]
    rec["refined"] = {"lat": float(b.lat), "lon": float(b.lon), "score": float(b.score),
                      "event_scores": [float(b[c]) for c in fine.columns if c.startswith("s") and c[1:].isdigit()],
                      "shift_s": float(b["shift"]), "spacing_m": cfg.refine_spacing_m, "half_width_m": cfg.refine_half_m,
                      "from_rank": 1, "extra_flights": list(fine.attrs.get("extra_icao", []))}
    flight["extras_dropped"] = [e.t_cpa for e in dropped]
    summary.append(f"refined {b.lat:.5f}, {b.lon:.5f} with {len(keep)} extra flyover(s) ({len(dropped)} without a flight near)")
    reasons = ["step A refines only the winner, so a competing mode isn't ruled out"]
    codes = ["winner_only_refined"]
    if cfg.silence_d_m is None:
        codes.append("silence_filter_off")
        reasons.append("the silence filter was off (S4)")
    return finish("ambiguous", codes, reasons)


def write_triples(out_dir: Path, segs, grid, triples: dict, res) -> dict:
    """Every hypothesis each stage kept, with its location, into funnel_triples.npz, for the comparison step."""
    import os

    from .result import sha256_file
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
