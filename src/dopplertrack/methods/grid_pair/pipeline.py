"""Direct position determination by grid search (Amar & Weiss 2008 §IV), the grid_pair recipe: the steps the CLI and
notebooks share, data preparation, the two-event grid search, the refinement and the single-event grid search, composed
from the methods under components/."""
from __future__ import annotations

import contextlib
import os
import time

import numpy as np
import pandas as pd

from dopplertrack.data.trajectories import Trace
from dopplertrack.data.aircraft_types import AircraftTypes
from dopplertrack.data.region_loading import load_region, save_traces
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.stft import compute_spectrogram
from dopplertrack.components.audio_input import load_audio
from dopplertrack.data.coverage import DEFAULT_MAX_RANGE_M, ScanReport, extraction_metadata, padded_bbox, report_altitude_sources, report_candidate_gaps, report_coverage
from dopplertrack.core.propagation import speed_of_sound
from dopplertrack.runtime.parallel import ordered_map, resolve_jobs
from dopplertrack.components.scoring.trajectory_score import custom_locked_score
from dopplertrack.components.scoring.doppler_inflection import INFLECTION_FLAT_RATIO
from dopplertrack.components.scoring.curve_integral import EventWindow
from dopplertrack.components.scoring.modelled_curve import modelled_curve
from dopplertrack.components.search.grid import Grid
from dopplertrack.components.search.types import Segment
from dopplertrack.components.search.segments import build_segments, clip_box
from dopplertrack.components.search.cpa_table import cpa_table
from dopplertrack.components.search.pair_join import stage_triples
from dopplertrack.components.search.pair_gate import in_gate, pair_candidates, rectangular_gate
from dopplertrack.components.search.time_gate import heard_near
from dopplertrack.components.fitting.hypothesis_merge import event_hypotheses
from dopplertrack.components.types import EventFit
from dopplertrack.components.assignment.pick_flight import pick_flight
from dopplertrack.components.nulls.event_decoy_null import NULL_N, event_decoy_null
from dopplertrack.components.scoring.f0_sweep import f0_sweep
from dopplertrack.components.scoring.fine_point_score import score_fine_points
from dopplertrack.components.scoring.inflection_gate import gate_settings, inflection_gate
from dopplertrack.components.search.hypothesis_join import pair_hypotheses
from dopplertrack.components.search.best_clock import best_clock
from dopplertrack.components.planning.square_grid import square_grid
from dopplertrack.components.scoring.pair_zscore import pair_zscore
from dopplertrack.runtime.pool_state import SCORE_CHUNK, SCORE_STATE, set_score_state


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@contextlib.contextmanager
def _file_lock(path):
    """Exclusive advisory lock on `path` (created if missing). Where fcntl is unavailable this is a no-op;
    atomic saves still keep the cache consistent, at the cost of possibly computing a table twice."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@contextlib.contextmanager
def _stage(stages: dict, name: str):
    """Record a stage's wall and CPU seconds in stages[name]. CPU time includes child processes reaped
    during the stage, so a process pool's workers count towards the stage that shut it down."""
    def cpu():
        t = os.times()
        return t.user + t.system + t.children_user + t.children_system
    w0, c0 = time.perf_counter(), cpu()
    try:
        yield
    finally:
        stages[name] = {"wall_s": time.perf_counter() - w0, "cpu_s": cpu() - c0}


def cached_cpa_table(grid: Grid, segs: list[Segment], max_range_m: float, c: float, path=None,
                     workers: int | None = None, temperature_c: float | None = None) -> pd.DataFrame:
    """Compatibility entry point; retain the injectable historical table builder."""
    from dopplertrack.runtime.cpa_cache import cached_cpa_table as cached
    return cached(grid, segs, max_range_m, c, path, workers, temperature_c, build=cpa_table)


def make_spectrogram(audio_path, out_path, hop_s=0.25, fmin=40, fmax=450, nperseg=8192, whiten_window_s=600):
    x, sr = load_audio(audio_path)
    sp = compute_spectrogram(x, sr, nperseg=nperseg, hop_s=hop_s, fmin=fmin, fmax=fmax, whiten_window_s=whiten_window_s)
    sp.save(out_path)
    return sp


