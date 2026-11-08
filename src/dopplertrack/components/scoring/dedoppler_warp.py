"""De-Dopplerization by resampling (Howell 1986 §2.1; Ramseier & Pieren 2023 §II.C.2): the recording read at the
reception times of a uniform grid of emission times. Gao 2021's Doppler-warping transform (§2.2 eq. 7) also scales
by sqrt(h'(t)) to conserve energy; this warp leaves that factor out (ours)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dopplertrack.components.scoring.resampling import lowpass, resample_at


@dataclass
class Warped:
    y: np.ndarray            # the warped signal on the emission grid, NaN outside the support
    u: np.ndarray            # emission times (the trajectory's clock), s
    max_rate: float          # largest d t_r / d u over the support (time compression, Howell 1986 §1)


def warp(x: np.ndarray, sr: int, audio_minus_traj: float, t_traj: np.ndarray, enu: np.ndarray, obs_enu: np.ndarray,
         c: float, u0: float, u1: float, valid: np.ndarray | None = None, method: str = "sinc", taps: int = 16,
         max_rate: float = 1.35, prefiltered: bool = False) -> Warped:
    """The recording x (sample 0 at audio time 0) at the reception times of emission times u0..u1 on a
    grid at sr. Trajectory times t_traj and audio time differ by audio_minus_traj (the clock).
    Positions are interpolated linearly between the trajectory's samples; an emission time is used only
    where both neighbouring samples are valid. Raises ValueError if the geometry needs a reading rate
    above max_rate. x is low-passed at sr / (2 max_rate) unless prefiltered."""
    u = u0 + np.arange(int(np.floor((u1 - u0) * sr))) / sr
    inside = (u >= t_traj[0]) & (u <= t_traj[-1])
    if valid is not None:
        j = np.clip(np.searchsorted(t_traj, u) - 1, 0, len(t_traj) - 2)
        inside &= np.asarray(valid, bool)[j] & np.asarray(valid, bool)[j + 1]
    p = np.stack([np.interp(u, t_traj, enu[:, k]) for k in range(3)], axis=1)
    r = np.linalg.norm(p - obs_enu[None, :], axis=1)
    t_r = u + r / c + audio_minus_traj
    rate = np.gradient(t_r, u)
    mr = float(np.max(rate[inside])) if inside.any() else 1.0
    if mr > max_rate:
        raise ValueError(f"geometry needs a reading rate of {mr:.3f} > {max_rate}")
    xf = x if prefiltered else lowpass(x, sr, sr / (2 * max_rate))
    y = resample_at(xf, t_r * sr, method, taps)
    y[~inside] = np.nan
    return Warped(y, u, mr)
