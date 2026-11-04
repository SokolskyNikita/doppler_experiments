# Re-architecture for agent-driven development

Draft, 2026-11-03. Status: proposal, not yet in PLAN.md.

## Purpose

Most of the code on this project is written by Claude and Codex sessions, reviewed by a human. PLAN.md's
route to a usable `locate` (Phases 1 to 6) is several thousand lines of new code across every module, and
every phase after 1 is research: many short experiments, each changing a gate, a score or a fit, each judged
by a number. The code's shape decides how fast those sessions move and how many of their changes are wrong
in ways the benchmark catches late or not at all.

This document is the requirements and the technical task for a restructuring whose only goal is that:
a session can make a one-concept change by touching one place, a wrong change fails in under a minute on
this Mac, and the numbers a change produces can be trusted to come from the change and not from a slip.

It excludes everything Phase 0 covers (download margin, data report, elevation no-data, altitude source,
the `detect` hand-off, empty detections, the ffmpeg check and install smoke test), and everything Phase 1
already claims (`--jobs` and parallelism, the result record's content, the case manifest and runner,
library-backed caches, audio gaps). Where Phase 1 items need a place to land, this document provides the
place and says so.

## 1. Why sessions are slow and wrong here today

Each item names the error class, then the evidence in the tree at `dev` 41d77a0.

- **The same fact lives in several places, so a change updates some of them.** The f0 sweep
  `np.arange(0.95, 1.0501, 0.005)` is spelled out four times (`score.py:65`, `score.py:86`,
  `pipeline.py:173`, `pipeline.py:219`); the audio-to-UTC offset `t0_map = ev1.t_cpa - t_heard1` is
  recomputed in four functions; metres per degree of latitude is a literal in `search.py` and
  `pipeline.py`; the search gates have defaults in `run_search`, `run_single_search` and the CLI.
  Phase 2 item 7 replaces the gates and Phase 3 fits one clock to every event. Both start by finding
  every copy.
- **Positions and tuples carry meaning that the type system can't check.** `run_search` appends
  16-tuples and names the columns in a parallel list (`pipeline.py:149`); `detect_events` indexes
  candidate tuples with `o[4]` and sorts them with `cands.sort(reverse=True)`, which silently ties on
  f0, speed and distance; `_scan_window` unpacks a 14-tuple; `refine` returns its chosen flights in
  `DataFrame.attrs`, which `to_csv` drops. A session that adds a column or reorders a field produces
  code that runs and is wrong.
- **Time conventions are implicit floats.** Audio seconds, unix seconds, emission CPA, heard CPA and
  steepest fall are all `float`, told apart by variable names that aren't consistent (`t_cpa` is heard
  time in `EventFit`, `t0` is emission time in `tracks.py`). PLAN's E2 is a bug of exactly this class,
  and the timing-conventions experiment had to be written to find it.
- **Nothing fails fast.** There is no lint, no type check and no pytest configuration. Nine unused
  imports, a `sys` import the CLI never uses and a `top_pairs` argument nothing reads passed review.
  `pipeline.fit_event` is an accidental import that the CLI calls and a test monkeypatches. A wrong
  call compiles, runs for the 7 min a search takes, and produces a plausible CSV.
- **Logic sits where it can't be called.** `cli.main` is one 140-line function; `search` builds the
  grid and terrain there, `refine` deduplicates rows and picks a rank there, `search-single` parses
  timestamps there. `locate` (Phase 3) and the benchmark runner (Phase 1) need every one of those steps
  as a function. Today the CLI test has to monkeypatch to get at them.
- **Two entry points, two defaults.** `fit_event` defaults to the contrast objective as a function and
  to brightness through `dopplertrack fit`. Documented, and still a trap for Phase 2's fit experiments.
- **Library code prints.** `pipeline.log` and the CLI's result tables share stdout. A runner collecting
  many runs can't separate progress from output, and a session reading a run folder's log has nothing
  structured to parse.
