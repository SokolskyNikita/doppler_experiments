# Choosing the two search events by search score (2026-11-04)

<!-- index
question: Does the search's own score pick the right two events from detect's top five?
outcome: No: on the eagle cam the true pair ranks 5th of 10, behind pairs with the loudest detection, so event choice needs item 7's joint hypotheses
-->

## Question

On the eagle-cam clip the two true flyovers are already among detect's top five (its ranks 2 and 5, within
0.03 s of the saved events), and the raw-audio profile loses only by taking ranks 1 and 2. If every pair of the
top five is searched, does the search's own score pick the true pair?

**Criterion, fixed before the run:** the test is informative if, on the eagle cam, the true pair's search score
ranks first among the ten. If it doesn't, event choice can't yet be a comparison of search scores, and PLAN
Phase 2 item 7's joint hypotheses are needed first.

## Setup

- Detections: the raw-audio baseline's `detected.json` at 5314396 for each case. The five highest-scoring
  detections make ten pairs, earlier event first.
- Each pair runs through the benchmark runner as its own variant case, with the case's gates and cached CPA table,
  harmonics (1, 1) as in the raw-audio profile (a detected event's harmonic is unknown), run_search at one worker,
  two variants at a time, on a loaded machine.
- Cases: eagle-cam-clip-18000s, oyster-bay, and the WSW moved-box negative (the same Oyster Bay detections).
- Blind order: the 30 records were written and hashed, then each case's ten were ranked by the search's top score
  and that ranking written and hashed (`ranking.json`, sha256 f2e1a331…) before any label was read. Only then were
  the true pairs and the errors added (`reveal.json`).
- Commit c378ea6, clean tree; 2,279 s wall in all, 27–586 s per search.

## Results

Ranked by the search's top score; "true pair" is its rank among that search's flight pairs.

**Eagle-cam clip** (true events: detect ranks 2 and 5)

| Rank | Events (detect ranks) | Top score | Margin | Flight pairs | Top error | True pair |
|---|---|---|---|---|---|---|
| 1 | 1 + 2 | 11.58 | 0.96 % | 108 | 54.3 km | absent |
| 2 | 1 + 4 | 10.87 | 4.80 % | 171 | 22.9 km | absent |
| 3 | 4 + 2 | 10.40 | 1.25 % | 730 | 35.3 km | absent |
| 4 | 1 + 5 | 10.32 | 0.56 % | 169 | 69.4 km | absent |
| **5** | **2 + 5** | **10.27** | **2.49 %** | 609 | **1.05 km** (refined 1.01 km) | **1st, within 85 m of the nest** |
| 6 | 1 + 3 | 10.17 | 2.27 % | 30 | 56.6 km | absent |
| 7 | 2 + 3 | 9.64 | 4.13 % | 62 | 71.8 km | absent |
| 8 | 5 + 3 | 8.68 | 5.61 % | 158 | 43.2 km | absent |
| 9 | 4 + 5 | 8.48 | 1.02 % | 811 | 18.7 km | absent |
| 10 | 4 + 3 | 8.24 | 3.48 % | 69 | 64.1 km | absent |

**Oyster Bay** (detect's ranks 1 and 2 are the README's two flyovers)

| Rank | Events | Top score | Margin | Flight pairs | Top error | True pair |
|---|---|---|---|---|---|---|
| **1** | **1 + 2** | **17.91** | 5.91 % | 448 | 77.5 km | **10th; nearest scored triple 354 m from the truth** |
| 2 | 1 + 5 | 16.84 | 1.07 % | 238 | 83.4 km | absent |
| 3 | 4 + 1 | 16.74 | 9.67 % | 117 | 59.5 km | absent |
| 4 | 4 + 3 | 15.75 | 4.22 % | 1,776 | 23.7 km | absent |
| 5 | 3 + 1 | 15.59 | 1.32 % | 353 | 77.5 km | absent |
| 6–10 | the rest | 15.56–13.02 | 0.27–6.35 % | 52–1,271 | 4.8–78.0 km | absent |

**WSW moved-box negative**: every pair returns an answer 92–228 km from the truth, with margins of 0.13–13.21 %. The
top one, events 1 + 2, wins by 13.21 %, more than any true positive here.

## Outcome

**The criterion fails: on the eagle cam the true pair's search ranks 5th of 10.** Four wrong event pairs score
higher, three of them with detect's rank 1, the loudest detection (score 6.92 against the true events' 4.94 and
3.65). So ranking candidate event pairs by their own search score picks the loudest events, not the right ones:
the scores of different pairs aren't on one scale, which is S2. Event choice can't be a score comparison until
Phase 2 item 7's joint hypotheses put them on one, and that is the result.

What the rule admits:
- **Where the true events are found, the search is right**: on the eagle cam the true pair's own search puts the
  true flight pair first, 1.05 km off, within 85 m of the nest at the scored stage. Event choice is the only
  failure there.
- **Where the true events win, the fit can still fail**: on Oyster Bay the right two events rank first by score,
  but detect's biased fit of event 2 (f0 +6 %) leaves the true flight pair 10th, and its nearest scored triple is
  354 m from the truth, outside the 250 m near-reference test. That is the fit and gate problem of items 1 and 4,
  not event choice.
- **Where there is no true answer, every pair answers**: the moved box's ten searches all name a location, with
  margins up to 13.2 %. Trying more pairs adds more confident wrong answers, which only a verdict (Phase 4) can
  refuse.

## Files

- Script: `tools/experiments/2026-11-04/event_pairs.py`.
- Run: `runs/2026-11-04-event-pairs/` (`plan.json`, `cases.json` with the 30 variants, one folder per variant with
  its hashed record, `ranking.json` and its hash, `reveal.json`, `driver.log`).
