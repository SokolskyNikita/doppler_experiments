"""Audio decoding with ffmpeg, and placing several files (an AudioMoth folder) on one timeline."""
from __future__ import annotations

import datetime
import re
import subprocess
from pathlib import Path

import numpy as np


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


def placed_blocks(files, sr, snap_s, block):
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


def ffmpeg_version() -> str:
    try:
        out = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError as exc:
        raise FFmpegNotFoundError(_FFMPEG_MISSING) from exc
    return out.splitlines()[0] if out else ""
