# Model error of the straight-pass fit on Livermore, stage 1 (2026-11-04)

<!-- index
question: How much of the straight-pass fit's error on Livermore is model error, noise or the optimiser, and what is the information limit?
outcome: Model error: a median 15.6 % in slant range from the trajectory curve alone, about 3× the Cramér–Rao bound (3.4–4.0 %, 63–74 m, provisional covariance); noise sits at the bound and the optimiser is exact. f0 drift of 0.5 % enters; temperature, interpolation and datum don't
-->

**Question** (PLAN Phase 2 item 2). How much of the fit error on real passes is model error, meaning a turning, climbing or accelerating aircraft fitted as a straight constant-speed pass? How much is measurement noise, and how much is the optimiser? Before that: how much does one pass's curve tell us at all?

## The information limit (read the rest against this)

**Setup.**
- **The bound.** It is the Cramér–Rao bound of the ideal straight-pass curve for (f0, v, R, τ), taken at each pass's own parameters. For Gaussian noise of covariance Σ the information is I = JᵀΣ⁻¹J, with J the numerical Jacobian of the Ferguson & Lo model (Kay I ch. 3; eq. 3.41 is the single-tone case).
- **Two noise structures:**
  - **Package, provisional.** The package's grid (a 2.048 s Hann window every 0.25 s) over each pass's ridge span, with σ 0.45 % of f0, the measured error of `tracks.ridge`.
    - **The frame correlation is modelled, not yet measured.** c(r) is the Hann window's own autocorrelation at multiples of the hop (Harris 1978 eq. 17, every lag): 1, 0.906, 0.672, 0.400, 0.183, 0.058, 0.010, 0.0005, 0. That is the correlation of the complex transform coefficients. A frequency estimate taken from their magnitudes correlates to first order as c(r)².
    - **Bounds as a range.** Both Toeplitz matrices are positive semi-definite. The bound is given as a range: c² (the model) to c (conservative).
    - **Check.** The independent form divided by the c² sum, 3.94, agrees with c² to within 2 %.
    - **Correction.** An earlier version of this record used the lags truncated to 0–4 (1, 0.91, 0.67, 0.40, 0.18, then zeros). That matrix is not positive semi-definite (smallest eigenvalue −0.095), so the bound built on it was not a Fisher information and is withdrawn (`runs/2026-11-04-crb/`).
    - **Next.** The package column stays provisional until the covariance is measured from synthesised waveforms passed through `tracks.ridge` on the package's grid.
  - **Ridge.** The published ridge's own sample times, every 0.19 s. σ and the autocorrelation (lags to 2 s, Bartlett-tapered) come from that pass's residuals about the trajectory curve, less their 5 s running median. This is the noise the stage-1 bootstrap draws from.
- **Position.** A single pass fixes only a distance from its track. So the bound is also given in metres:
  - in slant range;
  - in ground range from the track, R/L times the slant-range bound, with L the horizontal distance at CPA;
  - along the track as v times the τ bound, which counts only when the clock is known.

**Numbers**, package noise (provisional), median over passes, given as c² to c (largest, c² to c):

| Passes | Slant range | f0 | v | τ | Slant range, m | Ground range, m | Along track, m |
|---|---|---|---|---|---|---|---|
| Livermore primary (29, 0.3–5.7 km) | 3.4–4.0 % (18.7–21.5) | 0.15–0.17 % | 1.1–1.3 % | 0.23–0.27 s | 63–74 (464–534) | 135–157 | 16–18 |
| Livermore flagged (11) | 2.6–3.0 % (14.1–15.8) | 0.17–0.19 % | 0.8–1.0 % | 0.12–0.14 s | 47–55 (133–153) | 61–70 | 11–13 |
| Development events (4, 2.5–6.1 km) | 1.3–1.6 % (2.0–2.3) | 0.09–0.10 % | 0.4–0.5 % | 0.15–0.18 s | 66–77 (103–120) | – | 18–21 |

- **Ridge noise.** On the Livermore ridges' own noise the slant-range bound is close to the package one: a median 3.9 % on the primary passes and 8.2 % on the flagged ones.
- **The bootstrap sits at the bound.**
  - On the ideal curve with ridge noise (curve C+noise below), the bootstrap SD over the ridge bound is 1.00 for slant range (IQR 0.95–1.03, largest 1.18), 1.00 for speed and 1.02 for f0 on the primary passes. So on straight passes neither the optimiser nor the noise model adds spread beyond the information in the data.
  - It is wider only on three short, flagged passes: R41 2.3×, R36 2.4× and R44 1.5×.
- **Large ground-range numbers** (R17 at 7–8 km, R13 at about 2.5–2.9 km, R50 at 2.7–3.1 km) come from near-overhead passes, where L is small next to R. There, a slant range doesn't fix a ground range.

