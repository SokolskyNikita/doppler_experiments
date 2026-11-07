# A null of the maximum for the "located" verdict (proposal)

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `58de32d6d7c0a4d94268cd3caa8a71b072c64b0e2b4bdb4ce850baa9919a63bf`.

> **Research reset correction, 2026-11-04.** The saved-fit arm failed; the automatic arm and matched-extra
> penalty were not validated. The proposed 4/4 and 0/4 binomial intervals are not valid population intervals
> for source-dependent variants. Other-day traffic is a specified competitor distribution; its
> conservativeness and exchangeability with deployment false matches remain assumptions. Fifty draws plus a
> fitted Gumbel do not independently establish a 1% error rate, and fitted-parameter KS/ordinary bootstrap
> diagnostics do not settle tail misspecification. Preserve the failures and freeze the complete search/null
> procedure in any successor; see [the audit](../2026-11-04-research-reset.md).

PLAN Phase 4, "Thresholds". This is a design, written before any code or run.

**decision:** whether `locate`'s schema v2 verdict emits "located" when the winner's penalised score clears the 1 %
point of its own null of the maximum. The alternative is step A's rule, which never says "located", with PLAN's
fixed-rule fallback.

**Where `locate` starts** ([locate](../2026-11-04-locate.md), Tier 2, `runs/2026-11-04-locate-t2b-*-merged/`).
- With automatic events, only the `comparable` pair rule with the silence filter on picks a seed case's true pair:
  Oyster Bay and its degraded copy, refined 278 m from the truth on the copy.
- The eagle cam's pick is the 14.6 km wrong pair a0e90b/a25807.
- So the `locate` profile will likely fail the positives below whatever the threshold. The `saved-fit` profile is
  what tests the threshold itself.

## Why a null of the maximum

The winner is the maximum of a search over every grid point, flight pair and clock in the box. Its score is not a
single cell's score.
- A per-cell threshold understates the false-alarm rate by about the number of independent cells L:
  P_FA ≈ L · P_FA(cell), so the threshold must grow as 2 ln(L/P_FA) (Kay II eq. 7.36–7.38).
- Under H0 the location and clock aren't identifiable, so asymptotic χ² tests don't apply (Kay II Ex. 9.4).
- So the threshold is read from draws of the whole search under H0, not computed.

## How the null is drawn

**H0:** no flight in the box made the recording's events.
- **A draw** is the whole `locate` search, with the same events, box, grid, pair rule and refinement, run against
  the box's flight data from another day. The traffic is real, with the box's density and routes, but none of it
  can have made the audio.
- **Time shifts don't work.** `locate` searches the date clock-free, so the same day's traces shifted in time only
  shift the clock it finds. The maximum doesn't change.
- **The statistic per draw:** for each number of matched flights m, the best penalised score S_m over every
  distinct mode (below), and the two best modes.
- **The days:** a fixed, seeded list from the 120 days around each recording's date, skipping ±2 days. It starts at
  50 per recording group (review, 2026-11-04). It grows to 100 only if the fitted 1 % point's bootstrap interval is wider
  than the gap between the positives' scores and the threshold. Each day is cut to the case's margin-padded box, with extraction metadata, as the case's
  own traces are.
- **A caveat the record keeps.** Another day's traffic flies the same routes, so it can come close to matching the
  audio by construction. That makes this null conservative in the direction we want, and the probability plot is
  what shows it behaves.
- **Why a Gumbel fit.** With 0 exceedances in B draws the 95 % upper bound on the tail is 3/B, so an
  empirical 1 % claim alone needs B ≥ 300.
  - The 1 % point is taken instead from a Gumbel fit to the maxima. A maximum over many weakly dependent cells
    has an exponential tail, as in Kay's L · P_FA(cell).
  - The fit is checked by a probability plot and by the 3/B bound.
  - The fit is reported per case and per m, with its 95 % interval from a bootstrap over draws.
- **Why the comparable score.** Each event's z is already against its own null, so draws from different days are
  on one scale. a1_noise.py's redraws add each draw's null sampling error.

## The penalty for matched flights

A candidate matches m flights: the event pair (m = 2), plus each extra flyover that refinement assigns within ±15 s.
Every extra flight is one more chance under H0.
- So candidates with different m are compared by penalised score (Kay II §6.8, eq. 6.40–6.41), S_m = Z_m − κ (m − 2).
  Z_m is the sum of the m flights' comparable z.
