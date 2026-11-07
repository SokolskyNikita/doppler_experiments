# The recording's stated start time as a clock gate in `locate` (2026-11-04)

<!-- index
question: Does gating each pair's clock on the recording's stated start time reject the wrong clocks locate found, without losing a true pair?
outcome: Conditional development candidate recovery with emitted ambiguous verdicts; clock gate rejects tested wrong clocks, but success depends on weather/filter and does not establish calibrated location
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `11fb8c4c6f0e875c22ac18daedabcc3e647b0187ec37fbfc3411eb9026d07194`.

> **Research reset qualification, 2026-11-04.** “Located” in the narrative means a near-reference search
> candidate; emitted outcomes in these runs are ambiguous, without a calibrated verdict. At15°C the literal
> criterion that Oyster Bay remain found is not met; the favorable clock-gate conclusion uses no additional
> loss relative to the same-temperature baseline. Near-reference eagle winners under some settings use a
> different flight pair. These development results justify a conditional engineering gate/default decision,
> not a general location or false-positive-rate claim; see [the audit](2026-11-04-research-reset.md).

## Question

In `locate`'s Tier 2 run (`2026-11-04-locate.md`), every wrong answer on the eagle cam and the midnight clips came with a
clock hours away from the recording's known start. The eagle cam's stream metadata gives its start to 60 s, and
`locate` didn't use it. If each pair whose implied clock falls outside the stated start's tolerance is dropped, are the
wrong clocks rejected, is every true pair kept, and what do the eagle cam and the midnight cases end in?

## The gate

`locate.clock_gate`, applied to each search of each pair rule before a rule picks its pair. A triple's clock puts the
recording's start at `t_heard1 − t_cpa(event 1) − shift`; the triple is dropped when that is further from the stated
start than the stated tolerance plus the search's own time tolerance (`tol_s`, 6 s). A triple's score depends only on
its own events, flights and clock, and comparable's Z on each event's own null, so dropping triples after scoring
leaves exactly the candidates a gate before scoring would; the gate sits in `locate`'s search wrapper, not in
`pipeline.run_search`. The search's funnel records how many triples it kept.

The tolerance is data: each case's `start_time.utc` and `start_time.uncertainty_s` in `bench/cases.json`, set when the
case was made, with their source. What each case's files offer:

| Cases | Stated start | Tolerance | Source |
|---|---|---|---|
| `eagle-cam-clip-18000s` | 2024-12-28T19:21:16Z | 60 s | the stream's YouTube `release_timestamp`, plus the clip offset |
| `eagle-cam-midnight`, `-days0` | 2024-12-28T22:29:56Z | 60 s | the same, plus the clip offset |
| `xenocanto-xc990819` | 2025-04-20T04:10:00Z | 60 s | xeno-canto's recording time, local, to the minute |
| `oyster-bay` and its six variants | 2026-09-08T12:00:00Z | 43,200 s | the date only: colsto states no time |

So the gate can reject a wrong clock only on the four cases with a minute-level start. On the Oyster Bay family it
only keeps the clock inside the stated day.

`locate --start ISO --start-tolerance S` sets it from the command line; the benchmark's `locate` profile reads the
case's, and `--search-param clock_gate=false` turns it off.

## Criterion, written before the run

All ten `locate` cases run with the gate and locate's defaults (comparable, silence filter on), at the commit that adds
the gate. The gate passes if:

1. no true pair is dropped: Oyster Bay and its degraded copy are still found (true pair first, refined within 2 km),
   and on the eagle cam the true pair's clock, the case's reference clock 19:21:13.29Z, lies 2.7 s from the stated
   start, inside the gate;
2. every wrong clock the Tier 2 record shows on a case with a minute-level start is rejected: the eagle cam's
   (17:14:41Z and 19:15:50Z against 19:21:16Z), the midnight cases' (15:00:49Z, 21:51:09Z and 23:57:09Z against
   22:29:56Z) and Essex's (15:46:30Z against 04:10:00Z), so none of those clocks appears in any record.

Then the eagle cam's and the midnight cases' outcomes are read and reported as they come, with no pass or fail on
them: found, a different wrong pair inside the gate, or `no_surviving_candidate`.

