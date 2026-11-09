import numpy as np
import pytest

from dopplertrack.core import propagation as doppler
from dopplertrack.core import geometry as geo


def test_enu_round_trip():
    lat0, lon0 = 40.8765, -73.525
    lat, lon, alt = 40.95, -73.40, 1500.0
    e, n, u = geo.lla_to_enu(lat, lon, alt, lat0, lon0)
    la, lo, al = geo.enu_to_lla(e, n, u, lat0, lon0)
    assert la == pytest.approx(lat, abs=1e-8)
    assert lo == pytest.approx(lon, abs=1e-8)
    assert al == pytest.approx(alt, abs=1e-3)
    # ~10 km NE, altitude ~1.5 km
    assert 8000 < np.hypot(e, n) < 14000
    assert 1400 < u < 1500 + 20


def test_enu_matches_haversine_horizontally():
    lat0, lon0 = 40.0, -74.0
    lat, lon = 40.05, -74.0
    e, n, u = geo.lla_to_enu(lat, lon, 0.0, lat0, lon0)
    assert n == pytest.approx(geo.haversine_m(lat0, lon0, lat, lon), rel=2e-3)
    assert abs(e) < 1.0


def test_ideal_curve_limits_and_symmetry():
    c = 340.0
    f0, v, d, t0 = 130.0, 112.0, 3460.0, 1000.0
    t = np.linspace(t0 - 500, t0 + 500, 2001)
    f = doppler.ideal_curve(t, f0, v, d, t0, c=c)
    assert np.nanmax(f) == pytest.approx(f0 * c / (c - v), rel=1e-3)
    assert np.nanmin(f) == pytest.approx(f0 * c / (c + v), rel=1e-3)
    # monotonically decreasing
    assert np.all(np.diff(f[np.isfinite(f)]) <= 1e-9)
    # at the *heard* CPA (t0 + d/c) the frequency equals f0
    assert doppler.ideal_curve([t0 + d / c], f0, v, d, t0, c=c)[0] == pytest.approx(f0, rel=1e-4)


def test_endpoints_invert():
    c = 340.0
    f0, v = 131.5, 112.0
    fpre, fpost = f0 * c / (c - v), f0 * c / (c + v)
    f0b, vb = doppler.ideal_curve_params_from_endpoints(fpre, fpost, c=c)
    assert f0b == pytest.approx(f0) and vb == pytest.approx(v)


def test_trajectory_curve_matches_closed_form_for_straight_pass():
    c = 340.0
    f0, v, d, t0 = 130.0, 100.0, 3000.0, 500.0
    te = np.arange(0, 1000, 1.0)
    # straight east-bound pass with CPA slant distance d (altitude 1800, lateral 2400)
    pos = np.stack([v * (te - t0), np.full_like(te, 2400.0), np.full_like(te, 1800.0)], -1)
    obs = np.zeros(3)
    tobs, f, r = doppler.curve_from_trajectory(te, pos, obs, f0=f0, c=c)
    ref = doppler.ideal_curve(tobs[5:-5], f0, v, d, t0, c=c)
    assert np.nanmax(np.abs(f[5:-5] - ref)) < 0.05


def test_emission_time_delay_shifts_curve_not_just_in_time():
    """Plotting f against emission time (the naive method) differs from plotting
    it against observation time by more than a pure time shift."""
    c = 340.0
    f0, v, t0 = 130.0, 110.0, 500.0     # CPA 2000 m north and 2236 m up: 3 km slant
    te = np.arange(0, 1000, 0.5)
    pos = np.stack([v * (te - t0), np.full_like(te, 2000.0), np.full_like(te, 2236.0)], -1)
    tobs, f, r = doppler.curve_from_trajectory(te, pos, np.zeros(3), f0=f0, c=c)
    tq = np.arange(300, 700, 0.5)
    right = np.interp(tq, tobs, f)
    best = min(np.max(np.abs(np.interp(tq - s, te, f) - right)) for s in np.arange(0, 20, 0.25))
    assert best > 0.5


def test_cpa_from_trajectory():
    te = np.arange(0, 600, 1.0)
    pos = np.stack([100.0 * (te - 300), np.full_like(te, 3000.0), np.full_like(te, 1000.0)], -1)
    tcpa, theard, slant, speed = doppler.cpa_from_trajectory(te, pos, np.zeros(3), c=340.0)
    assert tcpa == 300.0
    assert slant == pytest.approx(np.hypot(3000, 1000))
    assert theard == pytest.approx(300 + slant / 340.0)
    assert speed == pytest.approx(100.0)


def test_trajectory_mask_does_not_bridge_a_gap_over_30_seconds():
    te = np.r_[np.arange(0, 61), np.arange(100, 161)].astype(float)
    pos = np.stack([100 * (te - 80), np.full_like(te, 3000), np.zeros_like(te)], -1)
    to, f, r, valid = doppler.curve_from_trajectory(te, pos, np.zeros(3), c=340, return_valid=True)
    assert not valid[60] and not valid[61]
    assert np.isnan(f[60:62]).all() and np.isnan(r[60:62]).all()


def test_forward_trajectory_mask_rejects_missing_positions():
    te = np.arange(10, dtype=float)
    pos = np.stack([100 * te, np.full_like(te, 3000), np.zeros_like(te)], -1)
    pos[5] = np.nan
    _, f, _, valid = doppler.curve_from_trajectory(te, pos, np.zeros(3), return_valid=True)
    assert not valid[4:7].any() and np.isnan(f[4:7]).all()
    assert valid[:4].all() and valid[7:].all()
