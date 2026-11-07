# Coherent alignment duration, second round (proposal)

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `bfe87514e6e7b8cd26a1637af20fbf062748ba02633dc2a2e211d3b859a6b8ad`.

> **Research reset status, 2026-11-04.** Unrun successor design. The first round's two failed gates remain
> failed. Its operating-point simulation and expanded levels do not yet have results, and segment-level
> empirical thresholds still need group/tail validation before a blind locator claim. A gain with the true
> flight/clock supplied cannot establish wrong-flight discrimination; see [the
> audit](../experiments/2026-11-04-research-reset.md).

A successor to [the first round](2026-11-04-coherent-duration.md), which ended undecided
([record](../experiments/2026-11-04-coherent-duration.md)). This is a design, written before any run. It runs after
the geometry study’s collective-find verdict is in.

**decision:** as before. Does a 6 s or 18 s coherent scorer earn a test on the locator's shortlist, in the collective
find's weak-window case (the eagle cam's event 2, at 6 dB on half its frames)? Otherwise the shortlist keeps today's
scorer.

**Why a second round.** The first round's gates found two things worth settling.
- With the true flight and clock supplied, one 18 s block recovered real passes at a median 2 dB less added power
  than nine 2 s blocks.
- Today's curve score trailed nine 2 s blocks by about 4 dB on a synthetic tone.

Its gate 1 failed for a design error, not a measured one. Its +4.8 dB target was the weak-signal 5 log₁₀ N law, which
Kay II §7.3 states only for per-block SNR ≪ 1. The first round's thresholds (P = 1/200 per window, after a pitch
search) and P_D = 0.8 put the blocks outside that regime.

## What changes, and nothing else

1. **Gate 1's target comes from the operating point.**
   - A Monte Carlo of the four detectors on white Gaussian noise: the same block lengths, pitch grid and band, and the
     same empirical 1 − 1/200 threshold over the same search. That is 10,000 noise-only windows per method, and 1,000
     tone windows per level on a 0.25 dB grid.
   - It gives the predicted L80 gaps, C1 − C9 and C3 − C9, and the per-block SNR at L80.
   - The record states whether that SNR satisfies Kay's condition. Either way the Monte Carlo, not the law, is the
     target.
   - Gate 1 passes when the measured synthetic gaps on development background are within ±1 dB of that prediction.
   - The Monte Carlo is written and hashed before the synthetic gate runs.
2. **The level grid** runs from +12 to −20 dB in steps of 0.5 dB, so that every real clip reaches 80 %.
3. **Gate 2's target** is unchanged: the median paired C9 − C1 on the eight real clips is within ±1 dB of the earlier replay study’s.
   That target was fixed before any of our results; this round doesn't move it after seeing −2.0 dB.
   - If gate 2 fails again while gate 1 passes, the record reads it as a real difference from the earlier replay study’s measurement on
     its other background and detector, and stops.
   - It is not retuned.

## Unchanged from the first round

- **Methods:** C1, C3, C9 and T, with the same constant pitch search and the same ±10 s clock search, and no drift.
- **Data:** the 27 passes (8 for verification, 19 for the test) and Tier 1's nine development spans, scaled to the band
  median.
- **Thresholds:** the empirical 1/200 point of all 419 calibration segments.
- **Wrong flights:** the real prop traffic within 12 km and ±30 min (set A, deciding), and the other 26 tracks
  (set B, reported).
- **Rule:** a C method wins if its L80 on the test set is at least 3 dB below the better of C1's and T's.
- **Report:** paired per-pass levels, their spread, and how often a wrong flight wins.
- **Retune:** one counted.

## On the fleet

- **The Monte Carlo** is one small job, written to its own run folder.
- **Then the gates and the frozen test,** as the first round's `coherent_duration.py` units, on 4xlarge boxes, one
  search at a time. The traffic cuts are already in derived/.
