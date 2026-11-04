"""cpa_table prunes track samples by tile and runs segments in a process pool; neither may change a bit
of the table that comparing every grid point with every sample gives."""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from dopplertrack import search
from dopplertrack.search import Grid, Segment


def _brute_force(grid, segs, max_range_m, c, chunk):
    """cpa_table before tile pruning and the process pool (commit 5c093cd), with the same chunks."""
    rows = []
    tree = cKDTree(grid.enu[:, :2])
    for si, s in enumerate(segs):
        step = max(1, int(max_range_m / 4 / max(np.median(s.speed), 1.0)))
        hits = tree.query_ball_point(s.enu[::step, :2], r=max_range_m * 1.05)
        m = np.unique(np.concatenate([np.asarray(h, int) for h in hits]))
        for k in range(0, len(m), chunk):
            idx = m[k:k + chunk]
            ctr = grid.enu[idx].mean(0)
            g = grid.enu[idx] - ctr
            pts = s.enu - ctr
            d2 = (g ** 2).sum(1)[:, None] + (pts ** 2).sum(1)[None, :] - 2.0 * (g @ pts.T)
            j = np.argmin(d2, axis=1)
            r = np.sqrt(np.maximum(d2[np.arange(len(idx)), j], 0.0))
            ok = (r <= max_range_m) & (j > 0) & (j < len(s.t) - 1)
            rows.append(pd.DataFrame({"gidx": idx[ok].astype(np.int32), "seg": np.int32(si),
                                      "t_emit": s.t[j[ok]], "t_heard": s.t[j[ok]] + r[ok] / c,
                                      "d": r[ok].astype(np.float32), "v": s.speed[j[ok]].astype(np.float32)}))
    return pd.concat(rows, ignore_index=True)


def _segment(t, enu):
    return Segment(0, "abc123", t, enu, np.linalg.norm(np.gradient(enu, t, axis=0), axis=1))


def _setup():
    rng = np.random.default_rng(0)
    xy = np.meshgrid(np.arange(-12000, 12001, 400.0), np.arange(-9000, 9001, 400.0))
    enu = np.stack([xy[0].ravel(), xy[1].ravel(), rng.uniform(0, 80, xy[0].size)], -1)
    grid = Grid(np.zeros(len(enu)), np.zeros(len(enu)), enu[:, 2], enu, 40.0, -74.0)
    t = 1e9 + np.arange(0, 600, 1.0)
    straight = np.stack([90.0 * (t - t[300]), np.full_like(t, 2500.0), np.full_like(t, 900.0)], -1)
    a = np.arange(120) * 2 * np.pi / 120                     # one lap's positions flown 5 times: exact ties
    orbit = np.tile(np.stack([3000 * np.cos(a) - 4000, 3000 * np.sin(a), np.full(120, 1200.0)], -1), (5, 1))
    ends = np.stack([-60.0 * (t - t[0]) + 9000, 40.0 * (t - t[0]) - 8000, np.full_like(t, 700.0)], -1)
    return grid, [_segment(t, straight), _segment(t, orbit), _segment(t[:200], ends[:200])]


def test_pruned_pooled_table_equals_brute_force():
    grid, segs = _setup()
    ref = _brute_force(grid, segs, 7000.0, 340.0, chunk=500)
    assert len(ref) > 0 and ref.seg.nunique() == 3
    for workers in (1, 2):
        got = search.cpa_table(grid, segs, 7000.0, 340.0, chunk=500, workers=workers)
        pd.testing.assert_frame_equal(got, ref, check_exact=True)
