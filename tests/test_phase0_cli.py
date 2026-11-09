"""Public CLI hand-off and explicit empty/missing-decoder outcomes."""
import json

import numpy as np
import pandas as pd
import pytest

from dopplertrack.components import spectrogram as audio
from dopplertrack.commands import main as cli
from dopplertrack.core import propagation as doppler
from dopplertrack.methods.grid_pair import pipeline
from dopplertrack.components.detection import grid_scan as tracks
import dopplertrack.components.audio_input as audio_input
import dopplertrack.components.types as components_types
import dopplertrack.data.region_loading as region_loading
import dopplertrack.components.stft as stft


def _event(t=100, score=4):
    return components_types.EventFit(t, t - 3, 120, 100, 1000, t - 30, t + 30, score, 150, 90)


def _spec():
    t, f = np.arange(0, 601, 0.5), np.arange(40, 251, 1.0)
    return audio.Spectrogram(t, f, np.zeros((len(f), len(t)), np.float32))


@pytest.mark.parametrize("command", ["search", "refine"])
@pytest.mark.parametrize("detect_list", [False, True])
def test_search_and_refine_take_fits_or_ranked_detect_list(tmp_path, monkeypatch, command, detect_list):
    spec = tmp_path / "spec.npz"
    _spec().save(spec)
    ev1, ev2 = _event(100), _event(400)
    if detect_list:
        events = tmp_path / "events.json"
        events.write_text(json.dumps([ev2.to_dict(), ev1.to_dict()]))
        event_args = ["--events", str(events), "--pick", "2", "1"]
    else:
        files = [tmp_path / "ev1.json", tmp_path / "ev2.json"]
        for f, ev in zip(files, (ev1, ev2)):
            f.write_text(json.dumps(ev.to_dict()))
        event_args = ["--events", *map(str, files)]
    traces = tmp_path / "traces.npz"
    region_loading.save_traces([], traces)
    seen = []
    row = dict(lat=40, lon=-74, lat0=40, lon0=-74, seg1=0, seg2=1, icao1="a", icao2="b",
               t_heard1=1e9, score=10, shift=0)

    def fake_search(sp, a, b, traces, grid, params, **kwargs):
        seen.append((a, b, params.gates.max_range_m))
        return pd.DataFrame([row]), []

    def fake_refine(sp, a, b, segs, row_, params, **kwargs):
        seen.append((a, b, params.gates.max_range_m))
        return pd.DataFrame([row])

    monkeypatch.setattr(pipeline, "pair_grid_search", fake_search)
    monkeypatch.setattr(pipeline, "refine", fake_refine)
    monkeypatch.setattr(pipeline, "segments_for_search", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "relocate_row", lambda row, *a: row)
    args = [command, str(spec)]
    if command == "refine":
        results = tmp_path / "search.csv"
        pd.DataFrame([row]).to_csv(results, index=False)
        args.append(str(results))
    cli.main(args + event_args + ["--traces", str(traces), "--bbox", "40", "40.01", "-74", "-73.99",
                                  "--no-dem", "--max-range", "9000", "--out", str(tmp_path / "out.csv")])
    assert seen == [(ev1, ev2, 9000)]


@pytest.mark.parametrize("files,picks,data", [
    (["one"], None, []), (["one", "two"], [1, 2], []),
    (["one"], [0, 1], [{}, {}]), (["one"], [1, 1], [{}, {}]),
    (["one"], [1, 3], [{}, {}]), (["one"], [1, 2], []),
    (["one"], [1, 2], {}), (["one", "two"], None, []),
])
def test_event_selection_rejects_invalid_ranks_and_formats(tmp_path, files, picks, data):
    for f in files:
        (tmp_path / f).write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cli.load_events([tmp_path / f for f in files], picks)


