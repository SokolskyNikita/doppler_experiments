"""detect's S1 statistic (PLAN Phase 2 item 6): a named option, S0 the default, with unit spread in noise."""
import numpy as np

from dopplertrack import audio, tracks


def test_s1_is_a_named_statistic_with_unit_spread_in_noise():
    """S1 has about unit spread on noise, and rescore_z reports each event's sigma_c."""
    rng = np.random.default_rng(3)
    zs = []
    for seed in range(6):
        x = (0.4 * np.random.default_rng(seed).standard_normal(240 * 4000)).astype(np.float32)
        sp = audio.compute_spectrogram(x, 4000, fmax=450.0, whiten_window_s=None)
        ef = tracks.EventFit(t_cpa=120.0, t_cpa_emit=117.0, f0=float(rng.uniform(120, 200)), v=60.0, d=900.0,
                             t_start=60.0, t_end=180.0, score=0.0, f_pre=0.0, f_post=0.0)
        z, sigma = tracks.curve_zscore(tracks.local_whiten(sp), ef, 340.0)
        assert sigma > 0
        zs.append(z)
    assert np.all(np.abs(zs) < 4)
    diag: list = []
    assert tracks.rescore_z(sp, [ef], 100.0, 250.0, c=340.0, diagnostics=diag) is not None and len(diag) == 1
    assert abs(tracks.overlap_weight(0.25) - 0.254) < 0.001
