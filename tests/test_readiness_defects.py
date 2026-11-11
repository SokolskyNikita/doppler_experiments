"""Research readiness R5: one test per defect that has no natural home in another file. The Viterbi decoder is in
test_lltrack.py; jobs=1 against jobs=N of the CPA build in test_cpa_build.py."""
import ast
import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import dopplertrack.components.planning.fine_grid as fine_grid
import dopplertrack.components.planning.modes as modes
import dopplertrack.components.scoring.point_score as point_score
import dopplertrack.components.search.cpa_table as cpa_table
import dopplertrack.components.stft as stft
import dopplertrack.data.day_mapping as day_mapping
import dopplertrack.data.trace_parsing as trace_parsing
from dopplertrack.components.search.grid import Grid
from dopplertrack.components.windows import Window
from dopplertrack.data.coverage import ScanReport
from dopplertrack.data.providers import adsblol
from dopplertrack.data.trajectories import Trace
from dopplertrack.methods.collective import merge, null, search, units
from dopplertrack.methods.collective.parameters import CollectiveParameters, resolve_collective
from dopplertrack.methods.grid_pair import runner

REPO = Path(__file__).resolve().parents[1]
BOX = (40.0, 40.03, -74.0, -73.96)


# ---- trace parsing (upstream's fixes) and file handles --------------------------------------------------------

def test_a_trace_document_that_is_not_an_object_or_has_dict_rows_is_malformed_not_a_crash():
    for doc in ([1, 2], "text", {"timestamp": 0, "trace": [{"lat": 40, "lon": -74}]}):
        with pytest.raises(trace_parsing.TRACE_ERRORS):
            trace_parsing.parse_trace_bytes(json.dumps(doc).encode())
    assert AttributeError not in trace_parsing.TRACE_ERRORS        # it would hide a programming error
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        raw = b"[1, 2]"
        ti = tarfile.TarInfo("traces/ab/trace_full_abcdef.json"); ti.size = len(raw); tf.addfile(ti, io.BytesIO(raw))
    report = ScanReport()
    assert list(adsblol.iter_tar_traces(io.BytesIO(buf.getvalue()), (0, 1, 0, 1), report=report)) == []
    assert (report.seen, report.malformed, report.empty) == (1, 1, 0)


def _calls(tree, parents):
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def test_no_file_is_opened_without_being_closed():
    """Every bare open() in the package is a with-statement's context or assigned to a name (closed by hand)."""
    bad = []
    for path in sorted((REPO / "src").rglob("*.py")):
        parents: dict = {}
        for call in _calls(ast.parse(path.read_text()), parents):
            if isinstance(call.func, ast.Name) and call.func.id == "open" \
                    and not isinstance(parents[call], (ast.withitem, ast.Assign)):
                bad.append(f"{path.relative_to(REPO)}:{call.lineno}")
    assert not bad, bad