def test_silent_audio_has_no_detections(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("DOPPLERTRACK_CACHE", str(tmp_path / "cache"))
    sp = stft.compute_spectrogram(np.zeros(4000 * 8, np.float32), 4000)
    assert tracks.detect_events(sp, 100, 130, workers=1) == []
    spec, out = tmp_path / "silence.npz", tmp_path / "events.json"
    sp.save(spec)
    cli.main(["detect", str(spec), "--band", "100", "130", "--out", str(out)])
    assert json.loads(out.read_text()) == []
    assert "no flyovers found" in capsys.readouterr().out


def test_cli_detect_reuses_cached_detections(tmp_path, monkeypatch):
    monkeypatch.setenv("DOPPLERTRACK_CACHE", str(tmp_path / "cache"))
    calls = []

    def fake_detect(sp, f_lo, f_hi, **kwargs):
        calls.append(kwargs["workers"])
        return [_event(100, 7)]

    monkeypatch.setattr(tracks, "detect_events", fake_detect)
    spec, outs = tmp_path / "spec.npz", [tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"]
    _spec().save(spec)
    args = ["detect", str(spec), "--band", "100", "130", "--top", "3"]
    cli.main(args + ["--jobs", "1", "--out", str(outs[0])])
    cli.main(args + ["--jobs", "4", "--out", str(outs[1])])     # workers don't change what is detected
    assert calls == [1] and outs[0].read_text() == outs[1].read_text()
    cli.main(args + ["--top", "2", "--out", str(outs[2])])       # another parameter is another entry
    assert len(calls) == 2


def test_min_score_is_applied_to_refined_scores(monkeypatch):
    monkeypatch.setattr(tracks, "_scan_window", lambda req: [tracks.Candidate(10, 120, 100, 1000, 100),
                                                             tracks.Candidate(2, 120, 100, 1000, 300)])
    monkeypatch.setattr(tracks, "fit_event", lambda *a, init, **k: _event(init[3], -1 if init[3] == 100 else 8))
    events = tracks.detect_events(_spec(), 100, 130, top=2, workers=1, min_score=5)
    assert [e.t_cpa for e in events] == [300]
    assert tracks.detect_events(_spec(), 100, 130, top=2, workers=1, min_score=9) == []


def test_merge_breaks_score_ties_as_the_tuple_sort_did():
    first = tracks.Candidate(score=5.0, f0_hz=120.0, speed_mps=100.0, slant_m=1000.0, t_cpa_emit_s=100.0)
    second = tracks.Candidate(score=5.0, f0_hz=121.0, speed_mps=100.0, slant_m=1000.0, t_cpa_emit_s=110.0)
    assert tracks.non_maximum_suppression([first, second], min_sep_s=60.0, keep=2) == [second]


def test_worker_pool_matches_serial_scan():
    c, f0, v, d, t0 = 340.0, 120.0, 90.0, 1500.0, 200.0
    t, f = np.arange(0, 480, 0.5), np.arange(60, 201, 1.0)
    S = np.random.default_rng(0).uniform(0, 1, (len(f), len(t))).astype(np.float32)
    ridge = doppler.ideal_curve(t, f0, v, d, t0, c=c)
    on = np.isfinite(ridge)
    S[np.rint(ridge[on] - f[0]).astype(int), np.flatnonzero(on)] += 10
    sp = audio.Spectrogram(t, f, S)
    # a coarse grid and one refined candidate keep this cheap; refinement still runs
    kwargs = dict(c=c, top=1, min_sep_s=600.0, v_grid=np.arange(40, 170, 26.0), d_grid=np.geomspace(400, 9000, 5))
    serial = tracks.detect_events(sp, 80, 160, workers=1, **kwargs)
    assert serial and abs(serial[0].f0 - f0) < 3
    assert tracks.detect_events(sp, 80, 160, workers=2, **kwargs) == serial


def test_missing_ffmpeg_has_actionable_library_and_cli_error(monkeypatch, capsys):
    def missing(*a, **k):
        raise FileNotFoundError("ffmpeg")
    monkeypatch.setattr(audio_input.subprocess, "run", missing)
    with pytest.raises(audio_input.FFmpegNotFoundError, match="brew install ffmpeg"):
        audio_input.load_audio("recording.wav")
    with pytest.raises(SystemExit) as exc:
        cli.main(["spectrogram", "recording.wav", "out.npz"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ffmpeg was not found on PATH" in err and "Traceback" not in err
