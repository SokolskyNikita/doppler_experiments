# Model error of the straight-pass fit on Livermore, stage 1 (2026-11-04)

**Question** (PLAN Phase 2 item 2). How much of the fit error on real passes is model error, meaning a turning, climbing or accelerating aircraft fitted as a straight constant-speed pass? How much is measurement noise, and how much is the optimiser? Before that: how much does one pass's curve tell us at all?

## The information limit (read the rest against this)

**Setup.**
- **The bound.** It is the Cramér–Rao bound of the ideal straight-pass curve for (f0, v, R, τ), taken at each pass's own parameters. For Gaussian noise of covariance Σ the information is I = JᵀΣ⁻¹J, with J the numerical Jacobian of the Ferguson & Lo model (Kay I ch. 3; eq. 3.41 is the single-tone case).
- **Two noise structures:**
  - **Package.** The package's grid (a 2.048 s Hann window every 0.25 s) over each pass's ridge span. σ is 0.45 % of f0, the measured error of `tracks.ridge`. Frames are correlated 1, 0.91, 0.67, 0.40 and 0.18 at lags 0–4 (Harris 1978 eq. 17), used as a full Toeplitz covariance. The independent form divided by 3.9 gives a bound 1.14× smaller (range 1.07–1.19), so the full form is the one quoted.
  - **Ridge.** The published ridge's own sample times, every 0.19 s. σ and the autocorrelation (lags to 2 s, Bartlett-tapered) come from that pass's residuals about the trajectory curve, less their 5 s running median. This is the noise the stage-1 bootstrap draws from.
- **Position.** A single pass fixes only a distance from its track. So the bound is also given in metres:
  - in slant range;
  - in ground range from the track, R/L times the slant-range bound, with L the horizontal distance at CPA;
  - along the track as v times the τ bound, which counts only when the clock is known.

**Numbers**, package noise, median (IQR; largest):

| Passes | Slant range | f0 | v | τ | Slant range, m | Ground range, m | Along track, m |
|---|---|---|---|---|---|---|---|
| Livermore primary (29, 0.3–5.7 km) | 4.0 % (2.8–6.9; 21) | 0.18 % | 1.3 % | 0.27 s | 73 (largest 518) | 156 (98–249; 8,024) | 18 |
| Livermore flagged (11) | 3.1 % (2.6–7.7; 16) | 0.20 % | 1.0 % | 0.14 s | 55 (largest 154) | 70 | 13 |
| Development events (4, 2.5–6.1 km) | 1.6 % (0.9–2.3) | 0.10 % | 0.5 % | 0.18 s | 76 (largest 119) | – | 21 |

- **Ridge noise.** On the Livermore ridges' own noise the slant-range bound is close to the package one: a median 3.9 % on the primary passes and 8.2 % on the flagged ones.
- **The bootstrap sits at the bound.**
  - On the ideal curve with ridge noise (curve C+noise below), the bootstrap SD over the ridge bound is 1.00 for slant range (IQR 0.95–1.03, largest 1.18), 1.00 for speed and 1.02 for f0 on the primary passes. So on straight passes neither the optimiser nor the noise model adds spread beyond the information in the data.
  - It is wider only on three short, flagged passes: R41 2.3×, R36 2.4× and R44 1.5×.
- **Large ground-range numbers** (R17 at 8 km, R13 at 2.9 km, R50 at 3.0 km) come from near-overhead passes, where L is small next to R. There, a slant range doesn't fix a ground range.

**What it says for PLAN.**
- **Information is not the limit.** One pass carries enough information for its distance from the track to well under 1 km at 1–6 km: about 50–500 m slant range, and about 100 m on the development events.
- **Model error is the limit.** The straight-pass fit of the noiseless trajectory curve misses the slant range by a median 229 m on the primary passes, 2.9 times the bound. 5 of 40 passes miss by more than 1 km (below).
- **One pass can't give a position.** It gives a distance from a track, not a position, and its error is set by model error. A 1 km answer has to come from several events per recording (item 7), and from a model or a weighting that copes with the passes that aren't straight.

## Model error, noise and the optimiser

**Setup.** No change to the package.
- **The fit.** `tools/experiments/2026-11-04/straight_pass_ls.py` is the Ferguson & Quinn reduced least-squares fit: α and β in closed form, a search over (τ, s).
  - Starts come from Ferguson & Lo eqs. 10–14, plus a grid of τ across the track ±30 s and s over its bounds.
  - Bounds are v 10–300 m/s and R 100 m–30 km.
  - Its signature is `fit(times, freqs, weights, c)`, so Phase 2 item 4's fit can be tested against it.
