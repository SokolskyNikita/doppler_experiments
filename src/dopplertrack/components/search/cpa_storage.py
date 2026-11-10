"""CPA table storage: the fingerprint of its inputs and its builder's code, and atomic save and checked load."""
from __future__ import annotations

import hashlib
import os
import threading
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from dopplertrack.components.search.cpa_table import CPA_COLUMNS, cpa_table
from dopplertrack.components.search.grid import Grid
from dopplertrack.components.search.types import Segment


def cpa_fingerprint(grid: Grid, segs: list[Segment], max_range_m: float, c: float,
                    temperature_c: float | None = None, build=cpa_table) -> str:
    """SHA-256 of everything a CPA table depends on: the grid's coordinates and elevations, every segment's
    times, positions and speeds, max_range, the speed of sound (and the ground temperature, when one sets
    each CPA's own), the builder (`build`, cpa_table unless another is passed) with its code (cache.code_sha256),
    and the Python, numpy, scipy and pandas versions. Changing any of them, e.g. running with and without a DEM
    or editing the builder, changes the fingerprint even when no array changes size. The number of workers is
    not part of it."""
    from dopplertrack.runtime.cache import code_sha256, describe, producer_name, versions
    air = "" if temperature_c is None else f" ground {float(temperature_c)!r} C"
    code = f"{producer_name(build)} {code_sha256(build)} {describe(versions('numpy', 'scipy', 'pandas'))}"
    h = hashlib.sha256(f"cpa-table {code} {float(max_range_m)!r} {float(c)!r}{air} "
                       f"{float(grid.lat0)!r} {float(grid.lon0)!r} {len(grid)} {len(segs)}".encode())
    for a in (grid.lat, grid.lon, grid.elev, grid.enu):
        h.update(np.ascontiguousarray(a, np.float64).tobytes())
    for s in segs:
        h.update(f"{s.icao} {len(s.t)}".encode())
        for a in (s.t, s.enu, s.speed):
            h.update(np.ascontiguousarray(a, np.float64).tobytes())
    return h.hexdigest()


def save_cpa_table(path, cpa: pd.DataFrame, fingerprint):
    """Written under a temporary name in the same folder and renamed into place, so another process never
    reads a partial table and an interrupted save leaves nothing behind.

    Uncompressed: compressing Oyster Bay's 86M rows took 69 s on one core against 1.5 s to write them
    (874 MB against 2.76 GB), longer than building the table. load_cpa_table reads either kind."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
    try:
        np.savez(tmp, fingerprint=np.array(repr(fingerprint)), **{k: cpa[k].to_numpy() for k in CPA_COLUMNS})
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_cpa_table(path, fingerprint) -> pd.DataFrame | None:
    """Return the cached table if it was built from the same inputs, else None. A file that can't be read,
    such as one cut short by an older version, also counts as a miss."""
    try:
        with np.load(path, allow_pickle=False) as z:
            if str(z["fingerprint"]) != repr(fingerprint):
                return None
            return pd.DataFrame({k: z[k] for k in CPA_COLUMNS})
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None
