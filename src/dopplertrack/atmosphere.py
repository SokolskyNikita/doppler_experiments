"""The air the sound crosses: the temperature that sets its speed (PLAN Phase 2 item 2).

Kept apart from doppler.py, whose source keys the detection and fit caches, so changes here don't invalidate them."""
from __future__ import annotations

import numpy as np

LAPSE_C_PER_KM = 6.5       # the standard atmosphere's lapse rate


def mid_height_temperature(ground_c: float, aircraft_height_m: float) -> float:
    """The air temperature halfway up a slant path to an aircraft at this height above the ground, which the
    path's harmonic-mean sound speed follows to about 0.2 %: ground - 3.25 C per km. Winter inversions, which a
    station can't see, are the exception."""
    return ground_c - LAPSE_C_PER_KM / 2 * aircraft_height_m / 1000.0


def point_sound_speed(ground_c: float, height_m):
    """Effective sound speed from emission points at these heights above the microphone (arrays welcome): the
    speed at the mid-height temperature, ground - 3.25 C per km. It stands in for the straight path's harmonic
    mean, which it follows to about 0.2 % under a standard lapse. One ground temperature serves every flight;
    each flight's own height sets its c (PLAN Phase 2, item 2)."""
    from .doppler import speed_of_sound
    return speed_of_sound(mid_height_temperature(ground_c, np.asarray(height_m, float)))
