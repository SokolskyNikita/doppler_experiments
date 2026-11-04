# Reference documents

Papers, books, and video references behind the technical choices in [PLAN.md](../../PLAN.md). Collected 2026-11-03.

The files themselves live outside the repo, in `$DOPPLERTRACK_DATA/reference/` (by default `~/data/dopplertrack/reference/`). This README and the conversion scripts in `tools/reference/` are tracked.

- `pdf/`: the originals. These are the source of truth, especially for equations, figures and tables.
- `md/`: Markdown conversions for fast searching and reading. Each page starts with a marker like `{149}------`, the **0-based** PDF page index: `{149}` is page 150 of the PDF (`pdftoppm -f 150 -l 150`). Printed book page numbers differ: in Kay I, book page = PDF page − 8; in Kay II, book page = PDF page − 13. Figures sit next to each file in `<name>_images/`.
- `youtube/<video-id>/`: downloaded video, annotated Markdown transcript, subtitles, captions, ASR/OCR output, visual evidence, provenance, validation report, and artifact checksums.
- `youtube/tooling/`: acquisition/review scripts and configuration; logs and temporary previews live under `work/<video-id>/`. The local `youtube/README.md` indexes the videos and `youtube/tooling/README.md` explains rebuilding them.

The material is copyrighted and the upstream repo is public, so it stays on this machine and never goes into git.

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

### Estimation and detection theory (Phases 2, 4 and detection)

| File | Source | What it is | Why it matters here |
|---|---|---|---|
| `kay-1993-ssp-vol1-estimation-theory` | Kay, *Fundamentals of Statistical Signal Processing, Vol. I: Estimation Theory* (Prentice Hall, 1993), 603 pp.. | The standard textbook on parameter estimation: Cramér–Rao lower bound (ch. 3), maximum likelihood (ch. 7), least squares (ch. 8), and many worked frequency-estimation examples. | The theory behind turning "how fast the fit score falls off around its optimum" into real uncertainty ranges for each fitted event (gap E1), once the score is a likelihood. Start with ch. 3 and ch. 7; §8.9 is separable least squares, the basis of variable projection. |
| `kay-1998-ssp-vol2-detection-theory` | Kay, *Fundamentals of Statistical Signal Processing, Vol. II: Detection Theory* (Prentice Hall, 1998), 573 pp.. | Detection: Neyman–Pearson, matched filters, detecting signals with unknown parameters (composite hypothesis testing), false-alarm control. | The principled basis for `detect`'s score floor and "no flyovers found" result (gap E4), and for the usability check (gap S6). Chapters 3–4 and 6–7 are the relevant ones. |
| `golub-pereyra-2003-variable-projection` | Golub & Pereyra, *Inverse Problems* 19:R1 (2003). This copy is the authors' 30-page preprint of July 2002, which numbers equations as section.count, e.g. (12.3). | Survey of variable projection: when a model is linear in some parameters, solve those exactly by linear least squares and optimize only the rest. Covers the theory, algorithms and applications. | **Read first.** In Ferguson & Quinn's model (eq. 16, f = α + β·z(t_c, s)), α and β enter linearly and carry the rest frequency and speed. Variable projection solves them exactly at each (t_c, s), leaving only timing and geometry to optimize. |
| `chan-towers-1992-doppler-passive-localization` | Chan & Towers, *IEEE TSP* 40:2594 (1992), 5-page issue extract (the paper starts on PDF page 1, after the end of another paper) | Locates a tone source from Doppler-shifted frequencies at five or more known positions. Introducing intermediate variables cuts a 5-D search to a 2-D position grid with a small linear solve at each point. Gives the Cramér–Rao bound. | Which parameters Doppler measurements can actually pin down, and the geometric ambiguities. Its 2-D grid-plus-linear-solve trick mirrors our `search` over candidate positions. |
| `white-1982-misspecified-mle` | White, *Econometrica* 50:1 (1982), 26 pp. | Maximum likelihood when the model is wrong: the estimate still converges to the best-fitting wrong model, standard tests become invalid, and a corrected ("sandwich") covariance applies. | Separates fit uncertainty from error caused by a wrong motion model (e.g. a turning or climbing aircraft). Read when designing uncertainty estimates, after the fitting baseline exists. |
| `raue-2009-profile-likelihood-identifiability` | Raue et al., *Bioinformatics* 25:1923 (2009), 7 pp. (open access) | Profile likelihood: fix one parameter, re-optimize the others, and read confidence intervals off the resulting curve. Tells "structural" non-identifiability (parameters that trade off exactly) apart from "practical" (data too weak to pin them down). Written for biology models, but the method is general. | The right way to derive each event's speed, distance and time ranges in Phase 2 (gap E1), and to see how they trade off against each other. Profiles that never close would flag a fit to discard rather than gate on. |

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
| Quinn & Hannan, *The Estimation and Tracking of Frequency* (Cambridge, 2001) | If frequency tracking becomes the bottleneck. Mostly covered by Kay I and Iatsenko. |
| Labelled aircraft-audio datasets (e.g. AeroSonicDB) | Detection only (gaps E4–E5): without location, timing and matching trajectories they can't validate a location. Needs a web search; not on hand. |
| Martín, Genescà, Romeu et al. 2014, "Passive acoustic method for aircraft states estimation based on the Doppler effect", *IEEE TAES* 50:1330 | Phase 2's model-error experiment: aircraft states, manoeuvres included, from Doppler. Cited by Ferguson 2016 §6. |
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

- `tools/reference/tidy_latex.py` rewrites spaced-out LaTeX (`\mathbf { x }` → `\mathbf{x}`). It changes only whitespace that TeX ignores, and checks every formula still tokenizes identically.
- `tools/reference/add_labels.py` restores 23 equation numbers Mistral dropped: 9 in Kay I, 10 in Kay II and 4 in Angelopoulos & Bates. Every file's printed equation numbers were compared with the Markdown (OCR of each page plus a numbering-gap check), and each restored number was placed by eye against the PDF page. A whole equation gets `\tag{n}`; one row of a multi-row equation gets `\qquad\text{(n)}`.

Mistral also writes some numbers as `\quad (n)` inside the math or as plain text beside the equation (White puts them on the left, e.g. `(5.2) $$…$$`). When looking for an equation, search for both `\tag{4.16}` and `(4.16)`.

Limitations:
- Multi-row derivations are `\begin{array}` blocks. Check alignment against the PDF.
- Figures are images with captions. Plots are not converted to data.
- Empty Markdown pages are blank in the PDF too.
