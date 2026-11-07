"""Locations shared by code, data and cache; existing defaults remain valid."""
import os
from pathlib import Path


def repository_root() -> Path:
    """Find a research checkout, or use DOPPLERTRACK_REPO for an installed wheel."""
    configured = os.environ.get("DOPPLERTRACK_REPO")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not (root / "bench/cases.json").is_file():
            raise ValueError("DOPPLERTRACK_REPO must contain bench/cases.json")
        return root
    for start in (Path(__file__).resolve().parent, Path.cwd()):
        for root in (start, *start.parents):
            if (root / "bench/cases.json").is_file() and (root / "pyproject.toml").is_file():
                return root
    raise RuntimeError("Evaluation needs a checkout: set DOPPLERTRACK_REPO")


def data_root() -> Path:
    return Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data/dopplertrack"))


def cache_root() -> Path:
    return Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache/dopplertrack"))
