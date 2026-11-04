"""High-level pipeline steps that the CLI and notebooks share."""
from __future__ import annotations

import contextlib
import os
import time

import numpy as np
import pandas as pd

from .adsb import AircraftTypes, Trace, load_region, save_traces
from .audio import Spectrogram, compute_spectrogram, load_audio
from .coverage import (DEFAULT_MAX_RANGE_M, ScanReport, extraction_metadata, padded_bbox,
                       report_altitude_sources, report_candidate_gaps, report_coverage)
from .doppler import ideal_curve, speed_of_sound
from .parallel import ordered_map, resolve_jobs
from .score import SF_FLAT_RATIO, EventWindow, locked_score, modelled_curve, steepest_fall
from .search import (Grid, Segment, build_segments, cpa_fingerprint, cpa_table, pair_candidates, save_cpa_table,
                     load_cpa_table, stage_triples)
from .tracks import EventFit


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
                     workers: int | None = None) -> pd.DataFrame:
    """cpa_table(), reusing the table saved at `path` if it was built from identical inputs (cpa_fingerprint).
    A lock file next to it makes a second process wait for the first instead of computing the same table."""
    if not path:
        return cpa_table(grid, segs, max_range_m=max_range_m, c=c, workers=workers)
    fp = cpa_fingerprint(grid, segs, max_range_m, c)
    with _file_lock(f"{path}.lock"):
        if os.path.exists(path):
            cpa = load_cpa_table(path, fp)
            if cpa is not None:
                log(f"loaded CPA table from {path}")
                return cpa
            log(f"{path} was built from other inputs; recomputing")
        cpa = cpa_table(grid, segs, max_range_m=max_range_m, c=c, workers=workers)
        save_cpa_table(path, cpa, fp)
        return cpa


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
    from .fetch import fetch_day
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
    from .geo import lla_to_enu
    la = np.array([bbox[0], bbox[0], bbox[1], bbox[1]]); lo = np.array([bbox[2], bbox[3], bbox[2], bbox[3]])
    enu = lla_to_enu(la, lo, np.zeros(4), lat0, lon0)
    clip = (enu[:, 0].min() - max_range_m, enu[:, 0].max() + max_range_m, enu[:, 1].min() - max_range_m, enu[:, 1].max() + max_range_m)
    return build_segments(traces, lat0, lon0, clip_enu=clip)


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


SCORE_CHUNK = 250       # triples (or fine points) per task when scoring across a pool
_SCORE_STATE: dict = {}


def _set_score_state(state: dict):
    """Pool initializer: what every scoring task shares, sent once per worker instead of with each task."""
    _SCORE_STATE.clear()
    _SCORE_STATE.update(state)


def _score_triples(task) -> list[tuple[tuple[float, float, float, float] | None, bool]]:
    """locked_score for a chunk of (observer ENU, segment 1, segment 2, heard time of segment 1, emission
    times of segments 1 and 2). Each result is (scores, unplaceable): scores is None for a triple the
    steepest-fall check rejects, and unplaceable says a steepest fall couldn't be placed, so the check
    was skipped and, under the steepest anchor, the heard anchor used instead."""
    obs, seg1, seg2, t_heard1, t_emit1, t_emit2 = task
    w1, w2, segs, c, sf = (_SCORE_STATE[k] for k in ("w1", "w2", "segs", "c", "sf"))
    out: list[tuple[tuple[float, float, float, float] | None, bool]] = []
    for o, a, b, th, te1, te2 in zip(obs, seg1, seg2, t_heard1, t_emit1, t_emit2):
        to1, r1 = modelled_curve(segs[int(a)], o, c)
        to2, r2 = modelled_curve(segs[int(b)], o, c)
        t0_map, unplaceable = None, False
        if sf is not None:
            m1 = steepest_fall(to1, r1, float(te1), sf["window_s"], sf["smooth_s"], sf["flat_ratio"])
            m2 = steepest_fall(to2, r2, float(te2), sf["window_s"], sf["smooth_s"], sf["flat_ratio"])
            f1, f2 = sf["fit"]
            if m1 is None or m2 is None or f1 is None or f2 is None:
                unplaceable = True
            else:
                if sf["tol_s"] is not None and abs((m2 - m1) - (f2 - f1)) > sf["tol_s"]:
                    out.append((None, False))
                    continue
                if sf["anchor"] == "steepest":
                    t0_map = f1 - m1
        out.append((locked_score(w1, w2, segs[int(a)], segs[int(b)], o, float(th), c=c,
                                 curves=(to1, r1, to2, r2), t0_map=t0_map), unplaceable))
    return out


