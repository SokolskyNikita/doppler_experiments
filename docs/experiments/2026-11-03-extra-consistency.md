# Does a candidate explain the other flyovers? (2026-11-03)

<!-- index
question: Can the flyovers a search didn't use tell the true flight pair from wrong ones?
outcome: A lead: with a ±15 s time gate, only the true pair explained any
-->

**Question.** Can the flyovers a search didn't use tell the true flight pair from wrong ones, as a basis for confidence (PLAN Phase 4)?

**Setup, on Oyster Bay** (development data):
- a blind search with the committed event fits, taking the top 10 flight pairs (rank 1 is the true pair);
- 8 extra events: those from `detect --top 10` other than the two search events;
- at each pair's best point, find a flight that explains each extra event and score its modelled curve, using the same time shift as event 1 and a propeller-tone scale of 0.95–1.05;
- an extra counts as explained at a score of 3 or more.

| Rule for the explaining flight | True pair | Wrong pairs (9) |
|---|---|---|
| any flight within 12 km and ±5 min (what `pick_flight` does) | sum 36.9 | up to 41.1; three of them at 35 or more |
| heard closest approach within ±6 s | 1 explained (4.7) | none explained (max sum 2.5) |
| within ±15 s | **2 explained (6.7, 4.7)** | **none explained (max sum 2.8)** |
| within ±30 s | 2 explained | two pairs explain 1 each (sums 6.6 and 6.3) |
| ±15 s plus `detect`'s speed and distance gates | none | none |

Separately, the robust z-score of each pair's best score against all 328 pairs is 4.2 for the true pair and 3.9 for the runner-up. Statistics from a single search don't separate them.

**Outcome: a lead, not a result.** It is one recording and ten candidates.
- **The time gate.** It is what makes extra flyovers informative, and ±15 s worked best of the windows tried. It was picked on this recording, so it stays a development hypothesis until it holds on recordings it wasn't chosen on.
- **`detect`'s parameters.** Its speed and distance are too unreliable to gate on, the same problem PLAN Phase 2 targets.
- **Detection quality.** Only 2 of 8 extras matched, so better detection feeds directly into confidence. The extras weren't checked by eye, so some may not be aircraft at all.
- **Comparisons across pairs.** All ten pairs came from one search and were scored on the same extras. Comparing candidates from different pairs needs that same footing (PLAN Phase 3).

**Script:** `extra_consistency.py`. **Outputs:** `runs/2026-11-03-extra-consistency/`, a rerun with hashed inputs, `command.sh` and `run.json` that reproduces these tables exactly.
