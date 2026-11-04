# Phase 0 regression check

<!-- index
question: Do Phase 0's data and trajectory masks preserve the Oyster Bay checks?
outcome: 2 passed, 1 expected failure; the detector-fit bias remains Phase 2 work
-->

## Question

Do the Phase 0 data and trajectory-coverage fixes preserve the known Oyster Bay fit and detection
checks, while leaving the Phase 2 raw-audio fit failure visible?

## Setup

Development recording: Oyster Bay, using the existing `derived/oyster_bay/rec.npz` and
`derived/oyster_bay/traces_ny.npz`. No new audio or flight data was downloaded, and no thresholds,
fit windows or scoring parameters were tuned. These are development checks, not evaluation results.

Script: `tests/test_oyster_bay.py`, including its saved-fit comparison, known-point flight-pair check,
automatic detection check and strict expected failure for detector fits passing the search gates.

```bash
DOPPLERTRACK_OYSTER_BAY="$HOME/data/dopplertrack/derived/oyster_bay" \
    .venv/bin/python -m pytest -q tests/test_oyster_bay.py
```

The run started on `f225176` with the Phase 0 source changes uncommitted. Its `run.json` records the
command, environment and dirty tree; `source.patch` captures those changes. The source changes were
then committed as `48ac387`.

## Numbers and outcome

- Oyster Bay: **2 passed, 1 expected failure**, 94.66 s.
- The README's fit windows still reproduce the committed event fits within the existing tolerances.
  The true pair (`a1dfeb`, `ace391`) survives at the known location, with event 2's score above 10.
- Automatic detection still finds the two flyovers within the existing 5 s timing tolerances.
- The detector-fit search test remains a strict expected failure. Phase 0 does not resolve E1/E2.
- The separate offline suite passed **62 tests**, with the three opt-in tests skipped, in 46.83 s.
- The final wheel passed an installed-package smoke test outside the checkout: ffmpeg decoded
  synthetic silence, a finite spectrogram was written, and detection returned `[]` with an explicit
  "no flyovers found" message.

Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-03-phase0-regression/` (`run.json`, `source.patch`,
`pytest.log`). No location-accuracy claim follows from this regression check.
