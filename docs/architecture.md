# Implementation map and verification boundaries

This page describes current source behavior. [README](../README.md) covers usage;
[PLAN](../PLAN.md) and [experiment records](experiments/README.md) distinguish research decisions and measurements.
A path being installed or unit-tested does not establish acoustic accuracy or a calibrated verdict.

## Entry points and profiles

| Surface | Entry point | Behavior |
|---|---|---|
| Installed CLI | `pyproject.toml` → [commands.main.main](../src/dopplertrack/commands/main.py) (also `python -m dopplertrack`) | `spectrogram`, `fit`, `detect`, `extract-region`, `fetch-day`, `search`, `refine`, `search-single`, `locate` |
| Audio-to-record orchestration | `commands.main._locate` → [grid_pair.runner.locate](../src/dopplertrack/methods/grid_pair/runner.py) | Detection, coverage preflight, pair searches, winner refinement, schema-v2 record/hash; never emits `located` |
| Repository benchmark | `python -m bench` → [evaluation/runner.py](../src/dopplertrack/evaluation/runner.py) | `saved-fit`, `raw-audio`, `locate`; record/hash before labels, revision exports, shards/resume, comparison; `bench report` renders HTML |
| Collective search | [collective_detection](../src/dopplertrack/methods/collective/search.py), `tools/experiments/2026-11-04/collective_run.py` | Experimental alternative; separate result dictionary, outside CLI locate, benchmark profiles and versioned verdicts |

Installed defaults:

- `spectrogram`: 4 kHz mono decode, 40–450 Hz, 8192-sample (2.048 s) Hann window and 0.25 s hop.
  Files and AudioMoth folders are supported; folder gaps remain invalid frames.
- `fit`: brightness objective. `detect`: sweep-weighted contrast S0, 240 s windows stepped by 120 s,
  one harmonic, top 20, finite scores strictly above `min_score=0`. Its band is required.
- `search`: 200 m grid; heard-CPA gap ±6 s, speed ±35%, distance 0.4–2.5× the fits, 6 km silence filter,
  heard clock anchor. Emission timing, steepest-fall checks and a steepest clock anchor are explicit options.
  Comparable scores (`scoring.normalisation=pair_zscore`) and hypotheses (`gates.event_gate=profile_intervals`) are
  parameters, off by default.
