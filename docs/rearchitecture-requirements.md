# Architecture preparation for agent-driven development

Requirements, revised 2026-11-03. Scheduled after Phase 0 and before Phase 1 in [PLAN.md](../PLAN.md).
This document specifies future implementation; it does not mark that work complete.

## Purpose

Most code on this project is written by Claude and Codex sessions and reviewed by a human. The next
phases are research: short experiments that change a detector, fit, gate or score, each judged by a
number. Architecture should increase the number of trustworthy experiments completed per hour of
human review, and help those experiments advance the project toward a usable `locate`.

A session should be able to find the implementation of a concept, see its inputs and conventions,
change it without missing another implementation, and get useful feedback in seconds to minutes.
One concept may require coordinated updates to code, configuration, tests and documentation; the goal
is one authoritative implementation and an obvious edit path, not a one-file limit.

This is a bounded preparation phase. It establishes the contracts and feedback needed by Phase 1,
then ends. Further restructuring needs a concrete downstream task that benefits from it.

## 1. Problems this preparation addresses

The original review inspected the code at `dev` 41d77a0; the implementation baseline is the merged
Phase 0 at a03ee30. Recheck examples against current `dev` before implementing. Retain Phase 0's
coverage metadata, evidence masks, CLI hand-off and smoke checks, extending its contracts rather than
duplicating them.

- **Duplicated semantic settings.** The same f0 sweep is defined in scoring and refinement, and the
  same audio-to-UTC mapping is reconstructed at several call sites. A change can update some copies
  and miss others. Some equal-looking settings have different meanings: pair search uses a 6 s time
  tolerance and known-time single search uses 30 s. Those must remain distinct.
- **Ambiguous positional records.** Search rows are assembled as 16-tuples beside a separate column
  list, detection candidates use numeric indices, and a worker receives a 14-tuple. Refinement's
  chosen flights live in `DataFrame.attrs`, which CSV serialization loses. Field changes can produce
  plausible but wrong output.
- **Implicit time conventions.** Audio seconds, Unix seconds, emission CPA and heard CPA are floats
  distinguished mainly by names. The convention is part of the scientific meaning, and a wrong
  conversion can still produce plausible scores.
- **Weak early feedback.** The existing unit suite is useful, but there is no combined lint/type/test
  command or explicit coverage of the new boundary contracts. A syntax or wiring mistake should not
  first appear during a long search.
- **Logic owned by the CLI.** Grid construction, result selection and timestamp interpretation need
  callable interfaces for the benchmark runner and later `locate`.
- **Implicit execution context.** CLI fitting uses brightness while library fitting and detection use
  contrast. Those existing choices need explicit profiles and tests. Progress mixed into stdout and
  metadata lost during serialization make experiment evidence harder to inspect.

The current AGENTS.md permits fork-only files to share commits with upstream code. Fork architecture
commits can include source, tests and documentation; retiring an upstream policy is not a prerequisite.
The upstream relationship is a separate decision and this preparation does not change it.

## 2. Scope, sequence and stopping condition

**Order:** Phase 0 merges and passes its checks → this preparation completes → Phase 1 starts,
including Phase 1 item 1, parallelism. No required work package runs alongside Phase 0 or Phase 1.
Independent recording collection can continue. Do not renumber the existing phases.

**Required:** a trustworthy local gate, safe stage boundary records, explicit time conversion and
configuration, callable workflows, separated progress/results, regression and independent correctness
checks, and a short architecture map. These are the acceptance criteria in sections 4 and 6.

**Out of scope:** new scientific algorithms or tuned defaults; Phase 0 fixes; Phase 1's parallelism,
result record, case manifest, runner, benchmark comparisons, new cache implementations and gap-aware
audio; Phase 5's report and plotting changes; GitHub CI; edits to archived experiment scripts. The
preparation provides interfaces these features can use, without implementing their future machinery.

Preserve the numerical behavior of every existing entry point at its current parameters. Keep the
brightness profile for CLI `fit`, contrast for library fitting and detection, and the distinct pair
and single-search tolerances. Moving progress to stderr, adding explicit metadata and migrating
schemas are intentional interface changes; test and document them separately from numerical equality.
Any algorithm or default change belongs in a separate measured change after this preparation.

A larger module reorganization, exhaustive typing of numerical internals, universal fixture migration,
tools-script cleanup and an automatic CLI generator are optional future work. They do not extend this
phase or block Phase 1. Stop when the required contracts, checks and navigation recipes pass.

## 3. Architecture and implementation constraints

### 3.1 Ownership and dependency direction

