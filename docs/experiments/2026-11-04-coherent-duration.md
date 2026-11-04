# Coherent alignment duration for weak flyovers

<!-- index
question: Does aligning waveform cycles over 6 s or 18 s, rather than nine 2 s blocks or today's curve score, recover weak real flyovers at a fixed false-alarm rate when the detector also picks the flight?
outcome: Pending: both verification gates failed narrowly (gate 1 by 0.2 dB on a 1 dB grid, gate 2 by 0.5 dB) and the Gumbel thresholds fit poorly; nothing else has run
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

## Status

Under the proposal, a failed gate stops the test set until the gate is fixed. The one counted retune hasn't been
spent. What to change is the PM's decision, recorded here when made.
