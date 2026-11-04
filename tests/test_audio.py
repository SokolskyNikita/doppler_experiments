import numpy as np
from dopplertrack import audio, doppler


def test_spectrogram_sample_and_synthetic_doppler():
    sr = 4000
    t = np.arange(0, 400, 1 / sr)
    f0, v, d, t0 = 130.0, 110.0, 3000.0, 200.0
    finst = doppler.ideal_curve(t, f0, v, d, t0, c=340.0)
    finst = np.nan_to_num(finst, nan=f0)
    phase = 2 * np.pi * np.cumsum(finst) / sr
    x = (0.1 * np.sin(phase) + 0.5 * np.random.default_rng(0).standard_normal(len(t))).astype(np.float32)
    sp = audio.compute_spectrogram(x, sr, nperseg=8192, hop_s=0.5, fmin=60, fmax=250, whiten_window_s=None)
    tt = np.arange(20, 380, 2.0)
    on = sp.sample(tt, doppler.ideal_curve(tt, f0, v, d, t0, c=340.0))
    off = sp.sample(tt, doppler.ideal_curve(tt, f0, v, d, t0, c=340.0) + 15.0)
    assert on.mean() > off.mean() + 5.0
    assert sp.sample([-5.0], [100.0])[0] == 0.0


def test_frequency_whitening_keeps_a_stationary_tone_and_is_named():
    sr = 4000
    t = np.arange(0, 240, 1 / sr)
    x = (0.05 * np.sin(2 * np.pi * 150.0 * t) + 0.4 * np.random.default_rng(0).standard_normal(len(t))).astype(np.float32)
    by_time = audio.compute_spectrogram(x, sr)
    by_freq = audio.compute_spectrogram(x, sr, whiten="frequency")
    j = int(np.argmin(np.abs(by_freq.f - 150.0)))
    assert by_time.whitening == "time" and by_freq.whitening == "frequency"
    assert np.median(by_time.S[j]) < 1.0                                  # the median over time removes the tone
    assert np.median(by_freq.S[j]) > 5.0                                  # the median across frequency keeps it
    assert abs(np.median(by_freq.S[(by_freq.f > 200) & (by_freq.f < 400)])) < 0.5
    from dopplertrack.tracks import local_whiten
    w = local_whiten(by_freq.crop(50, 200))
    assert w.whitening == "frequency" and np.median(w.S[j]) > 5.0        # local_whiten leaves it alone
    assert np.array_equal(local_whiten(by_time).S, np.maximum(by_time.S - by_time.bin_median(), 0).astype(np.float32))


def test_whitening_survives_the_npz(tmp_path):
    sp = audio.compute_spectrogram(np.random.default_rng(1).standard_normal(40 * 4000).astype(np.float32), 4000,
                                   whiten="frequency")
    sp.save(tmp_path / "f.npz")
    assert audio.Spectrogram.load(tmp_path / "f.npz").whitening == "frequency"
    plain = audio.compute_spectrogram(np.zeros(40 * 4000, np.float32) + 1e-3, 4000)
    plain.save(tmp_path / "t.npz")
    assert "whitening" not in np.load(tmp_path / "t.npz").files                 # today's files are unchanged
    assert audio.Spectrogram.load(tmp_path / "t.npz").whitening == "time"
