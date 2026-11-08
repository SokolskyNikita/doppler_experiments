"""The modelled received-frequency (Doppler) curve: the ratio f_R / f_S an observer hears from one flight segment
(Ramseier & Pieren 2023 eq. 6; emission and reception times as in Kelly & Wilson 1993 eq. 12)."""
from __future__ import annotations

import numpy as np

from dopplertrack.components.search.types import Segment
from dopplertrack.core.atmosphere import point_sound_speed
from dopplertrack.core.propagation import curve_from_trajectory


def modelled_curve(seg: Segment, obs_enu, c, temperature_c: float | None = None):
    """(t_obs unix, ratio f/f0) the observer at obs_enu hears from this segment. With a ground temperature, each
    emission sample's sound speed comes from its own height above the observer (atmosphere.point_sound_speed)."""
    if temperature_c is not None:
        c = point_sound_speed(temperature_c, seg.enu[:, 2] - np.asarray(obs_enu, float)[2])
    t_obs, ratio, r, valid = curve_from_trajectory(seg.t, seg.enu, obs_enu, f0=1.0, c=c,
                                                return_valid=True, sample_valid=seg.valid)
    return t_obs, np.where(valid, ratio, np.nan)