- κ is set from the null, as the median increase in the draws' maximum when one more flight may be matched. The
  null of S_m then doesn't drift with m.
- MDL's (n/2) ln N, with n = 2 parameters per flight (its CPA time and f0), is reported beside it as the analytic
  check, not used.

## Modes and regions

Modes are PLAN's: two candidates are distinct when they lie farther apart than the resolution (2 km, as in the
locate record) or their clocks differ by more than a pass resolves.
- **Located:** exactly one mode's S_m clears its threshold γ_m.
- **Ambiguous, reason `competing_mode`:** two or more modes clear it. Each region is listed, never merged.
- **Ambiguous, reason `below_null_threshold`:** none clears it.
- The two reason codes are in the v2 list (`988a0df`).
- The eagle cam's true pair and its 14.6 km wrong pair are this case today: two modes about 0.02 apart in Z. A third
  flyover that only the true clock explains is what can separate them, and it does, via m = 3
  ([frozen-clock](../2026-11-04-comparable-score.md)).

## What counts as calibrated

Development set only, both profiles.
- **`locate`, automatic events:** what the release does.
- **`saved-fit`, the committed fits:** isolates the verdict from event choice, which B1 and A1 show is still the
  weak step.

Criteria, each case judged against its own null's γ_m:
- **Positives:** oyster-bay, oyster-bay-hp150-aac32k, eagle-cam-clip-18000s and eagle-cam-midnight are each
  "located", on the true pair, within 2 km.
- **Negatives:** oyster-bay-moved-wsw150, oyster-bay-moved-north150, oyster-bay-sources-removed and xenocanto-xc990819
  are each not "located". eagle-cam-midnight-days0 ends before the search, as it does now.
- **The Beta intervals:** with 4 of 4 positives, the 95 % Clopper–Pearson interval for P(located | positive) is
  [0.40, 1]. With 0 of 4 negatives, P(located | negative) is [0, 0.60].
  - The record states both, and says that development cases can't establish rates.
  - The verdict stays labelled experimental until the calibration group (eclipse-esid740, xenocanto-xc979185) agrees.
- **What happens if the criteria fail:**
  - If they fail on `locate` but pass on `saved-fit`: the threshold is sound, event choice is the blocker, and v2
    keeps never-located.
  - If they fail on `saved-fit`: the threshold itself fails, and PLAN's fixed rule stands.

## Implementation, after this is read

- A driver on `tools/data/shards.py`. Units are (case, null day), and each unit is one `locate` search with the
  case's pair rule.
  - It runs on 4xlarge boxes, one search per box where memory decides. Stage B's d4 + d3 pairs exceed 128 GB, so
    `hypotheses` stays off.
  - Its merge fits γ_m and κ per case, then judges the Tier 2 cases.
- **The null days' traces** come first ([`verdict_null_days.py`](../../../tools/experiments/2026-11-04/verdict_null_days.py),
  planned in `verdict_null_days.json`).
  - Each day is streamed once from adsb.lol's release and cut into every box its group needs, by `extract_boxes.py
    --stream`, with the same recipe and margin as the cases' own cuts.
  - The groups: Oyster Bay with its WSW and north boxes, on 2026-09-08's side, and the eagle cam's SWFL box, on
    2024-12-28's.
  - A day already in derived/ is never fetched again.
  - The cuts are published read-only to `derived/traces/<day>/` and recorded in the data manifest (adsb.lol,
    ODbL 1.0).
- **The clock gate.** `locate`'s clock gate ([clock-gate](../2026-11-04-clock-gate.md)) keeps only
  triples whose clock lies within the case's stated start and tolerance. Another day's flights would all fail it.
  - So the locate arm shifts each null day's traces by whole days onto the recording's date, keeping the time of
    day, and runs with the gate on, as the case does.
  - The saved-fit arm runs `run_search`, which has no gate, so its days need no shift.
  - The null block's names follow schema v3 (`verdict.null`).
- The null replicates the pair rule and silence filter that `locate`'s verdict uses. A `comparable` draw is ten
  searches, like the case itself, and the `saved-fit` arm is one. The final locate record sets the rule; the null
  waits on it.
