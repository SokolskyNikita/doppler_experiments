"""Which propeller passes does a recording hear at its site? The known-point check of a private case's first look.

usage: known_point_site.py CASE OUT_DIR [--max-ground-m 6000] [--draws 200] [--fmax HZ --spectrogram PATH]

For every propeller or unknown-type airborne segment whose closest approach to the site, during the recording, is
within --max-ground-m of ground range: the flight's own heard curve at the site (`score.modelled_curve`, 15 C), placed
on the recording's own clock (its stated start; the audio is UTC − start), and scored as `locate` scores a window:
brightness along the curve over ±60 s of the heard CPA, swept over the tone (60–300 Hz, which covers any propeller
fundamental) and a residual shift of ±8 s. Its null is the same curve placed at --draws wrong times, at least 120 s
from the true one, inside the recording and swept the same way. A pass counts as heard when its score is above every
null draw (p < 1/draws), and z = (score − median) / (1.4826 MAD) is reported beside it.

The band is 40 Hz to --fmax (450, the pipeline's, by default). A wider band (a full-band session's band test) scores
the curve's first floor(fmax / 300) harmonics, every one of which stays in band for any tone in 60-300 Hz, on the
case's spectrogram built at that fmax (--spectrogram; session_spectrogram.py --fmax).

Everything here is relative to the site: ground and slant range, altitude above it. The per-flight table (with ICAO,
time and range) is written to OUT_DIR only, which must be under $DOPPLERTRACK_DATA/private/: with public ADS-B, a set
of (flight, time, range) triples would locate the site, so it never goes to git or a record. The summary carries
counts and range bins only.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bench import private as priv  # noqa: E402
from bench.cases import data_root, latest_case, resolve  # noqa: E402
from bench.runner import trace_paths  # noqa: E402
from dopplertrack.adsb import AircraftTypes, join_days  # noqa: E402
from dopplertrack.audio import Spectrogram  # noqa: E402
from dopplertrack.doppler import speed_of_sound  # noqa: E402
from dopplertrack.score import EventWindow, modelled_curve  # noqa: E402
from dopplertrack.search import build_segments  # noqa: E402
from dopplertrack.tracks import EventFit  # noqa: E402

F_REF = 100.0
F0_SCALES = np.arange(0.60, 3.0001, 0.01)        # 60-300 Hz around the 100 Hz reference tone
SHIFTS = np.arange(-8.0, 8.01, 0.5)
HALF_S = 60.0


def harmonics_for(fmax: float) -> int:
    """How many harmonics of a 60-300 Hz tone all fit under fmax: 1 at the pipeline's 450 Hz."""
    return max(1, int(fmax // 300))


def window(sp, t_cpa, fmax: float = 450.0):
    """An EventWindow over ±HALF_S of t_cpa covering the whole 40-fmax band (a reference tone of 100 Hz), scoring
    harmonics_for(fmax) harmonics."""
    h = harmonics_for(fmax)
    fit = EventFit(t_cpa, t_cpa, F_REF, 0.0, 0.0, t_cpa - HALF_S, t_cpa + HALF_S, 0.0, fmax / (1.25 * h), 40.0 / 0.8)
    return EventWindow.from_fit(sp, fit, harmonics=h, pad_s=0.0)


def best(ew, t_audio, ratio) -> float:
    return float(ew.sweep_scores(t_audio, ratio, SHIFTS, F0_SCALES).max())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case"); ap.add_argument("out", type=Path)
    ap.add_argument("--max-ground-m", type=float, default=6000.0); ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--fmax", type=float, default=450.0, help="the band's upper edge, Hz (default 450)")
    ap.add_argument("--spectrogram", help="the case's spectrogram at --fmax (default the case's own)")
    a = ap.parse_args()
    if not a.out.resolve().is_relative_to((data_root() / "private").resolve()):
        sys.exit(f"{a.out} is not under {data_root() / 'private'}: the per-flight table would place the site")
    case = priv.resolve_case(latest_case(a.case))
    site = priv.load_site(case["site"])
    sp = Spectrogram.load(resolve(a.spectrogram or case["spectrogram"]))
    if abs(float(sp.f[-1]) - a.fmax) > 1.0:
        sys.exit(f"the spectrogram's band ends at {sp.f[-1]:.1f} Hz, not --fmax {a.fmax:g}")
    import datetime
    start = datetime.datetime.fromisoformat(case["start_time"]["utc"].replace("Z", "+00:00")).timestamp()
    t0, t1 = start + float(sp.t[0]), start + float(sp.t[-1])
    types = AircraftTypes()
    traces = [t for t in join_days(trace_paths(case))[0] if types.is_prop(t.typ)]
    segs = build_segments(traces, site["lat"], site["lon"])
    obs = np.array([0.0, 0.0, site["elev_m"]])
    c = speed_of_sound()
    rng = np.random.default_rng(20261104)
    rows = []
    for seg in segs:
        ground = np.hypot(seg.enu[:, 0], seg.enu[:, 1])
        k = int(np.argmin(ground))
        if ground[k] > a.max_ground_m or not (t0 <= seg.t[k] <= t1):
            continue
        t_obs, ratio = modelled_curve(seg, obs, c)
        heard_utc = float(np.interp(seg.t[k], seg.t, t_obs))
        t_cpa = heard_utc - start
        if not (sp.t[0] + HALF_S <= t_cpa <= sp.t[-1] - HALF_S):
            continue
        ew = window(sp, t_cpa, a.fmax)
        score = best(ew, t_obs - start, ratio)
        null = []
        while len(null) < a.draws:
            d = rng.uniform(sp.t[0] + HALF_S, sp.t[-1] - HALF_S) - t_cpa
            if abs(d) < 120:
                continue
            null.append(best(window(sp, t_cpa + d, a.fmax), t_obs - start + d, ratio))
        null = np.array(null)
        med, mad = float(np.median(null)), float(np.median(np.abs(null - np.median(null))) * 1.4826)
        trace = traces[seg.trace_idx]
        rows.append({"icao": seg.icao, "type": trace.typ, "engine": types.engine(trace.typ),
                     "cpa_audio_s": round(t_cpa, 1), "ground_m": round(float(ground[k]), 0),
                     "slant_m": round(float(np.linalg.norm(seg.enu[k] - obs)), 0),
                     "height_m": round(float(seg.enu[k, 2] - obs[2]), 0), "score": round(score, 3),
                     "null_median": round(med, 3), "null_mad": round(mad, 3), "null_max": round(float(null.max()), 3),
                     "z": round((score - med) / mad, 2) if mad > 0 else None, "heard": bool(score > null.max())})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "known_point_passes.json").write_text(json.dumps(rows, indent=1) + "\n")   # private: never in git
    bins = [0, 1000, 2000, 3500, a.max_ground_m]       # 2 km: the ear's turboprop limit; 3.5 km: the rest's
    summary = {"case": a.case, "fmax_hz": a.fmax, "harmonics": harmonics_for(a.fmax), "passes": len(rows), "heard": sum(r["heard"] for r in rows), "draws": a.draws,
               "by_ground_range_m": [{"from": lo, "to": hi, "passes": sum(lo <= r["ground_m"] < hi for r in rows),
                                      "heard": sum(lo <= r["ground_m"] < hi and r["heard"] for r in rows)}
                                     for lo, hi in zip(bins[:-1], bins[1:])],
               "by_engine": {e: {"passes": sum(str(r["engine"]) == e for r in rows),
                                 "heard": sum(str(r["engine"]) == e and r["heard"] for r in rows)}
                             for e in sorted({str(r["engine"]) for r in rows})}}
    (a.out / "known_point_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
