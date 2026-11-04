# Which event time to pair on (2026-11-03)

**Question.** The search pairs two events by comparing their fitted *heard*-CPA times with the CPA table's `t_heard`. The fitted heard-CPA time is t_cpa = t_cpa_emit + d/c. For a straight, constant-speed pass, the heard frequency falls fastest at the emission-CPA instant, and passes f0 (the heard CPA) d/c later (Ferguson & Lo 2000, eqs. 3–4). So the heard-CPA gap inherits every error in the fitted distance, while the emission-CPA gap (`t_cpa_emit` against the table's `t_emit`) doesn't. Which convention puts the true pair closer?

**Change.** None to the code. At each true location: the true flights' gaps under each convention, and the gap error of each saved pair of fits. Development data.

True gaps, from the trajectories:

| | Oyster Bay | Eagle cam |
|---|---|---|
| Gap between the flights: heard CPA, emission CPA, steepest fall | 922.96, 930.17, 928.18 s | 331.61, 321.47, 338.30 s |
| Heard CPA after the emission CPA (d/c), flights 1 and 2 | 17.9, 10.7 s | 7.5, 17.6 s |
| Steepest fall after the emission CPA, flights 1 and 2 | −0.4, −2.4 s | −0.2, +16.6 s |

Gap error of each pair of fits. Each cell gives three errors: the heard gap; the emission gap; and the emission gap against the true steepest-fall gap.

| Fits | Oyster Bay | Eagle cam |
|---|---|---|
| Committed (pre-f890572 brightness objective; on the eagle cam these are `detect`'s #5 and #13) | −5.0 / −10.7 / −8.7 s | +6.2 / +14.1 / −2.7 s |
| Current contrast objective, README windows | −9.0 / −2.4 / −0.5 s | not run |
| `detect`'s own fits | −10.1 / −3.6 / −1.6 s | as committed |
| Re-fit ±55 s, brightness ([rewindow](2026-11-03-rewindow.md)) | – | +8.2 / +15.2 / −1.6 s |
| Re-fit, the other three variants | – | +19.4 to +26.0 / +26.4 to +29.3 / +9.5 to +12.5 s |

**Outcome: a lead, and PLAN Phase 2's first experiment.**
- **Size of the heard-gap errors.**
  - The fitted curve is pinned to the data around its steepest stretch. An f0 error of δf0 therefore moves its f0 crossing, the heard CPA, by δf0/g_max, where g_max is the curve's peak slope (Ferguson & Lo 2000, eq. 3).
  - For Oyster Bay's event 2 (f0 ≈ 126 Hz, 103.5 m/s, 3.6 km), g_max is 1.26 Hz/s, or 1.0 s per 1 % of f0.
  - That is consistent with the 5.0, 9.0 and 10.1 s errors at f0 errors of 5, 10 and 11 % ([event2-bias](2026-11-03-event2-bias.md)).
- **The emission convention, against the CPA table's `t_emit`.** It would have put the contrast and `detect` fits well inside ±6 s on Oyster Bay, but made the committed fits worse on both recordings:
  - The brightness objective weights the flat tails as much as the sweep, and misplaces the steepest point (−8.7 s on Oyster Bay).
  - The eagle cam's second flight falls fastest 16.6 s after its geometric CPA. Either it wasn't flying straight at constant speed there, or its slope peak at 6 km is too broad to place.
- **Like for like held on both recordings.** The contrast, `detect` and committed eagle-cam fits are within 0.5–2.7 s of each true curve's own steepest-fall time.
  - That compares the steepest-fall time of the fitted curve with the steepest-fall time of the curve modelled from the actual trajectory.
  - It costs more than a CPA-table lookup, so it belongs at scoring, after a looser emission-convention gate.
- **Scope.** Two recordings and two events each.

**Script:** `timing_conventions.py`. **Outputs:** `runs/2026-11-03-timing-conventions/`; `output_v2.txt` has all three columns.
