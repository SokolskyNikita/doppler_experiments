"""Emission-time resampling (dopplertrack.warp): the interpolator's floor on a synthetic flyover, the
anti-alias filter, the refusal of geometries that would alias, and the tone path."""
import numpy as np
import pytest

from dopplertrack import warp as W

SR, C = 4000, 340.0
V, H, TC = 100.0, 300.0, 30.0          # a close, fast pass: reading rate up to 1 + v/c = 1.29 on the recede


def _tau(t):
    """Emission time of the sound heard at t from a straight pass (Ferguson & Quinn 1994 eq. 14)."""
    return (C * C * t - V * V * TC - np.sqrt(H * H * (C * C - V * V) + V * V * C * C * (t - TC) ** 2)) / (C * C - V * V)


def _flyover(f_e, dur=60.0, noise=0.0, seed=0):
    t = np.arange(0, dur, 1 / SR)
    x = np.sin(2 * np.pi * f_e * _tau(t))
    return x + noise * np.random.default_rng(seed).standard_normal(len(t))


def _traj():
    t = np.arange(0.0, 61.0, 1.0)                                     # 1 Hz, as ADS-B segments are
    return t, np.stack([V * (t - TC), np.full(len(t), H), np.zeros(len(t))], axis=1)


def _floor_db(y, f_e, part):
    """Line power over the strongest other component in 40-1500 Hz, on 2.048 s blocks before
    (approach) or after (recede) CPA. Measured with a 4-term Blackman-Harris window (sidelobes near
    -92 dB) and +-8 bins excluded around the line, so the window's own leakage doesn't set the floor."""
    n, hop = 8192, 2048
    win = np.array([0.35875, -0.48829, 0.14128, -0.01168]) @ np.cos(2 * np.pi * np.outer(np.arange(4), np.arange(n)) / n)
    starts = [a for a in range(0, len(y) - n + 1, hop) if np.isfinite(y[a:a + n]).all()]
    tb = (np.array(starts) + n / 2) / SR
    sel = [a for a, tt in zip(starts, tb) if ((tt < TC - 4) if part == "approach" else (tt > TC + 4))]
    P = np.abs(np.fft.rfft(np.stack([y[a:a + n] * win for a in sel]), axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / SR)
    line = np.abs(f - f_e) <= 8 * (f[1] - f[0])
    band = (f >= 40) & (f <= 1500) & ~line
    return 10 * np.log10(P[:, line].sum(1) / P[:, band].max(1)).min()


@pytest.mark.parametrize("part", ["approach", "receding"])
def test_sinc_floor_at_the_band_edge(part):
    t, enu = _traj()
    x = _flyover(440.0)
    floors = {}
    for m in ("sinc", "linear", "nearest"):
        w = W.warp(x, SR, 0.0, t, enu, np.zeros(3), C, 2.0, 58.0, method=m)
        floors[m] = _floor_db(w.y, 440.0, part)
    assert floors["sinc"] >= 50.0, floors
    assert floors["sinc"] > floors["linear"] > floors["nearest"], floors     # Howell 1986's ordering


def test_lowpass_keeps_folded_noise_out_of_the_band():
    """Noise recorded only at 1600-2000 Hz, warped on the recede (rate 1.29), folds back below 2 kHz
    without the low-pass; with it nothing reaches 40-1450 Hz."""
    t, enu = _traj()
    x = W.bandpass(np.random.default_rng(1).standard_normal(60 * SR), SR, 1600, 1990)
    out = {}
    for pre in (False, True):
        xin = x if pre else x.copy()
        w = W.warp(xin, SR, 0.0, t, enu, np.zeros(3), C, 36.0, 58.0, prefiltered=not pre)
        cen, f, db = W.block_db(w.y, SR)
        P = 10 ** (db / 10)
        out[pre] = 10 * np.log10(P[:, (f >= 40) & (f <= 1450)].sum() / (np.var(x) * len(f) * P.shape[0] + 1e-30))
    assert out[True] < out[False] - 20 and out[True] < -50, out


def test_too_fast_a_reading_rate_is_refused():
    t, enu = _traj()
    fast = enu * 1.6                                                     # 160 m/s: rate 1.47
    with pytest.raises(ValueError, match="reading rate"):
        W.warp(_flyover(200.0), SR, 0.0, t, fast, np.zeros(3), C, 2.0, 58.0)


def test_warp_makes_the_true_geometry_stationary_and_a_wrong_one_not():
    t, enu = _traj()
    x = _flyover(150.0, noise=0.5)
    scores = {}
    for name, obs in (("true", np.zeros(3)), ("wrong", np.array([0.0, -900.0, 0.0]))):
        w = W.warp(x, SR, 0.0, t, enu, obs, C, 2.0, 58.0)
        cen, f, db = W.block_db(w.y, SR)
        S = W.across_frequency(db, f[1] - f[0])
        scores[name] = W.tone_score(S, f, 120.0, 180.0, harmonics=1, families=1)
    assert abs(scores["true"].f0[0] - 150.0) < 1.0           # pooling takes the best of +-1 bin
    assert scores["true"].score > scores["wrong"].score + 5.0


def test_off_state_and_drift():
    rng = np.random.default_rng(2)
    f = np.arange(0, 400, 0.5)
    S = rng.normal(0, 3, (60, len(f)))
    S[10:40, 200] += 20.0                                               # a tone at 100 Hz in blocks 10-39
    ts = W.tone_score(S, f, 90, 110, harmonics=1, theta=5.0, birth=5.0, families=1)
    assert ts.f0[0] == 100.0 and 0.45 < ts.on < 0.55
    S2 = rng.normal(0, 3, (60, len(f)))
    S2[np.arange(60), 400 + np.arange(60) // 10] += 20.0                 # 200 Hz, one bin every 10 blocks: 3 Hz in all
    strict = W.tone_score(S2, f, 190, 210, harmonics=1, theta=5.0, birth=5.0, families=1)
    drift = W.tone_score(S2, f, 190, 210, harmonics=1, theta=5.0, birth=5.0, families=1, drift_step_hz=0.5)
    assert drift.score > strict.score and drift.on > 0.9


def test_harmonics_beyond_the_grid_earn_nothing():
    """Energy only in the grid's last bin (500 Hz): a 200 Hz fundamental's third harmonic (600 Hz) lies
    beyond the grid and must not borrow it, and its first two harmonics are all that count."""
    f = np.arange(0.0, 500.0 + 1e-9, 0.5)
    S = np.zeros((4, len(f)))
    S[:, -1] = 30.0
    E = W.pooled(S, f, np.array([200.0]), harmonics=3)
    assert np.all(E == 0.0)
    S[:, 400] = 12.0                                                      # 200 Hz: h = 1 alone is seen
    E = W.pooled(S, f, np.array([200.0]), harmonics=3)
    w = W.harmonic_weights(3)
    assert np.allclose(E, w[0] * 12.0 / (w[0] + w[1]))                    # normalised over h = 1, 2 only
    exc = np.zeros(S.shape, bool); exc[:, 799:802] = True                 # 400 Hz excluded: h = 2 unobserved
    assert np.allclose(W.pooled(S, f, np.array([200.0]), harmonics=3, exclude=exc), 12.0)
