# Research reset: what the accumulated experiments establish (2026-11-04)

<!-- index
question: Which research conclusions survive a read-only audit of designs, saved summaries, scripts, data splits and unfinished stages?
outcome: The failure mechanisms are well supported on development data; no design has passed a complete automatic-location and calibrated-verdict gate, collective v3 is partial, v4 is unmeasured, and detector S2 is interrupted
-->

This is an evidence audit, not a new experiment. The source baseline is `dev` at `17758a5`.
The lineage table and broad inspection inventory below recover an earlier audit. The current review
independently rechecks the key original artifacts listed in the dated section at the end; inherited
findings outside that section remain the earlier audit's reported findings, not a claim of fresh exhaustive verification.
No audio processing, search, remote command or new scientific run was performed. Saved JSON/CSV/text,
completion markers and relevant script definitions were inspected locally. Historical commit IDs below are
those stored in the records and run metadata; the history rewrite means they are not necessarily current
checkout IDs. A successful job, a promising diagnostic and a passed research criterion are different things.

## Conclusions that survive

- **The fitted event is a fragile intermediate.** Saved fits reproduce the two demonstrations, while the
  original automatic top-two pipeline finds neither recording. Timing gates, a fixed tone sweep, wrong-line
  tracks and an ill-conditioned straight-pass fit each lose evidence. The trajectory-shaped candidate
  diagnostic supports removing that bottleneck; it does not establish a complete replacement locator.
- **Model mismatch matters more than local frequency precision on the studied passes.** Noiseless Livermore
  trajectory curves fitted as straight passes miss slant range by a median 229 m (15.6%) on the primary 29.
  Noise-only ideal-curve fits and the reduced optimizer behave well. This does not absolve the production
  optimizer: stage 2 finds failures even on rendered ideal curves. The later 20–50 m bound is a conditional
  sensitivity calculation, not measured position accuracy or a confidence region.
- **The failed designs remain failed.** Three tracker rounds, two window rounds, the heavier pass models,
  weave flag, hypotheses, frequency whitening, warp and saved-fit verdict criterion did not earn adoption.
  Useful sub-results do not reverse their gates.
- **No complete, calibrated automatic locator is established.** The clock gate helps on the two development
  recordings under different weather settings. Collective v3 finds a good Oyster Bay candidate in one fine
  cell, loses the eagle cam at pruning, and has no matching verdict null. v4 has no completed local result.
  There is no measured independent confident-wrong rate or uncertainty-region coverage.

## Lineage and decisions

Links name the original criterion and fuller numerical tables. Run paths are relative to
`$DOPPLERTRACK_DATA/runs/`; abbreviated names below all start `2026-11-04-` unless stated otherwise.
“Adopted” describes the recorded engineering/default decision, not external validation.

