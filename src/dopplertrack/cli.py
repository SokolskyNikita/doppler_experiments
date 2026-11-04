"""dopplertrack command line."""
from __future__ import annotations

import argparse
import json

import numpy as np

from . import pipeline
from .adsb import load_trace_metadata, load_traces
from .audio import FFmpegNotFoundError, Spectrogram
from .coverage import DEFAULT_MAX_RANGE_M, report_coverage
from .parallel import JOBS_ENV
from .search import Grid
from .terrain import Terrain
from .tracks import EventFit, fit_event


def load_events(files, picks=None):
    """Read two individual fits or one ranked detect list with two 1-based ranks."""
    if picks is None and len(files) != 2:
        raise ValueError("use --events EV1.json EV2.json, or --events detected.json --pick 1 2")
    if picks is not None and len(files) != 1:
        raise ValueError("--pick requires exactly one detect JSON list")
    data = []
    for filename in files:
        with open(filename) as f:
            data.append(json.load(f))
    if picks is not None:
        events = data[0]
        if not isinstance(events, list):
            raise ValueError("--pick requires a JSON list written by detect")
        if len(set(picks)) != 2 or any(i < 1 or i > len(events) for i in picks):
            raise ValueError(f"--pick needs two distinct ranks between 1 and {len(events)}")
        data = [events[i - 1] for i in picks]
    if not all(isinstance(e, dict) for e in data):
        raise ValueError("event files must contain individual fits; select detect list entries with --pick")
    try:
        return [EventFit(**e) for e in data]
    except TypeError as exc:
        raise ValueError(f"invalid event fit: {exc}") from exc


