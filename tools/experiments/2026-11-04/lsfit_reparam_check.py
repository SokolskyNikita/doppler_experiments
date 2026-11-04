"""Does fitting t_c relative to the track's start change any least-squares fit of run 2? Refits every track
run 2 fitted (the 40 Livermore passes and the four development events) with fit_track as of 51f59ce, loaded
from that commit's tracks.py, and with the installed one, and compares f0, v, d and t_c. It reads no error
or criterion, only the two versions' parameters.

usage: lsfit_reparam_check.py OLD_TRACKS_PY OUT.json"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import livermore_audit as LA                                            # noqa: E402

from dopplertrack import audio, tracks                                  # noqa: E402
from dopplertrack.audio import Spectrogram                              # noqa: E402
from dopplertrack.doppler import speed_of_sound                         # noqa: E402

REPO = Path(__file__).resolve().parents[3]
AUDIT = LA.DATA / "runs/2026-11-04-livermore-audit"


def load_old(path):
    spec = importlib.util.spec_from_file_location("dopplertrack.tracks_old", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "dopplertrack"
    sys.modules[spec.name] = mod                  # dataclasses look their module up while it executes
    spec.loader.exec_module(mod)
    return mod


def windows():
    """(label, spectrogram loader, t0, t1, f_lo, f_hi, c) for every track run 2 fitted."""
    rows = {r["id"]: r for r in csv.DictReader(open(AUDIT / "passes.csv"))}
    passes = {p["id"]: p for p in LA.load_passes()}
    sites = {s["name"]: s for s in json.load(open(AUDIT / "sites.json"))["sites"]}
    c15 = speed_of_sound(15.0)
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        th, g, _, _, _ = LA.heard_curve(p, sites[r["site"]], c15)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        fs = f0 * np.interp(start + np.arange(*span, 0.25) - shift, th, g, left=np.nan, right=np.nan)
        band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        load = (lambda p=p: audio.compute_spectrogram(audio.load_audio(p["dir"] / "audio.wav", 4000)[0], 4000,
                                                      nperseg=8192, hop_s=0.25, fmin=40, fmax=1900))
        yield pid, load, *span, *band, c15
    swfl = json.loads((REPO / "docs/results/swfl_detected.json").read_text())
    c = speed_of_sound()
    ob = lambda: Spectrogram.load(LA.DATA / "derived/oyster_bay/rec.npz")
    yield "oyster-bay ev1", ob, 2090, 2200, 95, 200, c
    yield "oyster-bay ev2", ob, 3020, 3130, 95, 195, c
    sw = lambda: Spectrogram.load(LA.DATA / "derived/swfl/rec.npz")
    for k in (4, 12):
        e = swfl[k]
        yield f"eagle-cam rank {k + 1}", sw, e["t_start"], e["t_end"], 0.85 * e["f_post"], 1.15 * e["f_pre"], c


def main(old_path, out):
    old = load_old(old_path)
    rows, cache = [], {}
    for label, load, t0, t1, lo, hi, c in windows():
        sp = cache.get(load) or load()
        if label.startswith(("oyster", "eagle")):
            cache = {load: sp}
        tr = tracks.ridge_track(sp, t0, t1, lo, hi)
        for weighted in (False, True):
            a = old.fit_track(old.Track(tr.t, tr.f, tr.amplitude, tr.valid), c=c, weighted=weighted)
            b = tracks.fit_track(tr, c=c, weighted=weighted)
            d = {k: (getattr(a, k), getattr(b, k)) for k in ("f0", "v", "d", "t_cpa_emit")}
            rel = {k: abs(x - y) / max(abs(x), 1e-12) if np.isfinite(x) and np.isfinite(y) else (0.0 if np.isnan(x) == np.isnan(y) else np.inf)
                   for k, (x, y) in d.items() if k != "t_cpa_emit"}
            rows.append(dict(window=label, weighted=weighted, params=d, rel_diff=rel,
                             t_cpa_emit_diff_s=abs(d["t_cpa_emit"][0] - d["t_cpa_emit"][1])))
            print(label, weighted, {k: f"{v:.2e}" for k, v in rel.items()}, f"dt {rows[-1]['t_cpa_emit_diff_s']:.2e}", flush=True)
    worst = {k: max(r["rel_diff"][k] for r in rows) for k in ("f0", "v", "d")}
    worst["t_cpa_emit_s"] = max(r["t_cpa_emit_diff_s"] for r in rows)
    Path(out).write_text(json.dumps({"worst": worst, "rows": rows}, indent=1, default=float) + "\n")
    print("worst", worst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