def extract_region(archive_dir, bbox, out_path, prop_only=True, workers=None,
                   max_range_m=DEFAULT_MAX_RANGE_M) -> list[Trace]:
    envelope = padded_bbox(bbox, max_range_m)
    report = ScanReport()
    log(f"scanning {archive_dir} for traces in {envelope} (search box plus {max_range_m:g} m)")
    traces = load_region(archive_dir, envelope, workers=workers, report=report)
    log(f"{len(traces)} traces touch the region")
    if prop_only:
        types = AircraftTypes()
        traces = [t for t in traces if types.is_prop(t.typ)]
        log(f"{len(traces)} after dropping known jets")
    report.excluded_types = report.kept - len(traces)
    report.kept = len(traces)
    metadata = extraction_metadata(bbox, max_range_m, report, archive_dir=str(archive_dir))
    save_traces(traces, out_path, metadata=metadata)
    report_coverage(metadata, bbox, max_range_m, log)
    report_altitude_sources(traces, log)
    return traces


def fetch_region(date: str, bbox, out_path, prop_only=True, pod="planes-readsb-prod-0",
                 max_range_m=DEFAULT_MAX_RANGE_M) -> list[Trace]:
    """Save traces touching bbox padded by the search range, with extraction diagnostics."""
    from dopplertrack.data.providers.adsblol import fetch_day
    envelope = padded_bbox(bbox, max_range_m)
    report = ScanReport()
    log(f"streaming adsb.lol {date} ({pod}) for traces in {envelope} (search box plus {max_range_m:g} m)")
    t0 = time.time()
    def prog(n, nbytes):
        log(f"  {n} trace files scanned, {nbytes / 1e9:.2f} GB read, {nbytes / 1e6 / max(time.time() - t0, 1):.1f} MB/s")
    traces = fetch_day(date, envelope, pod=pod, progress=prog, report=report)
    log(f"{len(traces)} traces touch the region")
    if prop_only:
        types = AircraftTypes()
        traces = [t for t in traces if types.is_prop(t.typ)]
        log(f"{len(traces)} after dropping known jets")
    report.excluded_types = report.kept - len(traces)
    report.kept = len(traces)
    metadata = extraction_metadata(bbox, max_range_m, report, date=date, pod=pod)
    save_traces(traces, out_path, metadata=metadata)
    report_coverage(metadata, bbox, max_range_m, log)
    report_altitude_sources(traces, log)
    return traces


def segments_for_search(traces: list[Trace], bbox, lat0: float, lon0: float, max_range_m=DEFAULT_MAX_RANGE_M) -> list[Segment]:
    """The airborne segments a search over bbox used, rebuilt without the grid: same origin,
    same clip box (bbox corners padded by max_range)."""
    from dopplertrack.core.geometry import lla_to_enu
    la = np.array([bbox[0], bbox[0], bbox[1], bbox[1]]); lo = np.array([bbox[2], bbox[3], bbox[2], bbox[3]])
    enu = lla_to_enu(la, lo, np.zeros(4), lat0, lon0)
    return build_segments(traces, lat0, lon0, clip_enu=clip_box(enu, max_range_m))


def relocate_row(row, segs: list[Segment], dt_s: float):
    """Point a search result row at this segment list: seg1/seg2 are re-found by ICAO and the
    time each flight was heard (t_heard1, and t_heard1 + dt_s for flight 2), so a row
    survives a rebuild of the segments."""
    row = row.copy()
    for k, icao_col, t in (("seg1", "icao1", float(row.t_heard1)), ("seg2", "icao2", float(row.t_heard1) + dt_s)):
        cands = [i for i, s in enumerate(segs) if s.icao == row[icao_col]]
        if not cands:
            raise ValueError(f"flight {row[icao_col]} not in these traces")
        # a segment that spans the heard time wins; otherwise the nearest one in time
        row[k] = min(cands, key=lambda i: 0.0 if segs[i].t[0] - 60 <= t <= segs[i].t[-1] + 60 else min(abs(segs[i].t[0] - t), abs(segs[i].t[-1] - t)))
    return row


