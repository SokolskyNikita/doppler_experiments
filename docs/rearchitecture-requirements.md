# Architecture preparation

The search code passes candidates through positional tuples, reconstructs the recording clock in
several functions and stores refinement metadata in `DataFrame.attrs`. A change to a field or time
convention can produce a plausible result with the wrong meaning. This work gives those interfaces
named types and tests, and makes the existing workflows callable by the benchmark runner.

The goal is to let coding agents complete and verify experiments with fewer missed dependencies and
less human correction.

## Scope

Complete this work after Phase 0 and before any Phase 1 item in [PLAN.md](../PLAN.md), including
parallelism. Keep the existing phase numbers.

The deliverables are stage records and configuration, clock conversion, workflow entry points,
an offline check command and `docs/architecture.md`. Use the coverage metadata, trajectory evidence
masks, event-file loading and install checks already present in the post-Phase-0 code.

Phase 1 owns parallel execution, the result record, benchmark cases and runner, new cache
implementations and gap-aware audio. Scientific changes belong to the later experiments in PLAN.md.
Plotting, the report, tools-script cleanup and GitHub CI are outside this work. Keep archived
experiment scripts unchanged.

## Module ownership

| Code | Owner | Responsibility |
|---|---|---|
| Physics and coordinates | `geo`, `doppler` | Calculate curves, propagation delays and coordinate conversions from in-memory inputs |
| Records and settings | Stage modules; shared `records`, `params` and `clock` where needed | Define fields, units, configuration and conversion between time frames |
| Input and storage | `audio`, `adsb`, `fetch`, `terrain`, `coverage`; extracted storage helpers | Decode and validate inputs, report coverage, load and save artifacts |
| Numerical stages | `tracks`, `score`, `search`; extracted `fit` or `detect` as needed | Produce fits, candidates and scores |
| Workflows | `pipeline` | Load inputs, compose stages and write artifacts |
| Command line | `cli` | Parse arguments, call workflows, display results and set exit status |

Keep a record or setting in its stage module unless another stage needs it. Shared records may
contain NumPy arrays or pandas frames. Constructing a record or importing its module must not read
files, inspect the environment or start a workflow.

Numerical stages must not import CLI or workflow modules, parse arguments or write result files.
Physics functions must not perform I/O. Add import tests for these boundaries and use focused tests
to check the callable interfaces.

The CPA cache's storage helpers own locking, fingerprints and atomic reads/writes. `pipeline` decides
whether to compute a cache miss and calls `search.cpa_table`. Preserve the cache's current identity
and recovery behavior. Extract modules where these responsibilities need separating; retain
compatibility exports for imports used by archived experiments, or record their replacements and
the historical revision in `docs/architecture.md`.

## Requirements

### R1. Preserve existing behavior

Capture baselines from the merged Phase 0 before editing production code. Exercise CLI and library
entry points at their current defaults and at the parameters used for the development recordings.

CLI `fit` uses brightness. Library fitting and detection use contrast. Pair search has a 6 s timing
tolerance; known-time single search has 30 s. Keep these choices in explicit profiles. Record other
entry-point differences in the baseline tests, including detection refinement bounds and refinement
defaults.

Preserve candidate identity, ranking and tie behavior. Detection currently breaks equal coarse scores
by the remaining tuple fields. Give that ordering an explicit sort key and test tied candidates.
Keep each straight-pass caller's sampling span, sample count and interpolation behavior if the two
shape implementations are combined.

Progress moving to stderr and the format changes in R4 are allowed interface changes. Changes to
algorithms or numerical defaults require a separate experiment.

### R2. Give each setting an owner

Use frozen dataclasses for settings that a stage shares with its callers or records as provenance.
Define the default for each semantic parameter once and pass the resolved value to every consumer.
Keep the fitting profiles and search tolerances in R1 distinct. Scoring and plotting retain separate
crop settings.

Configuration objects should contain immutable values. Store grids as tuples or make each
per-instance array read-only. Small numerical helpers can take scalar arguments; stage entry points take the
configuration they use. Keep physical constants in `geo` or `doppler`.

Argparse declarations read defaults from the appropriate profile. Tests must pass a non-default
option through the CLI and confirm the value received by the numerical stage. Serialize the resolved
scientific settings to deterministic JSON-safe values for Phase 1's provenance record.

