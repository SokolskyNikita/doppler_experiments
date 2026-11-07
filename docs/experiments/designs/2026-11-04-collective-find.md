# The collective find: every detected window against every flight's own curve (proposal)

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `13917fae0743530da1f1665a1efab897c468c48360c35c2592c3b6640812d0d0`.

> **Research reset status, 2026-11-04.** The original accuracy and runtime criteria failed on the completed
> top-five own-day run. Later v2/v3/v4 are successive designs, not a pass of this proposal or its one
> clock-width retune. v3 has only top-cell fine summaries; v4 has no completed result. No matching collective
> verdict null has passed. The original failed criteria remain failed; see [the
> audit](../2026-11-04-research-reset.md).

PLAN Phase 3, `locate`'s step B. This is a design, written before any code or run.

**decision:** whether `locate`'s step B becomes the collective find described here. It would retire the per-event straight-pass fits as the events' representation, along with item 7's pair rules (`top2`, `comparable`) and stage B's hypotheses.

**Why** ([event-fit](../2026-11-04-event-fit.md)).
- **The evidence and the objective are right; the candidate set is wrong.** On Oyster Bay event 2 the true flight's line is in the spectrogram at 15.6 dB on 96 % of frames. Brightness scores it 16 % above any straight-pass curve. But a straight pass can't express ace391's heard curve, so the fit settles on a straight compromise 2.3 km and 38 m/s from the truth.
- **The search already does the right thing.** It scores each flight's own heard curve against the spectrogram. That is why Oyster Bay ranks its true pair first with event fits 57σ off.
- **So the event fit adds nothing but a lossy intermediate.** Its v and d gate the search, and its f0 and CPA anchor it.

## 1. The object

For a grid point x (locate's coarse grid, 200 m), a shared clock b (audio seconds to UTC), and a detected window w:

  s(x, b, w) = max over the box's flights f, harmonics h ∈ {1, 2}, f0, and a residual shift δ ∈ ±8 s of the score of h · f0 · ratio_f,x(t + b + δ) in w,

where ratio_f,x is flight f's own heard curve at x (`score.modelled_curve`, per-flight sound speed when the run sets the weather). The score is today's `EventWindow.sweep_scores` contrast, normalised to the comparable score's z against the window's own null:

  z(x, b, w) = (s − median_w) / σ_w.

The point's collective score is the non-coherent sum

  Z(x, b) = Σ_w max(z(x, b, w), 0),   then   Z(x) = max over b of Z(x, b).

This is Axelrad et al. (2011)'s collective detection, read in full (`$DOPPLERTRACK_DATA/reference/md/axelrad-2011-collective-detection.md`, "Combining Satellites" and "Direct Positioning").
- **Their grid** is position × clock. Each grid point maps to every source's predicted observables, here each flight's heard curve at x.
- **Each source's correlogram is normalised by its own noise level and floor before the non-coherent sum.** Here that is each window's null, as the comparable score already does.
- **They search coarse to fine** around the peak. Here that is locate's refine at 50 m around each mode.

Two constraints keep it physical:
- **One clock per point,** shared by every window. A flight's pass is one acoustic event, so a pass (one segment's CPA at x) explains at most one window. A flight-school aircraft circling past twice is two passes and may explain two windows.

## 2. What replaces `fit_event`

**What detection keeps per window:**
- **The time bounds,** detect's window_s window.
- **The band:** the detection band, and the coarse tone's harmonic hint.
- **A coarse tone:** detect's grid-search f0, before refinement.
- **A coarse heard CPA:** the grid template's, used only as the clock prior (§4).
- **Its detect score,** for ordering and the threshold.
- **Its valid-frame mask** (gaps).

**What is dropped:**
- v, d, `t_cpa_emit`, f_pre and f_post, and `detect`'s Nelder-Mead refinement;
- the speed and distance gates that compare a straight-pass v and d with each flight's;
- the pair rules.

The silence filter is out of scope here and stays as it is.

**The f0 sweep must widen.** Today `single_score` sweeps 0.95–1.05 around the fitted f0. The two wrong finds sit 5.5 % and 5.9 % from their true lines' f0, so the collective find sweeps 0.90–1.10 around the coarse tone. The window's null is drawn with the same sweep, so its median rises to match.

## 3. Windows no flight explains, and how many enter

- **A floor, not a penalty.** A window no flight explains contributes max(z, 0) = 0. An inaudible flight, another source or a bird can't veto the point.
  - The cost of the floor: under H0 every window also contributes its best chance match above 0, so Z grows with the number of windows. That is what the verdict's null of the maximum absorbs (§5).
- **Which windows: the top k = 10 by detect score, fixed now.** That is `locate`'s `detect_top`. A recording where `detect` returns fewer enters with what it has, and the null is drawn with the same count. "All above detect's threshold" would make the null depend on each recording's count.
- **The weak window.** The eagle cam's event 2 is the case the design has to carry: the true line at about 6 dB on half the frames, and contrast preferring the straight compromise at 3.65 against 2.63.
  - In the collective find it enters with whatever z the true flight's own curve earns at the shared clock. That clock is fixed mostly by the other windows, so the weak window is scored where it belongs, not where its own fit wanders.
  - A z near 0 adds nothing and costs nothing. Anything above 0 helps the true point only where the stronger windows already put it.
  - It can't win the point alone, and it can't veto it.

