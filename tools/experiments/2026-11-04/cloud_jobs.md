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
   - Each comparable search reloads the case's CPA table (1.15 GB for the eagle cam), so a box's disk speed counts.
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

Jobs 1, 2 and 5 are independent of each other. Job 4 waits for the case bump and job 3.