def test_no_raw_process_pool_outside_the_wrapper():
    """Pools come from runtime/parallel.py (spawn, one thread per worker). The dated scripts are records and stay."""
    bad = []
    for top in ("src", "bench", "tools", "tests"):
        for path in sorted((REPO / top).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel == "src/dopplertrack/runtime/parallel.py" or rel.startswith("tools/experiments/"):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                names = ([node.id] if isinstance(node, ast.Name) else [node.attr] if isinstance(node, ast.Attribute)
                         else [a.name for a in node.names] if isinstance(node, ast.ImportFrom) else [])
                if "ProcessPoolExecutor" in names or ("Pool" in names and not isinstance(node, ast.Name)):
                    bad.append(f"{rel}:{node.lineno}")
    assert not bad, bad


# ---- coverage preflight ---------------------------------------------------------------------------------------

def test_separated_coverage_intervals_stay_apart_and_their_gap_is_reported():
    metas = [{"covered_utc": [0.0, 100.0]}, {"covered_utc": [300.0, 500.0]}, {"covered_utc": [90.0, 200.0]}]
    covered = runner._covered_days(["a", "b", "c"], metas, [])
    assert covered == [(0.0, 200.0), (300.0, 500.0)]                # touching or overlapping join; separated don't
    assert runner._coverage_gaps(covered, (50.0, 450.0)) == [(200.0, 300.0)]
    assert runner._coverage_gaps(covered, (310.0, 450.0)) == []
    assert runner._coverage_gaps(covered, (-10.0, 600.0)) == [(-10.0, 0.0), (200.0, 300.0), (500.0, 600.0)]
    assert runner._coverage_gaps([], (1.0, 2.0)) == [(1.0, 2.0)]
    days = runner._covered_days(["a", "b"], [{"date": "2026-09-08"}, {"date": "2026-09-09"}], [])
    assert len(days) == 1 and days[0][1] - days[0][0] == 2 * 86400.0   # consecutive days are one interval


# ---- control-day mapping --------------------------------------------------------------------------------------

def test_a_control_day_is_mapped_onto_the_recording_date_at_the_same_time_of_day():
    assert day_mapping.day_shift_s("2025-05-28", "2025-06-01") == 4 * 86400.0
    assert day_mapping.day_shift_s("2025-06-01", "2025-05-28") == -4 * 86400.0
    t = 1_748_390_400.0 + np.array([10.0, 20.0])                    # 2025-05-28 00:00:10 UTC
    tr = Trace("abc123", None, None, None, t, np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2, bool))
    out = day_mapping.map_to_day([tr], "2025-05-28", "2025-06-01")[0]
    assert np.array_equal(out.t % 86400.0, t % 86400.0) and np.array_equal(out.t - t, [345600.0, 345600.0])
    assert np.array_equal(tr.t, t) and out.icao == "abc123"         # the input is untouched
    with pytest.raises(ValueError):
        day_mapping.day_shift_s("2025-05-28", "yesterday")


# ---- CPA build and empty inputs -------------------------------------------------------------------------------

def test_empty_inputs_are_defined():
    grid = Grid.make(*BOX, 1000.0)
    for workers in (1, 2):                                          # no segments: an empty table, with its columns
        cpa = cpa_table.cpa_table(grid, [], 5000.0, 340.0, workers=workers)
        assert len(cpa) == 0 and list(cpa.columns) == cpa_table.CPA_COLUMNS
    sp = stft.compute_spectrogram(np.zeros(4000 * 60, np.float32), 4000, nperseg=4096, hop_s=0.5, fmin=60, fmax=300,
                                  whiten_window_s=None)
    wins = [Window(5.0, 25.0, 120.0, 15.0, 1.0), Window(30.0, 50.0, 130.0, 40.0, 1.0)]
    quiet = dict(workers=1, log=lambda m: None)
    none = search.collective_detection(sp, [], [], BOX, **quiet)
    assert none["winner"] is None and none["reason"] == "no windows were given"
    empty = search.collective_detection(sp, wins, [], BOX, **quiet)
    assert empty["winner"] is None and empty["reason"] == "no flight pass within range of the box"
    assert empty["counts"]["coarse_cpa_rows"] == 0
    for out in (none, empty):                                       # still a whole, identified output
        assert out["statistic"] == search.STATISTIC and out["statistic_identity"]["name"] == search.STATISTIC
        json.dumps(out, allow_nan=False)


def test_fine_points_without_terrain_are_left_out_like_coarse_ones():
    coarse = Grid.make(*BOX, 1000.0)
    k = int(round(fine_grid.COARSE_M / fine_grid.FINE_M)) ** 2
    def half(lat, lon):
        return np.where(lat > coarse.lat[0], 12.0, np.nan)
    fine, cell = fine_grid.fine_grid(coarse, [0, 1], half, coarse.lat0, coarse.lon0)
    assert 0 < len(fine) < 2 * k and len(cell) == len(fine) and np.all(fine.elev == 12.0)
    none, cell = fine_grid.fine_grid(coarse, [0], lambda lat, lon: np.full(len(lat), np.nan), coarse.lat0, coarse.lon0)
    assert len(none) == 0 and len(cell) == 0
    flat, _ = fine_grid.fine_grid(coarse, [0, 1], None, coarse.lat0, coarse.lon0)
    assert len(flat) == 2 * k