def _score_triples(task) -> list[tuple[tuple[float, float, float, float] | None, bool]]:
    """custom_locked_score for a chunk of (observer ENU, segment 1, segment 2, heard time of segment 1, emission
    times of segments 1 and 2). Each result is (scores, unplaceable): scores is None for a triple the
    inflection gate rejects, and unplaceable says a Doppler inflection couldn't be placed, so the gate
    was skipped and, under the "steepest" anchor, the heard anchor used instead."""
    obs, seg1, seg2, t_heard1, t_emit1, t_emit2, *rest = task
    anchor = rest[0] if rest else None             # per triple: the heard CPA of its event-1 hypothesis
    w1, w2, segs, c, sf = (SCORE_STATE[k] for k in ("w1", "w2", "segs", "c", "sf"))
    sweeps = SCORE_STATE.get("f0_scales")
    kw = {} if sweeps is None else {"f0_scales": sweeps[0], "f0_scales2": sweeps[1]}
    out: list[tuple[tuple[float, float, float, float] | None, bool]] = []
    for n, (o, a, b, th, te1, te2) in enumerate(zip(obs, seg1, seg2, t_heard1, t_emit1, t_emit2)):
        air = () if SCORE_STATE.get("temperature_c") is None else (SCORE_STATE["temperature_c"],)
        to1, r1 = modelled_curve(segs[int(a)], o, c, *air)
        to2, r2 = modelled_curve(segs[int(b)], o, c, *air)
        t0_map = None if anchor is None else float(anchor[n]) - float(th)
        unplaceable = False
        if sf is not None:
            kept, unplaceable, clock = inflection_gate(to1, r1, float(te1), to2, r2, float(te2), sf)
            if not kept:
                out.append((None, False))
                continue
            if clock is not None:
                t0_map = clock
        out.append((custom_locked_score(w1, w2, segs[int(a)], segs[int(b)], o, float(th), c=c,
                                 curves=(to1, r1, to2, r2), t0_map=t0_map, **kw), unplaceable))
    return out


