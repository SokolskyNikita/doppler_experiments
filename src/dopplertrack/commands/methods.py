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
    args = parser.parse_args(argv)
    if args.method == "grid-pair":
        from dopplertrack.commands.main import main as baseline
        return baseline(args.args[1:] if args.args[:1] == ["--"] else args.args)
    config = json.loads(args.config.read_text())
    required = {"spectrogram", "traces", "bbox", "windows"}
    if missing := required - config.keys():
        parser.error(f"missing configuration fields: {sorted(missing)}")
    if unknown := config.keys() - required - {"parameters", "terrain", "run"}:
        parser.error(f"unknown configuration fields: {sorted(unknown)}")
    from dopplertrack.methods.collective.parameters import resolve_collective
    try:   # the parameters are the dataclass's field names (methods/collective/parameters.py); unknown names are refused
        params = resolve_collective(config.get("parameters"))
    except ValueError as exc:
        parser.error(str(exc))
    run = dict(config.get("run", {}))
    if unknown := run.keys() - {"workers", "cpa_cache", "only_cells"}:
        parser.error(f"unknown run settings: {sorted(unknown)} (workers, cpa_cache and only_cells change no result)")
    from dopplertrack.components.spectrogram import Spectrogram
    from dopplertrack.data.day_seams import join_days
    from dopplertrack.data.terrain import Terrain
    from dopplertrack.methods.collective.search import collective_detection
    from dopplertrack.components.windows import Window
    from dopplertrack.runtime.cache import file_sha256
    def resolve(value):
        value = Path(value)
        return value if value.is_absolute() else args.config.resolve().parent / value
    spec = resolve(config["spectrogram"])
    traces = [resolve(p) for p in config["traces"]]
    provenance = {str(p): file_sha256(p) for p in [args.config, spec, *traces]}
    windows = [Window(**w) for w in config["windows"]]
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "request.json").write_text(json.dumps({"method": "collective", "config": config,
        "input_sha256": provenance, "assistance": "explicit event windows", "status": "running"}, indent=2) + "\n")
    flights, _ = join_days(traces)
    result = collective_detection(Spectrogram.load(spec), windows, flights, config["bbox"], params,
        elevation=Terrain().elevation if config.get("terrain", True) else None, **run)
    # This is the method's research output, not a calibrated common verdict.
    text = json.dumps(result, indent=2, default=float) + "\n"
    output = args.out / "result.json"
    output.write_text(text)
    (args.out / "result.json.sha256").write_text(f"{file_sha256(output)}  result.json\n")
    (args.out / "completed.json").write_text('{"status": "completed"}\n')
