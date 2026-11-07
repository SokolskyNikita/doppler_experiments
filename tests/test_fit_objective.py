"""fit_event's two objectives. On a uniform spectrogram "brightness" (mean brightness under the curve)
scores the level itself, while "contrast" (the curve minus its sidebands) is zero away from the crop's
edges and at most about half the level at them, so the two cannot be confused."""
import numpy as np
import pytest

from dopplertrack import cli
from dopplertrack.audio import Spectrogram
from dopplertrack.tracks import EventFit, fit_event, grid_search


def _uniform(level=1.0):
    t = np.arange(0, 400, 0.5); f = np.arange(40, 1000, 0.5)
    return Spectrogram(t, f, np.full((len(f), len(t)), level, np.float32))


def test_grid_search_objectives_differ():
    sp = _uniform()
    sb, _ = grid_search(sp, 100, 140, 100, 150, 340.0, objective="brightness")
    sc, _ = grid_search(sp, 100, 140, 100, 150, 340.0, objective="contrast")
    assert sb == pytest.approx(1.0) and sc == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(ValueError):
        grid_search(sp, 100, 140, 100, 150, 340.0, objective="loudness")


def test_fit_event_objectives_differ():
    sp = _uniform()
    b = fit_event(sp, 100, 140, 100, 150, c=340.0, whiten=False, objective="brightness")
    c = fit_event(sp, 100, 140, 100, 150, c=340.0, whiten=False, objective="contrast")
    assert b.score == pytest.approx(1.0, abs=1e-3)
    assert c.score < 0.75


def test_fit_cli_defaults_to_brightness(tmp_path, monkeypatch):
    spec = tmp_path / "rec.npz"
    _uniform().save(spec)
    seen = []

    def fake_fit_event(sp, t0, t1, f_lo, f_hi, harmonics=1, objective="contrast"):
        seen.append(objective)
        return EventFit(t_cpa=0, t_cpa_emit=0, f0=1, v=1, d=1, t_start=t0, t_end=t1, score=0, f_pre=1, f_post=1)

    monkeypatch.setattr(cli, "fit_event", fake_fit_event)
    cli.main(["fit", str(spec), "--window", "100", "140", "--band", "100", "150"])
    cli.main(["fit", str(spec), "--window", "100", "140", "--band", "100", "150", "--objective", "contrast"])
    assert seen == ["brightness", "contrast"]


def test_a_band_with_nothing_to_search_gives_a_weak_fit():
    """A band too narrow for its fundamental range (f_lo*1.15 >= f_hi*0.85) returns a weak fit, not an error."""
    sp = _uniform()
    for f_lo, f_hi in ((140, 150), (414, 450)):
        ev = fit_event(sp, 100, 140, f_lo, f_hi, c=340.0)
        assert ev.weak and ev.weak.startswith("band narrower than the f0 search margins") and np.isnan(ev.f0)
    assert fit_event(sp, 140, 100, 100, 150, c=340.0).weak            # an empty window
    ok = fit_event(sp, 100, 140, 100, 150, c=340.0)
    assert ok.weak is None and "weak" not in ok.to_dict()             # a fit's JSON is unchanged
    assert EventFit(**ok.to_dict()) == ok and EventFit(**ev.to_dict()).weak == ev.weak


def test_a_band_narrower_than_the_f0_margins_around_a_real_tone_gives_a_weak_fit():
    """grid_search searches f0 from 1.15 f_lo to 0.85 f_hi, empty whenever f_hi/f_lo < 1.15/0.85 = 1.353, whatever
    the curve: the model-error study's Livermore R35, R08, R51 and 654 Alaska crossings. A band of ratio 1.3 around a real tone."""
    from dopplertrack.doppler import ideal_curve
    t, f = np.arange(0, 400, 0.5), np.arange(40, 300, 0.5)
    S = np.zeros((len(f), len(t)), np.float32)
    curve = ideal_curve(t, 120.0, 60.0, 1500.0, 200.0, c=340.0)
    on = np.isfinite(curve)
    S[np.rint((curve[on] - f[0]) / 0.5).astype(int), np.flatnonzero(on)] = 10.0
    ev = fit_event(Spectrogram(t, f, S), 120, 280, 105.0, 136.5, c=340.0)
    assert ev.weak and ev.weak.startswith("band narrower than the f0 search margins") and "1.300" in ev.weak
    assert np.isnan(ev.v) and not np.isfinite(ev.score)
