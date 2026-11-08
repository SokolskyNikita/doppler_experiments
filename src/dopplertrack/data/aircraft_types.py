"""Aircraft-type filter: ICAO Doc 8643 designators, by engine type, for keeping propeller aircraft."""
from __future__ import annotations

import csv
import os
from pathlib import Path

import requests

_DOC8643_URL = "https://opensky-network.org/datasets/metadata/doc8643AircraftTypes.csv"


def _cache_dir() -> Path:
    p = Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack"))
    p.mkdir(parents=True, exist_ok=True)
    return p


class AircraftTypes:
    """ICAO Doc 8643 designator -> engine class ('Piston', 'Turboprop', 'Jet', ...)."""

    def __init__(self, path: str | Path | None = None):
        p = Path(path) if path else _cache_dir() / "doc8643AircraftTypes.csv"
        if not p.exists():
            p.write_bytes(requests.get(_DOC8643_URL, timeout=120).content)
        self.types: dict[str, dict] = {}
        with open(p, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self.types.setdefault(row["Designator"], row)

    def engine(self, designator: str | None) -> str | None:
        r = self.types.get(designator or "")
        return r["EngineType"] if r else None

    def is_prop(self, designator: str | None, unknown_ok: bool = True) -> bool:
        """True for a piston, turboprop/turboshaft or electric engine type, so it also accepts rotorcraft
        (helicopters, gyrocopters), not only propeller aircraft; unknown designators give unknown_ok."""
        e = self.engine(designator)
        if e is None:
            return unknown_ok
        return any(k in e for k in ("Piston", "Turboprop", "Electric"))
