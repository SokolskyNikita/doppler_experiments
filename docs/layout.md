# Package layout

This is the package's current organization after the independence refactor. The code was moved into clearer namespaces while preserving implementations where further splitting could change behavior. This is a partial reorganization; it does not establish scientific validity or mean every subsystem is fully separated.

## Current package layers

| Package | Current contents |
|---|---|
| `commands/` | CLI wiring. `main.py` holds the established `dopplertrack` commands; `methods.py` dispatches the method interface. |
| `methods/grid_pair/` | The existing grid and fitted-pair pipeline and locate runner. |
| `methods/collective/` | The collective search implementation. It currently takes explicit event windows and returns method output, not a calibrated common verdict. |
| `components/` | Reusable algorithm pieces: spectrogram handling, detection, fitting, scoring, candidate grid search, and tracking. |
| `core/` | Shared geometry, atmospheric calculations, and Doppler propagation. |
| `data/` | ADS-B providers and trajectory parsing, coverage, and terrain access. |
| `evaluation/` | Benchmark cases, input preparation, evaluation runs, private-case handling, and reports. The `bench/` command and case files remain as compatibility entry points and manifests. |
| `reporting/` | HTML reports and plotting helpers. |
| `runtime/` | Shared paths, caches (including CPA tables), parallel execution, and result-record handling. |

The package and installed command are still named `dopplertrack`. The top-level modules below remain compatibility aliases so existing imports continue to resolve; new code should use the canonical package paths.

| Compatibility import | Implementation |
|---|---|
| `adsb`, `coverage`, `fetch`, `terrain` | `data.trajectories`, `data.coverage`, `data.providers.adsblol`, `data.terrain` |
| `atmosphere`, `doppler`, `geo` | `core.atmosphere`, `core.propagation`, `core.geometry` |
| `audio`, `freqtrack`, `hmmtrack`, `hypotheses`, `lltrack`, `score`, `search`, `tracks`, `warp` | `components.spectrogram`, `components.tracking.viterbi`, `components.tracking.hmm`, `components.fitting.profile_hypotheses`, `components.tracking.likelihood`, `components.scoring.trajectory_brightness`, `components.search.grid`, `components.detection.grid_scan`, `components.scoring.coherent` |
| `cache`, `parallel`, `result` | `runtime.cache`, `runtime.parallel`, `runtime.records` |
| `collective`, `locate`, `pipeline`, `plots`, `report` | `methods.collective.search`, `methods.grid_pair.runner`, `methods.grid_pair.pipeline`, `reporting.plots`, `reporting.html` |

## Running methods

`commands/methods.py` exposes the two current method names. `grid-pair` forwards the remaining arguments to the established CLI:

```sh
dopplertrack run grid-pair -- detect --help
```

`collective` reads a JSON config with required `spectrogram`, `traces`, `bbox` (`[lat_min, lat_max, lon_min, lon_max]`), and `windows` fields. A window has `t_start`, `t_end`, `f0`, `t_cpa`, and `score`. Paths in the config are resolved relative to that file. Optional fields are `parameters` and `terrain`.

```sh
dopplertrack run collective --config /path/to/collective.json --out /path/to/new-run
```

The output directory must not already exist. Collective windows are supplied as input; this command does not provide end-to-end event detection or a calibrated locate verdict.

## Data, caches, and retained research records

The refactor changed code organization only. Existing files remain in their external roots: `$DOPPLERTRACK_DATA` (default `~/data/dopplertrack`) for raw and derived inputs, run outputs, references, and private data; `$DOPPLERTRACK_CACHE` (default `~/.cache/dopplertrack`) for regenerable caches. No recordings, ADS-B data, benchmark inputs, or cache files were moved.

Several substantial implementations remain in single modules, including `components/detection/grid_scan.py`, `components/tracking/viterbi.py`, `components/search/grid.py`, `methods/grid_pair/pipeline.py`, `methods/grid_pair/runner.py`, `methods/collective/search.py`, `evaluation/runner.py`, `evaluation/tier1.py`, and `reporting/html.py`. Their placement gives them package ownership; it does not claim that they have already been decomposed internally.

Dated experiment records under `docs/experiments/` and historical recipes under `tools/experiments/` are retained deliberately so prior runs can be interpreted and, where possible, reproduced against their recorded code and inputs. The package changes do not rewrite those records or imply that their results validate the current methods.

## Verification

The refactor and reconciled reset fixes were checked on the dev box using a history-free snapshot with
exactly the same Git tree (`44edd21f4e883b3675e8d2fa26ae799509163a75`). The full check passed: lint,
experiment-index validation, typing, 362 tests passed, 4 skipped, 2 expected failures, and an installed-wheel
smoke test. Pytest took 112.46 seconds and emitted two existing multiprocessing fork deprecation warnings;
the 60-second test target remains unmet. No scientific experiment or private-data transfer was performed.
