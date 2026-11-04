# Cloud jobs from SDE (item 7 stages A and B, item 1's sweep)

The heavy drivers here, as SDE-E's `tools/aws/runs launch` will run them. Use this list to check the wrapper against.

## What every driver does

The shared part is [`tools/data/shards.py`](../../data/shards.py), tested in `tests/test_shards.py`.
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

## The jobs

Times are from the Mac runs named below. That Mac has 10 performance cores and its load average was 30–90
throughout, so the core-hours are upper bounds. Box-hours assume one .16xlarge (64 vCPU). Splitting a job across
boxes can't bring it under its longest unit.

| Job | Command (from the repo root) | Units | Measured on the Mac | Box-hours |
|---|---|---|---|---|
| Stage B A1/A3 (`hypotheses-pairs`) | `event_pairs_z.py --hypotheses --detected $DOPPLERTRACK_DATA/runs/2026-11-04-bench-5314396-raw-audio-t2 --case eagle-cam-clip-18000s oyster-bay oyster-bay-moved-wsw150` | 30 searches | 26 of 30 took 14,913 s at 4 workers each (16.6 core-h). The longest, eagle cam d1+d5, took 6,217 s | about 2, set by the longest search; one box, one shard |
| Stage A comparable score (`comparable-score`) | the same without `--hypotheses` | 30 searches | 3,469 s at 4 workers each (3.9 core-h); the longest took 268 s | under 0.2; one box |
| Event pairs by raw score (SDE-B's `event_pairs.py`) | the same with `--score raw` | 30 searches | below stage A (no nulls) | under 0.2 |
| B1/B2 (`hypotheses-b1b2`) | `hypotheses_b1b2.py` | 3 cases | 398 s at 4 workers (retune run) | under 0.1; not worth sharding |
| Item 1's timing sweep (`timing-sweep`) | `timing_sweep.py` | 45 `bench run` cells | 8,542 s at the default 10 workers (at most 23.7 core-h) | about 0.5 per box over 3 shards |

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

## For SDE-E's wrapper

- **The baseline detections live in a run folder.** All the pairs and B1/B2 jobs read `detected.json` from
  `runs/2026-11-04-bench-5314396-raw-audio-t2/`. `seed` uploads only `raw/` and `derived/`, so `--input` needs
  that run's files in the bucket, or a job that remakes them first.
- **Merging shards.** Each `runs launch` makes its own `$RUN`, so a sharded job is N launches with `--shard k/N`.
  After `runs pull`, the merge is the same command on the Mac:
  `--merge RUN_1 --resume RUN_2 ... RUN_N`.
  - A spot interruption is resumed the same way: a new launch with `--resume` pointing at the interrupted
    folder, once it has been pulled.
- **The pinned code.** Stage B's A1/A3 must run the first run's hypotheses (`45d0bd8`), not the retune's. The
  drivers' shard support is newer, so that job launches from a branch cut at `45d0bd8` with this commit
  cherry-picked onto it. The other jobs launch from the branch tip.
