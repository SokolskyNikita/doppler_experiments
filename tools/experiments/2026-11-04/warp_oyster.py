"""PLAN Phase 2 item 8: emission-time resampling against today's curve score and a trajectory least-squares
fit, on the frozen Oyster Bay events, one candidate set for all scorers.

Candidates: the reference (the true point, flights a1dfeb and ace391) and up to ten wrong ones taken
greedily from the development search's ranking (docs/results/oyster_bay_search_best_per_pair.csv), each
at least 5 km from the truth and from every one already taken, each with its own flight pair. Wrong-box
test: the same for the moved boxes' top candidates from today's search (bench saved-fit runs).
Events: the README windows, ev1 2090-2200 s at 95-200 Hz and ev2 3020-3130 s at 95-195 Hz, with the saved
fits' f0 (docs/results/oyster_bay_ev*.json).
Freedom, the same for every scorer: a clock T joint across the two events, searched around each
candidate's own clock over +-CLOCK_SPAN s, coarse to fine (CLOCK_STEPS); each event's fundamental over
0.85-1.15x its fitted f0.
Scorers:
  1a  today's curve score (EventWindow.sweep_scores) on local_whiten, README harmonics
  1b  the same on a background taken across frequency (+-10 Hz median per frame), not over time
  2   least squares of ridge() tracks to the trajectory's Doppler factor, f0 in closed form
      (f0 = sum D f / sum D^2) for harmonic orders 1-3 within the f0 range; score = -(rms rel. residual)
  3   the warp: 4 kHz output grid, sinc 32 taps after a low-pass at 1.48 kHz, 2.048 s Hann blocks at
      0.512 s, across-frequency background +-10 Hz, 3 harmonics pooled over those inside the scoring grid
      (40-700 Hz, or 40-450 Hz on the band-limited pass), off state, two families;
      strict (one f0 per event, judged) and bounded drift (reported)
Outcomes: the reference's rank, z = (s_ref - s_best_wrong) / MAD(candidates' scores) and the raw
difference, the wrong-box count (box winners reaching the reference's score), the refined error around
each scorer's top candidate, and runtimes.

usage: warp_oyster.py RUN [full|band] [rank|wrongbox|all|refine]   (refine reads the all run's ranking)"""
import json
import os
import sys
import time
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
import numpy as np                                                       # noqa: E402
import pandas as pd                                                      # noqa: E402
import scipy.signal as ss                                                # noqa: E402

from dopplertrack import audio, warp as W                                # noqa: E402
from dopplertrack.adsb import load_traces                                # noqa: E402
from dopplertrack.audio import Spectrogram                               # noqa: E402
from dopplertrack.geo import lla_to_enu                                  # noqa: E402
from dopplertrack.score import EventWindow, modelled_curve               # noqa: E402
from dopplertrack.search import build_segments                           # noqa: E402
from dopplertrack.terrain import Terrain                                 # noqa: E402
from dopplertrack.tracks import EventFit, local_whiten, ridge            # noqa: E402

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
REPO = Path(__file__).resolve().parents[3]
SR, C = 4000, 340.0
TRUTH = (40.876466, -73.524951)
PAIR = ("a1dfeb", "ace391")
CLOCK_SPAN = 15.0
CLOCK_STEPS = (0.5, 0.1, 0.02)          # coarse to fine: each stage searches +-2 steps of the previous around its best
F0_RANGE = (0.85, 1.15)
BG_HZ, HARM, BLOCK, HOP = 10.0, 3, 8192, 2048
MAX_RATE = 1.35
EVENTS = [dict(window=(2090.0, 2200.0), band=(95.0, 200.0), harmonics=2, fit="oyster_bay_ev1.json"),
          dict(window=(3020.0, 3130.0), band=(95.0, 195.0), harmonics=1, fit="oyster_bay_ev2.json")]
BOXES = {"moved-wsw150": ("runs/2026-11-04-bench-5314396-saved-fit-t2/oyster-bay-moved-wsw150/result.json",
                          "derived/traces/2026-09-08/ny_wsw150.npz"),
         "moved-north150": ("runs/2026-11-04-bench-4088419-t2/oyster-bay-moved-north150/result.json",
                            "derived/traces/2026-09-08/ny_north150.npz")}


