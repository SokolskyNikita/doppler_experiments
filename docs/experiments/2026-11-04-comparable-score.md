# A comparable score for event choice

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

Pending.
