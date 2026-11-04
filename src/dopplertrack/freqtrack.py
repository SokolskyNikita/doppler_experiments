"""Frequency tracks (PLAN Phase 2 item 3): each tone as a line with an explicit start, end and gaps.

A track is found on the whitened image and measured on the original STFT:
- **Finding.** A Viterbi over the strongest spectral peaks of each frame, plus an "off" state with
  birth and death penalties (hermes's form). A cell's reward is its whitened level less `theta_db`,
  so steady noise scores below zero and a path ends where the tone does. Frames the spectrogram
  marks invalid are crossed without a measurement, for at most `max_bridge_s`. Tracks are taken one
  at a time, each path's cells removed before the next is sought.
- **Measuring.** Each point's frequency is refined below the bin width on the original STFT, since
  whitening shifts a peak that sits near the floor it partly subtracted. The estimators are quadratic
  interpolation on log magnitude, Candan's three-sample estimator in its Hann form, and Quinn's FTI(2)
  on the unwindowed DFT.
- **Segment rules.** Cuts at a weak run, a rise and a hop, a link across a short gap, and re-pairing
  at a crossing. Each is a separate function applied after the Viterbi, so each can be tested and
  switched alone.
- **Harmonic links.** Two overlapping tracks whose frequency ratio holds near p/q are linked; a
  group's orders are the smallest integers consistent with its links, whose gcd is 1 (hermes).

The original STFT comes from the samples (SampleSTFT), because a Spectrogram holds whitened dB only.
A later version may carry the un-whitened dB in the Spectrogram instead."""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import scipy.signal as ss

from .audio import Spectrogram


@dataclass(frozen=True)
class TrackParams:
    """Every knob of the tracker. Defaults were set on synthetic cases only
    (tools/experiments/2026-11-04/freqtrack_knobs.py), before any real recording was tracked."""
    peaks_per_frame: int = 8          # Viterbi states per frame, besides "off"
    theta_db: float = 9.5             # whitened level below which a cell costs: 1 false track per hour per 100 Hz on noise
    birth: float = 6.0                # cost of starting a track (dB)
    death: float = 6.0                # cost of ending one (dB)
    jump_cost: float = 0.1            # dB per bin of frequency change between frames
    max_rel_slope: float = 0.25       # physical cap on |df/dt| / f, per second (PLAN 6.1, v <= 110 m/s, R >= 150 m)
    max_bridge_s: float = 5.0         # longest run of invalid frames a track may cross
    exclusion_bins: int = 2           # cells removed either side of a found path
    max_tracks: int = 12
    min_track_s: float = 1.0
    weak_db: float = 3.0              # cut_weak: a run below this whitened level ...
    weak_run_s: float = 3.0           # ... lasting longer than this
    rise_bins: float = 4.0            # cut_rise: a rise of more than this many bins ...
    rise_window_s: float = 3.0        # ... within this long
    hop_factor: float = 4.0           # cut_hop: a step this many times the local slope ...
    hop_window_s: float = 2.0         # ... measured over this long either side
    link_gap_s: float = 5.0           # link_gaps: join across a gap this long at most ...
    link_tol_bins: float = 3.0        # ... when the next track starts this close to the extrapolation
    crossing_bins: float = 1.0        # resolve_crossings: tracks this close are crossing
    harmonic_tol: float = 0.01        # a link's median ratio within this of p/q
    harmonic_iqr: float = 0.005       # and its relative IQR below this
    max_order: int = 6
    estimator: str = "quinn2"         # lowest RMS on synthetic chirps of the three


# ---- the original STFT -------------------------------------------------------------------

