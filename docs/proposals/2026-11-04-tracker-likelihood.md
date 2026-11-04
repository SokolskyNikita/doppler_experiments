# A likelihood tracker for item 3 (proposal)

PLAN Phase 2 item 3, round 3. This is a design, written before any code or run.

**Why a new objective.** Rounds 1 and 2 rewarded each cell E − θ on the whitened dB image
([freqtrack](../experiments/2026-11-04-freqtrack.md), [hmm-tracker](../experiments/2026-11-04-hmm-tracker.md)).
Neither found a θ that is quiet on noise and still continuous on a pass. Round 2 shows the floor: with θ_cont below
about 7 dB, the best of about 800 correlated fundamentals stays above it in noise, so a noise track never ends.
This round replaces that reward with a likelihood, so that no dB threshold is left to set.

**decision:** whether item 3's tracker becomes this likelihood tracker, or stays `ridge()` with `hmmtrack` retired.

## Evidence: a log-likelihood ratio per cell

- **Normalised power.** Each cell's linear power P = |X|² (the package STFT) is divided by the frame's noise level
  across frequency, σ² = median(P over ±bg_hz) / ln 2, which gives z = P/σ². The median of an exponential is
  σ² ln 2. The noise level is Ramseier & Pieren's eq. 11 background. It was the better image for both trackers,
  though not as the package default ([whitening](../experiments/2026-11-04-whiten-frequency.md)). Invalid frames
  carry no evidence.
- **The two hypotheses.** In noise, z ~ Exp(1). With a tone of per-cell SNR a, z is Rician:
  f₁(z) = e^(−z−a) I₀(2√(az)). The log-likelihood ratio is ℓ(z; a) = −a + ln I₀(2√(az)). This is Kay I Ex. 7.16:
  the periodogram over the local noise level is the tone's log-likelihood with phase unknown, here at a fixed
  design SNR a rather than with the amplitude maximised out. A dip below the noise mean then costs log-likelihood
  in proportion to how unlikely it is under a tone, instead of a fixed θ.
- **Harmonics.** The state is the fundamental f₀, on a grid a quarter of a bin apart. Each observable harmonic
  h = 1..3 is present with prior probability q = 0.5, so its term is ln(1 − q + q·e^(ℓ_h)), and the terms add. A
  missing harmonic then costs at most ln 2, never an unbounded penalty.
- **Measurement.** Quinn & Hannan eq. 3.11 says harmonic j adds frequency information as j²·a_j. So each frame's
  f₀ is the inverse-variance combination of the per-harmonic estimates f_h/h, each measured on the original STFT
  (Quinn FTI(2), as now), with weights h²·Â_h². The present code weights by Â_h² alone.

## States and transitions

- **States:** OFF, ON(k) and DIP(k). DIP is a tone still present but below the noise, so its emission equals
  OFF's: log-likelihood ratio 0. It is Streit & Barrett 1990's track-lost state, and it keeps k so that a pass
  resumes on its own line.
- **Transitions:** each probability per frame of Δt = 0.25 s.
  - **Birth:** OFF → ON(k) with probability β·δf·Δt, where β is a birth prior per Hz per second and δf is the
    grid step. β sets the false-track rate directly.
  - **End of pass:** ON or DIP → OFF with probability Δt/T_pass.
  - **Into a dip:** ON → DIP with probability Δt/T_run.
  - **Out of a dip:** DIP → ON with probability Δt/T_dip.
  - **Frequency moves:** ON or DIP(k) → ON or DIP(k′) with a Laplace kernel in k′ − k, of scale 0.02·f per
    second, capped at round 2's physical bound of 0.25·f per second. The first draft's 0.1·f was amended before any
    run: a 60 m/s pass at 500 m CPA peaks at |df/dt|/f ≈ v²/(cR) ≈ 0.02 per second.
- **Fixed constants.** T_pass, T_run and T_dip are fixed before the run, from the development labels (Oyster Bay,
  the eagle cam): the median audible span, the median run between frames under noise and the median dip length.
  They never come from Livermore.
- **Decoding.** Forward–backward in log space, normalised per frame. Each frame's posterior that a tone is present
  is P(ON or DIP). A track is a maximal run of frames with that posterior above 0.5 that holds at least one ON
  frame, with k the posterior mode in each frame.
- **Families.** As in round 2: a second family is decoded after the first's cells (±4 bins) are excluded, then
  `resolve_crossings` and the harmonic links run.

## Knobs, picked on synthetic data only

There are two knobs: the design SNR a and the birth prior β.
- **The ROC.** On round 2's synthetic set (2 h of white noise in 12 windows over 150–250 Hz, and the weak pass:
  two straight passes, 3 seeds, amplitude 0.03 in 0.4 noise), compute the false-track rate and the weak-pass
  coverage at every point of a fixed grid: a ∈ {1, 2, 4, 8} and β ∈ 10^{−12, −11, …, −2} per Hz per second. The
  first draft stopped at 10⁻⁸. It was widened before any run, after the first Tier 0 run of the noise test: in noise,
  the best of about 500 fundamentals scores ℓ ≈ 4 in every frame, so the prior that keeps births rare can sit far
  below 10⁻⁸.
- **The pick, pre-registered:** among the grid points with at most 1 false track per hour per 100 Hz and a median
  weak-pass coverage of at least 0.5, the lowest β. Ties go to fewest fragments, then the higher a. If no point
  qualifies, the round stops there, and the record says so before any real recording is tracked.
- **Where it runs:** on the fleet, before the 29 passes are touched.

## Criterion and what is reported

- **Criterion:** round 1's, unchanged. On the 29 primary Livermore passes, at 2 % tolerance against the trajectory
  reference: a lower median error than `ridge()`, no more false bridges and no more fragments.
- **Reported beside it:**
  - the 11 flagged passes;
  - the 40–450 Hz run with no oracle band;
  - the development events (references written first, as in round 2);
  - runtime;
  - rounds 1 and 2.
- **Retune:** one counted retune after the first result, as always, written down before it runs.
- **Tier 0 tests:**
  - ℓ against the analytic Exp and Rician densities;
  - forward–backward against brute-force enumeration on a toy lattice;
  - round 2's five behaviour tests (missing fundamental, a steady tone, crossing passes, a dip, invalid frames);
  - the noise test.

## Out of scope: Quinn & Hannan's phase linking

Most of Quinn & Hannan's tracker gain comes from linking phase across contiguous blocks (§7.5). The tone's phase
at the next block is predicted, so the blocks integrate coherently, and the SNR gain grows with the number of
blocks linked, where magnitudes alone gain about its square root. Two things keep it out of this round:
- **It needs a different measurement.** The method needs unwindowed, contiguous blocks with a steady amplitude.
  Our frames are 2.048 s Hann windows at a 0.25 s hop, so they overlap eightfold. The phase of a Doppler-swept,
  propagated tone over 2 s is not predictable without a chirp state (f and df/dt) per cell. Linking would mean a
  complex-coefficient state, a new frame grid and its own measurement path.
- **This round asks a narrower question:** whether a likelihood objective removes the θ floor. If the result shows
  coverage limited by SNR rather than by the objective, phase linking is the next round's candidate, with its own
  design.
