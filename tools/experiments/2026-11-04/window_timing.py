"""Runtime of fit_event at the 2.048 s and 0.512 s windows on a quiet machine, single process, five
primary Livermore passes (the first five by id), both objectives: the timing window_length.py's
contended run could not give.

usage: window_timing.py RUN"""
import csv
import json
import os
import sys
import time
from pathlib import Path

for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[k] = "1"
import numpy as np                                                       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import window_length as WL                                              # noqa: E402

from dopplertrack.tracks import fit_event                                # noqa: E402

WL._liv_init()
rows = [r for r in csv.DictReader(open(WL.AUDIT / "passes.csv")) if float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) * 100 < WL.GOOD_RMS]
out = []
for r in sorted(rows, key=lambda r: r["id"])[:5]:
    p = WL._LIV["passes"][r["id"]]
    th, g, _, _, _ = WL.LA.heard_curve(p, WL._LIV["sites"][r["site"]], WL.C)
    shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
    fs = f0 * np.interp(start + np.arange(p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start, 0.25) - shift, th, g)
    span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start); band = (0.85 * fs.min(), 1.15 * fs.max())
    x, _ = WL.audio.load_audio(p["dir"] / "audio.wav", WL.SR)
    row = dict(id=r["id"], span_s=span[1] - span[0], band_hz=band[1] - band[0])
    for n in (8192, 2048):
        t0 = time.perf_counter(); sp = WL.spectrogram(x, n); row[f"stft_{n}"] = time.perf_counter() - t0
        for o in WL.OBJECTIVES:
            t0 = time.perf_counter(); fit_event(sp, *span, *band, c=WL.C, objective=o); row[f"fit_{n}_{o}"] = time.perf_counter() - t0
    out.append(row); print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
(Path(sys.argv[1]) / "window_timing.json").write_text(json.dumps(out, indent=1))
