"""The collective find (docs/proposals/2026-11-04-collective-find.md): every detected window against every flight's own
heard curve, summed non-coherently with a floor, at each grid point and shared clock (Axelrad et al. 2011).

For a grid point x and a clock b (audio = unix + b), each window w scores the best pass near it:
    z(x, b, w) = (s - median_w) / sigma_w,  s = sweep_scores of the pass's own heard curve at x in w,
with f0 free over the window's coarse tone and a residual shift; the point's score is
    Z(x, b) = sum over w of max(z, 0),  Z(x) = max over b.
A window no pass explains adds 0, so it can't veto a point. Windows keep only their bounds, a coarse tone and a coarse
heard CPA (the clock prior); the straight-pass v and d are not used.

The search is coarse to fine (the proposal's section 4, corrected): a COARSE_M grid scored as the maximum over its
cell's span (the residual shift and the f0 sweep widened to cover it), then the FINE_M grid inside the KEEP_TOP coarse
cells with the highest Z (a design step recorded before the rerun: a fraction of the maximum kept 141 cells on a
negative).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .audio import Spectrogram
from .doppler import speed_of_sound
from .score import EventWindow, modelled_curve
from .search import Grid, build_segments, cpa_table
from .tracks import EventFit, local_whiten

COARSE_M, FINE_M = 2000.0, 200.0
KEEP_TOP = 5                  # fine cells: the coarse cells with the highest Z
CLUSTER_S = 20.0              # the clock vote: a window's candidate clocks within +-CLUSTER_S of another window's
AGREE_S = 6.0                 # windows sum at a point only where their best clocks agree within +-AGREE_S
NULL_N = 1000
CHUNK = 400


@dataclass(frozen=True)
class Sweep:
    """The residual shift and the f0 sweep (fractions around the window's coarse tone), and the curve's samples."""
    shift_s: float
    shift_step: float
    f0_span: float
    f0_step: float
    n: int = 160

    def shifts(self):
        return np.arange(-self.shift_s, self.shift_s + 1e-9, self.shift_step)

    def f0_scales(self):
        return np.arange(1 - self.f0_span, 1 + self.f0_span + 1e-9, self.f0_step)


def fine_sweep(f0_span: float = 0.10) -> Sweep:
    return Sweep(8.0, 0.5, f0_span, 0.005)


def coarse_sweep(f0_span: float = 0.10) -> Sweep:
    """A COARSE_M cell's span: up to COARSE_M / sqrt(2) from its centre, about 4 s of travel, widens the shift, and the
    curve's shape changes with it, so the f0 sweep widens by 2 points; coarser steps and samples keep it affordable."""
    return Sweep(14.0, 2.0, f0_span + 0.02, 0.02, 60)


@dataclass
class Window:
    """What detection keeps of an event: its bounds, a coarse tone and a coarse heard CPA (the clock prior)."""
    t_start: float
    t_end: float
    f0: float
    t_cpa: float
    score: float

    @classmethod
    def from_detection(cls, e) -> "Window":
        return cls(float(e.t_start), float(e.t_end), float(e.f0), float(e.t_cpa), float(e.score))

    def view(self, sp: Spectrogram, pad_s: float = 40.0) -> EventWindow:
        """The whitened crop sweep_scores samples: the window plus pad_s, 0.6-1.6 times the coarse tone, which holds a
        pass's Doppler span up to about 150 m/s."""
        fit = EventFit(t_cpa=self.t_cpa, t_cpa_emit=float("nan"), f0=self.f0, v=float("nan"), d=float("nan"),
                       t_start=self.t_start, t_end=self.t_end, score=self.score, f_pre=float("nan"), f_post=float("nan"))
        crop = sp.crop(self.t_start - pad_s, self.t_end + pad_s, max(0.6 * self.f0, sp.f[0]), min(1.6 * self.f0, sp.f[-1]))
        return EventWindow(fit, local_whiten(crop), 1)


_STATE: dict = {}


def _set_state(state):
    _STATE.clear(); _STATE.update(state)


def _score_chunk(task):
    """For each (observer ENU, segment, heard time, window index, clock): the best score over the sweep and the
    clock it implies. The curve is computed once per (observer, segment) and reused for its windows."""
    obs, seg, t_heard, widx, offs = task
    views, segs, c, sw = _STATE["views"], _STATE["segs"], _STATE["c"], _STATE["sweep"]
    shifts, scales = sw.shifts(), sw.f0_scales()
    out_s, out_b, out_f = np.zeros(len(seg)), np.zeros(len(seg)), np.zeros(len(seg))
    cache = {}
    for i in range(len(seg)):
        key = (int(seg[i]), float(obs[i][0]), float(obs[i][1]))
        if key not in cache:
            cache = {key: modelled_curve(segs[int(seg[i])], obs[i], c)}
        to, r = cache[key]
        sc = views[int(widx[i])].sweep_scores(to + offs[i], r, shifts, scales, n=sw.n)
        k, j = np.unravel_index(int(np.argmax(sc)), sc.shape)
        out_s[i], out_b[i], out_f[i] = float(sc.max()), float(offs[i] + shifts[k]), float(scales[j])
    return out_s, out_b, out_f


def _run(tasks, state, workers):
    from .parallel import ordered_map, resolve_jobs
    jobs = min(resolve_jobs(workers), max(len(tasks), 1))
    try:
        parts = list(ordered_map(_score_chunk, tasks, jobs, _set_state, (state,)))
    finally:
        _STATE.clear()
    if not parts:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    return tuple(np.concatenate([p[i] for p in parts]) for i in range(3))


def _tasks(enu, gidx, seg, t_heard, widx, offs):
    order = np.lexsort((widx, seg, gidx))                  # a (point, segment)'s windows together, for the curve cache
    cols = [enu[gidx[order]], seg[order], t_heard[order], widx[order], offs[order]]
    return order, [tuple(c[a:a + CHUNK] for c in cols) for a in range(0, len(order), CHUNK)]


def window_nulls(views, wins, cpa, segs, enu, c, sweep, workers=None, n=NULL_N) -> list[dict]:
    """Each window's null: NULL_N CPA rows drawn uniformly (seeded by the window), each pass anchored on the window's
    coarse CPA and scored with the same sweep. Nearly all are wrong passes, so the median and 1.4826 MAD are the
    window's floor and spread, as the comparable score's event_null."""
    out = []
    for w, win in enumerate(wins):
        seed = int(hashlib.sha256(repr((round(win.t_start, 3), round(win.t_end, 3), round(win.f0, 4), round(win.t_cpa, 4),
                                        sweep)).encode()).hexdigest()[:16], 16)
        idx = np.sort(np.random.default_rng(seed).integers(0, len(cpa), n))
        g, s, th = (cpa[k].to_numpy()[idx] for k in ("gidx", "seg", "t_heard"))
        offs = win.t_cpa - th
        _, tasks = _tasks(enu, g, s, th, np.full(len(idx), w), offs)
        used = {int(k) for k in np.unique(s)}
        sc, _, _ = _run(tasks, {"views": views, "segs": {k: segs[k] for k in used}, "c": c, "sweep": sweep}, workers)
        med = float(np.median(sc)); sig = float(1.4826 * np.median(np.abs(sc - med)))
        out.append({"median": med, "sigma": max(sig, 1e-9), "n": n, "seed": seed,
                    "sample_sha256": hashlib.sha256(np.ascontiguousarray(idx).tobytes()).hexdigest(),
                    "f0_sweep": [1 - sweep.f0_span, 1 + sweep.f0_span], "anchor_s": win.t_cpa})
    return out


def candidates(cpa: pd.DataFrame, wins: list[Window]) -> pd.DataFrame:
    """The clock vote: every (row, window) whose clock b = t_cpa(w) - t_heard lies near another window's candidate at the
    same point. Clocks are binned at CLUSTER_S; a (row, window) is kept when its bin and the two beside it hold candidates
    of at least two windows (so any two within CLUSTER_S of each other are kept)."""
    g = cpa["gidx"].to_numpy(); th = cpa["t_heard"].to_numpy()
    parts = []
    for w, win in enumerate(wins):
        b = win.t_cpa - th
        parts.append(pd.DataFrame({"row": np.arange(len(cpa)), "gidx": g, "w": np.full(len(cpa), w, np.int16), "b": b,
                                   "bin": np.floor(b / CLUSTER_S).astype(np.int64)}))
    df = pd.concat(parts, ignore_index=True)
    u = df[["gidx", "bin", "w"]].drop_duplicates()
    near = pd.concat([u.assign(bin=u["bin"] + d) for d in (-1, 0, 1)], ignore_index=True).drop_duplicates()
    support = near.groupby(["gidx", "bin"]).size()
    keep = support[support >= 2].reset_index()[["gidx", "bin"]]
    return df.merge(keep, on=["gidx", "bin"], how="inner").reset_index(drop=True)


def collective_scores(cand: pd.DataFrame, cpa: pd.DataFrame, views, nulls, segs, enu, c, sweep, workers=None) -> pd.DataFrame:
    """z of each kept (row, window) at its best clock."""
    rows = cand["row"].to_numpy()
    g = cpa["gidx"].to_numpy()[rows]; s = cpa["seg"].to_numpy()[rows]; th = cpa["t_heard"].to_numpy()[rows]
    w = cand["w"].to_numpy(); offs = cand["b"].to_numpy()
    order, tasks = _tasks(enu, g, s, th, w, offs)
    used = {int(k) for k in np.unique(s)}
    sc, bb, ff = _run(tasks, {"views": views, "segs": {k: segs[k] for k in used}, "c": c, "sweep": sweep}, workers)
    out = pd.DataFrame({"gidx": g[order], "seg": s[order], "w": w[order], "t_heard": th[order], "s": sc, "b": bb, "f0_scale": ff})
    med = np.array([n["median"] for n in nulls]); sig = np.array([n["sigma"] for n in nulls])
    out["z"] = (out["s"] - med[out["w"]]) / sig[out["w"]]
    return out


def point_scores(scored: pd.DataFrame, n_windows: int) -> pd.DataFrame:
    """Z(x) = max over clocks of sum over windows of max(z, 0), the windows' best clocks agreeing within +-AGREE_S:
    clocks are binned at AGREE_S / 2, and a window's z at a bin is its best within two bins either side."""
    pos = scored[scored["z"] > 0].copy()
    if not len(pos):
        return pd.DataFrame(columns=["gidx", "Z", "b", "n_matched"])
    step = AGREE_S / 2
    pos["bin"] = np.floor(pos["b"] / step).astype(np.int64)
    best = pos.sort_values("z", ascending=False).drop_duplicates(["gidx", "w", "bin"])
    spread = pd.concat([best.assign(bin=best["bin"] + d) for d in range(-2, 3)], ignore_index=True)
    per = spread.sort_values("z", ascending=False).drop_duplicates(["gidx", "w", "bin"])
    tot = per.groupby(["gidx", "bin"]).agg(Z=("z", "sum"), n_matched=("w", "nunique")).reset_index()
    top = tot.sort_values("Z", ascending=False).drop_duplicates("gidx")
    top["b"] = (top["bin"] + 0.5) * step
    return top[["gidx", "Z", "b", "n_matched"]].reset_index(drop=True)


def matched_at(scored: pd.DataFrame, gidx: int, b: float, segs, wins) -> tuple[list, list]:
    """Each window's best pass at a point and its winning clock bin, by point_scores' own rule (the clock binned at
    AGREE_S / 2, a window's best within two bins either side), and the voters: the windows with any candidate there."""
    step = AGREE_S / 2
    b0 = int(np.floor(b / step))
    here = scored[(scored["gidx"] == gidx)]
    here = here[np.abs(np.floor(here["b"] / step).astype(np.int64) - b0) <= 2]
    out, voters = [], sorted({int(w) for w in here["w"]})
    for w, win in enumerate(wins):
        m = here[here["w"] == w]
        if not len(m):
            out.append(None); continue
        r = m.loc[m["z"].idxmax()]
        if r.z <= 0:
            out.append({"z": float(r.z), "score": float(r.s)}); continue
        out.append({"flight": segs[int(r.seg)].icao, "icao": segs[int(r.seg)].icao, "segment": int(r.seg),
                    "pass_cpa_utc": float(r.t_heard), "harmonic": 1, "f0_hz": float(win.f0 * r.f0_scale),
                    "shift_s": float(r.b - b), "clock": float(r.b), "score": float(r.s), "z": float(r.z)})
    return out, voters


def collective_find(sp: Spectrogram, wins: list[Window], traces, bbox, *, max_range_m=12000.0, c=None, elevation=None,
                    f0_span=0.10, workers=None, log=print, cpa_cache=None, null_n=NULL_N) -> dict:
    """The coarse-to-fine collective find over a box. Returns the coarse and fine maps' tops, the winner, its clock and
    each window's matched pass, and the stages' counts."""
    import time
    from .pipeline import cached_cpa_table
    c = speed_of_sound() if c is None else c
    counts, walls = {}, {}
    t = time.perf_counter()
    coarse = Grid.make(*bbox, COARSE_M, elevation)
    e0, e1 = coarse.enu[:, 0].min() - max_range_m - COARSE_M, coarse.enu[:, 0].max() + max_range_m + COARSE_M
    n0, n1 = coarse.enu[:, 1].min() - max_range_m - COARSE_M, coarse.enu[:, 1].max() + max_range_m + COARSE_M
    segs = build_segments(traces, coarse.lat0, coarse.lon0, clip_enu=(e0, e1, n0, n1))
    cpa_c = cached_cpa_table(coarse, segs, max_range_m, c, cpa_cache, workers=workers)
    views = [w.view(sp) for w in wins]
    walls["coarse_cpa"] = time.perf_counter() - t; counts["coarse_points"] = len(coarse); counts["coarse_cpa_rows"] = len(cpa_c)
    stages = {}
    for name, grid, cpa, sweep in (("coarse", coarse, cpa_c, coarse_sweep(f0_span)),):
        t = time.perf_counter()
        nulls = window_nulls(views, wins, cpa, segs, grid.enu, c, sweep, workers, null_n)
        cand = candidates(cpa, wins)
        counts[f"{name}_candidates"] = len(cand)
        scored = collective_scores(cand, cpa, views, nulls, segs, grid.enu, c, sweep, workers)
        pts = point_scores(scored, len(wins))
        walls[name] = time.perf_counter() - t
        stages[name] = (grid, cpa, nulls, scored, pts)
        log(f"{name}: {len(grid)} points, {len(cand)} candidates, best Z {pts.Z.max() if len(pts) else 0:.2f}")
    grid, cpa, nulls_c, scored_c, pts_c = stages["coarse"]
    if not len(pts_c):
        return dict(winner=None, counts=counts, walls=walls, reason="no point has a window above its null")
    zmax = float(pts_c.Z.max())
    keep = pts_c.sort_values("Z", ascending=False).head(KEEP_TOP)
    # the fine grid: FINE_M points inside each kept coarse cell
    k = int(round(COARSE_M / FINE_M))
    offs = (np.arange(k) - (k - 1) / 2) * FINE_M
    lat, lon = [], []
    for gi in keep.gidx.to_numpy():
        la0, lo0 = float(grid.lat[gi]), float(grid.lon[gi])
        dla = offs / 111320.0; dlo = offs / (111320.0 * np.cos(np.radians(la0)))
        LA, LO = np.meshgrid(la0 + dla, lo0 + dlo, indexing="ij")
        lat.append(LA.ravel()); lon.append(LO.ravel())
    lat, lon = np.concatenate(lat), np.concatenate(lon)
    elev = elevation(lat, lon) if elevation else np.zeros_like(lat)
    fine = Grid.points(lat, lon, np.where(np.isfinite(elev), elev, 0.0), lat0=coarse.lat0, lon0=coarse.lon0)
    t = time.perf_counter()
    cpa_f = cpa_table(fine, segs, max_range_m=max_range_m, c=c, workers=workers)
    sweep = fine_sweep(f0_span)
    nulls_f = window_nulls(views, wins, cpa_f, segs, fine.enu, c, sweep, workers, null_n)
    cand_f = candidates(cpa_f, wins)
    scored_f = collective_scores(cand_f, cpa_f, views, nulls_f, segs, fine.enu, c, sweep, workers)
    pts_f = point_scores(scored_f, len(wins))
    walls["fine"] = time.perf_counter() - t
    counts.update(fine_points=len(fine), kept_coarse_cells=len(keep), fine_cpa_rows=len(cpa_f), fine_candidates=len(cand_f))
    log(f"fine: {len(fine)} points in {len(keep)} cells, {len(cand_f)} candidates, best Z {pts_f.Z.max() if len(pts_f) else 0:.2f}")
    if not len(pts_f):
        return dict(winner=None, counts=counts, walls=walls, reason="no fine point has a window above its null")
    pts_f = pts_f.sort_values("Z", ascending=False).reset_index(drop=True)
    w0 = pts_f.iloc[0]
    matched, voters = matched_at(scored_f, int(w0.gidx), float(w0.b), segs, wins)
    winner = dict(lat=float(fine.lat[int(w0.gidx)]), lon=float(fine.lon[int(w0.gidx)]), Z=float(w0.Z), clock_audio_minus_unix=float(w0.b),
                  n_matched=int(w0.n_matched), windows=matched, voters=voters)
    modes, seen = [], []
    from .geo import haversine_m
    for r in pts_f.itertuples():
        la, lo = float(fine.lat[int(r.gidx)]), float(fine.lon[int(r.gidx)])
        if all(haversine_m(la, lo, a, b) > 2000.0 for a, b in seen):
            seen.append((la, lo)); modes.append(dict(lat=la, lon=lo, Z=float(r.Z), clock_audio_minus_unix=float(r.b), n_matched=int(r.n_matched)))
        if len(modes) == 5:
            break
    coarse_top = [dict(lat=float(grid.lat[int(r.gidx)]), lon=float(grid.lon[int(r.gidx)]), Z=float(r.Z)) for r in
                  pts_c.sort_values("Z", ascending=False).head(5).itertuples()]
    return dict(winner=winner, modes=modes, coarse_top=coarse_top, coarse_max=zmax, counts=counts, walls=walls,
                nulls={"coarse": nulls_c, "fine": nulls_f}, sweeps={"coarse": coarse_sweep(f0_span).__dict__, "fine": sweep.__dict__},
                windows=[w.__dict__ for w in wins])
