"""Sliding-window detection: the coarse grid search (Kay 1993 §7.7) over overlapping windows, greedy non-maximum
suppression of its maxima (Nixon & Aguado 2012 p. 171), and a refining fit of the best (detect_events)."""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.core.propagation import speed_of_sound
from dopplertrack.runtime.parallel import process_pool, resolve_jobs
from dopplertrack.components.detection.event_fit import fit_event
from dopplertrack.components.detection.grid_search import grid_search
from dopplertrack.components.types import EventFit
from dopplertrack.components.whitening.local_median import local_whiten


@dataclass(frozen=True)
class ScanRequest:
    """One detector window, as sent to a worker process. Times are recording seconds."""
    window: Spectrogram         # whitened crop, padded 30 s on each side of the scored span
    window_start_s: float       # the scored span and the searched emission-CPA times
    window_end_s: float
    f_lo_hz: float
    f_hi_hz: float
    sound_speed_mps: float
    harmonics: int
    speed_grid_mps: np.ndarray
    slant_grid_m: np.ndarray
    f0_step_hz: float
    t0_step_s: float
    n_curve: int
    per_window: int             # local maxima kept from this window
    min_sep_s: float            # between those maxima's emission-CPA times


@dataclass(frozen=True)
class Candidate:
    """A coarse grid-search maximum, before refinement by fit_event."""
    score: float
    f0_hz: float
    speed_mps: float
    slant_m: float
    t_cpa_emit_s: float         # emission-time CPA in recording seconds, not the heard CPA time


def _scan_window(req: ScanRequest) -> list[Candidate]:
    """Up to req.per_window local maxima of the coarse search in one window, by greedy non-maximum suppression
    (min_sep_s seconds apart)."""
    if not np.any(req.window.S > 0):
        return []
    t0s, bs, bp = grid_search(req.window, req.window_start_s, req.window_end_s, req.f_lo_hz, req.f_hi_hz,
                              req.sound_speed_mps, req.harmonics, req.speed_grid_mps, req.slant_grid_m,
                              f0_step=req.f0_step_hz, t0_step=req.t0_step_s, n_curve=req.n_curve, per_t0=True)
    out: list[Candidate] = []
    order = np.argsort(-bs)
    for i in order:
        if all(abs(t0s[i] - o.t_cpa_emit_s) >= req.min_sep_s for o in out):
            out.append(Candidate(float(bs[i]), float(bp[i, 0]), float(bp[i, 1]), float(bp[i, 2]), float(t0s[i])))
        if len(out) >= req.per_window:
            break
    return out


# old name: merge_candidates
def non_maximum_suppression(cands: list[Candidate], min_sep_s: float, keep: int) -> list[Candidate]:
    """Greedy non-maximum suppression (Nixon & Aguado 2012 p. 171; the greedy sort-and-suppress form used
    by detectors): the best `keep` candidates whose emission-CPA times are at least min_sep_s apart.

    Candidates are ranked by (score, f0, speed, slant range, emission CPA time), all descending, so
    equal scores are broken by the higher fundamental, then speed, and so on; a kept candidate
    suppresses every lower-ranked one within min_sep_s of it."""
    ranked = sorted(cands, key=lambda cnd: (cnd.score, cnd.f0_hz, cnd.speed_mps, cnd.slant_m, cnd.t_cpa_emit_s), reverse=True)
    out: list[Candidate] = []
    for cnd in ranked:
        if all(abs(cnd.t_cpa_emit_s - k.t_cpa_emit_s) >= min_sep_s for k in out):
            out.append(cnd)
        if len(out) >= keep:
            break
    return out


