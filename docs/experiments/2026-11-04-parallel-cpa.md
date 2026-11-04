# Parallel CPA build and scoring

## Question

PLAN Phase 1, item 1. Does building the CPA table in a process pool, with track samples pruned by tile,
give the same table as the serial code, byte for byte? Does any output of `detect` or `search` depend on
`--jobs`? How long do the Oyster Bay CPA build and the search's scoring take at 1 and 10 jobs?

## What changed

- **One knob.** `--jobs` on `detect`, `search`, `search-single` and `refine`. It defaults to
  `$DOPPLERTRACK_JOBS`, otherwise the performance-core count (`hw.perflevel0.physicalcpu`, 10 on this
  M4 Pro). Every pool is a spawn-context `ProcessPoolExecutor` whose workers start with
  `VECLIB_MAXIMUM_THREADS`, `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` and the like set to 1. numpy
  uses Accelerate here, which threadpoolctl can't control, so the variables are set in the environment
  the workers are spawned with. `ps -M` showed one thread per worker after a large matrix product,
  against three in the parent. No pool starts more workers than it has tasks.
- **CPA table.** Each segment is one task, handed out longest first and put back in segment order. The
  worker runs the existing loop over chunks of 20 000 corridor points. Each chunk is centred on its own
  mean before `|g|² + |p|² − 2 g·p` is evaluated, so which points share a chunk is part of the result's
  bits. A different pool unit, such as grid chunks across segments, would have changed the table.
- **Tile pruning.** Inside a chunk, points are split into 4 km tiles. Each tile is compared only with
  the samples within `max_range` + 1 m, horizontally, of its bounding box. A sample left out is beyond
  `max_range` from every point of the tile, so it can't be the nearest sample of a kept row (kept rows
  need r ≤ `max_range`). Every sample at a kept row's minimum distance is within `max_range` and so
  retained. The retained samples keep ascending index order and the block update is strict, so
  `argmin`'s first-index rule picks the same sample. Horizontal distance to the box is a lower bound
  on slant range.
- **Scoring.** `run_search`'s `locked_score` loop and `refine`'s fine-grid loop run in chunks of 250
  across the same kind of pool, in order. Each worker receives the two event windows and the segments
  the triples use once, through the pool initializer.
- **Funnel and stage timings.** `run_search` returns them in `res.attrs`, and `search` logs them.

### A rewrite that was rejected

A KD-tree nearest-sample query per segment was 2.6× faster than the serial code on a 1-in-30 slice
of Oyster Bay's segments, but it was not equivalent. Resampled tracks contain samples at exactly
equal distances from a grid point, and the table is defined by `argmin`'s first-index choice among
them. The KD-tree chose differently: 1,263 rows moved by up to 3 samples and 1,390 rows vanished.

## Setup

Development data only: Oyster Bay (`derived/oyster_bay/`, box 40.4–41.3, −74.4 to −72.6) and the eagle
cam (`derived/swfl/`, box 26.1–27.3, −82.5 to −81.2), both at 200 m spacing with the DEM, a 12 km range
and the default speed of sound. The saved-fit searches use `docs/results/oyster_bay_ev1.json` and
`ev2.json` with `--harmonics 2 1`, and for the eagle cam `runs/2026-11-03-issue-1/swfl/ev1_docs.json`
and `ev2_docs.json` with default harmonics. Both revisions get the same arguments.

The old revision is `5c093cd`, the last commit before this change, exported with
`git archive 5c093cd src/dopplertrack | tar -x -C <run>/old_src --strip-components=1`. The harness and
the old-revision searches put `<run>/old_src` first on `sys.path`, ahead of the installed package.
Every build's JSON records `pkg.__file__`: `<run>/old_src/dopplertrack/__init__.py` for the old builds,
and the worktree's `src/dopplertrack/__init__.py` for the new ones. A wrong import would otherwise make
the two trivially identical.

Script: [`tools/experiments/2026-11-04/cpa_parallel.py`](../../tools/experiments/2026-11-04/cpa_parallel.py).
`build` times `cached_cpa_table` into a fresh cache path, as `search --cpa-cache` does on a cold cache,
with CPU time from `os.times()` including reaped pool workers. `compare` checks column names and order,
dtypes, row order and values exactly. The run folder's `steps.sh` holds every command.

The machine is shared with other sessions. Each step's log records the load average before and after it.

## Results

