"""The spectrogram of one private recorder session, for a private case recipe.

The supported recorder format uses mono FLACs, a new file after every gap, and a timeline.jsonl whose
file_close events give each file's first-sample UTC (the clock's final estimate) and sample count. The files are placed
on one timeline by those times, so a gap between files is marked invalid, and transformed with `dopplertrack
spectrogram`'s defaults: a 2.048 s Hann window, 0.25 s hop, 0.49 Hz bins, whitened by a 600 s running median per bin.
The band is 40 Hz to --fmax: 450 Hz (the default, the pipeline's band, decoded at 4 kHz) or wider for a full-band
session (the band test, docs/experiments/2026-11-04-seattle-home-pilot.md), decoded at the lowest rate in 1 kHz steps
that keeps fmax below 0.45 of it, with the window's length in samples scaled so its duration and bins don't change.
Refuses to overwrite OUT, and refuses an OUT outside $DOPPLERTRACK_DATA/private/.

usage: session_spectrogram.py SESSION_DIR OUT [--fmax HZ]
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

WINDOW_S, HOP_S, FMIN = 2.048, 0.25, 40.0


def recipe(fmax: float = 450.0) -> dict:
    """The STFT settings for a band 40 Hz to fmax: 4 kHz up to 1.8 kHz, else the next 1 kHz step above fmax / 0.45."""
    sr = max(4000, 1000 * math.ceil(fmax / 0.45 / 1000))
    return {"sr": sr, "nperseg": int(round(WINDOW_S * sr)), "hop_s": HOP_S, "fmin": FMIN, "fmax": float(fmax)}


def session_files(session: Path) -> tuple[list[tuple[Path, float]], float]:
    """[(file, offset_s)] from the timeline's closed files, and the first file's first-sample UTC."""
    closed = [json.loads(line) for line in (session / "timeline.jsonl").read_text().splitlines()]
    closed = sorted((e for e in closed if e.get("type") == "file_close"), key=lambda e: e["first_sample_utc_epoch"])
    if not closed:
        sys.exit(f"{session}/timeline.jsonl has no closed file (an unclosed session can't be placed)")
    start = closed[0]["first_sample_utc_epoch"]
    files = [(session / e["file"], e["first_sample_utc_epoch"] - start) for e in closed]
    missing = [str(p) for p, _ in files if not p.exists()]
    if missing:
        sys.exit(f"files named by the timeline are missing: {missing}")
    return files, start


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path); ap.add_argument("out", type=Path)
    ap.add_argument("--fmax", type=float, default=450.0, help="the band's upper edge, Hz (default 450)")
    a = ap.parse_args()
    private = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack")) / "private"
    if not a.out.resolve().is_relative_to(private.resolve()):
        sys.exit(f"{a.out} is not under {private}: a home recording's derived files stay private")
    if a.out.exists():
        sys.exit(f"{a.out} exists")
    from dopplertrack.components.stft import spectrogram_from_files
    files, start = session_files(a.session)
    r = recipe(a.fmax)
    sp = spectrogram_from_files(files, sr=r["sr"], start_utc=start, snap_s=0.01, nperseg=r["nperseg"], hop_s=r["hop_s"],
                                fmin=r["fmin"], fmax=r["fmax"])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    sp.save(a.out)
    print(f"{a.session.name} -> {a.out}: {len(sp.t)} frames, {len(sp.f)} bins, "
          f"{0 if sp.valid is None else int((~sp.valid).sum())} invalid frames, start {start:.3f}, recipe {r}")


if __name__ == "__main__":
    main()