- **Tests don't share fixtures.** Synthetic spectrograms and traces are rebuilt per file. PLAN 5.1's
  synthetic failure matrix is fifteen more such scenes; without a factory each one is fifty lines of
  setup a session has to get right.
- **The upstream-parity rule taxes every change and forbids the useful ones.** AGENTS.md requires a
  commit meant for upstream to touch no fork-only file, and PLAN.md's principle "stay mergeable with
  upstream" adds that new capabilities go in new modules and upstream defaults are kept. So a session
  must classify each edit as upstream or fork, split commits accordingly, and leave `cli.py`,
  `pipeline.py` and the defaults alone, which is where the problems above live. The fork's destination
  (`locate`, verdicts, a benchmark) diverges from upstream's proof of concept whatever the code's
  shape, and the one upstream PR so far (#2) has waited on the maintainer since it was opened.

## 2. Scope

**In:** the package under `src/dopplertrack/`, `tests/`, `tools/data/`, `pyproject.toml`, AGENTS.md,
README.md's and PLAN.md's statements of the upstream-parity rule, and a new `docs/architecture.md`. No
change to any number: the known-point and search outputs for Oyster Bay and the eagle cam must be
identical before and after every work package.

**Out:** anything that changes a result (that is Phases 2 to 4); the result record's fields, the case
manifest, the runner, the tiers and `--jobs` (Phase 1, which lands in the structure defined here);
`plots.py` and the report (Phase 5); GitHub CI (deferred by Phase 0); the experiment scripts under
`tools/experiments/`, which are records.

**Order relative to PLAN.md.** After Phase 0 merges (its PR touches every module, and a restructuring
in parallel with it would conflict everywhere), the policy commit excepted, and before Phase 1 item 2. Phase 1 item 1 (parallelism)
can run alongside work packages that don't touch `search.cpa_table` or `tracks.detect_events`.

## 3. Target architecture

### 3.0 The fork owns its code

The restructuring starts by retiring the upstream-parity rule, in writing, before any code moves:

- AGENTS.md's Git section drops "a commit meant for upstream must not touch any of them; keep upstream
  and fork-only changes in separate commits". The fork-only file list stays as a description of what
  upstream doesn't have, not as a constraint on commits. The `up/<topic>` cherry-pick recipe stays as
  the way to send a self-contained physics or data fix upstream when one is worth sending, with the
  note that such a fix is adapted onto `upstream/main` by hand and that nothing on `dev` is shaped to
  make that easier. "Commit messages follow upstream's style" stays; it costs nothing.
- The layout table's "the package (upstream's)" becomes "the package, forked from upstream at a16b700".
- PLAN.md's principle "Stay mergeable with upstream" is replaced by "Merge upstream, don't mirror it":
  upstream is merged into `dev` when it has something the fork wants, conflicts in diverged modules are
  resolved by hand and accepted as the cost, and the fork's modules, defaults and CLI are its own.
  Section 2's "sending it upstream is deferred" and the risk "Upstream moves fast" are reworded to
  match. Phase 3's "`search` keeps upstream's default" for the silence filter becomes a choice the fork
  makes on its own numbers.
- README.md's "fixes that don't need anything from the fork go back upstream as pull requests" becomes
  "self-contained fixes may be offered upstream".

Until this is merged, nothing in work packages 1 to 7 can be committed under the current rules, since
each of them edits `cli.py` or `pipeline.py` together with `tests/` and docs.

### 3.1 Layers

Modules are grouped in layers, and a module may import only from its own layer or a lower one. A
Tier 0 test asserts this from the import graph (an AST walk, no new dependency).

