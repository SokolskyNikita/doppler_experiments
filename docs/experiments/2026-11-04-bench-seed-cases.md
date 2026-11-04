# Benchmark seed cases (2026-11-04)

## Question

Does the new benchmark runner (PLAN Phase 1 items 2–3) reproduce PLAN section 2's saved-fit results through
the result record, and what do the four seed cases of section 5.1 give with today's pipeline?

## Setup

`bench/cases.json` defines the cases; `uv run python -m bench run` runs each one without its labels, writes
`result.json` and `result.json.sha256`, and only then reads the reference point and scores the record into
`results.json`. Every case uses the committed saved fits (the saved-fit profile), a 200 m grid with terrain,
the default gates (±6 s, ±35 % speed, 0.4–2.5× distance, 6 km silence filter, 12 km range) and a 50 m,
±600 m refinement of the top flight pair with no extra flyovers. Each case has its own CPA cache file under
`$DOPPLERTRACK_CACHE/cpa/bench/`; Oyster Bay's was seeded from the existing table and accepted by its content key.

| Case | Audio | Flight data | Expected |
|---|---|---|---|
| `oyster-bay` | Oyster Bay Opus track, 1 h | `traces_ny.npz`, README box | located |
| `eagle-cam-clip-18000s` | eagle cam samples from 18,000 s for 5,400 s, cut sample-exactly to WAV; fits detect ranks 5 and 13, shifted by −18,000 s | `traces_swfl.npz`, README box | located |
| `oyster-bay-hp150-aac32k` | Oyster Bay high-passed at 150 Hz, 32 kbit/s mono AAC (the source is already lossy) | as Oyster Bay | located or abstain |
| `oyster-bay-moved-north150` | Oyster Bay | the README box moved 150 km north, search box 41.75–42.65 / −74.38 to −72.62 | not located |
| `oyster-bay-moved-wsw150` | Oyster Bay | the README box moved 150 km on bearing 250, search box 39.93–40.83 / −76.06 to −74.26 | not located |

Oyster Bay and the eagle cam are development recordings: these numbers can guide work but are not evaluation.

**Start times.** Neither recording has an independent clock. Oyster Bay's start is recorded as unknown,
the UTC date only, ±43,200 s about 12:00 UTC. The eagle cam's is YouTube's `release_timestamp`, the live
broadcast's start, ±60 s, since how the archived VOD's first sample relates to it is undocumented. As a sanity
check only, the clock the development search derives from the matched flights puts the eagle cam's first sample
3 s before `release_timestamp`. That clock is kept as `reference_clock_utc`, never as the start time's source.

**Moved box traffic.** PLAN 5.1 asks for a moved box "over land with similar traffic". Prop passes on 2026-09-08
within 12 km / 6 km of the truth and of the truth moved 150 km (`tools/data/site_traffic.py`):

| Point | ≤12 km | ≤6 km |
|---|---|---|
| Oyster Bay truth | 158 | 53 |
| moved N | 46 | 26 |
| moved W | 86 | 29 |
| moved WSW (bearing 250) | 339 | 102 |
| moved SW | 243 | 174 |
| moved NW | 21 | 9 |
| moved NNE | 51 | 22 |

No 150 km move over land matches. A sparse negative is an easy test of abstention, so the seed negative is the
WSW box, with about twice the traffic (1,280 prop traces in its cut against 1,190 for the Oyster Bay box plus
margin); the north box (573) stays as a sparse-airspace negative on the growth list. PLAN 5.1's "similar
traffic" should read "at least as much traffic".

**Coverage.** Every trace file used predates Phase 0's extraction metadata, so the pipeline can only report
"envelope unknown". Each case declares the box its traces were cut to, and the runner checks that the search box
padded by the search range lies inside it: true for both moved boxes, false for Oyster Bay and the eagle cam,
whose traces were fetched for the box itself with no margin. Both are recorded in each record's
`data_limitations`.

## Results

Run `runs/2026-11-04-bench-4088419-t2/`, commit 4088419, 16 min 35 s in all. Every record passed its hash check.

| Case | True pair rank | Flight pairs | Margin | Top error | Refined error | Box centre error |
|---|---|---|---|---|---|---|
| Oyster Bay | 1 | 328 | 4.94 % | 122.9 m | 43.3 m | 3,614 m |
| eagle-cam clip | 1 | 607 | 2.54 % | 916.6 m | 876.5 m | 344 m |
| degraded Oyster Bay | 1 | 328 | 4.62 % | 122.9 m | 43.3 m | 3,614 m |
| moved north | – | 35 | 3.25 % | 147.6 km | 147.7 km | 147.2 km |
| moved WSW (seed negative) | – | 61 | 10.69 % | 181.6 km | 181.7 km | 148.6 km |