def detect_events(sp: Spectrogram, f_lo: float, f_hi: float, c: float | None = None, harmonics: int = 1,
                  window_s: float = 240.0, step_s: float = 120.0, v_grid=None, d_grid=None,
                  f0_step: float = 2.0, t0_step: float = 2.0, n_curve: int = 80, top: int = 20,
                  per_window: int = 3, min_sep_s: float = 60.0, refine: bool = True,
                  workers: int | None = None, progress=None, min_score: float = 0.0) -> list[EventFit]:
    """Scan a whole recording for Doppler-shaped curves whose fundamental lies in [f_lo, f_hi].

    Each window gets the coarse grid search used by fit_event (windows run in `workers`
    processes, parallel.default_jobs() by default; the result doesn't depend on it) and contributes up to
    `per_window` local maxima in time. Those are thinned by non-maximum suppression (one event per
    min_sep_s), the best 2*top are refined with a local grid search plus
    Nelder-Mead, and the best `top` after refinement are returned, sorted by score
    (sweep-weighted ridge contrast, dB). Only finite scores strictly above
    min_score are returned, so the result may be empty. The default rejects a zero
    score; a useful false-alarm threshold still needs calibration. custom_rescore_zscore puts the result on
    S1's scale."""
    if top < 1:
        raise ValueError("top must be at least 1")
    if not np.isfinite(min_score):
        raise ValueError("min_score must be finite")
    c = speed_of_sound() if c is None else c
    v_grid = np.arange(40, 170, 13.0) if v_grid is None else v_grid
    d_grid = np.geomspace(400, 9000, 10) if d_grid is None else d_grid
    pad = 0.3 * (f_hi - f_lo)
    starts = np.arange(sp.t[0], max(sp.t[-1] - window_s, sp.t[0]) + 1e-9, step_s)
    workers = min(resolve_jobs(workers), len(starts))         # no idle workers for a short recording

    def jobs():
        for t in starts:
            t1 = min(t + window_s, sp.t[-1])
            win = local_whiten(sp.crop(t - 30, t1 + 30, max(f_lo - pad, sp.f[0]), min(f_hi * harmonics + pad, sp.f[-1])))
            yield ScanRequest(window=win, window_start_s=t, window_end_s=t1, f_lo_hz=f_lo, f_hi_hz=f_hi,
                              sound_speed_mps=c, harmonics=harmonics, speed_grid_mps=v_grid, slant_grid_m=d_grid,
                              f0_step_hz=f0_step, t0_step_s=t0_step, n_curve=n_curve, per_window=per_window,
                              min_sep_s=min_sep_s)

    cands: list[Candidate] = []
    with contextlib.ExitStack() as stack:
        if workers == 1:
            it: Iterator[list[Candidate]] = map(_scan_window, jobs())
        else:
            it = stack.enter_context(process_pool(workers)).map(_scan_window, jobs(), chunksize=2)
        for k, r in enumerate(it):
            cands.extend(r)
            if progress:
                progress(k + 1, len(starts))
    keep = non_maximum_suppression(cands, min_sep_s, 2 * top if refine else top)
    out = []
    for cnd in keep:
        f0, v, d, t0 = cnd.f0_hz, cnd.speed_mps, cnd.slant_m, cnd.t_cpa_emit_s
        if refine:
            ef = fit_event(sp, max(t0 - 120, sp.t[0]), min(t0 + 120, sp.t[-1]), f_lo, f_hi, c=c,
                           harmonics=harmonics, init=(f0, v, d, t0), v_bounds=(35.0, 200.0), d_bounds=(200.0, 15000.0))
        else:
            ef = EventFit(t_cpa=t0 + d / c, t_cpa_emit=t0, f0=f0, v=v, d=d, t_start=t0 - 120, t_end=t0 + 120,
                          score=cnd.score, f_pre=f0 * c / (c - v), f_post=f0 * c / (c + v))
        if np.isfinite(ef.score) and ef.score > min_score:
            out.append(ef)
    out.sort(key=lambda e: -e.score)
    final: list[EventFit] = []
    for e in out:          # refined fits can converge onto the same event; keep the best
        if all(abs(e.t_cpa - f.t_cpa) >= min_sep_s for f in final):
            final.append(e)
        if len(final) >= top:
            break
    return final
