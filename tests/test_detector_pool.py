"""Verify the late experimental null-rescoring pool without running a ROC study."""
from dataclasses import asdict
import importlib
from pathlib import Path

import numpy as np

from dopplertrack import audio, tracks


def test_null_rescoring_serial_and_pool_agree(monkeypatch):
    """Real reversed-window fits preserve scores, event order and diagnostics across workers."""
    scripts = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "2026-11-04"
    monkeypatch.syspath_prepend(str(scripts))
    roc = importlib.import_module("detector_roc")
    samples = (0.4 * np.random.default_rng(19).standard_normal(240 * 4000)).astype(np.float32)
    sp = audio.compute_spectrogram(samples, 4000, fmax=450.0)
    events = [tracks.EventFit(t_cpa=t, t_cpa_emit=t - 900 / roc.C, f0=f, v=60.0, d=900.0,
                              t_start=t - 30, t_end=t + 30, score=score, f_pre=0.0, f_post=0.0)
              for t, f, score in [(80.0, 130.0, 5.0), (160.0, 190.0, 7.0)]]
    serial, serial_diag = roc.null_scores(sp, events, 100.0, 220.0, 1)
    pooled, pooled_diag = roc.null_scores(sp, events, 100.0, 220.0, 2)
    assert len(serial) == len(pooled) == len(events)
    assert all(np.isfinite(e.score) for e in serial)
    assert [asdict(e) for e in serial] == [asdict(e) for e in pooled]
    assert serial_diag == pooled_diag
    assert [e.t_cpa for e in pooled] == [e.t_cpa for e in events]