- `refine`: CLI 50 m grid with 600 m half-width (the library's default half-width is 400 m).
  `search-single` takes an absolute heard-CPA time, default ±30 s gate and 200 m grid.
- `locate`: 60–300 Hz, top 10 detections, every pair among the top five usable events with comparable scores,
  6 km silence filter, 200 m grid, winner-only 50 m refinement over a 600 m half-width with placeable extras.
  `top2` and `both` are explicit alternatives. A stated start/tolerance gates the inferred clock when supplied.
  Two usable events are required even with a stated start.
- Sound speed defaults to 15 °C. CLI `--temperature` opts into temperature-based fits and height-dependent
  propagation in search/refinement. `--jobs` overrides `DOPPLERTRACK_JOBS`, otherwise the physical/performance-core
  default from [runtime/parallel.py](../src/dopplertrack/runtime/parallel.py).

Benchmark profiles are part of a result's identity. `saved-fit` (default) uses the case's fits and harmonics.
`raw-audio` uses detection's top two by score, earlier first, with one harmonic. The `locate` profile uses the
comparable default, but takes silence, geometry and refinement settings from the case, uses its own trace
selection/envelope rules, and gates on the case's stated start unless disabled. Weather is off unless `--weather`.

Every setting that can change a result is a field of one frozen parameters dataclass per recipe (research readiness
R2): `GridPairParameters` in [methods/grid_pair/parameters.py](../src/dopplertrack/methods/grid_pair/parameters.py)
and `CollectiveParameters` in [methods/collective/parameters.py](../src/dopplertrack/methods/collective/parameters.py),
nested by stage, with the functions' keyword defaults as defaults. Resolution runs default, then profile (`PROFILES`,
data: `saved-fit`, `raw-audio`, `locate`), then the case (`evaluation/runner.case_parameters`: its search and refine blocks,
harmonics under saved-fit, the station temperature with `--weather`, the stated start under locate), then the run's
explicit overrides (`bench run --search-param`, CLI flags then `--param`, the collective config's `parameters`), and
unknown names are refused. A method choice is a name looked up in a dict in the recipe module (`grid_pair/pipeline.py`:
`DETECTION_STATISTICS`, `TIME_CONVENTIONS`, `EVENT_GATES`, `SCORE_NORMALISATIONS`, `CLOCK_ANCHORS`; `runner.py`:
`EVENT_SOURCES`; `collective/search.py`: `VIEWS`, `ASSIGNMENTS`; `methods/parameters.py`: `WHITENINGS`). Each record
keeps the fully resolved set: grid_pair under `provenance.parameters.resolved`, collective under `parameters`
(`--revision` runs record that another revision's CLI ran instead). The `locate` profile still runs through
`execute_case_locate` and `grid_pair.runner.locate` (usability, coverage and verdict), saved-fit and raw-audio through
`execute_case`.

## Results, coverage and abstention

[grid_pair/runner.py](../src/dopplertrack/methods/grid_pair/runner.py) returns `insufficient_evidence` for too few usable events, excessive
recording gaps, missing geographic/time coverage or no surviving candidate. It checks the winning clock's
recording span against supplied days. Supplied files still need to cover the requested times; `--days 1` drives
next-day fetching, not automatic loading of an omitted trace file. A completed winner refinement returns
`ambiguous` with `winner_only_refined`. It neither searches/refines all competitors nor computes an uncertainty
region or a false-location probability. Comparable event-null normalization is not the null of a whole search's
maximum.

Coverage checks use extraction envelopes and declared/observed outer time bounds. `_covered_days` takes the
minimum start and maximum end: separated intervals are treated as one span, so passing preflight does not prove
continuous coverage. Pair search's candidate-gap warnings and trajectory support masks also cannot establish
that every audible aircraft is present in ADS-B. Geometry can interpolate 30–90 s gaps to propose a CPA while
modelled curves contribute no evidence over gaps longer than 30 s.

[runtime/records.py](../src/dopplertrack/runtime/records.py) writes schema **2**, validates schemas 1 and 2, and supports a
site-relative frame. Version 2 allows `located`, `ambiguous` and `insufficient_evidence` structurally;
`locate` never emits the first. Uncomputed fields carry `unavailable(reason)`. Schema validation checks required
fields, types, enumerations and finite floats; it permits extra fields and does not prove cross-field scientific
validity. `write_record` validates and writes canonical bytes atomically, returning their SHA-256. The benchmark
writes the record/hash before opening labels and refuses altered records/sidecars. This is procedural blinding,
not evidence that development data became held-out evaluation. Schema v3 was never adopted; the readiness plan adds a minimal collective record (R6.6).

The installed CLI produces no HTML report. `bench report` uses [reporting/html.py](../src/dopplertrack/reporting/html.py),
local result records and optional sidecars to render reports into a new run folder. Execution errors are distinct
from evidence verdicts; unreadable audio, missing ffmpeg or network failures are not scientific abstentions.

## Detector edit map

[grid_scan.detect_events](../src/dopplertrack/components/detection/grid_scan.py) schedules windows as keyword-built `ScanRequest`s.
Each request holds a whitened crop; `_scan_window` searches the ideal straight-pass grid, keeping separated maxima. Serial
`map` and the package's spawn pool consume the same requests. `non_maximum_suppression` ranks by score, f0, speed,
slant range and emission CPA (all descending), retaining up to `2 * top` before refinement. Refinement is serial:
[`fit_event`](../src/dopplertrack/components/detection/event_fit.py) narrows the
[grid search](../src/dopplertrack/components/detection/grid_search.py) then uses Nelder–Mead. Final finite-score filtering and deduplication use **heard**
CPA times; the earlier merge uses **emission** CPA times.

Audio times are recording seconds; flight/CPA times are Unix seconds. [trajectory_score.custom_locked_score](../src/dopplertrack/components/scoring/trajectory_score.py)
sets `audio = unix + (event1.t_cpa - flight1.t_heard) + shift`, sharing event 1's shift with event 2 and extras.
Pairing first compares time differences, requiring no absolute offset. Preserve these conventions when changing
scheduling or scoring.

[tests/test_phase0_cli.py](../tests/test_phase0_cli.py) covers tuple tie-breaking, serial/two-worker equality
including refinement, cache-wired CLI detection, refined-score thresholds and silent output.
[tests/test_parallel.py](../tests/test_parallel.py) checks job defaults and single-thread numerical workers.
Those deterministic synthetic checks do not calibrate detection thresholds on noisy recordings.

## CPA build and scoring edit map

[pipeline.pair_grid_search](../src/dopplertrack/methods/grid_pair/pipeline.py) builds clipped flight segments, then calls
`cached_cpa_table`. [cpa_table](../src/dopplertrack/components/search/cpa_table.py) runs one task per segment; workers hold
the grid and KD-tree once. Longest segments run first but results return in segment/grid order.
`_corridor` prunes horizontal grid points; `_nearest_samples` compares 4 km tiles with nearby trajectory samples.
Chunks (20,000 points by default) are centred on their own mean. Changing chunk membership can change rounding.
Repeated positions choose the earliest trajectory sample. Endpoint CPAs and out-of-range rows are discarded.
Rows hold `gidx`, `seg`, `t_emit`, `t_heard`, slant distance `d` and ground speed `v`.

The table is independent of event fits. Pairing gates its rows, then `custom_locked_score` samples trajectory-derived
curves. Search and refinement dispatch scoring chunks through `runtime.parallel.ordered_map`, passing immutable scoring
state with an initializer and restoring task order. Package process pools use spawn and pin numerical threads to
one. These guarantees do not automatically apply to experiment scripts' own executors.

[tests/test_cpa_build.py](../tests/test_cpa_build.py) compares serial/pool tables with brute force, including ties
and repeated positions. [tests/test_search_pairs.py](../tests/test_search_pairs.py) checks pairing and cache
round trips; [tests/test_pipeline_synthetic.py](../tests/test_pipeline_synthetic.py) requires the true synthetic
observer to rank first. [tests/test_cache.py](../tests/test_cache.py) checks content fingerprints, reuse,
corrupt-cache recovery and failed-save cleanup. Result tables' `attrs` contain funnel/stage diagnostics; CSV does
not preserve them.

## Caches

The default root is `$DOPPLERTRACK_CACHE` (otherwise `~/.cache/dopplertrack`); explicit paths/root overrides are
also supported. Keep caches outside the repository. Cache policies differ:

| Artifact | Key/invalidation | Storage and recovery |
|---|---|---|
| Spectrogram, `components.spectrogram_cache.cached_spectrogram` | File names, SHA-256 and offsets; start, snap, sample rate, filled-in STFT parameters; whole source of the modules in `SPECTROGRAM_MODULES`; ffmpeg/numpy/scipy versions | `runtime.cache.cached` joblib entry, per-key file lock; bad entries rebuilt |
| Detections, `runtime.cache.cached_detections` | Spectrogram t/f/power/mask/start; supplied detector parameters except workers/progress; producer name; selected executable AST definitions and referenced constants in the modules `DETECTOR_CODE` lists; numpy/scipy versions | Same joblib/lock path; CLI detect and locate call it |
| CPA, `methods.grid_pair.pipeline.cached_cpa_table` | Grid coordinates/elevations/ENU and origin; segments' ICAO/times/positions/speeds; range, sound speed, optional ground temperature, `CPA_CACHE_VERSION` | Explicit NPZ path, atomic replacement, `<path>.lock` via fcntl; unreadable/mismatched file is a miss |
| Terrarium terrain | Zoom/tile coordinates; no content/code/version hash | Atomic tile downloads, corrupt images fetched again, in-process memory cache; no per-tile lock |
| Aircraft types, `data.aircraft_types.AircraftTypes` | Existing file, no freshness/content/version check | Download-once CSV; no equivalent lock/atomic-repair policy |

The detection key intentionally ignores docstrings and error/warning messages, rather than hashing whole modules.
`tests/test_cache.py` checks the selected dependency list and AST key. Supplied parameter dictionaries are not
normalized to filled-in detector defaults. Equivalent calls can therefore occupy different entries.
The CPA key has no automatic source/library hash: **bump `CPA_CACHE_VERSION` when construction changes output for
the same inputs**. Give input combinations separate files to avoid repeated rebuilds when alternating them.
Where fcntl is unavailable, the CPA lock is a no-op; atomic replacement still prevents partial-table reads.

`runtime.cache.cached(kind, parts, produce)` uses canonical JSON (arrays represented by hashes) to identify entries.
The stored description is checked on load. Callers must describe all semantic dependencies in `parts`; the helper
does not discover them. [tests/test_artefact_cache.py](../tests/test_artefact_cache.py) covers content/parameter
misses, corrupt entries, concurrent builders and spectrogram equality. These policies do not make a cached
experimental statistic scientifically accepted.

## Experimental seams

The collective path keeps detection bounds and the returned `EventFit` frequency and heard CPA.
`Window.from_detection` reads refined `f0` and timing fields, despite the historical proposal calling them coarse
pre-refinement estimates. It omits fitted speed/distance gates but retains this fitted-template dependence. It uses
1 km coarse cells, 200 m fine points, each flight's trajectory, approximately ±25% tone freedom, the best 120 s
stretch and standardized per-window scores with a zero floor. Clocks are binned at 3 s and spread two bins either
side. Fine cells lie within two robust map spreads of the coarse maximum, capped at 20. Window nulls normalize
scores; they do not calibrate the maximum over cells/clocks or provide an uncertainty region.

Historical **v4** denotes the dense coarse sweep plus its original sequential pass/window deduplication.
The repaired aggregate is explicitly **`collective-Z-greedy-v1`** in returned `statistic`: a bounded descending-score
greedy selector reserves a window and pass only on accepting both. Scoring/reporting share rounded heard-CPA pass
identity and the three-row fallback cap per window/source clock bin. This is not optimal assignment. It can change
Z, winners and retained cells, so it requires new positives and a same-design maximum-over-search null. Preserve
v4's historical identity; old v3/v4 outcomes and nulls cannot be relabelled as calibration of the repair.
The historical experiment launcher still names run topics `v4`; inspect the emitted statistic and code provenance,
not just a folder label. Its merged summaries and NPZ null exports omit that identifier; they do not enforce
statistic compatibility. No real-data result for the repaired statistic is established by this page.

[tests/test_collective.py](../tests/test_collective.py) contains a synthetic search with reduced tone/null settings
and serial workers, plus small fallback/report consistency regressions. It does not establish collective
serial/pool equivalence, full-default real-data performance or a calibrated maximum null. The historical stopped
record reports v4's smoke cancelled without results; that is recorded history, not a fresh run inspection.

The trackers (`viterbi`, `hysteresis_viterbi`, `hmm_tracker`), the de-Dopplerised tone score, track fitting and the
hypotheses remain library/research code. The hypotheses are the `gates.event_gate=profile_intervals` choice; CLI detect
selects none of these trackers. `custom_rescore_zscore` (S1) and `rescore_surrogate` (S2's D) are the
`detection.statistic` choices beside the default contrast. Their tests demonstrate mechanics,
not adoption of a failed or unfinished experiment.

The late [detector_roc.py](../tools/experiments/2026-11-04/detector_roc.py) change dispatches S2 reversed-window fits
through a raw `ProcessPoolExecutor`, spectrogram initializer and ordered `ex.map`. It does not use the package's
spawn/thread wrapper; four thread variables use `setdefault`. `tests/test_detect_statistic.py` checks serial S2
with a substituted fit, not `null_scores` or pool equivalence at the historical tip. The reset adds
`tests/test_detector_pool.py` for real reversed-window fits, event order and diagnostic equality with two workers;
it passed on the development box during this reset (Python 3.12.15, Linux AArch64). The raw fork executor emitted
two multiprocessing deprecation warnings; equality in this bounded check does not prove general thread safety.
The [verification note](experiments/2026-11-04-research-reset.md#engineering-verification-2026-11-04)
records its tested tree and limits. S2's interrupted scientific gate remains unjudged.

The separate `collective_null.py` experiment fits a 1% other-day maximum threshold (Gumbel with a KS-based
empirical fallback), writes experimental verdict labels including `located`, then reveals labels. Those outputs
use proposed v3-style null fields, not the implemented result schema, and never feed CLI locate. Commit strings
and a generic statistic description are recorded; readers still need to establish that own-day and null searches
used the same algorithm, parameters and search domain.

## Check boundaries

[tools/check.sh](../tools/check.sh) runs ruff's pyflakes rules on `src/` and `tests/`, checks the experiment index,
runs mypy on tracks/search/parallel/hypotheses, offline pytest with the real-data opt-in variable removed, then
builds/installs a wheel and runs [tests/install_smoke.py](../tests/install_smoke.py) outside the checkout.
The smoke covers help, decoding, spectrogram generation and silent detection. Follow [AGENTS](../AGENTS.md) for
where checks run; a full suite is not a local inner-loop check.

CI runs pytest on Ubuntu/Python 3.12 and 3.13 for main pushes and pull requests. It does not trigger on dev pushes
or run all of `tools/check.sh`. Experiment scripts are outside the lint/type targets; locate/collective/cache/result
and bench are outside the explicit mypy targets.

`tests/test_locate.py` substitutes detection/search/refinement to check control flow, defaults, clock gating and
verdicts. Result/report/benchmark tests cover schema/hash ordering and rendering. The opt-in
[tests/test_oyster_bay.py](../tests/test_oyster_bay.py) retains a strict expected failure for detected fits passing
the truth gates. A green offline suite cannot establish raw-audio success, competitor rejection, held-out accuracy,
uncertainty coverage or a false-located rate.
