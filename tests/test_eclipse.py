"""ESID 740 keeps its timeline (PLAN Phase 1 item 8). Opt-in: needs an hour of the site's files.

Set DOPPLERTRACK_ESID740 to a folder made by
  tools/data/eclipse_extract.py $DOPPLERTRACK_DATA/raw/audio/eclipse/ESID_740/ESID_740_2024_04_07.zip \\
      $DOPPLERTRACK_DATA/derived/eclipse/ESID_740/2024-04-07_04h 20240407_040000 20240407_050000
That hour holds 58 one-minute files that abut, and one hole, 04:25:46-04:27:22 UTC, where the
device skipped a file."""
import datetime
import os
from pathlib import Path

import numpy as np
import pytest

from dopplertrack.audio import audiomoth_files, spectrogram_from_audiomoth

DATA = os.environ.get("DOPPLERTRACK_ESID740")
pytestmark = pytest.mark.skipif(not DATA, reason="set DOPPLERTRACK_ESID740 to run")
SR, NPERSEG, HOP = 4000, 8192, 1000


def test_esid740_hour_keeps_its_timeline():
    files, start = audiomoth_files(Path(DATA))
    first = datetime.datetime.strptime(files[0][0].name[:15], "%Y%m%d_%H%M%S").replace(tzinfo=datetime.timezone.utc)
    assert len(files) == 58 and start == first.timestamp()
    sp = spectrogram_from_audiomoth(DATA)
    span = files[-1][1] + 60.0                                   # every file holds 60.000 s
    assert len(sp.t) == (int(span * SR) - NPERSEG) // HOP + 1
    assert sp.start_utc == start                                  # frame 0's window starts at the first file's name
    lo, hi = sp.t - NPERSEG / 2 / SR, sp.t + NPERSEG / 2 / SR
    holes = [(o + 60.0, n) for (_, o), (_, n) in zip(files, files[1:]) if n > o + 61.0]
    assert holes == [(1500.0, 1596.0)]                            # 04:25:46 to 04:27:22 UTC
    expected = np.zeros(len(sp.t), bool)
    for a, b in holes:
        expected |= (hi > a) & (lo < b)
    assert np.array_equal(~sp.valid, expected)                    # nothing invalid at the 56 seams