class SampleSTFT:
    """Complex STFT columns of `x` on the Spectrogram's frame grid: frame k covers samples
    [k*hop, k*hop + nperseg), centred at (nperseg/2 + k*hop)/sr seconds, Hann window as
    compute_spectrogram uses. Samples outside x read as zero."""

    def __init__(self, x: np.ndarray, sr: int, nperseg: int = 8192, hop_s: float = 0.25):
        self.x = np.asarray(x, np.float64)
        self.sr, self.nperseg = sr, nperseg
        self.hop = max(1, int(round(hop_s * sr)))
        self.window = ss.get_window("hann", nperseg)
        self.df = sr / nperseg

    def frame(self, t: float) -> int:
        return int(round((t * self.sr - self.nperseg / 2) / self.hop))

    def segment(self, k: int) -> np.ndarray:
        a = k * self.hop
        seg = np.zeros(self.nperseg)
        lo, hi = max(a, 0), min(a + self.nperseg, len(self.x))
        if hi > lo:
            seg[lo - a:hi - a] = self.x[lo:hi]
        return seg

    def dft(self, k: int, window: bool = True) -> np.ndarray:
        s = self.segment(k)
        return np.fft.rfft(s * self.window if window else s)

    def dtft(self, k: int, bins: np.ndarray) -> np.ndarray:
        """Hann-windowed DTFT of frame k at fractional bin positions."""
        s = self.segment(k) * self.window
        n = np.arange(self.nperseg)
        return np.exp(-2j * np.pi * np.outer(np.asarray(bins, float), n) / self.nperseg) @ s


# ---- sub-bin estimators ------------------------------------------------------------------

def quadratic_delta(a: complex, b: complex, c: complex) -> float:
    """Parabola through log magnitudes of bins k-1, k, k+1."""
    la, lb, lc = (math.log(max(abs(z), 1e-300)) for z in (a, b, c))
    den = la - 2 * lb + lc
    return 0.0 if den == 0 else 0.5 * (la - lc) / den


def candan_hann_delta(a: complex, b: complex, c: complex) -> float:
    """Candan's three-sample estimator for a Hann window. For a Hann-windowed tone the three
    coefficients are proportional to 1/((d - m)(1 - (d - m)^2)), m = -1, 0, 1, which makes
    Re[(X-1 - X+1)/(2 X0 - X-1 - X+1)] = d/2 exactly as N grows."""
    den = 2 * b - a - c
    return 0.0 if den == 0 else float(2 * ((a - c) / den).real)


def _kappa(x: float) -> float:
    r = math.sqrt(2 / 3)
    return 0.25 * math.log(3 * x ** 4 + 6 * x ** 2 + 1) - math.sqrt(6) / 24 * math.log((x * x + 1 - r) / (x * x + 1 + r))


def quinn2_delta(a: complex, b: complex, c: complex) -> float:
    """Quinn's FTI(2) (Quinn 1995 IV.B) on the unwindowed DFT coefficients at k-1, k, k+1."""
    if b == 0:
        return 0.0
    a1, a2 = (a / b).real, (c / b).real
    d1, d2 = a1 / (1 - a1), -a2 / (1 - a2)
    return (d1 + d2) / 2 - _kappa(d1) + _kappa(d2)


def refine(stft: SampleSTFT, k: int, b: int, estimator: str = "candan", iterations: int = 3) -> tuple[float, float]:
    """(frequency Hz, amplitude dB) of the peak near bin b in frame k of the original STFT: the
    largest Hann bin within one of b, then the estimator. Candan is iterated on the DTFT
    around its own estimate, as dopplerprint does."""
    X = stft.dft(k)
    lo = max(b - 1, 1)
    j = lo + int(np.argmax(np.abs(X[lo:b + 2])))
    j = min(max(j, 1), len(X) - 2)
    if estimator == "quadratic":
        d = quadratic_delta(X[j - 1], X[j], X[j + 1])
    elif estimator == "quinn2":
        Y = stft.dft(k, window=False)
        d = quinn2_delta(Y[j - 1], Y[j], Y[j + 1])
    elif estimator == "candan":
        d = candan_hann_delta(X[j - 1], X[j], X[j + 1])
        for _ in range(iterations - 1):
            Z = stft.dtft(k, j + d + np.array([-1.0, 0.0, 1.0]))
            d += candan_hann_delta(*Z)
    else:
        raise ValueError(f"unknown estimator {estimator!r}")
    d = float(np.clip(d, -1.0, 1.0))
    w = abs(np.sinc(d) / (1 - d * d)) if abs(d) < 0.999 else 0.5
    amp = 20 * math.log10(max(abs(X[j]), 1e-300) / (w * stft.window.sum() / 2))
    return (j + d) * stft.df, amp


