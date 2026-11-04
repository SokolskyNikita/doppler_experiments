"""Doppler curve physics.

All functions use *emission-time* kinematics: the frequency heard at
observation time t_obs was produced at emission time t_e where
t_obs = t_e + r(t_e)/c, and the shift is set by the range rate at t_e.
"""
from __future__ import annotations

import numpy as np

MAX_TRACE_GAP_S = 30.0


def speed_of_sound(temp_c: float = 15.0) -> float:
    return 331.3 * np.sqrt(1.0 + temp_c / 273.15)


LAPSE_C_PER_KM = 6.5       # the standard atmosphere's lapse rate


def mid_height_temperature(ground_c: float, aircraft_height_m: float) -> float:
    """The air temperature halfway up a slant path to an aircraft at this height above the ground, which the
    path's harmonic-mean sound speed follows to about 0.2 % (PLAN Phase 2 item 2): ground - 3.25 C per km.
    Winter inversions, which a station can't see, are the exception."""
    return ground_c - LAPSE_C_PER_KM / 2 * aircraft_height_m / 1000.0


def observed_frequency(f0, range_rate, c):
    """Frequency heard for a source of rest frequency f0 with range rate dr/dt
    (positive = receding)."""
    return f0 * c / (c + range_rate)


def ideal_curve(t_obs, f0, v, d_cpa, t_cpa, c=None, span=600.0, n=4001):
    """Frequency heard at times t_obs for a straight, constant-speed pass.

    v: speed (m/s); d_cpa: slant distance at closest approach (m);
    t_cpa: *emission* time of closest approach.
    """
    c = speed_of_sound() if c is None else c
    te = t_cpa + np.linspace(-span, span, n)
    r = np.sqrt(d_cpa**2 + (v * (te - t_cpa)) ** 2)
    rr = v * v * (te - t_cpa) / r
    f = observed_frequency(f0, rr, c)
    tobs = te + r / c
    return np.interp(np.asarray(t_obs, float), tobs, f, left=np.nan, right=np.nan)


def ideal_curve_params_from_endpoints(f_pre, f_post, c=None):
    """Recover (f0, v) from the approach and recede asymptote frequencies."""
    c = speed_of_sound() if c is None else c
    # f_pre = f0 c/(c-v), f_post = f0 c/(c+v)
    v = c * (f_pre - f_post) / (f_pre + f_post)
    f0 = f_pre * (c - v) / c
    return f0, v


def curve_from_trajectory(t_e, pos_enu, obs_enu, f0=1.0, c=None, *, return_valid=False,
                          max_gap_s=MAX_TRACE_GAP_S, sample_valid=None):
    """Doppler curve a stationary observer hears from a sampled trajectory.

    t_e: (N,) emission times (s); pos_enu: (N,3) source positions (m);
    obs_enu: (3,) observer position (m). Returns (t_obs, f, r) with f for
    rest frequency f0 (use f0=1 to get the ratio). With return_valid=True a
    fourth array is the validity mask; invalid frequencies and ranges are NaN.

    The forward map t_obs = t_e + r/c solves the retarded-time relation
    directly, without an inverse solver. sample_valid carries the original
    observations' support through resampling: interpolated geometry can propose
    a CPA but cannot supply evidence in a gap. Derivatives never cross invalid
    samples or emission-time gaps above max_gap_s (30 s by default).
    """
    c = speed_of_sound() if c is None else c
    t_e = np.asarray(t_e, float)
    if len(t_e) < 2 or not np.all(np.isfinite(t_e)) or not np.all(np.diff(t_e) > 0):
        raise ValueError("trajectory needs at least two finite, strictly increasing emission times")
    if not np.isfinite(c) or c <= 0 or not np.isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError("sound speed and maximum trace gap must be finite and positive")
    d = np.asarray(pos_enu, float) - np.asarray(obs_enu, float)
    r = np.linalg.norm(d, axis=-1)
    finite = np.isfinite(r)
    if sample_valid is not None:
        sample_valid = np.asarray(sample_valid, bool)
        if sample_valid.shape != t_e.shape:
            raise ValueError("sample_valid must have one value per trajectory sample")
        finite &= sample_valid
    # Differentiate each supported run separately; even the boundary velocities
    # must not depend on samples on the other side of a gap or missing position.
    breaks = np.flatnonzero((np.diff(t_e) > max_gap_s) | ~finite[:-1] | ~finite[1:]) + 1
    rr = np.full_like(r, np.nan)
    for start, end in zip(np.r_[0, breaks], np.r_[breaks, len(t_e)]):
        if end - start >= 2 and finite[start:end].all():
            rr[start:end] = np.gradient(r[start:end], t_e[start:end])
    valid = finite & np.isfinite(rr) & (c + rr > 0)
    # A missing position has no observation-time coordinate. Mask its neighbours
    # too so removing that coordinate downstream cannot join the two sides.
    valid[:-1] &= finite[1:]
    valid[1:] &= finite[:-1]
    gaps = np.flatnonzero(np.diff(t_e) > max_gap_s)
    valid[gaps] = False
    valid[gaps + 1] = False
    heard = t_e + r / c

    causal = np.diff(heard) > 0
    valid[:-1] &= causal
    valid[1:] &= causal
    f = np.where(valid, observed_frequency(f0, rr, c), np.nan)
    result = (heard, f, np.where(valid, r, np.nan), valid)
    return result if return_valid else result[:3]


def cpa_from_trajectory(t_e, pos_enu, obs_enu, c=None):
    """Closest point of approach: (t_cpa_emission, t_cpa_heard, slant_m, speed_mps)."""
    c = speed_of_sound() if c is None else c
    t_e = np.asarray(t_e, float)
    d = np.asarray(pos_enu, float) - np.asarray(obs_enu, float)
    r = np.linalg.norm(d, axis=-1)
    i = int(np.argmin(r))
    vel = np.gradient(np.asarray(pos_enu, float), t_e, axis=0)
    speed = float(np.linalg.norm(vel[i]))
    return float(t_e[i]), float(t_e[i] + r[i] / c), float(r[i]), speed
