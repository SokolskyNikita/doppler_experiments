"""The spectrogram, the squared magnitude of the STFT (Flandrin 2018 eq. 6.2), of the low band in dB, normalised by a
median background, from samples, a sample stream or files on one timeline."""
from __future__ import annotations

import numpy as np
import scipy.signal as ss

from dopplertrack.components.audio_input import audiomoth_files, placed_blocks
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.whitening.frequency_median import whiten_frequency
from dopplertrack.components.whitening.time_median import whiten_time

WHITENINGS = ("time", "frequency")


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
    """The spectrogram (squared STFT magnitude, Flandrin 2018 eq. 6.2) of the low band, in dB and whitened.

    Whitening subtracts, per frequency bin, the median over blocks of
    `whiten_window_s`, linearly interpolated between block centres (or the global
    median if None). This flattens mains hum and stationary machinery so only
    *changing* tones stand out.

    The window (Hann unless `window` names another scipy window, e.g. "boxcar") is `nperseg` samples
    long and is zero-padded to `nfft` (default nperseg), so windows of different lengths can share
    one frequency grid; padding only interpolates the spectrum, and the resolution stays sr / nperseg.

    whiten="frequency" replaces the median over time with median spectral subtraction across
    frequency, each frame less its median within +-bg_hz (Ramseier & Pieren 2024 eq. 11;
    Spectrogram.whitening); whiten_window_s is then unused.
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
        return Spectrogram(t, f, whiten_frequency(L, float(f[1] - f[0]), bg_hz), whitening="frequency")
    L = whiten_time(L, None, hop / sr, whiten_window_s)
    return Spectrogram(t, f, L.astype(np.float32))


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
    return spectrogram_from_blocks(placed_blocks(files, sr, snap_s, block), sr, start_utc=start_utc, **kw)


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
        L = whiten_frequency(L, float(f[1] - f[0]), bg_hz)
    else:
        L = whiten_time(L, valid, hop / sr, whiten_window_s)
    L[:, ~valid] = 0.0
    return Spectrogram(t, f, L.astype(np.float32, copy=False), valid, start_utc, whiten)


def spectrogram_from_audiomoth(directory, snap_s: float = 1.0, **kw) -> Spectrogram:
    """spectrogram_from_files on an AudioMoth folder, placed by the files' UTC names. The names
    resolve whole seconds, so by default a file within 1 s of the previous file's end abuts it."""
    files, start = audiomoth_files(directory)
    return spectrogram_from_files(files, start_utc=start, snap_s=snap_s, **kw)
