"""Run against an installed wheel, outside the checkout, without pytest or network data."""
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from dopplertrack import __file__ as package_file
from dopplertrack.components.spectrogram import Spectrogram


def main():
    assert "site-packages" in str(package_file), f"expected an installed wheel, got {package_file}"
    cli = Path(sys.executable).with_name("dopplertrack")
    subprocess.run([str(cli), "--help"], check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        wav, spec, events = root / "silence.wav", root / "silence.npz", root / "events.json"
        with wave.open(str(wav), "wb") as f:
            f.setparams((1, 2, 4000, 0, "NONE", "not compressed"))
            f.writeframes(np.zeros(4000 * 8, dtype="<i2").tobytes())
        subprocess.run([str(cli), "spectrogram", str(wav), str(spec)], check=True)
        sp = Spectrogram.load(spec)
        assert sp.S.shape[1] > 1 and np.isfinite(sp.S).all()
        env = {**os.environ, "DOPPLERTRACK_CACHE": str(root / "cache")}     # detect caches its result
        result = subprocess.run([str(cli), "detect", str(spec), "--band", "100", "130",
                                 "--top", "1", "--out", str(events)], check=True, capture_output=True, text=True, env=env)
        assert json.loads(events.read_text()) == []
        assert "no flyovers found" in result.stdout
    print("installed-wheel smoke test passed")


if __name__ == "__main__":
    main()