def _jobs(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text!r}")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dopplertrack")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("spectrogram", help="audio/video file -> whitened low-band spectrogram (.npz)")
    s.add_argument("audio"); s.add_argument("out"); s.add_argument("--hop", type=float, default=0.25)
    s.add_argument("--fmin", type=float, default=40); s.add_argument("--fmax", type=float, default=450)

    f = sub.add_parser("fit", help="fit an ideal Doppler curve inside a time/frequency window")
    f.add_argument("spec"); f.add_argument("--window", nargs=2, type=float, required=True, metavar=("T0", "T1"))
    f.add_argument("--band", nargs=2, type=float, required=True, metavar=("FLO", "FHI"))
    f.add_argument("--harmonics", type=int, default=1); f.add_argument("--out")
    f.add_argument("--objective", choices=("brightness", "contrast"), default="brightness",
                   help="brightness: mean brightness under the curve (the docs/results fits); contrast: the sweep-weighted ridge contrast detect uses")

    d = sub.add_parser("detect", help="scan a whole spectrogram for Doppler events and rank them")
    d.add_argument("spec"); d.add_argument("--band", nargs=2, type=float, required=True, metavar=("FLO", "FHI"))
    d.add_argument("--harmonics", type=int, default=1); d.add_argument("--top", type=int, default=20)
    d.add_argument("--window", type=float, default=240.0); d.add_argument("--out", help="write ranked fits as a JSON list")
    d.add_argument("--min-score", type=float, default=0.0,
                   help="return only fits above this contrast score; may return no events (default: reject zero evidence, not a calibrated false-alarm threshold)")

    e = sub.add_parser("extract-region", help="pull traces touching a bbox out of an adsb.lol day archive")
    e.add_argument("archive_dir"); e.add_argument("out")
    e.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"))
    e.add_argument("--keep-jets", action="store_true")

    fd = sub.add_parser("fetch-day", help="stream one UTC day of adsb.lol history from GitHub, keeping traces in a bbox (no disk needed)")
    fd.add_argument("date", help="YYYY-MM-DD (UTC day)"); fd.add_argument("out")
    fd.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"))
    fd.add_argument("--keep-jets", action="store_true"); fd.add_argument("--pod", default="planes-readsb-prod-0")

    r = sub.add_parser("search", help="rank candidate locations for a two-event recording")
    r.add_argument("spec"); r.add_argument("--events", nargs="+", required=True, metavar="JSON")
    r.add_argument("--pick", nargs=2, type=int, metavar=("RANK1", "RANK2"), help="two 1-based ranks from one detect JSON list")
    r.add_argument("--traces", required=True); r.add_argument("--out", required=True)
    r.add_argument("--bbox", nargs=4, type=float, metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"))
    r.add_argument("--point", nargs=2, type=float, metavar=("LAT", "LON"), help="score a single known point instead of a grid")
    r.add_argument("--spacing", type=float, default=200.0); r.add_argument("--harmonics", nargs=2, type=int, default=(1, 1))
    r.add_argument("--no-dem", action="store_true"); r.add_argument("--no-silence", action="store_true")
    r.add_argument("--tol", type=float, default=6.0)
    r.add_argument("--cpa-cache", metavar="NPZ", help="cache the (point, flight) CPA table here; reused when the grid (with its elevations), traces, range and speed of sound are identical")

    rf = sub.add_parser("refine", help="fine grid around one search result, optionally adding more events")
    rf.add_argument("spec"); rf.add_argument("results", help="CSV written by search")
    rf.add_argument("--events", nargs="+", required=True, metavar="JSON")
    rf.add_argument("--pick", nargs=2, type=int, metavar=("RANK1", "RANK2"), help="two 1-based ranks from one detect JSON list")
    rf.add_argument("--traces", required=True); rf.add_argument("--out", required=True)
    rf.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"), help="the bbox the search used")
    rf.add_argument("--rank", type=int, default=1, help="which flight pair to refine, by rank in the results (1 = best)")
    rf.add_argument("--spacing", type=float, default=50.0); rf.add_argument("--half", type=float, default=600.0, help="half-width of the fine grid, m")
    rf.add_argument("--harmonics", nargs=2, type=int, default=(1, 1))
    rf.add_argument("--extra", nargs="*", default=[], metavar="EV_JSON", help="further events (from detect or fit) to score locked to the same clock")
    rf.add_argument("--extra-harmonics", nargs="*", type=int, default=[])
    rf.add_argument("--no-dem", action="store_true")

    g = sub.add_parser("search-single", help="rank locations for ONE event whose absolute time is known")
    g.add_argument("spec"); g.add_argument("--event", required=True); g.add_argument("--traces", required=True)
    g.add_argument("--utc", required=True, help="heard CPA time of the event, unix seconds or ISO-8601 UTC")
    g.add_argument("--tol", type=float, default=30.0); g.add_argument("--out", required=True)
    g.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("LATMIN", "LATMAX", "LONMIN", "LONMAX"))
    g.add_argument("--spacing", type=float, default=200.0); g.add_argument("--harmonics", type=int, default=1)
    g.add_argument("--no-dem", action="store_true")

    for parser in (d, r, g):
        parser.add_argument("--jobs", type=_jobs, metavar="N",
                            help=f"worker processes (default: ${JOBS_ENV}, else the performance-core count); "
                                 "results don't depend on it")
    for parser in (e, fd, r, rf, g):
        parser.add_argument("--max-range", type=float, default=DEFAULT_MAX_RANGE_M, metavar="METRES",
                            help="search range / extraction margin in metres (default: 12000); use the same value for extraction and search")

    a = ap.parse_args(argv)
    if hasattr(a, "max_range") and (not np.isfinite(a.max_range) or a.max_range <= 0):
        ap.error("--max-range must be finite and positive")
    if a.cmd in ("search", "refine"):
        try:
            ev1, ev2 = load_events(a.events, a.pick)
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    if a.cmd == "search" and bool(a.bbox) == bool(a.point):
        ap.error("search requires exactly one of --bbox or --point")
    if a.cmd == "detect" and (a.top < 1 or not np.isfinite(a.min_score)):
        ap.error("--top must be positive and --min-score must be finite")
    if a.cmd == "spectrogram":
        try:
            sp = pipeline.make_spectrogram(a.audio, a.out, hop_s=a.hop, fmin=a.fmin, fmax=a.fmax)
        except FFmpegNotFoundError as exc:
            ap.exit(2, f"dopplertrack: {exc}\n")
        print(f"wrote {a.out}: {sp.S.shape[0]} bins x {sp.S.shape[1]} frames")
    elif a.cmd == "fit":
        sp = Spectrogram.load(a.spec)
        ef = fit_event(sp, a.window[0], a.window[1], a.band[0], a.band[1], harmonics=a.harmonics,
                       objective=a.objective)
        js = json.dumps(ef.to_dict(), indent=1)
        print(js)
        if a.out:
            open(a.out, "w").write(js)
    elif a.cmd == "detect":
        from .tracks import detect_events
        sp = Spectrogram.load(a.spec)
        evs = detect_events(sp, a.band[0], a.band[1], harmonics=a.harmonics, top=a.top, window_s=a.window, min_score=a.min_score,
                            workers=a.jobs, progress=lambda k, n: print(f"\r  window {k}/{n}", end="", flush=True))
        print()
        if not evs:
            print("no flyovers found")
        print(f"{'rank':>4} {'t_cpa s':>9} {'f0 Hz':>7} {'v m/s':>6} {'d m':>7} {'score':>6}")
        for i, e in enumerate(evs):
            print(f"{i + 1:>4} {e.t_cpa:>9.1f} {e.f0:>7.1f} {e.v:>6.0f} {e.d:>7.0f} {e.score:>6.2f}")
        if a.out:
            json.dump([e.to_dict() for e in evs], open(a.out, "w"), indent=1)
    elif a.cmd == "extract-region":
        pipeline.extract_region(a.archive_dir, tuple(a.bbox), a.out, prop_only=not a.keep_jets, max_range_m=a.max_range)
    elif a.cmd == "fetch-day":
        pipeline.fetch_region(a.date, tuple(a.bbox), a.out, prop_only=not a.keep_jets, pod=a.pod, max_range_m=a.max_range)
    elif a.cmd == "search":
        sp = Spectrogram.load(a.spec)
        traces = load_traces(a.traces)
        elev = None if a.no_dem else Terrain().elevation
        if a.point:
            el = elev(np.array([a.point[0]]), np.array([a.point[1]])) if elev else np.zeros(1)
            grid = Grid.points([a.point[0]], [a.point[1]], el)
        else:
            grid = Grid.make(*a.bbox, a.spacing, elev)
        res, segs = pipeline.run_search(sp, ev1, ev2, traces, grid, harmonics=tuple(a.harmonics),
                                        silence_d_m=None if a.no_silence else 6000.0, tol_s=a.tol, cpa_cache=a.cpa_cache,
                                        max_range_m=a.max_range, trace_metadata=load_trace_metadata(a.traces),
                                        search_bbox=tuple(a.bbox) if a.bbox else (a.point[0], a.point[0], a.point[1], a.point[1]),
                                        workers=a.jobs)
        res["lat0"] = grid.lat0; res["lon0"] = grid.lon0
        res.to_csv(a.out, index=False)
        print(res.head(20).to_string())
    elif a.cmd == "refine":
        import pandas as pd
        sp = Spectrogram.load(a.spec)
        extra = [EventFit(**json.load(open(p))) for p in a.extra]
        xh = list(a.extra_harmonics) + [1] * (len(extra) - len(a.extra_harmonics))
        res = pd.read_csv(a.results)
        best = res.sort_values("score", ascending=False).drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
        row = best.iloc[a.rank - 1]
        traces = load_traces(a.traces)
        report_coverage(load_trace_metadata(a.traces), tuple(a.bbox), a.max_range, pipeline.log)
        elev = None if a.no_dem else Terrain().elevation
        segs = pipeline.segments_for_search(traces, tuple(a.bbox), float(row.lat0), float(row.lon0), max_range_m=a.max_range)
        row = pipeline.relocate_row(row, segs, ev2.t_cpa - ev1.t_cpa)
        print(f"refining rank {a.rank}: {row.icao1}/{row.icao2} at {row.lat:.5f}, {row.lon:.5f} (score {row.score:.2f})")
        fine = pipeline.refine(sp, ev1, ev2, segs, row, spacing_m=a.spacing, half_m=a.half, harmonics=tuple(a.harmonics),
                               elevation=elev, extra=extra, extra_harmonics=xh, max_range_m=a.max_range)
        fine.to_csv(a.out, index=False)
        b = fine.iloc[0]
        print(f"peak score {b.score:.2f} at {b.lat:.6f}, {b.lon:.6f}" + (f"; extra flights {fine.attrs['extra_icao']}" if extra else ""))
        print(fine.head(10).to_string())
    elif a.cmd == "search-single":
        from datetime import datetime, timezone
        sp = Spectrogram.load(a.spec)
        ev = EventFit(**json.load(open(a.event)))
        traces = load_traces(a.traces)
        try:
            t_unix = float(a.utc)
        except ValueError:
            t_unix = datetime.fromisoformat(a.utc.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        elev = None if a.no_dem else Terrain().elevation
        grid = Grid.make(*a.bbox, a.spacing, elev)
        res, segs = pipeline.run_single_search(sp, ev, traces, grid, t_unix, tol_s=a.tol, harmonics=a.harmonics,
                                               max_range_m=a.max_range, trace_metadata=load_trace_metadata(a.traces),
                                               search_bbox=tuple(a.bbox), workers=a.jobs)
        res["lat0"] = grid.lat0; res["lon0"] = grid.lon0
        res.to_csv(a.out, index=False)
        print(res.head(20).to_string())


if __name__ == "__main__":
    main()
