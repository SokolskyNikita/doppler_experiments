# Frequency tracks from a likelihood

<!-- index
question: Does a forward-backward tracker on per-cell log-likelihood ratios (Rician over Exp(1), OFF/ON/DIP states) beat `ridge()` on the Livermore passes?
outcome: Not met: at the one ROC point that qualified (a 2, β 1e-3), error 0.60 % against 0.48 %, 190 bridges against 36, 85 fragments against 12. The finding is the ROC: overlapping frames counted as independent evidence put a 12-per-hour floor no prior moves, and Harris's overlap weight (0.254) removes it. Next: the window (item 5), not the prior
-->

## Question

PLAN Phase 2 item 3, round 3, after the dB thresholds of rounds 1 and 2 failed
([freqtrack](2026-11-04-freqtrack.md), [hmm-tracker](2026-11-04-hmm-tracker.md)). The design was written before any
code ran: [the proposal](designs/2026-11-04-tracker-likelihood.md).
- **Evidence.** Each cell's power over the frame's noise level across frequency, z = P/σ², is scored by the
  log-likelihood ratio of a Rician tone at design SNR a against Exp(1) noise (Kay I Ex. 7.16). Each of harmonics
  1–3 is present with prior 0.5.
- **States.** OFF, ON(k) and DIP(k), decoded by forward–backward. A track is a run of frames with P(ON or DIP)
  above 0.5.
- **Transitions.** A birth prior β per Hz per second; pass, run and dip lengths fixed from the development
  events; frequency moves by a Laplace kernel of 0.02·f per second, capped at 0.25·f.
- **Measurement.** Weights h²·Â_h² (Quinn & Hannan eq. 3.11).

Criterion, round 1's and unchanged: on the 29 primary Livermore passes, at 2 % tolerance, a lower median error
than `ridge()` as shipped (time-whitened image), no more false bridges and no more fragments.

The knobs a and β were picked by a pre-registered ROC on synthetic data before any Livermore pass was read:
- **Grid:** a ∈ {1, 2, 4, 8} by β ∈ 10^−12…10^−2.
- **Data:** round 2's noise (2 h of white noise in 12 windows, 150–250 Hz) and its weak pass.
- **Rule:** the lowest β with ≤ 1 false track per hour per 100 Hz and a median weak-pass coverage ≥ 0.5.

## Setup

- **Code:** `src/dopplertrack/lltrack.py`, commits dab0fe0, 1ab2cfa (the retune) and 5730bd8.
- **Tests:** `tests/test_lltrack.py`. Seven pass: ℓ against the noncentral χ² density, forward–backward against
  enumeration, and round 2's behaviour cases. The noise test is a strict xfail because no defaults were adopted.
