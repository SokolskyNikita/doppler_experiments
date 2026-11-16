"""Write the synthetic study fixture (research readiness R6): a known scene, its cases and a study file.

One 30-minute recording at a known receiver: noise and the Doppler tones of two flights that pass it (the scene of
tests/test_collective.py), with those flights' traces for the recording's day and other flights for two control
days. OUT gets rec.npz (the spectrogram), traces/<day>/scene.npz, cases.json and study.json, every path absolute, so
the fixture runs wherever it is written: a test's temporary folder, or a fleet box's run folder (R8). Nothing here is
real data, and nothing of it says anything about accuracy.

The cases: synthetic-a and synthetic-b (the scene in two boxes), and synthetic-broken, whose spectrogram does not
exist, so its runs fail. The study: the collective recipe with reduced detection and null settings (a few seconds
per case), two variants, and both control days for every case.

usage: uv run python tools/data/synthetic_study.py OUT"""
import datetime
import json
import sys
from pathlib import Path

import numpy as np

T0 = 1_700_000_000.0                       # the recording's first sample: 2023-11-14T22:13:20Z
DAY = "2023-11-14"
CONTROL_DAYS = ("2023-11-12", "2023-11-13")
LAT0, LON0 = 40.8765, -73.525              # the receiver
C = 340.0
BASELINE = {"speed_of_sound_m_s": C, "scoring.f0_span": 0.04, "null.null_n": 60,
            "detection.band_hz": [90.0, 180.0], "detection.top": 4, "detection.refine": False,
            "detection.speed_grid_mps": [40.0, 170.0, 19.0], "detection.slant_range_grid_m": [400.0, 9000.0, 7]}


def _trace(icao, t, enu, gs):
    from dopplertrack.core.geometry import enu_to_lla
    from dopplertrack.data.trajectories import Trace
    lat, lon, alt = enu_to_lla(enu[:, 0], enu[:, 1], enu[:, 2], LAT0, LON0)
    return Trace(icao, None, "C172", "synthetic", t, lat, lon, alt, np.full_like(t, gs), np.zeros(len(t), bool))


def scene_traces(start: float = T0):
    """The two flights the receiver hears: one eastbound 2.5 km north, one northbound in a gentle turn 3 km east."""
    t1 = start + np.arange(0, 900, 5.0)
    enu1 = np.stack([110.0 * (t1 - (start + 300)), np.full_like(t1, 2500.0), np.full_like(t1, 1500.0)], -1)
    t2 = start + np.arange(900, 1800, 5.0)
    tau = t2 - (start + 1220)
    enu2 = np.stack([3000.0 + 0.02 * tau ** 2, 95.0 * tau, np.full_like(t2, 1200.0)], -1)
    return [_trace("aaa001", t1, enu1, 110 / 0.5144), _trace("aaa002", t2, enu2, 95 / 0.5144)]


def control_traces(day: str, k: int):
    """Another day's traffic: two other flights on other tracks at other times of that day's same half hour."""
    start = datetime.datetime.fromisoformat(f"{day}T22:13:20+00:00").timestamp()
    t1 = start + np.arange(0, 900, 5.0)
    enu1 = np.stack([np.full_like(t1, -4000.0 - 500 * k), 120.0 * (t1 - (start + 520 + 60 * k)), np.full_like(t1, 2000.0)], -1)
    t2 = start + np.arange(700, 1800, 5.0)
    enu2 = np.stack([-90.0 * (t2 - (start + 1500 - 80 * k)), np.full_like(t2, -5000.0 + 400 * k), np.full_like(t2, 900.0)], -1)
    return [_trace(f"bbb{k}01", t1, enu1, 120 / 0.5144), _trace(f"bbb{k}02", t2, enu2, 90 / 0.5144)]


