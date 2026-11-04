# Joining flight data across UTC midnight (2026-11-04)

<!-- index
question: Can flight data be joined across UTC midnight without changing one-day cases?
outcome: Yes: ESID 375 joins 5 of its 7 midnight seams and 937 its one; one-day cases are unchanged
-->

## Question

ESID 375 and 937 record for about 25 h from 2024-04-07 into 2024-04-08, and ESID 740 and 710 cross midnight by
59 s and 20 s. adsb.lol archives one UTC day per file, so a flight in the air at midnight becomes two traces. Can
the two days be joined so that such a flight is one trace again, without changing anything for a one-day case?

## Setup

- **What the data shows.** Each day's cut ends exactly at midnight: 2024-04-07's last point is at −0.2 s and
  2024-04-08's first at +0.01 s, and no point is in both. A flight crossing midnight leaves a seam of a few
  seconds to many minutes between its two traces. Unjoined, each half is its own segment, and the CPA table only
  accepts a CPA that lies inside a segment, so a pass whose closest approach falls in the seam loses its CPA.
- **The join.** `adsb.join_days(paths)` returns traces and metadata. Given one file, it is exactly
  `load_traces` and `load_trace_metadata`. Given consecutive days, it joins a later day's trace of an aircraft to
  the earlier day's when the seam passes all four limits below, clears readsb's new-leg bit on the later file's
  first point, and leaves every other pair of traces as they are. Duplicate times keep the first point. A legacy
  day's part gets alt_source "unknown" and flags 0, which is what loading that day alone gives. The metadata
  lists every day's own metadata, the intersection of their coverage envelopes when all are known, and every seam
  with its gap, jump, altitude change and ground speed, and why it was or wasn't joined.
- **The cuts.** The 2024-04-07 Eclipse cuts were legacy files without metadata. They were cut again from the local
  tar with `extract_boxes.py`, which now writes extraction metadata, as new `esid<n>_margin12_v2.npz` files beside
  the old ones, to the same envelopes as the 2024-04-08 cuts. The legacy ESID 375 cut had 266 prop traces, the new
  one 267; the other three sites match. The four Eclipse cases now name both days' files.
- **Callers.** `search`, `refine` and `search-single` take one or more `--traces` files. The benchmark runner takes
  a case's `flight_data.traces` as one path or a list of days, checks every day's box against the search range,
  and reports the seams in the record's data limitations. a16b700's CLI takes one file, so the runner refuses a
  multi-day case at that revision.

**Knobs**, set before any audio was looked at:

| Knob | Value | Why |
|---|---|---|
| Longest seam joined | 90 s | the segmenter's geometry bound |
| Horizontal jump allowed | 1.5 × mean ground speed × gap + 500 m | room for a turn and for position noise |
| Altitude change allowed | 8 m/s × gap + 100 m | a propeller aircraft climbs at 2.5–7.5 m/s: 220 m at a 15 s seam, 820 m at 90 s |
| Ground speed at the seam | required | without it the jump can't be judged, so the seam stays split |

## Results

**Tier 0** (`tests/test_join_days.py`, 0.1 s of test time):

- (a) A straight pass with its CPA 20 s after midnight, cut at midnight with a 15 s seam and the new-leg bit on
  the later file's first point. Unjoined, the grid points whose CPA falls in the seam get no CPA row; joined, they
  do, with emission CPA within 0.5 s and slant range within 5 m of the unsplit trace's. The joined trace is one
  segment and its times strictly increase.
- (b) The same pass with a 300 s seam, or with the later day displaced 5 km, stays two traces, and the seam
  record says why.
- (c) One day through `join_days` gives the same CPA fingerprint as `load_traces`. On the tiny Oyster Bay smoke
  grid, a case with its traces as a path and as a one-element list gives the same events, candidates, refinement,
  funnel and triples (`runs/2026-11-04-trace-list-regression/`).
- A legacy day joins to a day with metadata, with its part's provenance marked unknown.

**(d) The real seams** (`tools/experiments/2026-11-04/trace_join_check.py`, structural only: no audio was read and
nothing was searched; seams where both sides lie within 10 min of midnight):

| Site | Seams | Joined | Kept apart |
|---|---|---|---|
| ESID 375 | 7 | ab8354 (5.1 s), a081f4 (8.9 s), a4f9e3 (12.6 s), ad05c7 (17.5 s), a86aac (19.6 s) | a5f6ef (90.1 s, just over the bound), aa370d (668.7 s) |
| ESID 937 | 1 | a3b943 (23.1 s) | – |
| ESID 740 | 1 | aabc11 (19.9 s) | – |
| ESID 710 | 9 | a33e08 (2.2 s), aa5b6c (19.3 s), a86aac (19.6 s), aabc11 (19.9 s), a7f352 (41.1 s), a8b112 (46.6 s), aa0909 (57.9 s) | ab3252 (no usable position on one side), ac3696 (230 s) |

Every joined trace's times strictly increase. No airborne segment spanned midnight before the join; afterwards each
joined flight gives one. Each join stays visible in the metadata's seams list, so a result near midnight can be
traced to it. Two of the joined flights fly at 230 and 273 m/s: they are unknown-type aircraft that the prop
filter keeps, and their seams pass the limits on their own speed.

**A correction to the proposal.** It said four of the eight midnight seams carry readsb's new-leg bit. In this
code the new-leg bit is value 2 (`flags & 2`), and the flags read there were 4, 7, 1 and 0: only aa370d's 7
includes it, and that seam is split anyway for its 669 s gap. Clearing the bit at a joined seam is kept, since a
file start is not a new leg, but no real seam above needed it.

## Outcome

Flight data now joins across midnight, with the one-day path unchanged. ESID 375 and 937 are no longer blocked by
the runner, only by being evaluation cases, which run at milestones.

## Files

- Code: `src/dopplertrack/adsb.py` (`join_days`), `src/dopplertrack/cli.py` (`--traces` one or more),
  `bench/runner.py` and `bench/cases.py` (multi-day cases, folder-output recipes), `tests/test_join_days.py`,
  `tests/test_bench.py`.
- Script: `tools/experiments/2026-11-04/trace_join_check.py`.
- Runs: `runs/2026-11-04-recut-eclipse-2024-04-07/` (the new cuts), `runs/2026-11-04-trace-join-check/` (the seams,
  `seams.json`), `runs/2026-11-04-trace-list-regression/` (criterion c).
