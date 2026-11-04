# Timing convention

## Question

PLAN Phase 2, item 1 (E2). The search pairs two events by their fitted heard-CPA times, so every error
in a fitted distance or f0 moves the pairing gate ([timing-conventions](2026-11-03-timing-conventions.md)).
Does pairing on emission-CPA times, followed by a like-for-like steepest-fall check, let the true flight
pair through from `detect`'s events without admitting more candidates than today's ±6 s heard gate?

## Criterion, fixed before running

On each positive seed case (`oyster-bay`, `eagle-cam-clip-18000s`, `oyster-bay-hp150-aac32k`), with
`detect`'s events (the runner's raw-audio profile):
- the true pair survives: a triple with the true flights reaches scoring at a grid point within 250 m
  of the reference (the nearest point and its neighbours at 200 m spacing);
- the number of triples reaching scoring (after the emission gate, the silence filter and the
  steepest-fall check) is at most that case's count under today's ±6 s heard gate and silence filter.

Of the settings that meet both on every case, the one with the smallest count is adopted. If none
does, nothing is adopted. Survival anywhere in the box, and within `refine`'s half-width (600 m), are
reported beside it but decide nothing. Box-wide survival is true for every setting, including today's
heard gate on Oyster Bay's `detect` events, which fail at the true location.

The saved-fit profile is a regression check only.

**Amendment, 2026-11-04, before any sweep result was read.** On the eagle cam, item 1 is judged with its
committed fits, `detect`'s ranks 5 and 13, run through the saved-fit profile across the same 20 cells. On
the eagle-cam clip, the raw-audio profile's top-two rule picks a wrong flyover: full-stream ranks 2 and 5,
not 5 and 13 ([bench-baselines](2026-11-04-bench-baselines.md)). So the true pair can't reach scoring at any
gate. That is items 6 and 7's failure (event choice), outside the variable this item tests. The two Oyster
Bay cases are one recording, so without the eagle cam the decision would rest on one recording. Ranks 5 and
13 are `detect` output, so with them it rests on two true event pairs, as the development pass did. The
eagle cam's raw-audio cells are reported beside them, as out of this item's reach, with the wrong pick
named. The Oyster Bay cases are still judged at raw-audio.

**Clarification, 2026-11-04, before the deciding table was read.** "The smallest count" is the smallest
total of triples reaching scoring over the three judged cases. Each case's count is shown beside it.

## Design

All knobs are `run_search` keyword arguments and `search` flags. Their defaults reproduce the previous
results; the Oyster Bay saved-fit CSV is byte-identical.

| Knob | Values | Meaning |
|---|---|---|
| `time_convention` / `--convention` | `heard` (default), `emission` | pair the fits' `t_cpa` against the table's `t_heard`, or their `t_cpa_emit` against its `t_emit` |
| `tol_s` / `--tol` | 6 (default); grid G_e ∈ {8, 12, 16, 20} | pairing gate half-width, s |
| `sf_tol_s` / `--sf-tol` | off (default); grid T_sf ∈ {2, 3, 4, 6} | drop a triple whose modelled steepest-fall gap differs from the fits' by more than this, s |
| `sf_smooth_s` / `--sf-smooth` | 3, fixed | moving-average half-width before differentiating, s |
| `sf_window_s` / `--sf-window` | 60, fixed | search half-window around each CPA, s |
| `sf_flat_ratio` / `--sf-flat-ratio` | 1.03, fixed | a curve whose peak slope is under this multiple of its median slope over the window is unplaceable |
| `clock_anchor` / `--anchor` | `heard` (default), `steepest` | event 1's heard CPA or its steepest fall anchors the clock in scoring; changes scores, not survival |

- **One estimator.** `score.steepest_fall` places the steepest fall of the fitted ideal curve (audio
  seconds) and of each modelled curve (Unix seconds) in the same way: resample to 1 s, average over
  ±3 s, differentiate, refine the steepest point with a parabola. On the ideal curve the steepest fall
  lies within 0.5 s of the emission CPA for the four development geometries
  (`tests/test_timing_convention.py`). The comparison is between gaps, so no clock is needed.
- **Unplaceable curves.** The ideal curve at 9 km and 40 m/s peaks at 1.027 times its median slope over
  ±60 s; the development passes give 1.5–4.1. So 1.03 marks a curve too flat to place. A fall in a hole
  or outside the window is unplaceable too. An unplaceable triple skips the check, still reaches
  scoring, and is counted in the funnel as `unplaceable`.

## Prediction for the saved-fit regression check