# ---- the mode rule's parameters -------------------------------------------------------------------------------

def _peak(lat, lon, z, clock):
    return dict(lat=lat, lon=lon, Z=z, clock_audio_minus_unix=clock, n_matched=2)


def test_the_mode_rule_separates_by_clock_only_when_asked():
    peaks = [_peak(40.0, -74.0, 9.0, 0.0), _peak(40.0, -74.0, 8.0, 500.0), _peak(40.05, -74.0, 7.0, 0.0)]
    assert [m["Z"] for m in modes.distinct_modes(peaks, 2000.0, 5)] == [9.0, 7.0]                 # today's rule
    assert [m["Z"] for m in modes.distinct_modes(peaks, 2000.0, 5, 60.0)] == [9.0, 8.0, 7.0]
    assert [m["Z"] for m in modes.distinct_modes(peaks, 2000.0, 5, 600.0)] == [9.0, 7.0]
    assert [m["Z"] for m in modes.distinct_modes(peaks, 2000.0, 2, 60.0)] == [9.0, 8.0]


def test_a_point_can_keep_a_second_clock_that_shares_no_match_with_its_first():
    rows = [(0, 0, 0, 1000.0, 5.0, 10.0), (0, 1, 1, 2000.0, 4.0, 10.5),          # two windows agreeing near b = 10
            (0, 2, 0, 3000.0, 3.0, 400.0), (0, 3, 1, 4000.0, 2.5, 401.0)]        # and again near b = 400
    scored = pd.DataFrame(rows, columns=["gidx", "seg", "w", "t_heard", "z", "b"]).assign(s=1.0, f0_scale=1.0)
    one = point_score.point_scores(scored, 2)
    assert len(one) == 1 and one.Z.iloc[0] == 9.0
    two = point_score.point_scores(scored, 2, clocks=2)
    assert list(two.Z) == [9.0, 5.5] and abs(two.b.iloc[1] - 400.0) < 6.0
    assert len(point_score.point_scores(scored, 2, clocks=5)) == 2               # the neighbouring bins are not clocks


def test_the_mode_rule_defaults_are_the_rule_as_it_ran():
    pl = CollectiveParameters().planning
    assert (pl.mode_clock_separation_s, pl.clocks_per_point, pl.merge_modes) == (None, 1, "best_unit")
    with pytest.raises(ValueError, match="mode_clock_separation_s"):
        resolve_collective({"clocks_per_point": 2})
    with pytest.raises(ValueError, match="merge_modes"):
        resolve_collective({"merge_modes": "some"})
    assert resolve_collective({"clocks_per_point": 2, "mode_clock_separation_s": 60.0}).planning.clocks_per_point == 2


# ---- the statistic identity, complete units, merging and the null ---------------------------------------------

def test_the_statistic_identity_follows_the_parameters_and_names_the_label():
    a, b = search.statistic_identity(CollectiveParameters()), search.statistic_identity(resolve_collective({}))
    assert a == b and a["name"] == search.STATISTIC and len(a["code_sha256"]) == 64
    other = search.statistic_identity(resolve_collective({"null_n": 999}))
    assert other["code_sha256"] == a["code_sha256"] and other["parameters_sha256"] != a["parameters_sha256"]
    assert other["id"] != a["id"]
    assert search.statistic_label(a) == f"{search.STATISTIC}-{a['id'][:12]}"


WINS = [Window(5.0, 25.0, 120.0, 15.0, 1.0)]


