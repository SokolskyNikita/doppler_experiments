# What the course materials say about our failures

Reading and code review, 2026-11-04. [Material inventory](course-materials.md). Downloaded sources, reading copies, source manifests and checksums live in `$DOPPLERTRACK_DATA/reference/courses/2026-11-04/`; acquisition scripts, logs, and the small diagnostic live in `$DOPPLERTRACK_DATA/runs/2026-11-04-course-materials-intake/`.

**Assessment: partly textbook mistakes, partly a harder observation/model problem.** One concrete decoding defect was reproduced in the experimental likelihood tracker. Several other elementary weaknesses belong to the original pipeline and are already recognized in PLAN. The materials do not demonstrate a ready-made solution for faint, crossing aircraft tones or maneuvering flights.

## A concrete new finding: a sequence of marginal modes is not a decoded path

`lltrack.posterior()` computes smoothed state probabilities using forward–backward. `lltrack.runs()` then takes `argmax` over frequency independently at each frame. These operations answer different questions: the most probable frequency *at each time*, versus a jointly consistent frequency *trajectory*. Framewise modes may switch between competing posterior trajectories and need not obey the movement constraints used to obtain those probabilities.

Müller's [F0 notebook](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8S2_FundFreqTracking.html), and the downloaded `libfmp/c8/c8s2_f0.py`, make the alternative explicit: retain predecessor choices and backtrack a complete path. Its implementation adds an epsilon to transitions, so its zeros are softened; the important distinction here is sequence optimization/backtracking versus independent marginal maxima.

**Small reproducible diagnostic against our actual functions:** `decoding_probe.py`, seed 20261104, eight frames and eight frequency bins, using a transition kernel capped at one bin per frame. Trial 12 returns one continuous present run, with posterior-mode bins:

```
2, 2, 2, 0, 2, 1, 1, 1
```

The two-bin jumps are outside the kernel support. Presence exceeds 0.91 throughout, so these are not breaks explicitly labeled OFF. A separate Viterbi recursion over the same OFF/ON/DIP potentials returns:

```
0, 0, 0, 0, 0, 1, 1, 1
```

Parameters, emissions and both results are saved in `decoding_probe.json`. This is a short code diagnostic with constructed emissions, not a recording benchmark. It demonstrates a consistency defect in our reported path, **not** that it explains the measured bridges or that Viterbi will meet the tracker criterion. Marginal decoding is legitimate for minimizing framewise classification error; it is unsuitable if the output is meant to obey path constraints.

**Next action justified:** retain smoothed occupancy if useful for deciding when an event exists, but use a consistent path decoder for its frequency trajectory. Verify transitions explicitly. Then rerun the already-defined synthetic cases before spending another full tracker sweep. Existing enumeration tests check the forward–backward probabilities, not the trajectory extracted from them.

## Familiar weaknesses already visible in the pipeline

