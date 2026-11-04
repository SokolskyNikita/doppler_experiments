# Benchmark baselines at upstream a16b700 (2026-11-04)

## Question

PLAN Phase 1 item 4: what do the four seed cases give at upstream a16b700, from saved fits and from raw audio,
and does the fork's current code (5314396) give the same?

## Setup

- **The revision.** `bench run --revision a16b700` exports the commit with `git archive` into
  `$DOPPLERTRACK_CACHE/revisions/a16b700/`, installs it with `uv sync --frozen` against a16b700's own `uv.lock`
  (Python 3.12.15, tree `b4c63ab1`, lock `eee06f23`), and drives its CLI as subprocesses: `spectrogram`,
  `detect`, `search` with its own CPA cache file per case, and `refine`. No a16b700 code runs in the runner's
  process. Before every case the export is hashed as a git tree and refused unless it matches the commit's.
- **Profiles.** saved-fit takes each case's committed fits and isolates search and physics. raw-audio runs
  `detect --band 60 300 --top 10` and searches its two highest-scoring events, earlier first, with one harmonic
  each; trying other pairs is Phase 3's job.
- **Cases.** oyster-bay, eagle-cam-clip-18000s, oyster-bay-moved-wsw150 and oyster-bay-hp150-aac32k, at the
  default gates. Their derived audio (the clip, the degraded copy) is data, so it is a16b700's input too, and
  a16b700's own spectrograms came out byte-identical to the cases' on every case.
- **Running.** Saved-fit ran with the four cases at once, each in its own process (`--parallel 4`), a16b700 and
  5314396 side by side; raw-audio one case at a time, since detect uses every core.

## Results

**Saved-fit: a16b700 and 5314396 are identical on every case.**

| Case | True pair rank | Flight pairs | Margin | Top error | Refined error | Top score |
|---|---|---|---|---|---|---|
| Oyster Bay | 1 | 328 | 4.94 % | 122.9 m | 43.3 m | 27.1008 |
| eagle-cam clip | 1 | 607 | 2.54 % | 916.6 m | 876.5 m | 10.2972 |
| WSW negative | – | 61 | 10.69 % | 181.6 km | 181.7 km | 23.2547 |
| degraded Oyster Bay | 1 | 328 | 4.62 % | 122.9 m | 43.3 m | 26.5801 |

Top scores agree to the fourth decimal and the scored triples match (40,889, 50,682, 8,423, 40,889). Phase 1
changed nothing on the saved-fit path. The one internal difference is WSW's CPA table: a16b700 builds 72,664,844
rows against 72,877,753 at 5314396, from Phase 0's trajectory segmenting, with the same 8,423 triples scored and the
same answer.

**Raw-audio: a16b700 and 5314396 are identical in rank, pairs, margin and error; neither locates a positive.**

| Case | Events detect picked (heard CPA s, f0 Hz) | True pair rank | Flight pairs | Margin | Top error |
|---|---|---|---|---|---|
| Oyster Bay | 2155.6 / 112.9 and 3068.4 / 140.1 | 10 | 448 | 5.9 % | 77.5 km |
| eagle-cam clip | 820.0 / 114.1 and 2247.5 / 108.1 | absent | 108 | 1.0 % | 54.3 km |
| WSW negative | as Oyster Bay | – | 232 / 231 | 13.2 % | 92.2 km |
| degraded Oyster Bay | 2155.7 / 112.8 and 3068.5 / 140.1 | 10 | 445 | 5.9 % | 77.5 km |

The two positives fail in different ways, which belong to different PLAN Phase 2 items:

- **Oyster Bay: the right events, a biased fit.** detect's top two are the README's two flyovers, but event 2
  fits at 140.1 Hz against the saved 132.4 Hz (+6 %), the E1 bias. The true pair survives the gates and the silence
  filter somewhere in the box but ranks only 10th; the winner, a26f86/a77707, is 77.5 km away. This is the
  timing-gate and fitting problem (items 1 and 4), not event choice. The box-wide survival flag passes here even
  though the opt-in test shows these fits fail the filters at the true location, which is why the scoreboard now
  also reports survival within 250 m of the reference.
- **Eagle cam: the wrong event.** detect's top two are full-stream 18,820 s (its rank 2) and 20,247 s (rank 5);
  the saved pair is ranks 5 and 13. With one flyover wrong, the true pair can't pass the gates. This is event
  choice (items 6 and 7).

WSW differs by one flight pair (232 against 231; 9,737 against 9,555 triples after the silence filter), the same
Phase 0 segmenting, with the same answer.

**Stage times** (wall / CPU per case, s): a16b700 saved-fit 803 / 771 (Oyster Bay), 490 / 451, 541 / 512, 801 / 766,
each including a16b700 building its own CPA table; 5314396 saved-fit 464 / 414, 304 / 264, 125 / 102, 469 / 415 from
cached tables, four cases at once in both. Raw-audio per case 136–179 s wall and 487–642 s CPU at either revision.

**An incident, fixed.** The first a16b700 raw-audio run scored only Oyster Bay. a16b700's detect starts spawn worker
processes, which inherit `-I` but not `-X pycache_prefix`, so they wrote `__pycache__` into the exported tree, and
the hash check refused the other three cases. The export now runs with `-I -B`, which multiprocessing passes on to
its workers; a test shows a spawn worker writes bytecode under `-I` alone and none under `-I -B`. The rerun
(`-t2-2`) is the one reported, and the export verified clean after it.

## Outcome

The two baselines exist, and `bench compare` sets them beside the current code: identical on both profiles. From
raw audio, a16b700 locates none of the seed positives, and neither does the fork yet. The two failures name the
first Phase 2 work: Oyster Bay's is the gate and the fit, the eagle cam's the choice of events.

## Files

- Code: `bench/revisions.py` (export, install, verification), `bench/runner.py` (`execute_case_at`, the profiles,
  `--parallel`), `tests/test_bench.py`.
- Runs: `runs/2026-11-04-bench-a16b700-saved-fit-t2/`, `-5314396-saved-fit-t2/`, `-a16b700-raw-audio-t2-2/` (the
  first attempt, `-a16b700-raw-audio-t2/`, is kept for the incident), `-5314396-raw-audio-t2/`; the driver and its
  logs in `runs/2026-11-04-bench-baselines-driver/`; the tiny-grid smoke tests in `-bench-revision-smoke/` and
  `-bench-overrides-smoke/`.
- To repeat: `uv run python -m bench run --revision a16b700 --profile saved-fit --parallel 4 <cases>`, then
  `uv run python -m bench compare <a16b700 run> <current run>`.