def _result(ranks, z, params=None, kept=3, modes_=None, control=None, lat=40.01):
    p = params or CollectiveParameters()
    r = dict(statistic=search.STATISTIC, statistic_identity=search.statistic_identity(p),
             domain=search.search_domain(WINS, BOX, None), coarse_map=dict(lat=[40.0], lon=[-74.0], Z=[5.0], clock=[0.0], n_matched=[1]),
             counts=dict(fine_points=25 * len(ranks), fine_cells=len(ranks)), walls={}, windows=[w.__dict__ for w in WINS],
             sweeps={}, parameters=p.to_dict(), margin=dict(coarse_max=5.0, kept_cells=kept),
             kept=[dict(rank=i, lat=40.0, lon=-74.0 + i / 100, Z=5.0 - i) for i in range(kept)], fine_ranks=list(ranks))
    if z is None:
        return dict(r, winner=None, reason="no fine point has a window above its null")
    winner = dict(lat=lat, lon=-74.0, Z=z, clock_audio_minus_unix=-100.0, n_matched=1, windows=[], voters=[])
    r.update(winner=winner, modes=modes_ or [_peak(lat, -74.0, z, -100.0)],
             fine_cells=[dict(coarse_lat=40.0, coarse_lon=-74.0, lat=lat, lon=-74.0, Z=z)], coarse_max=5.0)
    if control:
        r["control"] = control
    return r


def _unit(tmp_path, name, result, traces=("t1",), spectrogram="s1"):
    out = tmp_path / name
    units.start_unit(out, {"method": "collective", "inputs": {"spectrogram": spectrogram, "traces": list(traces)},
                           "statistic_identity": result.get("statistic_identity")})
    units.finish_unit(out, result)
    return out


def test_merging_takes_only_complete_units_covering_every_kept_cell_once(tmp_path):
    a = _unit(tmp_path, "a", _result([0], 6.0, lat=40.01))
    b = _unit(tmp_path, "b", _result([1, 2], 7.5, lat=40.02))
    merged = merge.merge_units([a, b])
    assert merged["winner"]["Z"] == 7.5 and merged["fine_ranks"] == [0, 1, 2]
    assert [c["Z"] for c in merged["fine_cells"]] == [7.5, 6.0] and merged["counts"]["fine_points"] == 75
    assert merged["statistic_identity"] == search.statistic_identity(CollectiveParameters())
    assert [u["fine_ranks"] for u in merged["merged_from"]] == [[0], [1, 2]]
    assert [m["Z"] for m in merged["modes"]] == [7.5]               # best_unit: the winning unit's own list
    with pytest.raises(units.IncompleteUnit, match=r"missing ranks \[1, 2\]"):
        merge.merge_units([a])
    with pytest.raises(units.IncompleteUnit, match=r"repeated ranks \[0\]"):
        merge.merge_units([a, b, _unit(tmp_path, "a2", _result([0], 6.0))])
    # what the dated merge accepted: a result.json with no completion marker
    (b / "completed.json").unlink()
    with pytest.raises(units.IncompleteUnit, match="no completed.json"):
        merge.merge_units([a, b])
    c = _unit(tmp_path, "c", _result([1, 2], 7.5))
    (c / "result.json").write_text((c / "result.json").read_text().replace("7.5", "9.5"))
    with pytest.raises(units.IncompleteUnit, match="recorded hash"):
        merge.merge_units([a, c])
    old = _result([1, 2], 7.5); del old["statistic_identity"]
    with pytest.raises(units.IncompleteUnit, match="no statistic identity"):
        merge.merge_units([a, _unit(tmp_path, "old", old)])


def test_merging_refuses_units_of_another_statistic_or_search(tmp_path):
    a = _unit(tmp_path, "a", _result([0], 6.0))
    other = resolve_collective({"null_n": 999})
    with pytest.raises(units.IncompleteUnit, match="statistic_identity"):
        merge.merge_units([a, _unit(tmp_path, "b", _result([1, 2], 7.5, params=other))])
    with pytest.raises(units.IncompleteUnit, match="traces"):
        merge.merge_units([a, _unit(tmp_path, "c", _result([1, 2], 7.5), traces=("t2",))])
    with pytest.raises(units.IncompleteUnit, match="different coarse stage"):
        merge.merge_units([a, _unit(tmp_path, "d", _result([1, 2, 3], 7.5, kept=4))])