def haversine(lat1, lon1, lat2, lon2):
    p = np.radians
    a = np.sin(p(lat2 - lat1) / 2) ** 2 + np.cos(p(lat1)) * np.cos(p(lat2)) * np.sin(p(lon2 - lon1) / 2) ** 2
    return 6371000.0 * 2 * np.arcsin(np.sqrt(a))


def greedy(rows, n=10, sep=5000.0, avoid=()):
    out = []
    for r in rows:
        pts = list(avoid) + [(o["lat"], o["lon"]) for o in out]
        if all(haversine(r["lat"], r["lon"], a, b) >= sep for a, b in pts):
            out.append(r)
        if len(out) >= n:
            break
    return out


# ---- the shared state of a run (audio, spectrograms, windows, tracks) --------------------------------

class Case:
    def __init__(self, band_limited: bool):
        x, _ = audio.load_audio(DATA / "raw/audio/youtube/oyster_bay.webm", SR)
        if band_limited:
            x = W.bandpass(x, SR, 40.0, 450.0).astype(np.float32)
        self.x = x
        self.f_top = 450.0 if band_limited else 700.0      # the scoring grid's top: harmonics above it are unobserved
        self.xf = W.lowpass(x, SR, SR / (2 * MAX_RATE))
        self.fits = [EventFit(**json.load(open(REPO / "docs/results" / e["fit"]))) for e in EVENTS]
        sp = audio.compute_spectrogram(x, SR)
        self.win_a = [EventWindow.from_fit(sp, f, e["harmonics"]) for f, e in zip(self.fits, EVENTS)]
        # (1b): un-whitened dB, background across frequency per frame
        _, _, Z = ss.stft(x, SR, nperseg=8192, noverlap=8192 - 1000, window="hann", boundary=None, padded=False)
        fz = np.fft.rfftfreq(8192, 1 / SR); band = (fz >= 40) & (fz <= self.f_top)
        db = (10 * np.log10(np.abs(Z[band]) ** 2 + 1e-20)).T                     # (T, F)
        bg = W.across_frequency(db, fz[1] - fz[0], BG_HZ).T.astype(np.float32)
        spb = Spectrogram((8192 / 2 + np.arange(Z.shape[1]) * 1000) / SR, fz[band], bg)
        self.win_b = []
        for f, e in zip(self.fits, EVENTS):
            crop = spb.crop(f.t_start - 40, f.t_end + 40, max(f.f_post * 0.8, spb.f[0]), min(f.f_pre * 1.25 * e["harmonics"], spb.f[-1]))
            self.win_b.append(EventWindow(f, crop, e["harmonics"]))
        # (2): ridge() tracks in each window
        self.tracks = []
        for e in EVENTS:
            w = local_whiten(sp.crop(*e["window"], *e["band"]))
            self.tracks.append((w.t, ridge(w)))

    def clocks(self, base, scorer):
        """Coarse-to-fine joint clock search: scorer(T) -> (score, detail); returns the best."""
        best = None
        grid = base + np.arange(-CLOCK_SPAN, CLOCK_SPAN + 1e-9, CLOCK_STEPS[0])
        for k, step in enumerate(CLOCK_STEPS):
            if k:
                grid = best[1] + np.arange(-2 * CLOCK_STEPS[k - 1], 2 * CLOCK_STEPS[k - 1] + 1e-9, step)
            for T in grid:
                s, det = scorer(T)
                if best is None or s > best[0]:
                    best = (s, float(T), det)
        return best


def seg_for(segs, icao, obs, t_audio, amt):
    """The segment of this aircraft whose heard CPA is closest to audio time t_audio."""
    best = None
    for s in segs:
        if s.icao != icao:
            continue
        r = np.linalg.norm(s.enu - obs[None, :], axis=1)
        th = s.t + r / C + amt
        k = int(np.argmin(np.abs(th - t_audio)))
        if best is None or abs(th[k] - t_audio) < best[0]:
            best = (abs(th[k] - t_audio), s)
    return best[1]


# ---- scorers ------------------------------------------------------------------------------------------

