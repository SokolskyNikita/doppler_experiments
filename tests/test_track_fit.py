"""PLAN Phase 2, item 4: the least-squares straight-pass fit of a frequency track by variable projection."""
import numpy as np
import pytest
from scipy.optimize import least_squares

from dopplertrack import audio, tracks
from dopplertrack.doppler import ideal_curve

C = 340.0
PASSES = [(120.0, 100.0, 1500.0), (126.0, 103.5, 3600.0), (164.0, 54.6, 1315.0), (112.6, 139.9, 6400.0)]


def _closed_form(t, f0, v, d, tc, c=C):
    """Ferguson & Quinn 1994, eq. 15."""
    return f0 * c * c / (c * c - v * v) * (1 - v * v * (t - tc) / np.sqrt(d * d * (c * c - v * v) + v * v * c * c * (t - tc) ** 2))


def _track(f0, v, d, tc=1000.0, half=90.0, dt=0.25, noise=0.0, seed=0, harmonic=1):
    t = tc + np.arange(-half, half, dt)
    f = harmonic * _closed_form(t, f0, v, d, tc) + np.random.default_rng(seed).normal(0, noise, len(t))
    return tracks.Track(t, f, harmonic=harmonic)


@pytest.mark.parametrize("f0,v,d", PASSES)
def test_closed_form_is_the_ideal_curve(f0, v, d):
    t = 1000 + np.arange(-200, 200, 0.5)                          # ideal_curve interpolates 4,001 samples
    assert np.allclose(_closed_form(t, f0, v, d, 1000.0), ideal_curve(t, f0, v, d, 1000.0, c=C), rtol=1e-4)


@pytest.mark.parametrize("f0,v,d", PASSES)
def test_noiseless_track_is_recovered(f0, v, d):
    fit = tracks.fit_track(_track(f0, v, d, harmonic=2), c=C)
    assert fit.identified and fit.converged and not fit.at_bound
    assert fit.f0 == pytest.approx(f0, rel=1e-6) and fit.v == pytest.approx(v, rel=1e-5)
    assert fit.d == pytest.approx(d, rel=1e-4) and fit.t_cpa_emit == pytest.approx(1000.0, abs=1e-3)
    assert fit.t_cpa == pytest.approx(1000.0 + d / C, abs=1e-2)
    ev = fit.event()
    assert ev.f_pre == pytest.approx(f0 * C / (C - v), rel=1e-5)


@pytest.mark.parametrize("f0,v,d", PASSES)
@pytest.mark.parametrize("weighted", [False, True])
def test_reduced_optimum_matches_the_full_fit(f0, v, d, weighted):
    """Variable projection must reach the same optimum as fitting all four parameters directly."""
    tr = _track(f0, v, d, noise=0.4, seed=1)
    tr.amplitude = 1 + np.random.default_rng(2).uniform(0, 3, len(tr.t))
    fit = tracks.fit_track(tr, c=C, weighted=weighted)
    w = np.sqrt(tr.amplitude ** 2 / np.mean(tr.amplitude ** 2)) if weighted else np.ones_like(tr.t)
    full = least_squares(lambda p: w * (_closed_form(tr.t, *p) - tr.f),
                         [fit.f0 * 1.01, fit.v * 1.05, fit.d * 1.1, fit.t_cpa_emit + 2], xtol=1e-12, ftol=1e-12)
    assert full.success
    assert full.x[0] == pytest.approx(fit.f0, rel=1e-6) and full.x[1] == pytest.approx(fit.v, rel=1e-4)
    assert full.x[2] == pytest.approx(fit.d, rel=1e-3) and full.x[3] == pytest.approx(fit.t_cpa_emit, abs=1e-2)
    assert np.isfinite(fit.corr_v_d) and fit.corr_v_d > 0.5         # distance follows speed (6.1)
    sd = np.sqrt(np.diag(fit.cov))
    assert abs(fit.f0 - f0) < 6 * sd[0] and abs(fit.v - v) < 6 * sd[1] and abs(fit.d - d) < 6 * sd[3]


def test_amplitude_weights_discount_weak_outliers():
    f0, v, d = PASSES[0]
    tr = _track(f0, v, d, noise=0.2, seed=3)
    rng = np.random.default_rng(4)
    bad = rng.choice(len(tr.t), 60, replace=False)
    tr.f = tr.f.copy(); tr.f[bad] += rng.uniform(-25, 25, len(bad))
    tr.amplitude = np.ones_like(tr.f); tr.amplitude[bad] = 0.05
    plain, weighted = tracks.fit_track(tr, c=C), tracks.fit_track(tr, c=C, weighted=True)
    assert abs(weighted.d - d) < abs(plain.d - d) and abs(weighted.d - d) / d < 0.02


def test_a_tail_only_track_is_not_identified():
    f0, v, d = PASSES[0]
    tr = _track(f0, v, d, half=40.0)
    keep = tr.t > 1030                                              # only the receding tail, z near 1
    fit = tracks.fit_track(tracks.Track(tr.t[keep], tr.f[keep]), c=C)
    assert fit.z_span < tracks.LS_Z_SPAN_MIN and not fit.identified


def test_invalid_points_are_left_out():
    f0, v, d = PASSES[1]
    tr = _track(f0, v, d)
    tr.f = tr.f.copy(); tr.f[::7] = 0.0
    tr.valid = np.ones(len(tr.t), bool); tr.valid[::7] = False
    assert tracks.fit_track(tr, c=C).d == pytest.approx(d, rel=1e-4)
    with pytest.raises(ValueError):
        tracks.fit_track(tracks.Track(tr.t[:5], tr.f[:5]), c=C)


def test_ridge_track_follows_a_painted_pass():
    f0, v, d, tc = 120.0, 90.0, 1500.0, 200.0
    t, f = np.arange(0, 400, 0.5), np.arange(60, 201, 0.5)
    S = np.random.default_rng(0).uniform(0, 1, (len(f), len(t))).astype(np.float32)
    curve = ideal_curve(t, f0, v, d, tc, c=C)
    on = np.isfinite(curve)
    S[np.rint((curve[on] - f[0]) / 0.5).astype(int), np.flatnonzero(on)] += 10
    S[np.abs(f - 66.0) < 0.3, :] += 30                             # a strong steady line below the band
    tr = tracks.ridge_track(audio.Spectrogram(t, f, S), 120, 300, 70, 170)
    assert tr.f.min() >= 70 and tr.f.max() <= 170
    inside = np.isfinite(ideal_curve(tr.t, f0, v, d, tc, c=C))
    assert np.median(np.abs(tr.f[inside] - ideal_curve(tr.t[inside], f0, v, d, tc, c=C))) <= 0.5
    assert tr.amplitude.min() >= 1.0 and tr.valid.all()
    fit = tracks.fit_track(tr, c=C)
    assert fit.identified and abs(fit.f0 - f0) < 1 and abs(fit.v - v) / v < 0.1 and abs(fit.t_cpa_emit - tc) < 2