def fitted_steepest_fall(ev: EventFit, c: float, window_s: float = 60.0, smooth_s: float = 3.0,
                         flat_ratio: float = SF_FLAT_RATIO) -> float | None:
    """steepest_fall of a fit's own ideal curve, in recording seconds (within 0.3 s of t_cpa_emit for the
    development fits)."""
    tq = ev.t_cpa_emit + np.arange(-window_s - smooth_s - 2, window_s + smooth_s + 3, 1.0)
    return steepest_fall(tq, ideal_curve(tq, ev.f0, ev.v, ev.d, ev.t_cpa_emit, c=c) / ev.f0, ev.t_cpa_emit,
                         window_s, smooth_s, flat_ratio)


def run_search(sp: Spectrogram, ev1: EventFit, ev2: EventFit, traces: list[Trace], grid: Grid,
               harmonics=(1, 1), tol_s=6.0, v_tol=0.35, d_tol=(0.4, 2.5), silence_d_m=6000.0,
               max_range_m=DEFAULT_MAX_RANGE_M, c=None, top_pairs=None, progress=True,
               cpa_cache=None, trace_metadata=None, search_bbox=None,
               workers: int | None = None, time_convention: str = "heard", sf_tol_s: float | None = None,
               sf_smooth_s: float = 3.0, sf_window_s: float = 60.0, sf_flat_ratio: float = SF_FLAT_RATIO,
               clock_anchor: str = "heard", triples: dict | None = None) -> tuple[pd.DataFrame, list[Segment]]:
    """Rank grid points for a two-event recording.

    Timing (PLAN Phase 2, item 1); the defaults are the original behaviour:
    - time_convention: "heard" pairs the fits' heard CPA times (t_cpa) against the table's t_heard;
      "emission" pairs their emission CPA times (t_cpa_emit) against its t_emit. tol_s is the gate's half-width.
    - sf_tol_s: if set, scoring drops a triple whose two modelled curves' steepest-fall gap differs from
      the fits' steepest-fall gap by more than this (score.steepest_fall, with sf_smooth_s, sf_window_s
      and sf_flat_ratio). A triple where either can't be placed skips the check and is counted unplaceable.
    - clock_anchor: "heard" maps unix to audio time so event 1's modelled heard CPA lands on its fit's;
      "steepest" so its modelled steepest fall lands on its fit's (heard where unplaceable).

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
      silence filter; equal to "time_join" when it is off) and "scored". The emission convention reports
      "emission_gate" in place of "time_join". With sf_tol_s set or the steepest anchor, "steepest_fall"
      counts the triples the check kept (unplaceable ones included) and "unplaceable" those it couldn't test.

    triples: if a dict is given, it receives the triples surviving each stage under the funnel's keys
    ("time_join" or "emission_gate", "silence", and "steepest_fall" when the check runs), as
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
        e0, e1 = grid.enu[:, 0].min() - max_range_m, grid.enu[:, 0].max() + max_range_m
        n0, n1 = grid.enu[:, 1].min() - max_range_m, grid.enu[:, 1].max() + max_range_m
        segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(e0, e1, n0, n1))
        log(f"{len(segs)} airborne segments; grid of {len(grid)} points")
    with _stage(stages, "cpa_table"):
        cpa = cached_cpa_table(grid, segs, max_range_m, c, cpa_cache, workers=workers)
        log(f"{len(cpa)} (point, flight) CPA records")
    with _stage(stages, "pairing"):
        emission = time_convention == "emission"
        dt = ev2.t_cpa_emit - ev1.t_cpa_emit if emission else ev2.t_cpa - ev1.t_cpa
        pairs = pair_candidates(cpa, dt, tol_s=tol_s, time_col="t_emit" if emission else "t_heard",
                                v1=(ev1.v * (1 - v_tol), ev1.v * (1 + v_tol)), d1=(ev1.d * d_tol[0], ev1.d * d_tol[1]),
                                v2=(ev2.v * (1 - v_tol), ev2.v * (1 + v_tol)), d2=(ev2.d * d_tol[0], ev2.d * d_tol[1]),
                                silence_d_m=silence_d_m, funnel=funnel, triples=triples)
        log(f"{len(pairs)} candidate (point, flight1, flight2) triples after offset + silence filters")
        sf = None
        if sf_tol_s is not None or clock_anchor == "steepest":
            sf = {"tol_s": sf_tol_s, "anchor": clock_anchor, "window_s": sf_window_s, "smooth_s": sf_smooth_s,
                  "flat_ratio": sf_flat_ratio,
                  "fit": tuple(fitted_steepest_fall(e, c, sf_window_s, sf_smooth_s, sf_flat_ratio) for e in (ev1, ev2))}
    with _stage(stages, "scoring"):
        w1 = EventWindow.from_fit(sp, ev1, harmonics[0]); w2 = EventWindow.from_fit(sp, ev2, harmonics[1])
        used = np.union1d(pairs.seg1.to_numpy(), pairs.seg2.to_numpy())
        state = {"w1": w1, "w2": w2, "segs": {int(k): segs[k] for k in used}, "c": c, "sf": sf}
        cols_in = [pairs[k].to_numpy() for k in ("gidx", "seg1", "seg2", "t_heard1", "t_emit1", "t_emit2")]
        tasks = [(grid.enu[cols_in[0][a:a + SCORE_CHUNK]], *(x[a:a + SCORE_CHUNK] for x in cols_in[1:]))
                 for a in range(0, len(pairs), SCORE_CHUNK)]
        scores = []
        t0 = time.time()
        try:
            for part in ordered_map(_score_triples, tasks, min(resolve_jobs(workers), max(len(tasks), 1)), _set_score_state, (state,)):
                scores.extend(part)
                if progress and len(scores) // 500 > (len(scores) - len(part)) // 500:
                    log(f"scored {len(scores)}/{len(pairs)} ({(time.time() - t0) / len(scores) * 1000:.0f} ms each)")
        finally:
            _SCORE_STATE.clear()
        out = [(p.gidx, grid.lat[p.gidx], grid.lon[p.gidx], p.seg1, p.seg2, segs[p.seg1].icao, segs[p.seg2].icao, p.t_heard1, p.d1, p.v1, p.d2, p.v2, *sc)
               for p, (sc, _) in zip(pairs.itertuples(), scores) if sc is not None]
        if sf is not None:
            funnel["steepest_fall"] = len(out)
            funnel["unplaceable"] = sum(u for _, u in scores)
            if triples is not None:
                kept = np.array([sc is not None for sc, _ in scores], bool)
                triples["steepest_fall"] = stage_triples(pairs[kept])
        cols = ["gidx", "lat", "lon", "seg1", "seg2", "icao1", "icao2", "t_heard1", "d1", "v1", "d2", "v2", "score", "s1", "s2", "shift"]
        res = pd.DataFrame(out, columns=cols).sort_values("score", ascending=False).reset_index(drop=True)
        funnel["scored"] = len(res)
    with _stage(stages, "gap_report"):
        report_candidate_gaps(traces, res, sp, ev1, max_range_m, c, log)
    res.attrs["stages"] = stages
    res.attrs["funnel"] = funnel
    return res, segs


def pick_flight(sp: Spectrogram, ev: EventFit, segs: list[Segment], obs_enu, t0_map: float, shift: float,
                harmonics: int = 1, c=None, max_range_m=DEFAULT_MAX_RANGE_M, alive_pad_s=300.0) -> tuple[int, float]:
    """Which flight does an observer at obs_enu hear as `ev`, given the recording's time map
    (audio = unix + t0_map) and the time shift already chosen for event 1? Returns
    (segment index, locked score); (-1, 0) if no flight is near at that time."""
    from .score import EventWindow, modelled_curve
    c = speed_of_sound() if c is None else c
    w = EventWindow.from_fit(sp, ev, harmonics)
    t_unix = ev.t_cpa - t0_map
    best, best_s = -1, 0.0
    for k, seg in enumerate(segs):
        if not (seg.t[0] - alive_pad_s <= t_unix <= seg.t[-1] + alive_pad_s):
            continue
        if np.linalg.norm(seg.enu - obs_enu, axis=1).min() > max_range_m:
            continue
        to, r = modelled_curve(seg, obs_enu, c)
        sc = float(w.sweep_scores(to + t0_map, r, [shift], np.arange(0.95, 1.0501, 0.005)).max())
        if sc > best_s:
            best, best_s = k, sc
    return best, best_s


def _score_fine_points(task) -> list[tuple]:
    """refine's row for each fine point of a chunk: (lat, lon, score, s1, s2, s3..., shift)."""
    from .geo import lla_to_enu
    from .score import modelled_curve
    st = _SCORE_STATE
    c, seg1 = st["c"], st["seg1"]
    rows = []
    for lat, lon, elev in zip(*task):
        obs = lla_to_enu(lat, lon, elev, *st["origin"])
        d = np.linalg.norm(seg1.enu - obs, axis=1); j = int(np.argmin(d)); t_heard1 = seg1.t[j] + d[j] / c
        tot, s1, s2, sh = locked_score(st["w1"], st["w2"], seg1, st["seg2"], obs, float(t_heard1), c=c)
        t0_map = st["t_cpa1"] - float(t_heard1)
        xs = []
        for seg, w in zip(st["xsegs"], st["xwins"]):
            to, r = modelled_curve(seg, obs, c)
            xs.append(float(w.sweep_scores(to + t0_map, r, [sh], np.arange(0.95, 1.0501, 0.005)).max()))
        rows.append((lat, lon, tot + sum(xs), s1, s2, *xs, sh))
    return rows


