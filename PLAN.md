# Dopplertrack: current decisions and next research gates

Reset baseline, 2026-11-04 (Pacific). Historical records also use 2026-11-05 UTC.
The scientific campaign is **paused**. This plan authorizes no experiment, upload or release.

## 1. Destination and claim boundary

The goal is a reproducible acoustic geolocator that reports alternatives and can abstain when evidence is weak.
The current package is a research tool. A rank-one candidate, small reference error, winning margin, synthetic gain
or frequency-estimation bound is not a validated receiver localization. There is no calibrated `located` claim or
validated uncertainty region in the present pipeline.

The owner's practical release-resolution target remains a 1 km radius. The historical collective development
gate below permits 2 km; meeting that mechanism test would not meet the release target or validate a region.

Keep four quantities separate: modeled aircraft opportunity, acoustic detection, flight identification and receiver
localization. Flight coverage says what could have been heard under stated assumptions, not what was audible.

## 2. Current baseline

| Area | What exists | What the evidence supports |
|---|---|---|
| Installed workflow | `spectrogram`, `detect`, `fit`, `extract-region`, `fetch-day`, `search`, `refine`, `search-single`, `locate` | Working research interfaces; see README and architecture for defaults and limitations. `bench report` is a separate repository workflow. Presence in this local branch is not a published release. |
| Saved-fit search | Reproductions on Oyster Bay and eagle-cam development recordings | Useful regression baselines with selected/fitted events; not untouched evaluation or end-to-end detection success. |
| `locate` | Automatic detection, comparable pair selection, optional metadata clock gate, winner refinement, schema-v2 result | At best `ambiguous`; the single refined winner does not eliminate competing modes. Its defaults differ from benchmark case settings. |
| Collective search | Experimental library and dated drivers; successive coarse-to-fine designs | Development evidence motivates trajectory-based candidates. It is not a `locate` pair rule. Partial fine searches and old-design nulls do not validate the current design. |
| Sound speed | Explicit temperature/path options and benchmark weather opt-in | Default remains 15 °C. Physical correction alone did not consistently improve the saved-fit path; fitter conditioning and reproduction matter. |
| Data and caches | External roots, input hashes, keyed caches and per-run records | Reproducibility machinery exists; hashes do not by themselves establish complete execution, untouched data or correct provenance. |
| Verification | Offline unit checks, scoped typing, index consistency, installed-wheel smoke | Software invariants only. Historical checks are not checks of the reset branch; final verification is recorded separately. |

The implementation/verification map is [architecture](docs/architecture.md). The audited evidence, design history,
artifact availability and dated corrections are in the [reset record](docs/experiments/2026-11-04-research-reset.md).
Original failed criteria stand. No historical queue, proposal or resume command overrides this plan's pause.

## 3. Decisions from the evidence

- Retain the installed pair-based path as a regression baseline with explicit abstention. Metadata clock gating is
  useful when its source and tolerance are independently justified; a clock inferred from the winning match is not
  independent metadata.
- Investigate collective trajectory scoring as a **hypothesis**, not an adopted replacement. Versions 1–3 changed
  tone sweeps, coarse selection, window extent and sampling; v4 introduced denser sampling and pass exclusivity.
  A corrected assignment implementation defines another statistic and cannot inherit earlier calibration.
- The saved-fit maximum-score verdict failed its positive criterion. Do not lower its threshold after seeing the
  results or infer that every future statistic must fail. The unrun locate arm remains unrun.
- Tracker, window, hypotheses and warp rounds that missed their criteria remain closed failures of those designs.
  A successor must state the defect it addresses and new criteria before execution. Coherent synthetic gains and
  frame-noise bounds are conditional development findings, not demonstrated location accuracy.
- Do not promote weather, a new fitter, a detector threshold or an uncertainty radius on the present evidence.
- No broad rearchitecture is justified. The smallest justified code change repairs a demonstrable inconsistency
  between collective assignment scoring and its reported matches. Other integration and coverage defects are
  documented before they become follow-on work; they are not reasons to reorganize folders.