| Layer | Modules | Responsibility | Must not |
|---|---|---|---|
| physics | `geo`, `doppler` | pure functions of arrays; the straight-pass model, trajectory curves, geodesy | read files, log, know about events or grids |
| records | `records`, `params`, `clock`, `errors` | typed values that cross module boundaries; all tunables; the exception hierarchy | import anything but physics and the standard library |
| data | `audio`, `adsb`, `fetch`, `terrain`, `coverage`, `cache` | decode, stream, parse, persist; every on-disk format | score or search |
| model | `fit`, `detect`, `score`, `search` | turn spectrograms and segments into fits, candidates and scores | print, open files, parse argv |
| workflow | `pipeline` (later `locate`, `bench`) | compose model and data into steps that read and write run artefacts | define parameters or formats |
| cli | `cli` | argv to workflow calls, exit codes, terminal output | contain logic |

`tracks.py` splits: `fit.py` (`local_whiten`, `grid_search`, `fit_event`) and `detect.py`
(`detect_events`, the window scan). The straight-pass shape (`tracks._shape`) merges into
`doppler.ideal_curve`, one implementation parameterised by span and sample count. `ridge` stays in
`detect.py`, marked as the start of Phase 2 item 3. `plots.py` stays as it is, under workflow.

### 3.2 One place for every tunable

`params.py` holds frozen dataclasses, one per stage, with the current defaults as field defaults:

- `SpectrogramParams`: `nperseg`, `hop_s`, `fmin_hz`, `fmax_hz`, `whiten_window_s`, `sr`;
- `FitParams`: objective, `v_bounds`, `d_bounds`, the grids, `crop_pad_s`, `band_pad_frac`,
  Nelder-Mead options;
- `DetectParams`: `window_s`, `step_s`, `per_window`, `min_sep_s`, `top`, `refine`, plus its
  own `FitParams` for the refinement stage (today's `v_bounds=(35, 200)` and `d_bounds=(200, 15000)`);
- `ScoreParams`: the event window's `pad_s` and band factors (today `0.8 × f_post` to
  `1.25 × f_pre` in `score.py`, and a different `0.7` and `1.3` in `plots.py`, which then reads the
  same object), `n_samples`, `min_valid`, `shifts`, `f0_scales`;
- `SearchParams`: `max_range_m` (Phase 0's `DEFAULT_MAX_RANGE_M` moves here), `tol_s`, `v_tol`,
  `d_tol`, `silence_d_m`, `silence_margin_s`, `spacing_m`, `alive_pad_s`;
- `RefineParams`: `spacing_m`, `half_m`;
- `Paths`: the data and cache roots from the environment, resolved once; the only place in the
  package that reads `os.environ`;
- `Runtime`: `jobs` and the log level, so Phase 1's `--jobs` has a field waiting.

Every model and workflow function takes its params object, never a spread of keyword arguments with
their own defaults. The CLI builds its options from the dataclass fields, so a default is typed once.
Params serialise to JSON and are what the result record's provenance block stores (Phase 1 item 2 then
has nothing to invent).

Physical constants live in the physics layer with a name: metres per degree in `geo`, the speed of
sound reference in `doppler`, `FT` and `KT` where they are.

### 3.3 Typed records and versioned formats

`records.py` holds every value that crosses a module boundary or is written to disk:

- `EventFit`: derived fields (`f_pre`, `f_post`, `t_cpa` from `t_cpa_emit`) become properties or are
  checked in `__post_init__`; `to_json`/`from_json` carry `schema_version`, and the loader rejects
  a version it doesn't know. Phase 0's `--pick` loader uses this;
- `DetectionCandidate` (score, f0, v, d, t0) as a NamedTuple, replacing the 5-tuples;
- `GridSearchResult`, `LockedScore` (total, s1, s2, shift), `PairScore` as small dataclasses
  replacing tuple returns;
- `SearchRow`, `RefineRow`: the DataFrames are built from lists of these, and the column list is
  derived from the fields, never typed by hand. `refine`'s chosen flights become a field of a
  `RefineResult` that wraps the frame, not `attrs`;
