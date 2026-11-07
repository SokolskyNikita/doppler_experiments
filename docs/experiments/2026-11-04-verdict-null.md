# A null of the maximum for the "located" verdict: the saved-fit arm

<!-- index
question: Does the winner of a whole search clear the 1 % point of its own null of the maximum (other days' flight data through the same search), so that the "located" verdict can rest on it (Phase 4)?
outcome: Not met: with the committed fits no positive clears its threshold; the eagle cam's own day sits at its null's median and Oyster Bay's is beaten by 3 of 50 other days, so the maximum score alone can't carry "located"
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `cc7a18eed4c91ee3a337c008d3214164c98a0b68f684720f6ec3e6dd66a6cdf4`.

> **Research reset correction, 2026-11-04.** The usefulness criterion fails as reported; none of its
> positive cases clears the fitted threshold. The 0/3 Clopper–Pearson interval below must not be interpreted
> as a population interval: hp150 shares Oyster Bay's source, leaving two positive recording groups. Fifty
> null days do not empirically certify a 1% tail; fitted-Gumbel bootstrap intervals are conditional on that
> family. A standard fixed-distribution KS cutoff after fitting its parameters is not a calibrated
> goodness-of-fit test. Repeated routes do not prove this null conservative for every live false-match
> distribution. The automatic arm was unrun, not mathematically guaranteed to be worse. This is evidence
> against this statistic's usefulness under this specified null, not against all threshold methods; see [the
> audit](2026-11-04-research-reset.md).
> The saved verdicts.json also corrects the later “true pair is the search's own winner” claim:
> on the eagle cam its highest mode is the wrong pair a0e90b/a25807 at 8.596579; the true pair is second
> at 8.559615. The raw saved-fit baseline's rank1 is a different statistic/run. Both remain below gamma.

## Question and criterion

PLAN Phase 4, "Thresholds", as designed in [the proposal](../proposals/2026-11-04-verdict-null.md); the criteria were
written there before anything ran.
- **The verdict:** "located" when exactly one distinct mode's score clears γ, the 1 % point of the case's null of the
  maximum. Otherwise "ambiguous", with `competing_mode` or `below_null_threshold`.
- **The null:** the same events, box, grid and search, run against the box's flight data from another day.
  - That is real traffic that can't have made the audio.
  - It is 50 seeded days per recording group, from ±60 days around the recording, skipping ±2.
  - A Gumbel distribution is fitted to the 50 maxima, with a 1,000-resample bootstrap interval.
- **Calibrated means:**
  - every positive (oyster-bay, oyster-bay-hp150-aac32k, eagle-cam-clip-18000s) is "located", on the true pair,
    within 2 km;
  - every negative (oyster-bay-moved-wsw150, oyster-bay-moved-north150) is not.
- **If it fails on this saved-fit arm**, the threshold itself fails, and PLAN's fixed rule stands.

## Setup

- **The arm:** saved-fit, so the committed fits isolate the verdict from event choice. The search is
  `run_search(comparable=True)`, with m = 2 matched flights, so κ doesn't enter.
- **Code:** [`verdict_null.py`](../../tools/experiments/2026-11-04/verdict_null.py) at `0068669`.
- **Units:** 5 cases × 51 days (each case's own day and 50 others) = 255 searches.
- **Boxes:** 30 4xlarge boxes, one search at a time.
  - Spot, except four on-demand ones: shard 30 relaunched (`-s30of30-2`) and the resumes of shards 4, 7 and 12.
  - About $9.80 with the day cuts, $0.54 of it on demand.
- **Runs:** `runs/2026-11-04-verdict-null-s<k>of30*/`, merged in `runs/2026-11-04-verdict-null-merge/`.
  - `verdicts.json` was written and hashed before any label was read; then came `reveal.json`.
- **The null days' traces:** [`verdict_null_days.py`](../../tools/experiments/2026-11-04/verdict_null_days.py).
  - Each day was streamed once from adsb.lol and cut into every box of its group with the cases' own recipes:
    `derived/traces/<day>/`, read-only, in the data manifest.
  - The fleet's boxes can't reach OpenSky, so the prop filter's aircraft-type table is now a raw/aux input.
  - Day traffic ranges from 167 prop traces on Christmas Day to 845 on a January day, against 616 on the eagle cam's
    own day.

## Results

| Case | Expected | Own day's top Z | Null median | Null days ≥ own | γ (1 %) [95 % CI] | KS (n = 50) | Verdict |
|---|---|---|---|---|---|---|---|
| oyster-bay | located | 19.96 | 15.67 | 3 / 50 | 25.81 [23.37, 27.81] | 0.089 | ambiguous, below_null_threshold |
| oyster-bay-hp150-aac32k | located or abstain | 20.48 | 16.17 | 3 / 50 | 26.50 [23.79, 28.55] | 0.092 | ambiguous, below_null_threshold |
| eagle-cam-clip-18000s | located | 8.60 | 8.64 | 26 / 50 | 14.00 [12.87, 14.69] | 0.192 | ambiguous, below_null_threshold |
| oyster-bay-moved-wsw150 | not located | 17.88 | 14.58 | 4 / 50 | 23.86 [21.51, 25.47] | 0.132 | ambiguous, below_null_threshold |
| oyster-bay-moved-north150 | not located | 17.83 | 15.87 | 14 / 50 | 29.90 [26.19, 32.43] | 0.111 | ambiguous, below_null_threshold |

- **Calibration fails on the positives:** 0 of 3 located, Clopper–Pearson 95 % [0, 0.71]. The two negatives are not
  located, but trivially: nothing is.
- **The null days' best wrong answers score as high as the truth.**
  - On the eagle cam, the own day is at the null's median: 26 other days score at least as high.
  - On Oyster Bay, 3 of 50 do (Gumbel tail p ≈ 0.10).
  - WSW's own day, a negative, is beaten by only 4. So by this statistic Oyster Bay's truth isn't distinguishable
    from a moved box's best wrong answer.
- **The fits behave.** The KS statistics are 0.09–0.19 at n = 50; about 0.19 is the 5 % point, so the eagle cam's fit
  is at the edge. γ's bootstrap intervals are 1.8–4.4 wide, against gaps of 5.4–6.3 between the positives' scores and
  γ.
  - So under the review’s rule the extension to 100 days isn't needed for this arm: no gap is inside the interval. Its
    cuts are still published, for the locate arm and for the geometry study.
- **The caveat holds.** Other days' traffic flies the same routes, so it nearly matches the audio by construction.
  That makes this null conservative, and it is, by a wide margin.

## Outcome

**Not met, and it is the threshold's failure, not event choice's.** These are the committed fits, and the true pair
is the search's own winner on Oyster Bay and the eagle cam.
- **What this shows.** A whole-search maximum of the comparable score doesn't separate the true day from other days'
  traffic over the same box.
  - The search is so wide (every grid point, flight pair and clock) that its best wrong answer is as good as the
    truth.
  - That is Kay's L · P_FA(cell) made concrete.
- **Under the decision line,** `locate`'s v2 verdict doesn't adopt this threshold, and PLAN's fixed rule stands. The
  locate arm isn't run, since it can only do worse.
- **What could carry "located" instead** is a statistic the other-day null can't match. The best candidate so far is
  the [frozen-clock](2026-11-04-comparable-score.md) test: extra flyovers explained within ±15 s at the candidate's
  clock. At the true candidate's clock every extra flyover had a flight within 2–6 s; at the wrong one's, none did.
  The same null machinery tests it: draw the other-day maximum of "extras explained" and see whether the truth's count
  clears it. That is a new proposal, not a retune of this one.
