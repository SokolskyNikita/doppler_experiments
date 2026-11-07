# Dopplertrack research plan

**Status:** research is paused until [research readiness](docs/plans/research-readiness.md) closes (its §5 exit
checks). This plan authorizes no experiment, upload or release; each gate below needs its own approval with a
spending limit (§8). The engineering that research depends on is in the readiness plan, not here.

## 1. Destination and claim boundary

The goal is a reproducible acoustic geolocator that reports alternatives and can abstain when evidence is weak.
A rank-one candidate, small reference error, winning margin, synthetic gain or frequency-estimation bound is not
a validated receiver localization. No calibrated `located` claim or validated uncertainty region exists today.

The owner's release target is a 1 km radius. The development gate below permits 2 km; meeting it is a mechanism
test, not the release target and not a validated region.

Keep four quantities separate: modeled aircraft opportunity, acoustic detection, flight identification and
receiver localization. Flight coverage says what could have been heard under stated assumptions, not what was
audible.

## 2. What the evidence supports

| Area | Evidence | What it supports |
|---|---|---|
| Saved-fit search | Reproductions on the Oyster Bay and eagle-cam development recordings | Regression baselines with selected or fitted events; not untouched evaluation or end-to-end detection. |
| `locate` | Automatic detection, comparable pair selection, optional metadata clock gate, winner refinement | At best `ambiguous`: refining one winner does not eliminate competing modes. |
| Collective search | Coarse-to-fine designs v1–v4 on development recordings | Motivates trajectory-based scoring as a hypothesis. Partial fine searches and nulls of older designs do not validate any current design; v4 was never measured. |
| Sound speed | Temperature and path options, benchmark weather opt-in | Physical correction alone did not consistently improve the saved-fit path. Default stays 15 °C. |
| Private recording pilot | One development group ([record](docs/experiments/2026-11-04-seattle-home-pilot.md)) | The 200 m-grid box series failed its 300 m criterion; the detector found 2 of 11 ear-audible passes. |

The audited evidence, design history and dated corrections are in the
[reset record](docs/experiments/2026-11-04-research-reset.md). The readiness plan ends with a new baseline run of
the rebuilt recipes; its record replaces this table's numbers as the starting point. Earlier numbers stay history.

## 3. Decisions from the evidence

- Keep the pair-based path as a regression baseline with explicit abstention. A metadata clock gate is useful
  when its source and tolerance are independently justified; a clock inferred from the winning match is not
  independent metadata.
- Treat collective trajectory scoring as a **hypothesis**, not an adopted replacement. Versions 1–3 changed tone
  sweeps, coarse selection, window extent and sampling; v4 added denser sampling and pass exclusivity. The
  repaired selector is a new statistic (`collective-Z-greedy-v1`) and inherits no earlier calibration.
- These designs failed their criteria and stay closed: the saved-fit maximum-score verdict (its locate arm was
  never run), the tracker rounds, window round 2, the hypotheses and warp rounds, detector S1, and the first
  coherent-duration round (undecided after its one retune). A successor must state the defect it addresses and
  new criteria before running.
- Do not lower a failed threshold after seeing results. Coherent synthetic gains and frame-noise bounds are
  conditional development findings, not location accuracy. A small Cramér–Rao bound does not guarantee a correct
  global estimate: at low SNR an estimate can jump to a distant peak.
- Weighting log evidence by one effective-sample-size scalar is not a joint likelihood; it needs empirical
  calibration before any probability reading.
- Do not promote weather, a new fitter, a detector threshold or an uncertainty radius on present evidence.

## 4. Gates

Before each gate runs, freeze its design and record the commit, case versions, input hashes, settings, seed,
full selection budget and criteria. Report every case in the categories of the readiness plan's study runner (R6.4);
never replace missing units or failures with successful shards. Score, hash and seal outputs before labels are read. Any failure closes that fixed design:
there is no automatic retune, and a successor needs its own written design and approval.

### G1. Freeze the collective successor design

**Hypothesis.** Scoring trajectory-shaped curves jointly at one receiver location and clock keeps evidence that
straight-pass event fits lose, and separates the true solution from competitors across the whole search.