def test_modes_merge_across_all_units_when_asked(tmp_path):
    p = resolve_collective({"merge_modes": "all_units"})
    a = _unit(tmp_path, "a", _result([0], 6.0, p, lat=40.01, modes_=[_peak(40.01, -74.0, 6.0, -100.0), _peak(40.2, -74.0, 5.0, -100.0)]))
    b = _unit(tmp_path, "b", _result([1, 2], 7.5, p, lat=40.012, modes_=[_peak(40.012, -74.0, 7.5, -100.0), _peak(40.5, -74.0, 4.0, -100.0)]))
    merged = merge.merge_units([a, b])
    assert merged["merge_modes"] == "all_units"
    assert [m["Z"] for m in merged["modes"]] == [7.5, 5.0, 4.0]     # a's 6.0 is within 2 km of b's 7.5
    none = merge.merge_units([_unit(tmp_path, "n1", _result([0], None, p)), _unit(tmp_path, "n2", _result([1, 2], None, p))])
    assert none["winner"] is None and "reason" in none


def _control(day):
    return dict(traffic_day=day, recording_day="2025-06-01", shift_s=day_mapping.day_shift_s(day, "2025-06-01"))


def test_the_null_refuses_missing_incomplete_and_incompatible_draws(tmp_path):
    full = [0, 1, 2]
    own = _unit(tmp_path, "own", _result(full, 9.0, modes_=[_peak(40.01, -74.0, 9.0, -100.0), _peak(40.3, -74.0, 4.0, -100.0)]))
    days = ["2025-05-28", "2025-05-29", "2025-05-30"]
    draws = [_unit(tmp_path, d, _result(full, z, control=_control(d)), traces=(d,))
             for d, z in zip(days[:2], (5.0, 6.0))]
    draws.append(_unit(tmp_path, days[2], dict(_result(full, None), control=_control(days[2])), traces=(days[2],)))
    table = null.collect_draws(own, draws, days)
    assert table["own"]["max_Z"] == 9.0 and table["own"]["second_Z"] == 4.0
    assert [r["day"] for r in table["draws"]] == days and [r["max_Z"] for r in table["draws"]][:2] == [5.0, 6.0]
    assert np.isnan(table["draws"][2]["max_Z"]) and table["recording_day"] == "2025-06-01"   # no winner: kept, as NaN
    with pytest.raises(units.IncompleteUnit, match=r"missing \['2025-05-30'\]"):
        null.collect_draws(own, draws[:2], days)                    # a missing day is not skipped
    with pytest.raises(units.IncompleteUnit, match="not asked for"):
        null.collect_draws(own, draws, days[:2])
    partial = _unit(tmp_path, "partial", _result([0], 5.0, control=_control(days[2])), traces=("x",))
    with pytest.raises(units.IncompleteUnit, match="only part of the fine stage"):
        null.collect_draws(own, [*draws[:2], partial], days)
    other = _unit(tmp_path, "other", _result(full, 5.0, resolve_collective({"null_n": 999}), control=_control(days[2])))
    with pytest.raises(units.IncompleteUnit, match="statistic_identity"):
        null.collect_draws(own, [*draws[:2], other], days)
    elsewhere = _unit(tmp_path, "elsewhere", _result(full, 5.0, control=_control(days[2])), spectrogram="s2")
    with pytest.raises(units.IncompleteUnit, match="spectrogram"):
        null.collect_draws(own, [*draws[:2], elsewhere], days)
    with pytest.raises(units.IncompleteUnit, match="no control day"):
        null.collect_draws(own, [*draws[:2], _unit(tmp_path, "plain", _result(full, 5.0))], days)
    (draws[1] / "completed.json").unlink()
    with pytest.raises(units.IncompleteUnit, match="no completed.json"):
        null.collect_draws(own, draws, days)

    path = tmp_path / "null_draws.npz"
    null.save_draws(path, table)
    ident = table["statistic_identity"]
    back = null.load_draws(path, ident)
    assert str(back["statistic"]) == search.STATISTIC and back["statistic_identity"] == ident
    assert list(back["day"]) == days and float(back["own_max_Z"]) == 9.0
    with pytest.raises(units.IncompleteUnit, match="not collective-Z"):
        null.load_draws(path, search.statistic_identity(resolve_collective({"null_n": 999})))
    bare = tmp_path / "old.npz"
    np.savez(bare, day=np.array("2025-05-28"), max_S=1.0)           # the dated export: no identity
    with pytest.raises(units.IncompleteUnit, match="names no statistic identity"):
        null.load_draws(bare, ident)