def score_curve(case, wins, curves, T):
    """Joint clock: both events' best f0 at audio = unix + T; sums the two."""
    tot, det = 0.0, []
    for w, (to, r), f in zip(wins, curves, case.fits):
        sc = w.sweep_scores(to + T, r, [0.0], np.arange(F0_RANGE[0], F0_RANGE[1] + 1e-9, 0.005))
        tot += float(sc.max()); det.append(float(sc.max()))
    return tot, det


def score_ls(case, curves, T):
    tot, det = 0.0, []
    for (tt, ff), (to, r), f in zip(case.tracks, curves, case.fits):
        D = np.interp(tt, to + T, r, left=np.nan, right=np.nan)
        ok = np.isfinite(D)
        if ok.sum() < 20:
            det.append(None); tot += -1.0
            continue
        best = None
        for h in (1, 2, 3):
            f0 = float(np.dot(D[ok], ff[ok]) / np.dot(D[ok], D[ok])) / h
            f0 = float(np.clip(f0, F0_RANGE[0] * f.f0, F0_RANGE[1] * f.f0))
            rms = float(np.sqrt(np.mean(((ff[ok] - h * f0 * D[ok]) / ff[ok]) ** 2)))
            if best is None or rms < best[0]:
                best = (rms, h, f0)
        tot += -best[0]; det.append(best)
    return tot, det


def warp_event(case, seg, obs, T, e):
    """Background-normalised blocks of the warped event, or None if the geometry is refused."""
    t0, t1 = e["window"]
    r = np.linalg.norm(seg.enu - obs[None, :], axis=1)
    th = seg.t + r / C + T
    m = (th >= t0) & (th <= t1)
    if m.sum() < 5:
        return None
    try:
        w = W.warp(case.xf, SR, T, seg.t, seg.enu, obs, C, float(seg.t[m][0]), float(seg.t[m][-1]),
                   valid=seg.valid, prefiltered=True, max_rate=MAX_RATE)
    except ValueError:
        return None
    cen, f, db = W.block_db(w.y, SR, BLOCK, HOP)
    band = (f >= 40) & (f <= case.f_top)
    if len(cen) == 0:
        return None
    return W.across_frequency(db[:, band], f[1] - f[0], BG_HZ), f[band]


def score_warp(case, segs2, obs, T, theta, birth, drift_hz=None, cache=None):
    tot, det = 0.0, []
    for k, (seg, e, f) in enumerate(zip(segs2, EVENTS, case.fits)):
        key = (k, round(T, 4))
        blk = cache.get(key) if cache is not None else None
        if blk is None:
            blk = warp_event(case, seg, obs, T, e)
            if cache is not None:
                cache[key] = blk if blk is not None else False
        if blk is None or blk is False:
            det.append(None)
            continue
        S, fb = blk
        ts = W.tone_score(S, fb, F0_RANGE[0] * f.f0, F0_RANGE[1] * f.f0, HARM, theta, birth, drift_hz)
        tot += ts.score; det.append(dict(score=ts.score, f0=ts.f0, on=ts.on, blocks=ts.blocks))
    return tot, det


# ---- one candidate, all scorers ----------------------------------------------------------------------

