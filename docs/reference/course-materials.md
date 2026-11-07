# Public course materials for dopplertrack

**Local-library update, 2026-11-04:** the downloaded archive has been curated. Only the two selected videos remain; unrelated topics, duplicate bundles/layouts and generated assets were removed. The local library is now about 206 MB, retaining 107 PDFs (1,779 pages), 22 focused FMP notebooks, relevant code/data and exactly two videos. The external library README and pruning audit describe what is currently retained. Counts below describe the original source inventory.

Checked 2026-11-04. This inventory covers the instructors identified in the course search and maps their teaching materials to [PLAN.md](../../PLAN.md), especially Phases 2–4. It complements the [paper and book reading list](README.md).

The collection indexes were inspected and the selected items below were opened. Counts describe entries on those indexes, not a complete download or execution check. **Inspected** means the document or source was read; **linked** means its public index exposes it but its contents were not verified. **Not found** is limited to the inspected course pages. No course archives, audio, or third-party code have been added to this repository.

## At a glance

| Collection | Public materials found | Assessment materials |
|---|---|---|
| MIT 6.432 | Five verified full note chapters/addenda; 14 recitation outlines | 11 problem sets; no public solutions or exam files found |
| Serra/Smith audio course | 10 slide decks; 12 exercise notebooks; worked examples and implementation package | Public notebook exercises; Coursera assessments; no separate answer key or formal exam found |
| Smith MUSIC421A | Ten-week schedule with overheads, videos, free online textbook and code listings | Eight linked homework/lab PDFs; contents unreviewed; no solutions found |
| Müller Music Processing Analysis / FMP | Ten topic pages with slides/handouts; notebooks; code | Exam-preparation questions; no separate formal exams or answer keys found |
| Hendeby Sensor Fusion | Ten full decks; 40 short video modules with slides; acoustic lab, code and data | Eight past exams plus one practice exam, all indexed with solutions and data |
| Hendeby Target Tracking | Ten deck entries; three coding assignments; helper code and data | Assignment prompts; exam arranged with instructor, no public paper found |
| Tibshirani statistical learning | Ten full 2024 notes plus an outline and a borrowed 2023 note; source repository | Four homework sheets; solutions restricted; course uses a project instead of exams |
| UNH sonar short course | Public agenda and topic descriptions | Electronic notes supplied to participants; no public notes or exams found |

## Start here

