"""detect's S1 statistic (PLAN Phase 2 item 6): a named option, S0 the default, with unit spread in noise."""
import numpy as np

import dopplertrack.components.types as components_types
import dopplertrack.components.whitening.local_median as local_median
import dopplertrack.components.detection.custom_contrast_zscore as s1_zscore
import dopplertrack.components.detection.time_reversal_surrogate as s2_reversed_null
import dopplertrack.components.stft as stft


def test_s1_is_a_named_statistic_with_unit_spread_in_noise():
    """S1 has about unit spread on noise, and rescore_z reports each event's sigma_c."""
    rng = np.random.default_rng(3)
    zs = []
    for seed in range(6):
        x = (0.4 * np.random.default_rng(seed).standard_normal(240 * 4000)).astype(np.float32)
        sp = stft.compute_spectrogram(x, 4000, fmax=450.0, whiten_window_s=None)
        ef = components_types.EventFit(t_cpa=120.0, t_cpa_emit=117.0, f0=float(rng.uniform(120, 200)), v=60.0, d=900.0,
                             t_start=60.0, t_end=180.0, score=0.0, f_pre=0.0, f_post=0.0)
        z, sigma = s1_zscore.custom_contrast_zscore(local_median.local_whiten(sp), ef, 340.0)
        assert sigma > 0
        zs.append(z)
    assert np.all(np.abs(zs) < 4)
    diag: list = []
    assert s1_zscore.custom_rescore_zscore(sp, [ef], 100.0, 250.0, c=340.0, diagnostics=diag) is not None and len(diag) == 1
    assert abs(s1_zscore.overlap_weight(0.25) - 0.254) < 0.001




def test_s2_measures_an_event_against_its_window_reversed_in_time(monkeypatch):
    x = (0.4 * np.random.default_rng(7).standard_normal(120 * 4000)).astype(np.float32)
    sp = stft.compute_spectrogram(x, 4000, fmax=300.0, whiten_window_s=None)
    ef = components_types.EventFit(t_cpa=60.0, t_cpa_emit=57.0, f0=160.0, v=60.0, d=900.0, t_start=40.0, t_end=80.0,
                         score=5.0, f_pre=0.0, f_post=0.0)
    seen = []

    def fake_fit(win, *a, **k):                                           # the search, on whatever window it is given
        seen.append(win)
        return components_types.EventFit(t_cpa=0, t_cpa_emit=0, f0=0, v=0, d=0, t_start=0, t_end=0, score=2.0, f_pre=0, f_post=0)
    monkeypatch.setattr(s2_reversed_null, "fit_event", fake_fit)
    diag: list = []
    (e,) = s2_reversed_null.rescore_surrogate(sp, [ef], 120.0, 220.0, c=340.0, diagnostics=diag)
    win = sp.crop(10.0, 110.0, 90.0, 250.0)
    assert np.array_equal(seen[0].S, win.S[:, ::-1]) and np.array_equal(seen[0].valid, win.valid[::-1])
    assert e.score == 3.0 and diag[0]["s0_reversed"] == 2.0               # D = S0 - the reversed window's maximum
    assert (e.f0, e.v, e.d) == (ef.f0, ef.v, ef.d)                        # the fit is unchanged