Use these responsibilities to establish the required boundaries. This is not a requirement to create
a package or file for every row before Phase 1.

| Responsibility | Current or prospective owner | Boundary |
|---|---|---|
| Physics and geodesy | `geo`, `doppler` | Array calculations; no file access, CLI or workflow dependencies |
| Stage contracts and settings | Stage-owned dataclasses; small shared `records`, `params`, `clock` modules where useful | No CLI, workflow execution or I/O at construction/import time |
| Input and persistence adapters | `audio`, `adsb`, `fetch`, `terrain`, `coverage`; storage helpers extracted as needed | Decode, validate, load/save and report coverage; no scoring/search orchestration |
| Numerical stages | `tracks` or extracted `fit`/`detect`, `score`, `search` | In-memory inputs to fits, candidates and scores; no argv parsing or result-file writes |
| Workflows | `pipeline`; later `locate` and the benchmark runner | Compose adapters and numerical stages; own stage execution and artifact writing |
| CLI | `cli` | Parse arguments, invoke workflows, format terminal results and map failures to exit status |

Algorithms must be callable without importing `cli`. Keep settings and record definitions close to
their stage unless several stages need them. Shared modules must stay small; they must not collect
every helper, parameter and return value merely because it crosses a function boundary. NumPy and
pandas types are allowed where a contract genuinely contains arrays or a DataFrame; there is no
stdlib-only rule that conflicts with those types.

Persistence helpers may lock, fingerprint, load and atomically save a CPA table. The workflow keeps
responsibility for deciding to compute a miss and calling `search.cpa_table`. Do not move that
orchestration into a lower data layer that would then depend on search. Preserve the existing cache's
input identity, atomic writes and locking; replacing its internals remains Phase 1 work.

Extract `fit.py`/`detect.py`, cache storage or scoring helpers only as needed to establish these
boundaries. Preserve imports used by archived experiments through small compatibility exports where
practical, or document the old revision and replacement import in the architecture map. Do not edit
historical scripts to make them appear current. If the duplicate straight-pass shape is consolidated,
preserve each caller's sampling span, sample count and interpolation behavior.

An import check should guard concrete forbidden dependencies, including numerical modules importing
CLI/workflows. Do not invent an exhaustive six-layer AST framework or ban justified local imports.

### 3.2 Stage configuration and resolved parameters

Use frozen dataclasses for groups of settings that need propagation or provenance. Likely owners are
spectrogram, fit, detection, scoring, pair search, single search and refinement. Use immutable values
or safe factories; `frozen=True` alone does not make a contained NumPy array immutable.

Each shared semantic setting has one authoritative default and is passed explicitly to its consumers.
Equal numeric literals do not establish that two settings are the same. In particular:

- Keep pair-search and known-time single-search tolerances distinct.
- Express brightness fitting for the CLI and contrast fitting for detection/library calls as named,
  tested profiles. Detection's refinement bounds also remain explicit.
- Keep plotting crops separate from scoring crops; their existing purposes and widths differ, and
  plotting is out of scope.
- Name physical constants in `geo` or `doppler`; do not treat them as experiment knobs.

Stage entry points may accept a config object. Small helpers may take explicit scalar arguments when
that makes their dependency clearer. Do not pass an unrelated application-wide config through every
function. Keep argparse declarations explicit and obtain defaults from the appropriate profile; no
parser generation or field-reflection framework is required.

Provide deterministic JSON-safe serialization of the resolved scientific configuration for Phase 1
to reuse. Test that a CLI override reaches the workflow and numerical stage, including values that
differ from the defaults. Resolve environment-derived paths/runtime settings at the workflow or CLI
boundary, allow explicit injection in tests, and avoid environment reads or filesystem effects at
import time. Define the new `--jobs` behavior in Phase 1, not in this phase.

### 3.3 Named records and persistence contracts

Replace positional structures where field confusion can silently affect a scientific result:

- Detection candidates and window-scan requests/results have named fields. Use named access and an
  explicit ranking/tie-break key. A NamedTuple alone does not prevent indexing or lexicographic sorting.
  Preserve the current ordering during this refactor, making its tie behavior explicit and tested.
- Grid fitting and locked scoring return named records when their several values are ambiguous.
- Search and refinement expose named result objects. Refinement's selected flights are explicit
  metadata that survives serialization, not information stored only in `DataFrame.attrs`.
