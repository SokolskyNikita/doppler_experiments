"""A physical test of the eagle cam's two best candidates (PM, after stage B's runs; development data only).

Inside the eagle cam's true-pair search (stage A, runs/2026-11-04-comparable-score/, eagle-cam-clip-18000s--d2d5), the
two best candidates score 8.342 and 8.323 in Z, sit 14.6 km apart and imply recording clocks 13 minutes apart. Each is
frozen at its location and clock (the record's audio_minus_utc_s and shift_s), and the same additional flyovers are
scored under each without readjusting the clock, as refine's --extra path does (pipeline.pick_flight: any flight
alive within 300 s whose track comes within 12 km, its modelled curve at the frozen clock, an f0 sweep of 0.95-1.05).
The 2026-11-03 extra-consistency record found pick_flight's rule too loose and a heard-CPA gate of +-15 s
informative, so that variant is reported too.

Additional flyovers: the clip's detect ranks 1, 3 and 4 (the true pair is ranks 2 and 5). Rank 1, at 820 s, is
the eagle cam's README extra flyover at full-stream 18,820 s.

usage: frozen_clock_extra.py RUN"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from bench import cases as bench_cases                                   # noqa: E402
from dopplertrack import pipeline                                        # noqa: E402
from dopplertrack.adsb import load_traces                                # noqa: E402
from dopplertrack.audio import Spectrogram                               # noqa: E402
from dopplertrack.doppler import cpa_from_trajectory, speed_of_sound     # noqa: E402
from dopplertrack.geo import lla_to_enu                                  # noqa: E402
from dopplertrack.score import EventWindow, modelled_curve               # noqa: E402
from dopplertrack.search import Grid                                     # noqa: E402
from dopplertrack.terrain import Terrain                                 # noqa: E402
from dopplertrack.tracks import EventFit                                 # noqa: E402

import os                                                                # noqa: E402
DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
CASE = "eagle-cam-clip-18000s"
RECORD = DATA / "runs/2026-11-04-comparable-score" / f"{CASE}--d2d5" / "result.json"
DETECTED = DATA / "runs/2026-11-04-bench-5314396-raw-audio-t2" / CASE / "detected.json"
EXTRA_RANKS = (1, 3, 4)
GATE_S = 15.0


def main(run: Path):
    case = next(c for c in bench_cases.load_cases()["cases"] if c["id"] == CASE)
    s = case["search"]
    c = speed_of_sound()
    sp = Spectrogram.load(DATA / case["spectrogram"])
    traces = load_traces(DATA / case["flight_data"]["traces"])
    grid = Grid.make(*s["bbox"], s["spacing_m"], None)                 # only for its origin, as the search's
    segs = pipeline.segments_for_search(traces, tuple(s["bbox"]), grid.lat0, grid.lon0, max_range_m=s["max_range_m"])
    elev = Terrain().elevation
    record = json.loads(RECORD.read_text())
    det = sorted(json.loads(DETECTED.read_text()), key=lambda e: -e["score"])
    extras = {r: EventFit(**{k: v for k, v in det[r - 1].items() if k in EventFit.__dataclass_fields__}) for r in EXTRA_RANKS}
    out = {"record": str(RECORD), "extras": {r: e.to_dict() for r, e in extras.items()}, "candidates": []}
    for cand in record["candidates"][:2]:
        lat, lon = cand["lat"], cand["lon"]
        el = float(elev(np.array([lat]), np.array([lon]))[0])
        obs = lla_to_enu(lat, lon, el, grid.lat0, grid.lon0)
        shift = cand["clock"]["shift_s"]
        t0_map = cand["clock"]["audio_minus_utc_s"] - shift
        row = {"rank": cand["rank"], "lat": lat, "lon": lon, "flights": cand["flights"], "z": cand["score"],
               "audio_minus_utc_s": cand["clock"]["audio_minus_utc_s"], "extras": {}}
        for r, ev in extras.items():
            k, sc = pipeline.pick_flight(sp, ev, segs, obs, t0_map, shift, 1, c, max_range_m=s["max_range_m"])
            # the +-15 s variant: flights whose heard CPA at this point, at the frozen clock, is within 15 s of the event's
            w = EventWindow.from_fit(sp, ev, 1)
            best = (-1, 0.0, None)
            for j, seg in enumerate(segs):
                if np.linalg.norm(seg.enu - obs, axis=1).min() > s["max_range_m"]:
                    continue
                _, t_heard, _, _ = cpa_from_trajectory(seg.t, seg.enu, obs, c=c)
                if abs(t_heard + t0_map + shift - ev.t_cpa) > GATE_S:
                    continue
                to, ratio = modelled_curve(seg, obs, c)
                v = float(w.sweep_scores(to + t0_map, ratio, [shift], np.arange(0.95, 1.0501, 0.005)).max())
                if v > best[1]:
                    best = (j, v, float(t_heard + t0_map + shift - ev.t_cpa))
            row["extras"][r] = {"pick_flight": {"flight": segs[k].icao if k >= 0 else None, "score": sc},
                                "gated_15s": {"flight": segs[best[0]].icao if best[0] >= 0 else None, "score": best[1],
                                              "heard_offset_s": best[2]}}
        out["candidates"].append(row)
        print(json.dumps({k: row[k] for k in ("rank", "flights", "z")}), json.dumps(row["extras"]), flush=True)
    (run / "frozen_clock_extra.json").write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