- **Reference.** Built from the audit's reconstructed microphone, PCHIP through the KML and c at 15 °C:
  - R*, the slant range at the 3-D CPA; v*, the speed there; τ*, the emission CPA time;
  - f0*, the audit's fitted rest frequency: a model quantity, not an observation.

  The ridge is moved by the audit's per-pass clock shift.
- **Curves at each ridge's sample times:**
  - C, the ideal straight pass (f0*, v*, R*, τ*);
  - A, the trajectory curve f0*·g(t), noiseless;
  - B, which is A plus noise, and C+noise likewise: 200 replicates of a moving-block bootstrap (2 s blocks) of the ridge's residuals about A, less their 5 s running median;
  - D, the published ridge.
- **The noise model is the sub-5 s part only.** Slower ridge wander (wind, say) is removed along with model error. The f0-drift perturbation is where slow change is studied.
- **Noise level.** It is a median σ (MAD) of 1.8 Hz, with lag-1 autocorrelation 0.32; the slow part is 1.9 Hz RMS.
- **Failed replicates.** 4 of the 8,000 B replicates gave a speed above sound and were left out.
- **The fit's spread** is the bootstrap SD over B, per pass.
- **Criterion**, fixed before running: a perturbation enters the model only if it moves a fitted parameter on curve A by more than that pass's bootstrap SD, on the median primary pass.
- **A bug fixed before these numbers.** The first run optimised τ as an absolute unix time. Its finite-difference steps and step tolerance scaled with 1.8 × 10⁹ s, and it stopped early on 30 of 40 noiseless ideal curves. Fitted relative to the track, both start grids recover all 40 to 10⁻¹². That run (`runs/2026-11-04-model-error/`) is superseded.

**Errors against the reference**, primary passes, median and median |·| (signed IQR):

| Curve | f0 | v | R | τ |
|---|---|---|---|---|
| C, ideal | 0 | 0 | 0 | 0 |
| C+noise | 0.00 %, 0.02 % | +0.02 %, 0.06 % | +0.09 %, 0.17 % | 0.00 s, 0.01 s |
| A, trajectory | −0.20 %, 0.65 % (−0.9 to +0.4) | −2.6 %, 3.0 % (−8.2 to +0.7) | −3.5 %, 15.6 % (−19.3 to +4.0) | +0.45 s, 0.93 s |
| B, trajectory + noise | −0.27 %, 0.66 % | −2.5 %, 3.0 % | −3.6 %, 15.3 % | +0.44 s, 0.92 s |
| D, published ridge | −0.29 %, 0.83 % | −0.5 %, 4.8 % | −3.0 %, 15.0 % (−17.7 to +8.8) | +0.30 s, 1.12 s |

The flagged 11, median |·|: A gives f0 1.5 %, v 11.0 %, R 15.3 %, τ 1.3 s. D gives f0 3.2 %, v 19.1 %, R 34.3 %, τ 2.0 s.

