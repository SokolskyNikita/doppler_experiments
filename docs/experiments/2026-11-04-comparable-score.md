# A comparable score for event choice

<!-- index
question: Does scoring each event pair in units of its own wrong guesses put event pairs on one scale (item 7, stage A)?
outcome: Not met: A1 is inside the null's noise and not separable; the comparable score moves the eagle cam's true pair from 5th to 2nd and no further
-->

## Question and criterion

PLAN Phase 2, item 7, stage A. The [event-pairs](2026-11-04-event-pairs.md) test found that ranking `detect`'s
event pairs by their search's top score picks the loudest events: on the eagle cam the true pair is 5th of
10, behind three pairs that contain the loudest detection. Scores of different event pairs aren't on one
scale. Does scoring each event against its own null put them on one? Written before anything ran.

**The score.** `run_search(comparable=True)`:
- For each event, draw a null of N = 1,000 (grid point, flight) rows uniformly, with replacement, from the
  case's CPA table. The seed comes from the event's fit, so every search containing the event draws the
  same rows. Nearly all are wrong flights.
- Score the event against each row with `single_score`: the row's flight is anchored on the event's heard
  CPA, as `locked_score` anchors event 1, and swept over the same shifts and f0 scales.
- The null's median μ and 1.4826 × MAD σ are the event's floor and spread. A triple's event score s_k
  becomes z_k = (s_k − μ_k) / σ_k, and the triple's score is Z = z₁ + z₂, so a loud event's z is large only
  where a flight explains it. This is Axelrad 2011's normalise-then-sum, applied to events instead of
  satellites.
- Ranking within a search is by Z; an event pair's score is its search's top Z.
- **A correction to the design as approved.** That design drew the null from rows "whose heard CPA falls
  within the event's window ±60 s". The window is in recording seconds and the table in Unix seconds, with
  no clock between them in a two-event search. So the null instead anchors each row on the event, which is
  how a wrong flight is actually placed. The ±60 s knob is gone.
- **z₂ errs low.** Event 2 is scored at event 1's shift, while its null maximises over shifts.

