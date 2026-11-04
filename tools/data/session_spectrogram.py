"""The spectrogram of one session of the owner's home recorder, for a private case's recipe. Runs on this Mac only.

The recorder (samsung-a17/mic-recorder) writes hourly mono FLACs at 1 kHz, a new file after every gap, and a
timeline.jsonl whose file_close events give each file's first-sample UTC (the clock's final estimate) and sample
count. The files are placed on one timeline by those times, so a gap between files is marked invalid, and transformed
with `dopplertrack spectrogram`'s defaults (0.25 s hop, 40-450 Hz, decoded at the package's 4 kHz so the window and
bins match every other case; the content above 500 Hz is absent). Refuses to overwrite OUT, and refuses an OUT
outside $DOPPLERTRACK_DATA/private/.

usage: session_spectrogram.py SESSION_DIR OUT
"""
import json
import os
import sys
from pathlib import Path

from dopplertrack.audio import spectrogram_from_files

if len(sys.argv) != 3:
    sys.exit(__doc__)
session, out = Path(sys.argv[1]), Path(sys.argv[2])
private = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack")) / "private"
if not out.resolve().is_relative_to(private.resolve()):
    sys.exit(f"{out} is not under {private}: a home recording's derived files stay private")
if out.exists():
    sys.exit(f"{out} exists")
closed = [json.loads(line) for line in (session / "timeline.jsonl").read_text().splitlines()]
closed = sorted((e for e in closed if e.get("type") == "file_close"), key=lambda e: e["first_sample_utc_epoch"])
if not closed:
    sys.exit(f"{session}/timeline.jsonl has no closed file (an unclosed session can't be placed)")
start = closed[0]["first_sample_utc_epoch"]
files = [(session / e["file"], e["first_sample_utc_epoch"] - start) for e in closed]
missing = [str(p) for p, _ in files if not p.exists()]
if missing:
    sys.exit(f"files named by the timeline are missing: {missing}")
sp = spectrogram_from_files(files, start_utc=start, snap_s=0.01, hop_s=0.25, fmin=40, fmax=450)
out.parent.mkdir(parents=True, exist_ok=True)
sp.save(out)
print(f"{session.name} -> {out}: {len(sp.t)} frames, {len(sp.f)} bins, "
      f"{0 if sp.valid is None else int((~sp.valid).sum())} invalid frames, start {start:.3f}")
