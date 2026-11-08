"""Fit-error reference: the ground truth an observer should hear from a flight's ADS-B trace (heard CPA, Doppler
inflection point at closest approach, USNA 1962, scan p. 58), and a fit's estimation errors against it."""
from __future__ import annotations

import numpy as np


def line_f0(line) -> float:
    """A straight pass's rest frequency from its entry and exit frequencies: f_in = f0 c/(c - v) and
    f_out = f0 c/(c + v) give f0 = 2 f_in f_out / (f_in + f_out), their harmonic mean. Read from a picture, so good to about 5 %."""
    a, b = float(line[0]), float(line[1])
    return 2 * a * b / (a + b)


def trajectory_reference(traces, icao: str, observer_enu, lat0, lon0, t0_unix: float, near_audio_s: float, c: float):
    """Layer 3 for one flight (PLAN 5.3): what the observer should hear from its trace, in audio seconds.
    The heard CPA, the Doppler inflection point of the modelled curve (key t_steepest_fall_s), and the slant range and ground speed at CPA, from
    the segment whose heard CPA lies nearest near_audio_s. None if the flight has no segment in range."""
    from dopplertrack.components.scoring.modelled_curve import modelled_curve
    from dopplertrack.components.scoring.doppler_inflection import doppler_inflection
    from dopplertrack.components.search.segments import build_segments
    best = None
    for seg in build_segments([t for t in traces if t.icao == icao], lat0, lon0):
        r = np.linalg.norm(seg.enu - observer_enu, axis=1)
        j = int(np.argmin(r))
        if j == 0 or j == len(r) - 1:
            continue
        heard = seg.t[j] + r[j] / c - t0_unix
        if best is None or abs(heard - near_audio_s) < abs(best["t_heard_cpa_s"] - near_audio_s):
            # placed like the search's own inflection gate: within ±60 s of the emission CPA, smoothed
            t_obs, ratio = modelled_curve(seg, observer_enu, c)
            sf = doppler_inflection(t_obs, ratio, float(seg.t[j]))
            steep = None if sf is None else float(sf - t0_unix)
            best = {"t_heard_cpa_s": float(heard), "t_steepest_fall_s": steep, "slant_range_m": float(r[j]),
                    "ground_speed_m_s": float(seg.speed[j])}
    return best


def fit_errors(fit: dict, ref: dict, c: float) -> dict:
    """A fit's errors against layer 3; Doppler inflection points are placed by the same function on both sides."""
    from dopplertrack.components.scoring.inflection_gate import fitted_inflection
    from dopplertrack.components.types import EventFit
    sf = fitted_inflection(EventFit(**fit), c)
    return {"dt_heard_s": fit["t_cpa"] - ref["t_heard_cpa_s"],
            "dt_steepest_s": None if ref["t_steepest_fall_s"] is None or sf is None else sf - ref["t_steepest_fall_s"],
            "df0_pct": 100 * (fit["f0"] - ref["f0_hz"]) / ref["f0_hz"],
            "dv_m_s": fit["v"] - ref["ground_speed_m_s"], "dd_m": fit["d"] - ref["slant_range_m"]}