def candidate(case, segs, lat0, lon0, cand, knobs):
    """cand: dict(lat, lon, icao1, icao2, clock) -> per-scorer best (score, clock, detail) and time."""
    el = Terrain().elevation(np.array([cand["lat"]]), np.array([cand["lon"]]))
    obs = lla_to_enu(np.array([cand["lat"]]), np.array([cand["lon"]]), el, lat0, lon0)[0]
    T0 = cand["clock"]
    centres = [0.5 * sum(e["window"]) for e in EVENTS]
    s2 = [seg_for(segs, icao, obs, c, T0) for icao, c in zip((cand["icao1"], cand["icao2"]), centres)]
    curves = [modelled_curve(s, obs, C) for s in s2]
    out = {}
    t = time.perf_counter(); out["1a"] = case.clocks(T0, lambda T: score_curve(case, case.win_a, curves, T)); out["t_1a"] = time.perf_counter() - t
    t = time.perf_counter(); out["1b"] = case.clocks(T0, lambda T: score_curve(case, case.win_b, curves, T)); out["t_1b"] = time.perf_counter() - t
    t = time.perf_counter(); out["2"] = case.clocks(T0, lambda T: score_ls(case, curves, T)); out["t_2"] = time.perf_counter() - t
    cache = {}
    t = time.perf_counter()
    out["3"] = case.clocks(T0, lambda T: score_warp(case, s2, obs, T, knobs["theta"], knobs["birth"], None, cache))
    out["t_3"] = time.perf_counter() - t
    out["3drift"] = case.clocks(T0, lambda T: score_warp(case, s2, obs, T, knobs["theta"], knobs["birth"], knobs["drift_hz"], cache))
    rates = []
    for s, (to, r), f in zip(s2, curves, case.fits):
        ok = np.isfinite(r)
        sel = ok & (to + T0 >= f.t_start) & (to + T0 <= f.t_end)
        if sel.sum() > 3:
            rates.append(float(np.max(np.abs(np.gradient(f.f0 * r[sel], to[sel])))))
    out["peak_sweep_hz_s"] = min(rates) if rates else None
    return out


# ---- the parts of a run ---------------------------------------------------------------------------------

_CASE = {}


def _init(band_limited):
    _CASE["case"] = Case(band_limited)
    _CASE["segs"] = {}


def _segs(traces_path, lat0, lon0):
    key = (traces_path, lat0, lon0)
    if key not in _CASE["segs"]:
        _CASE["segs"][key] = build_segments(load_traces(DATA / traces_path), lat0, lon0)
    return _CASE["segs"][key]


def _one(job):
    traces_path, lat0, lon0, cand, knobs = job
    res = candidate(_CASE["case"], _segs(traces_path, lat0, lon0), lat0, lon0, cand, knobs)
    print(cand.get("name"), {k: (round(v[0], 3) if isinstance(v, tuple) else v) for k, v in res.items() if not k.startswith("t_")},
          {k: round(v, 1) for k, v in res.items() if k.startswith("t_")}, flush=True)
    return dict(cand=cand, **res)


def pool(jobs, band_limited):
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(int(os.environ.get("JOBS", "4")), initializer=_init, initargs=(band_limited,)) as ex:
        return list(ex.map(_one, jobs))


def main_candidates():
    df = pd.read_csv(REPO / "docs/results/oyster_bay_search_best_per_pair.csv")
    lat0, lon0 = float(df.lat0[0]), float(df.lon0[0])
    ev1 = EventFit(**json.load(open(REPO / "docs/results/oyster_bay_ev1.json")))
    def clock(r):
        return float(ev1.t_cpa - r["t_heard1"] + r["shift"])
    true_row = df[(df.icao1 == PAIR[0]) & (df.icao2 == PAIR[1])].iloc[0]
    ref = dict(name="reference", lat=TRUTH[0], lon=TRUTH[1], icao1=PAIR[0], icao2=PAIR[1], clock=clock(true_row), truth=True)
    rows = [dict(name=f"wrong {int(r['rank'])}", lat=float(r.lat), lon=float(r.lon), icao1=r.icao1, icao2=r.icao2, clock=clock(r), rank=int(r["rank"]),
                 truth=False) for _, r in df.iterrows() if (r.icao1, r.icao2) != PAIR]
    return lat0, lon0, [ref] + greedy(rows, avoid=[TRUTH])


def box_candidates(name):
    res_path, traces = BOXES[name]
    d = json.load(open(DATA / res_path))
    lat0, lon0 = None, None
    rows = []
    for c in d["candidates"]:
        rows.append(dict(name=f"{name} {c['rank']}", lat=c["lat"], lon=c["lon"], icao1=c["flights"][0], icao2=c["flights"][1],
                         clock=float(c["clock"]["audio_minus_utc_s"] + c["clock"]["shift_s"]), rank=c["rank"], truth=False))
    bb = json.loads((REPO / "bench/cases.json").read_text()) if (REPO / "bench/cases.json").exists() else None
    for cs in (bb or {}).get("cases", []):
        if cs["id"] == f"oyster-bay-{name}":
            b = cs["search"]["bbox"]; lat0, lon0 = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2
    return traces, lat0, lon0, greedy(rows)