# old name: run_search
def pair_grid_search(sp: Spectrogram, ev1: EventFit, ev2: EventFit, traces: list[Trace], grid: Grid,
               harmonics=(1, 1), tol_s=6.0, v_tol=0.35, d_tol=(0.4, 2.5), silence_d_m=6000.0,
               max_range_m=DEFAULT_MAX_RANGE_M, c=None, top_pairs=None, progress=True,
               cpa_cache=None, trace_metadata=None, search_bbox=None,
               workers: int | None = None, time_convention: str = "heard", sf_tol_s: float | None = None,
               sf_smooth_s: float = 3.0, sf_window_s: float = 60.0, sf_flat_ratio: float = INFLECTION_FLAT_RATIO,
               clock_anchor: str = "heard", triples: dict | None = None,
               comparable: bool = False, hypotheses: bool = False, null_n: int = NULL_N,
               temperature_c: float | None = None) -> tuple[pd.DataFrame, list[Segment]]:
    """Direct position determination by grid search (Amar & Weiss 2008 §IV): rank grid points for a two-event recording.

    Timing (PLAN Phase 2, item 1); the defaults are the original behaviour:
    - time_convention: "heard" pairs the fits' heard CPA times (t_cpa) against the table's t_heard;
      "emission" pairs their emission CPA times (t_cpa_emit) against its t_emit. tol_s is the gate's half-width.
    - sf_tol_s: if set, scoring drops a triple whose two modelled curves' Doppler-inflection gap differs from
      the fits' inflection gap by more than this (inflection_gate and doppler_inflection, with sf_smooth_s,
      sf_window_s and sf_flat_ratio). A triple where either can't be placed skips the gate and is counted unplaceable.
    - clock_anchor: "heard" maps unix to audio time so event 1's modelled heard CPA lands on its fit's;
      "steepest" so its modelled Doppler inflection lands on its fit's (heard where unplaceable).

    Sound speed: c, unless temperature_c (the ground temperature, C) is given. Then every propagation through
    the air, the CPA table's heard times and every modelled curve, uses each emission point's own speed at
    its mid-height temperature (atmosphere.point_sound_speed: ground - 3.25 C per km of height above the
    grid point), which follows the straight path's harmonic-mean speed to about 0.2 % under a standard
    lapse. c is still what the event fits use. With temperature_c None everything is as before.

    Comparable score (PLAN Phase 2, item 7, stage A); off by default:
    - comparable=True scores each event against its own decoy null (event_decoy_null): z_k = (s_k - median_k) / sigma_k,
      and ranks by Z = z1 + z2, so that scores from different event pairs are on one scale and a loud event
      doesn't win by being loud. "score" then holds Z, "raw_score" the old s1 + s2, and res.attrs["null"]
      each event's null (median, sigma, n, seed, sample hash). Event 2 is scored at event 1's shift, while
      its null maximises over shifts, so z2 errs low. null_n is the null's number of draws per event (also the
      null hypotheses=True scales its thresholds by).

    Hypotheses (PLAN Phase 2, item 7, stage B); off by default:
    - hypotheses=True replaces the speed and distance gates with each event's hypotheses (hypotheses.py): up to
      three optima from the least-squares fit of ridge()'s track and up to three from fit_event, each with
      sensitivity ranges in v, k = v^2/d, tau and f0, merged where they agree. A CPA row is admitted for an event
      if a hypothesis holds its speed and v^2/d. Every pair of the two events' hypotheses is joined at its own
      time offset, and each triple is scored with its event-1 hypothesis's heard CPA as the clock anchor and an
      f0 sweep widened to the hypotheses' f0 ranges. v_tol and d_tol set only the fallback for an event without
      an informative hypothesis (hypotheses.gate_hypothesis). res.attrs["hypotheses"] holds
      them, the funnel gains "event1_hypotheses" and "event2_hypotheses", and its event gates count admitted rows.
      It doesn't combine with sf_tol_s or the "steepest" anchor yet.

    cpa_cache: optional .npz path. The (grid point, flight) CPA table depends only on the grid
    (with its elevations), the traces, max_range and the speed of sound, not on the events, and is
    the slow part; with a path given it is reused when those inputs are identical, else computed
    and saved (see cached_cpa_table). workers: processes for building the table and for scoring the
    triples (parallel.default_jobs() by default); the result doesn't depend on it.

    Besides the ranked rows, the returned frame carries two dicts in `res.attrs`, set after the final sort.
    to_csv doesn't write them and pandas doesn't reliably carry attrs through operations, so read them from
    the returned frame itself:
    - "stages": {name: {"wall_s", "cpu_s"}} for "segments", "cpa_table", "pairing", "scoring" and
      "gap_report", in that order. CPU seconds include the process pool's workers.
    - "funnel": hypothesis counts after each filter: "cpa_rows" (the table), "event1_gates" and
      "event2_gates" (CPA rows within each event's speed and distance tolerances), "time_join"
      (triples whose heard-time gap matches the events' within tol_s), "silence" (left after the
      negative-information filter; equal to "time_join" when it is off) and "scored". The emission convention
      reports "emission_gate" in place of "time_join". With sf_tol_s set or the "steepest" anchor, the key
      "steepest_fall" counts the triples the inflection gate kept (unplaceable ones included) and "unplaceable"
      those it couldn't test.

    triples: if a dict is given, it receives the triples surviving each stage under the funnel's keys
    ("time_join" or "emission_gate", "silence", and "steepest_fall" when the inflection gate runs), as
    {"gidx", "seg1", "seg2"} int32 arrays; seg indexes the returned segments. The rows of the returned
    frame are the triples that reached scoring."""
    if time_convention not in ("heard", "emission"):
        raise ValueError(f"time_convention must be heard or emission, got {time_convention!r}")
    if clock_anchor not in ("heard", "steepest"):
        raise ValueError(f"clock_anchor must be heard or steepest, got {clock_anchor!r}")
    c = speed_of_sound() if c is None else c
    stages: dict = {}
    funnel: dict = {}
    bbox = search_bbox if search_bbox is not None else (grid.lat.min(), grid.lat.max(), grid.lon.min(), grid.lon.max())
    with _stage(stages, "segments"):
        log(f"{len(traces)} loaded traces")
        report_coverage(trace_metadata or {}, bbox, max_range_m, log)
        report_altitude_sources(traces, log)
        segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip_box(grid.enu, max_range_m))
        log(f"{len(segs)} airborne segments; grid of {len(grid)} points")
    with _stage(stages, "cpa_table"):
        cpa = cached_cpa_table(grid, segs, max_range_m, c, cpa_cache, workers=workers, temperature_c=temperature_c)
        log(f"{len(cpa)} (point, flight) CPA records")
    w1 = EventWindow.from_fit(sp, ev1, harmonics[0]); w2 = EventWindow.from_fit(sp, ev2, harmonics[1])
    nulls = None
    hyps: list = []
    with _stage(stages, "pairing"):
        emission = time_convention == "emission"
        if hypotheses:
            if sf_tol_s is not None or clock_anchor == "steepest":
                raise ValueError("hypotheses=True doesn't combine with the steepest-fall check or anchor yet")
            nulls = [event_decoy_null(w, cpa, segs, grid.enu, c, n=null_n, workers=workers, temperature_c=temperature_c) for w in (w1, w2)]
            hyps = [event_hypotheses(sp, w, ev, c, nl["sigma"], h, v_tol=v_tol, d_tol=d_tol)
                    for w, ev, nl, h in zip((w1, w2), (ev1, ev2), nulls, harmonics)]
            pairs = pair_hypotheses(cpa, hyps, tol_s, emission, silence_d_m, funnel, triples)
        else:
            dt = ev2.t_cpa_emit - ev1.t_cpa_emit if emission else ev2.t_cpa - ev1.t_cpa
            (v1, d1), (v2, d2) = rectangular_gate(ev1, v_tol, d_tol), rectangular_gate(ev2, v_tol, d_tol)
            pairs = pair_candidates(cpa, dt, tol_s=tol_s, time_col="t_emit" if emission else "t_heard",
                                    v1=v1, d1=d1, v2=v2, d2=d2, silence_d_m=silence_d_m, funnel=funnel, triples=triples)
        log(f"{len(pairs)} candidate (point, flight1, flight2) triples after offset + silence filters")
        sf = None
        if sf_tol_s is not None or clock_anchor == "steepest":
            sf = gate_settings(ev1, ev2, c, sf_tol_s, clock_anchor, sf_window_s, sf_smooth_s, sf_flat_ratio)
    with _stage(stages, "scoring"):
        used = np.union1d(pairs.seg1.to_numpy(), pairs.seg2.to_numpy())
        state = {"w1": w1, "w2": w2, "segs": {int(k): segs[k] for k in used}, "c": c, "sf": sf, "temperature_c": temperature_c}
        cols_in = [pairs[k].to_numpy() for k in ("gidx", "seg1", "seg2", "t_heard1", "t_emit1", "t_emit2")]
        if hypotheses:
            cols_in.append(np.array([hyps[0][int(i)].t_cpa for i in pairs.h1.to_numpy()]) if len(pairs) else np.zeros(0))
            state["f0_scales"] = tuple(f0_sweep(w, hs) for w, hs in zip((w1, w2), hyps))
        tasks = [(grid.enu[cols_in[0][a:a + SCORE_CHUNK]], *(x[a:a + SCORE_CHUNK] for x in cols_in[1:]))
                 for a in range(0, len(pairs), SCORE_CHUNK)]
        scores = []
        t0 = time.time()
        try:
            for part in ordered_map(_score_triples, tasks, min(resolve_jobs(workers), max(len(tasks), 1)), set_score_state, (state,)):
                scores.extend(part)
                if progress and len(scores) // 500 > (len(scores) - len(part)) // 500:
                    log(f"scored {len(scores)}/{len(pairs)} ({(time.time() - t0) / len(scores) * 1000:.0f} ms each)")
        finally:
            SCORE_STATE.clear()
        out = [(p.gidx, grid.lat[p.gidx], grid.lon[p.gidx], p.seg1, p.seg2, segs[p.seg1].icao, segs[p.seg2].icao, p.t_heard1, p.d1, p.v1, p.d2, p.v2, *sc)
               for p, (sc, _) in zip(pairs.itertuples(), scores) if sc is not None]
        if sf is not None:
            funnel["steepest_fall"] = len(out)
            funnel["unplaceable"] = sum(u for _, u in scores)
            if triples is not None:
                kept = np.array([sc is not None for sc, _ in scores], bool)
                triples["steepest_fall"] = stage_triples(pairs[kept])
        cols = ["gidx", "lat", "lon", "seg1", "seg2", "icao1", "icao2", "t_heard1", "d1", "v1", "d2", "v2", "score", "s1", "s2", "shift"]
        res = pd.DataFrame(out, columns=cols)
        if comparable:      # PLAN Phase 2 item 7, stage A: each event's score against its own null
            if hypotheses:  # the wrong flights get the same widened f0 sweep the candidates got
                nulls = [event_decoy_null(w, cpa, segs, grid.enu, c, n=null_n, workers=workers, f0_scales=sw, temperature_c=temperature_c)
                         for w, sw in zip((w1, w2), state["f0_scales"])]
            elif nulls is None:
                nulls = [event_decoy_null(w, cpa, segs, grid.enu, c, n=null_n, workers=workers, temperature_c=temperature_c) for w in (w1, w2)]
            res = pair_zscore(res, nulls)
        if hypotheses:      # one row per triple: the best of the clocks its event-1 hypotheses gave it
            funnel["scored_clocks"] = len(res)
            res = best_clock(res)
        res = res.sort_values("score", ascending=False).reset_index(drop=True)
        funnel["scored"] = len(res)
    with _stage(stages, "gap_report"):
        report_candidate_gaps(traces, res, sp, ev1, max_range_m, c, log)
    res.attrs["stages"] = stages
    res.attrs["funnel"] = funnel
    if comparable:
        res.attrs["null"] = {"event1": nulls[0], "event2": nulls[1]}
    if hypotheses:
        res.attrs["hypotheses"] = {"event1": [h.to_dict() for h in hyps[0]], "event2": [h.to_dict() for h in hyps[1]]}
    return res, segs


