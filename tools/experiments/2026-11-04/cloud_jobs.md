# Cloud jobs

One section per engineer; each lists its jobs' commands, units, inputs, split and merge.

[`tools/data/shards.py`](../../data/shards.py) (tested in `tests/test_shards.py`) is the repo's one shard, resume and
merge mechanism. SDE-C's `units.py`, built for its jobs at the same time, gives way to it once both sets of jobs have
run once.

## SDE-C

# SDE-C's jobs for the AWS fleet

Three jobs, each run through `tools/aws/runs launch` from a committed head, so the box gets that commit and no
uncommitted diff. The box sets `$RUN` to `runs/<id>/` and writes its `run.json`; each command below takes that
folder as its first argument.

Every job is a list of units (`units.py`). Each unit writes one JSON file, atomically, when it finishes, and a
unit whose file already exists is skipped:
- **Resume:** running the same command again on the same `$RUN` finishes the job.
- **Split:** each box names its own disjoint units.
- **Merge:** pull every box's run folder, copy the units into one folder with `cp -Rn`, which works because
  their paths are relative to `$RUN`, then run the merge step there.

Every process pool sizes itself from `DOPPLERTRACK_JOBS` (`--jobs`), defaulting to the box's physical cores.

All three run at once, on six boxes ([`fleet_launch.sh`](fleet_launch.sh)):
- job 1 on four boxes, one per arm (time, frequency) and tier;
- jobs 2 and 3 under each whitening, one box per whitening ([`hmm_box.sh`](hmm_box.sh)). Each box derives θ on
  synthetic data, picks the pair, and only then tracks the real recordings at that pair.

So whichever whitening job 1 adopts, its tracker result already exists, and the records report both settings
side by side. [`fleet_merge.py`](fleet_merge.py) `JOB ...` collects the pulled job folders into one new run
folder, runs every merge step and writes `side_by_side.txt`.

## 1. Whitening across frequency (`whiten_frequency.py`)