**What it says for PLAN.**
- **Information is not the limit.** One pass carries enough information for its distance from the track to well under 1 km at 1–6 km: about 50–500 m slant range, and about 100 m on the development events (provisional package model; the measured ridge-noise bound agrees).
- **Model error is the limit.** The straight-pass fit of the noiseless trajectory curve misses the slant range by a median 229 m on the primary passes, 2.8–3.2 times the bound. 5 of 40 passes miss by more than 1 km (below).
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
| C+noise, bias of the mean over 200 replicates | 0.00 %, 0.02 % | +0.02 %, 0.06 % | +0.09 %, 0.17 % | 0.00 s, 0.01 s |
| C+noise, one fit's spread (bootstrap SD, median) | 0.17 % | 1.1 % | 3.7 % (75 m) | 0.23 s |
| A, trajectory | −0.20 %, 0.65 % (−0.9 to +0.4) | −2.6 %, 3.0 % (−8.2 to +0.7) | −3.5 %, 15.6 % (−19.3 to +4.0) | +0.45 s, 0.93 s |
| B, trajectory + noise | −0.27 %, 0.66 % | −2.5 %, 3.0 % | −3.6 %, 15.3 % | +0.44 s, 0.92 s |
| D, published ridge | −0.29 %, 0.83 % | −0.5 %, 4.8 % | −3.0 %, 15.0 % (−17.7 to +8.8) | +0.30 s, 1.12 s |

C+noise's per-fit spread on the flagged 11 is 0.41 % in f0, 2.6 % in v, 8.4 % (136 m) in R and 0.40 s in τ. The flagged 11, median |·|: A gives f0 1.5 %, v 11.0 %, R 15.3 %, τ 1.3 s. D gives f0 3.2 %, v 19.1 %, R 34.3 %, τ 2.0 s.

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
- **The fit's error on real passes is model error.**
  - The optimiser is exact on straight curves.
  - Noise gives one fit a spread of about 4 % in slant range (3.7 %, 75 m, on the median primary pass), at the Cramér–Rao bound, with a negligible bias of the mean (0.17 %).
  - The trajectory curve alone misses slant range by a median 15.6 % and speed by 3.0 %, as large as the real ridges' 15.0 % and 4.8 %. That 15.6 % is to be read against the 4 % a single fit's noise allows.
- **Model error is about 3 times the information limit** (2.8–3.2×) on the median pass, and over 1 km on 5 of 40.
- **What enters the model:**
  - **f0 drift.** 0.5 % over a pass moves speed by more than the fit's spread on 21 of 29 passes, and the half-fits allow drifts of that size. So a drifting f0 (one more parameter) is the first candidate for a heavier model, measured against the half-fit differences.
  - **Wind.** It crosses the threshold only in f0, by 0.06 %, because f0's spread is tiny. It doesn't move speed or range, so it isn't worth modelling for location.
  - **The window.** It enters strongly, the wrong way: on real trajectories a longer window is worse, so windows should stay with the observed tone.
- **What doesn't enter:** sound speed from the temperature, interpolation (linear, PCHIP or spline), the geoid datum and the recorder height all stay below the spread on the median pass.
- **The textbook covariance can't be the spread.** On a wrong model it is about right (classical) or 1.5× wide (sandwich) only by accident. The bootstrap, or the bound for the straight-pass part, is what to report.
- **Stage 3,** Alaska as an independent check of total error, is the section after stage 2.

  The whitening floor and window and synthesised waveforms are left for a later round.

## Stage 2: the pipeline's fit

**Setup.** `tracks.fit_event`, imported unchanged, run with both objectives over each pass's ridge span on four spectrograms:
- the ideal curve C and the trajectory curve A, each drawn as a noiseless one-bin ridge on the package's grid (0.488 Hz × 0.25 s);
- the pass's own WAV through `compute_spectrogram`;
- the same WAV with the package's shipped 40–450 Hz band (wav-450), the fit's band clipped to it.

