"""The recipes' parameters (research readiness R2): every profile resolves to what the code used before R2, every
alternative method choice runs through its recipe on a synthetic case, and unknown parameter names are refused by
the CLI, the benchmark and the collective command."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dopplertrack.components.detection.custom_contrast_zscore import OFF_CURVE
from dopplertrack.core.geometry import enu_to_lla
from dopplertrack.core.propagation import curve_from_trajectory
from dopplertrack.data.region_loading import save_traces
from dopplertrack.data.trajectories import Trace
from dopplertrack.methods.collective import search as collective
from dopplertrack.methods.collective.parameters import CollectiveParameters, resolve_collective
from dopplertrack.methods.grid_pair import pipeline, runner as locate
from dopplertrack.methods.grid_pair.parameters import choices, from_record, resolve
from dopplertrack.methods.parameters import arange_grid, geometric_grid, inclusive_grid, to_dict
import dopplertrack.components.search.segments as segments
import dopplertrack.components.stft as stft
import dopplertrack.components.windows as windows

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dopplertrack.evaluation import cases, runner as bench  # noqa: E402


def _at(params, path):
    for part in path.split("."):
        params = getattr(params, part)
    return params


# What 1ad8d8c (R1) ran, by setting: the keyword defaults of the functions the recipe called (detect_events,
# pair_grid_search, refine, pick_flight, EventWindow, the hypotheses' constants, spectrogram_from_blocks) ...
R1_LIBRARY = {
    "spectrogram.nperseg": 8192, "spectrogram.hop_s": 0.25, "spectrogram.fmin": 40.0, "spectrogram.fmax": 450.0,
    "spectrogram.nfft": None, "spectrogram.whitening": "whiten_time", "spectrogram.whiten_window_s": 600.0,
    "spectrogram.bg_hz": 10.0, "spectrogram.spectral_floor": 0.0,
    "detection.harmonics": 1, "detection.window_s": 240.0, "detection.step_s": 120.0, "detection.f0_step_hz": 2.0,
    "detection.t0_step_s": 2.0, "detection.n_curve": 80, "detection.top": 20, "detection.per_window": 3,
    "detection.min_sep_s": 60.0, "detection.min_score": 0.0, "detection.refine": True,
    "detection.refine_speed_bounds_mps": (35.0, 200.0), "detection.refine_slant_range_bounds_m": (200.0, 15000.0),
    "detection.refine_half_window_s": 120.0, "detection.objective": "contrast", "detection.statistic": "contrast",
    "detection.contrast_df": 0.04, "detection.sweep_floor": 0.15, "detection.off_curve": OFF_CURVE,
    "event_source.source": "saved_fits", "event_source.report_top2": False, "event_source.top_k": 5,
    "event_source.usable_valid_share": 0.5, "event_source.day_slack_s": 600.0, "event_source.gate_pad_s": 300.0,
    "event_source.start_utc": None, "event_source.start_tol_s": None,
    "gates.time_gate_s": 6.0, "gates.single_event_time_gate_s": 30.0, "gates.speed_gate_fraction": 0.35,
    "gates.slant_range_gate_factors": (0.4, 2.5), "gates.negative_information_distance_m": 6000.0,
    "gates.negative_information_margin_s": 40.0, "gates.max_range_m": 12000.0, "gates.time_convention": "heard",
    "gates.event_gate": "rectangular", "gates.clock_anchor": "heard_cpa", "gates.inflection_tol_s": None,
    "gates.inflection_window_s": 60.0, "gates.inflection_smooth_s": 3.0, "gates.inflection_flat_ratio": 1.03,
    "gates.alive_pad_s": 300.0, "gates.harmonics": (1, 1),
    "hypotheses.max_optima": 3, "hypotheses.ls_delta_chi2": 3.84 * 3.0, "hypotheses.null_delta": 2.0,
    "hypotheses.model_error_factor": 3.0, "hypotheses.min_sep_s": 20.0, "hypotheses.speed_bounds_mps": (10.0, 300.0),
    "hypotheses.slant_range_bounds_m": (100.0, 30000.0), "hypotheses.tau_reach_s": 60.0,
    "hypotheses.ls_z_span_min": 0.5,
    "scoring.normalisation": "raw", "scoring.crop_pad_s": 40.0, "scoring.curve_samples": 160, "scoring.null_n": 1000,
    "refinement.spacing_m": 50.0, "refinement.half_width_m": 400.0, "refinement.rank": 1,
    "refinement.alive_pad_s": 300.0, "grid.spacing_m": 200.0, "grid.dem": True,
    "air.temperature_c": None, "air.speed_of_sound_m_s": None,
}
# ... and what each profile set on top: locate's LocateConfig defaults and comparable searches, raw-audio's
# PROFILES["raw-audio"] (detect's band, top, harmonics and window, then top2 with one harmonic per event).
R1_PROFILES = {
    "saved-fit": {"event_source.source": "saved_fits"},
    "raw-audio": {"event_source.source": "top2", "detection.band_hz": (60.0, 300.0), "detection.top": 10,
                  "detection.harmonics": 1, "detection.window_s": 240.0, "gates.harmonics": (1, 1)},
    "locate": {"event_source.source": "comparable_pairs", "event_source.report_top2": False,
               "detection.band_hz": (60.0, 300.0), "detection.top": 10, "detection.harmonics": 1,
               "detection.window_s": 240.0, "grid.spacing_m": 200.0, "gates.max_range_m": 12000.0,
               "gates.time_gate_s": 6.0, "gates.speed_gate_fraction": 0.35, "gates.slant_range_gate_factors": (0.4, 2.5),
               "gates.negative_information_distance_m": 6000.0, "refinement.spacing_m": 50.0,
               "refinement.half_width_m": 600.0, "grid.dem": True, "gates.harmonics": (1, 1),
               "air.temperature_c": None, "air.speed_of_sound_m_s": None},
}


@pytest.mark.parametrize("profile", sorted(R1_PROFILES))
def test_each_profile_resolves_to_what_the_code_used_before_r2(profile):
    p = resolve(profile)
    want = {**R1_LIBRARY, **R1_PROFILES[profile]}
    assert {k: _at(p, k) for k in want} == want
    assert set(R1_PROFILES) == set(bench.PROFILES)
    # the grids the dataclass stores as (start, stop, step) are R1's literal arrays, exactly
    assert np.array_equal(arange_grid(p.detection.speed_grid_mps), np.arange(40, 170, 13.0))
    assert np.array_equal(geometric_grid(p.detection.slant_range_grid_m), np.geomspace(400, 9000, 10))
    assert np.array_equal(arange_grid(p.hypotheses.coarse_speed_grid_mps), np.arange(40, 170, 13.0))
    assert np.array_equal(inclusive_grid(p.scoring.shift_grid_s), np.arange(-8, 8.01, 0.5))
    assert np.array_equal(inclusive_grid(p.scoring.f0_scale_grid), np.arange(0.95, 1.0501, 0.005))
    assert np.array_equal(inclusive_grid(p.refinement.extra_f0_scale_grid), np.arange(0.95, 1.0501, 0.005))
    assert from_record(json.loads(json.dumps(to_dict(p)))) == p          # the record's block resolves back


def test_the_case_layer_is_the_case_search_and_refine_blocks():
    case = cases.blind_case("oyster-bay")
    s, rf = case["search"], case["refine"]
    p = bench.case_resolved(case, "saved-fit")
    assert (p.gates.time_gate_s, p.gates.speed_gate_fraction, list(p.gates.slant_range_gate_factors)) == \
        (s["tol_s"], s["v_tol"], list(s["d_tol"]))
    assert p.gates.negative_information_distance_m == s["silence_d_m"] and list(p.gates.harmonics) == s["harmonics"]
    assert (p.refinement.rank, p.refinement.spacing_m, p.refinement.half_width_m) == (rf["rank"], rf["spacing_m"], rf["half_m"])
    assert bench.case_resolved(case, "raw-audio").gates.harmonics == (1, 1)
    gated = bench.case_resolved(case, "locate", clock_gate=True)
    assert gated.event_source.start_tol_s == float(case["start_time"]["uncertainty_s"])
    # the explicit overrides come last and win
    assert bench.case_resolved(case, "saved-fit", {"time_gate_s": 9.0}).gates.time_gate_s == 9.0


def test_the_collective_defaults_are_what_the_code_used_before_r2():
    from dopplertrack.components.scoring.sweeps import coarse_sweep, fine_sweep
    p = CollectiveParameters()
    assert collective._sweep(p.scoring.coarse_sweep, p) == coarse_sweep()
    assert collective._sweep(p.scoring.fine_sweep, p) == fine_sweep()
    assert repr(collective._sweep(p.scoring.coarse_sweep, p)) == repr(coarse_sweep())      # the nulls' seed
    assert (p.planning.coarse_m, p.planning.fine_m, p.planning.margin_sigma, p.planning.max_cells) == (1000.0, 200.0, 2.0, 20)
    assert (p.planning.mode_separation_m, p.planning.max_modes, p.null.null_n, p.max_range_m) == (2000.0, 5, 1000, 12000.0)
    assert (p.assignment.clock_bin_s, p.assignment.agree_s, p.assignment.pass_fallback) == (20.0, 6.0, 3)
    assert float(np.log1p(p.scoring.log_step)) == float(np.log1p(0.0025)) and p.scoring.sub_s == 120.0


def test_unknown_or_ambiguous_names_and_unknown_methods_are_refused():
    with pytest.raises(ValueError, match="unknown parameter names.*nope"):
        resolve(overrides={"nope": 1})
    with pytest.raises(ValueError, match="ambiguous.*spacing_m"):
        resolve(overrides={"spacing_m": 100.0})                  # the grid's and the refinement's
    with pytest.raises(ValueError, match="time_convention must be one of"):
        resolve(overrides={"time_convention": "steepest"})
    with pytest.raises(ValueError, match="unknown parameter names"):
        resolve_collective({"c": 340.0})
    assert set(choices()["gates.event_gate"]) == {"rectangular", "profile_intervals"}


def test_the_cli_the_benchmark_and_the_collective_command_refuse_unknown_names(tmp_path, capsys):
    from dopplertrack.commands.main import main
    from dopplertrack.commands.methods import main as run_method
    with pytest.raises(SystemExit):
        main(["detect", str(tmp_path / "none.npz"), "--band", "100", "130", "--param", "detection.nope=1"])
    assert "unknown parameter names" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["locate", str(tmp_path / "none.npz"), "--date", "2026-01-01", "--bbox", "40", "40.1", "-74", "-73.9",
              "--out", str(tmp_path / "o"), "--param", "tol_s=4"])
    assert "unknown parameter names" in capsys.readouterr().err
    with pytest.raises(ValueError, match="unknown parameter names"):
        bench.run_bench(["oyster-bay"], run_dir=tmp_path / "run", overrides={"silence_d_m": None})
    with pytest.raises(ValueError, match="CPA table"):
        bench.check_overrides("saved-fit", {"grid.spacing_m": 100.0})
    bench.check_overrides("locate", {"clock_gate": False, "negative_information_distance_m": None})
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"spectrogram": "s.npz", "traces": [], "bbox": [0, 1, 0, 1], "windows": [],
                                  "parameters": {"null_draws": 10}}))
    with pytest.raises(SystemExit):
        run_method(["collective", "--config", str(config), "--out", str(tmp_path / "out")])
    assert "unknown parameter names" in capsys.readouterr().err and not (tmp_path / "out").exists()


# ---- every alternative method choice through its recipe, one change at a time --------------------------------

LAT0, LON0, T0, C = 40.8765, -73.525, 1_700_000_000.0, 340.0
BOX = (LAT0 - 0.02, LAT0 + 0.02, LON0 - 0.025, LON0 + 0.025)
DAY = "2023-11-14"
# The synthetic case's base: the defaults with a small detection grid, a narrow band and short nulls, so each run is
# cheap; every alternative below is one change from this base.
BASE = {"spectrogram.hop_s": 0.5, "spectrogram.fmin": 60.0, "spectrogram.fmax": 300.0, "whiten_window_s": None,
        "detection.band_hz": (90.0, 180.0), "detection.top": 2, "detection.speed_grid_mps": (40.0, 170.0, 19.0),
        "detection.slant_range_grid_m": (400.0, 9000.0, 7), "event_source.source": "top2", "grid.dem": False,
        "grid.spacing_m": 400.0, "scoring.null_n": 60, "refinement.half_width_m": 150.0,
        "refinement.spacing_m": 75.0, "speed_of_sound_m_s": C}
GRID_PAIR_ALTERNATIVES = [("event_source.source", "saved_fits"), ("event_source.source", "comparable_pairs"),
                          ("detection.statistic", "custom_rescore_zscore"), ("detection.statistic", "rescore_surrogate"),
                          ("gates.event_gate", "profile_intervals"), ("scoring.normalisation", "pair_zscore"),
                          ("gates.time_convention", "emission"), ("gates.clock_anchor", "doppler_inflection"),
                          ("spectrogram.whitening", "whiten_frequency")]
COLLECTIVE_ALTERNATIVES = [("scoring.view", "event_window"), ("spectrogram.whitening", "whiten_frequency")]


def test_the_alternatives_cover_every_method_choice():
    base = resolve(overrides=BASE)
    for path, names in choices().items():
        if path == "detection.objective":
            continue                                       # a fit objective, not a seam: covered by test_fit_objective
        run = {v for k, v in GRID_PAIR_ALTERNATIVES if k == path}
        assert run == set(names) - {_at(base, path)}, path
    assert {v for k, v in COLLECTIVE_ALTERNATIVES if k == "scoring.view"} == set(collective.VIEWS) - {"log_view"}
    assert list(collective.ASSIGNMENTS) == ["greedy_assignment"]           # one entry until PLAN.md G4


def _trace(icao, t, enu, gs):
    lat, lon, alt = enu_to_lla(enu[:, 0], enu[:, 1], enu[:, 2], LAT0, LON0)
    return Trace(icao, None, "C172", "synthetic", t, lat, lon, alt, np.full_like(t, gs), np.zeros(len(t), bool))


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    """Two flights heard at the origin over 30 minutes, as audio samples, their traces with coverage metadata, and
    the collective windows on them; the detections cache is the test's own."""
    d = tmp_path_factory.mktemp("r2")
    mp = pytest.MonkeyPatch()
    mp.setenv("DOPPLERTRACK_CACHE", str(d / "cache"))
    t1 = T0 + np.arange(0, 900, 5.0)
    enu1 = np.stack([110.0 * (t1 - (T0 + 300)), np.full_like(t1, 2500.0), np.full_like(t1, 1500.0)], -1)
    t2 = T0 + np.arange(900, 1800, 5.0)
    tau = t2 - (T0 + 1220)
    enu2 = np.stack([3000.0 + 0.02 * tau ** 2, 95.0 * tau, np.full_like(t2, 1200.0)], -1)
    traces = [_trace("aaa001", t1, enu1, 110 / 0.5144), _trace("aaa002", t2, enu2, 95 / 0.5144)]
    sr = 4000
    tt = np.arange(0, 1800, 1 / sr)
    x = 0.4 * np.random.default_rng(1).standard_normal(len(tt)).astype(np.float32)
    wins = []
    for seg, f0 in zip(segments.build_segments(traces, LAT0, LON0), (120.0, 130.0)):
        to, ratio, _ = curve_from_trajectory(seg.t, seg.enu, np.zeros(3), f0=1.0, c=C)
        finst = np.interp(tt + T0, to, ratio, left=np.nan, right=np.nan) * f0
        m = np.isfinite(finst)
        x[m] += 0.05 * np.sin(2 * np.pi * np.cumsum(np.nan_to_num(finst, nan=0.0)) / sr)[m]
        heard = float(to[np.argmin(np.abs(ratio - 1))]) - T0
        wins.append(windows.Window(heard - 100, heard + 100, 1.03 * f0, heard + 4.0, 1.0))
    save_traces(traces, d / "traces.npz", metadata={"coverage_bbox": [39.0, 42.0, -75.0, -72.0], "date": DAY,
                                                     "covered_utc": [T0 - 80000, T0 + 6000]})
    yield {"dir": d, "x": x, "sr": sr, "traces": traces, "wins": wins, "spectrograms": {}}
    mp.undo()


