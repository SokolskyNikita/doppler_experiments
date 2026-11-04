# Phase 1 preparation regression

<!-- index
question: Do the detector's named records leave `detect`'s output unchanged?
outcome: Yes: Oyster Bay's `detect` JSON is byte-identical before and after; 2 passed, 1 expected failure
-->

## Question and changes

Does replacing the detector's positional tuples with named records leave `detect`'s output unchanged?

`detect_events` now sends each window to its worker as a `ScanRequest` and gets `Candidate`s back,
instead of a 14-value tuple and 5-value tuples. The merge of coarse candidates moved into
`merge_candidates`, which states the sort key the tuple sort used: score, f0, speed, slant range and
emission CPA time, all descending. The same change removed unused imports that ruff reported and added
type annotations so that mypy can check `tracks.py`. None of it should change a number.

## Setup

Development recording: Oyster Bay's `derived/oyster_bay/rec.npz`. No new data was downloaded and no
parameter was tuned. This is a regression check, not an evaluation.

```bash
uv run dopplertrack detect "$DOPPLERTRACK_DATA/derived/oyster_bay/rec.npz" --band 60 300 --top 10 --out before.json
# the same command after the refactor, with --out after.json
cmp before.json after.json
DOPPLERTRACK_OYSTER_BAY="$DOPPLERTRACK_DATA/derived/oyster_bay" uv run pytest -q tests/test_oyster_bay.py
tools/check.sh
```

`before.json` was produced at `1cb9c34` with a clean tree, before `tracks.py` was edited; `after.json`
at `3c3bf59`, also clean. Both used the default worker count, one process per core (14).

## Results

- `detect`: `before.json` and `after.json` are byte-identical (SHA-256 `0e444812…4d91e0`), 10 events
  each. The top two are the known flyovers at 2155.6 s and 3068.4 s.
- Oyster Bay test: **2 passed, 1 expected failure**, as before.
- `tools/check.sh`: passed. Offline suite 68 passed, 3 skipped; the new process-pool test takes 6.7 s
  of it.

Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-03-phase1-prep-regression/` (`run.json`, `before.json`,
`after.json`, their logs, `after.commit`, `oyster_bay_pytest.log`, `check.log`).
