"""Audio decoding and whitened low-band spectrograms."""
from __future__ import annotations

import dataclasses
import datetime
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.signal as ss


class FFmpegNotFoundError(RuntimeError):
    """The external audio decoder is not installed or not on PATH."""


_FFMPEG_MISSING = ("ffmpeg was not found on PATH. Install it with 'brew install ffmpeg' "
                   "(macOS) or 'sudo apt-get install ffmpeg' (Debian/Ubuntu).")


def _ffmpeg_cmd(path, sr):
    return ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
            "-f", "f32le", "-acodec", "pcm_f32le", "-"]


def load_audio(path: str | Path, sr: int = 4000) -> tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable file to mono float32 at `sr` Hz."""
    try:
        raw = subprocess.run(_ffmpeg_cmd(path, sr), check=True, capture_output=True).stdout
    except FileNotFoundError as exc:
        raise FFmpegNotFoundError(_FFMPEG_MISSING) from exc
    return np.frombuffer(raw, dtype=np.float32).copy(), sr


def stream_audio(path: str | Path, sr: int = 4000, block: int = 1 << 20):
    """Decode like load_audio, yielding float32 blocks of up to `block` samples, so a
    many-hour file is never held whole."""
    try:
        p = subprocess.Popen(_ffmpeg_cmd(path, sr), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise FFmpegNotFoundError(_FFMPEG_MISSING) from exc
    out, errs = p.stdout, p.stderr
    assert out is not None and errs is not None
    tail = b""
    try:
        while True:
            raw = out.read(4 * block)
            if not raw:
                break
            raw = tail + raw
            n = len(raw) // 4 * 4
            tail = raw[n:]
            if n:
                yield np.frombuffer(raw[:n], dtype=np.float32).copy()
    finally:
        out.close()
        err = errs.read()
        errs.close()
        rc = p.wait()
    if rc:
        raise subprocess.CalledProcessError(rc, p.args, stderr=err)


@dataclass
class Spectrogram:
    """Whitened power on a regular grid of frames along the recording's timeline.

    `valid` marks the frames that carry evidence. A frame whose STFT window overlaps a gap
    in the audio (a hole between files, a pause) is kept on the grid, so audio seconds stay
    convertible to UTC, but is marked invalid and holds 0 dB. `sample` returns its fill value
    for any point that would interpolate from an invalid frame, and the per-bin medians used
    for whitening skip invalid frames. A spectrogram built without a mask is all valid.

    A gap carries zero evidence, and a score must not be renormalised by the count of valid
    samples: a curve sample in a gap adds the fill value (0) and still counts in the mean, so a
    curve with half its samples in gaps keeps at most half its score. Renormalising would let a
    fit to the flat tails alone, its sweep lost in a gap, look as confident as a full curve.

    `start_utc`, when known, is the UNIX time of audio second 0, so frame i was heard at
    start_utc + t[i].

    `whitening` names how S was normalised: "time" (the default) is dB above each bin's median over
    time (compute_spectrogram's running median, and local_whiten's over an event window); "frequency"
    is dB above each frame's median across frequency within +-bg_hz (Ramseier & Pieren 2024 eq. 11),
    which keeps a tone that sits in one bin for long, and local_whiten then leaves it as it is."""
    t: np.ndarray      # (T,) centre time of each frame, s
    f: np.ndarray      # (F,) bin frequencies, Hz
    S: np.ndarray      # (F, T) whitened power, dB above per-bin median
    valid: np.ndarray = None           # type: ignore[assignment]  # (T,) bool, True where the frame carries evidence; None -> all valid
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


def _whiten(L: np.ndarray, valid: np.ndarray | None, hop_s: float, whiten_window_s: float | None) -> np.ndarray:
    """Subtract each bin's median (global, or running over `whiten_window_s`), in place where it
    can be. Medians are taken over valid frames only; valid=None means all frames are valid."""
    if valid is not None and valid.all():
        valid = None
    T = L.shape[1]
    w = None if whiten_window_s is None else int(whiten_window_s / hop_s)
    if w is None or w >= T:
        if valid is None:
            return L - np.median(L, axis=1, keepdims=True)
        if not valid.any():
            return L
        for k in range(L.shape[0]):
            L[k] -= np.median(L[k, valid])
        return L
    # block-wise running median (cheap, adequate for slow drifts), linearly blended between
    # block centres to avoid seams; a block without a valid frame contributes no centre
    nb = int(np.ceil(T / w))
    centers: list[float] = []
    meds: list[np.ndarray] = []
    for b in range(nb):
        sl = slice(b * w, min((b + 1) * w, T))
        if valid is None:
            meds.append(np.median(L[:, sl], axis=1))
        elif valid[sl].any():
            meds.append(np.median(L[:, sl][:, valid[sl]], axis=1))
        else:
            continue
        centers.append((sl.start + sl.stop) / 2)
    if not centers:
        return L
    cm = np.array(meds)                                                  # (nb, F)
    idx = np.arange(T)
    out = L if L.dtype == np.float32 else L.astype(np.float32)
    for k in range(L.shape[0]):                                          # row by row: no (F, T) float64 copy
        out[k] = L[k] - np.interp(idx, centers, cm[:, k])
    return out


WHITENINGS = ("time", "frequency")


def _whiten_frequency(L: np.ndarray, df: float, bg_hz: float, chunk: int = 4096) -> np.ndarray:
    """Each frame's dB less its running median across frequency within +-bg_hz, in place, a chunk of
    frames at a time."""
    from scipy.ndimage import median_filter
    size = 2 * int(round(bg_hz / df)) + 1
    for k in range(0, L.shape[1], chunk):
        L[:, k:k + chunk] -= median_filter(L[:, k:k + chunk], size=(size, 1), mode="nearest")
    return L


def _band(sr, nfft, fmin, fmax):
    f = np.fft.rfftfreq(nfft, 1 / sr)
    band = (f >= fmin) & (f <= fmax)
    return f[band], band


def _stft_db(seg, sr, nperseg, hop, band, nfft=None, window="hann"):
    _, _, Z = ss.stft(seg, sr, nperseg=nperseg, noverlap=nperseg - hop, window=window, nfft=nfft,
                      boundary=None, padded=False)
    return (10 * np.log10(np.abs(Z[band]) ** 2 + 1e-20)).astype(np.float32)


def compute_spectrogram(x: np.ndarray, sr: int, nperseg: int = 8192, hop_s: float = 0.25,
                        fmin: float = 40.0, fmax: float = 450.0,
                        whiten_window_s: float | None = 600.0, chunk_frames: int = 16384,
                        nfft: int | None = None, whiten: str = "time", bg_hz: float = 10.0,
                        window: str = "hann") -> Spectrogram:
    """High-resolution STFT in the low band, converted to dB and whitened.

    Whitening subtracts, per frequency bin, the running median over
    `whiten_window_s` (or the global median if None). This flattens mains
    hum and stationary machinery so only *changing* tones stand out.

    The window (Hann unless `window` names another scipy window, e.g. "boxcar") is `nperseg` samples
    long and is zero-padded to `nfft` (default nperseg), so windows of different lengths can share
    one frequency grid; padding only interpolates the spectrum, and the resolution stays sr / nperseg.

    whiten="frequency" replaces the median over time with each frame's median across frequency
    within +-bg_hz (Spectrogram.whitening); whiten_window_s is then unused.
    """
    if whiten not in WHITENINGS:
        raise ValueError(f"whiten must be one of {WHITENINGS}")
    hop = max(1, int(round(hop_s * sr)))
    # frames k = 0 .. K-1 cover samples [k*hop, k*hop + nperseg); computed in chunks so a
    # many-hour recording never holds its full complex STFT in memory
    K = (len(x) - nperseg) // hop + 1
    f, band = _band(sr, nfft or nperseg, fmin, fmax)
    parts = []
    for k0 in range(0, K, chunk_frames):
        k1 = min(k0 + chunk_frames, K)
        parts.append(_stft_db(x[k0 * hop:(k1 - 1) * hop + nperseg], sr, nperseg, hop, band, nfft, window))
    L = np.concatenate(parts, axis=1)
    t = (nperseg / 2 + np.arange(K) * hop) / sr
    if whiten == "frequency":
        return Spectrogram(t, f, _whiten_frequency(L, float(f[1] - f[0]), bg_hz), whitening="frequency")
    L = _whiten(L, None, hop / sr, whiten_window_s)
    return Spectrogram(t, f, L.astype(np.float32))


# ---- several files on one timeline -------------------------------------------------------

_AUDIOMOTH_NAME = re.compile(r"(\d{8})_(\d{6})\.wav", re.IGNORECASE)


def audiomoth_files(directory: str | Path) -> tuple[list[tuple[Path, float]], float]:
    """The WAVs in an AudioMoth folder as (path, offset_s) from the first one, and the first
    one's start as UNIX time. AudioMoth names a file by its start, YYYYMMDD_HHMMSS.WAV, in the
    time zone that CONFIG.TXT names; only UTC is accepted."""
    directory = Path(directory)
    cfg = directory / "CONFIG.TXT"
    if cfg.exists():
        m = re.search(r"^Time zone\s*:\s*(\S+)", cfg.read_text(errors="replace"), re.MULTILINE)
        if m and m.group(1) != "UTC":
            raise ValueError(f"{cfg}: time zone {m.group(1)}, only UTC file names are supported")
    found = []
    for p in directory.iterdir():
        m = _AUDIOMOTH_NAME.fullmatch(p.name)
        if m:
            ts = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            found.append((ts.replace(tzinfo=datetime.timezone.utc).timestamp(), p))
    if not found:
        raise ValueError(f"no AudioMoth files (YYYYMMDD_HHMMSS.WAV) in {directory}")
    found.sort()
    t0 = found[0][0]
    return [(p, ts - t0) for ts, p in found], t0


def _placed_blocks(files, sr, snap_s, block):
    """Yield (samples, is_audio) blocks along one timeline: each file at its offset, silence
    (is_audio=False) over any hole. A file starting within snap_s of the previous file's end is
    placed right at that end; an earlier start than that is an overlap, which is an error."""
    end = None
    snap = int(round(snap_s * sr))
    for path, offset in sorted(files, key=lambda pf: pf[1]):
        start = int(round(offset * sr))
        if end is None:
            if start:
                raise ValueError("the first file must start at offset 0")
        else:
            hole = start - end
            if hole < -snap:
                raise ValueError(f"{path} starts {-hole / sr:.3f} s before the previous file ends")
            if hole <= snap:
                start = end
            else:
                for g in range(0, hole, block):
                    yield np.zeros(min(block, hole - g), np.float32), False
        n = 0
        for x in stream_audio(path, sr, block):
            n += len(x)
            yield x, True
        end = start + n


def spectrogram_from_files(files, sr: int = 4000, start_utc: float | None = None, snap_s: float = 0.0,
                           **kw) -> Spectrogram:
    """compute_spectrogram for several files on one timeline: `files` is [(path, offset_s)],
    offsets from the recording's start (the first file at 0), and `start_utc` that start as
    UNIX time, if known.

    Holes between files are silence in the sample stream, and every frame whose window overlaps
    one is invalid. Files that abut exactly (to within `snap_s`) leave no invalid frame. The audio
    is decoded and transformed chunk by chunk, so memory holds the spectrogram but never the
    whole recording's samples. Keyword arguments are compute_spectrogram's."""
    block = 1 << 22
    return spectrogram_from_blocks(_placed_blocks(files, sr, snap_s, block), sr, start_utc=start_utc, **kw)


def spectrogram_from_blocks(blocks, sr: int, start_utc: float | None = None, nperseg: int = 8192,
                            hop_s: float = 0.25, fmin: float = 40.0, fmax: float = 450.0,
                            whiten_window_s: float | None = 600.0, chunk_frames: int = 16384,
                            nfft: int | None = None, whiten: str = "time", bg_hz: float = 10.0) -> Spectrogram:
    """compute_spectrogram over a sample stream given as (samples, is_audio) blocks in timeline
    order; a block with is_audio=False is a gap (its samples are ignored and every frame whose
    window overlaps it is invalid). Frames are computed in the same chunks as
    compute_spectrogram, so an all-audio stream gives the same frames."""
    hop = max(1, int(round(hop_s * sr)))
    f, band = _band(sr, nfft or nperseg, fmin, fmax)
    parts, vparts = [], []
    buf, gap = [np.empty(0, np.float32)], [np.empty(0, bool)]     # samples not yet past a full chunk
    need = (chunk_frames - 1) * hop + nperseg                       # samples behind one chunk of frames

    def emit(final):
        nonlocal buf, gap
        x = np.concatenate(buf); g = np.concatenate(gap)
        while len(x) >= need or (final and len(x) >= nperseg):
            n = min(chunk_frames, (len(x) - nperseg) // hop + 1)
            seg = x[:(n - 1) * hop + nperseg]
            parts.append(_stft_db(seg, sr, nperseg, hop, band, nfft))
            cg = np.concatenate([[0], np.cumsum(g[:len(seg)])])
            s0 = np.arange(n) * hop
            vparts.append(cg[s0 + nperseg] - cg[s0] == 0)
            x = x[n * hop:]; g = g[n * hop:]
        buf, gap = [x], [g]
        return len(x)

    have = 0
    for x, is_audio in blocks:
        x = np.asarray(x, np.float32) if is_audio else np.zeros(len(x), np.float32)
        buf.append(x); gap.append(np.full(len(x), not is_audio))
        have += len(x)
        if have >= need:
            have = emit(False)
    emit(True)
    if not parts:
        raise ValueError("recording shorter than one STFT window")
    L = np.concatenate(parts, axis=1)
    valid = np.concatenate(vparts)
    t = (nperseg / 2 + np.arange(L.shape[1]) * hop) / sr
    if whiten == "frequency":
        L = _whiten_frequency(L, float(f[1] - f[0]), bg_hz)
    else:
        L = _whiten(L, valid, hop / sr, whiten_window_s)
    L[:, ~valid] = 0.0
    return Spectrogram(t, f, L.astype(np.float32, copy=False), valid, start_utc, whiten)


def spectrogram_from_audiomoth(directory, snap_s: float = 1.0, **kw) -> Spectrogram:
    """spectrogram_from_files on an AudioMoth folder, placed by the files' UTC names. The names
    resolve whole seconds, so by default a file within 1 s of the previous file's end abuts it."""
    files, start = audiomoth_files(directory)
    return spectrogram_from_files(files, start_utc=start, snap_s=snap_s, **kw)


