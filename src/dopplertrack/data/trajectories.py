"""The Trace: one aircraft's ADS-B track from an adsb.lol / readsb `globe_history` archive."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dopplertrack.core.geometry import lla_to_enu
from dopplertrack.core.propagation import MAX_TRACE_GAP_S


@dataclass
class Trace:
    icao: str
    reg: str | None
    typ: str | None
    desc: str | None
    t: np.ndarray        # unix seconds
    lat: np.ndarray
    lon: np.ndarray
    alt: np.ndarray      # metres: WGS-84 ellipsoidal when geometric, else pressure altitude
    gs: np.ndarray       # m/s (nan if missing)
    on_ground: np.ndarray
    alt_source: np.ndarray | None = None       # geometric, barometric, none; unknown for legacy files
    position_source: np.ndarray | None = None  # readsb slot 9 (adsb_icao, mlat, tisb_icao, ...)
    flags: np.ndarray | None = None            # slot 6; bit 1 fix after reception gap, bit 2 new leg, bit 8 geometric height

    def __len__(self):
        return len(self.t)

    def valid_positions(self):
        """Airborne points with usable coordinates and altitude.

        readsb's stale bit describes the gap *before* this new reliable fix;
        it does not invalidate the fix (readsb track.c, seenPosReliable).
        """
        return (~self.on_ground & np.isfinite(self.alt) & np.isfinite(self.lat) & np.isfinite(self.lon))

    def break_indices(self, max_gap_s: float):
        """Shared boundaries for geometry segments and coverage diagnostics."""
        flags = self.flags if self.flags is not None else np.zeros(len(self.t), int)
        valid = self.valid_positions()
        return np.flatnonzero((np.diff(self.t) > max_gap_s) | (valid[1:] != valid[:-1])
                              | ((flags[1:] & 2) != 0)) + 1

    def segments(self, max_gap_s: float = 90.0) -> list[slice]:
        """Airborne geometry runs; resampling separately masks ADS-B observation gaps over 30 s.

        Keeping the 90 s geometry bound allows a CPA proposal inside a short
        reception hole without treating interpolated positions in that hole as observed.
        """
        out = []
        if len(self.t) == 0:
            return out
        valid = self.valid_positions()
        brk = self.break_indices(max_gap_s)
        starts = np.r_[0, brk]; ends = np.r_[brk, len(self.t)]
        for s, e in zip(starts, ends):
            if e - s >= 2 and valid[s]:
                out.append(slice(s, e))
        return out

    def coverage_gaps(self, max_gap_s: float = MAX_TRACE_GAP_S):
        """Interior observation holes bracketed by usable airborne points.

        Uses the same validity and boundary rules as segments(), with the
        stricter observation gap bound. Known ground intervals are not holes.
        """
        points = np.flatnonzero(self.valid_positions())
        boundaries = np.zeros(len(self.t), int)
        boundaries[self.break_indices(max_gap_s)] = 1
        boundaries = np.cumsum(boundaries)
        ground = np.cumsum(self.on_ground)
        flags = self.flags if self.flags is not None else np.zeros(len(self.t), int)
        legs = np.cumsum((flags & 2) != 0)
        left, right = points[:-1], points[1:]
        missing = (boundaries[right] != boundaries[left]) & (ground[right] == ground[left])
        for left, right in zip(left[missing], right[missing]):
            reasons = []
            if self.t[right] - self.t[left] > max_gap_s:
                reasons.append("time gap")
            if right > left + 1:
                reasons.append("missing position/altitude")
            if legs[right] != legs[left]:
                reasons.append("new leg")
            yield left, right, ", ".join(reasons)

    def resample(self, sl: slice, dt: float = 1.0, *, return_valid=False):
        """Resample geometry; optionally retain the original observations' support mask.

        Interpolated coordinates across 30–90 s holes serve CPA proposals only.
        The mask prevents modelled curves from scoring those coordinates.
        """
        t = self.t[sl]
        tq = np.arange(t[0], t[-1], dt)
        result = (tq, np.interp(tq, t, self.lat[sl]), np.interp(tq, t, self.lon[sl]), np.interp(tq, t, self.alt[sl]))
        if not return_valid:
            return result
        idx = np.clip(np.searchsorted(t, tq, side="right") - 1, 0, len(t) - 2)
        valid = ((t[idx + 1] - t[idx] <= MAX_TRACE_GAP_S)
                 | (tq == t[idx]) | (tq == t[idx + 1]))
        return (*result, valid)

    def enu(self, sl: slice, lat0: float, lon0: float, dt: float = 1.0, *, return_valid=False):
        tq, la, lo, al, valid = self.resample(sl, dt, return_valid=True)
        result = (tq, lla_to_enu(la, lo, al, lat0, lon0))
        return (*result, valid) if return_valid else result