# ---- tracks ------------------------------------------------------------------------------

@dataclass
class Track:
    """One line on contiguous frames t[0]..t[-1]. f and amp are NaN where nothing was measured
    (measured False): a gap, from an invalid frame or a link."""
    t: np.ndarray
    f: np.ndarray
    amp: np.ndarray
    level: np.ndarray        # whitened level at the path's cell, dB
    measured: np.ndarray
    bins: np.ndarray         # the path's bin on the whitened image (-1 where unmeasured)
    flags: dict = field(default_factory=dict)

    @property
    def start(self) -> float:
        return float(self.t[0])

    @property
    def end(self) -> float:
        return float(self.t[-1])

    def gaps(self) -> list[tuple[float, float]]:
        out, i, m = [], 0, self.measured
        while i < len(m):
            if not m[i]:
                j = i
                while j + 1 < len(m) and not m[j + 1]:
                    j += 1
                out.append((float(self.t[i]), float(self.t[j])))
                i = j
            i += 1
        return out

    def piece(self, i: int, j: int) -> "Track":
        """Frames i..j-1; a flag holding a list of times keeps only those inside the piece."""
        lo, hi = self.t[i], self.t[j - 1]
        flags = {k: ([x for x in v if lo <= x <= hi] if isinstance(v, list) else v) for k, v in self.flags.items()}
        return Track(self.t[i:j], self.f[i:j], self.amp[i:j], self.level[i:j], self.measured[i:j], self.bins[i:j],
                     {k: v for k, v in flags.items() if v != []})


@dataclass
class HarmonicLink:
    i: int
    j: int
    p: int              # f_j / f_i ~ p / q
    q: int
    ratio_median: float
    ratio_iqr: float
    overlap_s: float


@dataclass
class EventTracks:
    tracks: list[Track]
    links: list[HarmonicLink]
    groups: list[dict]        # {"tracks": [i...], "orders": {i: order}, "strength": float}

    def event_track(self) -> dict | None:
        """The strongest harmonic group: the event's track."""
        return max(self.groups, key=lambda g: g["strength"]) if self.groups else None


# ---- the Viterbi -------------------------------------------------------------------------

def _peaks(S: np.ndarray, band: np.ndarray, M: int) -> tuple[np.ndarray, np.ndarray]:
    """Per frame, the M highest local maxima along frequency inside `band`: bins (T, M), -1 for
    none, and their levels (T, M), -inf for none."""
    F, T = S.shape
    loc = np.zeros_like(S, bool)
    loc[1:-1] = (S[1:-1] > S[:-2]) & (S[1:-1] >= S[2:])
    loc &= band[:, None]
    lev = np.where(loc, S, -np.inf)
    idx = np.argsort(-lev, axis=0)[:M].T                                   # (T, M)
    val = np.take_along_axis(lev.T, idx, axis=1)
    idx = np.where(np.isfinite(val), idx, -1)
    return idx, val


