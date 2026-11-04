"""Each flight's own effective sound speed from the ground temperature and its height (PLAN Phase 2, item 2)."""
import numpy as np
import pandas as pd
import pytest

from dopplertrack import atmosphere, doppler, search
from dopplertrack.score import modelled_curve
from dopplertrack.search import Grid, Segment


def _overhead(height_m):
    """A straight flight at 100 m/s passing directly over the origin at this height, its CPA at t = 1e9 + 300."""
    t = 1e9 + np.arange(0, 600, 1.0)
    enu = np.stack([100.0 * (t - t[300]), np.zeros_like(t), np.full_like(t, height_m)], -1)
    return Segment(0, "abc123", t, enu, np.full_like(t, 100.0))


def test_a_flight_at_5_km_is_heard_later_by_the_mid_height_rule():
    ground = 25.0
    c_ground = doppler.speed_of_sound(ground)
    c_mid = doppler.speed_of_sound(ground - 3.25 * 5.0)              # 8.75 C halfway up a 5 km path
    expected = 5000.0 / c_mid - 5000.0 / c_ground                    # about 0.41 s later
    assert expected == pytest.approx(0.41, abs=0.02)
    grid = Grid.points([40.0], [-74.0], [0.0])
    seg = _overhead(5000.0)
    at_c = search.cpa_table(grid, [seg], 12000.0, c_ground, workers=1)
    per_point = search.cpa_table(grid, [seg], 12000.0, c_ground, workers=1, temperature_c=ground)
    assert per_point.t_emit[0] == at_c.t_emit[0] and per_point.d[0] == at_c.d[0]
    assert per_point.t_heard[0] - at_c.t_heard[0] == pytest.approx(expected, abs=1e-6)
    # the modelled curve agrees: its heard CPA (the f0 crossing) moves by the same amount
    t1, r1 = modelled_curve(seg, np.zeros(3), c_ground)
    t2, r2 = modelled_curve(seg, np.zeros(3), c_ground, temperature_c=ground)
    cross = [np.interp(1.0, rr[::-1][np.isfinite(rr[::-1])], tt[::-1][np.isfinite(rr[::-1])]) for tt, rr in ((t1, r1), (t2, r2))]
    assert cross[1] - cross[0] == pytest.approx(expected, abs=0.01)


def test_each_point_uses_its_own_height():
    heights = np.array([0.0, 1100.0, 5500.0])
    c = atmosphere.point_sound_speed(15.0, heights)
    assert c[0] == doppler.speed_of_sound(15.0) and c[2] < c[1] < c[0]
    assert c[2] / c[0] == pytest.approx(doppler.speed_of_sound(15 - 3.25 * 5.5) / doppler.speed_of_sound(15.0))
    assert 1 - c[2] / c[0] == pytest.approx(0.0315, abs=0.001)          # 17.9 C cooler halfway up 5.5 km: 3.2 %


def test_without_a_temperature_nothing_changes():
    grid = Grid.points([40.0, 40.01], [-74.0, -74.0], [0.0, 30.0])
    seg = _overhead(1500.0)
    a = search.cpa_table(grid, [seg], 12000.0, 340.0, workers=1)
    b = search.cpa_table(grid, [seg], 12000.0, 340.0, workers=1, temperature_c=None)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    fp = search.cpa_fingerprint(grid, [seg], 12000.0, 340.0)
    assert search.cpa_fingerprint(grid, [seg], 12000.0, 340.0, None) == fp
    assert search.cpa_fingerprint(grid, [seg], 12000.0, 340.0, 25.0) != fp
    assert search.cpa_fingerprint(grid, [seg], 12000.0, 340.0, 25.0) != search.cpa_fingerprint(grid, [seg], 12000.0, 340.0, 20.0)