The rendered and WAV inputs reach max(450 Hz, 1.5 × the ridge's top). Each row records the share of the trajectory curve over the ridge span inside its band: 1.00 on every pass for C, A and wav.

**Numbers**, primary passes, median |error| in slant range (passes over 10 %), with speed, f0 and τ:

| Input | Contrast objective | Brightness objective | LS (stage 1) |
|---|---|---|---|
| C, ideal, rendered | 0.2 % (6/29); v 0.1 %, τ 0.02 s | 5.0 % (13/29); v 2.1 %, τ 0.13 s | 0 (C) |
| A, trajectory, rendered | 30.8 % (23/29); v 17.7 %, f0 1.2 %, τ 2.6 s | 36.3 % (23/29); v 22.2 %, τ 5.9 s | 15.6 % (A) |
| wav, real audio | 28.7 % (24/29); v 11.9 %, f0 1.4 %, τ 1.5 s | 21.4 % (21/29); v 10.5 %, τ 1.7 s | 15.0 % (D, published ridge) |
| wav-450, shipped band | 32.2 % (19/23 fitted); v 15.7 % | 25.0 % (18/23); v 10.5 % | – |

On the flagged 11: A-render is 50.7 % (contrast) and 26.7 % (brightness), and wav is 18.7 % and 8.6 %.

- **`fit_event` on noiseless ideal curves.** Contrast is exact at the median but fails on 11 of 40 (6 of 29 primary): R44, R04, R19, R16, R21, R18, R60, R50, R45, R51, R48. Seven of them (R04, R19, R16, R21, R50, R45, R51) follow one pattern: speed and slant range 57–92 % low, with τ 7–31 s late. The fit locks onto one flank as a slow, close pass. Brightness fails on 17 of 40, mostly overestimating (R up to +98 %). The least-squares fit recovers all 40 exactly. So the grid-search and Nelder–Mead fit has an optimiser and objective error of its own, before any model error.
- **On trajectory curves `fit_event` doubles the model error,** about 31–36 % against least-squares' 15.6 %. On the real WAVs it gives 21–29 %, against least-squares' 15.0 % on the author's published ridge. So Phase 2 item 4's least-squares track fit has room to halve today's fit error on these passes, even before any heavier model.
- **An earlier attempt misled.** In the aborted stage-2 runs the crop topped out at 450 Hz, and R20's ideal curve "missed" by −94 %. With the full band it doesn't. Those runs are kept as `runs/2026-11-04-model-error-stage2-aborted*/` and superseded.

**The shipped band (PLAN item 6).**
- **What the shipped band loses.** With the package's 40–450 Hz band, 8 of the 40 Livermore passes are invisible: the whole curve lies above 450 Hz (R44, R35, R45, R21, R41, R60, R22, R24). 9 more are partly above it, with 44–98 % of the curve inside. Ten passes have a rest frequency above 450 Hz, up to 868 Hz.
- **What it does to the fits.** Where the whole curve is in band, wav-450 gives the same fits as wav. On the partly-in-band passes the contrast fit misses slant range by −69 % to +91 %.
- **A crash.** On three passes whose clipped band misses the curve (R35, R08, R51, band 342–450 or 414–450 Hz), `fit_event` raises `ValueError: attempt to get argmax of an empty sequence` inside `grid_search`, instead of returning a weak fit.
- **So, as shipped, the pipeline can't use 20 % of these passes, and fits another 22 % on a truncated curve.** The band should follow the tone, or the harmonics should be searched (item 6).

**Scripts:** `tools/experiments/2026-11-04/model_error_stage2.py`. **Outputs:** `runs/2026-11-04-model-error-stage2/stage2.csv` (one row per pass, input and objective, with `frac_curve_in_band` and any error).

## Stage 3: Alaska, an independent check of total error

**Setup.** The Alaska geophone crossings (Seppi, Tape & Fee 2025): seismic nodes along the Parks Highway, February–March 2019, vertical channel at 500 samples/s. There are no trajectories, only Flightradar24's CPA parameters, so stage 1's model-error split isn't possible here; this measures fit against reference.
- **Fit:** `tracks.fit_event`, imported unchanged: contrast objective, one harmonic, over the FR24 CPA time ±60 s, on a 2.048 s Hann / 0.25 s spectrogram from the raw counts, in 40–240 Hz (below the 250 Hz Nyquist). Run at three sound speeds: c = 340.3 m/s (the package's 15 °C), the authors' fitted c for that crossing, and c from the measured air temperature, 331.3·√(1 + T/273.15).
- **Temperature:** IEM ASOS, from the station nearest the crossing's node with a report within 1 h of the FR24 CPA time, using the report nearest in time (`raw/aux/metar/PA*_2019-02-12.csv`).
  - Stations along the highway: Talkeetna PATK, McKinley Park PAIN and Nenana PANN report hourly; Chulitna PAEC reports about 5 times a day. IEM has nothing for Healy PAHV or Cantwell PATW after 2011–12.
  - Over the 50: PATK 22, PAIN 13, PAEC 9, PANN 6. Distance median 26 km, up to 71 km where a nearer station had no report that hour. Node minus station elevation −227 to +313 m. Report median 18 min from CPA.
  - T −18 to +6 °C, so c_T 320–335 m/s, median 327.4. The authors' fitted c averages 19 m/s below c_T (SD of the difference 10.6 m/s, correlation with c_T −0.22).
  - This is ground temperature at a station, not along the path to an aircraft a few hundred metres up, and Alaskan winter inversions make the two differ; no lapse or inversion correction is applied.
- **Reference:** FR24's slant range, √(horizontal distance² + (altitude − node elevation)²), and speed. The authors' own fitted speed and slant range sit beside it.
- **Only speed, slant range and τ are compared;** f0 depends on which harmonic the fit locks to.
- **Sample:** 50 of the authors' 789 non-jet fitted crossings. The first 24 are those a stopped full run had finished, which goes through the file in date order; the other 26 were drawn with seed 20261104 from the remainder. They cover 36 flights at 44 nodes on 22 days: 14 C185, 10 PA31, 8 PC12, 7 PA46 and 11 others. FR24 slant ranges are 624 m to 8.0 km, median 1.9 km; median speed is 83 m/s.

**Numbers**, against FR24, median (IQR), and the share of crossings missing slant range by more than 20 %:

| Fit | Slant range | over 20 % | Speed, median abs | τ, median abs |
|---|---|---|---|---|
| `fit_event`, c = 340.3 m/s | +1.2 %, abs 6.9 % (−6.7 to +6.5) | 20 % | 6.3 % (median +5.5 %) | 1.6 s |
| `fit_event`, authors' c (median 310 m/s) | −8.2 %, abs 10.1 % | 24 % | 5.2 % | 1.7 s |
| `fit_event`, station-temperature c (median 327 m/s) | −3.3 %, abs 6.8 % (−9.0 to +2.3) | 22 % | 3.2 % (median +1.2 %) | 1.6 s |
| The authors' own fits | −9.3 %, abs 12.8 % | 22 % | 4.4 % | – |

The c = 340.3 m/s and authors'-c rows are from the rerun of all three settings (`runs/2026-11-04-model-error-alaska-ctemp/`), and match the first run's to the last digit.

**Outcome.**
- **The first independent number for our fitter at close range.** On real passes at a median 1.9 km, `fit_event` at the package's sound speed misses slant range by a median 6.9 %, against the authors' own 12.8 %. That sits beside stage 2's 29 % on Livermore's farther, longer passes (median 2.2 km reference, ridges of about 30–170 s). The fitter does far better on these close crossings, fitted over ±60 s, than on Livermore's passes, many of which turn (stage 1). The Alaska straightness can't be checked: FR24's CPA parameters are all there is. That is consistent with stage 1's finding that model error, not the fitter's noise, drives the Livermore numbers, though it is a different microphone (a geophone), a different site and a different traffic mix.
- **The authors' c makes the fit worse.** Their median 310 m/s, against the package's 340.3 m/s, moves slant range from 6.9 % to 10.1 % and its bias from +1.2 % to −8.2 %. Their c is fitted jointly with everything else, so it carries their model's error. That bears on stage 1's sound-speed perturbation: a c that is "right" for a jointly fitted model isn't automatically right for ours.
- **The measured temperature fixes speed.** At c_T, the speed error falls from 6.3 % to 3.2 % and its bias from +5.5 % to +1.2 %. Slant range barely moves in absolute terms (6.9 % to 6.8 %), but its bias goes from +1.2 % to −3.3 %. At 340.3 m/s, then, the range looked unbiased because a c about 4 % too high cancelled a range that comes out about 3 % short at the right c. That short range, with speed right, is what's left for model error to explain.
- **The fit absorbs none of a c error.** Changing c moves both speed and slant range by exactly the same fraction: d ln v / d ln c and d ln R / d ln c are 1.000 at the median over all 50 crossings (IQR 0.996–1.003 for v and 0.990–1.009 for R, between 340.3 m/s and c_T). The curve fixes v/c, through its asymptotes, and R/v, through how fast it crosses, so a c error of x % passes in full into speed and from there in full into range.
- **Item 2 outcome: the pipeline should take a measured temperature.** The shipped pipeline has no sound-speed input: `speed_of_sound()` defaults to 15 °C (340.3 m/s), and every caller in `tracks.py`, `search.py`, `score.py`, `pipeline.py`, the CLI and the bench runner uses that default. Where a station temperature exists for the recording's hour, `speed_of_sound(T)` is the input it should take. On these crossings that would have removed a 4 % speed bias, and, since range scales with c, a 4 % range error the fit can't see.

**All 788 crossings** (the fleet rerun: `runs/2026-11-04-merge-alaska/`, merged from `runs/2026-11-04-model-error-alaska-s{1..8}of8`, commit 5df450b).
- **Setup.** The band is 0.70–1.50 × the authors' best-determined tone, fitted at all three sound speeds. 775 crossings have all three fits.
- **The 13 others lack a station report within 1 h of the CPA,** so they have no temperature setting. No fit was weak and none raised.
- **The sample.** Median FR24 slant range 1.46 km and speed 63 m/s; 425 are C185s.

Median against FR24, with 95 % bootstrap intervals over crossings (`intervals.json`):

| Fit | Slant range, median | Slant range, median abs | over 20 % | Speed, median | Speed, median abs |
|---|---|---|---|---|---|
| `fit_event`, 340.3 m/s | −1.4 % (−2.3 to +0.2) | 11.9 % (10.5–13.1) | 33 % | +3.4 % (3.0–3.9) | 5.4 % (5.0–5.8) |
| `fit_event`, authors' c (median 310 m/s) | −10.8 % (−11.9 to −9.0) | 15.3 % (14.1–16.7) | 38 % | −6.3 % | 6.9 % |
| `fit_event`, station temperature (median 328 m/s) | −5.0 % (−6.3 to −3.9) | 12.1 % (10.9–13.4) | 33 % | −0.4 % (−0.8 to +0.1) | 3.6 % (3.2–4.0) |
| The authors' own fits | −10.3 % (−11.7 to −9.2) | 14.5 % (13.6–15.5) | 34 % | −6.2 % | 6.7 % |

- **The 50's ordering holds on all 788.** The station temperature takes the speed bias to zero within its interval (−0.4 %), against +3.4 % at 15 °C. The 15 °C slant range's small bias is again a cancellation of a c too high against a range that comes out short (−5.0 % at the right c). The authors' c is the worst of the three.
- **The fit still passes a c error through unattenuated.** d ln v / d ln c and d ln R / d ln c are 1.000 at the median.
- **The spread is wider than on the 50** (12 % against 7 % median abs). This is a narrower band on a larger, more varied sample; the 50 used the full 40–240 Hz. The stage 3 numbers above are the 50 at the wide band, and these are the whole set at the narrow band.
- **The narrow band no longer costs fits.** 0.70–1.50 × the tone gave no weak fit on any crossing (item 6).

**A failed run, kept and marked: `runs/2026-11-04-model-error-alaska-narrow/`.** It was meant to fit all 789 in a narrow band placed on the authors' best-determined tone (0.85–1.15×; their f0 placed the band and never entered the comparison).
- **The crash.** 655 crossings raised `ValueError: attempt to get argmax of an empty sequence`. `grid_search` searches f0 over (1.15·f_lo, 0.85·f_hi), which assumes the band holds a whole Doppler span. With f_hi/f_lo = 1.15/0.85 that range collapses to a point: 654 of the failures had no f0 candidate at all. The 134 that "ran" had exactly one, left by floating-point rounding. So `fit_event` needs f_hi/f_lo above about 1.35 or it crashes. This is also the real cause of stage 2's crash on R35, R08 and R51.
- **The 134 that ran are a biased sample,** fitted with a single f0 candidate. Their c = 340.3 slant-range error is a median 20.3 % over all 134. On the 7 of them that are also in the wide-band 50, it is 45.7 % against the wide band's 18.4 % on the same 7. Read that only as "a single fixed f0 fits badly", not as a band comparison.
- **A corrected rerun is queued, not started.** All 789 with the band at 0.70–1.50× the tone: f0 range 0.805–1.275×, wide enough for the span up to about 120 m/s at c = 310 m/s. It waits for an idle machine: `runs/2026-11-04-model-error-alaska-band070/command.sh`.

**Scripts:** `tools/experiments/2026-11-04/alaska_to_npz.py` (the one-off obspy conversion), `model_error_alaska.py` (`--same-as` reruns an earlier run's crossings), `model_error_alaska_summary.py` (the table and the c slopes). **Outputs:** `runs/2026-11-04-alaska-npz/`; `runs/2026-11-04-alaska-weather/` (the station fetch); `runs/2026-11-04-model-error-alaska-ctemp/` (the 50 at all three settings, `summary.json`); `runs/2026-11-04-model-error-alaska/` (the wide-band 50 at two settings: `alaska.jsonl`, `alaska.csv`); `runs/2026-11-04-model-error-alaska-stopped/` (the first full run, stopped at about 150 crossings and never written); `runs/2026-11-04-model-error-alaska-narrow/` (failed, as above).

## Heavier models: one extra parameter

**Question.** Does a pass model with one more parameter cut stage 1's model error? The candidates:
- **drift:** a linear f0 drift, f0(1 + η·u/T), with u the emission time from CPA and T the ridge span;
- **accel:** a constant along-track acceleration, x = v·u + ½·a·u², so v is the speed at CPA.

Each is fitted as a forward model in emission time, with f0 and f0·η in closed form. Bounds: a within ±3 m/s². η within ±5 % was meant as a bound too, but η is solved in closed form, so in the fits it is unbounded; the ±5 % applies only to its profile grid.

**Criterion, fixed before running.** A model enters if, on curve A:
- it cuts the primary passes' median |R − R*| from 229 m to at most 160 m;
- it doesn't worsen the flagged passes' median;
- its extra parameter is identified on at least two thirds of the primary passes.

Identified means: on A plus one stage-1 noise replicate, the parameter's profile Δ = (RSS(p) − RSS_min)/(σ²·κ) stays at or below 3.84 only on an interval that is finite on both sides inside the bounds. σ² is the sub-5 s noise variance, and κ the pass's (bootstrap SD / classical SD)² of R from stage 1.

The combination of both models was run once, as the agreed check, after neither passed alone.

Each model was first checked on its own synthetic curves: f0 180 Hz, 65 m/s, 1.5 km, with η 2 %, a 1.2 m/s² or both. Each recovered all of them exactly (RSS around 10⁻¹²). The straight case matches `straight_pass_ls` to 8 × 10⁻⁵ Hz. Those curves also show what is at stake: a straight-pass fit misses their slant range by −11 % (2 % drift), −45 % (1.2 m/s²) and +18 % (both).

**Numbers**, median |error| (on curve A the true η is 0, so a fitted η there is a nuisance term absorbing kinematic error, not drift):

| Curve, passes | Model | Slant range | v | f0 | τ |
|---|---|---|---|---|---|
| A, primary 29 | straight | 229 m (15.6 %) | 3.0 % | 0.65 % | 0.93 s |
| | drift | 750 m (30.0 %) | 13.2 % | 0.80 % | 1.55 s |
| | accel | 231 m (18.1 %) | 7.2 % | 1.62 % | 2.38 s |
| | both | 576 m (32.7 %) | 29.8 % | – | 4.57 s |
| A, flagged 11 | straight | 193 m (15.3 %) | 11.0 % | 1.54 % | 1.28 s |
| | drift | 882 m (62.9 %) | 30.3 % | 2.27 % | 1.93 s |
| | accel | 334 m (28.8 %) | 18.7 % | 4.83 % | 3.64 s |
| | both | 1,569 m (79.2 %) | 48.3 % | – | 4.55 s |
| D, primary 29 | straight | 230 m (15.0 %) | 4.8 % | 0.83 % | 1.12 s |
| | drift | 1,084 m (48.9 %) | 18.7 % | 0.93 % | 2.03 s |
| | accel | 299 m (14.5 %) | 8.1 % | 2.46 % | 3.19 s |
| | both | 1,136 m (48.6 %) | 27.3 % | – | 3.36 s |

- **Better fits, worse slant range.** The heavier models fit the curve shape better: RSS against the straight fit's is 0.90 (drift), 0.83 (accel) and 0.71 (both) on A, and 0.95, 0.95 and 0.88 on D. Meanwhile slant range, speed and τ all get worse.
- **Identifiability, drift:** 5 of 29 primary passes (1 of 11 flagged). η correlates with v and R at 0.98 and 0.95 over the bootstrap: it trades off with them.
- **Identifiability, accel:** 16 of 29 primary passes (6 of 11 flagged), short of two thirds.
- **The fitted acceleration isn't the aircraft's.** It is uncorrelated with the trajectories' own along-track acceleration within ±30 s of CPA (r = −0.01; median |a − a_traj| 0.22 m/s² against a median |a_traj| of 0.09).
- **Drift read on D, the published ridge.** η̂ has a median of +3.8 % (IQR −4.5 to +10 %, partly beyond the ±5 % bound). Stage 1's half-fit differences on D imply drifts of a few tenths of a percent. So η̂ isn't measuring drift there either.
- **Turns.** 10 of 29 primary passes and 6 of 11 flagged ones turn faster than 1°/s within ±30 s of CPA, with medians of 0.54 and 1.2°/s.

**Outcome: neither model enters, nor does the combination.**
- **Criterion 1 fails for both:** 750 m and 231 m against the 160 m target, and the combination gives 576 m.
- **Criterion 3 fails for both:** 5 and 16 of 29 identified, against 20 needed.
- **What the failure says.** With one more degree of freedom the fit lowers its residual by trading the new parameter against speed and distance. The information on R that the straight model had goes into explaining shape the extra parameter can't account for physically. So the model error isn't a drift or a steady acceleration.
- **The flagged passes are mostly turns** (6 of 11 above 1°/s). That is the case for the three-parameter turn model next round: turn rate, plus the split of R into horizontal offset and height, plus the turn's sign. And for anything heavier, the criterion should be read on R, not on RSS.

**Script:** `tools/experiments/2026-11-04/heavier_model.py`. **Outputs:** `runs/2026-11-04-heavier-model/` (`heavier_fits.csv`, `heavier_profiles.csv` with each profile's Δ values) and `runs/2026-11-04-heavier-model-both/`.

## The turn model: three parameters (design, written before any run)

**Question.** Does a constant-rate level turn cut the straight fit's model error on the passes that turn? Per the heavier-models section above, 16 of the 40 Livermore passes turn faster than 1°/s within ±30 s of CPA.

**Model.** A forward model in emission time u, heard at t = τ + u + r(u)/c, with f = f0 / (1 + ṙ/c).
- **Path.** At u = 0 the aircraft is at horizontal offset d from the microphone and height h, heading at right angles to the line to the microphone. That point is a horizontal CPA for any turn rate. Its position is x = (v/ω) sin ωu, y = d + s·(v/ω)(1 − cos ωu), z = h.
- **Parameters.** f0 (closed form), τ, v and R = √(d² + h²), as in the straight fit, plus three new ones:
  - ω ∈ [0, 6]°/s, the turn rate;
  - φ = atan(h/d) ∈ [0°, 90°], the split of R into offset and height;
  - s = ±1, the turn's sign: +1 turns away from the microphone, −1 toward it.
- **The sign is a discrete selection.** Each pass is fitted on both branches, and the fit is the branch with the lower RSS.
- **Reduces to the straight pass.** At ω = 0 the model is the straight pass exactly, and φ is unidentified by construction.
- **The compared R is the fitted path's true minimum distance,** min over u of r(u), the same quantity as the trajectory reference R*.
- **Starts:** the straight fit × ω ∈ {0.5, 1.5, 3}°/s × φ ∈ {15°, 45°, 75°}, on each branch.

**Checks first.** Synthetic arcs, f0 180 Hz, 65 m/s, 1.5 km, with ω 0, 1 and 3°/s, φ 20° and 60°, and both signs. Each must be recovered exactly. ω = 0 must match `straight_pass_ls`. Each also records what a straight fit misses on it.

**The straight fit's baseline on curve A** (`runs/2026-11-04-heavier-model/heavier_fits.csv`, straight on A), median |R − R*|:
- the 16 turning passes: 287 m (18.0 %);
- the 24 non-turning passes: 165 m (12.4 %);
- the primary 29: 229 m (15.6 %).

**Expectation, written before the criterion.**
- Real help on the turning passes, but not a cure: Livermore's turns aren't constant-rate, and φ can trade with R the way η traded with v and R. A guess: a third off the turning passes' median.
- The non-turning passes unchanged, with ω̂ near 0 and φ unidentified.
- The primary 29 near the 160 m target, probably just above it.
- ω identified on most turning passes, because a turn makes approach and recede asymmetric, which a straight pass can't produce. φ identified only on the fast turns.

**Criterion, fixed before running.** The model enters if, on curve A, all of these hold:
1. On the 16 turning passes, median |R − R*| ≤ 201 m (30 % below 287 m).
2. On the 24 non-turning passes, median |R − R*| ≤ 182 m (no more than 10 % above 165 m).
3. On the primary 29, median |R − R*| ≤ 160 m.
4. The signed turn rate s·ω is identified on at least 11 of the 16 turning passes. The rule is the same as for the one-parameter round: on A plus one stage-1 noise replicate, Δ = (RSS − RSS_min)/(σ²κ) ≤ 3.84 only on an interval finite on both sides inside ±6°/s, with σ² and κ as before.
5. On at least 11 of the 16 turning passes, the chosen s matches the trajectory's turn direction relative to the microphone, and s·ω̂ has the sign of the trajectory's mean turn rate over ±30 s. Across the turning passes, the correlation of s·ω̂ with that rate is at least 0.5.

Never judged on the residual: RSS ratios are reported only. Curve D (the published ridge) is reported beside A and isn't in the criterion.

**The bound beside it.** The Cramér–Rao bound of R under the six-parameter model at the fitted point, with the pass's own ridge noise as in `crb.py`, set beside the straight model's bound. Where s·ω's interval includes 0, φ's Fisher information is singular, so the bound there is taken with φ fixed and says so.

**The trade-off watch.** φ against R, as η was watched: the profile of φ, and over the bootstrap the correlations of φ and s·ω with v and R.

**Compute.** synth, fit and profile run here at two workers. The bootstraps wait for the cloud fleet: 200 moving-block replicates (2 s blocks of the sub-5 s residuals) per pass, refitting both branches. Every unit writes its own jsonl line, every replicate's seed comes from (pass, replicate), and a stopped or split run resumes and merges to the same numbers.

**Before any real curve: the synthetic check finds the design over-parametrized.**
- **Recovery.** On all 10 synthetic arcs (`runs/2026-11-04-turn-model-synth/`) the turn model recovers slant range exactly. At ω = 0 it matches `straight_pass_ls`.
- **What a straight fit misses.** On the same arcs it misses slant range by −30 % at 1°/s and −90 to −105 % at 3°/s.
- **The sign is not recovered.** On 3 of the 8 turning arcs the sign comes back wrong, and both branches fit to RSS ~10⁻²⁵ with different speeds. For example, the toward-turn at φ = 20° fits as an away-turn with v 41.5 m/s instead of 65 m/s.
- **Why.** For this path the range history is r(u)² = R² + 2K(1 − cos ωu), with K = (v/ω)(v/ω + s·R cos φ). This is exact: verified to 10⁻¹² m. One microphone hears only the range history, so the curve fixes R, ω and K, and nothing else.
  - Speed, the split φ and the sign trade freely along constant K. Of the three new parameters, only the turn rate is identifiable. K replaces v², which a turning fit no longer measures.
  - A straight pass is the limit r² = R² + v²u², so the turn model adds one parameter, ω, not three.
- **Consequences for the approved criterion.** Criteria (1)–(3), on R, stand. (4) is read on |ω|: the sign is not a parameter of the curve. (5) can't be met by construction: the sign and φ are unidentifiable. The φ–R trade becomes a K–R and ω–R trade.
- **The parametrization to use.** (f0, τ, R, K, ω). Its bound needs ω fixed where ω's interval includes 0, since K and ω merge into Kω² there.
- **Status.** Nothing has run on Livermore. The amendment waits for the PM.

**Numbers** (`runs/2026-11-04-turn-model-fit/`, the design as approved; `runs/2026-11-04-turn-model-profile/`, the identifiable form). Median |R − R*|:

| Curve, passes | Straight | Turn model |
|---|---|---|
| A, turning 16 | 287 m (18.0 %) | 882 m (44.2 %) |
| A, non-turning 24 | 165 m (12.4 %) | 327 m (15.8 %) |
| A, primary 29 | 229 m (15.6 %) | 373 m (15.6 %) |
| A, flagged 11 | 193 m (15.3 %) | 512 m (37.9 %) |
| D, primary 29 | 230 m (15.0 %) | 538 m (26.3 %) |

- **The residual barely moves:** RSS against the straight fit's is 0.97 on the turning passes and 1.00 on the rest.
- **Identification:** the turn rate is identified on 3 of the 16 turning passes and 6 of the 24 others. On 9 of the turning passes its interval includes 0.
- **The bound:** the Cramér–Rao bound of R in the identifiable form is a median 8.6 % on the turning passes, against the straight model's 5.0 %; on the non-turning passes both are 4.1 %.
- **Sign:** the chosen sign matches the trajectory's on 4 of 16, which is unidentifiable by construction as shown above.
- **The turn rate is real but not constant.** Its fitted size correlates with the trajectory's mean turn rate over ±30 s at r = 0.72 across the turning passes, and with the largest rate at only 0.32. Those passes' mean rate is a median 0.16°/s, against a largest rate of 2.3°/s: they weave rather than hold a turn.

**Outcome: the turn model doesn't enter.**
- **Criteria 1–4 fail:** 882 m against 201 m, 327 m against 182 m, 373 m against 160 m, and 3 of 16 identified against 11. Criterion 5 can't be met by construction.
- **The expectation was wrong.** It predicted a third off the turning passes' miss. Instead the miss triples.
- **Why.** As with η and the acceleration, the extra freedom lowers the residual a little by trading the turn rate against R. A constant-rate turn can't describe a weave, so the fit spends the rate on curve shape it can't explain physically.
- **Item 2's conclusion.** Three kinematic additions have now been tried (drift, acceleration, turn), and none cuts the model error. Each makes R worse. The per-pass model error isn't reducible by a heavier single-pass model on this data.
- **What the turn model does give.** Its fitted rate tracks how much a pass weaves (r = 0.72). That makes it a candidate flag for passes whose R to distrust, rather than a correction.

## The weave flag: a pass-quality gate (criterion written before the run)

**Question.** Can the turn model's fitted rate, which tracks how much a pass weaves, flag the passes whose slant range not to trust? This is a gate on which events to trust, feeding Phase 2 item 7 and Phase 3's choice of events. It isn't an item 2 fix: a heavier pass model still doesn't reduce one pass's model error.

**Setup.** On the published ridge D, the realistic input, fit each of the 40 Livermore passes in the identifiable form, r² = R² + Q·u²·sinc²(ωu/2π). Flag a pass when its fitted ω exceeds 0.5°/s, a threshold fixed now. The slant range judged is the straight fit's on D: the flag chooses passes, and doesn't change their fit.

**Criterion, fixed before running.** The gate enters if, on D:
- the retained passes' median |R − R*| is at most 161 m (30 % below all 40 passes' 230 m);
- at least 24 of the 40 passes are retained;
- the flagged passes' median |R − R*| is above the retained passes'.

One counted retune of the threshold is allowed.

**A correction to the criterion, found when reading the numbers.** The 230 m it quotes as "all 40 passes'" median on D is the primary 29's (heavier-models table). All 40 passes' median on D is 284 m, so the 30 % line is 199 m, not 161 m. The gate fails at either line.

**Numbers** (`runs/2026-11-04-turn-model-flag/`; the straight fit's |R − R*| on D):

| Threshold | Retained | Retained median | Flagged | Flagged median |
|---|---|---|---|---|
| 0.5°/s (the criterion's) | 18 | 441 m | 22 | 149 m |
| 0.1 and 0.25°/s | 16 | 441 m | 24 | 188 m |
| 1.0°/s | 29 | 393 m | 11 | 193 m |
| 1.5°/s | 33 | 271 m | 7 | 310 m |
| 2.0°/s | 34 | 284 m | 6 | 246 m |

Only the 0.5°/s row decides; the other thresholds are description, not the counted retune.

**Outcome: the gate doesn't enter, and points the wrong way.**
- **At 0.5°/s every criterion fails.** The retained passes' median is 441 m against 161 (or 199) m, only 18 of 40 are retained against 24, and the flagged passes are the better ones: 149 m against 441 m.
- **The retune isn't spent.** No threshold from 0.1 to 2°/s brings the retained median under 199 m; the best is 271 m at 1.5°/s.
- **On the real ridge the fitted rate doesn't measure weaving.** The 16 passes the identifiable form fits at ω = 0 on D are the worst, at a median of 441 m. 9 of the 16 turning passes are flagged and 7 aren't. The rank correlation of ω on D with the error is −0.10.
- **Why.** On the trajectory curve A, the fitted rate tracked the trajectory's mean turn rate (r = 0.72). On D, the ridge's own errors decide where the rate goes, so it is no use as a gate on real events.

**Scripts (stage 1):** `tools/experiments/2026-11-04/straight_pass_ls.py`, `model_error.py`, `model_error_summary.py`, `crb.py`. **Outputs:** `runs/2026-11-04-model-error-2/` (`fits.csv`, `perturbations.csv`, `halves.csv`, `noise.csv`, `summary.json`) and `runs/2026-11-04-crb-2/` (`crb.csv`, `crb_summary.json`; `runs/2026-11-04-crb/` used the invalid truncated covariance and is superseded). Weather: `raw/aux/metar/KLVK_*`, `RAOB_KOAK_*`.
