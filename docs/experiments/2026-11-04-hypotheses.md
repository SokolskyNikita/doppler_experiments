# Event hypotheses instead of gates

## Question and criterion

PLAN Phase 2, item 7, stage B. Can each event's own hypotheses replace the search's independent speed, distance
and f0 gates? Each hypothesis is an optimum of the event's fit with the region in v, k = v²/d, τ and f0 that it
supports. Can they keep the true flights while admitting no more candidates than today? Written before
anything ran; the design was agreed with the PM in advance.

**Criterion** (PLAN's, as agreed):
- **B1.** On every positive case, each event's hypotheses admit its true flight. That means the true flight's
  CPA row, at a grid point within 250 m of the reference, lies inside some hypothesis's v and k ranges.
  - `oyster-bay` and `oyster-bay-hp150-aac32k` are judged at raw-audio: `detect`'s top two by score, earlier
    first, from the raw-audio baseline at `5314396`.
  - `eagle-cam-clip-18000s` is judged with its committed fits, `detect`'s full-stream ranks 5 and 13, as
    item 1's ruling set it.
- **B2.** Per event, the CPA rows its hypotheses admit are no more than today's speed and distance gates
  admit (±35 % speed, 0.4–2.5× distance) for that event.
- **A1 and A3, re-run with stage B.** These are [stage A](2026-11-04-comparable-score.md)'s tests, under the
  same criterion, with the null kept at N = 1,000 so the two stages compare.
  - A1: the eagle cam's true pair (2 + 5) is first of the ten pairs by top Z.
  - A3: Oyster Bay's 1 + 2 stay first.
  - If A1 is still inside the null's sampling noise, the record says the test can't decide at this N, and the
    retune, if spent, goes on N.
  - A2 is reported, not judged (stage A's record says why).

**Design** (`hypotheses.py`, `run_search(hypotheses=True)`):
- **Two sources, up to K = 3 optima each.**
  - "ls": the least-squares fit of `ridge()`'s track, when `fit_track` says identified. Its optima are those
    within the threshold below of the best.
  - "fit_event": the best emission-CPA times on `detect`'s coarse scan grid, at least 20 s apart, each refined
    by `fit_event`. Its optima are those within the threshold below of the best.
- **Regions from profiles** (Raue 2009): for each of v, k, τ and f0, the objective re-optimised over the
  other three, with the range where it stays within the threshold. They are sensitivity ranges, since
  neither objective is a calibrated likelihood.
  - "ls": the track's RSS within 3.84 × 3 residual variances. The 3 is the variance inflation of 88 %
    overlapping frames from SDE-D's c(r)² model.
  - "fit_event": the brightness under the ideal curve within 2 σ of the event's null. That brightness is the
    null's own scale (`event_null`, N = 1,000).
- **Weak flags.** A range that reaches its bound before the objective falls off is weak and widened to the
  bound: v to 10–300 m/s, k to the speed and distance bounds, τ to ±60 s, f0 to the band. With a weak τ the
  time gate widens to 60 s.
- **Merging.** Optima that lie inside each other's v, k and τ ranges merge into one hypothesis with the wider
  ranges, so they count once against B2.
- **Admission.** A row is admitted for an event when some hypothesis holds its speed and its v²/d. Each
  candidate flight's own ground speed thereby gives the distance it implies.
- **Pairing and scoring.** Every pair of the two events' hypotheses is joined at its own time offset, with
  today's heard convention and ±6 s gate. Each triple is scored with its event-1 hypothesis's heard CPA as
  the clock anchor, and with an f0 sweep widened to the hypotheses' f0 ranges.
- **Band.** For each event, 0.85 f_post to 1.15 f_pre of its fit.

**Knobs**, counted: K = 3; the LS threshold 3.84 × 3; the brightness threshold 2 σ; the 20 s separation; the
coarse grid (`detect`'s); the bounds; τ's ±60 s reach; the band rule; the merge rule; OLS for the track fit.
One retune at most after the first run, counted.

**Scripts:**
- B1 and B2: [`hypotheses_b1b2.py`](../../tools/experiments/2026-11-04/hypotheses_b1b2.py).
- A1 and A3: [`event_pairs_z.py`](../../tools/experiments/2026-11-04/event_pairs_z.py) with
  `EVENT_PAIRS_HYPOTHESES=1`.

## Results

**A run stopped before it was read.** The first A1/A3 rerun (`runs/2026-11-04-hypotheses-pairs/`, from
`a50edfa`) was stopped two searches in and never read. An outside review found that the per-hypothesis-pair
joins kept each triple once, with the first pair's event-1 hypothesis. That hypothesis's heard CPA is the
clock the triple is scored at, so its score depended on hypothesis order. The null also scored wrong
flights over a narrower f0 sweep than the candidates got, which biases Z upward. Both are fixed in
`93a5c4d` (a test reproduces the first), and A1/A3 were rerun from it. The B1/B2 run (`a50edfa`) doesn't
score triples, so neither fix touches it, and it stands.

**B1 and B2, first run** (`runs/2026-11-04-hypotheses-b1b2/`, `a50edfa`): **not met.**

| Case, event | B1 (true flight admitted within 250 m) | admitted rows, against today's gates | hypotheses |
|---|---|---|---|
| Oyster Bay, 1 | yes, via fit_event | 673,107 / 16,722,629 | ls (v 80–101), fit_event (v 137–143) |
| Oyster Bay, 2 | **no**: true 103.5 m/s, k 2.99 | 257,529 / 13,292,417 | ls (v 86–91, k 3.31–4.09), fit_event (v 79–82, k 3.25–4.81) |
| degraded, 1 | **no**: v range 137–143 against true 136.8 | 633,396 / 16,692,860 | as Oyster Bay |
| degraded, 2 | **no** | 360,733 / 13,300,417 | as Oyster Bay |
| eagle cam, 1 | yes, via both sources | 289,456 / 6,912,926 | ls, fit_event |
| eagle cam, 2 | yes, via fit_event | **35,809,547 / 11,186,276** (B2 fails) | ls, fit_event, and a fit_event optimum weak in all four |

- **B1.** The ranges sit on the biased fit (E1) and are too narrow to reach the truth. Today's ±35 % box does reach it.
- **B2.** It fails only where one fit_event optimum, flat in every profile, widened to every bound and so
  admitted the whole table. Elsewhere the hypotheses admit 20–60× fewer rows than today.

**The one retune, written before its rerun** (agreed with the PM, counted). One change, in two parts:
1. **Thresholds scaled for model error.** A profile of a misspecified model measures spread about the
   model's best approximation, not distance to the truth (White 1982). SDE-D measured that distance at
   2.8–3.2× the information bound in slant range, on Livermore's trajectory curves
   ([model-error](2026-11-04-model-error.md)), not on these cases.
   - Taking the middle, a factor of 3, and the profile thresholds' quadratic scale, every parameter's
     threshold is multiplied by 3² = 9: LS 3.84 × 3 × 9 residual variances, brightness 2 × 9 null sigmas.
   - The ranges then are the "sensitivity ranges" PLAN calls them until the objective is a calibrated
     likelihood.
   The same threshold decides which of a source's optima are kept, so that scales too.
2. **The weak-hypothesis rule.** A hypothesis weak in v, k and τ together is dropped as uninformative. An
   event left with no hypotheses admits rows as today's gates do (±35 % speed, 0.4–2.5× distance).

**Expectation, before the rerun:**
- Oyster Bay event 2's fit_event range widens about 3× and reaches about 103 m/s, so B1 holds there.
- B2 keeps a wide margin everywhere.
- The degraded copy's event 1 is uncertain either way.
- The eagle cam's event 2 is handled by the weak-hypothesis rule.
- If B1 still fails on any event, stage B is recorded not met with no further change. The next lever is
  then item 2's turn model or item 8, not another factor.

The A1/A3 rerun from `45d0bd8` stands as the comparable-score result regardless. If the retune passes B1
and B2, A1/A3 run once more on the widened hypotheses, and both are reported.
