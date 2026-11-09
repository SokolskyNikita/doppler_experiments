"""Method boundaries and the command-line entry points."""
import subprocess
import sys

import pytest


def test_python_m_dopplertrack_runs_the_cli():
    out = subprocess.run([sys.executable, "-m", "dopplertrack", "--help"], capture_output=True, text=True, check=True)
    assert out.stdout.startswith("usage: dopplertrack")


def test_method_dispatch_preserves_grid_cli(capsys):
    from dopplertrack.commands.main import main
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