- A table's schema has one owner defining field names, units, dtypes and the empty-table shape.
  Construction and serialization use that schema. Explicit column lists are allowed; parallel
  positional lists that can drift are not. Do not allocate a Python dataclass for every row of a large
  array/DataFrame solely to meet a structural rule. Dynamic per-event scores need explicit event IDs
  and an adapter for existing CSV columns.

Use schema versions and explicit loaders for package-owned persistent formats touched by this work.
Treat existing unversioned files, including saved event fits, as an explicitly supported legacy format.
Test current, unversioned legacy, supported numbered legacy and unknown versions as applicable.
Document the migration policy: a persistent
user result gets a clear unsupported-version diagnostic; a regenerable incompatible cache is a miss
and rebuild. External source formats are parsed as external inputs, not rewritten to add our schema.
Do not pre-create Phase 1's `ResultRecord` or choose its fields here.

`EventFit`'s redundant fields must have a defined consistency policy. Its CPA delay and asymptote
frequencies depend on the sound speed used for fitting. Record that value for new fits before deriving
or validating those fields; never silently substitute today's default for a historical fit. An old
record without sound speed retains its stored derived values and marks the model metadata unknown,
or requires an explicit supplied value for an operation that needs recomputation. The legacy loader
must preserve its scientific values. Validate array shapes, finite required values and timestamp
ordering at stage boundaries, allowing explicitly represented invalid samples where Phase 0 requires them.

### 3.4 Time and coordinate conventions

`clock.py` owns conversion between recording-relative audio time and Unix time. Use a named anchor
such as `audio_start_unix`, with the documented equations:

- `t_unix = audio_start_unix + t_audio`;
- `t_audio = t_unix - audio_start_unix`.

A constructor from matching audio/Unix anchors is useful when a candidate flight establishes the
clock. Conversion changes the origin only; converting emission time to heard time is a separate
physical operation. Preserve today's per-candidate clock anchoring and shift treatment. Joint clock
fitting and drift remain Phase 3 work.

Use lightweight scalar boundary types, such as `NewType` aliases for audio seconds, Unix seconds and
durations. State emission/heard convention in fields and signatures, e.g. `t_cpa_heard_audio` and
`t_cpa_emit_unix`. Arrays retain NumPy representations, with frame, units and emission/heard convention
in their contract. No per-element wrappers or unit library are needed in numerical loops. Document
the ENU origin and height convention of position-bearing records as well.

Tests must use independent known values: an epoch-sized audio start maps to audio zero, a later UTC
anchor maps to its known audio offset, and a nonzero slant range produces the expected `d/c` heard
CPA delay. Include a non-default sound speed. Round trips are additional checks, not the only oracle.
Field renames need legacy loading and explicit serialization migration tests.

### 3.5 Callable workflows, outcomes and streams

Expose typed workflow entry points for existing commands. Move grid construction, event/result
selection and other reusable command behavior there. Keep argparse syntax and terminal rendering in
`cli.py`; timestamps may be parsed by a small explicit helper shared with the workflow boundary.
`cmd_<name>` functions may help dispatch, but neither a line limit nor exactly one function call is
an acceptance criterion.

A short synthetic composition should demonstrate that spectrogram, fitting/detection, search and
refinement can be invoked without `cli` or monkeypatching accidental re-exports. Use a local fixture
or injected input adapter; this check must not download data. It is a workflow smoke check, not an
implementation of automatic `locate` or the Phase 1 benchmark.

Expected empty/no-candidate outcomes carry a named status/reason or a documented empty result.
They remain distinct from execution errors such as unreadable inputs. Introduce a small domain
exception hierarchy only where callers need it, and test CLI mapping and existing behavior. Do not
turn every valid abstention into an execution error or design future verdict thresholds here.

Use standard module logging for progress, configured at the entry point, and send it to stderr.
Keep requested tables/JSON on stdout or in the named artifact, without progress mixed in. Library
imports do not configure logging. A captured-output test verifies the separation. Failure messages
identify the stage and relevant input; cached-data recovery must not swallow programming errors.

### 3.6 A trustworthy fast gate

One documented command, `tools/check.sh`, runs lint, scoped type checks and the ordinary no-data test
suite offline. Target under 90 s on this Mac, with tests under 60 s. Record the command, environment,
selected tests and measured durations. Preserve Phase 0's install/ffmpeg smoke checks.
Separate one-time dependency provisioning from the measured gate; installed-wheel smoke checks use
prepared local dependencies so the offline gate does not fetch packages.