decision: whether the across-frequency background (the warp record's lead, PLAN item 8) replaces the per-bin running median as the package's whitening (PLAN 4, step 1 `spectrogram`).

The criterion is in the script's docstring and was fixed before anything ran.

| Step | Units | Command |
|---|---|---|
| build | one per variant spectrogram (13) | `whiten_frequency.py "$RUN" build [SPECTROGRAM ...]` |
| Tier 2 | one per (arm, case): 2 × 5 | `whiten_frequency.py "$RUN" t2 time\|frequency [CASE ...]` |
| Tier 1 | one per arm: 2 | `whiten_frequency.py "$RUN" t1 time\|frequency` |
| merge | — | `whiten_frequency.py "$RUN" merge` |

Inputs:
- The five seed cases, passed with `--case oyster-bay --case eagle-cam-clip-18000s --case oyster-bay-hp150-aac32k
  --case oyster-bay-moved-north150 --case oyster-bay-moved-wsw150`.
- The development spans' spectrograms and traces, from `bench/tier1.json`. All of them are under `derived/`.
- The variant spectrograms in `derived/whiten_frequency/`. They are already built locally and are seeded with
  `derived/`, so the build step is a no-op on the box. If the seed predates them, build writes them on the
  box: it needs the audio in `raw/audio/youtube/` and `derived/`.
- Cache: `--cache terrarium`. CPA tables rebuild on the box.

Split: put each arm on its own box (`t2 time` with `t1 time`, and the same for `frequency`). For a finer split,
name the Tier 2 cases. A Tier 1 arm that stops part-way restarts in a fresh folder, and the partial one is kept
as `<arm>-t1_stopped`.

## 2. The tracker's noise-image θ (`hmm_knobs.py`)

decision: the `HMMParams` defaults θ_cont and θ_birth for Phase 2 item 3, and whether hysteresis in states gets below the noise floor (about 8 dB) that round 1 hit.

| Step | Units | Command |
|---|---|---|
| pairs | one per θ_cont in 3..9 dB (7) | `hmm_knobs.py "$RUN" pairs WHITEN [THETA_CONT ...]` |
| pick | — | `hmm_knobs.py "$RUN" pick WHITEN` |

Inputs: none. The noise and the weak passes are synthetic, with fixed seeds.

Each unit is a bisection whose steps run one after another. Each step uses 12 noise windows in parallel, so a
single process can't use more than 12 workers. To fill a box, run several θ_cont in parallel:

```sh
for tc in 3 4 5 6 7 8 9; do DOPPLERTRACK_JOBS=12 uv run python tools/experiments/2026-11-04/hmm_knobs.py "$RUN" pairs WHITEN $tc & done; wait
```

On a box with fewer cores, split the θ_cont across boxes instead. The pick is cheap and runs after the merge.
Its result, `chosen.json`, sets the `HMMParams` defaults, which makes `test_noise_and_a_short_tone_make_no_track`
pass.

## 3. The tracker on Livermore and the development events (`hmm_livermore.py`)

decision: Phase 2 item 3, whether `hmmtrack` replaces `ridge()` as the fitting path's tracker, which unblocks item 4's `fit_track` re-run. If it is not met, item 3's next step is the tracker's objective, not another configuration.

| Step | Units | Command |
|---|---|---|
| references | one file | `hmm_livermore.py "$RUN" references` |
| livermore | one per pass (40: the 29 primary and the 11 flagged) | `hmm_livermore.py "$RUN" livermore WHITEN TC TB [PASS ...]` |
| dev | one per event (6) | `hmm_livermore.py "$RUN" dev WHITEN TC TB [EVENT ...]` |
| merge | — | `hmm_livermore.py "$RUN" merge WHITEN TC TB` |

The references must exist before any dev unit runs, and before the dev units are split. Run that step once,
then copy `dev_references.json` to every dev box.

Inputs:
- `derived/livermore/`, the unpacked corpus.
- `runs/2026-11-04-livermore-audit/`: its `passes.csv` and `sites.json`. Pass it with `--input-run runs/2026-11-04-livermore-audit`:
  `runs launch` sends a named run folder up from this machine.
- `raw/audio/livermore/zenodo-23424278/final_results_40_cases.csv`.
- Cache: `--cache terrarium`, for the development events' terrain.
- `raw/audio/youtube/oyster_bay.webm` and `raw/audio/youtube/swfl_2024-12-28.webm`.
- `derived/oyster_bay/traces_ny.npz` and `derived/swfl/traces_swfl.npz`.

Split: by pass, for example 15 and 14 passes on two boxes, with the dev events on either of them.

## 4. Item 3 round 3, the likelihood tracker (`ll_box.sh`: `ll_roc.py`, then `ll_livermore.py`)

decision: whether item 3's tracker becomes the likelihood tracker (`lltrack`), or stays `ridge()` with `hmmtrack`
retired.

| Step | Units | Command |
|---|---|---|
| constants | one file, from the development events | `ll_roc.py "$RUN" constants` |
| roc | one per (a, β, noise window or weak-pass case): 4 × 11 × 18 | `ll_roc.py "$RUN" roc [A ...]` |
| pick | — | `ll_roc.py "$RUN" pick` |
| livermore, dev | one per pass (40) and per event (6) | `ll_livermore.py "$RUN" livermore\|dev [PASS or EVENT ...]` |
| merge | — | `ll_livermore.py "$RUN" merge` |

Inputs: the same as job 3. The box runs the steps in order, so the knobs are picked on synthetic data before any
Livermore pass is read.

## 5. Item 5 round 2, the window (`window_roc.py`)

decision: whether the package's window and hop change from the 2.048 s Hann window at a 0.25 s hop.

| Step | Units | Command |
|---|---|---|
| roc | one candidate per box (`--shards 6`); per candidate, the noise unit and 27 passes | `window_roc.py "$RUN" roc [CANDIDATE ...]` |
| gate | — | `window_roc.py "$RUN" gate`, over the shards' `window_roc/` collected into one folder (`copy_new.py`) |

Inputs: none; the noise and the passes are synthetic. The real-data stage runs on copies of the cases, never by
editing the committed fits.

## 6. PLAN item 2's provisional bound: the measured frame covariance (`cov_measure.py`)

decision: which slant-range bound PLAN items 2 and 4 quote, and whether "provisional" comes off.

| Step | Units | Command |
|---|---|---|
| measure | one geometry × amplitude per box (`--shards 9`), three seeds each | `cov_measure.py "$RUN" measure [CELL ...]` |
| bound | — | `cov_measure.py "$RUN" bound`, over the collected units, with job 3's Livermore inputs |

## SDE-C handoff (2026-11-04, end of day)

The branch is `claude/sde-c-warp`; everything below is committed in its tip. The records are in `docs/experiments/`.
Boxes are launched with `tools/aws/runs launch` and pulled with `tools/aws/runs pull JOB`. Collecting means copying
the units with `python3 tools/experiments/2026-11-04/copy_new.py SRC_RUN DST_RUN <dir>`, never `cp -n`.

**Item 6, the detector** ([record so far](../../../docs/experiments/2026-11-04-detector-threshold.md), proposal
`docs/proposals/2026-11-04-detector-threshold.md`):

1. **Interrupted, not running:** the S₂ retune on 2026-11-04-detector-roc-s2-s7of9, -s8of9 and -s9of9 (settings
   S2B0, S2B1, S2B2, one per box). All three were spot-interrupted after 208–224 min, about $3 in all.
   - Only s7 saved units (5, pulled). s8 and s9 never finished their noise unit.
   - The cause is that the noise unit calls `tracks.rescore_null` serially over about 200 candidates, one full
     `fit_event` on a reversed window each.
   - **Before relaunching:** run those fits in a process pool (`DOPPLERTRACK_JOBS`), as `detect_events` does with
     its windows. Then launch `--shards 9 --only-shard 7 --only-shard 8 --only-shard 9` on 4xlarge, or larger
     boxes, so the noise unit fits a spot lifetime.

   When they're done:
   - pull all three;
   - copy their `detector_roc/` into a new run folder beside the six finished settings (S₀: detector-roc-s{1,2,3}of6;
     S₁: detector-roc-s1-s{4,5,6}of6), or into 2026-11-04-detector-roc-collect;
   - run `detector_roc.py RUN gate` on a box, with `--input-run runs/<that folder>`.

   The gate prints each setting's thresholds, the unit-spread prediction and detection by amplitude; it passes S₂
   only if every threshold is within ×1.5 of the prediction and detection is no lower than S₀ in the same band.
2. **Then Tier 1,** with `--shards 11` on 4xlarge boxes, for every setting past the gate plus S₀/B0, S₀/B1 and the
   300–900 Hz half. **Not written yet:** it needs a driver that
   - builds the 40–1000 Hz spectrograms for B1 and B2 on the box from the recipes (as `whiten_frequency.py build`
     does);
   - patches `bench.tier1`'s detect band and, for S₂, rescoring;
   - sets `DOPPLERTRACK_CACHE` to a scratch folder (linking `terrarium/`), so no detection reaches the shared cache
     before the decision.
3. **Judge on item 6's criterion:**
   - ≤ 1 false alarm per countable hour on the pooled background;
   - Tier 1's 2 matched windows kept;
   - every development event's window in its span's top 10;
   - the record states that S₀ can't meet it (the flyovers score 4.28 and 2.46 against a 1/h threshold near 6).

**Seattle gallery** (the owner's, private): `$DOPPLERTRACK_DATA/private/runs/2026-11-04-seattle-gallery/`, holding
`index.html`, `seattle_gallery.py` and `run.json`. Nothing of it is in git. Rebuild on the Mac only, from the repo
root, with the command in its `run.json`:
`DOPPLERTRACK_JOBS=2 uv run --frozen python <that folder>/seattle_gallery.py <that folder> <raw session>
<private rec.npz> <private traces> <site.json>`.
After a rebuild, rerun the privacy check: no ICAO, registration or site coordinate in the page text.

**Half-built:** item 6's Tier 1 driver (above). The frame-covariance and window records are done.

**Next step:** parallelise `rescore_null`, relaunch S₂, then finish item 6 (gate S₂, Tier 1, the record's outcome), then propose the next drawing-board step on
the detector's statistic if S₂ also fails.

## SDE-B

# SDE-B's benchmark jobs for the fleet (2026-11-04)

What the benchmark runner needs from a cloud box, and the jobs to move there, for SDE-E's `runs` wrapper to be
checked against. Measured times only; the times are from the shared Mac under load unless marked.

## How a job runs on a box

- **Pinned code.** Every job runs from a clean commit. `run.json` records `code` (package version, commit, dirty
  flag) as on the Mac, and the wrapper adds the box's type, zone and spot status beside it. A dirty tree runs, but
  never resumes or merges.
- **Workers.** `DOPPLERTRACK_JOBS` sets the processes per case (detect, the CPA build, scoring). With `--parallel N`
  on one box, each case gets `DOPPLERTRACK_JOBS` if set, else the performance cores divided by N.
- **Splitting across boxes.**
  - `bench run --shard I/N` runs every N-th case from the I-th (sorted case ids), into its own run folder.
  - `bench tier1 --shard I/N` writes the blind records of every N-th unit (span ids, then known-point cases) and
    doesn't compare.
  - `bench merge OUT SRC...` copies the finished cases or blind records into one run folder. It refuses sources
    from different commits, profiles, tiers or overrides, a dirty tree, and a case two sources finished with
    different records.
  - `bench tier1 --run-dir OUT --resume` then compares, which needs every unit's blind record and is quick.
- **Stopping and resuming.**
  - Each case writes `entry.json` when it finishes, and `results.json` is rewritten after every case with
    `complete` and `missing`.
  - A spot interruption loses only the cases still running. `bench run --run-dir R --resume` keeps those with
    an entry and runs the rest; `tier1 --resume` keeps every blind record that matches its hash.
  - A case whose `run-case` process died has no entry, so it runs again; `results.json` records why it died
    (`crashed`).
- **Blind order** is as on the Mac: each `result.json` and its hash are written before labels are read. Labels
  are in the repo (`bench/cases.json`, `bench/labels/`), so a box has them from the commit.
- **Logs.** The case's record and `run.log` hold its own messages. The pipeline's progress lines go to stdout:
  with `--parallel`, each case's `process.log` has them; in a serial run, the job's stdout does.

## Inputs

`uv run python -m bench inputs [--profile P] [case ...]` and `bench inputs --tier1` print, as JSON, every file a
job reads, under three keys: `data` (paths under `$DOPPLERTRACK_DATA`, with SHA-256), `repo` (files the commit
already has) and `cache` (paths under `$DOPPLERTRACK_CACHE`). Each entry lists the cases or spans that read it.

- **Data.** A run reads spectrograms and trace files from `derived/`. Raw audio is listed only as the source of
  the derived files, which `bench build` remakes from it; a box needs `raw/` only to rebuild.
- **CPA tables** (`cpa/bench/*.npz`) are named per case grid, flight data and DEM setting. A box without one
  builds it, which is the long part of a cold case, so copying one in skips that. A table built from other inputs
  is rebuilt, never reused. Two shards that share a table must not build it at once into one shared cache: give
  each box its own cache, or copy the table in first.
- **Small caches.** `detections/` and `window_fits/` are content-keyed and small (248 KB and 1.2 MB today):
  copy them whole, and copy back what a run adds. `terrarium/` (291 MB) holds the terrain tiles; a box without
  them downloads them, which needs the network.

Sizes today:

| Job inputs | Derived files read | Raw sources (rebuild only) | CPA tables |
|---|---|---|---|
| locate, 10 cases | 0.52 GB | 0.90 GB | 5 of 8 absent (one never built); present ones 0.19–1.15 GB |
| saved-fit, 5 cases | 0.24 GB | 0.81 GB | all 4 present, 0.19–0.87 GB |
| Tier 1, development | 1.15 GB | 0.81 GB | none (the known point searches one grid point) |

The absent locate tables are `oyster-bay_200m_dem-locate`, `oyster-bay-sources-removed_200m_dem`,
`eagle-cam-midnight_200m_dem` and `xenocanto-essex-2025-04-20_200m_dem`. `oyster-bay-traces-end-early` ends before
its search, so it never builds its table.

## The jobs

1. **Tier 2 locate, silence filter off.**
   - Command: `bench run --profile locate --search-param pair_rule=both`, 10 cases, at the commit that lands
     locate.
   - Split: one shard per box, or a few cases per box.
   - Measured on the Mac, 4 workers under load, eagle-cam clip, before the run was stopped: the top2 search took
     41 s from a cached table. Four of comparable's ten searches had finished, at 62–170 s each, when the run
     stopped 507 s in.
   - Each comparable search reloads the case's CPA table (1.15 GB for the eagle cam), but a load took about 1 s;
     a search's time is its pairing and scoring, which scale with the workers.
   - decision: PLAN Phase 3 step A's done-when, and locate's pair rule (criteria in
     `docs/experiments/2026-11-04-locate.md`, written before the results). If every failure case ends in its reason
     code, step A is done; one that doesn't is a bug fixed first. If `comparable` finds more seed cases than `top2`
     and loses none, it becomes the default; otherwise `top2` stays. If neither finds a seed case from automatic
     events, the next work is event choice (Phase 2 item 7's joint hypotheses) before step B.
2. **Tier 2 locate, silence filter on.** The same with `--search-param silence_d_m=6000`. It reuses job 1's CPA
   tables, so run it after job 1 or with job 1's tables copied in.
   - decision: S4's silence default in locate. It stays off unless turning it on finds more seed cases, loses none
     and leaves the negatives unlocated; if it does all three, it turns on and S4's re-ranking penalty is dropped
     from step B.
3. **Tier 2 saved-fit**, the five development cases with saved fits.
   - Its run is the baseline for the v2-cut case bump; job 4 runs the bumped cases with the same command.
   - Measured: the four seed cases at `--parallel 4`, warm tables, took 368 s on the Mac
     (`docs/experiments/2026-11-04-tier1.md`).
   - decision: with job 4, whether the Phase 1 baselines stand (Phase 0 D1, coverage). See job 4.
4. **Tier 2 saved-fit after the case bump.** Every development case moves to its margin-padded cut (PM,
   2026-11-04), then `bench compare` against job 3. New flight data means new CPA tables, so these cases build
   theirs cold.
   - Measured cold builds at 10 jobs: Oyster Bay 26 s (saved uncompressed) and the eagle cam 43 s (saved
     compressed), from `docs/experiments/2026-11-04-parallel-cpa.md`.
   - decision: whether the Phase 1 baselines stand. If every seed case keeps its true-pair rank and its margin
     within 5 % of the legacy value, the legacy-cut baselines stand with a note; if any rank or margin moves, the baselines
     are restated from the margin-padded cut, and the shift is recorded as a Phase 0 finding (the legacy cuts broke
     the coverage rule D1 exists to catch).
5. **Tier 1, development set, cold** (a fresh box has no detection or window-fit cache).
   - Command: `bench tier1 --shard I/N` on N boxes, then `bench merge` and one `bench tier1 --resume`.
   - Measured on the Mac: 788 s cold and 108 s warm with default workers. Each span's detect took 122 s and
     161 s, and each raw-audio-windows known point 113–142 s (`docs/experiments/2026-11-04-tier1.md`).
   - The 788 s run predates the nine background spans. With them, a cold Tier 1 took about 50 minutes under load
     (`docs/experiments/2026-11-04-cache-keys.md`), so the background spans are the bulk of a cold run.
   - decision: where cold Tier 1 runs (PLAN 5.4's budget). If the sharded fleet run finishes cold in the warm
     budget's time, a cache-key change no longer costs a long wait and Tier 1 runs cold on the fleet by default; if
     not, the warm Mac run stays the default and cold runs are batched.

All five launch at once, one box per case or Tier 1 unit: `tools/experiments/2026-11-04/sde_b_cloud.sh launch`, then `... collect` pulls, merges the shards, compares (silence off against on; legacy against margin-padded cut) and renders the reports. Job 3 runs at the commit before the case bump, from a worktree, so it needs no wait.

## SDE-A

# SDE-A's jobs for the fleet (item 7 stages A and B, item 1's sweep)

The heavy drivers, as SDE-E's `tools/aws/runs launch` will run them.

### What every driver does

Every driver runs on `shards.py`:
- **One command.** It runs from the commit `runs` bundles. The run folder is the positional `RUN`, else `$RUN`
  (the box sets it), else a new one from `new_run.py`. run.json keeps new_run.py's fields, or the box's, and
  adds `driver` (script, parameters) and `invocations` (argv, shard, resume, merge).
- **Units.** Each search, case or sweep cell writes into `RUN/units/<id>/`. It is finished once `unit.json` is
  renamed into place, so a stopped unit reruns and a finished one never does.
- **`--shard K/N`.** Every N-th unit from the K-th, one shard per box.
- **`--resume DIR ...`.** Earlier run folders whose finished units are kept, not rerun.
- **`--merge`.** Runs nothing. It checks that every unit is finished, then writes the result. It refuses
  units whose parameters or commit differ, so the merged numbers are the ones a single run would give.
  - The pairs driver's ranking is written and hashed before any label is read, as before.
- **Workers.** These come from `$DOPPLERTRACK_JOBS` (`parallel.default_jobs`); no result depends on them.
- **`--inputs`.** Prints the case ids, the other data-root paths, the cache kinds and the CPA tables as JSON,
  for `runs launch --case/--input/--cache`.

### The jobs

| Job | Command (from the repo root) | Units | Box from here (first launch, 2026-11-04) |
|---|---|---|---|
| Stage B A1/A3 (`hypotheses-pairs`) | `event_pairs_z.py --hypotheses --detected $DOPPLERTRACK_DATA/runs/2026-11-04-bench-5314396-raw-audio-t2 --case eagle-cam-clip-18000s oyster-bay oyster-bay-moved-wsw150` | 30 searches | 8xlarge, 32 workers per search, one at a time: two to a 64 GB box ran out of memory; d4 + d3 needs over 128 GB (8 × 8xlarge, 16 per search: 45–51 % busy) |
| Stage A comparable score (`comparable-score`) | the same without `--hypotheses` | 30 searches | 8xlarge, 32 workers per search, one at a time (4 × 8xlarge, 16 per search) |
| Event pairs by raw score (SDE-B's `event_pairs.py`) | the same with `--score raw` | 30 searches | not launched |
| B1/B2 (`hypotheses-b1b2`) | `hypotheses_b1b2.py` | 3 cases | 4xlarge (3 × 8xlarge) |
| Item 1's timing sweep (`timing-sweep`) | `timing_sweep.py` | 45 `bench run` cells | 4xlarge (8 × 8xlarge: 22–37 % busy) |
| N = 250,000 null (`hypotheses-pairs-n250000`) | stage B's command with `--null-n 250000` | 30 searches | cancelled once A1 was decided (10 × 8xlarge, 32 per search: 45–51 % busy) |

Splitting a job across boxes can't bring it under its longest unit.

Each job's `decision:` line names the PLAN decision it informs and what each outcome changes. The jobs are listed
in the PM's order (2026-11-04); a job whose outcomes change no decision isn't launched.
- **Stage A comparable score** — decision: whether event choice is the Phase 3 blocker (item 7, stage A).
  - A1 and A3 met at today's code: ranking a recording's event pairs by Z is the event choice Phase 3 builds on.
  - Not met: event choice stays the blocker, and the next lever is stage B's joint hypotheses.
- **B1/B2** — decision: whether the score's input, the fit, is the blocker (item 7, stage B).
  - B1 still failing at today's code: the fit's bias, not event choice, is what Phase 3 waits on. The levers are
    item 2's turn model, item 8, or a track that stays on the pass (item 3).
  - B1 met: hypotheses replace the speed and distance gates.
- **Stage B A1/A3** — decision: whether stage B's hypotheses ship for event choice.
  - A1 met: Z with hypotheses picks the eagle cam's true pair, which counts for adopting them, though B1 alone still
    blocks that.
  - Not met: they don't ship for event choice.
  - Inside the null's noise: the N run below decides it.
- **Item 1's timing sweep** — decision: whether the (16 s, 4 s) emission setting still holds at today's code, after
  the changes since `51f59ce`.
  - Holds: it stays the development setting that a default change would cite.
  - Doesn't hold: item 1's setting reopens.
- **N = 250,000 null (stage B, `--null-n`)** — decision: whether A1 can be decided at all by the null's size.
  - It is read only if A1 is inside the null's noise and needs N ≤ 250,000, under the record's rule; otherwise it is
    a number nobody acts on, and it isn't read.
  - Decided: that is A1's result.
  - Still inside the noise: the record says the test can't decide, and a lower-variance scale estimate becomes the
    later method change.
- **Event pairs by raw score** — decision: none of its own. Stage A's earlier run already compared Z with the raw
  score, so it isn't launched.

**Inputs** (from each driver's `--inputs`):
- **Pairs jobs.** The three cases, plus each case's `detected.json` in
  `runs/2026-11-04-bench-5314396-raw-audio-t2/`. Cache kinds: `terrarium`. CPA tables:
  `cpa/bench/{eagle-cam,oyster-bay,ny-wsw150}_200m_dem.npz`.
- **B1/B2.** oyster-bay, oyster-bay-hp150-aac32k and eagle-cam-clip-18000s, plus the first two cases'
  `detected.json` from the same baseline run. The eagle cam's fits are committed (`docs/results/`). Cache kinds:
  `terrarium`. CPA tables: eagle-cam and oyster-bay.
- **Timing sweep.** The five seed cases, three positives and two moved boxes. Cache kinds: `detections`,
  `window_fits`, `terrarium`. CPA tables: all four of the seed cases'.

**Null draws.** These run inside the units above. Each comparable-score search draws each event's null, and each
B1/B2 case draws its events' nulls. Each draw is seeded from the event's fit, so a unit gives the same null on any
box. The pairs driver keeps each search's nulls in `null.json`, beside its record. N is `run_search`'s `null_n`,
1,000 by default; `--null-n` changes it. The follow-up runs at N = 250,000, the PM's cap.

### Launching, and after

[`launch_sde_a.sh`](launch_sde_a.sh) has every step as one command:
- `launch PINNED` starts five jobs at once, each sharded over its own boxes. Each box takes its shard from
  `$DOPPLERTRACK_SHARD_SPEC`.
  - Stage B's A1/A3 runs on 10 boxes, on demand.
  - Its null-N follow-up, N = 250,000, runs on 30 boxes, on demand, with 64 workers per search. It runs now and is
    read only if A1 needs it.
  - Stage A runs on 5 boxes, B1/B2 on 3, and the timing sweep on 15.
  - That is 63 .16xlarge boxes. `SHARDS_B`, `SHARDS_N`, `SHARDS_A`, `SHARDS_B12` and `SHARDS_SWEEP` change the
    counts.
  - A launch that fails, for example on a vCPU quota, is reported and the others go on.
- `merge KIND S1 S2 ...` merges a job's pulled shards into a new run folder, from a checkout at the job's commit
  (`PINNED=` for the two stage B jobs). A merge refuses units from another commit or other settings.
- `a1 MERGED_B [MERGED_N]` judges A1 with [`a1_noise.py`](a1_noise.py), and reads the N run only when the record's
  rule says to.

A spot interruption is `runs launch --resume JOB`. It continues the same run folder, and finished units are skipped.

### The pinned code

Stage B's A1/A3 must run the first run's hypotheses (`45d0bd8`), not the retune's. So that job launches from
`claude/sde-stageb-pairs-45d0bd8` (`6f0ce38`), as does its N follow-up:
- `45d0bd8`, plus the shard commit;
- `run_search`'s `null_n`, which defaults to 1,000, as before;
- the pairs driver's kept nulls and `--null-n`, and `a1_noise.py`;
- B1/B2's `event_hypotheses` call, kept as it was at `45d0bd8`.

The other jobs launch from `dev`.

## SDE-E

- **Box sizing per job, from `runs fleet --util`.** Each job's box is sized from its measured CPU use: a job under
  60 % over its run (after its first 5 minutes) moves to the next smaller size, or its driver is changed to use the
  cores (more units at once, or a wider `--shards`). `--history` gives today's jobs over their whole runs; `--watch 10`
  keeps an hour of snapshots in a run folder, which tells a bursty job from an over-provisioned one.
