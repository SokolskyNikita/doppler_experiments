# Wider search gates (2026-11-03)

<!-- index
question: Do wider search gates let the true pair through safely?
outcome: No: at ±12 s a wrong pair wins on both recordings
-->

**Question.** Ideal-curve fits of real passes overestimate f0, which moves the fitted CPA time with it ([2026-11-03-event2-bias](2026-11-03-event2-bias.md)). Does widening the pairing gate (the time between the events) and the f0 sweep let the true pair through without letting wrong pairs win?

**Change.** Two knobs: `--tol` (default ±6 s) and `--f0-tol` (default ±5 %). Their code is in tag `archive/gate-tolerances` (commit 174bc49). Development data.

| Gates (time between events, f0 sweep) | Oyster Bay, README windows, current objective | Oyster Bay, `detect` events | Eagle cam, committed events |
|---|---|---|---|
| ±6 s, ±5 % (defaults) | filtered out at the true location (blind search not run) | filtered out at the true location (blind search not run) | 1st of 607 pairs, 2.5 % margin, 50,682 candidates |
| ±10 s, ±12 % | 1st of 469, 17.8 %, 32,554 | – | 1st of 647, 1.6 %, 84,431 |
| ±12 s, ±12 % | 1st of 485, 17.8 %, 39,144 | 2nd of 505, −6.7 %, 38,531 | 2nd of 660, −0.5 %, 101,673 |

- **Committed Oyster Bay fits.** ±12 s / ±12 % changes nothing at the top: 1st of 358, the same 4.0 % margin, with 81,339 candidates instead of 40,889.
- **Eagle cam.** The ±12 s gate lets in points where a wrong pair 9 km from the nest outscores the true one.
- **The f0 sweep.** Widening it changed no score at the points both runs share. Scoring cost rises about 2.3× per candidate at ±12 %.

**Outcome: not adopted.** A single flyover's f0 and timing trade off in scoring, so a wider gate on one acts as a wider gate on the other, and widening both lets wrong pairs win. [2026-11-03-timing-conventions](2026-11-03-timing-conventions.md) gives the size of that trade-off.

±10 s / ±12 % is the only setting tried that kept the true pair first on both recordings with the README windows. It is therefore PLAN Phase 2's fallback, although it wasn't run on `detect`'s Oyster Bay events.

**Scripts:** `tol_grid.py`, `summarise.py`, `swfl_truth.py`. **Outputs:** `runs/2026-11-03-issue-1/`, which also keeps `gate-tolerances.patch`.