def recording(traces):
    """The spectrogram of what the receiver hears of `traces`: noise, and a tone of 120 and 130 Hz on each curve."""
    import dopplertrack.components.search.segments as segments
    import dopplertrack.components.stft as stft
    from dopplertrack.core import propagation as doppler
    sr = 4000
    tt = np.arange(0, 1800, 1 / sr)
    x = 0.4 * np.random.default_rng(1).standard_normal(len(tt)).astype(np.float32)
    for seg, f0 in zip(segments.build_segments(traces, LAT0, LON0), (120.0, 130.0)):
        to, ratio, _ = doppler.curve_from_trajectory(seg.t, seg.enu, np.zeros(3), f0=1.0, c=C)
        finst = np.interp(tt + T0, to, ratio, left=np.nan, right=np.nan) * f0
        m = np.isfinite(finst)
        x[m] += 0.05 * np.sin(2 * np.pi * np.cumsum(np.nan_to_num(finst, nan=0.0)) / sr)[m]
    return stft.compute_spectrogram(x, sr, nperseg=8192, hop_s=0.5, fmin=60, fmax=300, whiten_window_s=None)


def _case(cid: str, out: Path, bbox, spectrogram: Path) -> dict:
    return {
        "id": cid, "version": 1, "group": "synthetic", "set": "development", "expected_outcome": "located",
        "description": "synthetic scene of the readiness study fixture; not data", "built_with": "tools/data/synthetic_study.py",
        "source": {"identifiers": {}, "acquisition": "synthesized", "raw": []},
        "start_time": {"source": "synthesized", "utc": "2023-11-14T22:13:20Z", "uncertainty_s": 1.0},
        "audio": {"path": str(out / "none.wav"), "clip_offset_s": 0.0, "clip_offset_samples": 0, "sample_rate_hz": 4000},
        "derived": [], "spectrogram": str(spectrogram),
        "flight_data": {"date": DAY, "pod": "synthetic", "archive_assets": [],
                        "traces": str(out / "traces" / DAY / "scene.npz"), "extraction_box": list(bbox)},
        "search": {"bbox": list(bbox), "spacing_m": 500.0, "harmonics": [1, 1], "tol_s": 8.0, "v_tol": 0.35,
                   "d_tol": [0.4, 2.5], "silence_d_m": None, "max_range_m": 12000.0, "dem": False,
                   "cpa_cache": f"cpa/synthetic-study/{cid}.npz"},
        "refine": {"rank": 1, "spacing_m": 250.0, "half_m": 500.0},
        "events": {"mode": "detect"}, "profiles": ["collective"],
        "labels": {"reference": {"lat": LAT0, "lon": LON0}, "true_pair": ["aaa001", "aaa002"],
                   "checked_by": "construction"},
    }


def write(out) -> Path:
    """The fixture in `out` (created; it must be empty or absent); returns the study file's path."""
    from dopplertrack.data.region_loading import save_traces
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError(f"{out} is not empty")
    own = scene_traces()
    days = {DAY: own, **{d: control_traces(d, k) for k, d in enumerate(CONTROL_DAYS, 1)}}
    for day, traces in days.items():
        (out / "traces" / day).mkdir(parents=True)
        save_traces(traces, out / "traces" / day / "scene.npz")
    recording(own).save(out / "rec.npz")
    box_a = [LAT0 - 0.03, LAT0 + 0.03, LON0 - 0.035, LON0 + 0.035]
    box_b = [LAT0 - 0.02, LAT0 + 0.04, LON0 - 0.045, LON0 + 0.025]
    cases = [_case("synthetic-a", out, box_a, out / "rec.npz"), _case("synthetic-b", out, box_b, out / "rec.npz"),
             _case("synthetic-broken", out, box_a, out / "no-such-recording.npz")]
    (out / "cases.json").write_text(json.dumps({"schema": 1, "cases": cases}, indent=1) + "\n")
    study = {"name": "synthetic", "cases_file": str(out / "cases.json"),
             "cases": [c["id"] for c in cases], "unit_wall_s": 600, "seed": 20261115,
             "baseline": {"recipe": "collective", "profile": "collective", "parameters": BASELINE},
             "variants": {"fewer-modes": {"parameters": {"planning.max_modes": 2}},
                          "wider-tone": {"parameters": {"scoring.f0_span": 0.05}}},
             "controls": {"days": list(CONTROL_DAYS), "traces": str(out / "traces" / "{day}" / "{name}")},
             "aws": {"max_boxes": 2, "max_vcpus": 32, "size": "4xlarge", "shards": 2, "max_hours": 1}}
    (out / "study.json").write_text(json.dumps(study, indent=1) + "\n")
    return out / "study.json"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(write(sys.argv[1]))