Configure ruff with a practical initial rule set, including unused imports and unsafe constructs,
and apply mechanical fixes separately from numerical moves. Add mypy and the needed stubs.
`check_untyped_defs` checks bodies but does not require annotations: use `disallow_untyped_defs` on
the public stage/workflow boundaries this phase introduces or changes, and strict checking on the
small new contract/config/clock modules. Document the precise coverage. Exhaustively typing every
numerical helper is optional future work.

Register markers with strict marker checking. All ordinary no-data tests must run by default in the
fast gate; a test must not disappear because an author forgot `@pytest.mark.tier0`. Keep existing
real-data tests opt-in and skipped without their environment variable. Phase 1 can attach the later
tier runner to these checks without excluding ordinary tests.

The gate must demonstrate detection of representative mistakes: a missing required record field,
a scalar audio/Unix type mix-up, a configuration override that fails to propagate, and a forbidden
CLI dependency. Use small focused tests or temporary negative checks, recording the results without
committing intentionally failing code. A lint count alone does not establish these properties.

### 3.7 Fixtures, regression and independent correctness

Before changing production code, capture characterization outputs for a small deterministic synthetic
scene and existing development workflows. Create new run folders under the shared data root using
`tools/data/new_run.py`; record commands, resolved parameters, input hashes, dependency environment
and code revision. Never overwrite older runs or use evaluation recordings for this preparation.

A few composable factories for repeated spectrograms, traces and passes are useful. Share them where
they remove duplication; specialized tests may keep their own builders. Factories take explicit
seeds/configuration. Keep independent correctness oracles separate from production-model generators.
Retain or add analytically calculated geometry, asymptote and propagation-delay cases, plus
missing/empty input outcomes. A fixture rendered with the production curve is a regression aid, not
independent evidence that the curve is physically correct.

Define comparison rules before each refactor:

- Pin deterministic synthetic results in a recorded environment. Use exact comparison where promised;
  otherwise declare per-field absolute/relative tolerances justified by units and numerical behavior.
  Do not apply a universal `1e-9` tolerance to optimizers, scores, coordinates and epoch timestamps.
- Compare Oyster Bay and eagle-cam scientific payloads: candidate identity, ordering, selected flights,
  fitted values, scores and refined locations. Require exact equality for unchanged deterministic
  paths in the same environment; explain any predeclared tolerance and inspect ranking/tie changes.
- Preserve byte equality for explicitly unchanged legacy artifacts. Compare added schema/provenance
  metadata separately, and test renamed fields through a migration adapter. Numeric equivalence must
  not conceal a missing field, changed units or lost refinement metadata.
- Keep characterization expectations fixed during structural changes. A mismatch is investigated;
  updating expected values or widening tolerances to make a move pass is not acceptance.

Run focused contract tests per edit and development-data comparisons for each package touching the
numerical path or its parameter/time wiring. A documentation-only package needs documentation checks,
not a long audio run. Final acceptance covers both development recordings.

### 3.8 Navigation and evidence of agent usefulness

Start `docs/architecture.md` with the first implementation package and update it as ownership changes.
Keep it short: actual module map, stage inputs/results/settings, time and coordinate conventions,
compatibility adapters, dependency boundaries, and commands for focused and full checks. AGENTS.md
links it and names the fast gate. Put detailed conventions in one linked location rather than
copying them across module docstrings.

Give concrete edit recipes for adding a search gate, changing a fitting objective, adding an event or
search output field, and adding a workflow caller. Each names the implementation, settings owner,
relevant tests and compatibility/provenance obligations. The gate recipe points at focused behavioral
tests, not an instruction to change a fixed golden baseline.

Before and after preparation, walk representative parameter, record and workflow changes on the same
small synthetic setup. Record the time to find the edit path, production files involved, missed
propagation points, review corrections and check duration. A scratch patch may demonstrate the path
and then be discarded; no new feature or benchmark project is required. Use these observations to
assess agent usefulness without inventing a percentage-speedup claim or tuning on evaluation data.

## 4. Required outcomes and acceptance

These are semantic checks. Grepping numeric literals, counting command lines or banning all local
fixtures is not a substitute.

