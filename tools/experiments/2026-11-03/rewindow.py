"""Re-fit detected flyovers in a narrower window, the way `fit` does, then score the known point.

No hand choices: the window comes from detect's own CPA time (rule "fixed": +-55 s, as wide
as the README's hand windows; rule "scaled": +-2 d/v from detect's own fit, the time a
straight pass needs to cover ~90 % of its frequency drop on each side, clamped to 30-120 s);
the band brackets detect's own curve (0.85 f_post .. 1.15 f_pre). Harmonics 1 throughout.
Writes data/rewin/<case>_<variant>_ev{1,2}.json. Usage: rewindow.py CASE"""
import json
import sys
from pathlib import Path

import numpy as np

from dopplertrack import pipeline
from dopplertrack.adsb import load_traces
from dopplertrack.audio import Spectrogram
from dopplertrack.search import Grid
from dopplertrack.terrain import Terrain
from dopplertrack.tracks import EventFit, fit_event

CASES = {
    "oyster": dict(spec="data/rec.npz", det="data/detected.json", pick=(0, 1), traces="data/traces_ny.npz",
                   truth=(40.876466, -73.524951), pair=("a1dfeb", "ace391"), dt_true=922.96),
    "swfl": dict(spec="data/swfl/rec.npz", det="docs/results/swfl_detected.json", pick=(4, 12),
                 traces="data/swfl/traces_swfl.npz", truth=(26.702359, -81.847766), pair=("a2baea", "a336e4"), dt_true=None),
}
VARIANTS = {"A-bright": ("fixed", "brightness"), "A-contrast": ("fixed", "contrast"),
            "B-bright": ("scaled", "brightness"), "B-contrast": ("scaled", "contrast")}

name = sys.argv[1]
case = CASES[name]
pipeline.log = lambda *a, **k: None
sp = Spectrogram.load(case["spec"])
traces = load_traces(case["traces"])
det = [EventFit(**d) for d in json.load(open(case["det"]))]
evs = sorted((det[i] for i in case["pick"]), key=lambda e: e.t_cpa)
lat, lon = case["truth"]
grid = Grid.points([lat], [lon], Terrain().elevation(np.array([lat]), np.array([lon])))
out = Path("data/rewin"); out.mkdir(exist_ok=True)


def refit(ev, rule, objective):
    h = 55.0 if rule == "fixed" else float(np.clip(2 * ev.d / ev.v, 30, 120))
    t0, t1 = max(ev.t_cpa - h, float(sp.t[0])), min(ev.t_cpa + h, float(sp.t[-1]))
    return fit_event(sp, t0, t1, 0.85 * ev.f_post, 1.15 * ev.f_pre, objective=objective)


def report(label, e1, e2):
    res, _ = pipeline.run_search(sp, e1, e2, traces, grid, progress=False)
    hit = res[(res.icao1 == case["pair"][0]) & (res.icao2 == case["pair"][1])]
    dt = e2.t_cpa - e1.t_cpa
    err = f"{dt - case['dt_true']:+6.1f}" if case["dt_true"] else "   n/a"
    s = f"pair found, score {hit.score.iloc[0]:5.2f} (s1 {hit.s1.iloc[0]:5.2f}, s2 {hit.s2.iloc[0]:5.2f})" if len(hit) else "pair filtered out"
    win = " ".join(f"[{e.t_start:.0f},{e.t_end:.0f}]" for e in (e1, e2))
    print(f"{name:6s} {label:11s} gap {dt:7.2f} err {err}  ev2 f0 {e2.f0:6.1f} v {e2.v:5.1f} d {e2.d:6.0f}  {win:28s} {s}")


report("detect", *evs)
for label, (rule, objective) in VARIANTS.items():
    e1, e2 = (refit(e, rule, objective) for e in evs)
    for k, e in enumerate((e1, e2), 1):
        json.dump(e.to_dict(), open(out / f"{name}_{label}_ev{k}.json", "w"), indent=1)
    report(label, e1, e2)