| Question and original gate | Versions, provenance and completed evidence | Status and changed decision |
|---|---|---|
| [Baseline](2026-11-04-bench-baselines.md): reproduce saved-fit and raw-audio seed outputs | Upstream `a16b700` versus `5314396`, each revision's own CLI/lock; `bench-*-saved-fit-t2`, `bench-a16b700-raw-audio-t2-2`, `bench-5314396-raw-audio-t2`. Saved fits: 43 m / 877 m refined on the two sources; automatic: Oyster Bay true pair 10th, eagle true pair absent. hp150 reuses Oyster Bay and its clean saved fits. | Reproduction established; automatic success not established. Saved-fit scoring robustness is not end-to-end codec robustness. |
| [Timing](2026-11-04-timing-convention.md): true pair reaches scoring within 250 m on every judged positive with no more triples | Heard ±6 s versus emission gates 8/12/16/20 s and steepest-fall tolerances off/2/3/4/6 s; ±16/4 minimizes the passing total, 49,039 versus 89,037. `timing-convention`, `merge-sweep/sweep_table.json`; original `51f59ce`, reproduction `18ff8b4`. Eagle criterion amended **before deciding sweep** to use selected full-recording detect events, not automatic top two. | Development setting only. Oyster Bay raw-audio rank remains 8–9; saved-fit Oyster Bay regresses to rank 3 and a wrong winner. Default heard gate retained. Earlier wider-gate and narrower-window attempts (2026-11-03 records) failed across both sources. |
| [Model error](2026-11-04-model-error.md): separate noiseless trajectory bias, noise and optimizer; perturbation exceeds bootstrap spread | `model-error-2`, 200 moving-block replicates, 2 s blocks, residuals detrended over 5 s; `straight_pass_ls.py`, `model_error.py`, `crb.py`. Livermore: 29 primary / 11 flagged, clock fitted per pass, reconstructed site, ridge-span oracle windows. Primary A curve: 229 m, 15.6% range error; ideal fit exact. Full ±150 s error 35.6%, so the stated 14% ±5-point full-window reproduction **fails**. | Model mismatch diagnosed within this corpus. Drift 0.5% matters; longer trajectory span worsens fit. Error is not exclusively model error: published ridges retain unexplained slow structure, and production `fit_event` adds objective/optimizer failures. |
| Model-error stage 2 / Alaska stage 3 | `model-error-stage2/stage2.csv`: 320 pass/input/objective rows, wide-band correction supersedes aborted 450 Hz renders; contrast has >10% range error on 6/29 primary ideal renders. Alaska: initial 50 then `merge-alaska`, `5df450b`, 788 crossings, 775 complete at three c values; authors' tone places 0.70–1.50× band, FR24 CPA supplies window/reference. Median absolute range error 11.9–12.1%; temperature removes speed bias (+3.4% to −0.4%). | External corpus check of an **assisted fitter**, not blind detection/location. Crossings repeat flights/nodes/days; crossing-bootstrap intervals are not independent-site intervals. Failed 0.85–1.15× narrow-band run (655 crashes) stays failed. Later full run supersedes the stale “queued” paragraph. |
| Heavier models / weave flag: range ≤160 m, flagged median no worse, ≥20/29 identified; turn adds separate turning/nonturning/identification gates | `heavier-model`, `heavier-model-both`, `turn-model-{synth,fit,profile,flag}`. Drift/acceleration/both primary errors 750/231/576 m. Turn primary 373 m, turning 882 m versus target 201; only 3/16 turn rates identified versus 11. Synthetic range history exposes unidentifiable sign/height/speed. Flag 0.5°/s retains 18/40 at 441 m, rejected group 149 m. | All fail. Reducing RSS is not improved range. Sign criterion impossible by construction; later identifiable parametrization does not rescue range gates. Threshold alternatives are exploratory, not additional successful retunes. Bootstraps cancelled because no remaining outcome changed rejection. |
| [Covariance](2026-11-04-frame-covariance.md): measured overlap factor and range bound agree with Harris / 63–74 m | `cov-measure-s*`, `cov-bound`, `cov-bound2`. Both original and follow-up agreement gates fail. SNR-matched median sigma 0.137% versus assumed 0.45%; raw correlation ≈0.99, detrending produces negative tails; six passes outside synthetic SNR support are clamped. | Published working range becomes 20–50 m, **conditional on ideal curve, SNR transfer and covariance choice**. Neither covariance endpoint is a demonstrated bound on real errors; “provisional comes off” does not establish coverage. |
| [Tracker round 1](2026-11-04-freqtrack.md): lower error, no more bridges or fragments than ridge at 2% on primary 29 | `freqtrack/livermore_summary{,_run2}.txt`; off-state tracker, noise-set theta/birth, oracle band/span/reference; counted retune changes birth/theta and rise/hop handling, `run2_source.patch` preserves dirty defaults. First: 0.45% vs 0.48%, bridges 13 vs 36, fragments 204 vs 12. Retune fails all three. | Not adopted. Strong flagged-pass sub-result (0.84% vs 15%) is conditional on the scoring/selection rule; sparse coverage and oracle band prohibit a blind-detection claim. |
| [Tracker round 2](2026-11-04-hmm-tracker.md): same three-part gate | Hysteresis BORN/ON, two whitenings; synthetic pick initially selects no-coverage theta 9, counted retune requires ≥half weak-pass coverage. `sde-c-fleet-merge/hmm/*/hmm_summary.txt`, `02d705f` / `3438552`. Best frequency arm: 0.37%, 28 bridges, 59 fragments versus 0.74%, 29, 12. Retune bridges 144. | Not adopted. Fixing empty-track selection does not remove noise-continuation floor. |
| [Tracker round 3](2026-11-04-tracker-likelihood.md): same gate after synthetic ROC qualification | Rician/Exp forward-backward, a=1/2/4/8 × birth grid; initial floor 12 tracks/h, counted Harris weight retune w=.254 permits one point (a=2, beta=1e−3). `ll-retune1-merge/ll/a2_b1e-03/ll_summary.txt`: 0.60%, 190 bridges, 85 fragments versus .48%, 36, 12. | Not adopted; no third configuration within a failed round. Weight fixes the measured synthetic floor, not arbitrary real-frame dependence or tracker correctness. |
| [Least squares](2026-11-04-least-squares-fit.md): no worse f0/v/range than better image objective, and event-2 timing no worse | Padded-band bug discarded; exact-band run 2 at `51f59ce`, time-reparam equivalence checked, later physical-bound/polish effects recorded. `least-squares-fit/{livermore,dev}.json`. Weighted v/range 6.7%/15.2% beat image fits, f0 and both development timing comparisons fail. | Not wired into detect; waits for a reliable track. Saved summary JSON contains NaN range medians; replacing nonfinite per-fit errors by infinity, as the record specifies, reproduces its 16.7%/15.2% primary medians. This audit did that arithmetic only; no refits. |
| [Window round 1](2026-11-04-window-length.md): every f0/v/d median ≤1.05× baseline for both objectives and both cohorts | 2.048/1.024/.512 s, padded FFT, composites; `window-length`. Initial .512 “kept” reversed after correcting ob-e03 reference; no candidate meets corrected gate. Paired tests mostly unpersuasive, oracle composite worse. | No package change. Shorter windows sometimes improve fit medians, but neither a general improvement nor a new effective-frame count is established. |
| [Window round 2](2026-11-04-window-round2.md): synthetic detection no lower and ridge error ≤1.05× C0 at 1/h | Six window/hop/taper candidates; noise-name bug fixed, valid noise reused; `window-roc-2-*`, `window-gate/window_gate.json`, `5a2f0d5` / `968aa46`. Each alternative misses detection or ridge-error gate on nine .03 passes. | Stops before real-data/Tier 1/Tier 2; no retune spent. Brightness bimodality across seeds remains a useful failure diagnosis. |
| [Detector](2026-11-04-detector-threshold.md): synthetic gate then ≤1/h on real background, retain two matches and all labelled events in top ten | S0/S1 × three bands; amendment distinguishes fundamental from image band. S1's synthetic thresholds 9–11, recall 7/9 versus S0 8/9; wider S0 gets 4/6 high passes. S2 retune: rejected eight correlated null copies replaced before run by forward-minus-reversed maximum, standardized across noise candidates. `detector-gate`, `detector-roc-s2-s{7,8,9}of9`, source `98fe1c2`. | S1 fails; wider S0 passes **synthetic only**. S2 interrupted and incomplete, not a failed gate or a completed retune decision. B0 has noise + four pass files, B1/B2 no completed local unit files. Process-pool rescore edit at final source is reported untested; no S2 gate or real Tier 1. Narrow-band S0's real failure does not prove every wider S0 setting fails without measuring it. |
| [Event pair / comparable](2026-11-04-event-pairs.md): true eagle pair first of ten; A1/A2/A3 for normalized score | Raw score gives rank 5. Comparable wrong-row median/MAD null (N=1000) raises it to rank 2; A2 wrong-box margin criterion withdrawn **after** failure, A3 passes. `merge-pairs-a`, `18ff8b4`: A1 gap −.049, bootstrap-noise SD .128, first in 42% of redraws. CPA platform row difference changes seeded null rows. | Original stage-A gate not met; off-by-default library result later adopted in locate under a different criterion. Bigger N would improve scale precision, not demonstrate location correctness. Frozen-clock extras (three versus zero) are a selected development diagnostic, not a verdict calibration. |
| [Hypotheses](2026-11-04-hypotheses.md): true flights admitted within 250 m (B1), no more rows (B2), then A1/A3 | LS + image optima/profile boxes. Initial B1 fails; counted ×9 threshold + drop-weak retune makes all brightness hypotheses uninformative. `merge-b1b2` reproduces failure on each case. Original-hypothesis pair run `6f0ce38`: 28/30 searches, two memory failures; eagle A1 complete (rank 3), Oyster A3 already rank 8 of nine. N=250000 cancelled and results intentionally unread. | B1/A1/A3 fail; B2 alone passes after retune. Missing tenth Oyster pair cannot restore first place. No adoption; “sensitivity range” is not a calibrated confidence region. |
| [Weather / event fit](2026-11-04-case-weather.md): both true pairs rank 1; refits restore margin/rank | Ground c regresses saved fits; per-flight lapse path recovers Oyster but eagle rank 2. `merge-refit-savedfit`, `merge-basin-profile`, `0734635` / `2559728`: full-record eagle control remade after clip control failed; temperature remakes still fail. Oyster brightness surface has 50–51 near-equal optima. Gated LS (`merge-gated-track`) follows the gate, fails accuracy/eagle rank; overlay's “another source” inference is corrected by `find-test`. | Temperature remains opt-in. Basin switching and model-shaped candidate restriction explain sensitivity; no evidence that 15°C is physically best. Find-test true curve beats straight brightness on Oyster but weak eagle line misses half-frame presence criterion. Removing fits is a motivated design, not a criterion pass. |
| [Warp](2026-11-04-warp.md): reference first, wrong boxes no worse, refinement no worse, Tier 2 budget, gain survives controls | `warp/warp_oyster_{all,band_all,refine}.json`; corrected off-grid harmonic pooling before deciding run. Oyster only, exact reference + ten selected wrong candidates, joint clock, strict tone; z separation .07 versus 2.41 control, 200 m versus 0 refinement shift; ~2 min/candidate. 50 m warp refinement unrun. | Fails; not adopted as scorer/verifier. Candidate shortlist result is not a full-search negative test. Drift helps wrong candidates more; across-frequency lead tested separately and failed. |
| [Frequency whitening](2026-11-04-whiten-frequency.md): no worse rank/margin, no fewer matches, no more false alarms at own threshold | `sde-c-fleet-merge`, `02d705f`; frequency Tier 1 known-point failure after spans saved. Eagle margin 2.54→1.16%; background 6.98→18.85/h; hp150 event 2 absent. | Fails, retune unused. Separate tracker option can remain; isolated Oyster scorer gain does not support package switch. |
| [Coherent duration](2026-11-04-coherent-duration.md): theory gate ±1 dB, eight-real-pass gate ±1 dB, then blind 19-pass gain ≥3 dB | C1/C3/C9/T; initial Gumbel thresholds then counted empirical-tail + .5 dB-grid retune. `coherent-duration-gates[-retune]-judge`; `306b1fb` / `4f44d40`. Retune synthetic gaps 6.0/4.25 dB versus 4.8/3.0; assisted real gap −2 dB among five uncensored pairs. Both gates fail. | Closed undecided, no blind test or shortlist adoption. [Successor](https://github.com/SokolskyNikita/doppler_experiments/blob/64e8337/docs/proposals/2026-11-04-coherent-duration-2.md) changes theory target via operating-point simulation, extends levels, preserves real gate; unrun. Assisted gain does not establish wrong-flight discrimination. |
| [Locate / clock](2026-11-04-clock-gate.md): reject recorded wrong clocks without dropping true pairs; pair/filter defaults chosen by more seed finds and no losses | `locate-t2b-*`, `locate-comparable-*`, then `locate-gate-{w,15}-merged`, `locate-15-off-merged`; `d3a9391`, `702276c`, `894b27c` / `db398cd`. At weather on Oyster true pair/refined 278 m; at 15°C eagle true pair/390 m with gate/filter on. Other weather/filter eagle winners can be wrong pairs near truth. Midnight missing-day case never reaches intended reason. | Clock/default engineering adopted, conditional on metadata and these groups. Literal “Oyster still found” clause is not met at 15°C; favorable gate conclusion means no additional loss relative to same-temperature baseline. “Located” in narrative means near-truth candidate: every emitted candidate verdict is still ambiguous. |
| [Saved-fit verdict null](2026-11-04-verdict-null.md): all positives uniquely clear own 1% maximum threshold, negatives do not | `verdict-null-merge`, `0068669`, five cases ×51 searches; saved fits, comparable, no extras, no clock gate. Oyster own 19.96 vs gamma25.81 (3/50 days exceed); eagle wrong-pair winner8.596579 vs14.00 (26/50), true-pair mode second8.559615. Verdict hash verified; the original narrative that this run's eagle winner is true is incorrect. | Gate fails: zero positive cases clear; cannot promote “located”. This falsifies usefulness of this statistic/threshold under this null here, not validity of every possible threshold. The unrun automatic arm is not logically guaranteed to be worse. |
| Collective v1 → top-five rerun | `collective-find-merge`, `40454ae`: 2 km coarse, 200 m fine, ±10% tone (±5% comparator), top-five cap replacing ≥.7 maximum. All 12 own-day units complete. Oyster wrong 29.6/61.1 km, eagle .5 km both flights, midnight19.1 km; fine340–2543 s. | Original positive and runtime gates fail. Neither a successful eagle case nor later designs erase that. Initial margin, top-five, wider-tone/margin, 1 km/subwindow and dense/unique-pass changes are successive designs, not the original proposal's sole clock-width retune. |
| Collective v2 (wider tone / margin / log-frequency scorer) | `collective-coarse-v2-merge`, `91fb1c1`; ±25% fine, coarse sweep +2 percentage points, 2-s shifts/2% tone/60 samples, 2 km; margin 2 MAD-sigma capped20. Full coarse maps + cell0 fine only in summary. Eagle true coarse rank2/.5 km; Oyster rank1698. Truth-cell diagnostics at `75a8e02` / `5ba8c4b` read labels. 19/19 extra Oyster cells and 111/120 other extra-cell units present. | Superseded, incomplete global fine result: merge refuses nine missing units and has no collective.json. Diagnostic chosen cell is not blind recovery. Length dilution, not segment coverage, explains lost raw brightness. |
| Collective v3 (1 km / best120 s) | `collective-coarse-v3-merge`, `68a906c`: eight coarse maps + **one** fine cell per case. Oyster coarse rank1/Z18.50, cell0 fine318 m/Z17.19, both true flights (weak z .62); hp150318 m. Eagle true rank37, outside margin; cell0 1.86 km but neither true flight. Wrong WSW coarse18.22, cell0 fine15.04. Eagle true-cell diagnostic `337f23f` shows missed peak and duplicate use of one pass. | Partial and not adopted. No all-kept-cell fine merge or matching verdict null. Comparing coarse18.22 to coarse18.50 is a near-tie diagnostic, not a false-positive threshold or comparison of final maxima. Even a 1.86 km wrong-pair winner fails the matched-flight criterion. |
| Collective v4 (dense coarse / unique pass) | Source `aeba858` / smoke `347786b`; 1-s shift/1% tone and120 samples per240s window, one-window-per-pass, fallback top3. Stop log reports smoke cancelled before result; no completed v4 result locally. Current script labels v4. Twelve-case known-answer turn/climb/straight synthetic suite proposed in record; no local suite results found. | Unmeasured. v3 evidence cannot be assigned to v4. Current code is a research driver, not a completed CLI adoption. Any selector/statistic correction requires a new version and own-day/null redraw. |
| [Coverage / integration](2026-11-04-us-phone-interval-coverage.md): model opportunities, not a location pass gate | `us-movement-pickup`, `us-residential-aircraft-coverage`, `us-doppler-integration-coverage`, `us-indoor-outdoor-coverage`, `us-phone-interval-analysis`. Monthly snapshots→four native days; housing/activity/range assumptions; one-hour hit14.18% day/1.27% night, any positive time and ≥one tracked prop. Exact synthetic known-shape18s saves7dB vs2s; eight assisted real replays highly variable. | Conditional modeling and assisted sensitivity only. No measured blind recall, multiple-pass probability, fleet-wide tone fraction, representative national sample or location success rate. Phase repeats, carriers, snapshots and neighboring homes share signals/backgrounds. |
| [Evaluation preparation](2026-11-04-evaluation-prep.md) / [traffic](2026-11-04-site-traffic.md) | ESID375/710/937 v3: spectrograms, two-day cuts/weather, 1 km CPA builds; `eval-cpa-esid*/prepare.json` inspected. Traffic checks and metadata already use reference locations. ESID740 first-pass blind sheet inspected; default Tier1 excludes calibration. | Engineering readiness, not evaluation. No local results.json found containing these reserved-case searches. Traffic screening establishes possible sources, not audibility; A2O position uncertainty prevents a precision claim. |

## Collective completeness and null equivalence

The locally available first-design collective null comprises **84/95 completed result units**: 47/50 SWFL and
37/45 Essex, all metadata at `a225ac8`, 2 km / top5 / ±10%, weather off. These are **v1**, despite later informal
numbering. Each result describes a complete five-cell fine search for that draw. No `null_draws.npz` exists in
these pulled unit directories, although the handoff describes that file. The current `collective_null.py`
only reads `null_draws.npz` plus `unit.json`, so it would silently omit this local collection. No collective
verdict summary was found. This is an artifact/schema incompatibility as well as an interrupted sample.
There are no local completed v2/v3/v4 matched-null verdicts; NY draws were held after a reported smoke.

An audit of the current definitions adds these constraints before any future verdict:

1. Freeze and hash the **entire procedure**, including detector/preselection, actual window/tone source,
   coarse/fine grids and sweeps, per-window normalization, subwindow maximum, pruning/cap, pass assignment,
   clocks, weather, modes and budget. `Window.from_detection` actually uses the refined `EventFit` fields
   from `detect_events`, although the proposal calls them pre-refinement coarse estimates. That dependence
   must be explicit; dropping v/d does not remove all dependence on the fitted template.
2. Same per-window sweep on wrong CPA rows is useful normalization, but does not price the maximum over all
   windows/positions/clocks/retained cells. Own-day cell0 versus other-day all-kept-cell maxima is not the
   same statistic. A capped coarse-to-fine pipeline can have a calibratable null for **that pipeline**, while
   still missing the real peak; it is not exhaustive search over the mathematical position/clock space.
3. `collective_run.py` merges by the best cell's winner but does not merge all cells' alternate modes; extra
   cells are read when result.json exists without requiring unit completion. `collective_find` keeps one
   clock per point and separates reported modes by distance only, unlike the proposal's distance **or clock**
   definition. A second clock at the same place can therefore disappear. Unique-clearing-mode evidence is
   incomplete even when a best score is available.
4. No-start collective draws run without a clock gate. A metadata-gated successor needs null days mapped to
   the recording date with the same time-of-day and start tolerance, as the verdict proposal describes.
   Positives and nulls must share trace-day coverage, no-candidate handling and interruption policy too.
5. Reusing Oyster draws for sources-removed is reasonable only when all other inputs/settings are identical
   on other days. It creates no new independent null sample or negative recording group. Weather, selector
   or other changed-statistic fixes invalidate older draws.

## What was actually held out

`bench/cases.json` and `bench/tier1.json` keep development, calibration and evaluation distinct, but they are
not synonyms for an untouched corpus. Oyster Bay variants, moved boxes and source removal share a recording;
eagle clips and midnight variants share theirs. Livermore is one development group despite two inferred
sites and 40 passes. Its primary29 are selected by agreement of published ridge and trajectory (RMS<1.6%);
oracle bands, published spans and fitted per-pass clocks make these assisted comparisons. The flagged11
must remain visible. Alaska is a different corpus/device, but an assisted CPA-window/tone-selected fitter
check; 788 crossings are not 788 independent sites/flights.

The reserved calibration groups are ESID740 and XC979185. ESID740 has already had a blind 20-minute sheet,
layer-2 association, traffic/temperature checks and spectrogram/gap preparation. Its labels were first-pass,
not owner-checked at creation. Default `run_tier1(sets=("development",))` excludes that span; the inspected
pooled background comprises Essex and AeroSonicDB, not ESID740. I found no local benchmark results.json
showing a reserved calibration/evaluation search. This bounded filesystem check cannot prove no historical
or unpulled run exists. ESID375/710/937 have had reference-aware preparation and traffic screening; they may
still provide a frozen method evaluation, but are not uninspected natural samples. Selection/negative labels
based only on absence of tracked props do not label all acoustic aircraft.

The coherent experiment's “calibration/evaluation” means alternating 40 s segments within the same nine
background recordings, not the benchmark's reserved groups. 419 calibration segments and repeated ten-segment
mixtures share background structure; eight verification and 19 planned test passes share Livermore, and all
28 coherence-diagnostic passes were previously inspected. Scaling every background to a common band power
also changes the nuisance distribution. The actual completed gates supply the true flight and clock. No
blind wrong-flight competition ran after the gates failed. The earlier private-background replay has 49
held-out intervals from the same recording; synthetic test has 47, with 16 phase repeats and repeated carrier
calibration contexts. These are paired sensitivity studies, not independent field-validation sample sizes.
The private pilot has become development data; aggregate reported errors are read from its public record,
not verified here against private candidate/site files.

## Tail uncertainty and failed-criterion accounting

The saved-fit run is a decisive failure **of its specified usefulness gate**: own-day scores are below the
fitted thresholds. Its stored eagle-cam top mode is the wrong pair (8.596579), with the true pair second
(8.559615), correcting the original record's winner claim; the raw saved-fit baseline is a different score/run. It does not prove that a fitted 1% tail is calibrated, that another-day traffic stochastically
dominates all live false matches, or that every automatic statistic can only perform worse. Recurrent routes
can make the null difficult, but traffic density, coverage, source mix, season and conditioning can move its
tail in either direction. Call it a specified wrong-day competitor distribution, with exchangeability unproved.

Fifty draws provide at most about a 5.8% one-sided95% upper tail bound after **zero** exceedances at a fixed
threshold under independent Bernoulli trials (the usual approximation is3/B=6%). A fitted Gumbel extrapolation
and its bootstrap interval are conditional on that family and sampling model. The script fits location/scale
and then reports a KS statistic on the same data; comparing it to1.36/sqrt(n), a fixed-distribution cutoff,
is not a validated fitted-family calibration test. An acceptable diagnostic does not validate the1% tail.
At B = 50, the empirical .99 “higher” quantile is simply the maximum. A nonparametric bootstrap cannot invent
unobserved tail events. Dropping no-candidate draws fits a conditional finite-score distribution and must be
reported rather than silently changing the sampling unit.

The coherent retune's 419-sample .995 `higher` quantile is the third-highest order statistic:
`(419−1) × .995 = 415.91`, selecting zero-based index416. The historical “second-highest” description is
incorrect. Only two samples lie above that threshold; a bootstrap interval can be very wide (one C1
synthetic case:19.95, interval14.06–212.80). L80 based on ten mixtures has .1 resolution, and three C1
real clips never reach80% at+6dB. The −2dB summary is conditional on five uncensored pairs. No 1/h field
false-alarm guarantee follows. This audit checked quantile arithmetic without rerunning a scorer.

The saved-fit “0/3 positives, Clopper–Pearson[0,.71]” counts a degraded copy as an independent positive; it
cannot be a population interval. Likewise four positives/four negatives in the proposal share source groups.
Report per-case development outcomes and source-group counts instead. Group/date/site-block resampling or
independent recording groups are needed for generalization intervals; threshold tuning and evaluation must
use separate groups. A single-pass CRB, local curvature or bootstrap about a misspecified fit is not an
empirical region-coverage test. Failed gates and post-result criterion changes are retained explicitly above.

## Inspected artifacts and remaining evidence gaps

The main records inspected are the linked records above, the 2026-11-03 event-bias/timing/gate/rewindow/extra
records, bench seed/Tier1/blind-label/Livermore/cache records, trace-join, the sanitized private-pilot record,
and the residential/movement/integration/housing/interval records. All nine proposal files were inspected
for their criteria/status; relevant driver/estimator/merge definitions were read, including `collective_run`,
`collective_null`, `collective_truth`, `detector_roc`, `verdict_null`, `coherent_duration`/judge,
`lsfit_compare`, model-error summary scripts, `src/dopplertrack/collective.py`, and benchmark set/runner code.
This does not claim a line-by-line correctness audit of every experiment script or raw-data verification.

Underlying summaries read (content hashes are SHA-256 prefixes, for identification, not a replacement for raw
input provenance). All are existing files; no new result artifacts were produced:

| Run / summary | SHA-256 prefix / scope |
|---|---|
| `bench-a16b700-saved-fit-t2/results.json`; `bench-a16b700-raw-audio-t2-2/results.json`; `bench-5314396-raw-audio-t2/results.json` | `336473d9c76d`; `c8ca42e59060`; `746d74e3a80c` |
| `merge-sweep/sweep_table.json`; `model-error-2/{summary,settings}.json`; `crb-2/crb_summary.json` | timing `c98a83d13cba`; model summary `f478930c6df3`; settings/bound read |
| `model-error-stage2/stage2.csv`; `merge-alaska/{summary,intervals}.json` | `406a8c870e3b`; `9bcbd4e265a1`, `d51fb1153c6a` |
| `heavier-model/heavier_fits.csv`; `turn-model-fit/summary.json`; `turn-model-flag/flag.csv`; `cov-bound2/cov_bound2.json` | `ae8a3c5f208f`; `e2099fa42ed9`; `d9b2928ed7f7`; covariance arrays/SNR mapping read |
| `freqtrack/livermore_summary.txt`, `_run2.txt`; `sde-c-fleet-merge/summary.txt`, `hmm/*/hmm_summary.txt`; `ll-retune1-merge/ll/a2_b1e-03/ll_summary.txt` | tracker tables read; fleet summary `04c891a2c50c` |
| `least-squares-fit/{livermore,livermore_summary,dev}.json`; `window-gate/window_gate.json`; `detector-gate/detector_gate.json` | LS summary `8b06e2c02c84`; window `188418ce7efe`; detector table and partial S2 files read |
| `merge-pairs-a/{evaluation,a1_noise}.json`; `merge-pairs-b-partial/evaluation.json`; `merge-b1b2/b1b2_summary.json` | `48d0810b963a`, `6e4df3f2a824`; `e695660ab8f2`; `58ac46564e43` |
| `merge-basin-profile/basin_profile.json`; `merge-gated-track/gated_track.json`; `overlay-truth/overlay.json`; `find-test/find_test.json` | `c2100762d7f9`; `bcf0b13008f0`; `75d8ead772f9`; `46b982d5a6bd` |
| `warp/warp_oyster_{all,band_all,refine}.json` | `68df48dd1603`; `1f83eea86145`; `0033cfef006a` |
| `coherent-duration-gates[-retune]-judge/judge-gates.json` | `2685d28a14a8`; `f6f554cd1722` |
| `collective-find-merge/collective.json`; `collective-coarse-v{2,3}-merge/collective.json` | `3bdb5d48b6c6`; `b3cc030b5796`; `39909e8d78a0` |
| `collective-coarse-v{2,3}-s*/run.json`, unit completion metadata; `collective-fine-v2-*/units/*/unit.json`, merge.log; `collective-null-s*/run.json`, result structure | exact completion/configuration inventory; no new winner computed from partial cells |
| `locate-gate-{15,w}-merged/results.json`; `eval-cpa-esid{375,710,937}/prepare.json` | `2f3d3456ecf1`, `f71829831e76`; `d82186bf7fa9`, `5e4bb48ecae5`, `48e239725ddc` |
| `verdict-null-merge/{verdicts,reveal}.json` | verdict's stored full SHA-256 verified; reveal `45f4333451a7` |
| `real-tone-coherence/summary.json`; `seattle-matched-injection/summary.json`; residential `adsbx-pooled.csv`; housing `final.mix.csv`; interval `summary.csv`, fixed-scorer `validation-summary.json` | `08d54b4252d0`; `351b77e13362`; `b9c8c30fe4ba`; `7bf90f411676`; `900d99c79fc0`, `b54c218ffbc8` |

Unavailable locally or deliberately not judged: v2's nine missing fine units/complete merge; any v3 all-cell
fine merge; completed v4 smoke/own-day search; collective synthetic-suite results; compatible collective
null_draws sidecars and verdict; complete S2 gate/Tier1 or post-pool equivalence check; coherent blind 19 and
successor Monte Carlo; turn bootstrap merge; private pilot per-flight/site artifacts (not necessary here).
Unpulled/cancelled artifacts may exist elsewhere; this audit did not retrieve them. N=250000 hypothesis
follow-up results were intentionally left unread under the original rule. “Ready” evaluation CPA files were
built remotely and not retained; preparation summaries, not cache binaries, were inspected.

The next research decision is to freeze a corrected collective procedure and its failure/abstention rules
before any new data is opened. Its original accuracy, matched-flight, clock, negative and runtime gates
still stand unless a successor proposal explicitly changes them. A new null belongs to that exact procedure;
independent group evaluation and region coverage remain later, separate gates.

## Current review, 2026-11-04

**Decision changed:** freeze **one corrected complete-search procedure** and obtain an owner decision on
its bounded successor research budget before judging it,
not resume v4 as though v3 had passed or wait for more detector sensitivity. The
[successor acceptance contract](https://github.com/SokolskyNikita/doppler_experiments/blob/64e8337/docs/proposals/2026-11-04-collective-decision.md) fixes accuracy, association,
mode and completeness gates, and separates the complete-development diagnostic from a later conditional-tail
certification decision, with a proposed 120-minute feasibility cap per own/null unit on
a pinned 4xlarge pending owner approval. The original 180 s criterion remains **NOT MET**; v3 Oyster's saved
coarse score alone took 606.891 s, plus 142.745 s for one fine cell. A reported dense-v4 projection is not a
measurement. The successor budget is an explicit prospective change, never a retrospective pass.
Experiments remain paused. A feasible date/source frame is a prerequisite: the historical roughly 120-day
frame cannot supply 100 selection plus 300 independent validation draws. No resampling creates independence.
Once the procedure and research budget
are frozen and execution separately authorized, own-day and null computations can run concurrently;
their interpretation waits for complete parity. There is no scientific dependency on seeing positive
scores before computing null scores.

### Direct observations from existing files

No scorer was rerun. Counts and arithmetic below read existing JSON, completion markers and CSVs only.
Paths in this section are relative to `$DOPPLERTRACK_DATA/runs/` and begin `2026-11-04-`.

| Existing evidence | Direct check and inference boundary |
|---|---|
| `collective-coarse-v3-merge/collective.json`, SHA-256 `39909e8d78a093eed1d7eab41359b4260405c921103c29c7c040d38cda40d17f` | Each of eight cases has only cell0. Retained-cell counts in case order eagle clip / midnight / Oyster / degraded Oyster / north / WSW / sources-removed / Essex are 9 / 20 / 20 / 4 / 20 / 20 / 20 / 20: **8 of 133** retained fine cells, with 125 absent from this summary. Separate cell0 unit markers agree. These are complete coarse maps with partial fine coverage. |
| Same v3 file | Oyster cell0 Z=17.1930528, error318.401 m, both true flights. Eagle cell0 Z=10.0200515, error1857.211 m, neither true flight; truth coarse rank37 is outside the margin. Midnight cell0 error5790.604 m. WSW cell0 Z=15.0420655. Coarse Oyster18.4954212 versus WSW18.2180054 differs by0.2774158 (1.50% of Oyster); fine cell0 Oyster minus WSW is2.1509873. Neither difference is a calibrated significance or a comparison of complete fine maxima. |
| `collective-fine-v2-s*of19`, `-s*of20`, `-merge/merge.log` | 19/19 extra Oyster units and111/120 other extra units have completion markers; the merge log explicitly names nine unfinished units. No complete merge result exists in that folder. No winner was reconstructed from partial results. |
| `collective-null-s*/units/*` | 84 completed units:47 eagle and37 Essex, all under one stored configuration per case:2 km coarse,200 m fine,top5,±10% tone,weather off. Existing winner Z ranges are5.319872–14.732685 and3.922676–12.810562 (medians9.790014 and9.061944). All84 lack `null_draws.npz`, required by the current reader. These are old-design search results, not v3/v4 thresholds; no probability was inferred from them. |
| `verdict-null-merge/verdicts.json` and its stored hash | Stored SHA-256 matches. All five outcomes are ambiguous. Oyster19.9646527<25.8149670; degraded20.4791014<26.5024382; eagle8.5965794<13.9987662. Eagle's true pair is the **second** mode at8.5596153. The two wrong-box controls also stay below threshold. Thus the specified saved-fit usefulness gate fails; this is not evidence that the fitted1% tail is externally calibrated. |
| `cov-bound/cov_bound.json`; `cov-bound2/cov_bound2.json` | First agreement fields `match=None`, `bound_in_63_74=False`; second `rho_match=None`, `bound_match=None`. Second file SHA-256 `2d3b8e19ec52570760214cc0fd8ef53b31051246d58eb05ec9fe443bd1848210`. Its SNR-mapped/raw-covariance median is49.702 m and median sigma0.137375%. Neither failed agreement gate licenses an empirical20–50 m position-error bound. |
| `coherent-duration-gates-retune-judge/judge-gates.json`, SHA-256 `f6f554cd1722bf038d28dd3996a40555b45a7e96d6b1d958aafdf4fd9407b568` | Gate1 reports6.0/4.25 dB on8 passes, fail; gate2 reports−2.0 dB on5 uncensored pairs, fail. Three C1 real passes lack L80 on the tested level grid. The19-pass blind test is not present in this gate result. A gain conditional on supplied true flight/clock is not blind flight selection. |
| `detector-roc-s2-s7of9` through `-s9of9` | B0 has `noise.json` and four pass files; B1/B2 have no completed local scientific unit files. B0 run metadata says interrupted, exit143. Complete S2 judgment remains unavailable. This is partial evidence, not a completed negative result. |

Source inspection at baseline `17758a5` independently confirms that `Window.from_detection` reads refined
event fields; `collective_run.py` accepts extra `result.json` files without a completion marker and merges
only the best cell's winner; `collective.py` suppresses modes by distance after retaining one clock per point.
Those limitations block a unique-clearing-mode claim. A later engineering fix needs its own source hash
and matched own/null results; none is credited here as scientifically measured.

### Denominators and exposure

The current case manifest and Tier1 configuration distinguish source groups and default Tier1 to
development. That bookkeeping does not erase prior exposure: development variants share recordings;
Livermore fitting/coherence uses supplied bands, clocks or trajectory/ridge information; evaluation
preparation reports traffic/weather/reference-aware screening. An unchanged reserved method test may
still be useful if that exposure is declared. Preparation is not blind search success. This review did
not retrieve remote results or prove absence of unpulled evaluation runs.

Existing `us-phone-interval-analysis/summary.csv` (SHA-256 `900d99c79fc0a6c31a3ebfeb56b77a8b921463d62c5e6889f6a57f2990eacf6e`),
`us-phone-interval-scores-fixed/validation-summary.json` (`b54c218ffbc88d52133e33d145dbec679ee0d7408ff921d225fcce42d1277376`),
and `us-indoor-outdoor-coverage/final.mix.csv` (`7bf90f41167655bc44c8c1e595b8b445819280fe661c680839495db5082a8bb3`)
were read directly. Their units remain distinct:

| Quantity | Denominator and missing transition |
|---|---|
| Instantaneous exposure, e.g.0.640% day /0.0246% night in the carried-phone model | Weighted person-time in modeled range; acoustic audibility/tonality is assumed rather than labeled. |
| One-hour14.18% day /1.27% night;9.84% phone-available overall | Nonoverlapping windows with **any positive time** near at least one tracked propeller aircraft. No minimum support or second pass is required. |
| Acoustic detection | Needs independently labeled audible passes/background and frozen search thresholds; no conversion from proximity was measured here. |
| Correct flight identification | Needs competing-flight/clock decisions at the same selection-adjusted false-alarm rule; assisted replays do not measure it. |
| Correct localization and uncertainty coverage | Needs sufficient independent pass geometry, correct ID/clock, complete search, abstention and held-out site/device/day assessment. Neither opportunity percentage supplies this denominator. |

Privacy corrections retain the non-identifying model numbers, failure history, commands/revisions and
artifact names; removed identifying text is in privately hash-preserved originals. The pilot's aggregate
outcomes remain historical reports from that original, not a new inspection of its private site/flight files.
The current review independently rehashed the preserved originals before making these documentation edits.

## Engineering verification, 2026-11-04

`tools/check.sh` passed on the development box: Ruff, generated-index consistency, mypy on four modules,
**357 passed, 4 skipped, 2 expected failures**, and installed-wheel smoke. Pytest took 105.89 s and the full
check 116 s; the 60 s Tier 0 runtime target remains **not met**. The two warnings came from the experimental
rescoring executor's use of fork in a multithreaded process. The new deterministic serial/pool regression
passed; it establishes bounded output equality, not acceptance of S2 or general executor safety.

The tested source was `b08f4cb21727693ee8fd6c84e7703d9a84dded27`, tree
`c1676abf121e8dca07eede9d9c6f9eea621ba80e`. To avoid transferring historical internal contents, the check used
an independent one-commit snapshot with that identical complete tracked tree, rather than the branch's history.
The snapshot had no dirty patch, untracked payload, symlinks or submodules. It used the normal
`tools/aws/runs dev run -- tools/check.sh` path; no recording or data-root input was transferred.
Subsequent PLAN/verification prose received separate index, relative-link, whitespace and source-delta checks;
no executable source, tests or settings changed after the tested tree. Independent review inspected the actual
branch diff and original saved evidence. These checks validate engineering invariants only; experiments stayed paused.