Written before the runner sweep. Oyster Bay's committed fits come from the brightness objective, which
weights the flat tails as much as the sweep and misplaces the steepest point: their steepest-fall gap
is 8.7 s off the true one ([timing-conventions](2026-11-03-timing-conventions.md)). At T_sf ≤ 6 the
check should therefore reject the true pair on `oyster-bay` and `oyster-bay-hp150-aac32k` in the
saved-fit profile. That is the objective's known bias (PLAN 6.2), not a flaw in the convention. The
eagle cam's committed fits are `detect`'s ranks 5 and 13, so they behave as below.

## Development pass

Script: [`timing_grid.py`](../../tools/experiments/2026-11-04/timing_grid.py), on the two development
recordings. It computes triples reaching scoring and survival for every cell without scoring. The
Oyster Bay events are `detect --band 60 300 --top 10` ranks 1 and 2; the eagle cam's are ranks 5 and 13
of `docs/results/swfl_detected.json`, the 12 h `detect` run (the runner's clip may pick others).

Triples reaching scoring, and whether the true pair survives within 250 m (Y/N). The first row is
today's heard gate; "off" means no steepest-fall check.

| G_e | T_sf | Oyster Bay | Eagle cam |
|---|---|---|---|
| heard ±6 | off | 19,188 N | 50,682 Y |
| 8 | off / 2 / 3 / 4 / 6 | 25,563 Y / 3,429 Y / 4,767 Y / 5,955 Y / 8,346 Y | 65,986 N / 11,977 N / 15,162 N / 18,426 N / 24,886 N |
| 12 | off / 2 / 3 / 4 / 6 | 38,937 Y / 4,562 Y / 6,286 Y / 7,823 Y / 11,033 Y | 99,136 N / 16,232 N / 20,392 N / 24,629 N / 33,114 N |
| 16 | off / 2 / 3 / 4 / 6 | 52,532 Y / 5,551 Y / 7,559 Y / **9,401 Y** / 13,250 Y | 132,589 Y / 20,314 N / 25,252 N / **30,245 Y** / 40,265 Y |
| 20 | off / 2 / 3 / 4 / 6 | 65,546 Y / 6,324 Y / 8,519 Y / 10,565 Y / 14,916 Y | 166,943 Y / 24,311 N / 29,853 N / 35,407 Y / 46,658 Y |

- Within 600 m, today's heard gate keeps Oyster Bay's true pair, so refinement could still reach the
  truth. On the eagle cam, T_sf 2 and 3 at G_e 16 and 20 keep it within 600 m but not within 250 m.
- Unplaceable triples are 3–4 % of Oyster Bay's and 8 % of the eagle cam's.
- **Only (G_e 16, T_sf 4) meets the criterion on both recordings**, at about half today's count on each.
  It was chosen from 16 cells on two recordings, so it is a development setting until the Eclipse cases
  exist.

**Measurement (PLAN item 1's third bullet).** Modelled steepest fall minus `t_emit` for the true flights,
at the grid point nearest the reference:

| Flight | Slant range at CPA | Steepest fall − `t_emit` |
|---|---|---|
| Oyster Bay a1dfeb | 6.1 km | +0.19 s |
| Oyster Bay ace391 | 3.6 km | −4.89 s |
| Eagle cam a2baea | 2.6 km | +0.13 s |
| Eagle cam a336e4 | 6.0 km | +18.34 s |

Two of the four flights are straight to 0.2 s; one is 18 s off. Livermore's 40 passes put the steepest
fall a robust 6 s from the emission CPA ([livermore-audit](2026-11-04-livermore-audit.md)). Together they
say `t_emit` alone can't carry a tight gate. The emission gate has to be wide enough for the worst
flight, about 16 s here, and the like-for-like check is what brings the count back down.

## Runner results

The sweep ran from a detached checkout pinned at `51f59ce`, one `bench run` and run folder per setting:
`sweep.sh`, then `sweep2.sh` for the amendment's eagle-cam cells. All 45 runs exited cleanly.
[`timing_sweep_table.py`](../../tools/experiments/2026-11-04/timing_sweep_table.py) builds the table from
their records (`sweep_table.json`). "Within 250 m" is the true pair's least distance to the reference among
the triples that reached scoring (the runner's `funnel_triples.npz`).

**The deciding table.** Triples reaching scoring, and the true pair's least distance to the reference
(Y if 250 m or less). Oyster Bay and its degraded copy are at raw-audio; the eagle cam is at saved-fit
(ranks 5 and 13).

| G_e / T_sf | Oyster Bay | degraded Oyster Bay | Eagle cam | total | passes |
|---|---|---|---|---|---|
| heard ±6 (today) | 19,188, 354 m N | 19,167, 354 m N | 50,682, 85 m Y | | |
| 8 / off | 25,563, 93 m Y | 25,512 Y | 65,986, 4.7 km N | | no |
| 8 / 2, 3, 4, 6 | 3,429 to 8,346, Y | Y | 11,977 to 24,886, ~50 km N | | no |
| 12 / off | 38,937 Y | 38,862 Y | 99,136, 1.2 km N | | no |
| 12 / 2, 3, 4, 6 | 4,562 to 11,033, Y | Y | 16,232 to 33,114, 1.4 km N | | no |
| 16 / off | 52,532 Y | 52,425 Y | 132,589, 85 m Y | | no (count) |
| 16 / 2 | 5,551 Y | 5,548 Y | 20,314, 351 m N | | no |
| 16 / 3 | 7,559 Y | 7,554 Y | 25,252, 302 m N | | no |
| **16 / 4** | **9,401 Y** | **9,393 Y** | **30,245, 159 m Y** | **49,039** | **yes, adopted** |
| 16 / 6 | 13,250 Y | 13,236 Y | 40,265, 85 m Y | 66,751 | yes |
| 20 / off | 65,546 Y | 65,400 Y | 166,943 Y | | no (count) |
| 20 / 2, 3 | 6,324 / 8,519 Y | Y | 24,311 / 29,853, N | | no |
| 20 / 4 | 10,565 Y | 10,555 Y | 35,407, 159 m Y | 56,527 | yes |
| 20 / 6 | 14,916 Y | 14,900 Y | 46,658, 85 m Y | 76,474 | yes |

On Oyster Bay every emission cell puts the true pair 93 m from the truth, where today's gate leaves it
354 m away.

**The criterion is met at (G_e 16, T_sf 4)**, the cell the development pass picked. It keeps the true pair
within 250 m on all three judged cases, with about half today's count on each. It was chosen from 20 cells
on two recordings, so it is a development setting until the Eclipse cases exist.

**Ranks and answers** at the adopted cell, beside today's. Reported, not judged:

| | today: true pair rank, margin, top error | (16, 4) |
|---|---|---|
| Oyster Bay, raw-audio | 10th, 5.91 %, 77.5 km | 9th, 5.91 %, 77.5 km |
| degraded Oyster Bay, raw-audio | 10th, 5.93 %, 77.5 km | 8th, 5.93 %, 77.5 km |
| Eagle cam, saved-fit | 1st, 2.54 %, 917 m | 1st, 4.63 %, 917 m |
| WSW negative, raw-audio | –, 13.21 %, 92.2 km | –, 0.37 %, 109.4 km |
| north negative, raw-audio | –, 11.89 %, 135.5 km | –, 11.89 %, 135.5 km |

- **Oyster Bay at raw-audio.** The true pair now reaches scoring at the truth but still ranks 8th–9th. Event
  2's biased fit (f0 +6 %) scores it low, which is items 4 and 7's problem, not the gate's.
- **The eagle cam's margin almost doubles.**
- **The WSW negative** loses its confident wrong answer: 13.2 % → 0.4 %. This is the first change measured
  that makes a wrong answer less confident, and Phase 4's verdict will want it.
- **The steepest clock anchor** (`raw-g16-t4-steepest`) changes ranks by one either way and margins by under
  1 point: no consistent effect, so the heard anchor stays.
- **Unplaceable triples** at (16, 4) are 18 % on Oyster Bay and 34 % on the eagle cam. They pass to scoring
  unchecked, so the check could cut further where curves are placeable.

**The eagle cam at raw-audio is out of this item's reach**, as the amendment says: its top two events are
the clip's `detect` ranks 1 and 2 (full-stream 18,820 s and 20,247 s), not the true pair, so no gate admits
the true flights (`raw-*` runs, eagle-cam rows).

**Saved-fit regression check: the prediction held, and it is a regression.** On Oyster Bay's committed
brightness fits, (16, 4) leaves the true pair 478 m from the truth (outside 250 m, within `refine`'s
600 m). It ranks 3rd, and the top answer moves from 123 m to 70.7 km off. The degraded copy matches. That is
the brightness objective's misplaced steepest point (PLAN 6.2), as predicted. But it means switching the
search's default to (16, 4) would break today's saved-fit result on Oyster Bay.

## Outcome

**Kept, as a development setting, not yet the default.**
- `time_convention="emission"`, `tol_s=16`, `sf_tol_s=4` with the heard anchor meets the criterion. On
  raw-audio Oyster Bay it lets the true pair reach scoring at the truth, which today's gate can't.
- `run_search`'s defaults stay at today's heard gate. Switching them would break the committed brightness
  fits' Oyster Bay result.
- The default can move when the saved fits are refitted with the contrast or least-squares objective, or
  when a run shows no saved-fit regression.
- PLAN's phase exit ("no wrong pair beats the true one where it didn't before") rules out switching now.
