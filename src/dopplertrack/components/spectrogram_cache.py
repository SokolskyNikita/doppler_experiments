"""Spectrograms from the cache when one was built from identical inputs."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from dopplertrack.components.audio_input import audiomoth_files, ffmpeg_version
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.components.stft import spectrogram_from_blocks, spectrogram_from_files

# What a spectrogram build runs: decoding and placement, the STFT, both whitenings, the container and this entry point.
SPECTROGRAM_MODULES = ("dopplertrack.components.audio_input", "dopplertrack.components.stft",
                       "dopplertrack.components.whitening.time_median",
                       "dopplertrack.components.whitening.frequency_median", "dopplertrack.components.spectrogram",
                       "dopplertrack.components.spectrogram_cache")


def cached_spectrogram(audio: str | Path, sr: int = 4000, snap_s: float | None = None,
                       root: str | Path | None = None, **kw) -> Spectrogram:
    """The spectrogram of one file, or of an AudioMoth folder placed by its UTC names, from the
    cache (dopplertrack.runtime.cache, kind "spectrogram") when one was built from identical inputs.

    The key holds each audio file's name, SHA-256 and offset, the start time, every parameter
    (keyword arguments are spectrogram_from_blocks's, defaults filled in), the source of every module the
    build runs (SPECTROGRAM_MODULES) and the ffmpeg, numpy and scipy versions, since each can change the result."""
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
             "snap_s": snap, "sr": sr, "params": params, "source": source_sha256(*SPECTROGRAM_MODULES),
             "versions": {"ffmpeg": ffmpeg_version(), "numpy": np.__version__, "scipy": scipy.__version__}}
    return cached("spectrogram", parts,
                  lambda: spectrogram_from_files(files, sr, start_utc=start, snap_s=snap, **params), root=root)