**Design to freeze**, starting from dense v4: 60–300 Hz, harmonic 1, top 10 usable 240 s detections; 1 km coarse and
200 m fine grids; best 120 s support; ±25% fine tone search; the dense coarse sweep; a two-spread margin capped at
20 cells with the top-three fallback; 15 °C, weather off; the repaired selector. Tone and CPA come from **refined**
detections; state that dependence. Distinct modes are separated by more than 2 km **or** more than 20 s in clock,
suppressed greedily in descending score; keep enough candidates for every clearing mode, not a fixed top five.
Own-day and wrong-day searches use the identical finite search and mode rule, with equal relative-day trace
coverage (including second-day data where applicable). Record every sweep, sample count, weak-window rule,
normalization seed and clock setting.

**Inputs to settle before freezing:**
- The midnight case has `true_pair: null`. Establish its reference associations independently of any search
  result, or preregister a different criterion that can be evaluated. Never fill labels from search results.
- Inventory the available days and sources and their trace coverage; freeze each case's wrong-day list (at most
  50 days per group, 45 for Essex) before any score.
- The owner approves the per-unit cap and the total spend (G2).

A metadata gate, weather change, new detection support or changed selector after the freeze is a new version
needing new own-day and null results.

### G2. Complete development search

Run all eight development cases, every retained fine cell and all mode outputs. The four positives represent two
source groups, not four independent trials.

- **Pass:** each positive's winning mode is within 2 km and includes both true flights; the midnight case picks
  the correct UTC day. Truth-cell survival is reported separately from the winner.
- **Budget:** proposed cap of 120 minutes per unit (own-day or wrong-day) on a pinned 4xlarge, warm cache,
  including merge; a unit that hits the cap is incomplete. The worst-case envelope is 408 units (8 own-day plus
  at most 50 days for each of 8 cases), 816 box-hours; publish the actual unit list and total before asking for
  approval. The original 2–3 minute release runtime gate remains **not met**.
- **On failure:** if recall fails, diagnose once from the per-window contributions and pruning output to choose a
  successor, keeping three causes apart: wrong frequency measurement, wrong source or trajectory association, and
  wrong motion model. If only the budget fails, decide whether to optimize the same statistic or replace the budget.

### G3. Matched null diagnostic

Runs the identical frozen procedure on the frozen wrong-day lists; it can run concurrently with G2.

- **Threshold:** the empirical .99 `higher` quantile of complete-search maxima per case. At these counts it is the
  maximum, a diagnostic and **not a validated 1% threshold**. Gumbel fits are diagnostics only.
- **Accounting:** a complete draw with no candidate scores −∞; an interrupted draw is never counted as a
  non-exceedance.
- **Pass:** exactly one own mode exceeds the threshold on every positive, and none on the four controls. Zero or
  several clearing modes mean abstention.
- **On failure:** keep abstention and redesign aggregation or assignment; more positive fitting is not evidence of
  false-match control.
- **If G2 and G3 pass:** the mechanism earns consideration for research-only integration and for G5. It earns no
  `located` verdict and no 1% claim.

### G4. Target a measured bottleneck

One change addressing a failure that G2 or G3 exposed, with its own design, one primary comparison, matched
budgets and complete controls; every retune is counted. Synthetic gains must hold on real development recordings
before integration. Candidates, each opened only when a measured failure points to it:

- **Assignment:** exact maximum-weight pass-window matching instead of greedy, on the same graph, and later
  one-to-one event-to-flight assignment that models missed detections and clutter. Choose it only if existing
  artifacts separate objective loss on the same graph from loss due to the top-three cap or earlier pruning, and
  show an effect on correct-flight association or location ranking.
- **Joint clock shift:** `locked_score` picks the clock shift from the first event alone; fit it on the joint
  evidence of all events.
- **Detector:** finish the interrupted S2 retune, or use 120 s windows (today's 240 s windows are about twice the
  length of the lines they contain); the wider S0 band passed only the synthetic gate and is unmeasured on real
  Tier 1 data.
