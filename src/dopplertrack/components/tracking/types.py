"""Tracker types: the peak tracker's parameters, the original STFT from samples, tracks, harmonic links and an event's tracks."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np
import scipy.signal as ss


@dataclass(frozen=True)
class TrackParams:
    """Every knob of the tracker, set on synthetic cases only. The defaults are Livermore run 1's,
    the best measured configuration (docs/experiments/2026-11-04-freqtrack.md). Run 2's retune,
    theta 9 dB with birth 20 and rise and hop flagging, measured worse on all three criteria."""
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


class SampleSTFT:
    """Complex STFT columns of `x` on the Spectrogram's frame grid: frame k covers samples
    [k*hop, k*hop + nperseg), centred at t0 + (nperseg/2 + k*hop)/sr seconds, Hann window as
    compute_spectrogram uses, zero-padded to nfft (default nperseg). Samples outside x read as zero."""

    def __init__(self, x: np.ndarray, sr: int, nperseg: int = 8192, hop_s: float = 0.25,
                 nfft: int | None = None, t0: float = 0.0):
        self.x = np.asarray(x, np.float64)
        self.sr, self.nperseg, self.t0 = sr, nperseg, t0
        self.nfft = nfft or nperseg
        self.hop = max(1, int(round(hop_s * sr)))
        self.window = ss.get_window("hann", nperseg)
        self.df = sr / self.nfft                      # the grid's bin
        self.wbin = self.nfft / nperseg               # one resolution bin, in grid bins

    def frame(self, t: float) -> int:
        return int(round(((t - self.t0) * self.sr - self.nperseg / 2) / self.hop))

    def segment(self, k: int) -> np.ndarray:
        a = k * self.hop
        seg = np.zeros(self.nperseg)
        lo, hi = max(a, 0), min(a + self.nperseg, len(self.x))
        if hi > lo:
            seg[lo - a:hi - a] = self.x[lo:hi]
        return seg

    def dft(self, k: int, window: bool = True) -> np.ndarray:
        s = self.segment(k)
        return np.fft.rfft(s * self.window if window else s, n=self.nfft)

    def dtft(self, k: int, bins: np.ndarray, window: bool = True) -> np.ndarray:
        """DTFT of frame k (Hann-windowed or not) at fractional positions in grid bins."""
        s = self.segment(k) * (self.window if window else 1.0)
        n = np.arange(self.nperseg)
        return np.exp(-2j * np.pi * np.outer(np.asarray(bins, float), n) / self.nfft) @ s


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


def with_params(p: TrackParams, **kw) -> TrackParams:
    return dataclasses.replace(p, **kw)
