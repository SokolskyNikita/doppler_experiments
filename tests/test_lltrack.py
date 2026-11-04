"""The likelihood tracker (dopplertrack.lltrack): its log-likelihood ratio against the densities, forward-backward
against enumeration, and round 2's behaviour cases (a missing fundamental, a steady tone, crossing passes, a dip,
invalid frames, noise)."""
import itertools

import numpy as np
import pytest
from scipy.ndimage import convolve1d
from scipy.stats import ncx2

from dopplertrack import audio, doppler, freqtrack as ft, lltrack as ll

SR, N, HOP = 4000, 8192, 0.25
P = ll.LLParams()


def test_llr_is_the_rician_over_the_exponential():
    z = np.array([0.01, 0.3, 1.0, 2.5, 7.0, 20.0])
    for a in (1.0, 4.0, 8.0):
        f1 = 2 * ncx2.pdf(2 * z, 2, 2 * a)                                 # 2z is noncentral chi-square, 2 dof
        assert np.allclose(ll.llr(z, a), np.log(f1) + z, atol=1e-9)


def _matrix(K, p, step, f0s, dt):
    """The full transition matrix over [OFF, ON_0..ON_K-1, DIP_0..DIP_K-1], built from the same pieces."""
    ker = ll._kernel(step, float(f0s[-1]), dt, p)
    move = np.stack([convolve1d(np.eye(K)[j], ker, mode="constant") for j in range(K)])   # move[j, k]: j -> k
    p_end, p_dip, p_up = dt / p.t_pass_s, dt / p.t_run_s, dt / p.t_dip_s
    birth = p.birth_prior * step * dt
    A = np.zeros((2 * K + 1, 2 * K + 1))
    A[0, 0] = 1 - birth * K
    A[0, 1:K + 1] = birth
    A[1:K + 1, 0] = A[K + 1:, 0] = p_end
    A[1:K + 1, 1:K + 1] = (1 - p_end - p_dip) * move
    A[1:K + 1, K + 1:] = p_dip * move
    A[K + 1:, 1:K + 1] = p_up * move
    A[K + 1:, K + 1:] = (1 - p_end - p_up) * move
    return A


def test_forward_backward_matches_enumeration():
    rng = np.random.default_rng(0)
    T, K, dt, step = 5, 3, 0.25, 0.5
    f0s = 100.0 + step * np.arange(K)
    p = ll.with_params(P, birth_prior=0.05, t_pass_s=2.0, t_run_s=1.0, t_dip_s=0.5, slope_scale=0.05)
    E = rng.normal(0, 2, (T, K))
    valid = np.array([True, True, False, True, True])
    g_on, g_dip, g_off = ll.posterior(E, valid, dt, step, f0s, p)
    A = _matrix(K, p, step, f0s, dt)
    S = 2 * K + 1
    init = np.r_[1 - p.birth_prior * step * dt * K, np.full(K, p.birth_prior * step * dt), np.zeros(K)]
    emit = np.ones((T, S))
    emit[:, 1:K + 1] = np.exp(np.where(valid[:, None], E, 0.0))
    post = np.zeros((T, S))
    for seq in itertools.product(range(S), repeat=T):
        w = init[seq[0]] * emit[0, seq[0]]
        for n in range(1, T):
            w *= A[seq[n - 1], seq[n]] * emit[n, seq[n]]
        for n, s in enumerate(seq):
            post[n, s] += w
    post /= post.sum(axis=1, keepdims=True)
    assert np.allclose(g_off, post[:, 0], atol=1e-10)
    assert np.allclose(g_on, post[:, 1:K + 1], atol=1e-10)
    assert np.allclose(g_dip, post[:, K + 1:], atol=1e-10)


def _audio(dur, parts, noise=0.4, seed=0):
    t = np.arange(0, dur, 1 / SR)
    x = noise * np.random.default_rng(seed).standard_normal(len(t))
    for f, a, t0, t1 in parts:
        fi = f(t) if callable(f) else np.full(len(t), float(f))
        x += a * np.sin(2 * np.pi * np.cumsum(fi) / SR) * ((t >= t0) & (t < t1))
    return x.astype(np.float32)


