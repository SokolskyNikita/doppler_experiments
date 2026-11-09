"""Gaps in the audio (PLAN Phase 1 item 8): the spectrogram keeps the recording's timeline, frames
over a gap are invalid, and fits neither bridge nor are dragged by them."""
import datetime

import numpy as np
import pytest
import scipy.io.wavfile

from dopplertrack.core import propagation as doppler
from dopplertrack.components.spectrogram import Spectrogram
from dopplertrack.runtime.parallel import process_pool
import dopplertrack.components.audio_input as audio_input
import dopplertrack.components.detection.event_fit as event_fit
import dopplertrack.components.whitening.local_median as local_median
import dopplertrack.components.stft as stft

C, SR = 340.0, 4000
F0, V, D, T0 = 110.0, 80.0, 400.0, 150.0     # a close, fast pass: most of its sweep lies within ±10 s of CPA
T_CPA = T0 + D / C                           # heard CPA, s
GAP_S, PERIOD_S = 5.0, 60.0                  # AudioMoth's 55 s on, 5 s off
SEEDS = range(6)
HOP_S = 0.25


def _pass_audio(seed, dur=300.0, amp=0.03):
    """A straight pass made by integrating the phase of ideal_curve's frequency, in white noise.
    At this amplitude the uncut fit scores about 5 dB, inside the range of Oyster Bay's detections."""
    t = np.arange(0, dur, 1 / SR)
    fi = np.nan_to_num(doppler.ideal_curve(t, F0, V, D, T0, c=C), nan=F0)
    x = amp * np.sin(2 * np.pi * np.cumsum(fi) / SR) + 0.4 * np.random.default_rng(seed).standard_normal(len(t))
    return x.astype(np.float32)


def _gapped(x, first_gap_s, gap_s=GAP_S, period_s=PERIOD_S):
    """(samples, is_audio) blocks with gap_s cut from every period_s, the gaps starting at
    first_gap_s modulo period_s."""
    out, pos, s = [], 0, first_gap_s % period_s - period_s
    while pos < len(x):
        g0, g1 = max(int(round(s * SR)), pos), min(int(round((s + gap_s) * SR)), len(x))
        if g1 > pos:
            if g0 > pos:
                out.append((x[pos:g0], True))
            out.append((x[g0:g1], False))
            pos = g1
        s += period_s
    return out


def _spec(blocks):
    return stft.spectrogram_from_blocks(blocks, SR, hop_s=HOP_S, whiten_window_s=None)


def _fit(sp):
    return event_fit.fit_event(sp, T_CPA - 45, T_CPA + 45, 90, 135, c=C)


def _three_fits(seed):
    """The uncut fit; the fit with every gap at least 20 s from CPA (starting 20-35 s after it, a
    different phase per seed); and the fit with one gap centred on CPA."""
    x = _pass_audio(seed)
    uncut = _fit(_spec([(x, True)]))
    cut_sp = _spec(_gapped(x, T_CPA + 20 + 15 * seed / (len(SEEDS) - 1)))
    steep = _fit(_spec(_gapped(x, T_CPA - GAP_S / 2)))
    return uncut, _fit(cut_sp), steep, float(np.mean(~cut_sp.valid))


@pytest.fixture(scope="module")
def fits():
    with process_pool(min(len(SEEDS), 6)) as ex:      # spawn, as on the Mac: fork on Linux warns under threads
        return list(ex.map(_three_fits, SEEDS))


def test_gapped_pass_fits_like_uncut(fits):
    """5 s cut from every minute, each gap at least 20 s from CPA. For f0, speed and distance the
    gaps shift the fit without bias (the mean shift over seeds is within 2 standard errors of 0)
    and by at most 4 % on any seed; CPA moves by at most one hop.

    Not "within the uncut fit's noise spread": on this synthetic pass that spread is about 0.5 % in
    d, tighter than what losing 12 % of the frames does to d (about 1.2 % rms; see
    docs/experiments/2026-11-03-gap-aware-spectrogram.md)."""
    for k in ("f0", "v", "d"):
        uncut = np.array([getattr(u, k) for u, _, _, _ in fits])
        shift = np.array([getattr(g, k) for _, g, _, _ in fits]) - uncut
        assert abs(shift.mean()) <= 2 * shift.std(ddof=1) / np.sqrt(len(shift)), (k, shift)
        assert np.all(np.abs(shift) <= 0.04 * uncut), (k, shift / uncut)
    for u, g, _, _ in fits:
        assert abs(g.t_cpa - u.t_cpa) <= HOP_S, (u.t_cpa, g.t_cpa)