def summarise_rank(res):
    lines = []
    for sc in ("1a", "1b", "2", "3", "3drift"):
        s = np.array([r[sc][0] for r in res])
        ref = s[0]; wrong = s[1:]
        rank = 1 + int((wrong > ref).sum())
        mad = float(np.median(np.abs(s - np.median(s)))) or 1e-12
        z = (ref - wrong.max()) / mad
        lines.append(f"{sc:6s}: reference rank {rank} of {len(s)}, z {z:+.2f}, raw {ref - wrong.max():+.4f} (ref {ref:.4f}, best wrong {wrong.max():.4f} = {res[1 + int(np.argmax(wrong))]['cand']['name']})")
    return lines


def knobs_from_noise(lat0, lon0, ref, peak_rates, seed=0):
    """theta: the 95th percentile of the pooled evidence E on white noise warped with the reference's
    geometry (ev1's window and f0 range); birth = theta. drift: a quarter of the smallest peak sweep
    rate among the candidates, per 0.512 s block step."""
    case = _CASE["case"]
    el = Terrain().elevation(np.array([ref["lat"]]), np.array([ref["lon"]]))
    obs = lla_to_enu(np.array([ref["lat"]]), np.array([ref["lon"]]), el, lat0, lon0)[0]
    segs = _segs("derived/oyster_bay/traces_ny.npz", lat0, lon0)
    seg = seg_for(segs, ref["icao1"], obs, 0.5 * sum(EVENTS[0]["window"]), ref["clock"])
    saved = case.xf
    case.xf = W.lowpass(np.random.default_rng(seed).standard_normal(len(case.x)), SR, SR / (2 * MAX_RATE))
    S, fb = warp_event(case, seg, obs, ref["clock"], EVENTS[0])
    case.xf = saved
    f0s = np.arange(F0_RANGE[0] * case.fits[0].f0, F0_RANGE[1] * case.fits[0].f0, fb[1] - fb[0])
    E = W.pooled(S, fb, f0s, HARM)
    theta = float(np.percentile(E, 95))
    drift_hz = 0.25 * min(peak_rates) * HOP / SR
    return dict(theta=theta, birth=theta, drift_hz=drift_hz, min_peak_sweep_hz_s=min(peak_rates),
                drift_over_bin=drift_hz / (SR / BLOCK))


def peak_rates(lat0, lon0, cands, traces):
    case = _CASE["case"]; segs = _segs(traces, lat0, lon0); out = []
    for cand in cands:
        el = Terrain().elevation(np.array([cand["lat"]]), np.array([cand["lon"]]))
        obs = lla_to_enu(np.array([cand["lat"]]), np.array([cand["lon"]]), el, lat0, lon0)[0]
        for icao, e, f in zip((cand["icao1"], cand["icao2"]), EVENTS, case.fits):
            s = seg_for(segs, icao, obs, 0.5 * sum(e["window"]), cand["clock"])
            to, r = modelled_curve(s, obs, C)
            sel = np.isfinite(r) & (to + cand["clock"] >= e["window"][0]) & (to + cand["clock"] <= e["window"][1])
            if sel.sum() > 3:
                out.append(float(np.max(np.abs(np.gradient(f.f0 * r[sel], to[sel])))))
    return out


# ---- refinement (PM's option (a)): around each scorer's top candidate, its flight pair fixed -----------

REFINE_CLOCK = (1.0, 0.1)               # +-1 s at 0.1 s around the top candidate's best clock


def _point_score(job):
    """One grid point for one scorer: best over the refine clocks."""
    traces, lat0, lon0, lat, lon, icaos, T0, scorer, knobs = job
    case = _CASE["case"]; segs = _segs(traces, lat0, lon0)
    el = Terrain().elevation(np.array([lat]), np.array([lon]))
    obs = lla_to_enu(np.array([lat]), np.array([lon]), el, lat0, lon0)[0]
    centres = [0.5 * sum(e["window"]) for e in EVENTS]
    s2 = [seg_for(segs, icao, obs, c, T0) for icao, c in zip(icaos, centres)]
    curves = [modelled_curve(q, obs, C) for q in s2]
    fn = {"1a": lambda T: score_curve(case, case.win_a, curves, T), "1b": lambda T: score_curve(case, case.win_b, curves, T),
          "2": lambda T: score_ls(case, curves, T),
          "3": lambda T: score_warp(case, s2, obs, T, knobs["theta"], knobs["birth"], None, None)}[scorer]
    best = max((fn(T)[0], float(T)) for T in T0 + np.arange(-REFINE_CLOCK[0], REFINE_CLOCK[0] + 1e-9, REFINE_CLOCK[1]))
    return lat, lon, best[0], best[1]