def viterbi_segments(bins: np.ndarray, levels: np.ndarray, valid: np.ndarray, t: np.ndarray, f: np.ndarray,
                     p: TrackParams) -> list[tuple[int, int, np.ndarray]]:
    """Best path through peaks and "off": the runs of frames it spends on a peak, as
    (first frame, last frame, bin per frame or -1 across invalid frames)."""
    T, M = bins.shape
    df = float(f[1] - f[0])
    vidx = np.nonzero(valid)[0]
    if len(vidx) == 0:
        return []
    reward = levels - p.theta_db                                           # -inf where no peak
    U = np.full(M + 1, -np.inf); U[M] = 0.0                                # state M is "off"
    back = np.zeros((len(vidx), M + 1), np.int64)
    prev_bins = None; prev_t = None
    for n, k in enumerate(vidx):
        b = bins[k]
        new = np.full(M + 1, -np.inf)
        from_off = U[M] - p.birth
        if prev_bins is None:
            cand = np.full((M, 1), from_off); src = np.full((M, 1), M)
        else:
            dt = t[k] - prev_t
            jump = np.abs(b[:, None] - prev_bins[None, :]).astype(float)   # (M_now, M_prev)
            cap = np.maximum(2.0, p.max_rel_slope * f[np.maximum(b, 0)] * dt / df + 1)[:, None]
            ok = (b[:, None] >= 0) & (prev_bins[None, :] >= 0) & (jump <= cap) & (dt <= p.max_bridge_s + 1e-9)
            stay = np.where(ok, U[None, :M] - p.jump_cost * jump, -np.inf)
            cand = np.concatenate([stay, np.full((M, 1), from_off)], axis=1)
            src = np.broadcast_to(np.r_[np.arange(M), M], cand.shape)
        best = np.argmax(cand, axis=1)
        new[:M] = cand[np.arange(M), best] + reward[k]
        back[n, :M] = src[np.arange(M), best]
        to_off = U[:M] - p.death
        j = int(np.argmax(to_off))
        if to_off[j] > U[M]:
            new[M] = to_off[j]; back[n, M] = j
        else:
            new[M] = U[M]; back[n, M] = M
        U = np.where(np.isfinite(new), new, -np.inf)
        prev_bins, prev_t = b, t[k]
    end = U[:M] - p.death
    s = int(np.argmax(end)) if end.max() > U[M] else M
    states = np.empty(len(vidx), np.int64)
    for n in range(len(vidx) - 1, -1, -1):
        states[n] = s
        s = back[n, s]
    out, n = [], 0
    while n < len(vidx):
        if states[n] == M:
            n += 1
            continue
        m = n
        while m + 1 < len(vidx) and states[m + 1] != M:
            m += 1
        k0, k1 = vidx[n], vidx[m]
        path = np.full(k1 - k0 + 1, -1, np.int64)
        for q in range(n, m + 1):
            path[vidx[q] - k0] = bins[vidx[q], states[q]]
        out.append((int(k0), int(k1), path))
        n = m + 1
    return out


def find_tracks(win: Spectrogram, stft: SampleSTFT, f_lo: float, f_hi: float,
                p: TrackParams = TrackParams()) -> list[Track]:
    """Tracks in a whitened, unclipped window (local_whiten(..., floor=-inf)), measured on stft,
    before any segment rule."""
    S = np.where(win.valid[None, :], win.S, -np.inf)
    band = (win.f >= f_lo) & (win.f <= f_hi)
    bins, levels = _peaks(S, band, p.peaks_per_frame)
    tracks = []
    for _ in range(p.max_tracks):
        segs = viterbi_segments(bins, levels, win.valid, win.t, win.f, p)
        segs = [s for s in segs if win.t[s[1]] - win.t[s[0]] >= p.min_track_s]
        if not segs:
            break
        for k0, k1, path in segs:
            tracks.append(_measure(win, stft, k0, path, p))
            for i, b in enumerate(path):
                if b >= 0:
                    row = bins[k0 + i]
                    kill = (row >= 0) & (np.abs(row - b) <= p.exclusion_bins)
                    bins[k0 + i, kill] = -1; levels[k0 + i, kill] = -np.inf
    tracks.sort(key=lambda tr: tr.start)
    return tracks


def _measure(win: Spectrogram, stft: SampleSTFT, k0: int, path: np.ndarray, p: TrackParams) -> Track:
    n = len(path)
    t = win.t[k0:k0 + n]
    f = np.full(n, np.nan); amp = np.full(n, np.nan); level = np.full(n, np.nan)
    f_offset = int(round(win.f[0] / stft.df))                     # win bins -> full-STFT bins
    for i, b in enumerate(path):
        if b < 0:
            continue
        level[i] = win.S[b, k0 + i]
        f[i], amp[i] = refine(stft, stft.frame(float(t[i])), int(b) + f_offset, p.estimator)
    return Track(t.copy(), f, amp, level, path >= 0, path.copy())


# ---- segment rules -----------------------------------------------------------------------

