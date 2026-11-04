# The recording's stated start time as a clock gate in `locate` (2026-11-04)

<!-- index
question: Does gating each pair's clock on the recording's stated start time reject the wrong clocks locate found, without losing a true pair?
outcome: Pending: the criterion below was written before the run
-->

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
cut-short case, `runs/2026-11-04-locate-gate-s4of5/`) ran at 15 °C. Since the Tier 2 runs, SDE-D's change made a case's
station temperature apply only when a run asks for it (`bench run --weather`), and the Tier 2 finds were made with it
(Oyster Bay at 25.6 °C, each flight's own speed from its height). At 15 °C Oyster Bay's comparable search ranks the true
pair third (17.98 against 18.0+ for the winner), with the gate keeping the whole stated day. So the gate is judged
against Tier 2 at Tier 2's conditions: all ten cases with `--weather`, criterion as above. The 15 °C reading is reported
beside it, since it says the Tier 2 find depends on the station temperature.

**Both settings, added before the 15 °C runs (PM, 2026-11-04).** Weather stays off by default, so the gate and
locate's two new defaults are judged at both settings. At the station temperature: `locate-gate-w` (the gate,
locate's defaults, `--weather`). At 15 °C: `locate-gate-15` (the gate, `--pair-rule both`, the filter on) and
`locate-15-off` (the same with the filter off); `both` refines comparable's answer and reports top2's beside it. The
gate is judged at each setting by the criterion above. The defaults are judged at 15 °C by the Tier 2 record's
criteria 3 and 4 (comparable finds more seed cases than top2 and loses none; the filter on finds more and loses none,
with the negatives still unlocated), with the gate on in all of them. If either fails at 15 °C, that is reported with
the numbers for the PM to decide, not applied by rule.

## Results

Pending.

## Outcome

Pending.

## Files

`src/dopplertrack/locate.py` (`clock_gate`), `src/dopplertrack/cli.py` (`--start`, `--start-tolerance`),
`bench/runner.py` (the profile reads the case's start), `tests/test_locate.py`.
