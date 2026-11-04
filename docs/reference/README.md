# Reference documents

Papers, books, and video references behind the technical choices in [PLAN.md](../../PLAN.md). Collected 2026-11-03.

The files themselves live outside the repo, in `$DOPPLERTRACK_DATA/reference/` (by default `~/data/dopplertrack/reference/`). This README and the conversion scripts in `tools/reference/` are tracked.

- `pdf/`: the originals. These are the source of truth, especially for equations, figures and tables.
- `md/`: Markdown conversions for fast searching and reading. Each page starts with a marker like `{149}------`, the **0-based** PDF page index: `{149}` is page 150 of the PDF (`pdftoppm -f 150 -l 150`). Printed book page numbers differ: in Kay I, book page = PDF page − 8; in Kay II, book page = PDF page − 13. Figures sit next to each file in `<name>_images/`.
- `youtube/<video-id>/`: downloaded video, annotated Markdown transcript, subtitles, captions, ASR/OCR output, visual evidence, provenance, validation report, and artifact checksums.
- `youtube/tooling/`: acquisition/review scripts and configuration; logs and temporary previews live under `work/<video-id>/`. The local `youtube/README.md` indexes the videos and `youtube/tooling/README.md` explains rebuilding them.

The material is copyrighted and the upstream repo is public, so it stays on this machine and never goes into git.

Open-source projects on the same problem, the commits inspected and what PLAN.md takes from them: [related-projects.md](related-projects.md). Every search for data, what it found and why each source was taken, deferred or rejected: [datasets.md](datasets.md).

## How to use this folder