- `TraceSetMeta`: Phase 0's `extraction_metadata` dict becomes a dataclass with a version;
- `ResultRecord`: a skeleton with `schema_version`, `provenance`, `params` and `errors`, which
  Phase 1 item 2 fills.

Rule: no function returns a bare tuple of more than two elements, and no DataFrame column list is a
string literal list.

### 3.4 Time conventions in the type

`clock.py` defines:

- `Clock(offset_s)` with `to_audio(t_unix)` and `to_unix(t_audio)`, replacing the four `t0_map`
  computations. `locked_score`, `pick_flight`, `refine` and `run_single_search` take a `Clock`;
- a naming rule, enforced by review and stated in `docs/conventions.md`: every time-valued name
  carries its frame and its convention, `t_heard_audio`, `t_emit_unix`, `t_cpa_heard`. Columns and
  fields follow the same rule. `EventFit.t_cpa` becomes `t_cpa_heard`, with the JSON loader accepting
  the old name under schema version 1.

This is deliberately lightweight: no unit library, no wrapper around floats in the hot loops. The
point is that a session reading a signature sees which time it is handed.

### 3.5 Thin CLI

Each subcommand is a function `cmd_<name>(args) -> int` in `cli.py`, registered in a dict, with the
parser built from the params dataclasses. Everything a command does beyond argv parsing and printing
is a workflow function with a typed signature. The `fit` command's brightness default becomes a
field of `FitParams` with one documented value, and the CLI either overrides it explicitly or the
library default changes to match; not two silent defaults.

Design check, not a deliverable: a 20-line `locate` prototype composing spectrogram, detect, fetch,
search and refine can be written against the workflow layer without touching `cli.py`. If it can't,
the layering is wrong.

### 3.6 Errors and logs