def _split(tr: Track, cut: np.ndarray, p: TrackParams) -> list[Track]:
    """Pieces of tr between the cut points (indices dropped), keeping those of min_track_s."""
    out, i = [], 0
    for j in list(np.nonzero(cut)[0]) + [len(tr.t)]:
        if j > i and tr.t[j - 1] - tr.t[i] >= p.min_track_s and tr.measured[i:j].any():
            pc = tr.piece(i, j)
            m = np.nonzero(pc.measured)[0]
            out.append(pc.piece(int(m[0]), int(m[-1]) + 1))
        i = j + 1
    return out


def cut_weak(tr: Track, p: TrackParams) -> list[Track]:
    """Drop runs whose whitened level stays below weak_db for longer than weak_run_s."""
    weak = ~(np.nan_to_num(tr.level, nan=-np.inf) >= p.weak_db)
    cut = np.zeros(len(tr.t), bool)
    i = 0
    while i < len(weak):
        if weak[i]:
            j = i
            while j + 1 < len(weak) and weak[j + 1]:
                j += 1
            if tr.t[j] - tr.t[i] > p.weak_run_s:
                cut[i:j + 1] = True
            i = j
        i += 1
    return _split(tr, cut, p)


def rise_points(tr: Track, p: TrackParams, df: float) -> np.ndarray:
    """Indices where the track has risen by more than rise_bins within rise_window_s: a straight
    pass only falls."""
    m = np.nonzero(tr.measured)[0]
    out = []
    lo = 0
    for hi in range(len(m)):
        while tr.t[m[hi]] - tr.t[m[lo]] > p.rise_window_s:
            lo += 1
        seg = tr.f[m[lo:hi + 1]]
        if len(seg) > 1 and tr.f[m[hi]] - np.min(seg) > p.rise_bins * df:
            out.append(int(m[hi]))
    return np.array(out, int)


def cut_rise(tr: Track, p: TrackParams, df: float, flag_only: bool = False) -> list[Track]:
    """Cut at the first point of each rise (rise_points); with flag_only, keep the track whole and
    record the rise in tr.flags["rise"] instead."""
    r = rise_points(tr, p, df)
    if flag_only or len(r) == 0:
        if len(r):
            tr.flags["rise"] = tr.t[r].tolist()
        return [tr]
    cut = np.zeros(len(tr.t), bool)
    starts = r[np.r_[True, np.diff(r) > 1]]
    cut[starts] = True
    return _split(tr, cut, p)


def cut_hop(tr: Track, p: TrackParams, df: float) -> list[Track]:
    """Cut at a step more than hop_factor times the track's own slope over the neighbouring
    hop_window_s (and at least two bins): a jump onto another line."""
    m = np.nonzero(tr.measured)[0]
    if len(m) < 3:
        return [tr]
    tm, fm = tr.t[m], tr.f[m]
    step = np.abs(np.diff(fm)) / np.diff(tm)
    cut = np.zeros(len(tr.t), bool)
    for i in range(len(step)):
        near = (np.abs(tm[1:] - tm[i + 1]) <= p.hop_window_s) & (np.arange(len(step)) != i)
        local = np.median(step[near]) if near.any() else 0.0
        if abs(fm[i + 1] - fm[i]) > max(2 * df, p.hop_factor * local * (tm[i + 1] - tm[i])):
            cut[m[i + 1]] = True
    if not cut.any():
        return [tr]
    pieces, i = [], 0
    for j in [int(k) for k in np.nonzero(cut)[0]] + [len(tr.t)]:   # keep the cut point as the next piece's start
        if j > i and tr.t[j - 1] - tr.t[i] >= p.min_track_s and tr.measured[i:j].any():
            pieces.append(tr.piece(i, j))
        i = j
    return pieces


def _extrapolate(tr: Track, t: float, span: float, from_end: bool) -> float:
    m = tr.measured & np.isfinite(tr.f)
    sel = m & ((tr.t >= tr.end - span) if from_end else (tr.t <= tr.start + span))
    tt, ff = tr.t[sel], tr.f[sel]
    if len(tt) < 2:
        return float(ff[-1] if from_end else ff[0]) if len(ff) else np.nan
    a, b = np.polyfit(tt - tt.mean(), ff, 1)
    return float(a * (t - tt.mean()) + b)