1. Search the Markdown first: `rg -n "Cramer-Rao|CRLB" "$DOPPLERTRACK_DATA/reference/md/"`.
2. Before relying on an equation, a number or a figure, open that page of the PDF. No conversion is perfect (see [Conversion](#conversion)).
3. Cite by author, year and equation or page, e.g. "Ferguson & Quinn 1994, eq. 15".

**Read first for the next development cycle:** Ferguson & Lo 2000 §I (the model, eqs. 1–14), Ferguson 2016, then Golub & Pereyra 2003. Take the reduced objective from Ferguson & Quinn 1994 eq. 20: Ferguson 2016's eq. 14 is misprinted. [PLAN.md](../../PLAN.md) section 6.3 lists these caveats.

## Video walkthrough

[colsto, *I discovered a sound that leaks your exact location (and it's everywhere)*](https://www.youtube.com/watch?v=UytYrhYLOKI), published 2026-11-02, 29 min 12 s. The local annotated transcript is `$DOPPLERTRACK_DATA/reference/youtube/UytYrhYLOKI/transcript.md`.

It documents the national candidate search, manual event-fit bounds, the silence filter, emission-time Doppler modeling, locked two-event scoring, and a separate single-flight search using a hand-traced ridge. The transcript distinguishes narration from on-screen values and editorial checks; the full audio was compared with an independent Whisper pass, and sampled frames and selected full-resolution stills were reviewed. Ambiguous speech and source discrepancies remain marked. In particular, the two displayed winning coordinates differ by about 610 m, and the one-flight example supplies a nominal time in narration but a one-hour window in its comparison slide.

The source recording linked in the description, [4CxVxuMVkMc](https://www.youtube.com/watch?v=4CxVxuMVkMc), is already archived as `raw/audio/youtube/oyster_bay.webm` and `.m4a`; no duplicate was downloaded. It is our Oyster Bay **development** recording, not independent evaluation evidence. The walkthrough's thresholds and scores describe that demonstration and should not be substituted for this fork's measured results or current defaults.

## What's here

### Acoustic Doppler flight-parameter estimation (Phase 2: event fits)

Most of these come from Brian Ferguson's group at the Australian Defence Science and Technology Organisation (DSTO). They are the closest prior work to dopplertrack's `fit`: one ground microphone, the propeller blade-rate tone, and a model of how its observed frequency changes during a pass.

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `ferguson-1992-narrowband-altitude-speed` | Ferguson, *JASA* 92:1403 (1992), 5 pp. | The original method: track the blade-rate tone and least-squares fit a Doppler model with altitude and speed as parameters. Tested on 18 controlled overhead passes; RMS error about 100 ft in altitude (250–1500 ft) and 6 kn in speed. | The baseline our `fit` reimplements. Its error figures are the accuracy to expect from a clean, controlled pass. |
| `ferguson-quinn-1994-stft-wigner-ville-localization` | Ferguson & Quinn, *JASA* 96:821 (1994), 7 pp. | Same 18 passes. Compares the short-time Fourier transform with the Wigner–Ville distribution for estimating the tone frequency, then fits speed, altitude, rest frequency and CPA time. Gives the closed-form frequency model (eqs. 12–17) and the least-squares objective. | The reference formulation of our fit objective. A direct comparison point for the fit objectives in Phase 2. |
| `quinn-1995-doppler-speed-range-frequency-amplitude` | Quinn, *JASA* 98:2560 (1995), 7 pp. | Improves the 1994 algorithm by using **amplitude** estimates as weights (each frequency estimate's error variance falls as 1/amplitude²), derives the estimators' covariance, and works **even when only part of the Doppler track is available**. | Weights the frequency track by reliability, and handles partial passes, which real recordings often contain. Amplitude is a weight here, *not* a range measurement. |
| `ferguson-lo-2000-turboprop-rotary-wing` | Ferguson & Lo, *JASA* 108:1763 (2000), 9 pp. | One framework for a narrow-band method (Doppler of the tone at one sensor) and a broadband method (time differences across a sensor array), both tested on the same transits of a turboprop and two helicopter types. | More real-aircraft error figures, including helicopters, and when tone-based and broadband measurements complement each other. |
| `ferguson-2016-nls-aeroacoustic-source-parameters` | Ferguson, *IET Radar Sonar Navig.* 10:1552 (2016), 9 pp. | Reviews nonlinear least squares (NLS) for three cases: a turboprop from one microphone's frequency track, a jet from multipath delays, and a ground vehicle from array time differences. Finds simpler conventional methods comparable, and good as NLS starting points. | **Read first.** The newest treatment of exactly our fit, with conventional (asymptote and peak-slope) estimates as starting values. Helps decide which Phase 2 estimator to implement. Its printed eq. 14 squares each term inside the sum; use Ferguson & Quinn 1994 eq. 20 instead. |

Kept, but off the immediate reading list:

| File | Source | What it is | Why it's deferred |
|---|---|---|---|
| `timlelt-2017-closed-form-doppler-motion` | Timlelt, Remram & Belouchrani, *Digital Signal Processing* 63:35 (2017), 27 pp. (accepted manuscript) | A **closed-form**, non-iterative solution for speed, altitude, source frequency and CPA time from the instantaneous frequency, for propeller aircraft and helicopters. | An experimental comparator only. Eq. 19 takes the argmax of f′ although f′ is negative (its own eq. 15), and eq. 20 drops a square. Its simulations show a 7 % f0 error, and its experiments use a loudspeaker moving at 1–1.6 m/s. A weak foundation to implement from. |
| `lo-ferguson-2003-multipath-delays` | Lo, Ferguson, Gao & Maguer, *IEEE TAES* 39:259 (2003), 10 pp. | Gets the source's elevation angle, then speed and altitude, from the delay between direct and ground-reflected sound. Written for jets and other **broadband** sources over **hard** ground. | A separate research branch. Revisit once a usable reflection-delay track is shown in our recordings. |

### Frequency tracking (Phase 2)

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `iatsenko-2016-ridge-instantaneous-frequency` | Iatsenko, McClintock & Stefanovska, *Signal Processing* 125:290 (2016), 15 pp. (author's open copy) | Extracting a tone's frequency curve from a time-frequency map: an adaptive method based on dynamic path optimization, compared with alternatives on simulated and real data. Code is freely available. | A concrete alternative to compare with our tracker for faint tones. Warns that short-lived signals need stopping rules so the tracker doesn't join unrelated tones, and offers none. Harmonics aren't covered. |
| `quinn-hannan-2001-estimation-and-tracking-of-frequency` | Quinn & Hannan, *The Estimation and Tracking of Frequency* (Cambridge, 2001), 282 pp.; book page = PDF page − 12 | The statistics of frequency estimation: the periodogram maximiser and its Cramér–Rao bound (ch. 3), the three-Fourier-coefficient interpolators that `freqtrack` uses (§6.2.2), and tracking a slowly varying frequency at low SNR as a hidden Markov model with the Viterbi and forward–backward recursions (ch. 7, with a real sonar example in §7.5). | Phase 2 item 3's next step is hysteresis in states; ch. 7 is that model, with the transition and emission structure written out, and §7.4 is the HMM tracker to compare the off-state Viterbi against. |
| `harris-1978-windows-dft` | Harris, *Proc. IEEE* 66:51 (1978), 33 pp. | The catalogue of DFT windows and their figures of merit; §IV.C defines the overlap correlation c(r) between successive transforms (eq. 17, Table I) and gives Welch's variance of an average of overlapped transforms (eq. 19). | Our STFT frames overlap 87.8 % (2.048 s Hann, 0.25 s hop), so neighbouring frames are not independent samples: by eq. 17 a Hann frame correlates 0.91, 0.67, 0.40 and 0.18 with the next four, and 1 + 2Σc² = 3.9, so a covariance that counts frames as independent (Quinn 1995) is about four times too small, and a 1 s or 0.5 s window at the same hop brings the factor to 1.9 and 1.06. |

### Estimation and detection theory (Phases 2, 4 and detection)

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `kay-1993-ssp-vol1-estimation-theory` | Kay, *Fundamentals of Statistical Signal Processing, Vol. I: Estimation Theory* (Prentice Hall, 1993), 603 pp.. | The standard textbook on parameter estimation: Cramér–Rao lower bound (ch. 3), maximum likelihood (ch. 7), least squares (ch. 8), and many worked frequency-estimation examples. | The theory behind turning "how fast the fit score falls off around its optimum" into real uncertainty ranges for each fitted event (gap E1), once the score is a likelihood. Start with ch. 3 and ch. 7; §8.9 is separable least squares, the basis of variable projection. |
| `kay-1998-ssp-vol2-detection-theory` | Kay, *Fundamentals of Statistical Signal Processing, Vol. II: Detection Theory* (Prentice Hall, 1998), 573 pp.. | Detection: Neyman–Pearson, matched filters, detecting signals with unknown parameters (composite hypothesis testing), false-alarm control. | The principled basis for `detect`'s score floor and "no flyovers found" result (gap E4), and for the usability check (gap S6). Chapters 3–4 and 6–7 are the relevant ones. |
| `golub-pereyra-2003-variable-projection` | Golub & Pereyra, *Inverse Problems* 19:R1 (2003). This copy is the authors' 30-page preprint of July 2002, which numbers equations as section.count, e.g. (12.3). | Survey of variable projection: when a model is linear in some parameters, solve those exactly by linear least squares and optimize only the rest. Covers the theory, algorithms and applications. | **Read first.** In Ferguson & Quinn's model (eq. 16, f = α + β·z(t_c, s)), α and β enter linearly and carry the rest frequency and speed. Variable projection solves them exactly at each (t_c, s), leaving only timing and geometry to optimize. |
| `chan-towers-1992-doppler-passive-localization` | Chan & Towers, *IEEE TSP* 40:2594 (1992), 5-page issue extract (the paper starts on PDF page 1, after the end of another paper) | Locates a tone source from Doppler-shifted frequencies at five or more known positions. Introducing intermediate variables cuts a 5-D search to a 2-D position grid with a small linear solve at each point. Gives the Cramér–Rao bound. | Which parameters Doppler measurements can actually pin down, and the geometric ambiguities. Its 2-D grid-plus-linear-solve trick mirrors our `search` over candidate positions. |
| `white-1982-misspecified-mle` | White, *Econometrica* 50:1 (1982), 26 pp. | Maximum likelihood when the model is wrong: the estimate still converges to the best-fitting wrong model, standard tests become invalid, and a corrected ("sandwich") covariance applies. | Separates fit uncertainty from error caused by a wrong motion model (e.g. a turning or climbing aircraft). Read when designing uncertainty estimates, after the fitting baseline exists. |
| `raue-2009-profile-likelihood-identifiability` | Raue et al., *Bioinformatics* 25:1923 (2009), 7 pp. (open access) | Profile likelihood: fix one parameter, re-optimize the others, and read confidence intervals off the resulting curve. Tells "structural" non-identifiability (parameters that trade off exactly) apart from "practical" (data too weak to pin them down). Written for biology models, but the method is general. | The right way to derive each event's speed, distance and time ranges in Phase 2 (gap E1), and to see how they trade off against each other. Profiles that never close would flag a fit to discard rather than gate on. |

### Undoing Doppler in the waveform, and combining evidence (Phase 2 items 4–7, Phase 3)

Collected 2026-11-04 on an outside reviewer's advice (the review and its experiment design are summarised in PLAN.md Phase 2 item 8 and section 6.3); Howell 1986 and Ramseier & Pieren 2024 are paywalled and were supplied by the user.

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `howell-1986-de-dopplerization-flyover` | Howell, Bradley, McCormick & Brown (Rolls-Royce), *J. Sound Vib.* 105:151 (1986), 17 pp.; supplied by the user | The original single-microphone de-Dopplerisation: signals emitted at equal intervals reach a fixed microphone at the irregular times of eq. 1, so sample the recording at those reception times to rebuild the emission-time history (§2.1). Their simulation (§3.1, Fig. 4) sets the interpolation rule: nearest-sample resampling gives a 10 dB signal-to-noise floor at equal rates, linear interpolation with the recording sampled at twice the analysis rate gives about 35 dB. On an Avro Shackleton (four Griffons with counter-rotating propellers) the corrected 90° spectrum resolves half-engine orders every 20 Hz up to 980 Hz and blade-passing harmonics (53.1 Hz fundamental) to the 17th, which the raw spectrum blurs (§3.3, Figs. 9 and 11). | The propeller demonstration of the warp, with the number PLAN item 8 needs for its interpolator (sample at twice the analysis rate, interpolate linearly, or use band-limited interpolation); their two caveats are ours: the corrected history is right only for the assumed emission point, and reflections act as apparent sources that warp differently. |
| `kelly-wilson-1993-de-dopplerization-aiaa` | Kelly & Wilson, AIAA 93-0737 (1993), 12 pp.; the NTRS record 19930040830 is this paper and has no download | De-Dopplerization of a single microphone's recording from a tracked aircraft position history: for a uniform grid of emission times τ, compute the reception time from the range (their eq. 12), interpolate the measured pressure there (linear), scale by range and the Doppler factor (eq. 30), and Fourier-transform in τ (eq. 31). On an XV-15 flyover at 250 ft the corrected spectrum shows the blade-passing fundamental near 26 Hz and its overtones at 52, 78, 104 and 130 Hz where the raw spectrum smears them, and the 4th and 5th harmonics that smearing erased reappear (§V, Figs. 6–8). | The simplest published form of the warp PLAN item 8 proposes: resample the waveform onto emission time for a candidate trajectory and observer, then look for a stationary line. Their limitations list (§IV: quasi-stationary source, no absorption, uniform atmosphere, ground impedance) is ours too; their overhead case is 250 ft, ours 2–9 km. |
| `gao-2021-doppler-warping` | Gao, Gao, Chi, Wang & Song, *Acta Physica Sinica* 70:124302 (2021), 10 pp., Chinese with an English abstract; open access | The same resampling turned into an estimator ("Doppler-warping"): the warping operator h_D(t) = t + √(r₀² + v²(t − t₀)²)/c (eq. 6) linearises the phase of a tone from a straight constant-speed pass (eq. 7); for each candidate speed, resample, take the spectrum, and minimise its Shannon entropy over the line's band (eq. 9). On a 150 hp fishing boat at 174 m with a 124.5 Hz line, the entropy estimate gives 4.7 m/s against GPS 4.5 and a frequency-fit comparator 5.2 (§5). | Spectral concentration as the score for a motion hypothesis instead of brightness along a predicted curve. One hydrophone, one line, r₀ and t₀ assumed known: whether it separates candidate *locations and flights* on aircraft passes is what item 8 tests. The entropy over a band is also a natural "is this a tone" statistic for item 6. |
| `axelrad-2011-collective-detection` | Axelrad, Bradley, Donna, Mitchell & Mohiuddin, *Navigation* 58:305 (2011), 17 pp. | Collective detection for GNSS: instead of acquiring each satellite alone, map every point of a receiver position-and-clock grid to each satellite's delay and Doppler, add the satellites' correlation powers non-coherently there, and search the grid coarse to fine (Table 1: 1 km, 100 m, 30 m steps). Four weak satellites combined detect at about 36 dB-Hz where one alone needs about 40 (Fig. 4); the "noise-only" tail is fatter than the simple model says because of cross-correlations (§Combining Satellites). | The pattern Phase 3 proposes for several uncertain events: one location and clock, each event's evidence mapped into that space and summed, with an unmatched alternative. Their satellites have known codes; our aircraft have unknown tones, some are inaudible and several can explain one line, so the sum needs an assignment rule. The coarse-to-fine search and the fat null tail transfer directly. |
| `ramseier-pieren-2023-estimation-of-the-fan-rotational-speed-using-flyover-audio-recordings` | Ramseier & Pieren (Empa), *J. Aircraft* 61:58 (2024, online 2023), 15 pp.; supplied by the user | Fan speed (N1) of turbofans from ground flyover recordings with known trajectories: de-Dopplerise in the time domain by asynchronous resampling with a windowed-sinc (Hamming) kernel (eq. 7, §II.C.2); enhance the spectrogram by subtracting, at each instant, the median over the neighbouring frequencies f ± x (eq. 11); then track the blade-passing frequency and its harmonics together by dynamic programming, each harmonic's power added with weight (N+1−h)/N and a slope bound δ (eq. 14, §II.C.3), with a cepstral fallback for buzz-saw noise. Validated against flight-data-recorder N1: a mean absolute error of about 2 % near the runway for landings and departures (§VI); on landings the BPF tones become undetectable at larger distances because N1 is low (§IV.A). | The worked example of PLAN item 8's two ingredients, the warp and a background estimated across frequency at each instant rather than along time (our `local_whiten` does the latter, which would erase a line the warp made stationary), and of pooling harmonics inside the tracker rather than linking tracks afterwards (item 6). Their geometry is known and their aircraft are turbofans at 44.1 kHz; their distance limit is a warning for our 2–9 km passes. |
| `merino-martinez-2019-fan-speed-flyover-ica` | Merino-Martínez, Snellen & Simons (TU Delft), ICA 2019, 8 pp. (open, DEGA) | Fan rotational speed of landing and departing turbofans from flyover recordings, to replace the default thrust in noise-contour models: the blade-passing frequency and its harmonics are tracked in the ordinary spectrogram inside a band predicted from the ADS-B trajectory and the Doppler relation (eq. 3), then a least-squares curve fit gives the emitted frequency, allowing small bumps for pilot throttle changes. No de-Dopplerisation. | The simpler, curve-in-the-spectrogram approach to the same problem Ramseier & Pieren later solved by warping; a baseline for what tracking a predicted curve achieves on known-geometry turbofans, and a reminder that the emitted tone drifts with throttle. |
| `fatela-2024-adsb-flyover-daga` | Fatela, Masullo, Vorländer & Maffei, DAGA 2024, 4 pp. (open, DEGA) | An open ADS-B-plus-microphone pipeline for engine-speed estimation: shift each sample by minus the propagation delay from the ADS-B position (straight path, or ray-traced through a moving inhomogeneous atmosphere), resample evenly, STFT, then a 2-D convolution that favours long narrow tones over short broadband events before tracking the fan tone. | An independent description of the warp with the two ingredients ours would need (delay from ADS-B, even resampling) and its stated limits: it fails when the engine speed changes quickly and when reflected or diffracted paths (urban recordings) shift the tone differently from the direct path, both of which our recordings have. |



### Validation and calibration (Phases 1 and 4)

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `cawley-talbot-2010-model-selection-overfitting` | Cawley & Talbot, *JMLR* 11:2079 (2010), 29 pp. (open access) | Shows that tuning a method against a fixed evaluation set overfits that set, often by as much as the differences between methods, and how to avoid it. | Benchmark design: keep the cases used to tune objectives, gates and thresholds apart from the cases used to report accuracy. |
| `angelopoulos-bates-2021-conformal-prediction` | Angelopoulos & Bates, *A Gentle Introduction to Conformal Prediction* (arXiv 2107.07511), 51 pp. (open access) | A practical guide to calibrated prediction sets with distribution-free coverage guarantees. | A starting point for calibrating the uncertainty radius (Phase 4). Caveat: the guarantee assumes exchangeable cases (here, groups of recordings), and it does not automatically hold after filtering down to "located" answers; Learn-then-Test (Appendix B.2) is the template for that. |

## Notes for the plan

From reading these alongside PLAN.md (partly Astra's review):

- **Phase 2.** Call score-drop ranges "fit sensitivity ranges" until they are calibrated. The current brightness/contrast score is not a likelihood, so the Cramér–Rao and profile-likelihood machinery applies only once the objective is turned into one (e.g. a noise model for the frequency track, as in Ferguson & Quinn's least-squares fit).
- **Phase 2.** The DSTO papers fit frequency only. Quinn 1995 uses amplitude to weight the frequency estimates, not to constrain distance. Lo & Ferguson 2003 (deferred) adds the ground-reflection delay, which does constrain distance, but for broadband sources over hard ground. Distance is the weakest fitted parameter (PLAN section 6.1).
- **Benchmark.** Hold out whole recordings or days, keeping their clips and augmented copies together (Cawley & Talbot).
- **Labels.** Treat ADS-B passes as candidate events, not confirmed audible flyovers. Hand-check a small subset before trusting detection precision and recall.

## Worth considering later

Not fetched yet. Pull them when the phase they serve starts.

| Source | When |
|---|---|
| Reid & Zoubir 1997, "Aircraft flight parameter estimation based on passive acoustic techniques using the polynomial Wigner–Ville distribution", *JASA* 102:207 | If ridge extraction proves to be the bottleneck. |
| Ostashev & Wilson, *Acoustics in Moving Inhomogeneous Media*, 2nd ed. (CRC, 2016) | If residual errors point to wind or propagation (gap E6). Only the propagation chapters. |
| Labelled aircraft-audio datasets | Detection only (gaps E4–E5): without location, timing and matching trajectories they can't validate a location. AeroSonicDB, DataSED, DataSEC and an A2O sample are on disk since 2026-11-03 (data root `MANIFEST.md`). |
| Martín, Genescà, Romeu et al. 2014, "Passive acoustic method for aircraft states estimation based on the Doppler effect", *IEEE TAES* 50:1330 | Phase 2's model-error experiment: aircraft states, manoeuvres included, from Doppler. Cited by Ferguson 2016 §6. |
| Meng & Ben-Zion 2018, "Characteristics of airplanes and helicopters recorded by a dense seismic array near Anza California", *JGR Solid Earth* 123:4783, doi:10.1029/2017JB015240 | A published closed-form retarded-time fit of one straight pass (f0, speed, CPA distance, CPA time), on seismic rather than acoustic data. Its MATLAB is at [seismo-netizen/Air_Traffic](https://github.com/seismo-netizen/Air_Traffic). A precedent for Phase 2 item 4, not a method to copy. |
| Nielsen 2009, "Acoustic detection of low flying aircraft", Proc. IEEE Conf. Tech. Homeland Security, pp. 101–106 | The same: effects of acceleration and manoeuvre on narrowband signals, checked on real data. Cited by Ferguson 2016 §6. |
| NASA RP-1258, Hubbard (ed.), *Aeroacoustics of Flight Vehicles* (free on NASA NTRS) | Background on propeller tone generation and harmonics. |

## Provenance

Where each PDF came from, with its checksum, is recorded beside the files in `$DOPPLERTRACK_DATA/reference/PROVENANCE.md`, which stays out of the repo.

## Conversion

```bash
pdf-to-md "$DOPPLERTRACK_DATA/reference/pdf/" -o "$DOPPLERTRACK_DATA/reference/md" --backend mistral --paginate
python3 tools/reference/tidy_latex.py "$DOPPLERTRACK_DATA"/reference/md/*.md
python3 tools/reference/add_labels.py
```

Mistral OCR was chosen over the OpenAI backend because, on sample pages, OpenAI silently altered math (dropped a factor of ½ and a prime) while Mistral didn't.

Two fixes are applied to every file after conversion. Both are safe to re-run, and must be re-run after re-converting a file with `--overwrite`.

- Known conversion errors, reported by an outside reviewer on 2026-11-04 and to be checked against the PDF before use: the Kelly & Wilson conversion loses a minus sign in the time equations (eqs. 8 and 12), and the Ramseier & Pieren conversion mislabels the left-hand side of its eq. 9. Take time equations from the PDF pages.
- `tools/reference/tidy_latex.py` rewrites spaced-out LaTeX (`\mathbf { x }` → `\mathbf{x}`). It changes only whitespace that TeX ignores, and checks every formula still tokenizes identically.
- `tools/reference/add_labels.py` restores 23 equation numbers Mistral dropped: 9 in Kay I, 10 in Kay II and 4 in Angelopoulos & Bates. Every file's printed equation numbers were compared with the Markdown (OCR of each page plus a numbering-gap check), and each restored number was placed by eye against the PDF page. A whole equation gets `\tag{n}`; one row of a multi-row equation gets `\qquad\text{(n)}`.

Mistral also writes some numbers as `\quad (n)` inside the math or as plain text beside the equation (White puts them on the left, e.g. `(5.2) $$…$$`). When looking for an equation, search for both `\tag{4.16}` and `(4.16)`.

Limitations:
- Multi-row derivations are `\begin{array}` blocks. Check alignment against the PDF.
- Figures are images with captions. Plots are not converted to data.
- Empty Markdown pages are blank in the PDF too.