def refine(sp, ev1, ev2, segs, res_row, spacing_m=50.0, half_m=400.0, harmonics=(1, 1), elevation=None, c=None,
           extra: list[EventFit] | None = None, extra_harmonics: list[int] | None = None,
           max_range_m=DEFAULT_MAX_RANGE_M, workers: int | None = None):
    """Fine grid around one result row for one flight pair.

    extra: further measured events (beyond the two the search used). For each, the flight is
    chosen once at the candidate point (pick_flight), then its modelled curve is scored at
    every fine point with the same time shift as event 1, so every event is locked to the
    same clock. A low, lateral pass pins the location far better than a high overhead one,
    which is what the extra events are for. Columns s3, s4, ... are added and summed into
    score; the chosen flights are returned in the DataFrame's .attrs["extra_icao"]. workers: processes
    for scoring the fine points (parallel.default_jobs() by default); the result doesn't depend on it."""
    from .score import EventWindow
    from .geo import lla_to_enu
    c = speed_of_sound() if c is None else c
    extra = list(extra or []); extra_harmonics = list(extra_harmonics or [1] * len(extra))
    lat, lon = float(res_row.lat), float(res_row.lon)
    dlat = half_m / 111320.0; dlon = half_m / (111320.0 * np.cos(np.radians(lat)))
    g = Grid.make(lat - dlat, lat + dlat, lon - dlon, lon + dlon, spacing_m, elevation)
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
        k, sc = pick_flight(sp, ev, segs, obs0, t0_map0, float(res_row["shift"]), h, c, max_range_m=max_range_m)
        if k < 0:
            raise ValueError(f"no flight near the candidate at the time of the extra event at {ev.t_cpa:.0f} s")
        log(f"extra event at {ev.t_cpa:.0f} s: {segs[k].icao} (score {sc:.2f} at the candidate)")
        xsegs.append(segs[k]); xwins.append(EventWindow.from_fit(sp, ev, h))
    state = {"w1": w1, "w2": w2, "seg1": seg1, "seg2": seg2, "xsegs": xsegs, "xwins": xwins, "c": c,
             "t_cpa1": ev1.t_cpa, "origin": (res_row.lat0, res_row.lon0)}
    tasks = [(g.lat[a:a + SCORE_CHUNK], g.lon[a:a + SCORE_CHUNK], g.elev[a:a + SCORE_CHUNK]) for a in range(0, len(g), SCORE_CHUNK)]
    rows = []
    try:
        for part in ordered_map(_score_fine_points, tasks, min(resolve_jobs(workers), max(len(tasks), 1)), _set_score_state, (state,)):
            rows.extend(part)
    finally:
        _SCORE_STATE.clear()
    cols = ["lat", "lon", "score", "s1", "s2"] + [f"s{k + 3}" for k in range(len(extra))] + ["shift"]
    out = pd.DataFrame(rows, columns=cols).sort_values("score", ascending=False).reset_index(drop=True)
    out.attrs["extra_icao"] = [s.icao for s in xsegs]
    return out


