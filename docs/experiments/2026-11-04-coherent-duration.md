# Coherent alignment duration for weak flyovers

<!-- index
question: Does aligning waveform cycles over 6 s or 18 s, rather than nine 2 s blocks or today's curve score, recover weak real flyovers at a fixed false-alarm rate when the detector also picks the flight?
outcome: Not decided: both gates failed again after the one retune (C9 over C1 6.0 dB synthetic against 4.8+-1; C9 over C1 2.0 dB on real clips against +-1), so the blind test never ran; C9 led C1 throughout and today's curve score trailed
-->

## Question and criterion

As set in [the proposal](../proposals/2026-11-04-coherent-duration.md), fixed before any run.
- **The methods:**
  - C1, C3 and C9: nine 2 s, three 6 s and one 18 s coherent block, on `warp.py`'s emission-time resampling.
  - T: today's kind of curve score.
- **The search:** each method gets the same constant pitch search over the pass's third-octave band and the same clock
  search (±10 s), with no drift.
- **Thresholds:** 1 false alarm per hour, P = 1/200 per 18 s window, from a Gumbel fit to the calibration windows'
  maxima.
- **Two gates, each pass or fail, before the settings freeze:**
  - Gate 1, synthetic: C9's gain is within 1 dB of theory, +4.8 dB over C1 and +3.0 dB over C3.
  - Gate 2, the eight real clips with the true flight and clock supplied: the median paired C9 − C1 is within
    ±1 dB, as Codex's [integration record](2026-11-04-doppler-integration-coverage.md) found.

## The gates

- **Code:** [`coherent_duration.py`](../../tools/experiments/2026-11-04/coherent_duration.py) at `306b1fb`; judged by
  [`coherent_duration_judge.py`](../../tools/experiments/2026-11-04/coherent_duration_judge.py).
- **Background:** Tier 1's nine development spans, in 837 segments of 40 s. Calibration and evaluation segments
  alternate, and each segment is scaled to the median power in the pass's band (`runs/2026-11-04-coherent-duration-bands/`).
- **The eight verification passes,** each with 200 calibration and 10 evaluation segments, at levels from +12 to −18 dB.
- **Boxes:** 8 × 4xlarge spot; shard 1 was resumed on demand.
- **Runs:** `runs/2026-11-04-coherent-duration-gates-s<k>of8/`; judged in `runs/2026-11-04-coherent-duration-gates-judge/`.

| | Criterion | Result |
|---|---|---|
| Gate 1 | median L80(C1) − L80(C9) = 4.8 ± 1 dB, and L80(C3) − L80(C9) = 3.0 ± 1 dB | **fail**: 6.0 dB and 2.5 dB |
| Gate 2 | median L80(C9) − L80(C1) within ±1 dB | **fail**: −1.5 dB |

- **Gate 1, per pass.** L80(C1) − L80(C9) is 3, 4, 8, 7, 6, 6, 6 and 3 dB; the first leg misses by 0.2 dB on a 1 dB
  level grid. C9 is ahead on every pass, and T trails C1 by a median of about 5 dB.
- **Gate 2, per pass.** L80(C9) − L80(C1) is 0, 0, −4, −3, −1, −2, +1 and −4 dB, so C9 wins 5, ties 2 and loses 1.
  Codex had 3 wins, 2 ties and 3 losses, on the Seattle background with its own detector.
- **The thresholds fit poorly.** The Gumbel fits' KS statistics are 0.11–0.35 on n = 200, against a 5 % point of
  about 0.10. The background maxima have heavier tails than a Gumbel, from jets and birds in the Essex and AeroSonicDB
  audio. So each γ is an extrapolation that can't be trusted to a dB, and both gates' margins are smaller than that.

**A finding of its own: the Gumbel fails on real background maxima.**
- On the verdict null's other-day traffic the same fit behaved: KS 0.09–0.19 at n = 50
  ([verdict-null](2026-11-04-verdict-null.md)).
- On this background audio it doesn't: KS 0.11–0.35 at n = 200.
- So a null drawn from background audio needs an empirical tail, not a fitted extreme-value law.

## The one counted retune (PM, 2026-11-04), written before its rerun

