"""Compatibility and method boundaries must survive physical module moves."""
import importlib
import json
import pickle
from pathlib import Path

import pytest


def test_historical_imports_are_same_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    mapping = json.loads((Path(__file__).parents[1] / "docs/refactor-module-map.json").read_text())
    mapping['search'] = 'components.search.grid'
    for old, new in mapping.items():
        assert importlib.import_module(f'dopplertrack.{old}') is importlib.import_module(f'dopplertrack.{new}')
    assert importlib.import_module('bench.runner') is importlib.import_module('dopplertrack.evaluation.runner')


def test_old_pickle_module_path_resolves():
    # GLOBAL from a historical protocol-0 pickle must still resolve through the alias.
    from dopplertrack.components.types import EventFit
    assert pickle.loads(b'cdopplertrack.tracks\nEventFit\n.') is EventFit


def test_method_dispatch_preserves_grid_cli(capsys):
    from dopplertrack.cli import main
    with pytest.raises(SystemExit) as exc:
        main(['run', 'grid-pair', '--', '--help'])
    assert exc.value.code == 0
    assert 'search' in capsys.readouterr().out


def test_collective_requires_explicit_inputs(tmp_path):
    from dopplertrack.commands.methods import main
    config = tmp_path / 'config.json'
    config.write_text('{}')
    out = tmp_path / 'out'
    with pytest.raises(SystemExit):
        main(['collective', '--config', str(config), '--out', str(out)])
    assert not out.exists()
