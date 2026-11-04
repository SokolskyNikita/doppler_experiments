"""Public CLI hand-off and explicit empty/missing-decoder outcomes."""
import json

import numpy as np
import pandas as pd
import pytest

from dopplertrack import adsb, audio, cli, pipeline, tracks


def _event(t=100, score=4):
    return tracks.EventFit(t, t - 3, 120, 100, 1000, t - 30, t + 30, score, 150, 90)


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
    adsb.save_traces([], traces)
    seen = []
    row = dict(lat=40, lon=-74, lat0=40, lon0=-74, seg1=0, seg2=1, icao1="a", icao2="b",
               t_heard1=1e9, score=10, shift=0)

    def fake_search(sp, a, b, traces, grid, **kwargs):
        seen.append((a, b, kwargs["max_range_m"]))
        return pd.DataFrame([row]), []

    def fake_refine(sp, a, b, *args, **kwargs):
        seen.append((a, b, kwargs["max_range_m"]))
        return pd.DataFrame([row])

    monkeypatch.setattr(pipeline, "run_search", fake_search)
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


def test_silent_audio_has_no_detections(tmp_path, capsys):
    sp = audio.compute_spectrogram(np.zeros(4000 * 8, np.float32), 4000)
    assert tracks.detect_events(sp, 100, 130, workers=1) == []
    spec, out = tmp_path / "silence.npz", tmp_path / "events.json"
    sp.save(spec)
    cli.main(["detect", str(spec), "--band", "100", "130", "--out", str(out)])
    assert json.loads(out.read_text()) == []
    assert "no flyovers found" in capsys.readouterr().out


def test_min_score_is_applied_to_refined_scores(monkeypatch):
    monkeypatch.setattr(tracks, "_scan_window", lambda args: [(10, 120, 100, 1000, 100), (2, 120, 100, 1000, 300)])
    monkeypatch.setattr(tracks, "fit_event", lambda *a, init, **k: _event(init[3], -1 if init[3] == 100 else 8))
    events = tracks.detect_events(_spec(), 100, 130, top=2, workers=1, min_score=5)
    assert [e.t_cpa for e in events] == [300]
    assert tracks.detect_events(_spec(), 100, 130, top=2, workers=1, min_score=9) == []


def test_missing_ffmpeg_has_actionable_library_and_cli_error(monkeypatch, capsys):
    def missing(*a, **k):
        raise FileNotFoundError("ffmpeg")
    monkeypatch.setattr(audio.subprocess, "run", missing)
    with pytest.raises(audio.FFmpegNotFoundError, match="brew install ffmpeg"):
        audio.load_audio("recording.wav")
    with pytest.raises(SystemExit) as exc:
        cli.main(["spectrogram", "recording.wav", "out.npz"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ffmpeg was not found on PATH" in err and "Traceback" not in err