| ID | Required outcome | Acceptance |
|---|---|---|
| R1 | Correct sequence and bounded scope | Phase 0 is merged before implementation; every required row here passes before any Phase 1 item starts. Optional work does not delay handoff. |
| R2 | Trustworthy fast gate | `tools/check.sh` runs lint, declared type checks and all ordinary no-data tests offline in under 90 s; tests take under 60 s. Strict markers and real-data skipping work. |
| R3 | Useful static contracts | Changed public boundaries are annotated and enforce missing annotations; contract modules pass strict checks. Representative record/type/dependency mistakes are caught. |
| R4 | Named scientific boundaries | Detection/worker/scoring and search/refinement interfaces expose named fields where confusion was possible. Candidate ranking has an explicit tested tie key. |
| R5 | Persistent metadata and schemas | Refinement selections survive round trip; table names/dtypes/empty shape have one owner; touched formats handle current, legacy and unsupported versions explicitly. |
| R6 | Consistent event model metadata | New fits retain sound speed; derived-field validation uses it. Legacy fits retain their stored scientific values without inventing missing model metadata. |
| R7 | Explicit time and position conventions | Scalar frame types, array contracts and clock anchors are documented. Independent UTC/audio, `d/c` and non-default-sound-speed tests pass. Position records identify their frame/height convention. |
| R8 | Authoritative resolved settings | Shared semantic defaults have one owner. CLI/library/detection profiles and pair/single tolerances preserve existing behavior; override propagation and config serialization are tested. |
| R9 | Callable workflows and dependency boundaries | Existing workflows run in process without CLI imports or accidental re-exports. Numerical stages have no CLI/workflow dependency; persistence does not orchestrate search. |
| R10 | Observable outcomes | Expected empty results and execution errors are distinguishable. Captured CLI stdout contains requested results, stderr contains progress, and refinement metadata is retained. |
| R11 | Refactor safety | Pre-move characterizations and independent correctness checks pass; both development recordings satisfy the declared payload/legacy-artifact comparisons. Expectations are not rewritten to hide drift. |
| R12 | Accurate navigation and agent evidence | Architecture map and edit recipes match the tree; AGENTS.md links the check command. Representative change walkthroughs and check durations are recorded. |

## 5. Work packages and handoff

All four packages follow the merged Phase 0. Keep commits reviewable and separate mechanical cleanup
from contract or numerical moves. Each package leaves the fast gate green and updates the architecture
map. Record baseline and comparison evidence in new run folders, with commands/parameters as required
by AGENTS.md; if an experiment is performed, add its record under `docs/experiments/`.

| WP | Deliverable | Requirements | Depends on |
|---|---|---|---|
| A | Baseline characterizations, independent correctness checks, offline gate and initial architecture map | R2, R3 foundation, R11 foundation, R12 foundation | Phase 0 merged and checked |
| B | Named stage results, table/schema adapters, sound-speed metadata and explicit clock/time contracts | R3–R7 | A |
| C | Canonical settings/profiles, reusable workflow entry points, dependency guard and streams/outcomes | R8–R10 | B |
| D | Final synthetic/development compatibility checks, representative agent walkthroughs and finished navigation docs | R1–R12 | C |

Use one topic branch/worktree per implementation agent. Parallelize only independent edits within a
package with explicit file ownership; different sections of the same central file are not independent
ownership. There is no prescribed session count. Review scope at each package boundary and remove
optional cleanup rather than expanding this preparation.

The Phase 1 handoff names the stable workflow entry points, resolved-config serialization, stage
records, supported format adapters, fast-check command and baseline run folders. Phase 1 starts with
its own parallelism item, then owns the result record, runner, cases, cache additions and audio gaps.
No part of that handoff requires a prebuilt future result schema, scheduler or benchmark framework.

## 6. Completion and deferred work

Preparation is complete when all R1–R12 checks pass, the numerical behavior of existing workflows is
preserved, and a fresh session can follow the edit recipes to identify and validate a parameter,
record and workflow change. Record remaining optional work and proceed to Phase 1; perfect module
symmetry, complete numeric typing or universal fixture reuse are not additional exit criteria.

Optional work is considered later only with a concrete benefit to the next task: further splitting
`tracks` or `pipeline`, broad annotation/style cleanup, `tools/data/` CLI cleanup, fixture expansion,
and extra import-graph checks. The existing upstream contribution procedure remains in force.

Main risks and controls:

- **Preparation grows into a framework.** Use the required outcomes and four-package stopping rule;
  avoid registries, generated parsers, plugin systems and speculative future schemas.
- **Moves hide a scientific change.** Capture post-Phase-0 baselines first, retain independent oracles,
  preserve explicit profiles and compare scientific payloads as well as serialization.
- **Central contracts cause parallel conflicts.** Keep ownership stage-local where possible and
  coordinate shared-file edits; worktrees isolate code, not shared data/caches.
- **A green gate gives false confidence.** Ensure ordinary tests cannot escape marker selection and
  demonstrate that representative semantic mistakes are caught. The Phase 1 benchmark remains
  necessary for scientific quality; this preparation does not replace it.