| Issue | Teaching evidence read | Our status and consequence |
|---|---|---|
| Brightest curve is not automatically the most likely aircraft explanation | Smith's [ML sinusoid derivation](https://ccrma.stanford.edu/~jos/sasp/Maximum_Likelihood_Sinusoid_Estimation.html) and [colored-noise discussion](https://ccrma.stanford.edu/~jos/sasp/Non_White_Noise.html); MIT Chapter 2 detection framework | `score.EventWindow.sweep_scores` averages whitened brightness; `locked_score` adds two maxima. This is a heuristic with unknown null distribution. PLAN correctly requires a whole-search null; the courses do not supply a calibration for this score. |
| A small CRLB does not promise a successful global estimate | [MIT Chapter 3](https://sia.mit.edu/wp-content/uploads/2015/04/chapter3.pdf), §§3.4.1–3.4.2, especially printed pp. 172–175 and capture examples | Low-SNR sinusoid estimates jump to remote maxima. We cannot infer global 1 km reliability from our local information bound. Our noiseless model-error experiments remain useful, but the wording “information is not the limit” needs this qualification. |
| Confidence from correlated/reused evidence is too strong | Hendeby lectures 2–3, Safe Fusion module; MIT PS5 5.3 and PS9 colored-noise problems | Frame overlap, harmonics and reused events require the dependence model appropriate to the statistic. The Harris effective-sample weight is a useful approximation; multiplying log evidence by one scalar is not a derivation of the full joint likelihood. It requires empirical calibration. |
| Fitting nuisance parameters separately can distort the location comparison | [Linköping exam Q3 and solutions](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/20250109sol.pdf); acoustic lab §6 tasks 4–5 | Conditional linear fitting/variable projection is standard, and `tracks.fit_track` already uses it. `locked_score` still chooses the clock shift from event 1 alone; a shared clock should be optimized on the joint evidence. This is already S3 in PLAN. |
| Independent best matches are not a consistent assignment | Hendeby Target Tracking lectures 4–5 and Exercise 2; downloaded `auction.m`, `computeTrackProb.m`, `murty.m` | One-to-one event/flight matching, missed detections, clutter and alternative assignments belong in the model. PLAN's assignment/dummy-cost proposal is aligned with the teaching. Continuous tracking algorithms need adaptation to our batch problem. |
| Marginal coverage does not imply coverage after selecting successful answers | [Berkeley conformal note](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/lectures/conformal.pdf), §2; [HW4 Q2–Q3](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework4.pdf) | Repeated clips do not create independent calibration cases, and filtering to `located` changes the claim. PLAN already recognizes both limitations. These notes do not resolve selection-aware coverage with our small dataset. |

## What is not established as a rookie mistake

**One perfect window or ridge algorithm:** Serra/Smith E5 explicitly makes students trade frequency resolution against chirp smear and weak-tone visibility. Its chirps and amplitude-ratio examples are valuable controls. They do not prove a single window can handle all our passes. Our earlier window comparison should not be overturned merely because a class exercise has an easier example.

**Frequency tracking in clutter:** Müller's notebook still permits the stronger interfering component to take the trajectory. Its constrained examples use supplied information about when/where the target exists. It does not solve our event births/deaths, weak tails, or crossings automatically. A correct path decoder can still follow the wrong source.

**Model mismatch:** [our model-error record](../experiments/2026-11-04-model-error.md) fits noiseless trajectory-derived curves and measures a median 15.6% slant-range miss. This error exists without STFT noise. A better interpolator, likelihood or optimizer cannot make a turning trajectory obey an inadequate straight-pass model. More flexible models can also become unidentifiable, as the project's experiments already found.

**Unobserved and ambiguous sources:** propeller speed drift, multiple tone families, multipath, missing ADS-B, and geometrically similar flight explanations are observations/identification problems. The course examples generally give cleaner target identity or sensor models. Several independent flyovers and explicit alternatives remain necessary.

## Recommended order of work

1. Correct and verify the trajectory-decoding consistency issue, with the existing tracker adoption criterion unchanged. First check the synthetic cases; then determine whether real bridges actually fall.
2. Keep three failure categories separate in diagnostics: wrong frequency measurement, wrong source/trajectory association, and wrong motion model. A lower average residual can conceal deterioration in either of the latter two.
3. Use actual flight trajectories and a jointly fitted recording clock for final evidence. Keep plausible alternatives and unmatched events explicit. Do not require a biased straight-pass point estimate to pass a narrow gate before the true trajectory is considered.
4. Validate a proposed evidence statistic against realistic nulls after the same maximization/selection as the final search. Do not present a tempered tracker posterior, local Hessian, margin, or normalized brightness as calibrated confidence.

Items 2–4 mostly reinforce existing PLAN decisions. The new executable finding is item 1. It warrants a targeted correction and comparison, not a claim that the research problem is solved.

## Reading scope

Read for this assessment: MIT Chapter 2's detection formulation and Chapter 3's nonlinear/sinusoid estimation and capture discussion; Smith's ML and non-white-noise sections and Stanford HW5–HW6; Serra/Smith E4/E5 notebook statements and relevant tracking descriptions; Müller's F0 notebook and DP implementation; Hendeby nonlinear-estimation/CRLB slides, acoustic lab, January 2025 Q3 solutions, association/MHT material and helpers; Berkeley conformal §2 and HW4 Q2–Q3. The MIT page at printed p. 175 was also rendered to check the nonlinear model and information-matrix equations.

Stanford HW6 also supplies a colored-noise modeling exercise using an airplane-noise recording; it is a useful controlled background-model exercise, not an aircraft-localization benchmark.

The archive is larger than this reading scope. Downloading a lecture video is not the same as watching it; no claim is made to have read every archived page or watched every recording. No real-data benchmark was rerun for this review, and package source/defaults were not changed.