**Criterion.** At raw-audio, on the ten pairs of each case's top five `detect` events, from the raw-audio
baseline at `5314396` (SDE-B's selection), ranked blind:
- **A1.** On `eagle-cam-clip-18000s`, the true pair (`detect` ranks 2 + 5) ranks first of the ten by top Z.
- **A2.** On `oyster-bay-moved-wsw150`, the top pair's Z margin over the second pair is no larger than the
  eagle cam's true pair's Z margin over its second.
  - This tests comparability, not a verdict. One negative passing by chance is possible, so the ten pairs'
    full Z distribution is reported for both cases.
  - The absolute bar belongs to Phase 4's verdict.
- **A3.** On `oyster-bay`, events 1 + 2 stay first of its ten.

**Reported beside it**, as asked: whether the true pair survives the coarse search, i.e. within 250 m of
the reference in the runner's triples sidecar, and within `refine`'s reach. Separately, its rank once
retained. Each pair's raw top score is also reported.

**Knobs**, counted:
- N = 1,000;
- the null's median and 1.4826 × MAD;
- Z = z₁ + z₂ (an unweighted sum).

One retune at most after the first run, counted.

If A1–A3 pass, stage A ships: `comparable` as library code, and a runner profile `raw-audio-z` (top five
events, ten pairs, ranked by Z) beside `raw-audio`. `raw-audio`'s top-two rule is unchanged until stage B's
B1 and B2 pass and a Tier 2 run shows no regression on the seed cases.

**Script:** [`event_pairs_z.py`](../../tools/experiments/2026-11-04/event_pairs_z.py), SDE-B's
`event_pairs.py` copied with `comparable=True` added, using its run-folder layout.

## Results

The run used `abe6998`, from a pinned checkout, in `runs/2026-11-04-comparable-score/`: 30 searches, two at a time with 4
workers, 1,778 s. The ranking was written and hashed before any label was read (`ranking.json.sha256`); then came
`reveal.json` and `evaluation.json`.

**Eagle-cam clip**, the true events being `detect` ranks 2 and 5:

| Z rank | Events | top Z | raw top score (its raw rank) | True pair: within 250 m / rank in its search | Top error |
|---|---|---|---|---|---|
| 1 | 4 + 2 | 8.37 | 10.40 (3rd) | – | 35.3 km |
| **2** | **2 + 5** | **8.34** | 10.27 (5th) | **yes / 1st** | **917 m** |
| 3 | 2 + 3 | 7.72 | 9.64 (7th) | – | 71.8 km |
| 4 | 1 + 2 | 7.41 | 11.58 (1st) | – | 54.3 km |
| 5–10 | the rest | 6.76–4.97 | | – | 18.7–69.4 km |

**Oyster Bay**: events 1 + 2 first at Z 18.02, against 15.79 for the next. Their true pair is not within 250 m of
the truth (the heard gate, as in the [timing-convention](2026-11-04-timing-convention.md) baseline), and it ranks 4th
in its search, against 10th by raw score. The other nine pairs don't hold the true pair.

**WSW moved box**: events 1 + 2 first at Z 17.53, against 14.94 for the next, answering 92.2 km from the truth.

**The ten pairs' top Z**:
- eagle cam: 8.37, 8.34, 7.72, 7.41, 6.76, 5.76, 5.47, 5.19, 5.06, 4.97;
- Oyster Bay: 18.02, 15.79, 13.79, 12.23, 10.80, 9.35, 8.13, 7.39, 6.36, 6.21;
- WSW: 17.53, 14.94, 13.82, 12.90, 10.70, 10.59, 8.06, 7.83, 6.94, 6.28.

| | Criterion | Result |
|---|---|---|
| A1 | the eagle cam's true pair first of ten | **not met**: 2nd, 0.03 in Z behind 4 + 2 (5th by raw score) |
| A2 | WSW's top margin ≤ the eagle cam true pair's margin | **not met**: 2.59 against −0.03 |
| A3 | Oyster Bay's 1 + 2 first | met |

## Outcome

**Not met; stage A doesn't ship.** The one retune is not spent yet (see below).
- **What Z fixes.** The loudest event no longer carries its pairs. On the eagle cam, every pair holding
  `detect`'s rank 1 falls: 1 + 2 from 1st to 4th, 1 + 4 from 2nd to 8th, 1 + 5 from 4th to 10th. The true
  pair rises from 5th to 2nd, 0.03 behind a pair that shares its event 2. Comparability, the thing stage A
  was for, is mostly there.
- **What it doesn't fix.** The moved box isn't a comparability failure. Its top pair is Oyster Bay's own two
  true flyovers, which are genuinely the best-explained events in that audio, so Z picks them for the right
  reason. A busy box then offers a wrong flight pair that explains them well. So event-pair ranking can't
  make a wrong location less decisive: A2 asks event choice to do the verdict's job.
- **Two results kept apart, as the PM asked.** Survival: on the eagle cam the true pair survives the coarse
  search within 250 m in its own search; on Oyster Bay, under today's heard gate, it doesn't. Rank once
  retained: 1st on the eagle cam, 4th on Oyster Bay.
- **The size of the eagle-cam miss.** At 0.03 in Z, it is well inside the run's noise. A different null
  draw of the same size would move each event's median by about 1.25σ/√1000 ≈ 0.04σ, which is enough to
  swap the two pairs.
- **Not spent.** The one retune is kept, by the PM's decision. `comparable=True` stays as off-by-default library
  code (`a440f85`).

**A2 is withdrawn as a pass/fail criterion. This is a criterion change, made after seeing the result,
2026-11-04.** From stage B on, A2 is a reported quantity, not a test.
- It asked event choice to make a wrong location less decisive. The WSW result shows that is the verdict's
  job: Z picks Oyster Bay's two true flyovers there for the right reason, and the busy box then supplies a
  wrong flight pair that explains them.
- A criterion that only a worse event score could meet was wrong as written.

**Stage B re-runs A1 and A3** under the same criterion, with stage B's hypotheses and N kept at 1,000 so the
two stages compare. If A1 is still inside the null's sampling noise after stage B, the record will say the
test can't decide at this N, and the retune, if spent, goes on N.

## What this says for PLAN

- **Event choice (items 6 and 7).** Normalising each event by its own null removes most of the loudness
  advantage, so event pairs can be compared. Whether it picks the right pair on the eagle cam can't be told
  at N = 1,000.
- **Phase 4's verdict.** The look-elsewhere correction belongs there, not in the event score: subtract the
  expected maximum of Z over the triples each search scored (about √(2 ln n) per event, Gumbel). A busier box
  tries more wrong flight pairs, so its best wrong answer scores higher by chance. That is the WSW result, and
  only a verdict that accounts for how many hypotheses were tried can make it less confident.

## A frozen-clock test of the eagle cam's two best candidates

Asked for by the PM; development data only. Inside the eagle cam's true-pair search, the two best candidates score
almost alike:
- 1st: Z 8.342, the true flights a2baea/a336e4, 917 m from the nest;
- 2nd: Z 8.323, a0e90b/a25807, 14.6 km away, with a recording clock 792 s (13.2 min) different.

Each was frozen at its location and clock (its record's `audio_minus_utc_s` and `shift_s`), and the clip's other
detections were scored under each without readjusting the clock. These are `detect`'s ranks 1, 3 and 4; rank 1,
at 820 s, is the README's extra flyover at full-stream 18,820 s. Two rules for the explaining flight:
`pick_flight`'s (`refine --extra`), and the [extra-consistency](2026-11-03-extra-consistency.md) record's ±15 s
heard-CPA gate.

| Extra flyover | true candidate, ±15 s | wrong candidate, ±15 s | true, pick_flight | wrong, pick_flight |
|---|---|---|---|---|
| rank 1, 820 s | **a68cab, 4.27** (heard 6.2 s off) | **none** | 4.27 | 4.13 |
| rank 3, 4,283 s | **a44af9, 3.54** (2.3 s) | **none** | 3.54 | 2.76 |
| rank 4, 2,175 s | **a13d1e, 3.34** (4.9 s) | **none** | 4.00 (a2baea) | 3.56 |

- **The ±15 s gate separates them completely.** At the true candidate's clock, every extra flyover has a flight
  whose heard CPA lands within 2–6 s. At the wrong candidate's, none has one within 15 s. Under the 2026-11-03
  record's bar of 3.0, the true candidate explains 3 of 3 and the wrong one 0 of 3.
- **`pick_flight`'s ±5 min rule doesn't separate them** (11.8 against 10.5 summed), as the 2026-11-03 record found.
- So the two candidates that Z can't tell apart make different physical predictions, and one extra flyover
  is enough to test them.
- This is Phase 4's verdict material. It is the first case where it decided between two candidates of one
  search that a score couldn't.

One recording, three extras, one pair of candidates: a lead. Script:
[`frozen_clock_extra.py`](../../tools/experiments/2026-11-04/frozen_clock_extra.py). Output:
`runs/2026-11-04-frozen-clock-extra/frozen_clock_extra.json`.

## Stage A at today's code, on the fleet

Rerun on 2026-11-04 at `18ff8b4` to answer cloud_jobs.md's decision line: is event choice the Phase 3 blocker?
- **Setup:** the same 30 searches and detections. N = 1,000 per event, as before.
- **Boxes:** 4 × 8xlarge (3 on demand, 1 spot), 300–366 s wall each, $0.59.
- **Shards:** `runs/2026-11-04-comparable-score-s1of4/` to `-s4of4`. **Merged:** `runs/2026-11-04-merge-pairs-a/`.
- The ranking was hashed before the labels were read.

| | Criterion | Result |
|---|---|---|
| A1 | the eagle cam's true pair first of ten | **not met, and inside the null's noise**: 2nd at Z 8.176, 0.049 behind 4 + 2 (8.225) |
| A3 | Oyster Bay's 1 + 2 first | met: Z 16.93, against 14.84 for the next |
| A2 | reported only | WSW's top margin 2.75 |

**The noise test**, by [`a1_noise.py`](../../tools/experiments/2026-11-04/a1_noise.py), on this run's kept nulls:
- the gap is −0.049, and its standard deviation from the nulls' sampling error is 0.128;
- the true pair comes first in 42 % of 20,000 redraws;
- deciding the gap would take N ≈ 27,300 per event.

**The null's noise, directly.**
- Inside the true pair's own search, the true flights and the 14.6 km wrong pair (a0e90b/a25807) have the same raw
  event scores as in stage A's `abe6998` run: [6.242, 4.029] and [6.802, 3.223].
- Only the nulls changed. The CPA table built on the Linux box has one row more than the Mac's (35,861,817 against
  35,861,816), so the null's index draws land on different rows.
- That alone moved Z by about 0.15, and swapped the two candidates: true 8.342 and wrong 8.323 before, against
  8.157 and 8.176 now.
- So the call between them is the null's sampling, not the recording.

**Outcome (PM, 2026-11-04).**
- A1 is inside the null's noise at N = 1,000, and is not separable. A true pair that a 14.6 km wrong pair beats by
  0.05 in Z ≈ 8 is not something this score separates, whatever the null's size.
- The comparable score moves the eagle cam's true pair from 5th to 2nd, and no further. A3 is met.
- No rerun at a larger N: stage A's one retune stays unspent. A bigger null would only measure the −0.049 ± 0.128
  gap more precisely.
- The decision line's answer:
  - The comparable score improves event choice but doesn't fix it.
  - B1 is not met on any case, in [stage B](2026-11-04-hypotheses.md)'s reproduction at today's code. So the fit's
    bias is the blocker for Phase 3.
- That the CPA table differs by one row between Linux and macOS is its own item: see
  [parallel-cpa](2026-11-04-parallel-cpa.md).