`errors.py`: `DopplertrackError` and subclasses `DataError` (unreadable trace, missing coverage,
missing elevation), `UsabilityError` (no usable flyovers), `NoCandidatesError`, `CacheError`. Model
and workflow code raise these; the CLI maps them to a message and an exit code; Phase 3's `locate`
maps them to verdict reasons. A broad `except` is allowed only where it counts what it skipped
(Phase 0's scan report) and says so in a comment.

The package uses `logging` with one logger per module. `pipeline.log` becomes `logger.info`. Progress
goes to stderr, results to the paths the user named or to stdout when they asked for it, never both on
one stream. `-v` and `-q` on every command. The log format carries the stage name so a session reading
a run folder's log can grep it.

### 3.7 The Tier 0 gate

`pyproject.toml` gains `[tool.ruff]` (line length 120; rules E, F, B, I, UP, with E702 and E701 on so
the semicolon-joined statements go), `[tool.mypy]` (`check_untyped_defs` everywhere; `strict` on
`params`, `records`, `clock`, `errors`, `cache`) and `[tool.pytest.ini_options]` (test paths, the
markers `tier0`, `tier1`, `tier2`, `real_data`, `--durations=10`). The dev dependency group adds
ruff, mypy, pandas-stubs and types-requests.

One command, `tools/check.sh`, runs ruff, mypy and `pytest -m tier0`, and must finish in under 90 s
here. AGENTS.md says to run it before every commit. This is the local gate Phase 0 chose instead of
GitHub CI; it is also where Phase 1's Tier 0 and Tier 1 markers attach.

### 3.8 Fixtures as factories

`tests/conftest.py` provides factories that return typed records:

- `straight_pass(f0, v, d, t_cpa, ...)`: a synthetic `Spectrogram` with the ideal curve rendered on
  noise, plus the `EventFit` that generated it;
- `scene(flights, observer, f0s)`: traces, segments and the synthetic recording an observer hears,
  generalising `test_pipeline_synthetic`;
- `uniform_spectrogram(level)`.

Every existing test that builds these by hand moves to the factories. They are the base of PLAN
5.1's synthetic failure matrix: a partial pass or a crossing tone is then one call with different
arguments.

### 3.9 Golden tests

Before any module moves, a Tier 0 golden test pins the exact numbers of a small synthetic scene:
`grid_search`'s best score and parameters, `fit_event`'s output, `cpa_table`'s rows, `pair_candidates`'
survivors and `locked_score`'s total, to 1e-9. Every work package must leave it green without editing
the expected values. The Oyster Bay known-point and search outputs are the Tier 2 check, byte for byte
against the run folder from before the work package (the CPA cache has already shown this
reproducibility holds).

### 3.10 Documentation for the next session

`docs/architecture.md`: the layer table, the import rule, the module map with one line each, the
naming conventions, the record and params rules, and recipes: "a new gate goes in `SearchParams` and
`pair_candidates`, with a row in the golden test", "a new on-disk field bumps the schema version and
extends `from_json`", "a new experiment script imports from `model` and `records`, never from `cli`".
AGENTS.md links it and stays short. Every module's docstring states its responsibility and what it must
not do, in the words of the layer table.

## 4. Requirements

Each requirement has its acceptance check. "Grep" means a check that `tools/check.sh` can run.

**Policy**

- R0. The upstream-parity rule is retired as 3.0 describes. Acceptance: AGENTS.md no longer requires
  separate upstream and fork commits; PLAN.md's principles list has "Merge upstream, don't mirror it"
  in place of "Stay mergeable with upstream"; README.md and the layout tables match; the user has
  approved the wording. This is the first commit of the restructuring and touches no code.

**Single source of truth**

- R1. Every tunable is a field of one params dataclass. Acceptance: the literals `6000`, `0.35`,
  `0.95, 1.0501`, `-8, 8.01`, `111320`, `300.0` (alive pad), `0.8` and `1.25` (the event window's
  band) and the crop pads each appear once in `src/`, and `os.environ` is read only in `params.py`.
- R2. CLI defaults are derived from the dataclasses. Acceptance: no `default=<number>` in `cli.py`
  for a value that a params class holds.
- R3. One straight-pass model. Acceptance: `tracks._shape` is gone, and the golden test for
  `grid_search` is unchanged.
- R4. `fit_event` has one default objective. Acceptance: the test `test_fit_cli_defaults_to_brightness`
  is rewritten to read the default from `FitParams`.

**Records**

- R5. No function in `model` or `workflow` returns a tuple of more than two elements. Acceptance:
  review; the module map in `docs/architecture.md` names each return type.
- R6. DataFrame columns are derived from record fields. Acceptance: `cols = [...]` literals gone from
  `pipeline.py`.
- R7. Every on-disk JSON and NPZ record has a schema version and one loader that rejects unknown
  versions. Acceptance: a Tier 0 test per format loads a current file, a version-1 file and refuses
  a version-99 file.
- R8. `EventFit`'s derived fields can't disagree with their sources. Acceptance: constructing one
  with inconsistent `f_pre` raises, or `f_pre` is a property.

**Conventions**

- R9. A `Clock` type replaces the `t0_map` arithmetic. Acceptance: grep for `t0_map` finds nothing;
  a Tier 0 test round-trips `to_audio(to_unix(t))`.
- R10. Time-valued names carry frame and convention. Acceptance: `docs/conventions.md` lists the
  suffixes; `EventFit`, `SearchRow`, `cpa_table`'s columns and `Segment` follow them.

**Layering**

- R11. The import direction is enforced. Acceptance: `tests/test_layers.py` walks the AST of every
  module and fails on an upward import; no function-local imports except `fcntl` and matplotlib.
- R12. `cli.py` contains no logic. Acceptance: every `cmd_*` function is under 25 lines and calls
  one workflow function; the CLI test suite runs each command in-process on the synthetic scene.
- R13. `pipeline.py` holds workflow only. Acceptance: `pick_flight` and the refine scoring loop live
  in `score.py`; `cached_cpa_table` and `_file_lock` live in `cache.py` beside the fingerprint and
  atomic save, where Phase 1 item 7 then swaps the internals.
- R14. `tracks.py` is split into `fit.py` and `detect.py`. Acceptance: the experiment scripts'
  imports are updated in a comment at their top (they are records and aren't run), and
  `docs/architecture.md`'s module map matches `ls`.

**Errors and logs**

- R15. Failures are typed. Acceptance: `errors.py` exists, every `raise ValueError` in `model` and
  `workflow` that signals a data or search outcome becomes a subclass of `DopplertrackError`, the
  CLI exits 2 on `DataError`, 3 on `NoCandidatesError`, 1 otherwise, and `fetch._ChainedHTTP`
  raises `DataError` when its retries run out instead of falling through to a `TypeError` on `None`.
- R16. No `print` in the package outside `cli.py`. Acceptance: grep.
- R17. Progress and results are on different streams. Acceptance: running `search` with stdout
  redirected to a file yields only the result table.

**The gate**

- R18. ruff, mypy and `pytest -m tier0` pass and run in under 90 s via `tools/check.sh`. Acceptance:
  timed on this Mac, recorded in `docs/architecture.md`.
- R19. Every public function in the package is fully annotated and `py.typed` is truthful.
  Acceptance: mypy `check_untyped_defs` reports nothing; `disallow_untyped_defs` on the strict
  modules.
- R20. Hygiene findings are fixed, not ignored: semicolon-joined statements, files opened without
  `with`, the process pool in `detect_events` as a context manager, `np.arange` in signature
  defaults, `zip` without `strict`, unused imports, the unread `top_pairs` and the uncalled
  `grid_lla`, `matplotlib.use("Agg")` moved from import time into the first plotting call, and
  `__init__.py` reduced to the package docstring and `__version__` from `importlib.metadata` in
  place of the template's `hello()`. Acceptance: ruff's configured rule set reports nothing and no
  rule is disabled per line except with a reason.

**Tests**

- R21. Fixture factories exist and the existing tests use them. Acceptance: no test file defines
  its own synthetic spectrogram or trace builder.
- R22. Golden tests pin the numbers. Acceptance: they exist before the first module move, and no
  expected value changes in any work package's diff.
- R23. The suite is tiered. Acceptance: `pytest -m tier0` under 60 s; `real_data` tests skip without
  the environment variable as today.

**Documentation**

- R24. `docs/architecture.md` and `docs/conventions.md` exist, AGENTS.md links them, and each
  module's docstring names its layer. Acceptance: a new session, given only AGENTS.md, can say where
  a new gate goes.

**Tools**

- R25. `tools/data/extract_boxes.py` and `site_traffic.py` get a `main()` and argparse, and their
  duplicated `Chained` reader moves into `fetch.py` as the local-file twin of `_ChainedHTTP`.
  Acceptance: both scripts import it; `KEEP_ALL` becomes a flag.

## 5. Work packages

Each is one session, one branch off `dev`, one or a few commits, merged only with the golden test and
the Oyster Bay byte-for-byte check green. Sizes are PLAN's S/M/L.

| WP | Content | Requirements | Size | Depends on |
|---|---|---|---|---|
| P | Retire the upstream-parity rule in AGENTS.md, PLAN.md and README.md | R0 | S | the user's wording |
| 0 | Tooling gate, pytest config, markers, `tools/check.sh`, autofixable hygiene, fixture factories, golden tests, the baseline run folders for Oyster Bay and the eagle cam | R18, R20 (part), R21, R22, R23 | S–M | WP P, Phase 0 merged |
| 1 | `records.py`, `EventFit` schema, NamedTuples and result dataclasses, derived columns | R5–R8 | M | WP0 |
| 2 | `params.py`, constants named, CLI defaults derived, one fit default | R1–R4 | M | WP0 |
| 3 | `clock.py`, naming convention, `docs/conventions.md` | R9, R10 | S–M | WP1 |
| 4 | Layer split: `fit`/`detect`, `cache.py`, slim `pipeline`, `cmd_*` functions, layer test | R11–R14 | M | WP1, WP2, WP3 |
| 5 | `errors.py`, `logging`, streams | R15–R17 | S | WP4 |
| 6 | Full annotations, mypy strict on the record modules, `py.typed` truthful | R19, R20 (rest) | S–M | WP4 |
| 7 | `docs/architecture.md`, module docstrings, AGENTS.md link | R24 | S | WP4 |
| 8 | Tools scripts | R25 | S | none |

WP P is a documentation commit and can merge today, before Phase 0, since it conflicts with nothing.
WP1 and WP2 can run in parallel in separate worktrees; they touch different files except `cli.py`,
whose parser section goes to WP2 and whose loaders go to WP1. WP8 can start at any time. Everything
else is sequential because each moves code the previous one typed.

Estimated total: three to five sessions over about a week of elapsed time, with the user's review
between packages. Phase 1 item 2 (the result record) starts after WP1; items 3 and 7 after WP4.

## 6. Acceptance for the whole

- `tools/check.sh` is green and under 90 s; `pytest -m tier0` under 60 s.
- Oyster Bay known-point and search outputs, and the eagle-cam refined result, are byte-identical to
  the run folders made before WP0, at upstream's parameters.
- The golden test's expected values are unchanged from WP0.
- A `locate` prototype of about 20 lines composes the workflow layer in a scratch file without
  importing `cli`.
- `docs/architecture.md` matches the tree, and every module docstring names its layer.
- The ruff rule count for `src/` and `tests/` is zero with the configured rules.

## 7. Decisions needed

1. **What, if anything, still goes upstream.** R0 retires the rule; this decides the residual
   practice. Proposed: nothing by default. A self-contained fix in `geo`, `doppler`, `audio`, `adsb` or
   `fetch` may be offered when the user wants to, adapted by hand onto `upstream/main`; PR #2 stays
   open as it is. No module is kept clean for that purpose.
2. **Strictness.** Proposed: mypy `check_untyped_defs` package-wide and `strict` only on the new
   record modules, so numeric code with pandas isn't blocked on stubs.
3. **Dependencies.** Proposed: stdlib dataclasses and hand-written JSON, no pydantic or msgspec. The
   records are few, the fields are floats, and one fewer dependency is one fewer thing a session gets
   wrong.
4. **Where the benchmark code lives.** `bench/` is a fork-only data directory. Proposed: Phase 1's
   runner becomes the subpackage `dopplertrack.bench`, under the workflow layer, so it is importable,
   typed and covered by the gate. With R0 there is no longer a reason to keep it out of the package.

## 8. Risks

- **Conflicts with Phase 0.** Its PR touches every module. Mitigation: start the code packages after
  it merges, and keep each work package to one or two sessions so nothing stays open long.
- **Merging upstream later gets harder.** Once `pipeline` and `cli` are restructured, an upstream
  change to either is a hand merge. Mitigation: upstream is a proof of concept with one maintainer and
  the fork already carries the CPA cache and Phase 0 on top of it; the physics and data modules, where
  upstream fixes are most likely, keep their function names and signatures through this work.
- **A silent numeric change during a move.** Mitigation: the golden test before any move, and the
  byte-for-byte Tier 2 check per package.
- **Over-engineering.** A params tree and record types can grow into a framework. Mitigation: no
  base classes, no registries, no plugins; a dataclass per stage and a NamedTuple per return, and
  nothing a session can't read in one screen.
- **Sessions skipping the gate.** Mitigation: AGENTS.md makes `tools/check.sh` the pre-commit step,
  and a work package's PR description quotes its timing.