**Equivalence: every output is identical.**
- CPA tables, compared exactly (column names and order, dtypes, row order, values, fingerprint):
  - Oyster Bay, old against new: identical at 1 worker, at 10 workers, and at 10 workers saved
    uncompressed (86,166,301 rows from 379,758 points and 3,068 segments).
  - Eagle cam, old against new at 10 workers: identical (35,861,816 rows from 432,196 points and 1,233 segments).
- Saved-fit search CSVs:
  - Oyster Bay: one SHA-256, `506a129b…`, for the old code, the new code at 1 and 10 jobs reading the
    cached table, and the new code at 1 and 10 jobs building a fresh one.
  - Eagle cam: old against new at 10 jobs, `0116874b…` for both.
- `detect` on Oyster Bay (`--band 60 300 --top 10`): 1 and 10 jobs give `0e444812…`. That is also the
  hash of the [Phase 1 preparation regression](2026-11-03-phase1-prep-regression.md)'s output, made
  with 14 workers before this change.
- The jobs=1 runs used `4e27d77` and the jobs=10 runs `e576c2a`, its merge with dev (`3f37c94`).
  Identical outputs across that merge, so no run was repeated.

**Funnel, Oyster Bay saved fits:** 86,166,301 CPA rows; 16,350,399 and 16,357,469 within event 1's and
event 2's speed and distance gates; 197,177 triples after the time join; 40,889 after the silence filter,
all scored. Eagle cam: 35,861,816; 6,912,926 and 11,186,276; 84,441; 50,682.

**Timings.** Wall and CPU seconds; CPU includes pool workers. The 10-job steps started once no other
process had used over half a core for 15 s (`quiet.log`). The single-core steps ran while other
sessions' jobs held the 1-min load average at 5–19 (`single.log`), so they overstate a quiet machine.

| Step | Old (`5c093cd`) | New, 1 job | New, 10 jobs |
|---|---|---|---|
| Oyster Bay CPA build, cold cache, saved compressed | 405 s / 396 s | 194 s | 96.4 s / 220 s |
| Oyster Bay CPA build, cold cache, saved uncompressed (as committed) | – | – | **26.3 s / 151 s** |
| Eagle cam CPA build, cold cache, saved compressed | 134 s / 137 s | – | 43.4 s / 89.6 s |
| Oyster Bay search, scoring 40,889 triples | – | 246 s / 243 s | 46.7 s / 343 s |
| Oyster Bay search from a cached table, whole command | 265 s | 267 s | 64 s |
| Eagle cam search, scoring 50,682 triples | – | – | 36.4 s / 232 s |
| Oyster Bay `detect` | – | 231 s | 94 s |

- **Why the compressed save had to go.** Built at 10 jobs, the Oyster Bay table took 24.7 s, and
  `np.savez_compressed` then took 68.9 s on one core (874 MB). `np.savez` writes the same arrays in
  1.5 s (2.76 GB) (`cpa_split.json`, from
  [`cpa_split.py`](../../tools/experiments/2026-11-04/cpa_split.py)). `save_cpa_table` now writes
  uncompressed, and `load_cpa_table` reads both kinds, so the cold build meets PLAN's one-minute
  acceptance at 26.3 s. A case-day's table is now about 3 GB on disk, not 1 GB.
- **Follow-up for the next `CPA_CACHE_VERSION` bump:** drop `t_heard` from the file and recompute it on
  load as `t_emit + d / c` with the same float64 expression. That cuts a third of the size without
  changing a bit.
- At one job the new build took 194 s against the old code's 405 s, both under load; the tile pruning
  accounts for that.
- At 10 jobs the CPA build used 151 s of CPU against 194 s at one job, and took 24.7 s without the
  save rather than a tenth of 151 s. Pool start-up and moving 2.4 GB of rows to the parent are the
  likely cause; this wasn't measured.
- Scoring at 10 jobs used 343 s of CPU against 243 s at one: ten single-threaded workers on this
  chip's performance cores each run slower than one alone does. Wall time still fell 5.3×.

**Outcome: adopted.** The parallel build is bit-identical to the serial one, and nothing the CLI
writes depends on `--jobs`. The Oyster Bay table builds from a cold cache in 26 s. With a cached table,
a two-event search on Oyster Bay takes about a minute, against 4.5 min before.

Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-04-parallel-cpa/` (`run.json`, `steps.sh`, `single.log`,
`quiet.log`, `cmp.log`, one log per step, `tables/*.json`, the compare JSONs, `cpa_split.json`, the
CSVs and detect JSONs; the tables themselves are regenerable and can be deleted).
