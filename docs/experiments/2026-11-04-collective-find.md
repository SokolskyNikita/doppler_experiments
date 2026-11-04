# The collective find on the development cases (2026-11-04)

<!-- index
question: Does the collective find (every detected window against every flight's own heard curve, summed non-coherently with a floor) locate the development recordings, and keep the negatives below the verdict null?
outcome: (pending)
-->

**Question.** The design is [the collective-find proposal](../proposals/2026-11-04-collective-find.md), accepted by the PM.

**Why drop the event fit.** The case is in [event-fit](2026-11-04-event-fit.md): the brightness objective's flat v–d ridge, and finds that are the true flights' lines bent into a straight-pass shape. There is independent evidence from C's window round 2 ([window-round2](2026-11-04-window-round2.md)).
- **Brightness is bimodal on synthetic passes.** On delay-synthesised straight passes at amplitude 0.03, `fit_event`'s brightness objective lands within about 0.5 % or 20–80 % off, about half the time each, under every window tried. C0's 1,500 m pass gives v errors of 21 %, 0.2 % and 68 % over three seeds.
- **Contrast stays at or under 2.3 %** in v and d.

So a single brightness fit was never a safe find, even on straight passes. Does it meet the proposal's criteria, which were fixed before this run?

**What runs** (`src/dopplertrack/collective.py`; `tools/experiments/2026-11-04/collective_run.py`; fleet, one (case, f0 sweep) per 4xlarge box; 15 °C, the weather off).
- **Detection,** locate's: 60–300 Hz, harmonics 1, top 10, 240 s windows. Its usable windows, the top 10 by score, keep only their bounds, coarse tone and coarse heard CPA.
- **Coarse to fine.** This is the proposal's section 4 as corrected to the PM before the build: its cost bound counted the time-joined triples after today's speed and distance gates, which the design drops.
  - **Coarse:** a 2 km grid with its own CPA table. Each cell is scored as the maximum over its span, with the residual shift ±14 s at 2 s and the f0 sweep ±12 % at 2 %, on 60 samples.
  - **Fine:** a 200 m grid inside the coarse cells with Z ≥ 0.7 of the coarse maximum, with the shift ±8 s at 0.5 s and the f0 sweep ±10 % at 0.5 %, on 160 samples.
- **The clock vote:** clocks binned at 20 s, keeping a (row, window) when its bin and the two beside it hold at least two windows.
- **The sum:** windows add at a point where their best clocks agree within ±6 s (bins of 3 s, ±2 bins).
- **The normalisation:** each window's z is against its own null, 1,000 CPA rows drawn uniformly, anchored on its coarse CPA, with the same sweep.
- **Not enforced:** "one window per pass". The record reports any pass matched twice.
- **The PM's note (1):** the positives run a second time with the f0 sweep at ±5 %, so that the record can say which change did what.

**A design step, recorded before the rerun: the top 5 coarse cells.** The first run's fine stage kept every coarse cell with Z ≥ 0.7 of the coarse maximum.
- That is 141 cells on north150, a negative, against 12–16 on the positives, and it made the fine stage take 1,400–6,300 s.
- The rerun keeps the top 5 coarse cells by Z instead. k = 5 is fixed now, not tuned.
- The own-day cases rerun with it, and the other-day null for Z is drawn only on that search.
- The first run's results (commit a002696) are reported as the superseded configuration.

**The f0 sweep is load-bearing.** The eagle cam is found at ±10 % and lost at ±5 %: in the first run, ±5 % left a2baea unmatched. So the wider sweep is a change in its own right. The collective find is judged at ±10 %, and the ±5 % result is reported beside it.

**Cases.**
- Positives: oyster-bay, oyster-bay-hp150-aac32k, eagle-cam-clip-18000s, eagle-cam-midnight.
- Negatives: oyster-bay-moved-wsw150, oyster-bay-moved-north150, oyster-bay-sources-removed, xenocanto-xc990819.

**Criteria (the proposal's, fixed before the run).**
1. Each positive's maximum lies within 2 km of the truth, and its matched set (windows with z > 0 at the winning point and clock) includes both true flights.
2. eagle-cam-midnight's winning clock puts the recording on the right UTC day.
3. Each negative's maximum stays below A's verdict null for Z.
4. Each positive's search fits Tier 2's budget, 2–3 min per case on a 4xlarge, with its CPA table warm.

One counted retune is allowed, of the clock vote's cluster width.

**The eagle cam's event 2,** the weak window, is reported explicitly: its z at the winning clock, and whether the maximum lands within 2 km while it contributes nothing.

**From the first run, said plainly.** The eagle cam at ±10 % is the first time any method has put both true flights in the matched set from automatic windows: 0.5 km from the nest, with the weak window contributing (a336e4 at z 1.96). But north150, a negative, reaches Z = 16.7 against the eagle cam's 17.2. So the sum alone is not yet a verdict, and A's null is what decides.

**Expectation, written before the run.**
- Oyster Bay and its copy pass 1, with event 2 matched through ace391's own curve.
- The eagle cam passes 1 only if its event 2's window earns z > 0 at the true clock, or if another window carries a336e4. I expect the latter to be unlikely, so it may land with a2baea and some other window.
- The runtime is the open risk: the coarse stage's candidates are unbounded by any speed or distance gate.
- **Against the verdict null, written before it is drawn.** A's saved-fit arm isn't met: against 50 other days' traffic, the eagle cam's own-day best pair Z (8.60) sits at the null's median, Oyster Bay's (19.96) is beaten by 3 of 50 days, and the WSW negative's best wrong answer (17.88) looks like Oyster Bay's truth.
  - The statistic that has separated the eagle cam's true candidate from its 14.6 km rival is the frozen-clock count of extra flyovers, and Z summed over all windows at one clock generalises it. So it is the statistic with a chance.
  - The two negatives already finished reach Z = 12.7 and 16.7, against the eagle cam's 17.2. So I expect the collective Z's own-day maxima to sit in the upper part of the other-day null at best, and not to clear γ on the eagle cam.
  - If it doesn't clear, the record says so, and the evidence, not the threshold, is what gets rethought.

## A known-answer suite: turning and climbing passes (written before the run)

**Question.** Is the collective find's gain specific to non-straight trajectories, the claim PLAN's conclusion now makes, or general?

**What runs** (`tools/experiments/2026-11-04/synth_suite.py`; one case per 4xlarge box).
- **The recordings.** Twelve synthetic 30 min recordings, 4 kHz, white noise of std 0.4, heard by an observer at 40.78 N, 73.40 W, ground level, from 2026-09-08 19:00 UTC.
- **The passes.** Each recording holds three target passes, each a tone with a second harmonic at half amplitude:
  - 110 Hz, 120 m/s, 3.5 km horizontal offset, 1.2 km up, heard about 450 s in;
  - 125 Hz, 100 m/s, 4.5 km, 1.5 km, about 1,000 s;
  - 140 Hz, 140 m/s, 5.5 km, 1.0 km, about 1,500 s.
  That is 3.7–5.6 km slant range.
- **The shapes.**
  - straight;
  - **turn:** a 25° heading change, linear over ±60 s about the CPA;
  - **climb:** 300 m, linear over ±60 s;
  - **both.**
- **The amplitudes:** 0.02, 0.03 and 0.05.
- **The competitors.** The real 2026-09-08 Oyster Bay traffic (`derived/traces/2026-09-08/ny_margin12_v2.npz`), with the three synthetic flights added. Real flights are silent competitors.
- **The search.** A sub-box of ±0.18° latitude and ±0.22° longitude about the observer, 200 m, the DEM off.
- **Each case runs two ways:**
  - `locate` with the `comparable` pair rule (detect, fit_event, ten pair searches, refine);
  - the collective find (as above, ±10 % f0) on the same detections.

**Criterion, fixed before the run.**
1. **The non-straight cases (turn, climb, both).** On every one where the pair rule's fit lands in a wrong basin, the collective find's maximum is within 2 km of the observer. A wrong basin is a chosen event's straight-pass v or d more than 20 % from its synthetic pass's truth, matched by heard CPA within 30 s; an event matching no synthetic pass counts too.
2. **The straight controls.** The collective find is no worse: within 2 km wherever the pair rule's refined point is.

**Decision line.**
- **The gain is specific to non-straight passes** if 1 holds, the pair rule fails mainly on the non-straight cases, and both are within 2 km on the straight controls.
- **It is general** if the pair rule also fails on straight controls that the collective find gets.

**Expectation.**
- The pair rule lands in wrong basins on most turn and both cases at every amplitude, and on some straight ones at 0.02. C's window round 2 found brightness bimodal even on straight synthetic passes, though `detect` and locate's ten searches use contrast.
- The collective find is within 2 km on all cases at 0.05 and 0.03, and on some at 0.02.
