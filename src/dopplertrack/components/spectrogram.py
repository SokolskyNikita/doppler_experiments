"""The Spectrogram container: a log spectrogram (dB of the squared STFT magnitude, Flandrin 2018 eq. 6.2) less a median
background, on a regular grid of frames along a recording's timeline, with its mask."""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Spectrogram:
    """Spectrogram level in dB above a median background, on a regular grid of frames along the recording's timeline.

    `valid` marks the frames that carry audio. A frame whose STFT window overlaps a gap
    in the audio (a hole between files, a pause) is kept on the grid, so audio seconds stay
    convertible to UTC, but is marked invalid and holds 0 dB. `sample` returns its fill value
    for any point that would interpolate from an invalid frame, and the per-bin medians used
    for whitening skip invalid frames. A spectrogram built without a mask is all valid.

    A gap carries no signal, and a score must not be renormalised by the count of valid
    samples: a curve sample in a gap adds the fill value (0) and still counts in the mean, so a
    curve with half its samples in gaps keeps at most half its score. Renormalising would let a
    fit to the flat tails alone, its sweep lost in a gap, look as confident as a full curve.

    `start_utc`, when known, is the UNIX time of audio second 0, so frame i was heard at
    start_utc + t[i].

    `whitening` names how S was normalised: "time" (the default) is dB above each bin's median over
    time (compute_spectrogram's interpolated block median, and local_whiten's over an event window);
    "frequency" is median spectral subtraction, dB above each frame's median across frequency within
    +-bg_hz (Ramseier & Pieren 2024 eq. 11),
    which keeps a tone that sits in one bin for long, and local_whiten then leaves it as it is."""
    t: np.ndarray      # (T,) centre time of each frame, s
    f: np.ndarray      # (F,) bin frequencies, Hz
    S: np.ndarray      # (F, T) level in dB above the median background (per bin, or across frequency; see whitening)
    valid: np.ndarray = None           # type: ignore[assignment]  # (T,) bool, True where the frame carries audio; None -> all valid
    start_utc: float | None = None     # UNIX time of audio second 0, if known
    whitening: str = "time"            # "time" or "frequency"; see above

    def __post_init__(self):
        self.valid = (np.ones(len(self.t), bool) if self.valid is None
                      else np.asarray(self.valid, bool))
        if self.valid.shape != np.shape(self.t):
            raise ValueError(f"valid has shape {self.valid.shape}, expected {np.shape(self.t)}")

    @property
    def dt(self) -> float:
        return float(self.t[1] - self.t[0])

    @property
    def df(self) -> float:
        return float(self.f[1] - self.f[0])

    def with_S(self, S: np.ndarray) -> "Spectrogram":
        """The same grid, mask and start time with new power values."""
        return dataclasses.replace(self, S=S)

    def bin_median(self) -> np.ndarray:
        """Per-bin median over the valid frames, shape (F, 1); zeros if none is valid."""
        if self.valid.all():
            return np.median(self.S, axis=1, keepdims=True)
        if not self.valid.any():
            return np.zeros((self.S.shape[0], 1), self.S.dtype)
        return np.median(self.S[:, self.valid], axis=1, keepdims=True)

    def sample(self, t, f, fill=0.0):
        """Bilinear sample at (t, f) pairs (arrays); outside the grid, or wherever the
        interpolation would take weight from an invalid frame -> fill."""
        t = np.asarray(t, float); f = np.asarray(f, float)
        ti = (t - self.t[0]) / self.dt
        fi = (f - self.f[0]) / self.df
        ok = (ti >= 0) & (ti <= len(self.t) - 1) & (fi >= 0) & (fi <= len(self.f) - 1) & np.isfinite(ti) & np.isfinite(fi)
        out = np.full(t.shape, fill, float)
        ti = ti[ok]; fi = fi[ok]
        i0 = np.floor(ti).astype(int); j0 = np.floor(fi).astype(int)
        i1 = np.minimum(i0 + 1, len(self.t) - 1); j1 = np.minimum(j0 + 1, len(self.f) - 1)
        wt = ti - i0; wf = fi - j0
        v = (self.S[j0, i0] * (1 - wt) * (1 - wf) + self.S[j0, i1] * wt * (1 - wf)
             + self.S[j1, i0] * (1 - wt) * wf + self.S[j1, i1] * wt * wf)
        out[ok] = np.where(self.valid[i0] & (self.valid[i1] | (wt == 0)), v, fill)
        return out

    def crop(self, t0, t1, f0=None, f1=None) -> "Spectrogram":
        m = (self.t >= t0) & (self.t <= t1)
        fm = np.ones_like(self.f, bool)
        if f0 is not None: fm &= self.f >= f0
        if f1 is not None: fm &= self.f <= f1
        return Spectrogram(self.t[m], self.f[fm], self.S[np.ix_(fm, m)], self.valid[m], self.start_utc, self.whitening)

    def save(self, path):
        """Write an .npz (the suffix is added if missing, as numpy does), atomically: readers see
        the old file or the complete new one."""
        path = Path(path)
        if path.suffix != ".npz":
            path = path.with_name(path.name + ".npz")
        extra = {} if self.start_utc is None else {"start_utc": np.float64(self.start_utc)}
        if self.whitening != "time":
            extra["whitening"] = np.array(self.whitening)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp.npz")
        try:
            np.savez_compressed(tmp, t=self.t, f=self.f, S=self.S.astype(np.float32), valid=self.valid, **extra)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def load(cls, path) -> "Spectrogram":
        z = np.load(path)
        valid = z["valid"] if "valid" in z.files else np.ones(len(z["t"]), bool)
        start = float(z["start_utc"]) if "start_utc" in z.files else None
        whitening = str(z["whitening"]) if "whitening" in z.files else "time"
        return cls(z["t"], z["f"], z["S"], valid, start, whitening)