def _spectrogram(synthetic, sp_params):
    key = repr(sp_params)
    if key not in synthetic["spectrograms"]:
        sp = stft.compute_spectrogram(synthetic["x"], synthetic["sr"], **sp_params.stft_kwargs())
        path = synthetic["dir"] / f"spec{len(synthetic['spectrograms'])}.npz"
        sp.save(path)
        synthetic["spectrograms"][key] = (sp, path)
    return synthetic["spectrograms"][key]


def _saved_fits(synthetic):
    """The two detections of the base, standing in for a case's saved fits."""
    p = resolve(overrides=BASE)
    sp, _ = _spectrogram(synthetic, p.spectrogram)
    found, _ = pipeline.detect(sp, p, workers=1)
    return sorted(found[:2], key=lambda e: e.t_cpa)


@pytest.mark.parametrize("path, value", GRID_PAIR_ALTERNATIVES, ids=[f"{k}={v}" for k, v in GRID_PAIR_ALTERNATIVES])
def test_grid_pair_runs_with_each_alternative_method(synthetic, path, value):
    from dopplertrack.components.search.grid import Grid
    p = resolve(overrides={**BASE, path: value})
    assert _at(p, path) == value and _at(resolve(overrides=BASE), path) != value
    sp, spec = _spectrogram(synthetic, p.spectrogram)
    if p.event_source.source == "saved_fits":          # the bench's saved-fit path: search, then refine the winner
        ev1, ev2 = _saved_fits(synthetic)
        grid = Grid.make(*BOX, p.grid.spacing_m, None)
        res, segs = pipeline.pair_grid_search(sp, ev1, ev2, synthetic["traces"], grid, p, progress=False, workers=1)
        assert res.attrs["funnel"]["scored"] == len(res) and len(res), res.attrs["funnel"]
        row = res.iloc[0].copy()
        row["lat0"], row["lon0"] = grid.lat0, grid.lon0
        fine = pipeline.refine(sp, ev1, ev2, segs, row, p, workers=1)
        assert len(fine) and np.isfinite(fine.score.iloc[0])
        if value == "pair_zscore":
            assert "raw_score" in res and set(res.attrs["null"]) == {"event1", "event2"}
        if value == "profile_intervals":
            assert "event1_hypotheses" in res.attrs["funnel"]
        if value == "doppler_inflection":
            assert "steepest_fall" in res.attrs["funnel"]
        if value == "emission":
            assert "emission_gate" in res.attrs["funnel"]
        return
    out = locate.locate(spec, DAY, BOX, [synthetic["dir"] / "traces.npz"], p, locate.RunSettings(workers=1),
                        out_dir=synthetic["dir"] / f"locate-{path}-{value}")
    rec = out.record
    assert not rec["execution"]["errors"] and rec["verdict"]["outcome"] in ("ambiguous", "insufficient_evidence")
    assert from_record(rec["provenance"]["parameters"]["resolved"]) == p
    assert rec["pair_rules"] and rec["pair_rules"][0]["rule"] == locate.RULE_NAMES[p.event_source.source]
    assert rec["events"], rec["verdict"]


@pytest.mark.parametrize("path, value", COLLECTIVE_ALTERNATIVES, ids=[f"{k}={v}" for k, v in COLLECTIVE_ALTERNATIVES])
def test_collective_runs_with_each_alternative_method(synthetic, path, value):
    base = {"spectrogram.hop_s": 0.5, "spectrogram.fmin": 60.0, "spectrogram.fmax": 300.0, "whiten_window_s": None,
            "speed_of_sound_m_s": C, "scoring.f0_span": 0.04, "null.null_n": 60}
    p = resolve_collective({**base, path: value})
    assert _at(p, path) == value and _at(resolve_collective(base), path) != value
    sp, _ = _spectrogram(synthetic, p.spectrogram)
    out = collective.collective_detection(sp, synthetic["wins"], synthetic["traces"],
                                          (LAT0 - 0.03, LAT0 + 0.03, LON0 - 0.035, LON0 + 0.035), p, workers=1,
                                          log=lambda m: None)
    assert out["parameters"] == to_dict(p) and out["winner"] is not None, out.get("reason")
    assert pd.notna(out["winner"]["Z"]) and out["winner"]["Z"] > 0