**Conditions, added before the run's other shards (after its smoke shard).** The smoke shard (Oyster Bay and the
cut-short case, `runs/2026-11-04-locate-gate-s4of5/`) ran at 15 °C. Since the Tier 2 runs, the geometry study’s change made a case's
station temperature apply only when a run asks for it (`bench run --weather`), and the Tier 2 finds were made with it
(Oyster Bay at 25.6 °C, each flight's own speed from its height). At 15 °C Oyster Bay's comparable search ranks the true
pair third (the winner, a26f86 + a77707, scores 17.98), with the gate keeping the whole stated day. So the gate is judged
against Tier 2 at Tier 2's conditions: all ten cases with `--weather`, criterion as above. The 15 °C reading is reported
beside it, since it says the Tier 2 find depends on the station temperature.

**Both settings, added before the 15 °C runs (review, 2026-11-04).** Weather stays off by default, so the gate and
locate's two new defaults are judged at both settings. At the station temperature: `locate-gate-w` (the gate,
locate's defaults, `--weather`). At 15 °C: `locate-gate-15` (the gate, `--pair-rule both`, the filter on) and
`locate-15-off` (the same with the filter off); `both` refines comparable's answer and reports top2's beside it. The
gate is judged at each setting by the criterion above. The defaults are judged at 15 °C by the Tier 2 record's
criteria 3 and 4 (comparable finds more seed cases than top2 and loses none; the filter on finds more and loses none,
with the negatives still unlocated), with the gate on in all of them. If either fails at 15 °C, that is reported with
the numbers for review to decide, not applied by rule.

## Results

Three runs of all ten cases with the gate, at 894b27c and db398cd (the same locate code), five boxes each, two cases per
box: the station temperature with locate's defaults (`runs/2026-11-04-locate-gate-w-merged/`), and 15 °C with
`--pair-rule both`, the filter on (`-gate-15-merged/`) and off (`-15-off-merged/`). "Clock gate kept" counts the
triples the chosen search kept; "Outside gate" counts candidates whose clock is outside the stated start's tolerance
plus 6 s (it must be 0). From `tools/experiments/2026-11-04/locate_tier2.py`, after every record's hash:

| Run | Case | Verdict | Expected | True-pair rank | Top (km) | Refined (km) | top2 pick | comparable pick | top2 / comparable (s) | Start (UTC) | Clock gate kept | Outside gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| weather-on | eagle-cam-clip-18000s | ambiguous winner_only_refined | – | none of 5 | 0.86 | 0.33 | – | a13d1e + a2baea | 361 | 19:21:01Z | 508 of 55,016 | 0 |
| weather-on | oyster-bay-moved-north150 | ambiguous winner_only_refined | – | – of 86 | 135.49 | 135.49 | – | a1d3d1 + a88f95 | 208 | 13:00:04Z | 8,398 of 8,398 | 0 |
| weather-on | eagle-cam-midnight | insufficient_evidence no_surviving_candidate | – | – of 0 | – | – | – | unavailable | 157 | – | 0 of 1,939 | – |
| weather-on | oyster-bay-moved-wsw150 | ambiguous winner_only_refined | – | – of 148 | 118.06 | 117.48 | – | ad0d9d + a2311a | 368 | 12:35:25Z | 8,641 of 8,808 | 0 |
| weather-on | eagle-cam-midnight-days0 | insufficient_evidence no_surviving_candidate | **no** | – of 0 | – | – | – | unavailable | 139 | – | 0 of 824 | – |
| weather-on | oyster-bay-sources-removed | ambiguous winner_only_refined | – | – of 373 | 77.39 | 77.56 | – | a26f86 + a77707 | 429 | 11:59:48Z | 23,357 of 24,251 | 0 |
| weather-on | oyster-bay | ambiguous winner_only_refined | – | 1 of 381 | 0.18 | 0.28 | – | **true pair** | 527 | 20:17:30Z | 24,163 of 25,057 | 0 |
| weather-on | oyster-bay-traces-end-early | insufficient_evidence flight_data_missing_time | yes | – of 0 | – | – | – | – | – | – | – | – |
| weather-on | oyster-bay-hp150-aac32k | ambiguous winner_only_refined | – | 1 of 381 | 0.18 | 0.28 | – | **true pair** | 516 | 20:17:30Z | 24,050 of 24,940 | 0 |
| weather-on | xenocanto-xc990819 | insufficient_evidence no_surviving_candidate | – | – of 0 | – | – | – | unavailable | 214 | – | 0 of 1,656 | – |
| 15C-on | eagle-cam-clip-18000s | ambiguous winner_only_refined | – | 1 of 1 | 0.92 | 0.39 | unavailable | **true pair** | 28 / 374 | 19:21:13Z | 392 of 50,706 | 0 |
| 15C-on | oyster-bay-moved-north150 | ambiguous winner_only_refined | – | – of 97 | 135.49 | 135.50 | a1d3d1 + a88f95 | a1d3d1 + a88f95 | 26 / 218 | 13:00:04Z | 7,946 of 7,946 | 0 |
| 15C-on | eagle-cam-midnight | insufficient_evidence no_surviving_candidate | – | – of 0 | – | – | unavailable | unavailable | 25 / 146 | – | 0 of 1,939 | – |
| 15C-on | oyster-bay-moved-wsw150 | ambiguous winner_only_refined | – | – of 263 | 98.89 | 98.42 | a6b42a + a16cac | ae202c + ab31d7 | 46 / 519 | 16:45:53Z | 11,778 of 11,785 | 0 |
| 15C-on | eagle-cam-midnight-days0 | insufficient_evidence no_surviving_candidate | **no** | – of 0 | – | – | unavailable | unavailable | 20 / 134 | – | 0 of 824 | – |
| 15C-on | oyster-bay-sources-removed | ambiguous winner_only_refined | – | – of 431 | 77.47 | 77.49 | a26f86 + a77707 | a26f86 + a77707 | 63 / 463 | 11:59:48Z | 18,151 of 18,605 | 0 |
| 15C-on | oyster-bay | ambiguous winner_only_refined | – | 3 of 439 | 77.47 | 77.49 | a26f86 + a77707 | a26f86 + a77707 | 70 / 555 | 11:59:48Z | 18,709 of 19,163 | 0 |
| 15C-on | oyster-bay-traces-end-early | insufficient_evidence flight_data_missing_time | yes | – of 0 | – | – | – | – | – | – | – | – |
| 15C-on | oyster-bay-hp150-aac32k | ambiguous winner_only_refined | – | 6 of 436 | 77.47 | 77.61 | a26f86 + a77707 | a26f86 + a77707 | 66 / 402 | 11:59:48Z | 18,688 of 19,141 | 0 |
| 15C-on | xenocanto-xc990819 | insufficient_evidence no_surviving_candidate | – | – of 0 | – | – | unavailable | unavailable | 18 / 203 | – | 0 of 1,513 | – |
| 15C-off | eagle-cam-clip-18000s | ambiguous winner_only_refined silence_filter_off | – | none of 3 | 0.59 | 0.35 | a68cab + a2baea | a68cab + a2baea | 53 / 637 | 19:21:03Z | 401 of 42,834 | 0 |
| 15C-off | oyster-bay-moved-north150 | ambiguous winner_only_refined silence_filter_off | – | – of 132 | 135.49 | 135.50 | a1d3d1 + a88f95 | a1d3d1 + a88f95 | 28 / 244 | 13:00:04Z | 12,757 of 12,757 | 0 |
| 15C-off | eagle-cam-midnight | ambiguous winner_only_refined silence_filter_off | – | – of 1 | 3.58 | 3.94 | a6b714 + aa1ed4 | a6b714 + aa1ed4 | 39 / 260 | 22:30:30Z | 7 of 14,008 | 0 |
| 15C-off | oyster-bay-moved-wsw150 | ambiguous winner_only_refined silence_filter_off | – | – of 727 | 133.16 | 133.14 | a7c80c + a958d8 | a7c80c + a958d8 | 85 / 1536 | 17:27:23Z | 50,431 of 51,715 | 0 |
| 15C-off | eagle-cam-midnight-days0 | insufficient_evidence no_surviving_candidate | **no** | – of 0 | – | – | unavailable | unavailable | 32 / 213 | – | 0 of 12,221 | – |
| 15C-off | oyster-bay-sources-removed | ambiguous winner_only_refined silence_filter_off | – | – of 1020 | 79.94 | 79.37 | a26f86 + a77707 | ab050a + aa9b54 | 138 / 1420 | 12:08:58Z | 88,698 of 90,730 | 0 |
| 15C-off | oyster-bay | ambiguous winner_only_refined silence_filter_off | – | 19 of 1736 | 77.47 | 77.49 | a26f86 + a77707 | a26f86 + a77707 | 172 / 1862 | 11:59:48Z | 128,055 of 132,348 | 0 |
| 15C-off | oyster-bay-traces-end-early | insufficient_evidence flight_data_missing_time | yes | – of 0 | – | – | – | – | – | – | – | – |
| 15C-off | oyster-bay-hp150-aac32k | ambiguous winner_only_refined silence_filter_off | – | 26 of 1730 | 77.47 | 77.61 | a26f86 + a77707 | a26f86 + a77707 | 136 / 995 | 11:59:48Z | 127,753 of 132,150 | 0 |
| 15C-off | xenocanto-xc990819 | insufficient_evidence no_surviving_candidate | – | – of 0 | – | – | unavailable | unavailable | 22 / 229 | – | 0 of 5,826 | – |

- **Eagle cam.** Located at every setting once the gate is on: refined 0.33 km (station temperature), 0.39 km (15 °C,
  filter on) and 0.35 km (15 °C, off) from the nest, against 54–71 km without the gate. The gate keeps under 1 % of the
  triples (392–508 of 42,834–55,016), the ones whose clock agrees with the stream's start. At 15 °C with the filter on
  the only survivor is the true pair, a2baea + a336e4, whose clock gives 19:21:13Z, the reference clock to 0.1 s. At the
  other two settings the winner pairs a2baea with another flight (a13d1e, a68cab), in the right place.
- **Oyster Bay.** The gate can only keep the stated day here, so it changes little: found at the station temperature
  (true pair first, 278 m, as in Tier 2), not at 15 °C (true pair 3rd and 6th with the filter on, 19th and 26th off;
  the winner a26f86 + a77707 is 77 km off).
- **The midnight cases.** No pair's clock survives on `eagle-cam-midnight-days0` at any setting, so it ends at
  `no_surviving_candidate`, not `past_utc_midnight`: with one day of flight data, a pair from before midnight would have
  to explain events in a recording that is mostly after it. `eagle-cam-midnight` (both days) ends there too, except at
  15 °C with the filter off, where 7 triples survive and the winner is 3.9 km off with a clock of 22:30:30Z.
- **Essex** ends at `no_surviving_candidate` at every setting: none of its 1,513–5,826 triples, all from jets and wrong
  clocks, has a clock within a minute of the recording's time. The negatives stay 98–135 km off.

## Outcome

- **The gate passes at both settings.** No true pair is dropped: Oyster Bay keeps its find at the station temperature,
  and at 15 °C the gate is what lets the eagle cam's true pair through, first and alone. Every wrong clock from the
  Tier 2 record is gone: no candidate in any of the 30 records lies outside its gate.
- **locate's defaults hold at 15 °C with the gate.** Pair rule (criterion 3): comparable finds the eagle cam with the
  filter on; top2 finds no seed case at either filter setting (its eagle-cam search keeps no candidate, its Oyster Bay
  pick is the 77 km pair). Silence filter (criterion 4): on finds the eagle cam, off finds no seed case, and the
  negatives stay unlocated. Both defaults stand at the benchmark's present setting, so nothing is put to review here.
- **What it means for step A.** With the gate, step A locates one recording of two at each setting, but not the same
  one: Oyster Bay at the station temperature, the eagle cam at 15 °C (true pair) and to 0.33–0.39 km at every setting.
  That one recording's find flips with the speed of sound is the ill-conditioned event fit the geometry study traced, now seen from
  automatic events too. The midnight check still never fires on these clips: the gate leaves no pair to give it a
  clock past midnight.

## Files

`src/dopplertrack/locate.py` (`clock_gate`), `src/dopplertrack/cli.py` (`--start`, `--start-tolerance`),
`bench/runner.py` (the profile reads the case's start), `tests/test_locate.py`.
Script: `tools/experiments/2026-11-04/locate_tier2.py` (the table; `table-all.md` in `runs/2026-11-04-locate-15-off-merged/`).
Runs: `runs/2026-11-04-locate-gate-w-merged/`, `-gate-15-merged/`, `-15-off-merged/` (merged from their
`-s{1..5}of5` shards); the 15 °C smoke shard `runs/2026-11-04-locate-gate-s4of5/`; launches in
`runs/2026-11-04-sde-b-fleet-launch/command.txt`.