- **Constants**, from the six development events (the references are round 2's):
  - T_pass = 142.5 s;
  - T_run = T_dip = 0.75 s.

  The share of reference frames under the noise (max z over harmonics < ln 10) is 0.02 and 0.15 on Oyster Bay's
  events, 0.51 and 0.62 on the eagle cam's, 0.71 on ob-e03 and 0.46 on sw-e01.
- **Fleet:**
  - the first ROC: 2026-11-04-ll-round3, one 16xlarge;
  - the retune's ROC: four 4xlarge shards, collected as 2026-11-04-ll-retune1-roc-collect, picked by
    2026-11-04-ll-retune1-pick;
  - the passes: two 4xlarge shards, collected as 2026-11-04-ll-retune1-passes-collect, merged by
    2026-11-04-ll-retune1-merge.

## Numbers

**The first ROC.** Weak-pass coverage, fragments and bridges barely move with β; the noise column is what
matters.

| a \ β | 10⁻¹² | 10⁻¹⁰ | 10⁻⁸ | 10⁻⁶ | 10⁻⁴ | 10⁻³ | 10⁻² |
|---|---|---|---|---|---|---|---|
| 1 | 12.0 | 12.0 | 12.0 | 12.0 | 12.0 | 12.0 | 12.0 |
| 2 | 12.0 | 12.0 | 12.0 | 12.5 | 19.5 | 26.0 | 19.0 |
| 4 | 12.0 | 12.5 | 18.5 | 27.0 | 74.5 | 131 | 113 |
| 8 | 17.0 | 24.0 | 44.5 | 88.0 | 210 | 345 | 238 |

The values are false tracks per hour per 100 Hz. At a = 1, weak-pass coverage is 0.96 with 5 fragments; at
a = 8 it is 0.82 with 22. No point qualifies.

The floor of 12 per hour is exactly two tracks per 10-minute window, one per family, each spanning the window, and
it is the same at β = 10⁻¹² as at 10⁻⁴. A birth prior that has no effect over eight decades means the noise
model, not the prior, is wrong:
- **The prior already carries the number of hypotheses.** It is per Hz, spread over the grid (β·δf·Δt per
  fundamental), so the total birth rate per frame doesn't grow with the number of fundamentals tested. That is
  Kay II's ln L.
- **The bound that should have held.** For a true likelihood ratio, E₀[LR] = 1 under noise, so a track's
  posterior in noise is bounded by its prior (Markov's inequality).
- **Why it didn't.** The bound needs independent frames. Ours are 2.048 s Hann windows at a 0.25 s hop, an
  eightfold overlap, so a noise peak persists over about eight frames and its evidence adds up like a tone.

**Retune 1 (counted, written before it ran).** Each frame's evidence is multiplied by Harris's overlap correlation,
w = 1 / (1 + 2 Σ_m ρ(m·hop)²). For this window and hop, w = 0.254: a property of the analysis, not a knob. The
grid, kernel and pick rule are unchanged.

| a \ β | ≤ 10⁻⁴ | 10⁻³ | 10⁻² |
|---|---|---|---|
| 1 | 0 / 0.00 | 9.0 / 0.77 | 12.0 / 0.93 |
| 2 | 0 / 0.00 | **0 / 0.56** (1 fragment, 1 bridge) | 12.0 / 0.96 |
| 4 | 0 / 0.00 | 0 / 0.45 | 12.0 / 0.98 |
| 8 | 0 / ≤ 0.05 | 0 / 0.19 | 4.5 / 0.97 |

Each cell gives false tracks per hour per 100 Hz, then median weak-pass coverage. One point qualifies,
a = 2, β = 10⁻³, and it was picked. Its coverage, 0.56, is thin against the 0.5 floor.

**Livermore, the 29 primary passes, 2 %.** A is `ridge()` on today's image, L is `lltrack`, and B1 is round 1's
run 1.

| Tracker | Median error | Bridges | Fragments (≥ 3 s) | Coverage | Runtime per pass |
|---|---|---|---|---|---|
| A | 0.48 % | 36 | 12 (4) | 0.97 | 0.01 s |
| L | 0.60 % | 190 | 85 (34) | 0.79 | 1.5 s |
| B1 | 0.45 % | 13 | 204 (76) | 0.50 | 0.4 s |

Criterion (error, bridges, fragments): no, no, no. **Not met.**

**The 11 flagged passes.** Median error: A 15 %, L 13 %, B1 0.84 %.

**L over 40–450 Hz, with no oracle band:** its strongest group holds the published line on 0 of 23 passes.

**Development events, summed over the six judged events** (reported only):
- bridges: A 48, L 135, B1 21;
- fragments: A 18, L 44, B1 37.

On Oyster Bay ev1 and ev2, L has the lowest error: 0.15 % and 0.22 %, against A's 0.18 % and 0.40 %. On sw-e01 it
has 1.1 % against A's 27 %. On the eagle cam's events it has 8.9 % and 17.5 %, against A's 2.6 % and 12 %.

## Outcome

Not met. `ridge()` stays the fitting path's tracker, and neither `hmmtrack` nor `lltrack` is adopted. Item 3 has
now had three rounds, each with its counted retune spent.

What this round established:
- **No prior has grip on a per-frame likelihood ratio over overlapping frames.** The ratio counts eightfold-
  overlapping frames as independent evidence, so noise accumulates like a tone. That is the 12-per-hour floor,
  the same 12 per hour that round 2 hit through θ_cont.
- **Harris's overlap weight removes the floor.** After it, noise makes no false tracks for β up to 10⁻³.
- **At the one point that then passes the synthetic test, L covers more of the real passes than any earlier
  round** (0.79, against 0.43–0.65 for rounds 1 and 2). But it bridges five times as often as `ridge()`. With w
  at 0.254, a weak real tone also gets only a quarter of its evidence per frame, so the tracker holds a line only
  where the tone is strong and wanders between lines elsewhere.

The weight is a correction for the analysis window, not a cure for it. The next step is therefore the window, not
the prior: frames that overlap less (a longer hop, or non-overlapping blocks) bring w towards 1, so each frame's
evidence is its own. That belongs with item 5's window work, and it should be measured there before item 3 takes
another round.

## Script and run folder

- **Scripts:** `tools/experiments/2026-11-04/ll_roc.py`, `ll_livermore.py`, `ll_box.sh`, `ll_collect.sh` and
  `copy_new.py`, launched with `tools/aws/runs`.
- **Run folders** (in `$DOPPLERTRACK_DATA/runs/`):
  - 2026-11-04-ll-round3: the first ROC;
  - 2026-11-04-ll-retune1-roc-s{1..4}of4 and -roc-collect;
  - 2026-11-04-ll-retune1-pick (`ll_chosen.json`);
  - 2026-11-04-ll-retune1-passes-s{1,2}of2 and -passes-collect;
  - 2026-11-04-ll-retune1-merge (`ll_summary.txt` under `ll/a2_b1e-03/` in the collect folder).
- **Cost:** about $0.15 in all, on spot.