- **Coherent duration, second round:** gate 1's target from an operating-point Monte Carlo (10,000 noise windows
  per method and 1,000 tone windows per level, hashed before the gate runs), levels +12 to −20 dB in 0.5 dB steps,
  gate 2 at ±1 dB, wrong-flight set A (real propeller traffic within 12 km and ±30 min) decides, and a coherent
  method wins with an L80 at least 3 dB better.
- **Tracker:** Quinn–Hannan phase linking; the likelihood tracker with Viterbi path decoding instead of a per-frame
  posterior argmax (readiness adds the decoder as an option only).
- **Fitting:** the least-squares straight-pass fit, once a reliable track exists.
- **Silence filter:** conditioned on traffic density for busy sites; another site's default removed every candidate
  in the private pilot.

Pass: version the entire design and repeat the affected G2–G3 checks. Fail: close it. Inconclusive: stop at the
written limit; no third configuration by default.

**Upstream ideas not imported**, to weigh as explicit method imports when a gate needs them: a verdict that fits
an exponential tail to the best wrong pairs of the same search (p = exp(−gap/width)); a nationwide search that
pairs flights first and grids only each pair's region; rescoring the top pairs with further flyovers
(`search-wide --extra`); a ridge-residual score; and flagging broadband bursts such as trains and vehicles
(`detect --max-burst`).

### G5. Independent claims and release

Before any 1% claim, preregister a feasible frame with disjoint threshold-selection data and at least 300
independent validation units from a stated competitor population. The validation event is "complete-search
maximum above the frozen threshold", including draws with several clearing modes; complete no-candidate draws stay
in the denominator. Require an exact one-sided 95% upper bound of at most 1% per claimed case distribution (zero
exceedances in 300 gives 0.994%); shared traffic days, fixed audio or source variants break that independence.
Define site, day and source groups, denominators, target population and sample size before unsealing, and do not
tune after evaluation. The calibration recordings are listed in the [verdict-null](docs/experiments/2026-11-04-verdict-null.md)
and [evaluation-prep](docs/experiments/2026-11-04-evaluation-prep.md) records; the prepared evaluation groups stay
sealed. Coverage measured only over answers that were not abstentions is a different claim from coverage over
all cases; state which one is reported. Pass: report only measured claims with intervals and population limits;
the owner decides release.

For perspective: even zero exceedances in 50 independent draws gives a one-sided 95% upper bound near 5.8%, not 1%.

## 5. Private recording pilot

Paused, like all use of private recordings, until the owner decides how sessions are recorded and moved (§8).
Open items:

- A band test, pre-registered in the pilot record, for the first full-band session.
- A 20 km box search, which needs the regional day cut.
- Known-point detection: only 2 of 11 ear-audible passes were found.
- A re-listen to the band-limited copy at the audible passes' times: if they are still audible, the content is in
  band.

Running `locate` on a private site needs the private-case interface's missing pieces (`locate --site`, and a review
of the path and per-file approval guards); that work belongs to this item when it opens.

## 6. Data roles and provenance

- Oyster Bay and the eagle cam, including crops, filters, encodings, moved boxes, removed-source controls and
  midnight variants, are development families. They do not add independent receiver recordings.
- A corpus or site-day used to choose a setting, diagnose a failure or select a successor is development for that
  decision. A declared `set` value in a case file is not evidence that the data stayed sealed; do not relabel old
  case definitions and erase their tuning history.
- Synthetic signals test mechanism. Livermore and Alaska fit studies measure conditional parameter error; repeated
  passes are not independent localization trials. Opportunity studies keep their assumptions and denominators.
- A hash guards integrity, not blindness: code can contain labels or development truth.

## 7. Open questions

The complete collective design's behavior, its matched search-maximum null, a usable detector threshold,
independent localization error and coverage, and a robust uncertainty region all remain unknown. Historical
top-cell results, unit tests and successful shards cannot close them.

## 8. Owner decisions

- **Now:** none for research; readiness comes first.
- **Before G1–G3:** the midnight-association method; the frozen day inventory; the per-unit cap and total spend.
- **Private pilot:** when and where the first full-band session is recorded, and whether files move to the Mac
  hourly (keeping per-file approval) or upload directly (needing a scoped key and a change to the approval rule).
- Private-file transfers and irreversible infrastructure or data actions remain separate decisions.
