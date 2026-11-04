"""The air the sound crosses: the temperature that sets its speed (PLAN Phase 2 item 2).

Kept apart from doppler.py, whose source keys the detection and fit caches, so changes here don't invalidate them."""
from __future__ import annotations

LAPSE_C_PER_KM = 6.5       # the standard atmosphere's lapse rate


def mid_height_temperature(ground_c: float, aircraft_height_m: float) -> float:
    """The air temperature halfway up a slant path to an aircraft at this height above the ground, which the
    path's harmonic-mean sound speed follows to about 0.2 %: ground - 3.25 C per km. Winter inversions, which a
    station can't see, are the exception."""
    return ground_c - LAPSE_C_PER_KM / 2 * aircraft_height_m / 1000.0