- **Model error by range.** A's |R| error is a median 13.1 % below 2 km (22 passes), 21.8 % at 2–4 km (14) and 2.5 % above 4 km (4). Model error is not a fixed fraction of range.
- **Does model error plus noise explain the real fit?** No. fit(D) differs from mean(B) by a median |z| of 2.5 in R and 3.0 in v on the primary passes (flagged: 2.5 and 4.4). The real ridges carry slow structure (below 5 s it is in the noise model, above it isn't) or a mismatch with the trajectory that curve A doesn't have.
- **The textbook covariance on these ridges.**
  - The classical σ²(JᵀJ)⁻¹ is 0.86–0.90 of the bootstrap SD.
  - A Newey–West sandwich with 8 lags (the overlap span, set by hand) is 1.5–1.6 times it at fit(A+noise), and 1.3–1.4 at fit(D).
  - The ridge's own samples are only weakly correlated (lag 1: 0.32). Harris's 3.9 is for the package grid, not for these ridges.
  - The sandwich runs wide because its residuals include the model misfit, which it counts as noise. White 1982 §3's point is that under misspecification neither form measures the spread about the truth.

**Perturbations of A**, one at a time. |Δ|/SD is on the median primary pass; "n > 1" counts primary passes over 1:

| Perturbation | f0 | v | R | τ | Enters |
|---|---|---|---|---|---|
| f0 drift ±0.5 % over the span | 0.2 | 1.2 (21/29; Δ ∓1.5 %) | 0.8 (Δ ∓2.3 %) | 0.4 | yes |
| f0 drift ±1 % | 0.4–0.5 | 2.5 (26/29; Δ ∓3.0 %) | 1.5–1.6 (Δ ∓4.6 %) | 0.8 | yes |
| f0 drift ±2 % | 0.8–1.0 | 4.9 (29/29; Δ ∓6.0 %) | 3.0–3.2 (Δ ∓9.2 %) | 1.6 | yes |
| Sound speed from KLVK temperature | 0.07 | 0.78 (13/29; Δ −1.1 %) | 0.29 (Δ −1.0 %) | 0.04 | no |
| Wind from the OAK sounding (c + w·n) | 1.49 (20/29; Δ −0.06 %) | 0.17 | 0.12 | 0.17 | yes, in f0 only |
| Linear interpolation | 0.27 | 0.35 | 0.25 (Δ +0.4 %) | 0.27 | no |
| Smoothing spline | 0.35 | 0.52 | 0.43 (Δ +0.4 %) | 0.41 | no |
| Track height + N (−31.8 m, EGM96) | 0.06 | 0.06 | 0.31 (Δfit −1.3 %, Δref −27 m) | 0.07 | no |
| Recorder at Terrarium + 1.5 m | 0.01 | 0.01 | 0.03 (Δref +3 m) | 0.01 | no |
| Full ±150 s window, noiseless | 6.3 | 7.2 | 7.7 (Δ −16.7 %) | 11.7 | yes |

On the flagged 11, every |Δ|/SD median is below 1 except drift ±2 % in v (1.8) and the full window (2.4–4.4): their spread is larger.

**Approach against recede**, White's two estimators. Each half is fitted with τ and s held at the full fit, so each gives its own f0 and v; a straight pass gives the same from both.
- **Primary, A (model error alone):** recede minus approach is a median |0.19 %| in f0 and |0.86 %| in v, at |z| 0.8 and 1.6 against the bootstrap spread of that difference.
- **Primary, D:** |0.36 %| in f0 and |0.56 %| in v, at |z| 1.8 and 1.5.
- **What D's excess means.** A linear drift δ over the span splits the halves' f0 by about δ/2, so D's excess over A is consistent with drifts of a few tenths of a percent, around the 0.5 % at which drift starts to matter. The halves can't separate drift from model error.
- **Free halves.** With all four parameters free, each half's far asymptote is unconstrained: f0 differences of 11–24 % at |z| below 0.7. They are uninformative.

**dopplerprint's hypothesis**, a median 14 % slant-range miss for a straight-pass fit to the noise-free ADS-B curve:
- Over all 40 passes, A's median |R| error is 15.5 % on the ridge span, signed median −3.4 %.
- Over the full ±150 s window it is 35.6 %, signed −32 %.
- The stated test was the full window within ±5 points of 14 %, so **as stated it is not reproduced**. The ridge-span figure does match it.
- Fitting more of the trajectory makes the straight-pass fit worse, because the aircraft turn and change height over 5 minutes.

**Outcome.**
- **The fit's error on real passes is model error.** The optimiser is exact on straight curves, and noise moves slant range by a fraction of a percent, at the Cramér–Rao bound. The trajectory curve alone misses slant range by a median 15.6 % and speed by 3.0 %, as large as the real ridges' 15.0 % and 4.8 %.
- **Model error is about 3 times the information limit** on the median pass, and over 1 km on 5 of 40.
- **What enters the model:**
  - **f0 drift.** 0.5 % over a pass moves speed by more than the fit's spread on 21 of 29 passes, and the half-fits allow drifts of that size. So a drifting f0 (one more parameter) is the first candidate for a heavier model, measured against the half-fit differences.
  - **Wind.** It crosses the threshold only in f0, by 0.06 %, because f0's spread is tiny. It doesn't move speed or range, so it isn't worth modelling for location.
  - **The window.** It enters strongly, the wrong way: on real trajectories a longer window is worse, so windows should stay with the observed tone.
- **What doesn't enter:** sound speed from the temperature, interpolation (linear, PCHIP or spline), the geoid datum and the recorder height all stay below the spread on the median pass.
- **The textbook covariance can't be the spread.** On a wrong model it is about right (classical) or 1.5× wide (sandwich) only by accident. The bootstrap, or the bound for the straight-pass part, is what to report.
- **Not yet run:**
  - stage 2: `fit_event` on rendered C and A curves and on the real WAVs;
  - stage 3: Alaska, as an independent check of total error.

  The whitening floor and window and synthesised waveforms are left for a later round.

**Scripts:** `tools/experiments/2026-11-04/straight_pass_ls.py`, `model_error.py`, `model_error_summary.py`, `crb.py`. **Outputs:** `runs/2026-11-04-model-error-2/` (`fits.csv`, `perturbations.csv`, `halves.csv`, `noise.csv`, `summary.json`) and `runs/2026-11-04-crb/` (`crb.csv`, `crb_summary.json`). Weather: `raw/aux/metar/KLVK_*`, `RAOB_KOAK_*`.