def test_the_commands_write_identified_units_and_refuse_incomplete_ones(tmp_path, capsys):
    """`run collective` with a control day, then collective-merge and collective-null over its folders. No traffic
    is near, so each search ends at once; what is checked is what the folders say and what the commands refuse."""
    from dopplertrack.commands.methods import main as run_method
    from dopplertrack.components.spectrogram import Spectrogram
    from dopplertrack.data.region_loading import save_traces
    sp = stft.compute_spectrogram(np.zeros(4000 * 60, np.float32), 4000, nperseg=4096, hop_s=0.5, fmin=60, fmax=300,
                                  whiten_window_s=None)
    Spectrogram.save(sp, tmp_path / "spec.npz")
    t = 1_748_390_400.0 + np.arange(0.0, 600.0, 5.0)                # 2025-05-28, far from the box
    far = Trace("abc123", None, None, None, t, np.full(len(t), 10.0), np.linspace(0, 1, len(t)), np.full(len(t), 900.0),
                np.full(len(t), 60.0), np.zeros(len(t), bool))
    save_traces([far], tmp_path / "day.npz")
    base = {"spectrogram": "spec.npz", "traces": ["day.npz"], "bbox": list(BOX), "terrain": False,
            "windows": [w.__dict__ for w in WINS], "run": {"workers": 1}}

    def run(name, **extra):
        (tmp_path / f"{name}.json").write_text(json.dumps({**base, **extra}))
        run_method(["collective", "--config", str(tmp_path / f"{name}.json"), "--out", str(tmp_path / name)])
        return tmp_path / name

    own = run("own")
    request, result = (json.loads((own / f).read_text()) for f in ("request.json", "result.json"))
    assert request["statistic_identity"] == result["statistic_identity"]
    assert request["label"] == search.statistic_label(result["statistic_identity"])
    assert request["inputs"]["spectrogram"] and result["reason"] == "no flight pass within range of the box"
    days = ["2025-05-28", "2025-05-29"]
    draws = [run(d, control={"traffic_day": d, "recording_day": "2025-06-01"}) for d in days]
    control = json.loads((draws[0] / "result.json").read_text())["control"]
    assert control == {"traffic_day": "2025-05-28", "recording_day": "2025-06-01", "shift_s": 345600.0}
    with pytest.raises(SystemExit):
        run("bad", control={"traffic_day": "2025-05-28"})
    assert "recording_day" in capsys.readouterr().err and not (tmp_path / "bad").exists()

    run_method(["collective-merge", str(own), "--out", str(tmp_path / "merged")])
    merged = json.loads((tmp_path / "merged" / "result.json").read_text())
    assert merged["statistic_identity"] == result["statistic_identity"] and merged["winner"] is None
    assert units.unit_problem(tmp_path / "merged") is None

    out = tmp_path / "null_draws.npz"
    run_method(["collective-null", *map(str, draws), "--own", str(tmp_path / "merged"), "--days", ",".join(days), "--out", str(out)])
    back = null.load_draws(out, result["statistic_identity"])
    assert list(back["day"]) == days and np.isnan(back["max_Z"]).all() and back["recording_day"] == "2025-06-01"
    with pytest.raises(SystemExit):
        run_method(["collective-null", str(draws[0]), "--own", str(own), "--days", ",".join(days), "--out", str(tmp_path / "n2.npz")])
    assert "missing ['2025-05-29']" in capsys.readouterr().err and not (tmp_path / "n2.npz").exists()
    (draws[1] / "completed.json").unlink()
    with pytest.raises(SystemExit):
        run_method(["collective-merge", str(draws[1]), "--out", str(tmp_path / "m2")])
    assert "no completed.json" in capsys.readouterr().err and not (tmp_path / "m2").exists()
