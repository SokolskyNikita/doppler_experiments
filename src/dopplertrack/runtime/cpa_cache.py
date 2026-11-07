"""Shared CPA cache used by both independent methods."""
import contextlib
import os
import time
import pandas as pd
from dopplertrack.components.search.grid import (Grid, Segment, cpa_table, cpa_fingerprint, load_cpa_table, save_cpa_table)

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@contextlib.contextmanager
def _file_lock(path):
    """Exclusive advisory lock on `path` (created if missing). Where fcntl is unavailable this is a no-op;
    atomic saves still keep the cache consistent, at the cost of possibly computing a table twice."""
    try:
        import fcntl
    except ImportError:
        yield
        return
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def cached_cpa_table(grid: Grid, segs: list[Segment], max_range_m: float, c: float, path=None,
                     workers: int | None = None, temperature_c: float | None = None, *, build=None) -> pd.DataFrame:
    """cpa_table(), reusing the table saved at `path` if it was built from identical inputs (cpa_fingerprint).
    A lock file next to it makes a second process wait for the first instead of computing the same table."""
    build = cpa_table if build is None else build
    if not path:
        return build(grid, segs, max_range_m=max_range_m, c=c, workers=workers, temperature_c=temperature_c)
    fp = cpa_fingerprint(grid, segs, max_range_m, c, temperature_c)
    with _file_lock(f"{path}.lock"):
        if os.path.exists(path):
            cpa = load_cpa_table(path, fp)
            if cpa is not None:
                log(f"loaded CPA table from {path}")
                return cpa
            log(f"{path} was built from other inputs; recomputing")
        cpa = build(grid, segs, max_range_m=max_range_m, c=c, workers=workers, temperature_c=temperature_c)
        save_cpa_table(path, cpa, fp)
        return cpa