Gate 1's miss is not accepted as rounding: a gate loosened after the result is no gate. The retune changes two
things, and nothing else.
- **(a) Thresholds from an empirical tail.** For each pass and method, the threshold is the empirical 1 − 1/200 point
  of all 419 calibration segments' maxima (numpy's `higher` quantile, the second-highest of 419). It comes with a
  1,000-resample bootstrap interval. The Gumbel fit is kept only as the KS diagnostic. This fixes the null estimator's
  defect; it isn't a knob.
- **(b) A 0.5 dB level grid,** from +6 to −20 dB, for resolution.
- **Unchanged:** the methods, the search, the backgrounds and their scaling, the passes, the evaluation segments, both
  gate criteria and the test rule.
- **Then:** the gates rerun. If both pass, the settings freeze and the test set runs. If either fails, the record says
  so, and nothing more is spent.

## The gates after the retune

- **Code:** `4f44d40`.
- **Units:** 496, on 10 × 4xlarge spot, in `runs/2026-11-04-coherent-duration-gates-retune-s<k>of10/`; judged in
  `runs/2026-11-04-coherent-duration-gates-retune-judge/`.
- **Thresholds:** the empirical 1 − 1/200 point of all 419 calibration segments, with levels on a 0.5 dB grid.

| | Criterion | Result |
|---|---|---|
| Gate 1 | median L80(C1) − L80(C9) = 4.8 ± 1 dB, and L80(C3) − L80(C9) = 3.0 ± 1 dB | **fail**: 6.0 dB and 4.25 dB |
| Gate 2 | median L80(C9) − L80(C1) within ±1 dB | **fail**: −2.0 dB, on the 5 passes where both reach 80 % |

**L80 per pass, in dB:**

| Pass | Synthetic: C1 / C3 / C9 / T | Real clip, assisted: C1 / C3 / C9 / T |
|---|---|---|
| N373DF_R06 | −9.0 / −10.0 / −12.0 / −1.5 | 4.5 / 5.5 / 4.5 / – |
| N4004R_R19 | −3.0 / −5.0 / −9.0 / 0.0 | 3.0 / 3.5 / 3.0 / 2.5 |
| N60RS_R11 | −2.0 / −4.0 / −9.0 / 1.5 | – / – / 6.0 / – |
| N61NG_R37 | −3.5 / −5.5 / −11.0 / 1.0 | – / – / 4.0 / 5.5 |
| N662EZ_R48 | −3.5 / −9.5 / −13.0 / 3.0 | 3.5 / 1.0 / 1.0 / 4.5 |
| N784MB_R04 | −3.5 / −5.5 / −9.5 / 0.5 | 0.5 / 1.5 / −1.5 / 4.0 |
| N795MM_R13 | −5.5 / −7.0 / −11.5 / 0.0 | – / – / – / – |
| N913TC_R15 | −11.0 / −11.5 / −16.0 / −4.0 | 6.0 / – / 3.0 / 4.5 |

A dash means 80 % wasn't reached even at the grid's top, +6 dB.
- **The empirical thresholds sit well above the Gumbel's,** because the tails are heavy. So every method needs more
  power than in the first run, and on three real clips C1 never reaches 80 %.
- **C9 leads.** It is ahead of or level with C1 on every pass in both modes. Today's curve score, T, trails C1 by about
  4 dB on the synthetic tone.
- **Gate 1's target was probably the wrong theory.** +4.8 dB is the weak-signal law for adding nine powers (√9). At a
  strict false-alarm rate (P = 1/200 per window, after a search over pitch bins) and P_D = 0.8, adding blocks
  incoherently loses more than that law (Kay II, §5.3–5.4).
  - The steady 6 dB here, and Codex's 5 dB on its own synthetic, are consistent with that.
  - This doesn't pass the gate, which was fixed before the run. It is the reason a successor would derive gate 1's
    target at the operating point, not from the weak-signal law.

## Outcome

**Not decided.** Both gates failed after the one counted retune, so under the proposal the blind test on the 19 passes
never ran, and nothing more is spent.
- **Under the decision line,** no 6 s or 18 s scorer earns a test on the locator's shortlist from this experiment.
- **What it does show, from the gates alone (not the decision rule):**
  - With the true flight and clock supplied, one 18 s coherent block recovers real passes at a median 2 dB less added
    power than nine 2 s blocks.
  - Today's curve score is the weakest of the four on a synthetic tone.
  - A null drawn from background audio needs an empirical tail.
- **A successor proposal would need:** gate 1's target derived at the operating point; a level grid reaching above
  +6 dB for the real clips; and the same blind test.