# ---- cached spectrograms -----------------------------------------------------------------

def _ffmpeg_version() -> str:
    try:
        out = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError as exc:
        raise FFmpegNotFoundError(_FFMPEG_MISSING) from exc
    return out.splitlines()[0] if out else ""


def cached_spectrogram(audio: str | Path, sr: int = 4000, snap_s: float | None = None,
                       root: str | Path | None = None, **kw) -> Spectrogram:
    """The spectrogram of one file, or of an AudioMoth folder placed by its UTC names, from the
    cache (dopplertrack.cache, kind "spectrogram") when one was built from identical inputs.

    The key holds each audio file's name, SHA-256 and offset, the start time, every parameter
    (keyword arguments are spectrogram_from_blocks's, defaults filled in), this module's source and
    the ffmpeg, numpy and scipy versions, since each can change the result."""
    import inspect

    import scipy

    from dopplertrack.runtime.cache import cached, file_sha256, source_sha256
    p = Path(audio)
    if p.is_dir():
        files, start = audiomoth_files(p)
        snap = 1.0 if snap_s is None else snap_s
    else:
        files, start, snap = [(p, 0.0)], None, 0.0 if snap_s is None else snap_s
    sig = inspect.signature(spectrogram_from_blocks).parameters
    params = {k: v.default for k, v in sig.items() if k not in ("blocks", "sr", "start_utc")}
    unknown = set(kw) - set(params)
    if unknown:
        raise TypeError(f"unknown spectrogram parameters: {sorted(unknown)}")
    params.update(kw)
    parts = {"files": [[f.name, file_sha256(f), float(o)] for f, o in files], "start_utc": start,
             "snap_s": snap, "sr": sr, "params": params, "source": source_sha256(__name__),
             "versions": {"ffmpeg": _ffmpeg_version(), "numpy": np.__version__, "scipy": scipy.__version__}}
    return cached("spectrogram", parts,
                  lambda: spectrogram_from_files(files, sr, start_utc=start, snap_s=snap, **params), root=root)
