# Research readiness

**Status:** written 2026-11-07. R1 done and merged to `main` on 2026-11-07 (the split and the naming in standard terms; checked locally, the dev-box `tools/check.sh` runs in R8 per AGENTS.md) (its ledger entries are in `$DOPPLERTRACK_DATA/runs/2026-11-07-readiness-ledger/`). R2 done and merged to `main` on 2026-11-09
(checked locally, synthetic outputs equal R1's apart from the new keys; ledger entries 14–21). R3–R9 not started. This is the first of two plans. No research in
[PLAN.md](../../PLAN.md) starts until every exit check in §5 passes. Implementation is authorized by the owner's
implementation instruction; status changes are recorded here only.

## 1. Goal

Make the code a place where experiments can be run properly: each statistical, signal-processing or
data-science method lives in its own file, the two current recipes (`grid_pair` and `collective`) become thin
compositions whose parts can be swapped and whose settings can be changed, and a small study runner runs
variants against a baseline with complete case accounting, locally or on the AWS fleet.

The current methods are not considered good, and many refinements are blocked by the architecture. This plan
removes that block. It does not try to make the methods better: that is research, and belongs in PLAN.md.

## 2. Rules

1. **One method per file.** A method is one mathematical or statistical operation with its own assumptions:
   a whitening, a tracker, a frequency estimator, a regression, a null, an assignment rule, a grid planner.
   Shared result types go in small type modules beside them. Plumbing (I/O, caching, CLI) is not a method.
2. **Plain composition, no framework.** A recipe is ordinary Python that calls method functions. Its settings,
   including which method to use at each point where an alternative exists, are fields of one parameters
   dataclass per recipe, with today's values as defaults. A method choice is a name looked up in a small dict in
   the recipe module. There is no universal stage list, no shared pipeline object model, no plugin loading and no
   templating system. Add a seam where an experiment needs one; don't pre-build seams nobody asked for.
3. **Outputs may change; accuracy is not the goal.** Exact equivalence with the current code is not required.
   Changes that come from the cleaner structure, fixed defects or unified conventions are allowed. Every one of
   them goes in the behavior-change ledger (§4). Choosing a method or a default because it scores better on real
   recordings, tuning anything on real data, or reading labels to judge this work is research and is out of scope.
   R9 scores labels only to give PLAN.md its starting point; no readiness item or default changes because of them.
4. **History is reproduced at its own revision.** Old results are reproduced with `bench run --revision <commit>`
   (the exported, hash-checked environments in [revisions.py](../../src/dopplertrack/evaluation/revisions.py)), not
   with import aliases. The compatibility layer can therefore go (R3). Dated scripts under `tools/experiments/` are
   records of their revision and are not updated, except for links to moved documents.
5. **Compute and checks follow [AGENTS.md](../../AGENTS.md).** Targeted tests while editing; no heavy computation
   on the Mac. No AWS use until every local item and local test is done; then R8, then R9. Every fleet launch
   passes `--check` and `--rehearse` first.

## 3. Work

Each item lists what is done and when it is finished. Items in different areas can run in parallel worktrees with
one owner per area: detection and fitting; tracking; scoring and coherence; CPA and the `grid_pair` recipe; the
`collective` recipe; the benchmark and study runner; AWS. R1 and R2 landed for every area at once (owner's
instruction, 2026-11-07), and R3 does too, since the aliases it removes span every area.

### R1. Split every method into its own file

**Done (2026-11-07).** This section keeps its pre-R1 file and function names. The ledger's old-to-new table maps
them to the current ones.

Split each file that holds more than one method. File names below are suggestions; the split is what matters.

| Current file | Methods to separate |
|---|---|
| `components/spectrogram.py` | audio decoding and AudioMoth placement; STFT in dB; time-axis median whitening; across-frequency median whitening. The `Spectrogram` container stays as a type. |
| `components/detection/grid_scan.py` | local median whitening (`local_whiten`); ridge Viterbi (`ridge`, `ridge_track`); curve contrast and sweep weights; curve-template grid search (`grid_search`); Nelder–Mead event fit (`fit_event`); variable-projection track regression (`fit_track`, `_profile_rss`, `_z`); sliding-window scan with greedy non-maximum suppression (`_scan_window`, `merge_candidates`, `detect_events`); the S1 off-curve z-score (`rescore_z`); the S2 time-reversed null (`rescore_null`). `EventFit` and `Track` move to a types module. |
| `components/fitting/profile_hypotheses.py` | profile-likelihood ranges; least-squares hypotheses; fit-event hypotheses; hypothesis merge and fallback gate. |
| `components/scoring/trajectory_brightness.py` | curve-brightness scorer (`EventWindow`); modelled heard curve; steepest-fall locator; locked two-event score and single score. |
| `components/scoring/coherent.py` | filters and resampling; de-Dopplerising warp; block spectra; harmonic pooling (`harmonic_weights`, `pooled`); block-path dynamic programs; tone score. |
| `components/tracking/viterbi.py` | sub-bin frequency estimators (quadratic, Candan, Quinn); peak-picking Viterbi with an off state; segment rules (cut, link, crossings); harmonic linking. |
| `components/tracking/hmm.py` | one method (the hysteresis HMM); it only loses its imports of harmonic pooling and of the Viterbi module's measurement code, which move to their own files. |
| `components/tracking/likelihood.py` | Rician log-likelihood evidence; forward–backward posterior; run extraction. |
| `components/search/grid.py` | position grid; 1 Hz trajectory segmentation; CPA table build; CPA table storage; the v/d tolerance gate (`pair_candidates`); the time-bucket pair join; the silence filter (inline in `join_pairs` today). |
| `data/trajectories.py` | trace parsing; region loading; day-seam joining; aircraft-type filter. |
| `evaluation/tier1.py` | label-to-detection matching; threshold and ROC curves; fit-error reference. These are evaluation methods and stay in `evaluation/`. |

Method logic that is inline in the recipes moves out the same way:

- `methods/grid_pair/pipeline.py`: the robust event null (`event_null`); the steepest-fall consistency gate and
  clock anchor (`_score_triples`); the hypothesis-pair join (`_pair_hypotheses`); the f0 sweep; the z-sum pair score
  and best-clock dedup inside `run_search`; extra-event flight assignment (`pick_flight`); the fine-grid refinement
  score (`refine`, `_score_fine_points`); the absolute-time and v/d gates inside `run_single_search`. The segment
  clip-box computation repeated in three places becomes one function.
- `methods/grid_pair/runner.py`: the pair rules (`top2`, `comparable`); the usability filter; the clock gate; the
  per-pair dedup.
- `methods/collective/search.py`: the log-frequency brightness view (`LogView`); coarse and fine sweeps; window
  nulls; clock-vote candidates; pass-window assignment (`_clock_matches`); the point score; coarse-cell selection
  (`keep_cells`); the fine grid; mode extraction (inline in `collective_find`).

Duplicates are merged into one implementation: the robust median/MAD null (`event_null` and `window_nulls`) and
the top-two pair rule (`evaluation/runner.py:pick_detected` and the runner's `top2`).

Finished when no file holds two methods, every recipe calls methods instead of embedding them, and the
dependencies between methods run through shared types rather than through another method's module (today the
HMM tracker imports harmonic pooling from the coherence scorer, and collective builds fake `EventFit`s), and every
method is named and described in standard terms: each method file, function, class, parameter and constant uses the
term the reference literature (`$DOPPLERTRACK_DATA/reference/`, `docs/reference/`) uses for the concept, and each
method file's docstring opens with that term and a citation. A statistic with no standard name (S1, for example) says
so and defines itself. A renamed definition keeps an `# old name: X` comment, and the ledger holds the old-to-new
table. Names that are part of an output (result-record and JSON keys, CLI flags, benchmark profile names, the
`STATISTIC` identity) keep their spelling until R6's record work; the ledger lists them.

### R2. Make both recipes configurable compositions

Give each recipe one frozen parameters dataclass, `GridPairParameters` in `methods/grid_pair/parameters.py` and
`CollectiveParameters` in `methods/collective/parameters.py`. Each groups its settings into a few nested
dataclasses, one per stage: spectrogram, detection, event source, gates, scoring, null, refinement, and planning
for collective. The recipe reads every setting below from that object and no longer from a module constant, a
literal or its own keyword default. Field names follow R1's naming rule. Run settings that cannot change a result
(workers, cache paths, `progress`, `log`, output folders) stay as arguments and are not parameters.

Settings that become fields, by where they live today:

- **Both recipes, spectrogram** (`components/stft.py`, `spectrogram_from_blocks`): `nperseg`, `hop_s`, `fmin`,
  `fmax`, `nfft`, `whiten`, `whiten_window_s`, `bg_hz`; the per-window `spectral_floor` (`local_whiten`).
- **grid_pair, detection** (`detect_events`, `fit_event`): band, `window_s`, `step_s`, the v/d/f0/t0 grids and steps,
  `n_curve`, `top`, `per_window`, `min_sep_s`, `min_score`, `refine`, the refinement bounds (`v_bounds`, `d_bounds`,
  ±120 s), the objective; the statistic's settings (`OFF_CURVE`, `CONTRAST_DF`, `SWEEP_FLOOR`).
- **grid_pair, event source and pair rule** (`methods/grid_pair/runner.py`, `evaluation/runner.py`): `TOP_K`,
  `USABLE_VALID_SHARE`, the pair rule; `DAY_SLACK_S`, `GATE_PAD_S`, the clock gate's start and tolerance.
- **grid_pair, gates and pairing** (`pair_grid_search`, `single_grid_search`): `tol_s`, `v_tol`, `d_tol`, the
  negative-information distance (`silence_d_m`) and margin, `max_range_m`, `time_convention`, the inflection
  gate (`sf_tol_s`, `sf_window_s`, `sf_smooth_s`, `INFLECTION_FLAT_RATIO`, `clock_anchor`), the alive window
  (±300 s), harmonics, `temperature_c`.
- **grid_pair, hypotheses** (`components/fitting/`): `MAX_OPTIMA`, `LS_DCHI2`, `NULL_DELTA`, `MODEL_ERROR_FACTOR`,
  `MIN_SEP_S`, `V_BOUNDS`, `D_BOUNDS`, `TAU_REACH_S`, `COARSE_V`, `COARSE_D`, `LS_Z_SPAN_MIN`.
- **grid_pair, scoring and null** (`custom_locked_score`, `custom_single_score`, `EventWindow`, `f0_sweep`,
  `event_decoy_null`): the shift grid (−8 to 8 s by 0.5), the f0 scales (0.95–1.05 by 0.005), the crop pad (40 s)
  and samples (160), `null_n`.
- **grid_pair, refinement** (`refine`, `pick_flight`): `spacing_m`, `half_m`, the extra events' harmonics and f0
  sweep, `alive_pad_s`.
- **collective** (`methods/collective/search.py`, `components/planning/`, `components/assignment/`,
  `components/scoring/`, `components/nulls/window_decoy_null.py`): `COARSE_M`, `FINE_M`, `MARGIN_SIGMA`,
  `MAX_CELLS`, `F0_SPAN`, `CLOCK_BIN_S`, `AGREE_S`, `PASS_FALLBACK`, `SUB_S`, `LOG_DU`, the coarse and fine sweeps
  (`coarse_sweep`, `fine_sweep`), the view crops (pad 40 s, 0.45–2.0 × f0), `MODE_SEPARATION_M`, `MAX_MODES`,
  `NULL_N`, `max_range_m`; and R5's mode-rule settings.

Plumbing constants (`SCORE_CHUNK`, `CHUNK`, `CPA_TILE_M`, `CPA_COLUMNS`, `CPA_CACHE_VERSION`, `STATISTIC`) stay
constants. A setting found later that changes a result is added to its dataclass in the same way.

**Method choices.** A choice is a field holding a name, looked up in a small dict in the recipe module. Seams go
only where two methods exist today or where PLAN.md's next gates need one. Each dict holds today's choice as its
default:
- grid_pair: the event source (saved fits; detection with `top2`; detection with `comparable_pairs`), the detection
  statistic (the fit's contrast; S1 `custom_rescore_zscore`; S2 `rescore_surrogate`), the event gate (rectangular
  gates; profile-interval hypotheses, today's `hypotheses=True`), the score normalisation (raw; `pair_zscore`
  against the decoy null, today's `comparable=True`), the time convention, and the clock anchor (heard CPA; the
  Doppler inflection).
- collective: the curve-integral view (`LogView`; `EventWindow`), and the window-pass assignment
  (`greedy_assignment`). The dict has one entry until PLAN.md G4 adds exact matching.
- both: the spectrogram whitening (`whiten_time`; `whiten_frequency`).

Not seams in R2: the frequency trackers (`viterbi`, `hysteresis_viterbi`, `hmm_tracker`), which no recipe calls
today. A gate that needs one wires it in as the least-squares hypotheses' track source, in place of
`ridge_track`. Also not seams: the null, the planner and the fine-grid shape, which have one method each.

**Defaults and profiles.** A dataclass default is today's library default, the keyword default of the function
the setting comes from. A profile is a named set of overrides, and resolution runs in this order: dataclass
default, then profile, then case (`bench/cases.json` geometry, gates and refinement), then the run's explicit
overrides (`--search-param`, CLI flags, collective's config `parameters`). Today's profiles become:
- `saved-fit`: the case's fits and harmonics;
- `raw-audio`: detection with band 60–300 Hz, `top` 10, one harmonic, 240 s windows, then `top2`;
- `locate`: `LocateConfig`'s defaults, that is `comparable_pairs`, the negative-information filter on at 6 km and
  the clock gate on.

`LocateConfig` is removed. `locate`, the installed CLI, `bench` and the collective command all build the same
parameters object, so a profile is data, not a code path.

**Records.** Every result records its fully resolved parameters, after all four layers, as one JSON object with
the dataclass field names. grid_pair writes it under the result record's `provenance.parameters.resolved`. If
`runtime/records.py`'s validator refuses the new key, the schema version is bumped and old records stay readable.
Collective writes it into its output dict until R6.6 gives it a record. Existing output keys keep their spelling
(R6 decides them); where a field's name differs from the key it fills, a comment maps the two. R2 lands before R6,
whose study runner prints each arm's differences from these resolved parameters.

**Behaviour.** With default parameters and each profile, the outputs on the synthetic fixtures equal R1's
(`1ad8d8c`), apart from the new `resolved` block. Any difference goes in the ledger.

Finished when:
- every setting listed above is a field and the recipe code reads none of them from elsewhere;
- results record the fully resolved parameters;
- a test resolves each profile and checks that the resolved object matches what the code used before R2;
- a test runs each recipe once per alternative method choice, one change from the defaults at a time, on a
  synthetic case;
- the CLI, `bench` and the collective command reject unknown parameter names.

### R3. Remove the compatibility layer

Delete the top-level alias modules (`dopplertrack.tracks`, `.score`, `.search` and the rest), the
`sys.modules` redirects, the `bench/` module shims (keeping `python -m bench` as the entry point),
[refactor-module-map.json](../refactor-module-map.json) and the alias and pickle tests in `tests/test_layout.py`.
Update the remaining internal users. After R2, `evaluation/tier1.py`, `prepare.py`, `report.py`, `private.py`,
`cases.py` and `runner.py` still import legacy module paths, and so do 38 files in `tests/`, `bench/` and `tools/`
(dated experiments excepted). R1 already re-pointed the aliases at its renamed modules, so a legacy name that R1
renamed (for example `dopplertrack.score.locked_score`) no longer resolves. Cached pickles that name `EventFit`
under its old path are unreachable since R2 changed the detection key (ledger entry 14), so they are rebuilt
rather than shimmed. The `# old name:` and `# old module:` comments stay: they are the record that links the dated
experiments to the current names.

The command-line entry points move with the aliases:
- add `src/dopplertrack/__main__.py`, so `python -m dopplertrack` runs `commands.main` (moved here from R5);
- point the installed script in `pyproject.toml` (`dopplertrack = "dopplertrack.cli:main"`) at `commands.main`;
- `evaluation/cases.py`, which starts the current tree's CLI as `-m dopplertrack.cli`, uses `-m dopplertrack`;
- `evaluation/revisions.py` starts another commit's CLI as `-m dopplertrack.cli`. Commits before R3 have only that
  name and later ones lack it, so the revision's own export decides: `-m dopplertrack.cli` where
  `dopplertrack/cli.py` exists in it, `-m dopplertrack` otherwise. A test covers both kinds of export.

Finished when nothing imports or runs a legacy name, the installed `dopplertrack` command, `python -m dopplertrack`
and `bench run --revision` at a pre-R3 commit all work, and `docs/architecture.md`, `docs/layout.md` and
`AGENTS.md` link only canonical paths.

### R4. Cache identity per method

The detection cache key is an AST hash over a hand-maintained list of definitions in `runtime/cache.py`
(`DETECTOR_CODE`, nine modules since R1). The spectrogram cache hashes the six modules listed by hand in
`components/spectrogram_cache.py` (`SPECTROGRAM_MODULES`). The CPA table has no code hash and depends on a manual
`CPA_CACHE_VERSION` bump (`components/search/cpa_storage.py`, version 2). R1 and R2 kept the two lists in step by
hand. Since R2 the recipes pass every detection setting from the resolved parameters, so the detection key already
covers them (ledger entry 14); what remains is the hand-kept code lists and the CPA table's manual version.

Key each cache by the source of the method files its producer uses, plus resolved parameters and input hashes,
declared next to the producer. Give the CPA table the same kind of key. Keep the existing test that checks the
key covers everything the producer can reach.

Finished when moving or editing a method file invalidates exactly the caches that use it, and the CPA table no
longer needs a manual version bump.

### R5. Fix the known defects

These change outputs and go in the ledger. Each gets a test.

- **Collective search:** complete-unit enforcement (extra-cell merging currently accepts any `result.json`); the
  statistic identity written into every output, including launcher labels, NPZ null exports and merged summaries;
  null tooling that refuses incompatible or missing draws (it currently reads only `null_draws.npz` and skips units
  without it). Today the merging and the null tooling exist only in the dated scripts
  `tools/experiments/2026-11-04/collective_run.py` and `collective_null.py`, which stay as records (rule 4). The
  fixes go into the package's collective path, which R6.1's profile and R6.6's record run on. R2 made the mode rule's spatial separation and number of modes fields of
  `CollectiveParameters.planning` (`mode_separation_m`, `max_modes`); R5 adds the rest there, with today's behavior
  as the default: the clock separation, clocks kept per point, and merging modes across all cells. Choosing their
  values is PLAN.md G1.
- **HMM tracker decoding:** `forward_backward.runs`, used by `hmm_tracker.hmm_posterior_track`, takes a per-frame
  argmax of the forward–backward posterior,
  which can return a frequency sequence that breaks the transition limits
  ([review](../reference/course-reading-review.md)). Add Viterbi decoding with backtracking as a selectable decoder,
  a field of `HMMTrackerParams`. The default stays as it is, because the tracker rounds are closed research.
  Adopting it is PLAN.md G4.
- **Trace parsing and file handles:** compare ours (`data/trace_parsing.py`, whose `TRACE_ERRORS` already
  includes `KeyError`, and `data/providers/adsblol.py`) with upstream's fixes in `upstream/main`'s `adsb.py` and
  `fetch.py`: trace rows that are dicts, the narrowed `TRACE_PARSE_ERRORS`, and explicitly closed CLI file
  handles. Import what ours lacks as explicit method imports.
- **Coverage preflight:** `_covered_days` (`methods/grid_pair/runner.py`) treats separated intervals as one span;
  report gaps instead.
- **Null-day mapping** onto the recording date for metadata-gated runs.
- **CPA build:** `jobs=1` and `jobs=N` produce the same table.
- **Empty inputs:** define behavior for empty CPA or window paths and for fine grids with missing terrain.
- **Process pools:** the package already uses its spawn wrapper (`runtime/parallel.process_pool`) everywhere; the
  raw pools are in dated scripts, which stay. Add a test that fails on a raw `ProcessPoolExecutor` or
  `multiprocessing.Pool` outside `runtime/parallel.py` and `tools/experiments/`, so new study and benchmark code
  keeps to the wrapper.

### R6. Study runner: just enough for experiments

Extend the existing benchmark (`bench run`, profiles, `--search-param` overrides, shards, `--resume`, `merge`,
`compare`) rather than building a second system.

1. **Collective in the benchmark.** A `collective` profile that runs end to end from a case (detections to
   windows to search) on R2's `CollectiveParameters`, and control draws that substitute another day's traffic for
   the same recording.
2. **Study files.** `bench study run STUDY.json` reads cases, a baseline (recipe, profile, parameters), variants
   (parameter overrides, including method choices), the control-day lists and a master seed (for null and
   normalization draws), and runs each arm as an ordinary benchmark run inside one study folder. It records each
   arm's resolved parameters and prints the differences from the baseline before running, so nothing changes
   unannounced.
3. **Labels stay out of workers.** Workers get the labels-free case; the projection also strips
   `expected_outcome` and other evaluator-only fields, checked on the serialized request, not only in memory.
4. **Complete accounting.** `bench compare` (and the study summary) reports, per arm and case group: scheduled,
   answered, abstained, no candidate, failed, incomplete and missing. The denominator is the scheduled list, never
   just what finished; paired differences use only cases complete in both arms. For old runs with no scheduled
   list the denominator is reported as unknown.
5. **Bounded units.** A per-unit wall-time cap, a required study-file field with no default, marks a unit
   incomplete rather than letting it run on; a timeout is never counted as a result.
6. **A minimal collective result record.** Collective outputs get a versioned, validated record: windows, modes
   with their matched passes, the statistic identity, and the null block for control draws. Old records stay
   readable. The fuller schema-v3 design is in git history if a later study needs more.
7. **AWS.** Arms and shards launch through the existing `tools/aws/runs`. Add a study-wide limit on concurrent
   boxes and vCPUs that is checked before each launch, and make the box lifetime cover output upload (today
   `max_hours` starts after preparation and bootstrap cancels its fallback shutdown first).

Finished when a study with a baseline, two variants and wrong-day controls runs on a synthetic fixture locally and
reports complete accounting, including deliberately failed and missing cases.

**Not built here**, and added only when a real study shows the need: a journaled multi-attempt state machine,
a global admission authority, EC2 client tokens and reconciliation, sealed-artifact dependency graphs, adaptive
discovery contracts, a remote or always-on controller, and a GPU backend. The detailed design for these is the
2026-11-06 study-runner specification, archived privately with the owner's records.

### R7. Tests with known answers

- Each method has small tests of its own contract (units, shapes, masks, score direction).
- A synthetic scene with a known receiver, flights, f0 and clock runs end to end through both recipes and must
  recover the receiver. This checks the software, not performance.
- The pass-window assignment (`greedy_assignment`) is checked against an exhaustive reference on tiny graphs,
  including ties, caps and shared-pass conflicts.
- Serial and parallel runs of detection, CPA build, the decoy nulls and the collective search give the same
  results. R1 removed the S2 rescoring's pool test, which ran a dated script; the package's own S2 path has no
  pool.

### R8. Final AWS phase

All local work and local checks finish first. Then, after the owner signs in to the `dopplertrack` profile in
their own terminal: run `tools/check.sh` on the dev box against the final source, and the opt-in Oyster Bay test
(`tests/test_oyster_bay.py`, whose imports R1 rewrote); run `tools/aws/check.sh` and
deploy only if the box lifetime change (R6.7) needs a new launch template, with the owner's approval of that
deployment; and run one small study on the fleet using the synthetic fixture to verify launch, caps, upload,
collection and termination, after its `--check` and `--rehearse` pass. Credentials are never pasted into chat.

### R9. New baseline

Run the rebuilt `grid_pair` (saved-fit, raw-audio and `locate` profiles) and `collective` recipes, with default
parameters, on the existing benchmark cases on the fleet, rebuilding caches once. The spend needs the owner's
approval before launch. Record it as `docs/experiments/<date>-readiness-baseline.md` with the behavior-change
ledger's summary. These numbers are PLAN.md's starting point and are not used to tune anything.

## 4. Behavior-change ledger

Every change that alters an output (R1–R5) gets one entry: what changed, why, which method or recipe, and its
effect on the synthetic and fixture tests. The ledger is `ledger.md` in
`$DOPPLERTRACK_DATA/runs/2026-11-07-readiness-ledger/`, beside R1's naming review and term checks; every later
item appends to it. R9's record summarizes it. An unexplained output change blocks
the item that caused it. If a change flips the strict expected failure in `tests/test_oyster_bay.py`, record it here
and remove the marker; it is not an accuracy result.

## 5. Exit checks

Research may start when all of these hold:

1. R1–R3: no file holds two methods; methods are named and described in standard terms; both recipes are compositions with a parameters dataclass; no legacy imports.
2. R4: caches are keyed per method and parameters; the CPA table has a code-derived key.
3. R5: every listed defect is fixed and tested.
4. R6: the study runner runs baseline, variants and controls with complete accounting, locally and on the fleet.
5. R7: the known-answer tests pass.
6. R8: `tools/check.sh` passes on the dev box against the final source; the fleet study ran and its boxes
   terminated.
7. R9: the baseline record exists.

PLAN.md's first gate starts from this point.

Owner decisions along the way: signing in to the `dopplertrack` profile for R8; approving a launch-template
deployment if R6.7 needs one; approving R9's spend.

## 6. Out of scope

Everything that seeks better accuracy or a scientific verdict: new methods, changed defaults chosen by results,
the collective successor study, nulls and thresholds, detector redesign, the private recording pilot and any use
of private recordings, including the private-case `locate --site` interface (PLAN.md §5). Those are in [PLAN.md](../../PLAN.md). An engineering need discovered during research is
handled inside that research item, not added back here.

## 7. Earlier labels

| Earlier label | Where it went |
|---|---|
| Bundle M1 (harmonic pooling extraction) | R1 |
| Bundle E1–E3, E5 (study runner) | R6, reduced to what experiments need |
| Bundle E4a, E4b (managed AWS) | R6.7 and R8, reduced |
| Bundle F1–F3 (frequency measurement, track regression, background) | R1 |
| Bundle M3 (exact-assignment comparator) | the reference test in R7; exact assignment as a method is research (PLAN.md) |
| Bundle M4, M5 (scientific recipe, execution) | PLAN.md |
| PLAN Gate 0 (software baseline) | §5 exit checks |
| Proposal `2026-11-04-schema-v3` (deleted; in git history at `64e8337`) | R6.6, reduced |
| `docs/phase1-preparation.md` (deleted; done) | its open CPA-equivalence item is in R5 |
| Proposal `2026-11-04-collective-decision` (deleted) | PLAN.md G1–G3 |
