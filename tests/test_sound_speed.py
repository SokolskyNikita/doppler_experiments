"""The sound-speed input (PLAN Phase 2 item 2's engineering outcome): CLI options, the case field, the runner."""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dopplertrack import adsb, atmosphere, audio, cache, cli, doppler, pipeline, tracks
from dopplertrack.search import Grid, Segment, cpa_fingerprint

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import cases, runner  # noqa: E402


def test_the_default_and_the_mid_height_temperature():
    assert doppler.speed_of_sound() == doppler.speed_of_sound(15.0) == pytest.approx(340.275, abs=0.001)
    assert atmosphere.mid_height_temperature(15.0, 2000.0) == pytest.approx(8.5)
    assert atmosphere.mid_height_temperature(15.0, 0.0) == 15.0


def _spec():
    t, f = np.arange(0, 601, 0.5), np.arange(40, 251, 1.0)
    return audio.Spectrogram(t, f, np.zeros((len(f), len(t)), np.float32))


def _event(t):
    return tracks.EventFit(t, t - 3, 120, 100, 1000, t - 30, t + 30, 4, 150, 90)


@pytest.fixture
def inputs(tmp_path):
    spec = tmp_path / "spec.npz"
    _spec().save(spec)
    files = [tmp_path / "ev1.json", tmp_path / "ev2.json"]
    for f, ev in zip(files, (_event(100), _event(400))):
        f.write_text(json.dumps(ev.to_dict()))
    traces = tmp_path / "traces.npz"
    adsb.save_traces([], traces)
    results = tmp_path / "search.csv"
    pd.DataFrame([dict(lat=40, lon=-74, lat0=40, lon0=-74, seg1=0, seg2=1, icao1="a", icao2="b", t_heard1=1e9,
                       score=10, shift=0)]).to_csv(results, index=False)
    return spec, files, traces, results


@pytest.mark.parametrize("command", ["search", "refine", "search-single", "detect", "fit"])
@pytest.mark.parametrize("flags, c", [([], None), (["--temperature", "15"], doppler.speed_of_sound(15.0)),
                                      (["--temperature", "30"], doppler.speed_of_sound(30.0)),
                                      (["--temperature", "15", "--aircraft-height", "2000"], doppler.speed_of_sound(8.5))])
def test_the_cli_passes_c_only_when_a_temperature_is_given(tmp_path, monkeypatch, inputs, command, flags, c):
    spec, files, traces, results = inputs
    seen = []
    row = pd.DataFrame([dict(lat=40, lon=-74, lat0=40, lon0=-74, seg1=0, seg2=1, icao1="a", icao2="b",
                             t_heard1=1e9, score=10, shift=0)])

    def capture(*a, **kw):
        seen.append(kw)
        return (row, []) if not kw.get("_refine") else row

    monkeypatch.setattr(pipeline, "run_search", capture)
    monkeypatch.setattr(pipeline, "run_single_search", capture)
    monkeypatch.setattr(pipeline, "refine", lambda *a, **kw: (seen.append(kw), row)[1])
    monkeypatch.setattr(pipeline, "segments_for_search", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "relocate_row", lambda r, *a: r)
    monkeypatch.setattr(cache, "cached_detections", lambda sp, produce, **kw: (seen.append(kw), [])[1])
    monkeypatch.setattr(cli, "fit_event", lambda *a, **kw: (seen.append(kw), _event(100))[1])
    common = ["--traces", str(traces), "--bbox", "40", "40.01", "-74", "-73.99", "--no-dem", "--out", str(tmp_path / "o")]
    args = {"search": ["search", str(spec), "--events", *map(str, files), *common],
            "refine": ["refine", str(spec), str(results), "--events", *map(str, files), *common],
            "search-single": ["search-single", str(spec), "--event", str(files[0]), "--utc", "1000000000", *common],
            "detect": ["detect", str(spec), "--band", "100", "130"],
            "fit": ["fit", str(spec), "--window", "70", "130", "--band", "90", "160"]}[command]
    cli.main(args + flags)
    (kw,) = seen
    if c is None:
        assert "c" not in kw            # the default path is today's, untouched
    else:
        assert kw["c"] == pytest.approx(c)


def test_aircraft_height_needs_a_temperature(inputs, capsys):
    spec = inputs[0]
    with pytest.raises(SystemExit):
        cli.main(["fit", str(spec), "--window", "70", "130", "--band", "90", "160", "--aircraft-height", "1000"])


def test_a_changed_speed_of_sound_changes_the_cpa_fingerprint():
    grid = Grid.points([40.0], [-74.0], [0.0])
    seg = Segment(0, "a", np.arange(3.0), np.zeros((3, 3)), np.ones(3))
    assert cpa_fingerprint(grid, [seg], 12000.0, doppler.speed_of_sound(15.0)) != \
        cpa_fingerprint(grid, [seg], 12000.0, doppler.speed_of_sound(20.0))


def _case(**weather):
    case = copy.deepcopy(cases.load_cases()["cases"][0])
    case["weather"].update(weather)
    return case


def test_the_case_weather_field_is_validated():
    files = cases.manifest_files()
    cases.validate_case(_case(), files)                        # null throughout: today's default
    with pytest.raises(cases.CaseError, match="weather.source"):
        cases.validate_case(_case(temperature_c=21.0, station="KFRG", station_distance_km=12.0), files)
    with pytest.raises(cases.CaseError, match="needs a temperature"):
        cases.validate_case(_case(aircraft_height_m=1000.0), files)
    cases.validate_case(_case(temperature_c=21.0, source="IEM ASOS", station="KFRG", station_distance_km=12.0,
                              aircraft_height_m=1000.0), files)


def test_the_runner_passes_the_case_speed_of_sound_and_records_it():
    kw, rec = runner.sound_speed(_case())
    assert kw == {} and rec["c_m_s"] == doppler.speed_of_sound() and rec["temperature_c"] is None
    kw, rec = runner.sound_speed(_case(temperature_c=21.0, source="IEM ASOS", station="KFRG", station_distance_km=12.0,
                                       aircraft_height_m=1000.0))
    assert kw["c"] == pytest.approx(doppler.speed_of_sound(21.0 - 3.25)) == rec["c_m_s"]
    assert rec["effective_temperature_c"] == pytest.approx(17.75) and rec["station"] == "KFRG"
    d = runner.Draft(cases.blind_case("oyster-bay"), {}, "saved-fit", lambda m: None)
    assert d.c_kw == {} and d.params["speed_of_sound"]["basis"].startswith("the pipeline's default")
