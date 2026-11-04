"""Phase 2 item 2, stage 2: the pipeline's fit, tracks.fit_event (imported unchanged), on each Livermore
pass, with both objectives, on three spectrograms over the ridge's span:
  C-render  the ideal straight pass (f0*, v*, R*, tau*) drawn as a one-bin ridge (10 dB, split
            bilinearly between the two nearest bins) on the package's grid (0.488 Hz x 0.25 s)
  A-render  the trajectory curve f0* g(t) drawn the same way
  wav       the pass's own audio.wav through the package's compute_spectrogram (2.048 s Hann, 0.25 s hop)
The rendered images carry no noise: C-render measures fit_event's own discretisation and objective error,
A-render adds model error, and wav is the pipeline on the real recording. Times are recording seconds of
the WAV, whose first sample is on the ADS-B clock at the first ridge stamp less the audit's pad and shift.
References as in model_error.py.

Run from the repo root:  uv run python tools/experiments/2026-11-04/model_error_stage2.py "$RUN"
"""
import csv
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

from dopplertrack.audio import Spectrogram, compute_spectrogram, load_audio
from dopplertrack.tracks import fit_event

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("model_error", HERE / "model_error.py")
me = importlib.util.module_from_spec(spec); spec.loader.exec_module(me)
ls = me.ls
C = me.C15
SR, NFFT, HOP = 4000, 8192, 1000
F_ALL = np.fft.rfftfreq(NFFT, 1 / SR)


def render(curve, dur, fmax):
    F = F_ALL[(F_ALL >= 40.0) & (F_ALL <= fmax)]
    t = NFFT / 2 / SR + np.arange(0.0, dur - NFFT / SR, HOP / SR)
    f = curve(t)
    S = np.zeros((len(F), len(t)), np.float32)
    x = (f - F[0]) / (F[1] - F[0])
    ok = np.isfinite(x) & (x >= 0) & (x < len(F) - 1)
    i0 = np.floor(x[ok]).astype(int); w = x[ok] - i0
    cols = np.flatnonzero(ok)
    S[i0, cols] = 10.0 * (1 - w); S[i0 + 1, cols] += 10.0 * w
    return Spectrogram(t, F.copy(), S)


def main(run: Path):
    rows = {r["id"]: r for r in csv.DictReader(open(me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(me.AUDIT / "sites.json"))["sites"]}
    flagged = {k for k, r in rows.items() if 100 * float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) >= 1.6}
    out = []
    for p in me.audit.load_passes():
        a = rows[p["id"]]; site = sites[a["site"]]
        shift, f0s = float(a["shift_15C"]), float(a["f0_15C"])
        T0 = p["ridge"][0, 0] - float(a["pad_before"]) - shift          # WAV sample 0 on the ADS-B clock
        te, pos = me.trajectory(p, site)
        ref = me.reference(te, pos, C)
        th, g, _ = me.heard(te, pos, C)
        dur = float(a["dur"])
        t_start, t_end = p["ridge"][0, 0] - shift - T0, p["ridge"][-1, 0] - shift - T0
        f_lo, f_hi = 0.9 * p["ridge"][:, 1].min(), 1.1 * p["ridge"][:, 1].max()
        fmax = max(450.0, 1.5 * f_hi)       # the package's default top is 450 Hz; some passes' tones are above it
        x, _ = load_audio(p["dir"] / "audio.wav", SR)
        sources = {
            "C-render": render(lambda t: ls.model(t + T0, f0s, ref["v"], ref["R"], ref["tau"], C), dur, fmax),
            "A-render": render(lambda t: f0s * me.at(t + T0, th, g), dur, fmax),
            "wav": compute_spectrogram(x, SR, fmax=fmax),
        }
        for src, sp in sources.items():
            for obj in ("contrast", "brightness"):
                t0 = time.time()
                row = dict(id=p["id"], group="flagged" if p["id"] in flagged else "primary", source=src, objective=obj,
                           ref_f0=f0s, ref_v=ref["v"], ref_R=ref["R"], ref_tau=ref["tau"] - T0, fmax=fmax, error="")
                try:
                    fe = fit_event(sp, t_start, t_end, f_lo, f_hi, c=C, objective=obj)
                    row.update(f0=fe.f0, v=fe.v, R=fe.d, tau=fe.t_cpa_emit, score=fe.score)
                except Exception as e:      # a failed fit is a result, recorded
                    row.update(f0=np.nan, v=np.nan, R=np.nan, tau=np.nan, score=np.nan, error=repr(e))
                row["seconds"] = time.time() - t0
                for q in ("f0", "v", "R"):
                    row[f"err_{q}_pct"] = 100 * (row[q] / row[f"ref_{q}"] - 1)
                row["err_tau"] = row["tau"] - row["ref_tau"]
                out.append(row)
        last = out[-6:]
        print(p["id"], " ".join(f"{r['source']}/{r['objective'][:4]} R {r['err_R_pct']:+6.1f}% v {r['err_v_pct']:+5.1f}%" for r in last),
              f"({sum(r['seconds'] for r in last):.0f} s)", flush=True)
    with open(run / "stage2.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
