"""Do an AudioMoth folder's minute files abut, or is there a gap between them? For each pair of
consecutive WAVs: fit an order-32 linear predictor to the last 200,000 samples of the first file,
predict the first sample of the next, and express the error in units of the predictor's in-file
residual. Continuous audio gives about 1; unrelated samples give about std(x)/residual. A mid-file
point of the next file, predicted from its own past, is the control.

usage: gap_seams.py FOLDER   (raw 16-bit mono WAVs with an 80-byte header, as ESID 740/710's are)"""
import datetime
import sys
from pathlib import Path

import numpy as np

P = 32
fs = sorted(Path(sys.argv[1]).glob("*.wav"))


def read(p):
    return np.frombuffer(p.read_bytes()[80:], dtype="<i2").astype(float)


def start(p):
    return datetime.datetime.strptime(p.name[:15], "%Y%m%d_%H%M%S")


X = [read(p) for p in fs]
seam, ctrl, indep, holes = [], [], [], []
for i, (a, b) in enumerate(zip(X, X[1:])):
    x = a[-200000:]
    A = np.lib.stride_tricks.sliding_window_view(x[:-1], P); y = x[P:]
    c, *_ = np.linalg.lstsq(A, y, rcond=None); se = np.std(y - A @ c)
    err = (b[0] - a[-P:] @ c) / se
    step = (start(fs[i + 1]) - start(fs[i])).total_seconds()
    if step == len(a) / 48000:
        seam.append(err)
    else:
        holes.append((fs[i].name, fs[i + 1].name, step, err))
    ctrl.append((b[100000] - b[100000 - P:100000] @ c) / se)
    indep.append(np.std(a) / se)
print(f"{len(X)} files of {sorted({len(x) / 48000 for x in X})} s")
print(f"{len(seam)} abutting seams: RMS normalised 1-step error {np.sqrt(np.mean(np.square(seam))):.2f}; "
      f"mid-file control {np.sqrt(np.mean(np.square(ctrl))):.2f}; if unrelated about {np.median(indep):.2f}")
for h in holes:
    print("hole:", *h)