| Our question | First material | Why this is useful |
|---|---|---|
| How can a fit have a small local error bound yet select a completely wrong peak? | [MIT estimation notes, Chapter 3](https://sia.mit.edu/wp-content/uploads/2015/04/chapter3.pdf), §3.4 | Nonlinear sinusoid estimation and low-SNR capture failures; directly relevant to interpreting our information bounds and wrong-mode fits. |
| How do window length and competing tones affect frequency tracks? | [Serra/Smith Exercise 5](https://github.com/MTG/sms-tools-materials/blob/main/exercises/E5-Sinusoidal-model.ipynb), especially part 2 | Synthetic two-component chirps, known frequency truth, and explicit window-length comparisons. |
| What does a transparent harmonic/DP tracker actually assume? | [Müller's F0-tracking notebook](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8S2_FundFreqTracking.html) | Runnable path extraction and optional constraints, with documented interference and full-window-path limitations. |
| How should we eliminate source-frequency or clock nuisance parameters? | [Linköping January 2025 exam](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/20250109exam.pdf), Q3, with [solutions](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/20250109sol.pdf) | A compact, solved exercise in separating linear nuisance parameters from nonlinear position and deriving the reduced objective. |
| How do location, clock, and geometry interact? | [Linköping acoustic lab](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/localization.pdf), §6 tasks 4–5 | Cost maps, CRLB maps, joint position/time search, and separable least squares that removes the clock from the numerical search. |
| How do we match observations to flights while allowing clutter and missed detections? | [Target Tracking lecture 4](https://mtt.edu.hendeby.se/lectures/le4.pdf) and [Exercise 2](https://mtt.edu.hendeby.se/assets/ex2.pdf) | Global assignment and probabilistic association, with simulation and supplied data. |
| What does a nominal 90% region mean with few calibration recordings? | [Berkeley conformal notes](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/lectures/conformal.pdf), §2, then [Homework 4](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework4.pdf), Q2–Q3 | Finite-sample calibration, variability across calibration sets, and the distinction between marginal and conditional coverage. |

These are teaching examples, not validations of our pipeline. In particular, a local CRLB does not cover wrong modes or model mismatch; multi-sensor time-of-arrival localization differs from one-microphone Doppler localization; and ordinary conformal coverage does not establish coverage among the subset declared `located`.

## 1. MIT: Wornell, Willsky, and Shapiro — detection and estimation

[6.432 Spring 2004 OCW](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/) lists Wornell and Willsky as instructors. The separate Fall 2003 course-note chapters identify Willsky, Wornell, and Shapiro as authors. The MIT lab's [course index](https://sia.mit.edu/courses/) lists the archived course; the older PDFs below are directly readable even though its current rendered index does not expose their links.

### Collection

| Material | Inventory and access | Use here |
|---|---|---|
| Course-note chapters | Five chapters/addenda verified readable: [1](https://sia.mit.edu/wp-content/uploads/2015/04/chapter1.pdf) (52 PDF pages), [3](https://sia.mit.edu/wp-content/uploads/2015/04/chapter3.pdf) (85), [4](https://sia.mit.edu/wp-content/uploads/2015/04/chapter4.pdf) (88), [6](https://sia.mit.edu/wp-content/uploads/2015/04/chapter6.pdf) (14), [7](https://sia.mit.edu/wp-content/uploads/2015/04/chapter7.pdf) (16). This is an incomplete verified set. | Substantive derivations; Chapter 3 is the first read. |
| [Recitations](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/pages/recitations/) | 14 public PDFs, R1–R14. R6, R10, and R14 were opened and are each one-page outlines. | A topic index and pointers to exercises; do not mistake these for full lecture notes or worked solutions. |
| [Assignments](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/pages/assignments/) | 11 public problem-set PDFs. PS4, PS5, PS6, PS9, and PS11 inspected. | Full problem statements, with especially useful estimation and colored-noise exercises below. |
| [Calendar](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/pages/calendar/) and [readings](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/pages/readings/) | Public. | Map topics to chapters; includes the Kay/Van Trees background. |
| Solutions, exams, lecture recordings, software | No public files found in this OCW offering. | The syllabus mentions exams and student solutions, but the public site does not supply them. R14's reference to a 2001 final-exam problem is not the exam itself. |

Chapter 2 timed out twice and Chapter 5 was inaccessible through the PDF reader during this check; neither is counted as verified readable.

### Selected notes and exercises

| Item | Specific content inspected | PLAN connection |
|---|---|---|
| [Chapter 3](https://sia.mit.edu/wp-content/uploads/2015/04/chapter3.pdf), §§3.3.3–3.4.1 | CRLB, ML, vector parameters, nonlinear estimation, sinusoid frequency/phase/amplitude estimation, and threshold/capture failures. | Distinguish local precision from a globally wrong fit. |
| [Chapter 6](https://sia.mit.edu/wp-content/uploads/2015/04/chapter6.pdf), §§6.1–6.2 | Spectral-observation likelihoods and information bounds; autoregressive noise models. | A basis for a spectral evidence score, subject to its long-record stationary Gaussian assumptions. |
| [PS5](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/e0281031ec730680e6ba3e4211c73c4d_ps5.pdf), 5.2–5.4, PDF pp. 1–2 | Amplitude estimation and its bound; BLUE with an arbitrary known covariance; a parameter-dependent variance example. | Check noise weighting and remember that a bound need not be attained. **5.3 is the most immediate exercise for correlated observations.** |
| [PS6](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/36b85618288a33a6ccaa7e468262b2b4_ps6.pdf), 6.2, PDF p. 2 | A piecewise observation model; derive ML, CRLB, efficiency, and consistency. | Local information versus nonlinear/global ambiguity. |
| [PS9](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/874711e09a6a3074feedfe0305d10803_ps9.pdf), 9.1 and 9.3 | Unequal observation variances; optimal versus restricted matched receiver. | Why extra low-quality samples need not add unlimited evidence, and how to compare a convenient scorer with an optimal one. |
| Same PS9, **9.7–9.8**, PDF pp. 5–7 | Colored Gaussian noise, whitening, covariance expansions, optimal processing. | The statistical treatment of correlated frames and noise normalization. |
| [PS11](https://ocw.mit.edu/courses/6-432-stochastic-processes-detection-and-estimation-spring-2004/a143dfe9855d7698e6009023d07bb0c5_ps11.pdf), **11.5**, PDF pp. 4–5 | Weighted-periodogram detector; compare maximizing deflection with minimizing error probability. | A useful exercise before choosing a spectral separation statistic for detection. |
| Same PS11, 11.6, PDF pp. 5–6 | ML autoregressive estimation and linear prediction. | Possible background-model reference. |

## 2. Serra and Smith — spectral audio processing

[Audio Signal Processing for Music Applications](https://www.coursera.org/learn/audio-signal-processing), Xavier Serra / UPF and Julius O. Smith III / Stanford. The Coursera page lists 11 modules and 10 assignments. Its FAQ states that free enrollment includes lectures, readings, assignments, and a final grade, without a certificate. No account was used in this inventory; the public GitHub materials are independently accessible.

### Public course repository

[Materials repository](https://github.com/MTG/sms-tools-materials) and [sms-tools implementation](https://github.com/MTG/sms-tools).

| Material | Inventory and inspection | PLAN connection |
|---|---|---|
| [Lecture PDFs](https://github.com/MTG/sms-tools-materials/tree/main/lectures) | Ten decks, filenames confirmed through the public GitHub contents API. PDFs were not individually read. | Spectral representation, sinusoidal/harmonic models, residuals. |
| [Exercise notebooks](https://github.com/MTG/sms-tools-materials/tree/main/exercises) | Twelve notebooks: E1–E9 plus three E10 projects. Prompts, skeleton code, reference outputs/test cases; no separate solution collection found. | Controlled examples suitable for learning and comparing implementations. |
| [Worked examples](https://github.com/MTG/sms-tools-materials/tree/main/examples) | Includes peak detection, STFT, sinusoidal/harmonic models, F0, residual, and stochastic examples. | Runnable demonstrations alongside the incomplete exercises. |
| Course videos and assessments | Listed on Coursera, with programming work early and peer-review projects later. | No public formal exam or separate answer key found. |

Direct slide links, **linked, not individually inspected**: [04 STFT](https://github.com/MTG/sms-tools-materials/blob/main/lectures/04-STFT.pdf), [05 Sinusoidal model](https://github.com/MTG/sms-tools-materials/blob/main/lectures/05-Sinusoidal-model.pdf), [06 Harmonic model](https://github.com/MTG/sms-tools-materials/blob/main/lectures/06-Harmonic-model.pdf), [07 Sinusoidal plus residual](https://github.com/MTG/sms-tools-materials/blob/main/lectures/07-Sinusoidal-plus-residual-model.pdf).

| Selected notebook | Contents inspected | Why use it |
|---|---|---|
| **[E5: Sinusoidal model](https://github.com/MTG/sms-tools-materials/blob/main/exercises/E5-Sinusoidal-model.ipynb)** | Four parts: reduce sinusoid frequency error; track a two-component linear chirp; track tones of very different amplitudes; model a multicomponent signal. Includes a comparison against known synthetic trajectories and explicit window-length questions. | Closest practical exercise to our sweep smear, bin error, and competing-tone problems. Contains unfinished learner code; it is not a completed robust detector. |
| [E4: STFT](https://github.com/MTG/sms-tools-materials/blob/main/exercises/E4-STFT.ipynb) | Window main lobes, reconstruction SNR, band-energy envelopes, onset detection; distinguishes window length and FFT zero padding. | Sanity checks for spectrogram changes. Reconstruction overlap and statistical dependence of overlapping frames are different questions. |
| [Peak detection/interpolation example](https://github.com/MTG/sms-tools-materials/blob/main/examples/peak-detection-process.ipynb) | Generates non-bin-centered tones, detects spectral peaks, applies `peakInterp`, plots the estimates. | A direct reference for frequency measurement and interpolation bias. |

Follow-ups **linked but not inspected**: [E6 Harmonic model](https://github.com/MTG/sms-tools-materials/blob/main/exercises/E6-Harmonic-model.ipynb) and [E10-3 Multiresolution](https://github.com/MTG/sms-tools-materials/blob/main/exercises/E10-3-Multiresolution.ipynb).

The materials README distinguishes software (AGPLv3), slides (CC BY-NC-SA 4.0), and sounds (CC BY 4.0). This inventory imports none of them.

### Smith's deeper Stanford materials

[MUSIC421A / Time-Frequency Audio Signal Processing](https://ccrma.stanford.edu/courses/421a/) is currently described as self-paced independent study. Its [ten-week schedule](https://ccrma.stanford.edu/~jos/intro421/Schedule.html) links readings, lecture overheads, 2016 YouTube topic videos, 2020 MP4 lectures, and homework.

| Material | Inspection and relevant content |
|---|---|
| [FFT Windows overheads](https://ccrma.stanford.edu/~jos/Windows/) | Public HTML index inspected: leakage, resolution, Hann/Blackman/Kaiser/DPSS windows. |
| **[Audio Spectrum Analysis overheads](https://ccrma.stanford.edu/~jos/SpecAnal/)** | Public index inspected: quadratic interpolation, bias versus SNR, least-squares/ML sinusoid estimation, CRLB, interference. The most relevant overhead collection. |
| [Noise Spectrum Analysis overheads](https://ccrma.stanford.edu/~jos/NoiseAnal/) | Public index inspected: normalization, stationarity, periodograms, Welch averaging, processing gain. |
| [Videos on the schedule](https://ccrma.stanford.edu/~jos/intro421/Schedule.html) | Week 5 includes QIFFT bias, bias versus SNR, least-squares estimation, and maximizing DTFT magnitude. Weeks 3 and 6 cover windows and noise. Links/titles inspected; recordings not watched. |
| [Homework index](https://ccrma.stanford.edu/~jos/hw421/) | Eight linked PDF homework/labs, [HW1](https://ccrma.stanford.edu/~jos/hw421/hw1/hw1.pdf) through [HW8](https://ccrma.stanford.edu/~jos/hw421/hw8/hw8.pdf). Contents could not be decoded in this audit. No solutions or formal exam listed. |
| [Spectral Audio Signal Processing](https://ccrma.stanford.edu/~jos/sasp/) | Free online book. Chapters 3, 5, and 6 cover windows, sinusoid analysis, and noise. Appendix G includes MATLAB/Octave code for interpolation, spectrograms, and F0. |
| [Maximum-likelihood sinusoid estimation](https://ccrma.stanford.edu/~jos/sasp/Maximum_Likelihood_Sinusoid_Estimation.html), [non-white noise](https://ccrma.stanford.edu/~jos/sasp/Non_White_Noise.html) | Both inspected. The first derives estimation under additive white Gaussian sample noise; the latter addresses estimating/whitening colored noise. |

This gives a bridge from spectral peaks to a statistical objective. It does not justify treating our overlapping STFT frames as independent observations.

## 3. Meinard Müller — frequency tracking and audio analysis

[Music Processing Analysis, winter 2026/27](https://www.audiolabs-erlangen.de/fau/professor/mueller/teaching/2026w-mpa) links ten public topic pages, reusing `2025w-mpa/MPA_material/` URLs. They expose slide PDFs, six-slide handouts, reading assignments, notebooks, and exam-preparation questions. No separate formal exam paper or answer key was found. The textbook requires purchase/institutional access; the [FMP notebooks](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C0/C0.html) are freely readable.

| Material | Inspection and access | PLAN connection |
|---|---|---|
| [Fourier/STFT lecture page](https://www.audiolabs-erlangen.de/fau/professor/mueller/teaching/2025w-mpa/MPA_material/MPA_Fourier.html) | Page inspected. Links the Audio Features deck plus handwritten Fourier notes. **Fifteen exam-preparation prompts**, including windows and time/frequency resolution. | Short review questions for the assumptions behind our spectrogram. |
| [Audio decomposition lecture page](https://www.audiolabs-erlangen.de/fau/professor/mueller/teaching/2025w-mpa/MPA_material/MPA_AudioDecomp.html) and [slides](https://www.audiolabs-erlangen.de/fau/professor/mueller/teaching/2025w-mpa/MPA_material/data/2021_Mueller_MPA_AudioDecomp.pdf) | 39-page PDF inspected. Harmonic/percussive/residual decomposition and NMF. Five review questions on the lecture page. | Background for separating tonal evidence from other sound. |
| [FMP Chapter 8](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8.html) | Eleven HTML/IPYNB notebook entries. | Instantaneous frequency, harmonic salience, F0 tracking, decomposition. |
| **[Fundamental-frequency tracking notebook](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8S2_FundFreqTracking.html)** | Actual notebook inspected: transition matrix, log-domain dynamic programming/backtracking, audio rendering of a track, optional constraint regions. | A transparent harmonic/DP comparator for our ridge extraction. |
| [Instantaneous-frequency estimation](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8S2_InstantFreqEstimation.html) | Index description inspected; individual notebook not read. Phase-based bin refinement and hop dependence. | Candidate alternative to magnitude-peak interpolation. |
| [Salience representation](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C8/C8S2_SalienceRepresentation.html) | Index description inspected; individual notebook not read. Harmonic summation/log-frequency representation. | Combining a tone family before tracking. |
| [libfmp](https://github.com/meinardmueller/libfmp) | Public implementation package. The tracking notebook uses `compute_trajectory_dp` and `compute_traj_from_audio`. | Inspectable implementation; not executed in this audit. |

**Tracker limitation relevant to PLAN:** the unconstrained DP produces a path across the whole input, and stronger interference can take that path. Unvoiced regions in the constrained example come from supplied annotations. It does not discover a flyover's birth/death in noise, so it is a comparator rather than evidence that our failed off-state experiments are solved.

The FMP landing page distinguishes notebook text/figures (CC BY-NC-SA 4.0), the `libfmp` package (MIT), and audio (individual original licenses).

## 4. Gustaf Hendeby / Linköping — localization and association

### Sensor Fusion, TSRT14

[Course information](https://isy.gitlab-pages.liu.se/rt/en/courses/TSRT14/info.html), Spring 2026.

| Material | Inventory and access | Priority |
|---|---|---|
| [Full lecture decks](https://isy.gitlab-pages.liu.se/rt/en/courses/TSRT14/lectures.html) | 10 decks, each in one-slide and four-slide-per-page forms. | High: lectures 2–3. |
| [Video modules with slides](https://isy.gitlab-pages.liu.se/rt/en/courses/TSRT14/video-lectures.html) | 40 numbered modules; matching PDFs, YouTube links, and reading references. Recorded for 2020–2021 teaching and retained. [Playlist](https://www.youtube.com/playlist?list=PLluhvIZgE0mP3Cm36ua4i98A-G43Lw_KU). | High for selected topics. |
| [Exams](https://isy.gitlab-pages.liu.se/rt/en/courses/TSRT14/exam.html) | **Eight dated exams plus one practice exam**, every row linking an exam PDF, worked solutions PDF, and MATLAB data. | Highest-value solved exercise bank found. |
| [Acoustic localization lab](https://isy.gitlab-pages.liu.se/rt/en/courses/TSRT14/lab1.html) | Public 13-page instructions, starter code, report template, and 22 MB example data. Example recordings are explicitly supplied for outside users. | High: joint clock/position and geometry. |
| [SigSys toolbox](https://sensorfusion.gitlab-pages.liu.se/edu/sigsys/sigsys-open.zip), [manual](https://sensorfusion.gitlab-pages.liu.se/edu/sigsys/sfmanual.pdf) | Publicly linked; archives/manual not inspected. | MATLAB support for the examples. |
| Exercise compendium | Course information places its link in Lisam/SharePoint. | Account-bound; not publicly inspected. |

The exam index lists 2026-08-18, 2026-06-02, a 2026 practice exam, 2026-01-08, 2025-08-19, 2025-06-02, 2025-01-09, 2024-08-20, and 2024-05-29. The January 2025 exam and solutions were opened; contents of the newer 2026 papers were not verified because PDF retrieval failed.

| Selected item | Inspected content | PLAN connection |
|---|---|---|
| [Lecture 2](https://sf.edu.hendeby.se/le2.pdf), 30 PDF pages | Nonlinear WLS, Gaussian ML, grid/Gauss–Newton methods, partly linear models. | Robustly fitting and profiling nuisance parameters. |
| [Lecture 3](https://sf.edu.hendeby.se/le3.pdf), 33 PDF pages | Fisher information, TOA/TDOA, an unknown common clock offset, cost and CRLB maps. | Shared clock and poor localization geometry. |
| [Safe Fusion slides](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/videos/04-SafeFusion.pdf), 8 pages | Combining estimates with unknown dependence; overconfidence from reused evidence. | Correlated harmonics and events must not become independent votes. This is a conceptual connection, not an STFT covariance derivation. |
| [2025-01-09 exam](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/20250109exam.pdf), **Q3**, with [worked solutions](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/20250109sol.pdf) | Jointly estimate position and nuisance source power/attenuation; identify the conditional linear structure; eliminate it to derive a reduced nonlinear cost. | A solved variable-projection exercise. Q1(b) also asks for an optimal Gaussian detector; Q1(c) combines independent estimates. |
| [Acoustic lab instructions](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/localization.pdf), **§6 tasks 4–5** | Compare geometries using cost/CRLB maps; compare a search over position plus emission time with Gauss–Newton and separable least squares. | A concrete location/clock exercise. Uses four synchronized microphones and an RC car emitting pulses, so it is not our single-microphone Doppler setup. |

The video index also exposes modules 2 (WLS), 5 (ML/CRLB), 6 (NLS), 10–11 (sensor-network estimation), 12 (detection), 25 (shooter localization), and 38 (microphone lab). These were catalogued from the index; not every video or deck was opened.

Lab downloads, linked but not unpacked: [starter files](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/SFlab1.zip), [recordings](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/SFlab1-data.zip), [report template](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/SFlab1-report-template.zip). The January 2025 exam's [MATLAB data](https://isy.gitlab-pages.liu.se/rt/assets/TSRT14/data20250109.mat) is also linked, not downloaded.

### Target Tracking

[Course home](https://mtt.edu.hendeby.se/) identifies the 2025 offering; the schedule extends into January 2026 and some exercise files have later revisions.

| Material | Inventory and access | PLAN connection |
|---|---|---|
| [Lecture index](https://mtt.edu.hendeby.se/lecture.html) | 10 deck entries: nine numbered lectures plus a preliminaries deck, each with standard/4-up versions. | Gating, clutter, data association, hypothesis management. Count is from the schedule; the home page's smaller lecture count is stale. |
| [Lecture 4: GNN/JPDA](https://mtt.edu.hendeby.se/lectures/le4.pdf) | Inspected, 51 PDF pages including overlays. | Global assignment and association hypotheses, rather than separate per-event choices. |
| [Lecture 5: MHT](https://mtt.edu.hendeby.se/lectures/le5.pdf) | Inspected, 58 PDF pages including overlays. | Retaining, scoring, pruning, and merging several assignments. |
| [Exercises](https://mtt.edu.hendeby.se/exercise.html) | Three coding-assignment PDFs, two MATLAB data files, three helper source files. No worked solutions linked. | Build a small test problem with missing detections and confusers. |
| [Reading list](https://mtt.edu.hendeby.se/resources.html) | Public bibliography, including assignment algorithms and MHT scoring. | Further references; not every linked paper is open. |
| Exam | [Instructions](https://mtt.edu.hendeby.se/2026/01/08/exam-info.html) require arranging receipt with the instructor. No public paper or solution found. | Not counted as an available exam. |
| Videos | Demonstration links appear in slides; no full lecture-recording series found. | Demonstrations only. |

Assignments: [Exercise 1](https://mtt.edu.hendeby.se/assets/ex1.pdf) builds simulation/basic tracking ([data](https://mtt.edu.hendeby.se/assets/ex1data.mat)); [Exercise 2](https://mtt.edu.hendeby.se/assets/ex2.pdf), **inspected, four pages**, adds multiple targets, missed detections, Poisson clutter, GNN and JPDA ([data](https://mtt.edu.hendeby.se/assets/ex2data.mat)); [Exercise 3](https://mtt.edu.hendeby.se/assets/ex3.pdf) adds MHT and comparison with earlier trackers. Exercises 1 and 3 were catalogued; their contents were not fully inspected.

Helper source files were read: [auction.m](https://mtt.edu.hendeby.se/assets/auction.m) has an explicit unassigned cost; [computeTrackProb.m](https://mtt.edu.hendeby.se/assets/computeTrackProb.m) includes a no-measurement/missed-detection case for each track and clutter-rate normalization; [murty.m](https://mtt.edu.hendeby.se/assets/murty.m) generates several best assignments. They are educational MATLAB implementations; runtime behavior and reuse license were not assessed.

Transfer to our task is strongest for assignment and maintaining alternatives. These courses track targets across time scans; our immediate problem is a batch assignment conditional on shared location and recording clock.

## 5. Ryan Tibshirani / Berkeley — calibration and uncertainty

[Stat 241B / CS 281B, Spring 2024](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/).

The public schedule has ten full 2024 lecture-note PDFs, one one-page 2024 calibration outline, and a linked full calibration note from 2023. There are four homework PDFs (6, 4, 4, and 3 pages), a [project brief](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/project.pdf), and a [source repository](https://github.com/ryantibs/statlearn-s24). The course page links source directories; their contents were not fully enumerated. The [syllabus](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/syllabus.pdf) grades homeworks and a project, with no exams. Homework solutions are explicitly on login-only bCourses. No lecture-video collection is listed.

| Material | Inspected content | Use and limit |
|---|---|---|
| [Conformal Prediction](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/lectures/conformal.pdf), 16 pages | §2: held-out calibration, finite-sample quantiles/coverage, variability conditional on calibration, limitations of conditional coverage. §4: locally weighted scores and conformalized quantile regression. | Direct foundation for Phase 4 regions. Geographic sets and independent site/day groups need our own formulation. |
| [Homework 4](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework4.pdf), 3 pages | **Q2:** derive Beta-distributed calibration-conditional coverage and simulate different calibration sizes. **Q3:** conditional-coverage impossibility and comparison of scores by local coverage. Q1 supplies CDF/quantile facts. | The best uncertainty exercise sheet found. Public questions; restricted solutions. |
| [Conformal Prediction Under Distribution Shift](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/lectures/conformal_ds.pdf), 15 pages | Covariate-shift weighting, departures from exchangeability, sequential adaptive conformal inference. | Relevant to changed sites/devices. Covariate-shift validity assumes the conditional response law stays fixed; not a general repair for arbitrary shifts. |
| [Forecast Scoring and Calibration](https://www.stat.berkeley.edu/~ryantibs/statlearn-s23/lectures/calibration.pdf), 18 pages, 2023 | Proper scores, log/Brier/CRPS and interval scores, calibration and sharpness. | Assess honesty and usefulness of uncertainty; these scores do not calibrate our whole-search winner on their own. |
| [2024 calibration outline](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/lectures/calib_bw.pdf), 1 page | Topic checklist including Blackwell approachability. | Use the full 2023 note for substance. |

Other inspected homeworks: [HW1](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework1.pdf) includes a Brownian-bridge/KS simulation that could inform null diagnostics; [HW2](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework2.pdf) covers RKHS/minimax theory; [HW3](https://www.stat.berkeley.edu/~ryantibs/statlearn-s24/homeworks/homework3.pdf) covers sparsity/regression. The latter two have low immediate priority.

There is no dedicated post-selection, multiple-testing, or grouped-recording unit in this schedule. The `located` selection rule still needs separate statistical treatment.

## 6. UNH — Abraham, Lyons, and the sonar short course

The [Marine Acoustics, Sonar Systems and Signal Processing course page](https://eos.unh.edu/center-acoustics-research-education/education/marine-acoustics-sonar-systems-signal-processing-short-course) publicly provides the agenda and detailed topic descriptions. Relevant sessions include correlated-noise matched filters, passive localization, detector design, Doppler filter banks, and detection-performance estimation.

The page states that participants receive electronic notes for all sessions and that these are included in the paid course. **No public slide decks, exercise sheets, exams, or note downloads were found on the inspected page or in the targeted search.** This is a relevant teaching program, but presently a weaker source for immediate self-study than the public collections above. Its underwater and array-specific material also needs adaptation to our setting.

## Access and scope notes

- Public indexes and selected PDFs/source files were checked on the date above; link availability can change. Course years are distinguished from later file updates.
- Counts treat alternate slide layouts as versions of one deck and exclude videos from slide counts. PDF page counts can include animation overlays.
- No exercises were solved or source packages executed during this inventory. The mappings to PLAN are assessments of potential use, not evidence that a method will improve our benchmark.
- Missing public solutions at MIT, Berkeley's restricted solutions, and UNH participant notes are recorded explicitly so a later acquisition task can target the actual gaps.

## Acquisition and reading update, 2026-11-04

The public documents, linked assets and four repository archives have now been acquired under `$DOPPLERTRACK_DATA/reference/courses/2026-11-04/`. This includes 315 valid PDFs totaling 4,378 physical pages (including repository-contained PDFs), notebooks, source, lab/example data and HTML book chapters. Lecture-video acquisition is recorded separately in the local video manifest. The archive README, source manifests and file hashes provide the precise inventory and exceptions. No source materials are stored in git.

MIT Chapter 2 and all eight Stanford homework PDFs were successfully downloaded and text-extracted, resolving earlier retrieval failures. Stanford HW5 includes sinusoid estimation in interference and spectral peak interpolation. MIT Chapter 5, unavailable Stanford video links, login-only solutions and participant-only notes remain acquisition gaps as recorded locally.

The [reading assessment](course-reading-review.md) compares selected relevant materials with the code and measured failures. It records one reproduced trajectory-decoding inconsistency in the unadopted likelihood tracker and distinguishes it from the remaining source-association and motion-model problems.