- **Oyster Bay reproduces PLAN section 2.** The top and refined coordinates are bit-identical to
  `docs/results/oyster_bay_search_best_per_pair.csv` and `oyster_bay_refined_50m.csv`. The scores are not: the top
  score is 27.1008 against the committed 27.0993, and 40,889 triples survive the silence filter against 40,885. The
  2026-11-03 cache check at 2bf61cc already scored 27.1036, so the drift predates the runner and follows the
  Phase 0 trajectory masks.
- **Funnel, Oyster Bay:** 86,166,301 CPA rows; 197,177 triples (691 flight pairs) after the speed, distance and
  time gates; 40,889 (328 pairs) after the silence filter. The true pair survives both. The per-gate counts are
  recorded as unavailable until `run_search` returns them.
- **The eagle-cam clip** matches the full 12 h recording: the same 50,682 triples, the true pair first of 607 by
  2.54 %, and the two-event refinement 877 m off, as in PLAN section 2. Whitening over the clip alone changed
  nothing that the scores show.
- **The box centre beats the search on the eagle cam**: the README box happens to be centred 344 m from the
  nest, closer than the top (917 m) and refined (877 m) answers. A case whose box is centred on the truth
  says little about location error; growth cases should place the truth away from the centre.
- **The degraded copy** still ranks the true pair first, with a margin of 4.62 %. Its fits come from the clean
  audio, so in the saved-fit profile it tests scoring on degraded audio, not fitting; the raw-audio profile is
  what tests the fits.
- **The north box gives a confident-looking wrong answer**: flights ac0565/a68103, 147.6 km from the truth, by a
  3.25 % margin, larger than the eagle cam's true positive. Margin alone does not separate right from wrong
  answers, which is what Phase 4's verdict has to do.
- **Stage times** (wall / CPU): the Oyster Bay search 248 s / 247 s, of which loading the cached CPA table is 5 s
  and the rest scoring; recounting the funnel 12 s; refinement 3.7 s. The eagle-cam search, including rebuilding
  its table, 329 s; the north box, including building its table, 112 s.
- The records say `git_dirty: true`: uncommitted edits landed during the run, and this version of the runner read
  the flag at the end. The code executed was 4088419. The runner now reads both once, before anything runs.

**The WSW seed negative** ran separately, in `runs/2026-11-04-bench-f5ccdfe-t2/` at f5ccdfe; its tree was dirty only
with this record's uncommitted text. 72,877,753 CPA rows; 35,281 triples (148 flight pairs) after the gates; 8,423
(61 pairs) after the silence filter. The top pair, ae64c1/aae29f, is 181.6 km from the truth (refined 181.7 km, box
centre 148.6 km), by a **10.7 % margin**: larger than either true positive's (Oyster Bay 4.9 %, the eagle cam 2.5 %).
The busier box gives the more confident wrong answer. Search 401 s wall / 388 s CPU, including building the CPA table;
7 min 4 s in all.

## Outcome

The runner reproduces the saved-fit Oyster Bay result through the result record, with ranks and locations exact
and scores within 0.01 %; the score drift comes from the Phase 0 trajectory masks and is not a regression. The
eagle-cam clip is a faithful 1.5 h stand-in for the 12 h recording. The moved-north negative returns a wrong
answer 148 km out with a 3.2 % margin, above the eagle cam's true positive at 2.5 %: direct evidence for PLAN S5
and for Phase 4's rule that margin alone can't carry a verdict. The WSW seed negative makes the point harder: 182 km out by a 10.7 % margin, twice
Oyster Bay's true positive. `results.json` marks the
verdict, region, detection, association and fit scores unavailable until the features that produce them exist.

Tier 0 after merging dev at 5c093cd: `tools/check.sh` green, pytest 93 passed and 3 skipped in 75 s (over the 60 s
target; the new tests take 0.3 s), 111 s in all.

## Files

- Code: `bench/` (`cases.json`, `cases.py`, `runner.py`, `__main__.py`), `src/dopplertrack/result.py`;
  tests `tests/test_result.py`, `tests/test_bench.py`.
- Runs: `runs/2026-11-04-bench-4088419-t2/` and `runs/2026-11-04-bench-f5ccdfe-t2/` (WSW) (`results.json`, one folder per case with `result.json`, its hash and
  `run.log`); `runs/2026-11-03-moved-box-traffic/` (pass counts); `runs/2026-11-04-cut-ny-wsw150/` (the WSW cut);
  `runs/2026-11-03-bench-build-derived/` (the clip and the degraded copy, rebuilt byte-identically).