## 4. Cost, and what is reused

> **Correction (before the build).** The bound below is wrong: today's 197,177 and 84,441 time-joined triples are counted after the speed and distance gates (v ±35 %, d ×0.4–2.5), which leave 16.35 M of Oyster Bay's 86.2 M CPA rows per event, and the design drops those gates. At 200 m the clock vote keeps on the order of 10⁸–10⁹ window pairs. The build therefore takes the review’s coarse-to-fine lever as a design step: a 2 km grid scored as the maximum over each cell's span (shift ±14 s, f0 ±12 %), then 200 m inside the cells at ≥ 0.7 of the coarse maximum ([collective-find record](../2026-11-04-collective-find.md)).

Measured today on the saved-fit Tier 2 cases:
- **Grid points:** 378,500 (Oyster Bay) and 430,882 (the eagle cam) at 200 m.
- **CPA records:** 86.2 M and 35.9 M.
- **Triples after the time gate:** 197,177 and 84,441. Triples scored: 40,889 and 50,682.

**The clock vote replaces the pair time gate.**
- At each point, every (window, pass within 12 km) gives a clock candidate b = t_heard(pass, x) − t_cpa,coarse(w). That is W × (passes per point), about 10 × 230 at Oyster Bay, read from the CPA table.
- Candidates are clustered within ±20 s, wider than the ±8 s residual because the coarse CPA comes from a straight template. The find test's CPA errors were 5.5 and 7.7 s.
- A cluster is kept when at least two windows fall in it. Today's pair gate is the special case W = 2.

**Curve evaluations.**
- N_eval = Σ over points and kept clusters of Σ over its windows of the passes in it, each scored over the f0 and shift sweep.
- Its bound is today's time-gated triple count × W / 2: about 1.0 M at Oyster Bay and 0.4 M at the eagle cam. That is 8–24 times today's scored triples, with each evaluation as costly as today's, before the wider f0 sweep doubles it.
- **That is the runtime risk.** The vote's minimum of two windows is the lever if it is too slow. A minimum of three windows is a different statistic, so that is a design change, not a tuning.

**Reused unchanged:**
- **The CPA table and its cache.** Grid, segments, range and sound speed are unchanged, so the same fingerprint and the same `cpa/bench/*.npz`.
- **`score.modelled_curve`, `EventWindow.sweep_scores` and the process pool of `_score_triples`.**
- **`event_null`,** with its anchor taken from the window's coarse CPA and its seed from the window's bounds and coarse tone in place of the fit.
- **Refinement,** locate's refine at 50 m around each mode. Its extra-event path takes windows in place of fits, which is the one change it needs.

## 5. Criteria, fixed now

On the development cases, `locate` with step B as above, k = 10, from raw audio (`locate` profile):
1. **Oyster Bay, its hp150 copy, the eagle cam clip and eagle-cam-midnight:** the collective map's maximum is within 2 km of the truth, and its matched set (windows with z > 0 at the winning point and clock) includes both true flights.
2. **eagle-cam-midnight:** the winning clock puts the recording on the right UTC day. eagle-cam-midnight-days0 still ends before the search, as it does now.
3. **The negatives** (oyster-bay-moved-wsw150, oyster-bay-moved-north150, oyster-bay-sources-removed, xenocanto-xc990819): every maximum stays below the verdict null γ, the 1 % point of the null of the maximum ([verdict-null](2026-11-04-verdict-null.md)). That null is redrawn for this statistic, the maximum of Z over the box from other days' traffic with the same k and grid, since the pair rule's γ doesn't apply to Z.
4. **Runtime:** each positive's search fits Tier 2's budget, 2–3 min per case on a 4xlarge, with its CPA table warm.

No tuning before the run. One counted retune is allowed, of the clock vote's cluster width only.

## 6. Decision line

- **If 1–4 hold,** `locate`'s step B becomes the collective find. The per-event straight-pass fits stop being the events' representation: `fit_event` stays as a tool and the saved-fit profile as a benchmark of the old path. Item 7's pair rules and stage B's hypotheses are retired, and the verdict is the null of Z's maximum.
- **If 1 fails on the eagle cam** while Oyster Bay passes, the weak-window question is answered against the design. Its next test is the matched set's per-window z at the true point.
- **If 4 fails,** the design stands and its cost is item 5's (parallel CPA build and scoring) to solve.
- **If 3 fails,** the non-coherent sum with a floor finds structure in other days' traffic that the pair rule doesn't, and the floor needs the null's per-window median subtracted after the max, not before.

## Implementation, after this is read

- A `pair_rule = "collective"` path in `locate`, with the clock vote as a new stage in `pipeline`, and its units as shards.py jobs on 4xlarge boxes: one case per unit, plus the null's (case, day) units as the verdict proposal sets them out.
- The criteria are judged on the merged run. The record goes to `docs/experiments/` with the null's γ beside each case.