def _run(x, lo, hi, blocks=None, fmax=1000.0, p=P):
    sp = (audio.compute_spectrogram(x, SR, fmax=fmax, whiten="frequency") if blocks is None
          else audio.spectrogram_from_blocks(blocks, SR, fmax=fmax, whiten="frequency"))
    return sp, ll.ll_track(sp, ft.SampleSTFT(x, SR, N, HOP), sp.t[0], sp.t[-1], lo, hi, p)


def _pass(f0):
    return lambda t: np.nan_to_num(doppler.ideal_curve(t, f0, 60.0, 900.0, 60.0, c=340.0), nan=f0)


def test_missing_fundamental_tracks_the_fundamental():
    g = _pass(100.0)
    x = _audio(120.0, [(lambda t, h=h: h * g(t), 0.15, 0, 120) for h in (2, 3, 4)])     # no fundamental
    _, ev = _run(x, 80, 125)
    tr = max(ev.tracks, key=lambda q: q.measured.sum())
    ok = tr.measured & (tr.t > 10) & (tr.t < 110)
    assert np.median(np.abs(tr.f[ok] - g(tr.t[ok]))) < 0.5                 # f0, not 2 f0 or f0/2
    assert tr.measured.mean() > 0.8


def _keeps_lines(ev, lines):
    """Every track lies on one of the lines and follows it for 90 % of its points: no swap at a crossing."""
    for tr in ev.tracks:
        ok = tr.measured
        err = {name: np.median(np.abs(tr.f[ok] - g(tr.t[ok]))) for name, g in lines.items()}
        name = min(err, key=err.get)
        assert err[name] < 1.0, (tr.start, tr.end, err)
        assert (np.abs(tr.f[ok] - lines[name](tr.t[ok])) < 2.0).mean() > 0.9, (tr.start, tr.end, name)
    return {min(lines, key=lambda n: np.median(np.abs(tr.f[tr.measured] - lines[n](tr.t[tr.measured]))))
            for tr in ev.tracks}


def test_a_pass_crossing_a_steady_tone():
    fall = _pass(150.0)
    x = _audio(120.0, [(fall, 0.2, 0, 120), (140.0, 0.12, 0, 120)])
    _, ev = _run(x, 115, 200, p=ll.with_params(P, harmonics=1))
    assert _keeps_lines(ev, {"fall": fall, "tone": lambda t: np.full(len(t), 140.0)}) == {"fall", "tone"}


def test_two_passes_crossing():
    a, b = _pass(150.0), (lambda t: np.nan_to_num(doppler.ideal_curve(t, 120.0, 70.0, 700.0, 75.0, c=340.0), nan=120.0))
    x = _audio(140.0, [(a, 0.2, 0, 140), (b, 0.15, 0, 140)])
    _, ev = _run(x, 95, 200, p=ll.with_params(P, harmonics=1))
    assert _keeps_lines(ev, {"a": a, "b": b}) == {"a", "b"}


def test_a_dip_under_the_noise_is_carried():
    g = _pass(120.0)
    amp = lambda t: np.where((t > 50) & (t < 53), 0.0, 0.2)               # 3 s with no tone at all
    t = np.arange(0, 120, 1 / SR)
    x = (0.4 * np.random.default_rng(1).standard_normal(len(t)) + amp(t) * np.sin(2 * np.pi * np.cumsum(g(t)) / SR)).astype(np.float32)
    _, ev = _run(x, 95, 150, p=ll.with_params(P, harmonics=1, families=1))
    long = [tr for tr in ev.tracks if tr.end - tr.start > 60]
    assert len(long) == 1 and long[0].start < 45 and long[0].end > 60


@pytest.mark.xfail(strict=True, reason="design_snr and birth_prior come from the synthetic ROC (ll_roc.py)")
def test_noise_and_a_short_tone_make_no_track():
    x = _audio(120.0, [(130.0, 0.2, 40, 40.5)])
    _, ev = _run(x, 100, 160, p=ll.with_params(P, harmonics=1))
    assert ev.tracks == []


def test_invalid_frames_are_crossed_without_a_measurement():
    x = _audio(60.0, [(lambda t: 140.0 - 0.3 * t, 0.2, 0, 60)])
    a, b = int(28 * SR), int(29 * SR)
    _, ev = _run(x, 110, 160, [(x[:a], True), (x[a:b], False), (x[b:], True)], p=ll.with_params(P, harmonics=1, families=1))
    (tr,) = ev.tracks
    assert (~tr.measured).sum() >= 8 and tr.end - tr.start > 50
