"""Explicit entry points for independent research methods."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dopplertrack run")
    sub = parser.add_subparsers(dest="method", required=True)
    grid = sub.add_parser("grid-pair", help="existing detector, fitted-pair search and locate commands", add_help=False)
    grid.add_argument("args", nargs=argparse.REMAINDER)
    collective = sub.add_parser("collective", help="trajectory-first search with explicit input windows")
    collective.add_argument("--config", type=Path, required=True)
    collective.add_argument("--out", type=Path, required=True, help="new output directory")
    merge = sub.add_parser("collective-merge", help="one result from the complete only_cells units of a collective search")
    merge.add_argument("units", nargs="+", type=Path, help="the units' output directories")
    merge.add_argument("--out", type=Path, required=True, help="new output directory")
    null = sub.add_parser("collective-null", help="collect a collective search's control draws into one NPZ")
    null.add_argument("draws", nargs="+", type=Path, help="the control draws' output directories")
    null.add_argument("--own", type=Path, required=True, help="the own-day search's output directory")
    null.add_argument("--days", required=True, help="the control days expected, comma-separated (YYYY-MM-DD)")
    null.add_argument("--out", type=Path, required=True, help="the NPZ to write")
    args = parser.parse_args(argv)
    if args.method == "grid-pair":
        from dopplertrack.commands.main import main as baseline
        return baseline(args.args[1:] if args.args[:1] == ["--"] else args.args)
    from dopplertrack.methods.collective.units import IncompleteUnit, finish_unit, read_units, start_unit
    if args.method == "collective-merge":
        from dopplertrack.methods.collective.merge import merge_results
        try:
            units = read_units(args.units)
            result = merge_results(units)
        except IncompleteUnit as exc:
            parser.error(str(exc))
        start_unit(args.out, {"method": "collective-merge", "units": [u["path"] for u in units],
                              "inputs": units[0]["request"].get("inputs"),
                              "statistic_identity": result["statistic_identity"]})
        return finish_unit(args.out, result)
    if args.method == "collective-null":
        from dopplertrack.methods.collective.null import collect_draws, save_draws
        if args.out.exists():
            parser.error(f"{args.out} exists")
        try:
            table = collect_draws(args.own, args.draws, [d for d in args.days.split(",") if d])
        except IncompleteUnit as exc:
            parser.error(str(exc))
        return save_draws(args.out, table)
    config = json.loads(args.config.read_text())
    required = {"spectrogram", "traces", "bbox", "windows"}
    if missing := required - config.keys():
        parser.error(f"missing configuration fields: {sorted(missing)}")
    if unknown := config.keys() - required - {"parameters", "terrain", "run", "control"}:
        parser.error(f"unknown configuration fields: {sorted(unknown)}")
    control = config.get("control")
    if control is not None and (not isinstance(control, dict) or control.keys() != {"traffic_day", "recording_day"}):
        parser.error("control takes exactly traffic_day and recording_day (YYYY-MM-DD): the day the traces are of, "
                     "and the recording's day they are mapped onto")
    from dopplertrack.methods.collective.parameters import resolve_collective
    try:   # the parameters are the dataclass's field names (methods/collective/parameters.py); unknown names are refused
        params = resolve_collective(config.get("parameters"))
    except ValueError as exc:
        parser.error(str(exc))
    run = dict(config.get("run", {}))
    if unknown := run.keys() - {"workers", "cpa_cache", "only_cells"}:
        parser.error(f"unknown run settings: {sorted(unknown)} (workers, cpa_cache and only_cells change no result)")
    from dopplertrack.components.spectrogram import Spectrogram
    from dopplertrack.data.day_mapping import day_shift_s, map_to_day
    from dopplertrack.data.day_seams import join_days
    from dopplertrack.data.terrain import Terrain
    from dopplertrack.methods.collective.search import collective_detection, statistic_identity, statistic_label
    from dopplertrack.components.windows import Window
    from dopplertrack.runtime.cache import file_sha256
    def resolve(value):
        value = Path(value)
        return value if value.is_absolute() else args.config.resolve().parent / value
    spec = resolve(config["spectrogram"])
    traces = [resolve(p) for p in config["traces"]]
    provenance = {str(p): file_sha256(p) for p in [args.config, spec, *traces]}
    windows = [Window(**w) for w in config["windows"]]
    identity = statistic_identity(params)
    if control is not None:
        try:
            control = dict(control, shift_s=day_shift_s(control["traffic_day"], control["recording_day"]))
        except (TypeError, ValueError) as exc:
            parser.error(f"control: {exc}")
    # Written before the search: what was asked, of which inputs, and which statistic the result will be a value of.
    start_unit(args.out, {"method": "collective", "config": config, "input_sha256": provenance,
                          "inputs": {"spectrogram": provenance[str(spec)], "traces": [provenance[str(p)] for p in traces]},
                          "statistic_identity": identity, "label": statistic_label(identity),
                          "assistance": "explicit event windows"})
    flights, _ = join_days(traces)
    if control is not None:           # another day's traffic, set on the recording's date at the same time of day
        flights = map_to_day(flights, control["traffic_day"], control["recording_day"])
    result = collective_detection(Spectrogram.load(spec), windows, flights, config["bbox"], params,
        elevation=Terrain().elevation if config.get("terrain", True) else None, **run)
    if control is not None:
        result["control"] = control
    # This is the method's research output, not a calibrated common verdict.
    finish_unit(args.out, result)