Resolve environment-derived paths and runtime settings at the CLI or workflow boundary. Tests can
supply them explicitly. Importing a library module must not resolve those settings or create files.

### R3. Name the fields that cross stages

Replace detection candidate tuples and window-scan request/result tuples with records whose fields
state their meaning. Use named field access. Grid fitting and locked scoring also need named return
values for their parameters and component scores.

Search and refinement return result objects with an explicit table schema. The schema owns column
names, units, dtypes and the empty-table shape. Constructors and serializers use the same definition.
Keep array and DataFrame storage for large collections.

Refinement's selected flights belong in the result object and its serialized output. Give scores
for extra events explicit event identifiers, with an adapter for the existing `s3`, `s4` and subsequent
CSV columns. Tests must cover an empty result, multiple extra events and a serialization round trip.

Validate array shapes, required finite values and timestamp ordering when inputs enter a stage.
Represent invalid trajectory samples with the existing evidence masks and retain those masks through
resampling, clipping and record conversion.

### R4. Load existing files and version new formats

Each package-owned persistent format changed by this work has a schema version and one loader.
Support today's unversioned files, including saved event fits, through an explicit legacy adapter.
Keep external source files in their original format.

Test the current format, each supported legacy format and an unknown version. An unsupported result
version produces a diagnostic with the file and version. An incompatible or unreadable regenerable
cache counts as a miss and rebuilds. Cache recovery must not hide programming errors.

Field renames need migration tests for their old and new names. Assert metadata, units, table dtypes
and refinement selections as well as numerical values.

### R5. Record the sound speed used by a fit

New `EventFit` records contain the sound speed used to calculate CPA delay and asymptote frequencies.
Derive `t_cpa_heard_audio`, `f_pre` and `f_post` from their source fields, or validate the stored values
against those fields and that sound speed.

Historical fits without sound speed keep their stored scientific values. Represent the missing
sound speed explicitly and require a supplied value for operations that need to recompute derived
fields. Do not fill it with the current default.

Tests use a non-default sound speed, reject inconsistent new records and load existing fits without
changing their values.

### R6. Make time and position conventions explicit

`clock.py` converts recording-relative audio seconds to Unix seconds. Its anchor is the Unix time of
audio zero:

```text
t_unix = audio_start_unix + t_audio
t_audio = t_unix - audio_start_unix
```

Provide a constructor from matching audio and Unix anchors for candidate-flight clock estimates.
Replace repeated offset arithmetic in scoring and refinement with these conversions. Preserve the
current per-candidate anchor and shared score shift. Joint clock fitting and drift remain Phase 3.

Use distinct scalar types for audio seconds, Unix seconds and durations at public boundaries.
`NewType` is sufficient. Field and argument names state the emission/heard convention, for example
`t_cpa_heard_audio` and `t_cpa_emit_unix`. NumPy arrays retain their numeric representation; their
contracts state the frame, units and emission/heard convention.

Clock conversion changes the time origin. Propagation changes emission time to heard time. Test
these operations separately with known values: Unix time `1_700_000_000` at audio zero maps
`1_700_000_123` to audio second `123`; a 3,400 m slant range at 340 m/s adds 10 s to emission CPA.
Also test the inverse conversions and round trips.

Position-bearing records identify their coordinate frame, ENU origin where applicable and height
datum. Retain the altitude-source and terrain-datum information from Phase 0.

### R7. Expose workflows independently of the CLI

Move reusable command behavior into typed workflow functions. This includes grid construction,
event loading and selection, result ranking/selection and timestamp interpretation. `cli.py` owns
argparse declarations, terminal formatting and exit status.

Call those workflows in process on a local synthetic fixture. Exercise spectrogram creation,
fitting/detection, search and refinement without importing `cli` or patching accidental re-exports
such as `pipeline.fit_event`. Inject input adapters where a workflow would otherwise fetch data.
The smoke test runs offline.

### R8. Separate outcomes, errors and progress

An empty detection or search result has a documented status or reason. Input-read failures and
execution errors have exceptions that callers can identify. Test both paths, including CLI exit
behavior. Use domain exception classes where callers need distinct handling.

Library modules use module loggers. Configure logging at the entry point and send progress to stderr.
Stdout contains the requested table or JSON; named output files contain their documented format.
Captured-output tests must exercise progress and results in the same invocation. Error messages name
the stage and input that failed.

