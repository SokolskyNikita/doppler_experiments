"""CPA tables and terrain tiles are cached on disk and may be shared by several processes: a cached table
must only be reused for identical inputs, and no reader may see a file that is still being written."""
import io

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from dopplertrack.methods.grid_pair import pipeline
from dopplertrack.components.search import grid as search
from dopplertrack.data import terrain
from dopplertrack.data.trajectories import Trace
from dopplertrack.core.geometry import enu_to_lla
import dopplertrack.components.search.cpa_storage as cpa_storage
import dopplertrack.components.search.cpa_table as cpa_table
import dopplertrack.components.search.segments as segments

LAT0, LON0 = 40.0, -74.0


def _setup(elev=0.0, dx=0.0, dt=0.0):
    """A 1 km grid and one flight passing 2 km north of it at 1 km; elev, dx and dt change contents only."""
    t = 1e9 + dt + np.arange(0, 600, 5.0)
    enu = np.stack([100.0 * (t - t[0]) - 30000 + dx, np.full_like(t, 2000.0), np.full_like(t, 1000.0)], -1)
    lat, lon, alt = enu_to_lla(enu[:, 0], enu[:, 1], enu[:, 2], LAT0, LON0)
    traces = [Trace("abc123", None, "C172", "test", t, lat, lon, alt, np.full_like(t, 194.0), np.zeros(len(t), bool))]
    grid = search.Grid.make(LAT0 - 0.02, LAT0 + 0.02, LON0 - 0.03, LON0 + 0.03, 1000.0, lambda la, lo: np.full_like(la, elev))
    return grid, segments.build_segments(traces, grid.lat0, grid.lon0)


def test_fingerprint_follows_contents_not_sizes():
    grid, segs = _setup()
    fp = cpa_storage.cpa_fingerprint(grid, segs, 12000, 340.0)
    assert cpa_storage.cpa_fingerprint(*_setup(), 12000, 340.0) == fp
    for changed in (_setup(elev=50.0), _setup(dx=10.0), _setup(dt=1.0)):   # DEM on, a position moved, times shifted
        assert len(changed[0]) == len(grid) and len(changed[1][0].t) == len(segs[0].t)
        assert cpa_storage.cpa_fingerprint(*changed, 12000, 340.0) != fp
    assert cpa_storage.cpa_fingerprint(grid, segs, 10000, 340.0) != fp
    assert cpa_storage.cpa_fingerprint(grid, segs, 12000, 343.0) != fp


def test_cached_table_is_reused_only_for_identical_inputs(tmp_path, monkeypatch):
    built = []
    real = pipeline.cpa_table
    monkeypatch.setattr(pipeline, "cpa_table", lambda *a, **k: built.append(1) or real(*a, **k))
    path = tmp_path / "cpa.npz"
    first = pipeline.cached_cpa_table(*_setup(), 12000, 340.0, path)
    again = pipeline.cached_cpa_table(*_setup(), 12000, 340.0, path)
    assert len(first) > 0 and len(built) == 1
    pd.testing.assert_frame_equal(first, again)
    pipeline.cached_cpa_table(*_setup(elev=50.0), 12000, 340.0, path)    # a DEM run after a no-DEM run
    assert len(built) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cpa.npz", "cpa.npz.lock"]


def test_unreadable_cache_file_is_a_miss(tmp_path):
    path = tmp_path / "cpa.npz"
    path.write_bytes(b"cut short")
    assert cpa_storage.load_cpa_table(path, "fp") is None


def test_failed_save_leaves_nothing_behind(tmp_path, monkeypatch):
    def fails_part_way(file, **arrays):
        open(file, "wb").write(b"partial")
        raise OSError("disk full")
    monkeypatch.setattr(search.np, "savez", fails_part_way)
    with pytest.raises(OSError):
        cpa_storage.save_cpa_table(tmp_path / "cpa.npz", cpa_table.empty_cpa_table(), "fp")
    assert list(tmp_path.iterdir()) == []


def test_unreadable_tile_is_fetched_again(tmp_path, monkeypatch):
    png = io.BytesIO()
    Image.new("RGB", (256, 256), (128, 0, 0)).save(png, "PNG")       # Terrarium for 0 m

    class Resp:
        content = png.getvalue()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(terrain.requests, "get", lambda url, timeout=0: Resp())
    t = terrain.Terrain(cache_dir=tmp_path)
    t._path(1, 2).write_bytes(b"cut short")
    assert np.allclose(t._tile(1, 2), 0.0)
    assert [p.name for p in t.cache.iterdir()] == ["1_2.png"]


def _reachable(roots, modules):
    """(module, name) of every top-level definition in `modules` that the roots can reach, by following each name a
    definition reads to a definition of its own module or to one imported from another listed module."""
    import ast
    import importlib.util
    from pathlib import Path
    trees = {m: ast.parse(Path(importlib.util.find_spec(m).origin).read_text()) for m in modules}
    defs = {m: {n.name: n for n in t.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))} for m, t in trees.items()}
    imports = {m: {} for m in modules}
    for m, t in trees.items():
        for n in t.body:
            if isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").startswith("dopplertrack."):
                src = n.module
                for alias in n.names:
                    imports[m][alias.asname or alias.name] = (src, alias.name)
    seen, todo = set(), list(roots)
    while todo:
        m, name = todo.pop()
        if (m, name) in seen or m not in defs or name not in defs[m]:
            continue
        seen.add((m, name))
        for n in ast.walk(defs[m][name]):
            if isinstance(n, ast.Name):
                if n.id in defs[m]:
                    todo.append((m, n.id))
                elif n.id in imports[m]:
                    todo.append(imports[m][n.id])
    return seen


def test_the_detector_code_key_lists_everything_detect_and_fit_can_reach():
    from dopplertrack.runtime.cache import DETECTOR_CODE
    reach = _reachable([("dopplertrack.components.detection.grid_scan", "detect_events"),
                        ("dopplertrack.components.detection.event_fit", "fit_event")],
                       list(DETECTOR_CODE))
    listed = {(m, n) for m, names in DETECTOR_CODE.items() for n in names}
    assert ("dopplertrack.components.detection.grid_search", "grid_search") in reach     # the trace follows imports
    assert reach <= listed, f"add to DETECTOR_CODE: {sorted(reach - listed)}"


def test_the_code_key_ignores_docstrings_and_messages_but_not_code_or_constants(tmp_path, monkeypatch):
    import importlib
    import sys
    from dopplertrack.runtime.cache import code_sha256
    monkeypatch.syspath_prepend(str(tmp_path))

    def key(src):
        (tmp_path / "kmod.py").write_text(src)
        importlib.invalidate_caches()
        sys.modules.pop("kmod", None)
        return code_sha256({"kmod": ("f",)})
    base = key('K = 2\n\ndef f(x):\n    """Doc."""\n    if x < 0:\n        raise ValueError(f"bad {x}")\n    return K * x\n')
    assert key('K = 2\n\ndef f(x):\n    """Another doc."""\n    if x < 0:\n        raise ValueError(f"x must be >= 0, got {x}")\n    return K * x  # a comment\n') == base
    assert key('K = 2\n\ndef f(x):\n    """Doc."""\n    if x < 0:\n        raise ValueError(f"bad {x}")\n    return K * x + 1\n') != base
    assert key('K = 3\n\ndef f(x):\n    """Doc."""\n    if x < 0:\n        raise ValueError(f"bad {x}")\n    return K * x\n') != base