def refine(sp, ev1, ev2, segs, res_row, spacing_m=50.0, half_m=400.0, harmonics=(1, 1), elevation=None, c=None,
           extra: list[EventFit] | None = None, extra_harmonics: list[int] | None = None,
           max_range_m=DEFAULT_MAX_RANGE_M, workers: int | None = None, temperature_c: float | None = None):
    """The refinement stage of a coarse-to-fine search (Harvey 2018 §5.3.1): a fine square grid around one result
    row for one flight pair. temperature_c: see pair_grid_search.

    extra: further measured events (beyond the two the search used). For each, the flight is
    chosen once at the candidate point (pick_flight, nearest-neighbour association), then its modelled curve is scored at
    every fine point with the same time shift as event 1, so every event is locked to the
    same clock. A low, lateral pass pins the location far better than a high overhead one,
    which is what the extra events are for. Columns s3, s4, ... are added and summed into
    score; the chosen flights are returned in the DataFrame's .attrs["extra_icao"]. workers: processes
    for scoring the fine points (parallel.default_jobs() by default); the result doesn't depend on it."""
    from dopplertrack.components.scoring.curve_integral import EventWindow
    from dopplertrack.core.geometry import lla_to_enu
    c = speed_of_sound() if c is None else c
    extra = list(extra or []); extra_harmonics = list(extra_harmonics or [1] * len(extra))
    lat, lon = float(res_row.lat), float(res_row.lon)
    g = square_grid(lat, lon, half_m, spacing_m, elevation)
    # re-express grid in the segments' ENU frame (segments were built on the search grid origin)
    seg1, seg2 = segs[int(res_row.seg1)], segs[int(res_row.seg2)]
    w1 = EventWindow.from_fit(sp, ev1, harmonics[0]); w2 = EventWindow.from_fit(sp, ev2, harmonics[1])
    # choose the flight for each extra event at the candidate point itself
    if extra:
        el0 = float(elevation(np.array([lat]), np.array([lon]))[0]) if elevation else 0.0
        if not np.isfinite(el0):
            raise ValueError("terrain elevation is unavailable at the refinement centre; use --no-dem to explicitly assume sea level")
        obs0 = lla_to_enu(lat, lon, el0, res_row.lat0, res_row.lon0)
    t0_map0 = ev1.t_cpa - float(res_row.t_heard1)
    xsegs, xwins = [], []
    for ev, h in zip(extra, extra_harmonics):
        k, sc = pick_flight(sp, ev, segs, obs0, t0_map0, float(res_row["shift"]), h, c, max_range_m=max_range_m,
                            temperature_c=temperature_c)
        if k < 0:
            raise ValueError(f"no flight near the candidate at the time of the extra event at {ev.t_cpa:.0f} s")
        log(f"extra event at {ev.t_cpa:.0f} s: {segs[k].icao} (score {sc:.2f} at the candidate)")
        xsegs.append(segs[k]); xwins.append(EventWindow.from_fit(sp, ev, h))
    state = {"w1": w1, "w2": w2, "seg1": seg1, "seg2": seg2, "xsegs": xsegs, "xwins": xwins, "c": c,
             "temperature_c": temperature_c,
             "t_cpa1": ev1.t_cpa, "origin": (res_row.lat0, res_row.lon0)}
    tasks = [(g.lat[a:a + SCORE_CHUNK], g.lon[a:a + SCORE_CHUNK], g.elev[a:a + SCORE_CHUNK]) for a in range(0, len(g), SCORE_CHUNK)]
    rows = []
    try:
        for part in ordered_map(score_fine_points, tasks, min(resolve_jobs(workers), max(len(tasks), 1)), set_score_state, (state,)):
            rows.extend(part)
    finally:
        SCORE_STATE.clear()
    cols = ["lat", "lon", "score", "s1", "s2"] + [f"s{k + 3}" for k in range(len(extra))] + ["shift"]
    out = pd.DataFrame(rows, columns=cols).sort_values("score", ascending=False).reset_index(drop=True)
    out.attrs["extra_icao"] = [s.icao for s in xsegs]
    return out