## 4. Ordered next gates

These gates are proposed work, requiring a separate decision to resume research. Freeze each design and record
its commit, dirty patch if any, case versions, input hashes, settings, seed, full selection budget and criteria before
execution. Preserve missing units and failures; do not replace them with successful shards or change the denominator.

The [successor contract](docs/proposals/2026-11-04-collective-decision.md) is the concrete proposal. Its research
budget, independently established midnight associations, and a frozen available-day sampling frame require
resolution before the development study. A larger independent certification frame is a later dependency. The old 180 s
runtime gate remains unmet; repeating a dense search merely to fail that known gate changes no decision.
The successor asks whether its information warrants making the procedure efficient, under a separately approved
resource ceiling shared by own-day and null arms. A timeout is incomplete evidence, never a null nonexceedance.

After the common design and inputs are frozen, own-day development searches and matched null searches can run
concurrently on separate boxes under one explicit authorization and spending cap. Neither depends on the other's
numerical result. Keep any threshold-validation draws sealed until the decision rule is frozen. A failed development
criterion still rejects adoption, even if the null arm looks favorable. Detector/coherence redesign waits for an
identified bottleneck; it is not needed to interpret the present partial collective evidence.

| Gate | Hypothesis and dependencies | Acceptance and stopping rule | Decision for each outcome |
|---|---|---|---|
| 0. Reproducible software baseline | Scored and explained assignments agree; the reset interfaces are accurately documented. Requires final reset review and dev-box checks. | Required checks pass on the final implementation; changed statistic has a distinct identity. Missing historical checks stay marked missing. | Pass: freeze baseline for a proposed study. Fail: fix bounded software defects before science. No experiment is authorized by passing. |
| 1. Freeze one complete search design | A fully specified collective design can retain the relevant development modes without relying on labeled truth during selection. Requires a new proposal, audited case roles, and resolution of coarse/fine/null equivalence. | Declare all locations, clocks, flights, windows, tone ranges, fallback/assignment rules, sampling, mode retention, refinement and computational budget. Positive and null arms must execute the identical selection/statistic pipeline. Tiny deterministic equivalence checks must pass. | Pass: seek approval for Gate 2. Missing parity or undefined budget: stop and repair design. No historical job is resumed. |
| 2. Complete development search | The frozen design places the maximum within 2 km and includes both reference flights on each original positive family, including the correct midnight day. Requires Gate 1 and an approved run. | Run every retained fine region and finish the predefined merge; report truth-cell survival separately from final winner. Preserve the original collective runtime target (2–3 min warm per positive on a 4xlarge) as failed/unmet unless a new study explicitly changes its objective in advance. Transformed copies are sensitivity checks. | All search criteria pass: proceed to matched null assessment, still no `located` claim. Any miss or incomplete stage: fail or incomplete as applicable; stop, diagnose once, and require a new named design before another configuration. |
| 3. Complete matched null diagnostic | The full-search statistic separates development positives from realistic wrong-day/wrong-box/wrong-flight maxima. Requires the identical frozen procedure and all completed stages; own/null computation can run concurrently. | Use the preselected available historical days (at most 50 per applicable group, 45 for Essex), complete-search empirical .99 higher quantile, fixed uniqueness/abstention rule and explicit incomplete-draw accounting in the successor contract. Every positive must clear the diagnostic threshold uniquely; controls must abstain. This is no 1% tail certificate. | Pass: development separation at the disclosed cost, sufficient to decide whether to invest in integration/efficiency. Fail: reject this fixed design. Missing stages/settings: incomplete, no favorable judgment. Independent tail certification and region coverage remain later gates. |
| 4. Target a measured bottleneck | One detector/window/coherent or model change addresses a failure exposed by Gates 2–3. Requires a concrete failure attribution and its own proposal. | One primary comparison, matched search budgets and complete controls; count every retune. Synthetic signal gains must survive real development recordings before integration. Preserve prior failures. | Pass: version the entire design and repeat affected validation/null gates. Fail: close that design. Inconclusive: stop at the written limit; no third configuration by default. |
| 5. Independent claims and release | A frozen pipeline can meet a stated error/abstention/region-coverage target on independent recording groups. Requires separated calibration groups, truly unseen evaluation, full-pipeline verdict and competitor/region machinery. | Before certification, require a feasible independent traffic-day frame, fixed thresholds and conservative tail uncertainty bounds; development diagnostic draws cannot certify 1%. Define independent site/day/source groups, denominators, target population, sample-size justification and confidence bounds before unsealing. No tuning after evaluation. Test complete installation and documented failure modes on supported systems. | Pass: report only measured claims with intervals and population limits; owner decides release. Fail/inconclusive: retain research status and abstention, with a new evaluation set required after any tuning. |

