# Coherent alignment duration for weak flyovers (proposal)

From the outside reviewer's advice (2026-11-04), as the PM adopted it. This is a design, written before any code or run.

**decision:** whether a 6 s or 18 s coherent scorer earns a test on the locator's shortlist, in the collective find's
weak-window case (the eagle cam's event 2, at 6 dB on half its frames). Otherwise the shortlist keeps today's scorer.

**Prior work.** Codex's [doppler-integration-coverage](/Users/nsokolsky/.codex/worktrees/60b9/doppler_track/docs/experiments/2026-11-04-doppler-integration-coverage.md)
record, read in place.
- With the true flight and clock supplied, 18 s of coherent integration against nine 2 s power blocks on eight real
  Livermore passes won 3, tied 2 and lost 3.
- On 28 passes, the 18 s phase concentration had a median of 0.36 with a ±2 Hz constant-offset search, and 0.11
  without one.
- Its replays used the Seattle home background, which is private and local-only. Nothing here touches it.

## The methods

All four read the same 18 s of audio, and each has the same constant pitch-offset search per candidate. None has any
freedom for drift (the [warp](../experiments/2026-11-04-warp.md) record found drift lifts wrong candidates more than
the true one).
- **C1:** nine 2 s blocks. **C3:** three 6 s blocks. **C9:** one 18 s block. **T:** today's trajectory-curve scorer.
  - C1 and T are the baselines.
- **The C methods:**
  - The audio is resampled to emission time by C's `warp.py`, for the candidate's trajectory and clock, so its tone
    becomes a stationary line. That aligns the waveform cycles.
  - Each block is one FFT. The block powers are added at each pitch bin, so the constant pitch search is the bins.
  - The statistic is the best pitch's summed power, over the median of the bins within ±20 Hz.
- **T:** `score.single_score` on the 2.048 s spectrogram, over the same pitch range.
- **The pitch range:** the pass's third-octave band ±10 %, so the pitch is inferred, not supplied. That is
  4·18 = 72 bins per Hz at C9, scaled to each block length.
- **The clock:** each candidate's CPA is searched over ±10 s, in steps of 0.25 s.

## Passes, backgrounds, levels

- **Passes:** 27 Livermore props from the 28 the coherence diagnostic took (`runs/2026-11-04-real-tone-coherence/`,
  dropping the jet N958JX_R50). Each is the original 18 s around its fitted CPA, with its own ambient, at 2 kHz.
  - **Verification set:** Codex's eight replays, N373DF_R06, N4004R_R19, N60RS_R11, N61NG_R37, N662EZ_R48,
    N784MB_R04, N795MM_R13 and N913TC_R15.
  - **Test set:** the other 19.
- **Backgrounds:** Tier 1's nine independent development spans, 7.2 h of waveform audio.
  - These are three xeno-canto Essex mornings (XC990819, XC990820, XC986433, CC BY-NC-SA) and six AeroSonicDB
    environment clips (CC BY-NC 4.0).
  - Each span's 18 s windows alternate between calibration and evaluation.
  - Each window is scaled to one fixed level: the set's median power in the pass's third-octave band.
- **Levels:** the added clip's band power against that background, from +12 dB to −18 dB in steps of 1 dB.
  - Each (pass, level) gets 10 evaluation windows, drawn by a seed and shared by every method.
- **Candidates:** the true flight and the other 26 passes' trajectories, each with the same clock and pitch search.
  - The hand-traced pitch is used only afterwards, to diagnose misses.

## Thresholds, and the decision rule fixed now

- **Calibration:** for each method, the full search (27 candidates × clocks × pitches) runs on every calibration
  window, and the window's maximum is kept.
  - The threshold is 1 false alarm per hour, P = 1/200 per window. It is read off a Gumbel fit to those maxima, with
    a bootstrap interval, using the verdict null's `gumbel()`. About 720 windows are too few for an empirical 1/200.
- **A trial recovers the pass** when its true flight wins the search and clears the threshold.
- **L80** is the lowest level at which at least 80 % of a set's trials recover.
- **The rule:**
  - **Win:** a C method wins if its L80 on the test set is at least 3 dB below the better of C1's and T's.
  - **Report:** the record also gives each pass's lowest recovering level, paired across methods; the spread across
    passes; and how often a wrong flight wins.
- **Verification first, then frozen.**
  - On an exact synthetic tone, C9 must gain within 1 dB of theory over C1 (+4.8 dB) and C3 (+3.0 dB).
  - On the eight verification passes, with the true flight and clock supplied, the methods' order must agree with
    Codex's.
  - Only then are the settings frozen and the test set run. There is one counted retune.

## On the fleet

- **Units:** (pass, level), 27 × 31 = 837, plus the calibration windows. They run as `shards.py` jobs on 4xlarge
  boxes, one unit at a time.
- **The cost** is the resampling: 27 candidates × 81 clocks per window, and the FFTs are cheap.
- **Inputs:** the Livermore WAVs and background audio, which are in raw/ and in the bucket already. No derived file
  is new, so the freeze on `runs seed` doesn't block it.
