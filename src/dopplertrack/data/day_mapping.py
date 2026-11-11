"""Control-day mapping: another day's traffic set on the recording's date, at the same time of day, by a shift of a
whole number of UTC days. A search that gates on the recording's stated time, or reads a clock off its winner, then
treats a control day's flights exactly as it treats the recording day's."""
from __future__ import annotations

import dataclasses
import datetime

from dopplertrack.data.trajectories import Trace


def day_shift_s(traffic_day: str, recording_day: str) -> float:
    """Seconds to add to times on traffic_day to put them on recording_day (both YYYY-MM-DD, UTC): 86400 a day."""
    a, b = (datetime.date.fromisoformat(d) for d in (traffic_day, recording_day))
    return 86400.0 * (b - a).days


def map_to_day(traces: list[Trace], traffic_day: str, recording_day: str) -> list[Trace]:
    """The traces with every time moved by day_shift_s; nothing else changes, and the input is left as it is."""
    shift = day_shift_s(traffic_day, recording_day)
    return [dataclasses.replace(tr, t=tr.t + shift) for tr in traces]