def link_gaps(tracks: list[Track], p: TrackParams, df: float, dt: float) -> list[Track]:
    """Join a track to the next one that starts within link_gap_s of its end and within
    link_tol_bins of its linear extrapolation (fitted over its last 2 s); the result has an
    explicit gap."""
    tracks = sorted(tracks, key=lambda tr: tr.start)
    used = [False] * len(tracks)
    out = []
    for i, a in enumerate(tracks):
        if used[i]:
            continue
        cur = a
        while True:
            best = None
            for j, b in enumerate(tracks):
                if used[j] or b is a or b.start <= cur.end or b.start - cur.end > p.link_gap_s:
                    continue
                err = abs(_extrapolate(cur, b.start, 2.0, True) - b.f[b.measured][0])
                if err <= p.link_tol_bins * df and (best is None or err < best[0]):
                    best = (err, j)
            if best is None:
                break
            j = best[1]; b = tracks[j]; used[j] = True
            n_gap = max(int(round((b.start - cur.end) / dt)) - 1, 0)
            gap_t = cur.end + dt * np.arange(1, n_gap + 1)
            nan = np.full(n_gap, np.nan)
            cur = Track(np.r_[cur.t, gap_t, b.t], np.r_[cur.f, nan, b.f], np.r_[cur.amp, nan, b.amp],
                        np.r_[cur.level, nan, b.level], np.r_[cur.measured, np.zeros(n_gap, bool), b.measured],
                        np.r_[cur.bins, np.full(n_gap, -1), b.bins], {**cur.flags, "linked": cur.flags.get("linked", 0) + 1})
        used[i] = True
        out.append(cur)
    return out


def resolve_crossings(tracks: list[Track], p: TrackParams, df: float, span: float = 2.0) -> list[Track]:
    """Where two tracks overlapping in time come within crossing_bins, re-pair their four ends
    by slope continuity if swapping the tails fits better than keeping them."""
    tracks = list(tracks)
    changed = True
    while changed:
        changed = False
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                a, b = tracks[i], tracks[j]
                common = np.intersect1d(a.t[a.measured], b.t[b.measured])
                if len(common) == 0:
                    continue
                fa = np.interp(common, a.t[a.measured], a.f[a.measured])
                fb = np.interp(common, b.t[b.measured], b.f[b.measured])
                close = np.abs(fa - fb) <= p.crossing_bins * df
                if not close.any() or close.all():
                    continue
                tc = float(common[np.argmin(np.abs(fa - fb))])
                if tc - max(a.start, b.start) < span or min(a.end, b.end) - tc < span:
                    continue
                def slope(tr, lo, hi):
                    sel = tr.measured & (tr.t >= lo) & (tr.t <= hi)
                    return np.polyfit(tr.t[sel], tr.f[sel], 1)[0] if sel.sum() >= 2 else np.nan
                sa0, sa1 = slope(a, tc - span, tc - span / 4), slope(a, tc + span / 4, tc + span)
                sb0, sb1 = slope(b, tc - span, tc - span / 4), slope(b, tc + span / 4, tc + span)
                keep = abs(sa0 - sa1) + abs(sb0 - sb1)
                swap = abs(sa0 - sb1) + abs(sb0 - sa1)
                if np.isfinite(swap) and swap < keep:
                    ka, kb = a.t <= tc, b.t <= tc
                    na = _concat(a, ka, b, ~kb); nb = _concat(b, kb, a, ~ka)
                    na.flags["crossing"] = nb.flags["crossing"] = tc
                    tracks[i], tracks[j] = na, nb
                    changed = True
    return tracks


def _concat(a: Track, ma: np.ndarray, b: Track, mb: np.ndarray) -> Track:
    return Track(np.r_[a.t[ma], b.t[mb]], np.r_[a.f[ma], b.f[mb]], np.r_[a.amp[ma], b.amp[mb]],
                 np.r_[a.level[ma], b.level[mb]], np.r_[a.measured[ma], b.measured[mb]],
                 np.r_[a.bins[ma], b.bins[mb]], dict(a.flags))


# ---- harmonics ---------------------------------------------------------------------------

