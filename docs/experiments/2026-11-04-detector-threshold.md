# The detector's statistic, threshold and band

<!-- index
question: Does a calibrated detect statistic (S₁, then the reversed-window null S₂) or a wider band hold 1 false alarm per hour while keeping recall?
outcome: S1 failed the synthetic gate; wider S0 passed synthetic only; S2 is interrupted with partial files, no complete gate or Tier 1, and rescore-pool equivalence unverified
-->

> **Research reset status, 2026-11-04.** S2 is stopped and partial, not running. Local S2B0 contains
> noise.json and four pass files; S2B1/B2 contain no completed unit files. No complete S2 gate or real Tier1
> result exists locally. The process-pool rescore edit was stopped before its equivalence check, so it is
> unverified. S1's synthetic failure stands. The narrow-band S0 Tier1 failure below does not by itself
> establish failure of every wider-band S0 setting; those real-data comparisons were not completed. See [the
> audit](2026-11-04-research-reset.md).

## Question

PLAN Phase 2 item 6, to the design in [the proposal](designs/2026-11-04-detector-threshold.md), written
before any code ran.
- **Settings:** the statistic S₀ (today), S₁ (a z-score over the curve's frames with Harris's weight) or S₂ (the
  retune: S₀ less the search's maximum on the window reversed in time, standardised on the null), crossed with the
  band:
  - B0: 60–300 Hz on the 40–450 Hz image, today's;
  - B1: 60–900 Hz on a 40–1000 Hz image;
  - B2: 60–300 and 300–900 Hz searched apart.
- **Synthetic gate:** at 1 false alarm per hour on 2 h of noise, detection of the 0.03 passes at f0 ≤ 300 Hz no
  lower than S₀/B0's, and for B1 and B2 at least half the passes above 300 Hz. S₂'s gate also requires its
  threshold within a factor of 1.5 of Φ⁻¹(1 − 1/n), and detection no lower than S₀ in the same band.
- **Criterion, on Tier 1:**
  - ≤ 1 false alarm per countable hour on the pooled background (Essex and AeroSonicDB);
  - the positives keep today's 2 matched windows;
  - every development event's window in its span's top 10.

## Numbers so far

**The synthetic gate,** at 0.03 and 1 false alarm per hour (2026-11-04-detector-gate):

| Setting | Threshold | f0 ≤ 300 Hz | f0 > 300 Hz | Gate |
|---|---|---|---|---|
| S₀/B0 | 1.07 | 8/9 | 0/6 | baseline |
| S₀/B1 | 1.06 | 8/9 | 4/6 | passes |
| S₀/B2 | 1.08 and 1.16 | 8/9 | 4/6 | passes |
| S₁/B0 | 10.6 | 7/9 | 0/6 | stops |
| S₁/B1 | 8.6 | 7/9 | 3/6 | stops |
| S₁/B2 | 10.9 and 9.0 | 7/9 | 3/6 | stops |

S₁ fails because it is evaluated on the curve the search maximised, so it inherits the best-of-many tail. Its null
level σ_c is also unstable: the robust and the cross-window estimates differ by more than 20 % on 33–41 % of events.

**Already known, from the [tier1](2026-11-04-tier1.md) record:** at 1 false alarm per hour, S₀ keeps neither
labelled flyover. They score 4.28 and 2.46 against a threshold near 6. So item 6's criterion is out of reach for
every S₀ setting as the detector stands. That isn't fatal to the collective find, which takes the top k windows with
no threshold, but it is fatal to any thresholded release.

**S₂ (the counted retune):** not yet measured. Its three boxes were spot-interrupted after 208–224 min (about $3
in all), before two of them finished their noise unit. The noise unit gives each of about 200 candidates a second,
serial `fit_event` on its reversed window. The handoff in `tools/experiments/2026-11-04/cloud_jobs.md` says what to
change before relaunching.

## What a change would invalidate

A change to `detect` would regenerate the detections cache (kind `detections`, keyed by `cache.code_sha256`) and
Tier 1's span records, which are re-run, never edited. The saved fits are untouched. S₁ and S₂ live outside
`detect_events` (`tracks.rescore_z`, `tracks.rescore_null`), so the cache key is unchanged until a decision.

## Script and run folders

- **Scripts:** `tools/experiments/2026-11-04/detector_roc.py` (roc, gate); `tracks.rescore_z` and
  `tracks.rescore_null`.
- **Run folders** (in `$DOPPLERTRACK_DATA/runs/`):
  - S₀: 2026-11-04-detector-roc-s{1,2,3}of6;
  - S₁ (rerun): 2026-11-04-detector-roc-s1-s{4,5,6}of6;
  - S₂: 2026-11-04-detector-roc-s2-s{7,8,9}of9, running;
  - collected: 2026-11-04-detector-roc-collect;
  - the gate: 2026-11-04-detector-gate.