def test_gap_over_steepest_part_weakens_fit(fits):
    """Weaker means: the score falls by more than the gaps' share of the timeline (cutting frames
    uniformly costs about that share, since a gap carries no evidence), and below the score of the
    same pass with its gaps elsewhere."""
    for u, g, s, invalid in fits:
        assert 0.0 < s.score <= (1 - invalid) * u.score, (u.score, s.score, invalid)
        assert s.score < g.score, (g.score, s.score)


def test_npz_round_trip_with_and_without_mask(tmp_path):
    t, f = np.arange(10) * 0.5 + 1.0, np.arange(4) * 2.0 + 40
    S = np.arange(40, dtype=np.float32).reshape(4, 10)
    legacy = tmp_path / "legacy.npz"
    np.savez_compressed(legacy, t=t, f=f, S=S)               # a file from before the mask existed
    sp = Spectrogram.load(legacy)
    assert sp.valid.dtype == bool and sp.valid.all() and sp.start_utc is None

    valid = np.ones(10, bool); valid[3:6] = False
    masked = Spectrogram(t, f, S, valid, 1712462446.0)
    masked.save(tmp_path / "masked")                          # suffix added, as numpy does
    back = Spectrogram.load(tmp_path / "masked.npz")
    for a, b in ((back.t, t), (back.f, f), (back.S, S), (back.valid, valid)):
        assert np.array_equal(a, b)
    assert back.start_utc == 1712462446.0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["legacy.npz", "masked.npz"]    # no temp file left

    c = back.crop(2.0, 4.0)
    assert np.array_equal(c.t, t[2:7]) and np.array_equal(c.valid, valid[2:7]) and c.start_utc == back.start_utc


@pytest.mark.parametrize("window_s", [None, 60.0])
def test_whitening_ignores_gaps(window_s):
    """Steady noise with 40% of the time in gaps. Zero-filled gaps sit near -200 dB, so a median
    that counted them would be dragged far down; over valid frames each bin's median stays at 0."""
    x = 0.3 * np.random.default_rng(3).standard_normal(240 * SR).astype(np.float32)
    sp = stft.spectrogram_from_blocks(_gapped(x, 10.0, gap_s=12.0, period_s=30.0), SR, whiten_window_s=window_s)
    assert 0.3 < np.mean(~sp.valid) < 0.6
    med = np.median(sp.S[:, sp.valid], axis=1)
    assert np.max(np.abs(med)) < 0.5, np.max(np.abs(med))
    assert np.all(sp.S[:, ~sp.valid] == 0)
    counted = np.median(np.where(sp.valid, sp.S, -200.0), axis=1)      # what a mask-blind median would see
    assert np.min(np.abs(counted)) > 5.0

    win = local_median.local_whiten(sp.crop(60, 180))
    assert np.array_equal(win.valid, sp.crop(60, 180).valid)
    w = sp.crop(60, 180)
    assert np.allclose(win.S[:, w.valid], np.maximum(w.S[:, w.valid] - np.median(w.S[:, w.valid], axis=1, keepdims=True), 0))
    assert np.all(win.S[:, ~w.valid] == 0)


def test_local_whiten_unchanged_without_gaps():
    """An all-valid spectrogram whitens byte for byte as local_whiten did before the mask."""
    rng = np.random.default_rng(5)
    sp = Spectrogram(np.arange(400) * 0.25, 40 + np.arange(60) * 0.49, rng.normal(0, 3, (60, 400)).astype(np.float32),
                     start_utc=1712462446.0)
    for floor in (0.0, -2.0):
        before = np.maximum(sp.S - np.median(sp.S, axis=1, keepdims=True), floor).astype(np.float32)
        after = local_median.local_whiten(sp, floor)
        assert after.S.dtype == before.dtype and after.S.tobytes() == before.tobytes()
        assert after.valid.all() and after.start_utc == sp.start_utc