# old name: run_single_search
def single_grid_search(sp: Spectrogram, ev: EventFit, traces: list[Trace], grid: Grid, t_cpa_unix: float,
                      tol_s: float = 30.0, harmonics: int = 1, v_tol=0.35, d_tol=(0.4, 2.5),
                      max_range_m=DEFAULT_MAX_RANGE_M, c=None, trace_metadata=None,
                      search_bbox=None, workers: int | None = None,
                      temperature_c: float | None = None) -> tuple[pd.DataFrame, list[Segment]]:
    """Grid search (Amar & Weiss 2008 §IV) for one event whose absolute time is known (±tol_s): rank grid points
    by how well the curve they would hear from each nearby flight matches the spectrogram. workers: processes
    for the CPA table (see cpa_table). temperature_c: see pair_grid_search."""
    from dopplertrack.components.scoring.trajectory_score import custom_single_score
    c = speed_of_sound() if c is None else c
    bbox = search_bbox if search_bbox is not None else (grid.lat.min(), grid.lat.max(), grid.lon.min(), grid.lon.max())
    report_coverage(trace_metadata or {}, bbox, max_range_m, log)
    report_altitude_sources(traces, log)
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=clip_box(grid.enu, max_range_m))
    # only segments alive around the event time
    keep = [s for s in segs if s.t[0] - 300 <= t_cpa_unix <= s.t[-1] + 300]
    log(f"{len(keep)} of {len(segs)} segments overlap the event time")
    cpa = cpa_table(grid, keep, max_range_m=max_range_m, c=c, workers=workers, temperature_c=temperature_c)
    m = in_gate(heard_near(cpa, t_cpa_unix, tol_s), *rectangular_gate(ev, v_tol, d_tol))
    log(f"{len(m)} candidate (point, flight) pairs")
    w = EventWindow.from_fit(sp, ev, harmonics)
    out = []
    for p in m.itertuples():
        s = custom_single_score(w, keep[p.seg], grid.enu[p.gidx], float(p.t_heard), c=c, temperature_c=temperature_c)
        out.append((p.gidx, grid.lat[p.gidx], grid.lon[p.gidx], p.seg, keep[p.seg].icao, p.t_heard, p.d, p.v, s))
    res = pd.DataFrame(out, columns=["gidx", "lat", "lon", "seg", "icao", "t_heard", "d", "v", "score"]).sort_values("score", ascending=False).reset_index(drop=True)
    return res, keep
