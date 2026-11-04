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

The jobs depend on each other in order: job 1 decides `WHITEN`, job 2 decides `THETA_CONT` and `THETA_BIRTH`,
and job 3 uses both.

## 1. Whitening across frequency (`whiten_frequency.py`)

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

| Step | Units | Command |
|---|---|---|
| references | one file | `hmm_livermore.py "$RUN" references` |
| livermore | one per primary pass (29) | `hmm_livermore.py "$RUN" livermore WHITEN TC TB [PASS ...]` |
| dev | one per event (6) | `hmm_livermore.py "$RUN" dev WHITEN TC TB [EVENT ...]` |
| merge | — | `hmm_livermore.py "$RUN" merge WHITEN TC TB` |

The references must exist before any dev unit runs, and before the dev units are split. Run that step once,
then copy `dev_references.json` to every dev box.

Inputs:
- `derived/livermore/`, the unpacked corpus.
- `runs/2026-11-04-livermore-audit/`: its `passes.csv` and `sites.json`. `--input` reads from the bucket's
  `data/`, and `runs/` isn't seeded there, so this folder has to be seeded once before the job can run.
- `raw/audio/youtube/oyster_bay.webm` and `raw/audio/youtube/swfl_2024-12-28.webm`.
- `derived/oyster_bay/traces_ny.npz` and `derived/swfl/traces_swfl.npz`.

Split: by pass, for example 15 and 14 passes on two boxes, with the dev events on either of them.

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
2. **Tier 2 locate, silence filter on.** The same with `--search-param silence_d_m=6000`. It reuses job 1's CPA
   tables, so run it after job 1 or with job 1's tables copied in.
3. **Tier 2 saved-fit**, the five development cases with saved fits.
   - Its run is the baseline for the v2-cut case bump; job 4 runs the bumped cases with the same command.
   - Measured: the four seed cases at `--parallel 4`, warm tables, took 368 s on the Mac
     (`docs/experiments/2026-11-04-tier1.md`).
4. **Tier 2 saved-fit after the case bump.** Every development case moves to its margin-padded cut (PM,
   2026-11-04), then `bench compare` against job 3. New flight data means new CPA tables, so these cases build
   theirs cold.
   - Measured cold builds at 10 jobs: Oyster Bay 26 s (saved uncompressed) and the eagle cam 43 s (saved
     compressed), from `docs/experiments/2026-11-04-parallel-cpa.md`.
5. **Tier 1, development set, cold** (a fresh box has no detection or window-fit cache).
   - Command: `bench tier1 --shard I/N` on N boxes, then `bench merge` and one `bench tier1 --resume`.
   - Measured on the Mac: 788 s cold and 108 s warm with default workers. Each span's detect took 122 s and
     161 s, and each raw-audio-windows known point 113–142 s (`docs/experiments/2026-11-04-tier1.md`).
   - The 788 s run predates the nine background spans. With them, a cold Tier 1 took about 50 minutes under load
     (`docs/experiments/2026-11-04-cache-keys.md`), so the background spans are the bulk of a cold run.

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

| Job | Command (from the repo root) | Units |
|---|---|---|
| Stage B A1/A3 (`hypotheses-pairs`) | `event_pairs_z.py --hypotheses --detected $DOPPLERTRACK_DATA/runs/2026-11-04-bench-5314396-raw-audio-t2 --case eagle-cam-clip-18000s oyster-bay oyster-bay-moved-wsw150` | 30 searches |
| Stage A comparable score (`comparable-score`) | the same without `--hypotheses` | 30 searches |
| Event pairs by raw score (SDE-B's `event_pairs.py`) | the same with `--score raw` | 30 searches |
| B1/B2 (`hypotheses-b1b2`) | `hypotheses_b1b2.py` | 3 cases |
| Item 1's timing sweep (`timing-sweep`) | `timing_sweep.py` | 45 `bench run` cells |

Splitting a job across boxes can't bring it under its longest unit.

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
box. N is fixed at `pipeline.NULL_N` = 1,000. A larger-N job would first need N as a search parameter. That only
happens if stage B's retune is spent on N, which hasn't happened.

### For SDE-E's wrapper

- **The baseline detections live in a run folder.** All the pairs and B1/B2 jobs read `detected.json` from
  `runs/2026-11-04-bench-5314396-raw-audio-t2/`. `seed` uploads only `raw/` and `derived/`, so `--input` needs
  that run's files in the bucket, or a job that remakes them first.
- **Merging shards.** Each `runs launch` makes its own `$RUN`, so a sharded job is N launches with `--shard k/N`.
  After `runs pull`, the merge is the same command on the Mac:
  `--merge RUN_1 --resume RUN_2 ... RUN_N`.
  - A spot interruption is resumed the same way: a new launch with `--resume` pointing at the interrupted
    folder, once it has been pulled.
- **The pinned code.** Stage B's A1/A3 must run the first run's hypotheses (`45d0bd8`), not the retune's. The
  drivers' shard support is newer, so that job launches from `claude/sde-stageb-pairs-45d0bd8` (`1702067`):
  `45d0bd8` with the shard commit cherry-picked, keeping B1/B2's `event_hypotheses` call as it was at
  `45d0bd8`. The other jobs launch from `dev`.