def test_sample_never_bridges_an_invalid_frame():
    t, f = np.arange(10, dtype=float), np.array([100.0, 101.0])
    valid = np.ones(10, bool); valid[5] = False
    sp = Spectrogram(t, f, np.full((2, 10), 10.0, np.float32), valid)
    q = np.array([3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 9.0])
    got = sp.sample(q, np.full(len(q), 100.5), fill=-1.0)
    # 4.0 and 6.0 sit on valid frames and take no weight from frame 5; the points either side of it do
    assert got.tolist() == [10.0, 10.0, -1.0, -1.0, -1.0, 10.0, 10.0]
    assert sp.sample([12.0], [100.5], fill=-1.0)[0] == -1.0


# ---- several files on one timeline (needs ffmpeg) ---------------------------------------------

def _wav(path, x):
    scipy.io.wavfile.write(path, SR, np.round(np.clip(x, -1, 1) * 32767).astype(np.int16))


def _noise(seconds, seed):
    return 0.3 * np.random.default_rng(seed).standard_normal(int(seconds * SR))


def test_files_that_abut_leave_no_invalid_frame(tmp_path):
    a, b = _noise(70, 1), _noise(50, 2)
    _wav(tmp_path / "a.wav", a); _wav(tmp_path / "b.wav", b); _wav(tmp_path / "ab.wav", np.concatenate([a, b]))
    sp = stft.spectrogram_from_files([(tmp_path / "a.wav", 0.0), (tmp_path / "b.wav", 70.0)], SR)
    one = stft.compute_spectrogram(audio_input.load_audio(tmp_path / "ab.wav", SR)[0], SR)
    assert sp.valid.all()
    assert np.array_equal(sp.t, one.t) and np.array_equal(sp.S, one.S)


def test_hole_between_files_is_invalid_and_timeline_is_kept(tmp_path):
    _wav(tmp_path / "a.wav", _noise(70, 1)); _wav(tmp_path / "b.wav", _noise(50, 2))
    sp = stft.spectrogram_from_files([(tmp_path / "a.wav", 0.0), (tmp_path / "b.wav", 73.0)], SR, nperseg=8192)
    assert len(sp.t) == (123 * SR - 8192) // int(HOP_S * SR) + 1            # 123 s of timeline, hole included
    lo, hi = sp.t - 8192 / 2 / SR, sp.t + 8192 / 2 / SR                      # each frame's window
    assert np.array_equal(sp.valid, (hi <= 70.0) | (lo >= 73.0))


def test_audiomoth_folder_uses_utc_names(tmp_path):
    (tmp_path / "CONFIG.TXT").write_text("Time zone                       : UTC\n")
    for name, seed in (("20240407_040046.WAV", 1), ("20240407_040146.WAV", 2), ("20240407_040322.WAV", 3)):
        _wav(tmp_path / name, _noise(60, seed))
    files, start = audio_input.audiomoth_files(tmp_path)
    assert start == datetime.datetime(2024, 4, 7, 4, 0, 46, tzinfo=datetime.timezone.utc).timestamp()
    assert [o for _, o in files] == [0.0, 60.0, 156.0]
    sp = stft.spectrogram_from_audiomoth(tmp_path)
    assert sp.start_utc == start
    lo, hi = sp.t - 8192 / 2 / SR, sp.t + 8192 / 2 / SR
    assert np.array_equal(sp.valid, (hi <= 120.0) | (lo >= 156.0))           # the seam at 60 s is clean

    _wav(tmp_path / "20240407_040130.wav", _noise(60, 4))                    # starts 16 s before the first ends
    with pytest.raises(ValueError, match="before the previous file ends"):
        stft.spectrogram_from_audiomoth(tmp_path)
    (tmp_path / "CONFIG.TXT").write_text("Time zone                       : UTC+2\n")
    with pytest.raises(ValueError, match="only UTC"):
        audio_input.audiomoth_files(tmp_path)