def harmonic_links(tracks: list[Track], p: TrackParams, min_overlap_s: float = 2.0) -> list[HarmonicLink]:
    ratios = sorted({Fraction(a, b) for a in range(1, p.max_order + 1) for b in range(1, a + 1)})
    out = []
    for i, a in enumerate(tracks):
        for j, b in enumerate(tracks):
            if j <= i:
                continue
            common, ia, ib = np.intersect1d(a.t[a.measured], b.t[b.measured], return_indices=True)
            if len(common) < 2 or common[-1] - common[0] < min_overlap_s:
                continue
            fa, fb = a.f[a.measured][ia], b.f[b.measured][ib]
            lo, hi, swap = (fa, fb, False) if np.median(fb) >= np.median(fa) else (fb, fa, True)
            r = hi / lo
            med = float(np.median(r)); iqr = float(np.subtract(*np.percentile(r, [75, 25]))) / med
            fr = min(ratios, key=lambda x: abs(med / float(x) - 1))
            if fr == 1 or abs(med / float(fr) - 1) > p.harmonic_tol or iqr > p.harmonic_iqr:
                continue
            pp, qq = fr.numerator, fr.denominator
            if swap:
                pp, qq = qq, pp
            out.append(HarmonicLink(i, j, pp, qq, med if not swap else 1 / med, iqr, float(common[-1] - common[0])))
    return out


def harmonic_groups(tracks: list[Track], links: list[HarmonicLink]) -> list[dict]:
    """Connected tracks with their orders: f_j/f_i = p/q fixes order_j/order_i; orders are scaled
    to the smallest integers, so lines at 2, 4 and 6 read 1, 2 and 3. A link inconsistent with its
    group's orders is dropped."""
    adj: dict[int, list[tuple[int, Fraction]]] = {i: [] for i in range(len(tracks))}
    for lk in links:
        adj[lk.i].append((lk.j, Fraction(lk.p, lk.q)))
        adj[lk.j].append((lk.i, Fraction(lk.q, lk.p)))
    seen, groups = set(), []
    for root in range(len(tracks)):
        if root in seen:
            continue
        order = {root: Fraction(1)}
        stack = [root]
        while stack:
            i = stack.pop()
            for j, r in adj[i]:
                if j not in order:
                    order[j] = order[i] * r
                    stack.append(j)
        seen |= set(order)
        den = math.lcm(*(o.denominator for o in order.values()))
        ints = {i: int(o * den) for i, o in order.items()}
        g = math.gcd(*ints.values())
        ints = {i: o // g for i, o in ints.items()}
        strength = float(sum(np.nansum(np.maximum(tracks[i].level, 0)) for i in ints))
        groups.append({"tracks": sorted(ints), "orders": ints, "strength": strength})
    return groups


# ---- the whole event ---------------------------------------------------------------------

def track_window(sp: Spectrogram, stft: SampleSTFT, t_start: float, t_end: float, f_lo: float, f_hi: float,
                 p: TrackParams = TrackParams(), rules: tuple[str, ...] = ("weak", "rise", "hop", "link", "crossing"),
                 rise_flag_only: bool = False) -> EventTracks:
    """Tracks between t_start and t_end with fundamentals or harmonics in [f_lo, f_hi], after the
    segment rules named in `rules`, with harmonic links."""
    from .tracks import local_whiten
    win = local_whiten(sp.crop(t_start, t_end), floor=-np.inf)
    df, dt = win.df, win.dt
    tracks = find_tracks(win, stft, f_lo, f_hi, p)
    if "weak" in rules:
        tracks = [q for tr in tracks for q in cut_weak(tr, p)]
    if "rise" in rules:
        tracks = [q for tr in tracks for q in cut_rise(tr, p, df, flag_only=rise_flag_only)]
    if "hop" in rules:
        tracks = [q for tr in tracks for q in cut_hop(tr, p, df)]
    if "link" in rules:
        tracks = link_gaps(tracks, p, df, dt)
    if "crossing" in rules:
        tracks = resolve_crossings(tracks, p, df)
    links = harmonic_links(tracks, p)
    return EventTracks(tracks, links, harmonic_groups(tracks, links))


def with_params(p: TrackParams, **kw) -> TrackParams:
    return dataclasses.replace(p, **kw)
