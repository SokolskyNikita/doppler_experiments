# Plan: making dopplertrack usable on real recordings

Written 2026-11-03 against v0.2.0 (a16b700). It merges two independent reviews (Claude's and Astra's) with what was measured in this checkout, and was revised the same day after Astra reviewed the plan itself; section 10 lists what that changed. "Checked" means confirmed in the code or by a run here.

## 1. Target for the first usable release

**Recording + UTC date + approximate region (a box of roughly 100–150 km) → candidate locations, each with its evidence and an uncertainty radius, plus an explicit verdict: located, ambiguous, or insufficient evidence.**

The verdict and radius ship labelled experimental until enough independent recordings exist to check them (Phase 4).

Not in scope: recordings with an unknown date or region, moving microphones, real-time use, a GUI. Section 4 explains why.

## 2. Where things stand

- **Oyster Bay result.** It reproduces from raw audio again on `fix/issue-1`, sent upstream as [PR #2](https://github.com/mjshiggins/dopplertrack/pull/2) for [issue #1](https://github.com/mjshiggins/dopplertrack/issues/1). The PR's CI waits on the maintainer approving the workflow run.
  - **The fix.** `fit` uses its pre-f890572 mean-brightness objective by default, so the README commands return the committed event fits.
  - **Search.** With `--harmonics 2 1`, which the README's search and refine commands had left out, the result matches the committed tables exactly: the true pair ranks 1 of 328, the top candidate is 123 m off, the refined peak 43 m off, and the margin is 27.1 vs 25.8. With the default `--harmonics 1 1` the ranking and distances are the same, with a 4.0 % margin.
  - **Still open.** `detect`'s own fits are still filtered out at the true location (gap 4).
- **Eagle cam.** The current code reproduces it with the committed events: 432,196 points, 1,233 segments, 50,682 candidates from 607 pairs, the true pair first at 917 m, with a 2.5 % margin.
  - **Extra flyovers.** The README's three are the committed `detect` candidates #2, #3 and #10. With them the refined peak is 567 m from the nest (README 592 m); with two events only, it is 877 m (README 1.7 km). The two-event score surface is flat, so small input differences move its peak.
  - **Audio copy.** The audio downloaded here is 11.9 h long, and `detect` on it matches the committed candidates only in the top five.
- **`fetch-day`** crashed on days whose archive is split into parts. Fixed on `fix/issue-1` with a regression test; part of PR #2.
- **Costs on this Mac** (M4 Pro, 48 GB RAM, 111 GB free disk):

| Stage | Time | Disk |
|---|---|---|
| `spectrogram`, 1 h of audio | 9 s | 45 MB |
| `detect`, 1 h | 1.5 min | – |
| `fetch-day`, one day, 100 × 150 km box | 4.8 min (3.9 GB streamed) | 29 MB |
| `search`, 200 m grid over that box | 7.6 min, 5.5 of them building the CPA table | 874 MB CPA cache, 10 MB results |
| `refine`, 50 m grid | 4 s | – |

The CPA table depends only on the grid and the flight data, not on the events, and `--cpa-cache` already reuses it. That is what makes fast iteration possible. Once a case has its table, re-running the search with different event fits, pairing rules or scoring takes about 2 minutes instead of 8. All clips from the same day and box share one table.

One catch, checked: the cache is matched on array sizes and a few grid values, not on contents (gap 19). A DEM run and a `--no-dem` run of the same box get the same fingerprint, and so would flight data whose positions or times changed but not its sizes. It has to be fixed before any benchmark number is trusted.

## 3. Merged gap list

Source: **C** = Claude's review, **A** = Astra's, **C+A** = both, **A2** = Astra's review of this plan. Gaps 19–22 came from that review and are filed under their topics.

**Workflow**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 1 | No single audio-to-result command: five or more steps, with time windows and frequency bands chosen by eye | C+A | README Usage; its own Oyster Bay run used hand-picked windows |
| 2 | `detect` writes a JSON list, but `search`/`refine` need two single-event files. The README says entries pass "as they are" | A, checked | `cli.py:104`, `cli.py:120`, `README.md:75` |
| 3 | Choosing which two events to search with, and which extras to add, is manual. Extras are applied to one candidate at a time | C+A | `refine --rank`, `pipeline.py:151` |
| 21 | Scores from different event pairs aren't on one scale: each is brightness summed along curves in that pair's own two audio windows, and every candidate fits the pair that proposed it. Merging candidates from several pairs by raw score favours the pair with the loudest events | A2, checked | `score.py:32`, `score.py:82` |

**Silent wrong answers**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 4 | Each event fit is a single estimate used as hard gates: ±35 % speed, 0.4–2.5× distance, ±6 s on the time between the two events, and a ±5 % sweep of each fitted f0 when scoring. Ideal-curve fits of a real pass are off by more than that, and a bad fit removes the true answer with no warning. Oyster Bay's event 2 fits with f0 5 % (pre-f890572 objective), 10 % (current) and 11 % (`detect`) above what its trajectory needs, and the time between the events 5.0, 9.0 and 10.1 s short. A straight pass at the true speed and distance fits that window worse than any of the three fits, so the bias is the model's, not one objective's. The committed fit got through by 1 s, at the edge of the f0 sweep. At the eagle-cam nest the committed events fail ±6 s too; the top candidate 917 m away is where the geometry makes up the difference | C | issue #1; `pipeline.py:86`; `score.py:65` |
| 5 | `fetch-day` crashes on split archives | C | fixed locally |
| 6 | Edge of region: the download keeps flights that enter the box, but the search uses flights up to 12 km outside it, so flights passing just outside are missing | A, checked | `adsb.py:152` vs `pipeline.py:95` |
| 7 | `detect` always returns its top N, even on silence; there is no "no flyovers found" outcome | A, checked | `tracks.py:194`, no score floor |
| 8 | Malformed traces are skipped silently, with no report of coverage or missing data | A, checked | `fetch.py:88`, `adsb.py:129` |
| 19 | The CPA cache is matched on sizes, not contents: grid count, origin and two extremes, segment and point counts, range and sound speed. Grid elevations, trace contents and code version aren't in the fingerprint, so a DEM run and a `--no-dem` run of the same box share a table | A2, checked | `pipeline.py:100`, `search.py:31` |
| 20 | The silence filter drops a pair at a point if any other flight in the data (props and unknown types) passes within 6 km between the two events. That suits two hand-picked flyovers with a quiet gap, but an automatically chosen pair with other flyovers between them loses the true location. Props pass every few minutes at the eagle cam | A2, checked | `search.py:163`, `README.md:131` |

**Credibility**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 9 | No calibrated confidence, no abstention, no uncertainty radius. The winning margins were 4.9 % and 2.5 %, and the eagle cam's two-event refinement was 1.7 km off. A 50 m grid is not 50 m accuracy | C+A | README results; section 7 |
| 10 | No up-front check that a recording is usable (number and quality of flyovers, continuity, stationary microphone) before spending a 4 GB download and a search. Edits and microphone motion can be flagged, but not reliably detected | A, A2 | – |
| 11 | Physics simplifications: sound speed fixed at 15 °C, no wind, constant propeller speed through a pass | C | `doppler.py:12` |

**Validation**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 12 | Only two real recordings, both used while building the method (the eagle cam changed the scorer). There is no held-out data: clips and augmented copies of one recording share its site, microphone and day. The end-to-end test is synthetic, there are no negative cases, and nothing in CI would have caught the event-2 regression | C+A, A2 | `tests/test_pipeline_synthetic.py`, `README.md:166` |
| 22 | ADS-B passes are possible events, not acoustic labels: a pass within 12 km may be inaudible, masked or filtered out by the microphone, and an audible aircraft may have no ADS-B. At the eagle cam, 20 of `detect`'s top 40 candidates coincide with a known prop pass | A2 | `README.md:134` |

**Inherent data limits**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 13 | Needs the UTC date and a region. Each search covers one day of flight data, about 12 min per extra day here, so a recording that crosses UTC midnight needs two | C+A, A2 | `fetch-day` takes one date |
| 14 | adsb.lol history starts in 2023 and covers aircraft broadcasting ADS-B near volunteer receivers. Light aircraft without ADS-B are invisible | C | `globe_history_2023`…`2026` repos |
| 15 | Needs at least two unedited flyovers, or one with its time known to ±30 s. Phone voice processing, noise suppression and bass cut-off can remove the 60–400 Hz band | C+A | `search-single --tol 30` |

**Packaging and output**

| # | Gap | Source | Evidence |
|---|---|---|---|
| 16 | Output is CSV and terminal tables only, with no versioned result format for a report or benchmark to build on. No command uses the `plots.py` helpers, so there is no map, matched-flight list, inferred start time or curve overlay | C+A, A2 | `plots.py:21`, `plots.py:32`, `plots.py:50` |
| 17 | On PyPI (0.2.0), but ffmpeg must be installed separately, CI runs on Ubuntu only, and there is no fresh-install test | C+A | `audio.py:14`, `.github/workflows/ci.yml` |
| 18 | The 4 GB stream resumes dropped connections but not a killed process | A | low priority: 5 min here |

## 4. What we can realistically do

Constraints: one developer plus Claude sessions; this Mac; free data only; an upstream author who is still changing the code fast (the repo is a day old), so PR acceptance is unknown; and very little ground truth (recordings with known location and date), none of it independent of the development so far.

| Verdict | Items | Why |
|---|---|---|
| **Do now**: small and certain | 2, 5, 6, 7, 8, 17, 19 | Bug fixes and plumbing, each under a day. 19 comes first, because every benchmark comparison depends on it |
| **Do, with measured iteration**: the core work | 1, 3, 4, 10, 12, 16, 20, 21, 22 | Engineering on existing pieces. The risk is in tuning, which the benchmark (section 5) makes cheap |
| **Research, time-boxed** | 9, then 11 | 9 has a promising lead (section 7), and its machinery can be built and tuned on development data. Claiming calibrated numbers needs independent recordings, so that part is evidence-gathering with no fixed date. 11 is small gains; historical METAR temperatures are free |
| **Accept, then detect and report** | 13, 14, 15, moving microphones, edited recordings | Code can't fix these. The tool should say "insufficient evidence" instead of guessing, and flag what it can: an edit between flyovers usually breaks the shared clock. These checks are diagnostics, not guarantees. A ±few-days date mode is a later option at about 12 min per day |
| **Not for us** | Unknown date and region; a GUI | A worldwide index means about 1.4 TB of ADS-B per year and far more compute. A static HTML report covers most of what a GUI would |
| **Later, if needed** | 18; choosing extra flyovers by geometry | Useful, not blocking |

## 5. Approach: build the measuring stick first

Every change is judged by numbers on a fixed set of cases, in loops of seconds to minutes. The 20-minute end-to-end run becomes the final check, not the inner loop. The measuring stick has to be trustworthy before it gets big: caches that can't go stale, labels checked against the audio, and evaluation data kept apart from the data we tune on.

### 5.1 Cases

**Seed set.** Phase 1 starts with four cases, one for each kind of outcome:

| Case | Expected outcome | What it tests |
|---|---|---|
| Oyster Bay, 1 h | located | the reference result |
| An eagle-cam clip of 1–2 h holding its two search events | located | another site, geometry and noise level |
| Oyster Bay audio with the box moved 150 km, over land with similar traffic | not located | the truth is outside the box by construction, so any confident answer is wrong |
| A degraded copy of one of these, e.g. high-passed at 150 Hz and encoded as low-bitrate AAC | located or abstain | abstaining passes; a confident wrong answer fails |

**Growth**, once the seed loop works, cheapest first:

1. **More eagle-cam clips**: the 12 h archive cut into 1–2 h clips. Every clip has the same known location but different flights, so one download gives roughly 6–12 positive cases with different geometry. They share a site, microphone and day, so for evaluation they count as one recording.
2. **Augmented copies**, made with ffmpeg: low-bitrate AAC, Opus and MP3; high-pass at 100 and 150 Hz; noise suppression; added wind noise; shorter trims (30 and 15 min); a 30 s cut between two flyovers. Expected outcome: located or abstain. Severe ones should sometimes end in "insufficient evidence"; they aren't all cases the tool must locate.
3. **Negative controls**, expected not to be located:
   - the right audio with another day's flight data;
   - the right day with the box moved 150 km;
   - stretches with no flyovers, confirmed in the spectrogram.
4. **Stress tests**, inspected rather than scored as plain negatives:
   - time-reversed audio. Its curves mostly rise, which a straight pass at steady power can't produce, but turns, climbs and power changes can, so it isn't a guaranteed negative. A confident answer gets looked at, not counted as a false positive automatically;
   - incomplete flight data (an hour of traces removed), and a recording crossing UTC midnight (synthetic if none of ours does).
5. **New real recordings** as we find them: public livestream archives with published locations, and clips we record ourselves at known spots, including moving and phone-processed ones. These are the only source of evaluation data.

**Groups.** Every clip, augmented copy and negative made from one recording stays in that recording's group, since they share its site, microphone, day and flights. Groups are assigned whole:

- **Development**: Oyster Bay and the eagle cam. Both have shaped the method already, so they never count as evaluation.
- **Calibration**: recordings used to fit Phase 4's thresholds. While there are few, fit them leaving one recording out at a time rather than fixing a split, so each recording gets used.
- **Evaluation**: whole recordings held out, from other sites and days where possible, run only at milestones and never tuned on.

Calibration and evaluation are empty today. That, not code, is what limits Phase 4.

### 5.2 Labels: ADS-B proposes, the audio confirms

For any case with a known location, the flight data shows which propeller aircraft passed within 12 km, when each pass would be heard, and how close and how fast it was. Those are possible events, not ground truth (gap 22). Used as labels as they stand, they would reward detecting aircraft that aren't in the audio.

So:

- **Propose.** Generate a window for each ADS-B pass and draw its modelled curve over the spectrogram crop (`plots.py` already draws this overlay), as one contact sheet per case.
- **Confirm.** Mark each window as heard or not by eye, along with every detection that matches no pass. With the overlay that takes minutes per case, so all windows in the seed set get checked and a sample elsewhere. A Claude session can do the first pass, with you spot-checking it; each label records who checked it.
- **Score by class.** Confirmed acoustic events, unverified passes and synthetic events are reported separately. Recall and fit errors in time, speed and distance are measured on confirmed and synthetic events, and precision on detections checked by eye. Unverified passes are reported but never tuned on.

Detection and fit metrics still come in seconds, without running a search.

### 5.3 Tiers

| Tier | Runs | Time | When |
|---|---|---|---|
| 0 | unit tests, including the cache-miss tests | < 1 min | every change |
| 1 | `detect`/`fit` against labels, and the known-point check, on the seed set | < 3 min | every change to detection, fitting or scoring |
| 2 | blind search on the seed set from cached CPA tables | 2–3 min per case | before keeping a change |
| 3 | everything from scratch (audio, flight data, CPA table, search, refine, report) on all development cases, negatives and stress tests | hours, in the background | nightly and before a PR |
| E | the evaluation group, end to end | hours | at milestones only |

Tier 1's budget holds only on a small subset: `detect` takes 1.5 min per audio hour here, so the 12 h eagle cam alone would take 18 min. Tier 1 runs the seed set with its cases in parallel, and detections are cached by audio and detector version, so changes to fitting or scoring skip detection. A case joins Tier 1 only if Tier 1 stays under 3 min.

### 5.4 Scoreboard

Every run of `locate` or of a benchmark case writes one versioned `result.json` (it carries a schema version), so the CLI, the benchmark and the report can be built independently. A benchmark run collects them into `bench/results/<commit>-<tier>.json` with:

- provenance: code revision, parameters, and the hash of every input and cache used (audio, flight data, CPA table, detections);
- for each case, the expected outcome and whether it was met;
- event metrics by label class, and the known-point result;
- the rank of the true pair, and the error of the top and refined candidates;
- the margin, confidence and verdict;
- confident wrong answers and abstentions, as counts and rates, for each group;
- stage timings.

`bench compare <a> <b>` prints the difference between two runs. There are two baselines, both at upstream a16b700:

- **saved-fit**: the event fits committed in `docs/results/`. It isolates search and physics.
- **raw-audio**: `detect` output with no hand-picked windows. It is what a user gets, event-2 regression included.

A fitting change shows only in the raw-audio numbers; a search or scoring change is judged on both.

### 5.5 How we work

- **Repos.** The fork is `SokolskyNikita/dopplertrack`. Remote `origin` is the fork and `upstream` is mjshiggins; this checkout's pushes always use the SokolskyNikita account, through a repo-local credential helper.
  - **`main`** mirrors upstream; nothing is committed to it.
  - **Topic branches** carry upstreamable fixes. Each starts from upstream `main` and becomes one small PR.
  - **`dev`** is the improved version: `main` plus every fix, whether merged upstream or not, plus all fork-only work and this plan. Upstream is merged into it, never rebased.
  - **Upstream review.** Bigger features (benchmark, `locate`, confidence) get an upstream issue first and stay on `dev` until the author wants them. New capabilities go in new modules. Core edits stay small, keep defaults that preserve upstream behaviour, and go upstream quickly, so merges stay cheap.
- **Data.** Caches live outside git. Each is keyed by content hashes of its inputs plus the parameters and code version that produced it; today's CPA cache isn't (gap 19), and Phase 1 fixes that first. Budget about 1 GB per case-day for CPA tables, so 20 case-days is about 20 GB of the 111 GB free. CI gets only small fixtures.
- **Case manifest.** Each case's entry is immutable provenance: source URL and audio hash, clip offsets, augmentation recipe, flight-data assets (date, pod and archive asset names), box, parameters, labels and who checked them, expected outcome, group, and the code revision it was built with. Changing a case makes a new version of it.
- **Experiment log.** One entry per experiment in `bench/LOG.md`: hypothesis, change, tier 1–2 numbers, kept or reverted. Section 7 is the first entry.
- **Parallel work.** Once the benchmark and the result format exist, independent streams (the Phase 0 fixes, the report, packaging) run in separate Claude sessions, each in its own worktree. The cache fix, the fit gates and multi-pair search all change `pipeline.py` or `search.py`, so they land one at a time. Tier 3 runs in the background.

## 6. Phases

Sizes assume Claude writes most of the code and you review: S is a day or less, M is 2–5 days, L is 1–2 weeks. As a rough guess, 4–6 weeks of part-time work gets to a `locate` command with explicit failure outcomes and an experimental confidence. Calibrated confidence is a separate milestone that waits on collecting independent recordings, and no estimate here covers it. The critical path is 1 → 2 → 3 (step B) → 4. Step A of Phase 3 runs alongside Phase 2, and Phases 0, 5 and 6 alongside everything.

### Phase 0: quick fixes (S; each independent)

- Commit the `fetch-day` fix and send it upstream as a PR linked to issue #1. Done: part of PR #2.
- Fix the event-2 regression from issue #1. Done in PR #2: `fit` uses the pre-f890572 mean-brightness objective by default, so the README commands return the committed fits again. The opt-in `tests/test_oyster_bay.py` checks the README windows, and tracks the `detect`-output path as a strict expected failure. That test is the benchmark's raw-audio regression fixture; it flips to a pass once Phase 2 makes `detect`'s fits usable.
- **Download margin.** Fetch the search box plus 12 km by default, and have `search` warn when the flight data doesn't cover that margin. Test it with a synthetic flight that passes outside the box but within 12 km of an edge point.
- **Hand-off.** Let `search` and `refine` take `detect` output directly, e.g. `--events detected.json --pick 1 2`, and fix the README sentence.
- **`detect` score floor**, with a clear "no flyovers found" result.
- **Data report** from `fetch-day` and `search`: traces kept, traces skipped as malformed, gaps near the candidates.
- **Platform.** A macOS CI job, a fresh-install smoke test, and a clear error when ffmpeg is missing.

### Phase 1: minimal benchmark (M)

The first milestone: trustworthy numbers on a few cases before adding more.

1. **Cache correctness** (S, first). Key the CPA cache on content hashes of the grid (coordinates and elevations) and of the segments (times and positions), plus `max_range`, sound speed and a format and algorithm version, and apply the same rule to every cache the benchmark adds. Tests: a run with changed flight positions or timestamps but the same array sizes, and a DEM run after a `--no-dem` run of the same box, must each miss the cache. It's a plain bug fix, so it also goes upstream. It changes `pipeline.py`, as the `fix/issue-1` work does, so it starts after that lands.
2. **Result format v1**, as in 5.4.
3. **One manifest, one runner, the four seed cases** from 5.1, with provenance, expected outcomes and checked labels.
4. **Both baselines** at a16b700, and `bench compare`.
5. Tiers 0–2.

**Done when** the cache tests pass; the seed cases have both baselines, with every input and cache hash recorded; Tier 1 runs in under 3 min; and Tier 2 on the seed set runs in under 15 min.

**Then grow it** alongside Phases 2–4, as they need cases: the other eagle-cam clips, the augmentations, the negatives and stress tests from 5.1, and Tier 3.

### Phase 2: robust event fits (M–L; research, time-box 1 week)

Hypotheses, each tested in tier 1 against confirmed events:
- Keep several fit hypotheses per event (the best local optima of the grid search) instead of one.
- Derive each event's speed, distance and time ranges from how fast the fit's score falls off around its optimum, instead of the fixed ±35 % / 0.4–2.5× / ±6 s.
- Pair events on their best-constrained feature (when the frequency falls fastest) rather than the fitted CPA time, which inherits distance errors.
- Compare the old and new fit objectives case by case, and use harmonics where they're visible.
- Ideal-curve fits overestimate f0 on real passes, which moves the fitted CPA time with it (gap 4). Correct for that, or carry it as uncertainty, rather than widening the gates. Widening alone doesn't work: a single flyover's f0 and timing trade off in scoring, so a wider gate on one acts as a wider gate on the other. The measurements below, all on development recordings, show the trade-off.

| Gates (time between events, f0 sweep) | Oyster Bay, README windows, current objective | Oyster Bay, `detect` events | Eagle cam, committed events |
|---|---|---|---|
| ±6 s, ±5 % (defaults) | filtered out at the true location (blind search not run) | filtered out at the true location (blind search not run) | 1st of 607 pairs, 2.5 % margin, 50,682 candidates |
| ±10 s, ±12 % | 1st of 469, 17.8 %, 32,554 | – | 1st of 647, 1.6 %, 84,431 |
| ±12 s, ±12 % | 1st of 485, 17.8 %, 39,144 | 2nd of 505, −6.7 %, 38,531 | 2nd of 660, −0.5 %, 101,673 |

With the committed Oyster Bay fits, ±12 s / ±12 % changes nothing at the top: 1st of 358, the same 4.0 % margin, with 81,339 candidates instead of 40,889. On the eagle cam, the ±12 s gate lets in points where a wrong pair 9 km from the nest outscores the true one. The wider f0 sweep changed no score at the points both runs share. Scoring cost rises about 2.3× per candidate at ±12 %. The code for both knobs (`--tol` help, `--f0-tol`) is saved as `data/patches/gate-tolerances.patch`.

**Done when** the true flights pass the search filters on every positive development case using `detect` output with no hand-picked windows, and Oyster Bay reproduces from raw audio.

### Phase 3: `dopplertrack locate` (M–L; step A can start alongside Phase 2)

**Step A: a thin `locate` with explicit failures.** One command over today's pieces:

1. audio → spectrogram → `detect` → usability check;
2. flight data (with margin, cached) → CPA table (cached);
3. search with one automatically chosen pair of adjacent detected flyovers, the case the silence filter was written for (Tier 2 checks it with and without the filter);
4. refine the winner with the other flyovers;
5. verdict and `result.json`.

Each failure is an outcome with a stated reason, not a crash or a guess: no usable flyovers; flight data missing over the recording's time or the box; a recording that runs past UTC midnight; no candidate surviving the filters.

**Step B: search over several pairs.** Choosing pairs automatically breaks assumptions the single-pair search relies on:

- **Silence filter** (gap 20). For pairs with other flyovers between them, replace the hard rule with a penalty, at re-ranking, for close passes that no detected flyover explains. Weight it weakly, since passes can be inaudible (5.2). Keep the hard rule only for adjacent pairs, and only if Tier 2 shows it still helps there.
- **Comparable scores** (gap 21). Pairs only propose candidates. Every distinct candidate is then refined and scored on the same full set of flyovers. Its score on the flyovers it wasn't proposed from is reported separately, since every candidate fits its own pair by construction.
- **One flyover, one vote.** Merge duplicate detections of a flyover, and don't let one pass of one flight explain two events.
- **One clock.** All flyovers behind a candidate share one audio-to-UTC time map, so the same place with two different clocks is two hypotheses. A flyover that only fits with a different clock suggests an edit, as a diagnostic.
- **Confidence on the final output.** Trying many pairs and keeping the best inflates the winner's score, so Phase 4's confidence is computed after the whole pair selection and re-ranking, never per pair.

The pipeline becomes: steps 1–2 as in step A; then search over the top few pairs, reusing one CPA table; then refine and re-rank every distinct candidate on the full set of flyovers with one shared clock; then the verdict and `result.json`.

**Done when**, from audio, date and box alone, both development recordings are located, and each failure case gives its expected outcome with no confident wrong answer: no usable flyovers, incomplete flight data, a recording crossing UTC midnight, and the moved box. Motion and edit checks are diagnostics and not part of this.

### Phase 4: confidence and abstention (L; research, time-box 2 weeks for the machinery)

- Start from the time-gated extra-flyover consistency in section 7. Its ±15 s gate is a development hypothesis until it holds on recordings it wasn't chosen on.
- Candidate features: margin over the strongest distinct competing hypothesis (the best candidate more than one radius away, from any pair); the number of extra flyovers explained and their scores; close passes that no flyover explains; peak width after refinement; event fit quality; clock consistency.
- Fit thresholds on the calibration group's positives against its negatives, never on the evaluation group. Output located, ambiguous or insufficient evidence, with a radius, labelled experimental.
- **Done when** the verdict and radius come out of `locate`, and the benchmark reports confident-wrong and abstention rates for each group.

**Claims need an evaluation group.** A calibrated claim is made only on evaluation recordings, against criteria set in advance:

- Zero confident wrong answers out of n bounds the true rate below about 3/n at 95 % confidence: under 10 % after 30 confident answers, under 5 % after 60. Abstentions don't count toward n, so the more the tool abstains, the more recordings this takes.
- A radius stated at 90 % that holds in 27 of 30 cases is consistent with a true coverage anywhere from 74 % to 98 %. 54 of 60 narrows that to 80–96 %.

Until the evaluation group is that large, the verdict and radius stay labelled experimental. Gathering it is evidence work, not engineering, and has no fixed date.

### Phase 5: report (S–M; independent once the result format exists)

One HTML page per `result.json`:
- a map of candidate areas and the score map;
- the matched flights, with registration and type;
- the inferred recording start time;
- a measured-vs-modelled overlay for each event (`plots.py` already draws these);
- the data report and diagnostics: flight-data coverage, clock consistency, possible edits;
- GeoJSON and KML export.

### Phase 6: release (S)

A README covering install (including ffmpeg), requirements and limits, and how to read the verdict, including what "experimental" means. Release in the fork, and send upstream PRs as the author accepts them.

### Later

- A ±N-day date search, at about 12 min per extra day here.
- Temperature and wind from historical METAR.
- Choosing extra flyovers by how well their geometry pins down the location.
- Downloads that resume across restarts.

## 7. First experiment: does a candidate explain the other flyovers?

Setup, on Oyster Bay:
- a blind search with the committed event fits, taking the top 10 flight pairs (rank 1 is the true pair);
- 8 extra events: those from `detect --top 10` other than the two search events;
- at each pair's best point, find a flight that explains each extra event and score its modelled curve, using the same time shift as event 1 and a propeller-tone scale of 0.95–1.05;
- an extra counts as explained at a score of 3 or more.

| Rule for the explaining flight | True pair | Wrong pairs (9) |
|---|---|---|
| any flight within 12 km and ±5 min (what `pick_flight` does) | sum 36.9 | up to 41.1; three of them at 35 or more |
| heard closest approach within ±6 s | 1 explained (4.7) | none explained (max sum 2.5) |
| within ±15 s | **2 explained (6.7, 4.7)** | **none explained (max sum 2.8)** |
| within ±30 s | 2 explained | two pairs explain 1 each (sums 6.6 and 6.3) |
| ±15 s plus `detect`'s speed and distance gates | none | none |

Separately, the robust z-score of each pair's best score against all 328 pairs is 4.2 for the true pair and 3.9 for the runner-up. Statistics from a single search don't separate them.

Takeaways:
- The time gate is what makes extra flyovers informative, and ±15 s worked best of the windows tried. It was picked on this recording, so it stays a development hypothesis until it holds on recordings it wasn't chosen on.
- `detect`'s speed and distance are too unreliable to gate on, the same problem Phase 2 targets.
- Only 2 of 8 extras matched, so better detection feeds directly into confidence. The extras weren't checked by eye (5.2), so some may not be aircraft at all.
- All ten pairs came from one search and were scored on the same extras. Comparing candidates from different pairs needs that same footing (Phase 3, step B).
- This is one recording and ten candidates: a lead to test on the benchmark, not a result.

## 8. Decisions for you

1. Work in a fork and upstream small fixes, or try to upstream everything? Recommended: fork first.
2. Can data derived from third-party recordings (spectrogram crops of the YouTube clips) go into the repo for CI, or should fixtures download on demand? Recommended: on demand, plus small synthetic fixtures in the repo. This also decides whether the raw-audio regression fixture can run in CI.
3. Will you record ground-truth clips yourself? It's the only way to get controlled moving, edited and phone-processed cases, and the surest way to build the evaluation group that calibrated confidence needs (Phase 4): tens of recordings, preferably at more than one site. It needs a spot with regular light-aircraft traffic and a phone whose clock and location give the truth.

## 9. Risks

- **Upstream moves fast.** Rebase often and keep changes modular.
- **Ground truth stays scarce.** Slicing and augmentation stretch two recordings a long way for development, but slices of one recording share its site, microphone and day, so they aren't independent evidence. Both recordings are in busy US airspace; add at least one quiet-airspace case before trusting the calibration.
- **Tuning to the benchmark.** Development cases get tuned on, so their numbers will flatter the method. Only the evaluation group counts for claims.
- **Labels from ADS-B.** Unchecked passes would reward detecting aircraft that aren't in the audio, so only confirmed events are tuned on.
- **Stale caches.** Until Phase 1's cache fix lands, a cached CPA table can silently belong to other inputs.
- **Test recordings disappear from YouTube.** Keep the downloaded audio in the local cache.
- **Confidence may not generalise.** Report the abstention rate alongside every accuracy number.

## 10. What Astra's review of this plan changed

Astra reviewed the first version of this plan. All six main points were adopted; where the plan goes further or differs, it says so here.

1. **Labels are provisional** (5.2, gap 22). ADS-B passes now propose windows that are confirmed against the spectrogram, and metrics are kept for each label class. The plan checks every window in the seed set rather than a sample, since drawing the modelled curve over each crop makes that quick.
2. **Development, calibration and evaluation groups** (5.1), with every derivative of a recording kept in its group. Phase 4 claims now need the evaluation group and criteria set in advance, with the numbers worked out, and confidence stays experimental until then. "Margin over the best wrong pair", which needs the answer, is now "margin over the strongest distinct competing hypothesis". Added: leave-one-recording-out calibration while recordings are few.
3. **Cache correctness first** (Phase 1, gap 19). Checked in the code, which also turned up a collision the review didn't name: DEM and `--no-dem` runs of one box share a fingerprint.
4. **Multi-pair search assumptions** (Phase 3 step B, gaps 20–21): a soft penalty in place of the silence filter, candidates compared on one set of flyovers, one flyover one vote, one clock, and confidence on the final output. The hard silence rule stays for adjacent pairs, where its assumption holds, if Tier 2 shows it still helps.
5. **A smaller first benchmark**: four seed cases, saved-fit and raw-audio baselines, and a Tier 1 budget defined on that subset, because detection alone on every case would take far longer. The moved-box negative goes over land with similar traffic, since a box over the sea would be too easy.
6. **Failure behaviour before `locate` counts as done.** Phase 3 now starts with a thin `locate` whose failures are explicit outcomes, its done-when includes the failure cases, augmented copies expect "located or abstain", and motion and edit checks are described as diagnostics.

Smaller changes: time-reversed audio is a stress test rather than a guaranteed negative; ±15 s is a development hypothesis; a versioned `result.json` comes in Phase 1; case manifests hold immutable provenance; and the 4–6 week estimate no longer covers calibrated confidence.
