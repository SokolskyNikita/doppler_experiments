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

**Expectation, written before the run.**
- Oyster Bay and its copy pass 1, with event 2 matched through ace391's own curve.
- The eagle cam passes 1 only if its event 2's window earns z > 0 at the true clock, or if another window carries a336e4. I expect the latter to be unlikely, so it may land with a2baea and some other window.
- The runtime is the open risk: the coarse stage's candidates are unbounded by any speed or distance gate.
