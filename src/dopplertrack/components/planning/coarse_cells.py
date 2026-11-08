"""Coarse-to-fine grid search (Harvey 2018 §5.3.1, regional contraction; Axelrad 2011, Direct Positioning): the coarse
cells the fine stage visits, those within a margin of the coarse map's maximum in units of the MADN (Maronna 2019 p.32)
of its positive cells, capped. Keeping every cell within the margin, where Axelrad re-centres on the one peak, is
ours."""
from __future__ import annotations

import pandas as pd

from dopplertrack.components.nulls.robust import median_madn

MARGIN_SIGMA = 2.0            # fine cells: every coarse cell within MARGIN_SIGMA x the MADN of the map's positive Z of its maximum,
MAX_CELLS = 20                #   at most MAX_CELLS of them by Z


def keep_cells(pts_c: pd.DataFrame, margin_sigma: float = MARGIN_SIGMA,
               max_cells: int = MAX_CELLS) -> tuple[pd.DataFrame, dict]:
    """The coarse cells the fine stage visits: Z >= Z_max - margin_sigma (MARGIN_SIGMA) * sigma_c, sigma_c = MADN (1.4826 MAD) of the
    coarse map's Z over its positive cells only (the cells with any window above its null), the highest max_cells
    (MAX_CELLS) of them."""
    z = pts_c.Z.to_numpy(float)
    zmax = float(z.max())
    _, sigma = median_madn(z)
    thr = zmax - margin_sigma * sigma
    within = pts_c[pts_c.Z >= thr].sort_values("Z", ascending=False)
    keep = within.head(max_cells)
    return keep, dict(coarse_max=zmax, coarse_sigma=sigma, margin_threshold=thr, margin_cells=len(within),
                      kept_cells=len(keep), capped=len(within) > max_cells,
                      margin_reached=float(zmax - keep.Z.min()) if len(keep) else None)