def run_single_search(sp: Spectrogram, ev: EventFit, traces: list[Trace], grid: Grid, t_cpa_unix: float,
                      tol_s: float = 30.0, harmonics: int = 1, v_tol=0.35, d_tol=(0.4, 2.5),
                      max_range_m=DEFAULT_MAX_RANGE_M, c=None, trace_metadata=None,
                      search_bbox=None, workers: int | None = None) -> tuple[pd.DataFrame, list[Segment]]:
    """One event whose absolute time is known (±tol_s): rank grid points by how well the
    curve they would hear from each nearby flight matches the spectrogram. workers: processes
    for the CPA table (see cpa_table)."""
    from .score import single_score
    c = speed_of_sound() if c is None else c
    bbox = search_bbox if search_bbox is not None else (grid.lat.min(), grid.lat.max(), grid.lon.min(), grid.lon.max())
    report_coverage(trace_metadata or {}, bbox, max_range_m, log)
    report_altitude_sources(traces, log)
    e0, e1 = grid.enu[:, 0].min() - max_range_m, grid.enu[:, 0].max() + max_range_m
    n0, n1 = grid.enu[:, 1].min() - max_range_m, grid.enu[:, 1].max() + max_range_m
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(e0, e1, n0, n1))
    # only segments alive around the event time
    keep = [s for s in segs if s.t[0] - 300 <= t_cpa_unix <= s.t[-1] + 300]
    log(f"{len(keep)} of {len(segs)} segments overlap the event time")
    cpa = cpa_table(grid, keep, max_range_m=max_range_m, c=c, workers=workers)
    m = cpa[(cpa.t_heard - t_cpa_unix).abs() <= tol_s]
    m = m[m.v.between(ev.v * (1 - v_tol), ev.v * (1 + v_tol)) & m.d.between(ev.d * d_tol[0], ev.d * d_tol[1])]
    log(f"{len(m)} candidate (point, flight) pairs")
    w = EventWindow.from_fit(sp, ev, harmonics)
    out = []
    for p in m.itertuples():
        s = single_score(w, keep[p.seg], grid.enu[p.gidx], float(p.t_heard), c=c)
        out.append((p.gidx, grid.lat[p.gidx], grid.lon[p.gidx], p.seg, keep[p.seg].icao, p.t_heard, p.d, p.v, s))
    res = pd.DataFrame(out, columns=["gidx", "lat", "lon", "seg", "icao", "t_heard", "d", "v", "score"]).sort_values("score", ascending=False).reset_index(drop=True)
    return res, keep