### R9. Run the local checks offline

Add `tools/check.sh` to run ruff, scoped mypy checks and all ordinary no-data tests. The whole command
must finish in under 90 s on this Mac, with the tests under 60 s. Record the environment and measured
times. Provision dependencies before measuring the command; installed-wheel checks use prepared local
dependencies. Include Phase 0's install and ffmpeg smoke checks.

Configure ruff for unused imports and unsafe constructs. Put mechanical fixes in separate commits
from code moves. For mypy, require annotations on public stage/workflow boundaries introduced or
changed here, and strict checking on new record/configuration/clock modules. State the checked scope
in the tool configuration. `check_untyped_defs` can check other function bodies; it does not require
annotations.

Register pytest markers and reject unknown markers. The default gate includes ordinary tests even
when they have no tier marker. Real-data tests remain opt-in and skip without their environment
variable.

Verify that the checks catch a missing required record field, an audio/Unix scalar mix-up, an option
that fails to reach its consumer and a forbidden CLI import. Use focused tests or temporary failing
patches. Record the command and failure for each; discard temporary patches afterward.

### R10. Check the numbers independently

Create baseline run folders with `tools/data/new_run.py`. Record commands, resolved parameters,
input hashes, dependency versions and the source revision. Follow AGENTS.md's data rules and keep
outputs outside the repository. Use Oyster Bay and the eagle cam as development recordings.
Do not use evaluation recordings for this preparation or the walkthroughs.

Pin a deterministic synthetic scene before moving code. Share seeded builders for repeated
spectrograms, traces and passes; specialized tests can keep local builders. Add analytical tests with
independently calculated geometry, frequency limits and propagation delays. Cover empty input and
missing-data outcomes too.

Declare comparison rules before a refactor. Unchanged deterministic paths in the same environment
must match exactly. Where numerical variation requires a tolerance, specify absolute/relative limits
per field and justify them by units and algorithm behavior. Keep expected values fixed during code
moves. Investigate mismatches before proceeding.

Compare the development recordings' candidate identities, rankings, selected flights, fitted values,
scores and refined locations. Preserve byte equality for unchanged legacy artifacts. Compare schema
and provenance changes through their adapters and assert the new metadata separately.

Run focused tests per edit. Run development comparisons after changes to numerical code or its
configuration/time wiring, and cover both recordings before completing the preparation. Documentation
changes need link and consistency checks.

### R11. Document the edit paths

Create `docs/architecture.md` with the first implementation package and update it as code moves.
Describe the actual module owners, stage inputs/results/settings, time and position conventions,
format adapters and check commands. Keep conventions in one place and link to them from module
docstrings where needed. AGENTS.md links the architecture document and the local check command.

Include recipes for adding a search gate, changing a fitting objective, adding an event/search output
field and calling a workflow from another module. Each recipe names the implementation and settings
owner, relevant tests and any schema or provenance update. A new gate gets a focused behavioral test;
fixed regression expectations remain unchanged.

### R12. Try the edit paths with a fresh session

Before implementation, use the existing documentation and a synthetic setup to walk through a
parameter change, a record-field change and a new workflow caller. Repeat those tasks after the
changes with the same setup. The final walkthrough starts with a fresh agent reading AGENTS.md and
following its link to the architecture document. Discard scratch patches after the walkthrough.

Record time spent locating the code, production files touched, missed propagation points, review
corrections and check duration. Put the observations beside the edit recipes. This records the
problems an agent encounters and gives later architecture changes a comparison point.

## Implementation order

1. Capture the post-Phase-0 baselines and analytical checks, add the local gate and start the
   architecture document.
2. Introduce the stage records and format adapters, fit sound-speed metadata and clock conversions.
3. Consolidate shared settings, expose the workflow functions and separate output streams.
4. Run the final comparisons and fresh-session walkthroughs, then update the module map and recipes.

Each package passes the checks introduced so far. Keep commits reviewable and give parallel agents
separate worktrees with explicit file ownership. Coordinate edits to shared record/configuration
files. Shared data and cache paths must not expose partially written artifacts.

Phase 1 starts when R1–R12 pass. Its handoff consists of the workflow signatures, resolved-setting
serializer, stage records and format adapters, check commands, baseline run-folder paths and
walkthrough observations in `docs/architecture.md`.