For perspective on Gate 3, even zero exceedances in 50 *independent* draws gives a one-sided 95% binomial upper
bound near 5.8%, not 1%. Reused traffic days and recordings may reduce effective independence. A fitted tail can
extrapolate, but its model assumptions and uncertainty must be tested and reported rather than hidden by a point estimate.

## 5. Data roles and provenance

- Oyster Bay and eagle cam, including crops, filters, encodings, moved boxes, removed-source controls and midnight
  variants, are development families. They do not increase the number of independent receiver recordings.
- Treat a corpus or site/day used to choose a setting, diagnose a failure or select a successor as development for
  that decision. A JSON `set` value is a declared role, not evidence that it stayed sealed. The reset record audits
  actual usage; do not silently relabel old case definitions and thereby erase tuning history.
- Synthetic signals test mechanism and invariants. Livermore/Alaska fit studies measure conditional parameter error;
  repeated passes are not automatically independent receiver-localization trials. Modeled opportunity studies keep
  their time/range/aircraft/coverage assumptions and denominators.
- For every run, record the exact design and stage completeness before reading labels. Record hashes before reveal
  where supported. A hash guards integrity, not blindness: code can contain labels or development truth.
- Pre-rewrite commit IDs remain quoted in historical records. Resolve them using the private revision map or original
  saved bundle; never substitute today's HEAD silently. Record unavailable artifacts explicitly.

## 6. Documentation authority and preservation

| Document | Owns |
|---|---|
| `AGENTS.md` | Durable working, privacy, compute and verification rules |
| `README.md` | Installed user-facing behavior and limitations |
| `PLAN.md` | Current research decisions, open questions and next gates |
| `docs/architecture.md` | Current implementation paths, invariants and verification gaps |
| Dated `docs/experiments/` records | Historical evidence, failures, retunes and corrections; generated index is navigation |
| `docs/proposals/` | Explicitly labeled designs; never execution authorization |
| `tools/aws/README.md` | Operational mechanics; never live fleet status or research decisions |

The former accumulated PLAN and internal fleet ledgers were preserved outside the repository with original paths,
source revision and SHA-256 integrity records. Git history and dated research records retain their original evidence.
Current conclusions supersede old roadmap instructions without pretending they were known before the experiments.
Internal assignments, session notes and machine/account details belong only in the private coordination ledger.

## 7. Open questions

The complete collective design's behavior, its matched search-maximum null, a usable detector threshold,
independent localization error/coverage and a robust uncertainty region remain unknown. Historical top-cell results,
unit tests and successful shards cannot close these questions. Temporal coverage gaps and other implementation
limitations are listed in architecture; resolve them before depending on those interfaces in a study.

## 8. Owner decisions

No new scientific decision is needed to finish the reset. After review, the owner decides whether to integrate the
local branch into `dev`, and separately whether to authorize the first frozen research proposal with its scope and
spending limit. Private-file transfers, publishing and irreversible infrastructure/data actions remain separate decisions.