def refine(rank, knobs, band, spacing_by_scorer):
    """Per scorer, the grid around its top-ranked candidate; returns the best point's error from the truth."""
    from concurrent.futures import ProcessPoolExecutor
    lat0, lon0 = rank["lat0"], rank["lon0"]
    out = {}
    for scorer, spacings in spacing_by_scorer.items():
        res = rank["rank"]
        top = max(res, key=lambda r: r[scorer][0])
        cand, T0 = top["cand"], top[scorer][1]
        for sp in spacings:
            n = int(round(1000.0 / sp))
            dl = sp / 111320.0; dlon = sp / (111320.0 * np.cos(np.radians(cand["lat"])))
            pts = [(cand["lat"] + i * dl, cand["lon"] + j * dlon) for i in range(-n, n + 1) for j in range(-n, n + 1)]
            jobs = [("derived/oyster_bay/traces_ny.npz", lat0, lon0, a, b, (cand["icao1"], cand["icao2"]), T0, scorer, knobs) for a, b in pts]
            t = time.perf_counter()
            with ProcessPoolExecutor(int(os.environ.get("JOBS", "4")), initializer=_init, initargs=(band,)) as ex:
                got = list(ex.map(_point_score, jobs, chunksize=4))
            best = max(got, key=lambda g: g[2])
            out[f"{scorer}@{sp:g}m"] = dict(top=cand["name"], lat=best[0], lon=best[1], score=best[2], clock=best[3], points=len(pts),
                                           error_m=float(haversine(best[0], best[1], *TRUTH)),
                                           top_error_m=float(haversine(cand["lat"], cand["lon"], *TRUTH)),
                                           wall_s=time.perf_counter() - t)
            print(scorer, sp, out[f"{scorer}@{sp:g}m"], flush=True)
    return out


if __name__ == "__main__":
    run = Path(sys.argv[1]); mode = sys.argv[2] if len(sys.argv) > 2 else "full"; what = sys.argv[3] if len(sys.argv) > 3 else "all"
    band = mode == "band"
    tag = "_band" if band else ""
    _init(band)
    lat0, lon0, cands = main_candidates()
    rates = peak_rates(lat0, lon0, cands, "derived/oyster_bay/traces_ny.npz")
    knobs = knobs_from_noise(lat0, lon0, cands[0], rates)
    print("knobs", knobs, flush=True)
    out = dict(knobs=knobs, candidates=cands)
    if what in ("rank", "all", "one"):
        jobs = [("derived/oyster_bay/traces_ny.npz", lat0, lon0, c, knobs) for c in (cands[:1] if what == "one" else cands)]
        t = time.perf_counter()
        out["rank"] = pool(jobs, band)
        out["rank_wall_s"] = time.perf_counter() - t
        if what != "one":
            lines = summarise_rank(out["rank"])
            print("\n".join(lines)); out["rank_summary"] = lines
    if what in ("wrongbox", "all"):
        out["wrongbox"] = {}
        for name in BOXES:
            traces, blat0, blon0, bc = box_candidates(name)
            out["wrongbox"][name] = pool([(traces, blat0, blon0, c, knobs) for c in bc], band)
    if what == "refine":
        rank = json.loads((run / f"warp_oyster{tag}_all.json").read_text())
        rank["lat0"], rank["lon0"] = lat0, lon0
        out["refine"] = refine(rank, knobs, band, {"1a": (200.0, 50.0), "1b": (200.0, 50.0), "2": (200.0, 50.0), "3": (200.0,)})
    (run / f"warp_oyster{tag}_{what}.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
