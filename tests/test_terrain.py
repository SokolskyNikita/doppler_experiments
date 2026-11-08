"""Terrarium no-data must never turn into a plausible observer height."""
import numpy as np
import pandas as pd
import pytest
from PIL import Image

from dopplertrack import pipeline, search, terrain
from dopplertrack.audio import Spectrogram
from dopplertrack.components.search.types import Segment
from dopplertrack.components.types import EventFit


def test_esid937_nodata_pixel_is_masked(tmp_path):
    # ESID 937 box, 37.053 N / 90.108 W: z12 tile (1022,1593), pixel (197,135).
    # Reproduce the cached pixel's (0,0,0) value without network or external data.
    t = terrain.Terrain(cache_dir=tmp_path)
    img = Image.new("RGB", (256, 256), (128, 10, 0))  # valid +10 m
    img.putpixel((197, 135), (0, 0, 0))
    img.putpixel((198, 135), (127, 255, 0))  # valid -1 m, not no-data
    img.save(t._path(1022, 1593))
    elev = t.elevation([37.053], [-90.108])
    assert np.isnan(elev[0])
    assert t._tile(1022, 1593)[135, 198] == -1
    assert t._tile(1022, 1593)[0, 0] == 10


def test_grid_excludes_missing_terrain_and_point_rejects_it():
    def elevation(lat, lon):
        el = np.full_like(lat, 20)
        el[0] = np.nan
        return el
    baseline = search.Grid.make(40, 40.01, -74, -73.99, 200)
    with pytest.warns(RuntimeWarning, match="excluding 1 grid points"):
        g = search.Grid.make(40, 40.01, -74, -73.99, 200, elevation)
    assert len(g) == len(baseline) - 1
    assert np.isfinite(g.enu).all() and np.all(g.elev == 20)
    with pytest.raises(ValueError, match="unavailable at the point"):
        search.Grid.points([40], [-74], [np.nan])
    with pytest.warns(RuntimeWarning), pytest.raises(ValueError, match="no grid points"):
        search.Grid.make(40, 40.01, -74, -73.99, 200, lambda la, lo: np.full_like(la, np.nan))


def test_refine_does_not_use_missing_centre_for_extra_flight(monkeypatch):
    # The centre can be a missing pixel even when nearby fine-grid points are valid.
    monkeypatch.setattr(search.Grid, "make", lambda *a: search.Grid.points([40], [-74], [20]))
    sp = Spectrogram(np.arange(0, 601, 0.5), np.arange(40, 251), np.zeros((211, 1202)))
    ev = EventFit(300, 297, 120, 100, 1000, 200, 400, 1, 150, 90)
    seg = Segment(0, "a", np.arange(10), np.zeros((10, 3)), np.ones(10))
    row = pd.Series(dict(lat=40, lon=-74, lat0=40, lon0=-74, seg1=0, seg2=1))
    with pytest.raises(ValueError, match="refinement centre"):
        pipeline.refine(sp, ev, ev, [seg, seg], row, extra=[ev], elevation=lambda la, lo: np.full_like(la, np.nan))
