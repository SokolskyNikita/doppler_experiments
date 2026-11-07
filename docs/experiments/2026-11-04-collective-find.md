# The collective find on the development cases (2026-11-04)

<!-- index
question: Does the collective find (every detected window against every flight's own heard curve, summed non-coherently with a floor) locate the development recordings, and keep the negatives below the verdict null?
outcome: Partial development evidence only: v3 Oyster Bay has a 318 m cell0 candidate with both true flights, no all-kept-cell winner or matched null; eagle regresses, v4 unmeasured
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `9f9c7e3eec91d4eb40ab481cd9598863d9cd787019b16f3b6996f9a35eff1a87`.

> **Research reset correction, 2026-11-04.** “Found” below describes selected search candidates, not a
> passed locator or verdict criterion. The v2 fine merge is incomplete (nine of 120 non-Oyster extra-cell
> units missing); v3's saved merge contains only cell0's fine result for each of eight cases. Oyster Bay's 318
> m v3 candidate is therefore not the winner over all retained cells. The v3 eagle candidate fails the
> true-flight requirement, and v4 has no completed local result. The pulled 84 other-day draws use v1's 2
> km/top5/±10% statistic, not v2/v3/v4; no matching collective verdict was established. Their local folders
> contain result.json but lack the null_draws.npz consumed by the current judge. Claims that “their nulls
> priced” later changes are conditional design statements, not completed calibration. Successive
> margin/tone/grid/subwindow/pass-rule changes are new designs, beyond the original single clock-width retune.
> See [the audit](2026-11-04-research-reset.md).

**Where it stands: located by the search, not yet by the verdict.**
- **Oyster Bay.** Under the third design step (a 1 km coarse grid, each window scored over its best 120 s stretch, each candidate's tone over ±25 %), Oyster Bay's true cell is the coarse map's maximum, rank 1 of 15,253. The top cell's fine winner is 0.3 km from the truth, with both true flights matched.
- **The eagle cam** was found at 0.5 km with both flights under the earlier designs.
- **A wrong box nearly ties it.** oyster-bay-moved-wsw150, a moved box with no true flight, reaches a coarse maximum of 18.22, against Oyster Bay's 18.50. So the collective Z at this site has a wrong-box ceiling near 18.
  - "Found at rank 1" is the search's result, not a claim.
  - oyster-bay-hp150-aac32k is the cleaner positive: rank 1, with only 4 cells inside the margin.
- **The eagle cam regressed** under the third design, from 2nd to 37th, outside the margin. The true-point diagnostic says whether the fixed 120 s stretch cost it. If it did, the stretch becomes per-window, the line's own extent from the detector (PLAN item 6).
- **Not yet a claim.** Only the other-day null on the collective Z can say whether 18.50 clears that ceiling, and it hasn't been drawn for this statistic yet.
- **Open:** ace391's weak window (z 0.62), now a detector-window question (PLAN item 6).

The sections below follow the work in order: the first design, the second, the diagnostics that split their faults, and the third.

**Question.** The design is [the collective-find proposal](designs/2026-11-04-collective-find.md), accepted by review.

**Why drop the event fit.** The case is in [event-fit](2026-11-04-event-fit.md): the brightness objective's flat v–d ridge, and finds that are the true flights' lines bent into a straight-pass shape. There is independent evidence from the window study’s round 2 ([window-round2](2026-11-04-window-round2.md)).
- **Brightness is bimodal on synthetic passes.** On delay-synthesised straight passes at amplitude 0.03, `fit_event`'s brightness objective lands within about 0.5 % or 20–80 % off, about half the time each, under every window tried. C0's 1,500 m pass gives v errors of 21 %, 0.2 % and 68 % over three seeds.
- **Contrast stays at or under 2.3 %** in v and d.

So a single brightness fit was never a safe find, even on straight passes. Does it meet the proposal's criteria, which were fixed before this run?

**What runs** (`src/dopplertrack/collective.py`; `tools/experiments/2026-11-04/collective_run.py`; fleet, one (case, f0 sweep) per 4xlarge box; 15 °C, the weather off).
- **Detection,** locate's: 60–300 Hz, harmonics 1, top 10, 240 s windows. Its usable windows, the top 10 by score, keep only their bounds, coarse tone and coarse heard CPA.
- **Coarse to fine.** This is the proposal's section 4 as corrected to review before the build: its cost bound counted the time-joined triples after today's speed and distance gates, which the design drops.
  - **Coarse:** a 2 km grid with its own CPA table. Each cell is scored as the maximum over its span, with the residual shift ±14 s at 2 s and the f0 sweep ±12 % at 2 %, on 60 samples.
  - **Fine:** a 200 m grid inside the coarse cells with Z ≥ 0.7 of the coarse maximum, with the shift ±8 s at 0.5 s and the f0 sweep ±10 % at 0.5 %, on 160 samples.
- **The clock vote:** clocks binned at 20 s, keeping a (row, window) when its bin and the two beside it hold at least two windows.
- **The sum:** windows add at a point where their best clocks agree within ±6 s (bins of 3 s, ±2 bins).
- **The normalisation:** each window's z is against its own null, 1,000 CPA rows drawn uniformly, anchored on its coarse CPA, with the same sweep.
- **Not enforced:** "one window per pass". The record reports any pass matched twice.
- **The review's note (1):** the positives run a second time with the f0 sweep at ±5 %, so that the record can say which change did what.

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
3. Each negative's maximum stays below the verdict null for Z.
4. Each positive's search fits Tier 2's budget, 2–3 min per case on a 4xlarge, with its CPA table warm.

One counted retune is allowed, of the clock vote's cluster width.

**The eagle cam's event 2,** the weak window, is reported explicitly: its z at the winning clock, and whether the maximum lands within 2 km while it contributes nothing.

**From the first run, said plainly.** The eagle cam at ±10 % is the first time any method has put both true flights in the matched set from automatic windows: 0.5 km from the nest, with the weak window contributing (a336e4 at z 1.96). But north150, a negative, reaches Z = 16.7 against the eagle cam's 17.2. So the sum alone is not yet a verdict, and the null is what decides.

**Expectation, written before the run.**
- Oyster Bay and its copy pass 1, with event 2 matched through ace391's own curve.
- The eagle cam passes 1 only if its event 2's window earns z > 0 at the true clock, or if another window carries a336e4. I expect the latter to be unlikely, so it may land with a2baea and some other window.
- The runtime is the open risk: the coarse stage's candidates are unbounded by any speed or distance gate.
- **Against the verdict null, written before it is drawn.** the saved-fit arm isn't met: against 50 other days' traffic, the eagle cam's own-day best pair Z (8.60) sits at the null's median, Oyster Bay's (19.96) is beaten by 3 of 50 days, and the WSW negative's best wrong answer (17.88) looks like Oyster Bay's truth.
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
- The pair rule lands in wrong basins on most turn and both cases at every amplitude, and on some straight ones at 0.02. The window study’s round 2 found brightness bimodal even on straight synthetic passes, though `detect` and locate's ten searches use contrast.
- The collective find is within 2 km on all cases at 0.05 and 0.03, and on some at 0.02.

## The own-day rerun: the top 5 coarse cells (40454ae)

Twelve units on 12 spot 8xlarge boxes, the unit shards relaunched after spot interruptions at the same commit, merged into `runs/2026-11-04-collective-find-merge/` (`collective.json`, and `OWN.json` for the null). Each unit's result was written before any label was read.

| Case | Sweep | Z | Second mode ≥ 2 km off | Distance from truth | True flights matched | Fine stage |
|---|---|---|---|---|---|---|
| oyster-bay | ±10 % | 15.30 | 15.10 | 29.6 km | neither | 2,543 s |
| oyster-bay-hp150-aac32k | ±10 % | 18.38 | 15.08 | 61.1 km | neither | 2,215 s |
| eagle-cam-clip-18000s | ±10 % | 16.27 | 9.37 | **0.5 km** | **both** (a2baea z 4.95, a336e4 z 1.80) | 1,279 s |
| eagle-cam-midnight | ±10 % | 8.81 | 8.06 | 19.1 km | – | 977 s |
| oyster-bay-moved-wsw150 (−) | ±10 % | 19.30 | 17.36 | – | – | 1,571 s |
| oyster-bay-moved-north150 (−) | ±10 % | 10.37 | 9.91 | – | – | 340 s |
| oyster-bay-sources-removed (−) | ±10 % | 15.31 | 14.97 | – | – | 2,131 s |
| xenocanto-xc990819 (−) | ±10 % | 13.36 | 12.93 | – | – | 610 s |
| oyster-bay | ±5 % | 19.82 | 17.33 | 58.3 km | neither | 777 s |
| oyster-bay-hp150-aac32k | ±5 % | 21.51 | 21.22 | 58.5 km | neither | 728 s |
| eagle-cam-clip-18000s | ±5 % | 17.21 | 14.76 | 1.3 km | both (z 6.59, 2.44) | 816 s |
| eagle-cam-midnight | ±5 % | 10.10 | 9.50 | 23.5 km | – | 553 s |

**Against the criteria.** Criterion 3 waits for the verdict threshold γ; its draws are the other-day null below.
1. **Fails on Oyster Bay and its copy at both sweeps; holds on the eagle cam clip at both.** eagle-cam-midnight's winner is 19 km off.
2. **Holds only trivially.** eagle-cam-midnight's clock puts the recording on 2024-12-28, but 9.3 h from its start.
3. **Waits for the verdict threshold γ.**
4. **Fails.** The fine stage alone takes 6–42 min per case against 2–3 min, though the top-5 rule cut it 2–6× from the first run.

**Why Oyster Bay fails.**
- **The true cell never reaches the fine stage.** None of the five kept coarse cells is within 14 km of the truth, on any of the three Oyster Bay runs. The kept cells' coarse Z are 18–23 (±10 %), out of 3,876 cells in the case's 100 × 150 km box of New York traffic.
- **The winner doesn't depend on the true flights.** oyster-bay's winner and matched flights (a0bcb7, a27aab) are sources-removed's exactly: the same point, found with the true pair deleted.
- **ace391's window is out of the fine sweep's reach.** Detection gives its window a coarse tone of 140 Hz against the true line's 125.5 Hz, 11.5 % off. The fine stage's ±10 % can't reach it even at the true point; the coarse stage's ±12 % just can.

**Against the expectation.** I expected Oyster Bay to pass 1 and the eagle cam to be the doubtful one. The opposite happened:
- the eagle cam is found with both true flights, weak window included, at both sweeps;
- Oyster Bay is lost twice over, in the coarse ranking and in the tone sweep.

**Decision line.** "If 1–4 hold" is false, whatever γ shows: step B doesn't become the collective find in this form. The proposal's second line ("if 1 fails on the eagle cam while Oyster Bay passes") doesn't apply either: the failure is the other way round. What the null can still tell:
- whether the eagle cam's win is significant over SWFL traffic;
- whether the negatives stay below γ.

## A design step, written before the next rerun: cells by margin, the tone per candidate

**Two causes, both design.** Both lost Oyster Bay, and both repeat the per-event fit's failure: the find inherits a fixed choice made before the evidence is weighed.
- **The pruning keeps a count, not a margin.** Five cells out of 3,876, whatever the scores.
- **The tone comes from detection's coarse template.** ace391's window is the second-strongest of ten, and its coarse tone (140 Hz) is 11.5 % off the true line (125.5 Hz). Its estimate isn't weak; it is confidently wrong, so a sweep widened only where the tone estimate is weak wouldn't catch it.

**The step, fixed now.**
1. **The coarse map is written whole,** every cell's Z, so the true cell's rank is known on each case. The fine stage keeps every coarse cell with Z ≥ Z_max − 2σ_c, where σ_c is 1.4826 × the MAD of the coarse Z over the cells with Z > 0. The count is reported, not fixed, under a cap of 20 cells by Z. Where the cap binds, the record gives the margin it reached.
2. **The tone is each candidate's own.** For each (point, flight, window), the score is maximised over f0 across ±25 % of detection's coarse tone: the crop's span holds it, and ace391 needs −10.4 %. So each candidate flight's curve picks its own f0 from the window's observed frequencies, instead of starting from detection's.
   - This is the review’s variant (b). Its look-elsewhere cost is the same as any ±25 % sweep's. Each window's null is drawn with the same rule, so the cost is priced there, and the other-day null redraws on it.
   - The coarse stage takes the same ±25 % (at 2 % steps); the fine stage steps at 0.5 %.

**The cost, and its bound.**
- **Today's fine stage** on Oyster Bay is 2,543 s for 5 cells × 41 tone points on an 8xlarge, about 510 s per cell.
- **The new step at today's sampler** would be 20 cells × 101 tone points, about 21 min per cell and 7 box-hours per case at the cap.
- **Two implementation items keep that affordable.**
  - **A log-frequency view of each window:** a scaled f0 becomes an index shift, so the 101 tone points are a gather from one precomputed (log f × time) matrix, not 101 bilinear samplings. Its speed is measured on the unit test before any run.
  - **The fine stage as fleet units,** one per (case, kept cell). The wall time per case is then one cell's, under 21 min, and the box cost is at most 7 hours per case.
- **The null at the cap** would be up to 150 × 7 box-hours for New York. That's why the coarse map comes first: it says what the cap needs to be.

**The order.**
1. **The coarse map,** at ±25 %, on the eight cases. It's cheap, about 5–10 min per case. It reports the true cell's rank on the positives.
2. **The fine stage** within the margin.
3. **Only then** the New York draws.

**What it should do to the eagle cam.**
- **Its z values drop.** Widening the sweep from ±5 % to ±10 % took a2baea from z 6.59 to 4.95, and a336e4 from 2.44 to 1.80, about × 0.75 each. Going to ±25 % should cost a similar factor again: about 3.5 and 1.3.
- **Both should stay matched.** The margin rule can only add cells, so it can't drop the eagle cam's winning cell. Its second mode (9.37 against 16.27) leaves room.
- **I expect the eagle cam's location and matched set unchanged,** with lower z, and ace391 reachable at Oyster Bay. Whether Oyster Bay's true cell then wins is what the coarse map's rank says first.

**The log-frequency gather, measured before any run** (03c6a39). On the unit test's synthetic pass (8192-point STFT at 0.5 s; 33 shifts, 160 times), 50 calls each, on the Mac:

| Scorer | f0 points | Per call |
|---|---|---|
| `EventWindow.sweep_scores` (bilinear), ±10 % | 41 | 5.52 ms |
| `LogView.sweep_scores` (gather), ±10 % | 43 | 1.47 ms |
| `LogView.sweep_scores`, ±25 % | 104 | 3.59 ms |

- **Accuracy.** On the true curve the gather scores 12.58 against the bilinear sampler's 12.96; the log grid's second interpolation costs 3 %. Its maximum lands at f0 scale 0.9705, against the truth's 0.9709.
- **Cost.** Building each window's matrix takes 4.4 ms. The ±25 % sweep costs 0.65× today's ±10 % per evaluation, so the per-cell estimate falls from 21 min to about 0.65 × 510 s ≈ 5.5 min on an 8xlarge.
- **The unit test** passes on the new code: 1.0 s as committed, 4.8 s at ±25 % with 200 null draws. Both flights are matched at the observer.
- **The real per-cell time** is the coarse stage's top-cell fine stage; it's reported before the fine stage launches.
- **The look-elsewhere cost.** ±25 % of f0 freedom per candidate flight lets wrong flights fit as easily as true ones. Each window's null and the other-day null are drawn under the same ±25 % rule, so the cost is priced in both before any margin is read.

**The second design's first read: Oyster Bay's coarse map at ±25 %** (`runs/2026-11-04-collective-coarse-v2-s1of8`, unit `oyster-bay--cell0`, 91fb1c1, 8xlarge).
- **Runtime.**
  - Coarse CPA 15 s, coarse stage 167 s (288 s at ±12 % under the bilinear sampler).
  - One fine cell (100 points) 284 s, against the 5.5 min estimate. At the cap that's 20 × 284 s ≈ 95 box-minutes per case, about 8 min of wall with one box per cell.
- **The margin rule binds.** 114 of 3,852 cells lie within 2σ_c (σ_c = 1.70) of the coarse maximum (14.80). The cap keeps 20, which reach 1.69 below the maximum, about 1σ.
- **The true cell isn't pruned; it doesn't score.** Its coarse Z is 7.36, rank 1,698 of 3,852, about the map's median and far below the margin (11.41). Even with ±25 % of tone freedom, the coarse stage doesn't see the true pair at the true cell.
- **One kept cell, rank 13, is 2.0 km from the truth,** next to the true cell. The fine stage over the 20 kept cells will show whether the fine grid there reaches the truth.
- **Its top cell's winner** is 14.1 km from the truth, at Z 14.80 with 3 windows matched.

**The split: Oyster Bay's true cell in the fine stage** (`runs/2026-11-04-collective-truth/`, [collective_truth.py](../../tools/experiments/2026-11-04/collective_truth.py), 75a8e02). This is a diagnostic that reads the labels: the fine stage on the true coarse cell (1.0 km from the reference) and on the reference point, with the run's own whole-box fine nulls.
- **The fine grid sees the true point; the coarse grid doesn't.**
  - In the true cell the fine stage reaches Z 17.54.
  - With the clock free it gives 16.21 at the reference point, 3.8 s from the reference clock.
  - Both beat the whole coarse map's maximum (14.80) and the top kept cell's fine winner (14.80). The same cell's coarse Z was 7.36.
  - So the coarse span's maximum (shift ±14 s at 2 s, f0 at 2 %, 60 samples) steps over a narrow peak. That is the coarse sampler's fault, Axelrad's warning, not the pruning's.
- **Per window at the reference clock,** every CPA row at the reference point scored without the vote:

| Window (heard CPA, coarse tone) | Best flight, f0, z | a1dfeb's z | ace391's z |
|---|---|---|---|
| 2,156 s, 112.9 Hz | a1dfeb, 112.9 Hz, 9.67 | 9.67 | −5.99 |
| 3,068 s, 140.1 Hz | a1dfeb, 104.9 Hz, 2.22 | 2.22 | 1.97 |
| 790 s, 92.3 Hz | a63e21, 94.6 Hz, 2.43 | −5.13 | −5.13 |
| 210 s, 72.5 Hz | a0ddc4, 85.0 Hz, 0.82 | −2.80 | −2.80 |
| 3,400 s, 73.1 Hz | a1cecb, 84.9 Hz, 2.91 | −4.07 | −0.48 |
| 1,409 s, 83.3 Hz | aa61d2, 84.2 Hz, 4.62 | −7.65 | −7.65 |
| 693 s, 105.8 Hz | a63e21, 92.9 Hz, 2.15 | −4.61 | −4.61 |
| 359 s, 105.7 Hz | a0ddc4, 84.4 Hz, 1.10 | −4.99 | −4.99 |
| 3,189 s, 68.1 Hz | a1cecb, 83.6 Hz, 0.43 | −2.99 | −0.70 |
| 502 s, 178.8 Hz | a1cecb, 173.5 Hz, 1.30 | −11.50 | −11.50 |

- **ace391's window is the second, smaller fault.** Its window (3,068 s) gives ace391 only z 1.97, below a1dfeb's tail at 2.22 in the same window. The find test found ace391's line there at score 12.93 under brightness, so the window, or its ±25 % null, must be checked against that.
  - a1dfeb carries the true point at z 9.67.
  - Other flights explain several windows at the true point too: aa61d2 at 4.62 in the 1,409 s window, for one.

**The second design's coarse stage on the eight cases** (`runs/2026-11-04-collective-coarse-v2-merge/`, 91fb1c1). This is each case's cell-0 fine winner; the other kept cells are the fine stage's.

| Case | True cell's coarse rank (of cells with Z > 0) | Within the margin | Kept | Cell 0's winner from the truth | True flights in cell 0 |
|---|---|---|---|---|---|
| eagle-cam-clip-18000s | **2** of 4,073 (Z 9.98 against the maximum 10.87) | yes | 9 | **0.5 km**, clock 2.5 s off | both (a2baea z 6.05, a336e4 z 2.20) |
| eagle-cam-midnight | 396 of 4,194 | no | 20 | 3.7 km | – |
| oyster-bay | 1,698 of 3,852 | no | 20 | 14.1 km | neither |
| oyster-bay-hp150-aac32k | 1,371 of 3,850 | no | 20 | 57.7 km | a1dfeb only (z 8.64) |
| oyster-bay-sources-removed (−) | 3,473 of 3,852 | no | 20 | (the same 14.1 km point as oyster-bay) | – |
| xenocanto-xc990819 (−) | 71 of 3,716 | no | 19 | – | – |
| north150, wsw150 (−) | the true point is outside the box | – | 19, 20 | – | – |

- **Against the expectation.** I expected the ±25 % sweep to lower the eagle cam's true z (to about 3.5 and 1.3). It raised them instead, to 6.05 and 2.20, against 4.95 and 1.80 at ±10 %. The eagle cam's true cell ranks second, so the coarse sampler isn't what loses Oyster Bay there.
- **The fine stage runs on every kept cell.** Oyster Bay's 19 other cells run as `2026-11-04-collective-fine-v2-s*of19` (75a8e02), the other cases' 120 as `…-s*of20` (80599d3). The merge takes each case's best cell over both stages.

**The two follow-ups the split asks for, written before their results.**
1. **ace391's window.** The find test's 12.93 is a raw brightness (mean whitened dB along the curve, f0 and clock free, on the saved-fit window, 95–195 Hz), not a z. On the same scale the collective find's LogView scores ace391 at about 6.4 in window 3,068: z 1.97 against that window's null, median 4.33 and σ 1.04. So the denominator isn't inflated: σ is ordinary, like the other windows'. The raw score is what halves.
   - **The suspect is segment coverage.** The find test joined the flight's segments into one curve. The collective find scores each segment as its own CPA row, with uncovered times counting as zero.
   - **`collective_truth.py`'s `pair_detail`** (unit truth2, fc224b3) reports, per true flight and window: the segments' coverage and scores, the joined curve's score, and the find test's brightness on the same window and on the saved-fit windows.
2. **The coarse sampler.** Cost per evaluation on the synthetic pass, against today's coarse sweep (±14 s at 2 s, 2 %, 60 samples: 0.21 ms):

| Sampler | Per evaluation | Coarse stage relative to today |
|---|---|---|
| Dense: ±14 s at 1 s, 1 %, 120 samples | 1.40 ms | 6.5× |
| 3×3 sub-grid (667 m), ±8 s at 2 s, 2 %, 60 | 9 × 0.15 ms | 6.1× |
| 3×3 sub-grid at the dense sweep | 9 × 0.81 ms | 33.8× |
| 1 km grid (4 points per cell), today's sweep | 4 × 0.21 ms | 4.0× |

   - **Both of the review’s options cost more than 2×.** The dense version is 6.5×, about 18 min per case at Oyster Bay's 167 s coarse stage.
   - **The sub-grid is the review’s upper bound.** It costs about the same (6.1×), and it samples position, which a denser shift or tone can't: the true cell's centre is 1.0 km from the truth, and a 1 km offset changes the curve's shape.
   - **The data decides.** `coarse_variants` (unit truth3, 5ba8c4b) scores the true coarse cell under all four samplers, each with its own whole-box nulls. The sampler adopted is the cheapest whose true-cell Z ranks inside the margin.

**The follow-ups' results** (`runs/2026-11-04-collective-truth-3/`, 5ba8c4b; truth-2 is the same pair detail, at fc224b3).

1. **ace391's window loses half to its length, not to coverage.**
   - **No split.** ace391 is one segment covering the 3,068 s window fully, with coverage 1.00.
   - **The two scorers agree on the same window.** The find test's own brightness on that 240 s detect window (2,947–3,187 s) is 6.63, against the LogView's 6.39.
   - **The 12.93 belongs to a shorter window.** It came from the saved-fit window, 3,020–3,130 s, 110 s long.
   - **a1dfeb shows the same thing:** 20.24 on its saved-fit window, 11.42 on its 240 s detect window.
   - **So both true lines lose about half their brightness.** The score is the mean over 240 s, and each line is bright for about 110 s. My coverage hypothesis was wrong.
   - **The fix is in the score's support:** for example the best fixed-length sub-interval of the window, or the window's bounds cut to the line's extent. The window nulls must take the same rule.
2. **Position, not sweep density, is what the coarse stage misses.** The true coarse cell under four samplers, each with its own whole-box nulls; on today's map the maximum is 14.80 and the margin threshold 11.41:

| Sampler | Points per cell | True cell's Z | Cost against today |
|---|---|---|---|
| Today (±14 s at 2 s, 2 %, 60) | 1 | 7.36 | 1× |
| Dense (±14 s at 1 s, 1 %, 120) | 1 | 10.04 | 6.5× |
| 1 km grid, today's sweep | 4 | **16.61** | 4.0× |
| 3×3 sub-grid (667 m), ±8 s | 9 | **20.76** | 6.1× |

   - **The dense sweep lifts the cell by 2.7,** still below the margin.
   - **Sampling position lifts it past today's whole-map maximum.** The best 667 m sub-point is 20.76, the best 1 km point 16.61.
   - **Other cells rise too under a new sampler,** so the true cell's rank needs a full map. The 1 km grid is the cheapest sampler that sees the peak.

## The third design step, written before its run: a 1 km coarse grid and the best 120 s stretch

**Fixed now, not tuned** (2170d9c):
- **The coarse grid at 1 km.** `COARSE_M` 1000, so a fine cell is 25 points at 200 m. The coarse sweep stays as it is (±14 s at 2 s, 2 %, 60), since the true cell's test showed that position, not sweep density, is what the coarse stage missed.
- **The best 120 s stretch.** Each (flight, window) scores its best stretch of `SUB_S` = 120 s within the window: the best mean over any 120 s run of the n times, uncovered times still zero. The window nulls take the same rule, so the extra maximum over the stretch's position is priced in them.
  - 120 s is the find test's line extent (about 110 s) rounded up, not a value searched for.
  - This is the find's workaround for a detector finding (PLAN item 6): `detect`'s windows are twice the lines' length.
- **The margin rule and the cap of 20 are unchanged,** now counted in 1 km cells.

**Cost expected:** about 4× today's coarse stage, about 11 min for Oyster Bay on an 8xlarge, plus the top cell's 25-point fine stage, about a quarter of the 2 km cell's 284 s.

**Expectation.**
- At 1 km the true coarse cell scored 16.61 on the old score, so on Oyster Bay I expect the true cell inside the margin and near the top. Other cells rise too, so the rank is the test.
- The sub-interval score should lift both Oyster Bay true lines to about their 110 s values (z well above today's 9.67 and 1.97), and similarly the eagle cam's.
- The negatives rise as well, through the extra maximum; the null prices that.

**The third design's first read: Oyster Bay** (`runs/2026-11-04-collective-coarse-v3-s1of8`, 68a906c, 8xlarge).
- **The true cell is the coarse map's maximum:** rank 1 of 15,253 cells with Z > 0, Z 18.50.
- **The top cell's fine winner** is 0.3 km from the truth, at Z 17.19. Both true flights are in its matched set: a1dfeb at z 10.43, ace391 at z 0.62, with a63e21 and aa61d2.
- **The margin:** 24 cells lie within 2σ_c (σ_c 1.81). The cap keeps 20, reaching 3.46 below the maximum. A second kept cell is 0.7 km from the truth.
- **Cost:** the coarse stage 607 s, 3.6× the 2 km stage, and one 25-point fine cell 143 s.
- **Against the expectation.** The rank came out as I expected (the true cell inside the margin and near the top). The second half didn't: ace391 stays weak, at z 0.62 against 1.97 before. The best-120 s score lifted a1dfeb (9.67 to 10.43) but not ace391, whose window remains the open question.
- **Whether the case passes criterion 1** waits for the fine stage over all 20 kept cells.

**The third design's coarse stage on the eight cases** (`runs/2026-11-04-collective-coarse-v3-merge/`, 68a906c). These are cell 0's fine winners; the other kept cells are the fine stage's.

| Case | True cell's rank | Kept | Cell 0's winner from the truth | True flights at the winner | Coarse, one fine cell |
|---|---|---|---|---|---|
| oyster-bay | **1** of 15,253 | 20 | **0.3 km** | a1dfeb z 10.43, ace391 z 0.62 | 607 s, 143 s |
| oyster-bay-hp150-aac32k | **1** of 15,245 | 4 | **0.3 km** | a1dfeb z 9.11, ace391 z 0.53 | 659 s, 134 s |
| eagle-cam-clip-18000s | 37 of 16,392 (outside the margin) | 9 | 1.9 km | neither | 239 s, 146 s |
| eagle-cam-midnight | 280 of 16,843 | 20 | 5.8 km | – | 272 s, 172 s |
| oyster-bay-sources-removed (−) | 5,821 of 15,255 | 20 | 67.4 km, Z 13.36 | – | 898 s, 192 s |
| xenocanto-xc990819 (−) | 6,241 of 14,673 | 20 | 50.6 km, Z 9.66 | – | 184 s, 116 s |
| oyster-bay-moved-north150 (−) | the true point is outside the box | 20 | coarse maximum 15.82 | – | 148 s, 134 s |
| oyster-bay-moved-wsw150 (−) | the true point is outside the box | 20 | coarse maximum 18.22 | – | 518 s, 162 s |

- **Oyster Bay and its hp150 copy are found.** In each the true cell is the coarse maximum, and the winner is 0.3 km off with both true flights matched.
- **sources-removed behaves as a control should.** With the true flights deleted, the true cell falls to 5,821st.
- **The eagle cam regressed.** Under the second design its true cell was 2nd and its winner 0.5 km off with both flights. Now it is 37th, outside the margin.
  - Either the best-120 s stretch or the 1 km cells cost it.
  - The true-point diagnostic on it (`collective-truth-s2of2`, 337f23f) says which.
- **wsw150, a negative, reaches a coarse maximum of 18.22,** against Oyster Bay's 18.50. Only the other-day null can separate them.

**The eagle cam's regression: the coarse sweep, not the 120 s stretch** (`runs/2026-11-04-collective-truth-s2of2`, 337f23f; a diagnostic that reads the labels).
- **The fine grid sees the eagle cam's true point.** In its true 1 km cell (centre 146 m from the nest) the fine stage reaches Z 18.06, and 16.57 at the reference point with the clock 0.2 s from the reference clock. That's above the whole v3 coarse map's maximum (12.0).
- **The true flights at the reference point and clock:** a2baea z 6.16 and 3.81, a336e4 z 1.93. So the best-120 s score keeps both true flights, and isn't what cost the case.
- **The coarse stage missed it, again on sampling.** The true cell's coarse Z is 8.40, rank 37. Within that one 1 km cell, the other samplers give:

| Sampler within the true 1 km cell | True cell's Z |
|---|---|
| Today's coarse sweep (±14 s at 2 s, 2 %, 60 samples) | 8.40 |
| The dense sweep (±14 s at 1 s, 1 %, 120) | **13.66** |
| A 2 × 2 grid (500 m) at today's sweep | **14.14** |
| A 3 × 3 grid (333 m) at today's sweep | 11.85 |

  - **Here sweep density matters, unlike at Oyster Bay.** With the best-120 s stretch, the coarse sweep's 60 samples over a 240 s window leave about 30 inside the stretch, 4 s apart. That's too sparse for a line that is bright for about 110 s.
  - **The coarse stage needs the denser sweep as well as the 1 km cells.** Either sampler above lifts the true cell past the map's maximum.
- **One pass counted twice.** Two overlapping windows (2,175 s and 2,247 s) both take a2baea's single pass, at z 6.16 and 3.81. "One window per pass" isn't enforced (design §1), so the sum counts that pass twice. The same can inflate chance matches; the null includes it, but the constraint should be enforced.

## The fourth design step, written before its run: a denser coarse sweep and one window per pass

**Fixed now** (aeba858):
- **The coarse sweep** keeps 60 samples per 120 s stretch, with 1 s shifts and 1 % f0. Each window's n scales with its length. For `detect`'s 240 s windows that is n = 120, so this is the dense sweep from the samplers table: about 7× today's coarse cost per evaluation.
  - The review preferred the scaled form expecting it to be cheaper. On 240 s windows it's the same sweep.
  - The fine sweep is unchanged: 80 per stretch, which is 160 per 240 s window.
- **One window per pass, enforced.** At a point and clock, a pass (a segment's CPA there) explains only its best window. A window whose best pass is taken falls back to its next, among its best 3 per clock bin. The same rule applies in `point_scores` and in `matched_at`.
  - **The first three designs didn't enforce it.** Overlapping windows on one pass were summed twice: at the eagle cam's true point, a2baea counted at z 6.16 and 3.81.
  - **Their nulls priced it,** since every draw was summed the same way.
  - **Each run now also records its coarse maximum without the rule** (`counts.coarse_max_without_pass_rule`), so the rule's effect on Oyster Bay's and wsw150's maxima is reported.

**Order:** Oyster Bay's coarse unit first, with its coarse time stated before the other seven; then the fine stage within the margin.

**Expectation.**
- The eagle cam's true cell lifts past its coarse maximum, as the samplers table's 13.66 against 12.0 says.
- Oyster Bay stays first.
- The pass rule lowers every maximum that leaned on overlapping windows, true or chance. I don't know in advance which of Oyster Bay and wsw150 it lowers more.
