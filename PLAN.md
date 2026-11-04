# Plan: from today's dopplertrack to a dependable acoustic geolocator

This is the route from what dopplertrack does today to the tool we want, written from what we currently know. It will change as we learn: each experiment gets a record in [docs/experiments/](docs/experiments/README.md), and its conclusion is folded in here.
- [AGENTS.md](AGENTS.md) has the working rules.
- [docs/reference/README.md](docs/reference/README.md) has the papers.
- Code references are to `dev` at 5a617ff.

## 1. Destination

### The tool we're aiming for

Given a recording made at one fixed spot, on any device and of any length, plus roughly when and where it was made, the tool says where it was recorded, how sure it is, and why. When the recording doesn't hold enough to tell, it says so plainly.

What "good" means, in terms we can measure:
- **Trustworthy when it answers.** Confident wrong answers are rare, and that rate is measured on recordings never used to build the tool.
- **Useful.** It locates most recordings that hold two or more matchable propeller flyovers (or one, with a known time), to within the resolution in decision 1.
- **Honest about uncertainty.** Each answer has a region whose stated coverage holds on independent recordings, and separated alternatives are shown, not hidden.
- **Robust** to what real recordings go through:
  - lossy codecs and phone processing;
  - wind, and other tonal noise such as jets and machinery;
  - edits;
  - aircraft that turn, climb or change speed.
- **Explains itself.** A report shows the matched flights, the measured and modelled curves, and the alternatives with why they lost.
- **Practical.** It installs with pip and runs on a laptop in minutes once a day's flight data is cached. It survives interruptions and fails with clear messages.

Further out, if the first releases work: uncertain dates (a search over ±N days), larger regions, jets as a signal source (most traffic is jets), and single-flyover recordings with only a rough time.

**Out of reach or not planned:**
- aircraft without ADS-B, which can be heard but not matched;
- moving microphones;
- no date or region at all: a worldwide index is about 1.4 TB of ADS-B per year, with far more compute;
- real-time use;
- a GUI, since a static report covers most of it.

### The first usable release

The first usable release, milestone M2 in section 4, is a `locate` command.

**Inputs:**
- **The recording.** Any file ffmpeg can decode. Channels are averaged to mono, the audio is resampled to 4 kHz, and only 40–450 Hz is analysed (`audio.py:14`, `cli.py:24`). Searches have run on 1 h and 12 h recordings, and `detect` on clips of 5–92 min. At about 1.5 min of `detect` per audio hour, long recordings are slow but allowed.
- **The UTC date the recording falls on.** Flight data is fetched for that day only, and the inferred clock is checked against the day's edges.
- **A region**: a box of roughly 100–150 km. Flight data is fetched with a margin equal to the search range.
- **Optionally, the start time**, in UTC with a tolerance such as ±30 s. It makes a single-flyover search possible and narrows a two-flyover one.

**Outputs:**
- a verdict;
- the candidate locations behind it, each with its evidence;
- an uncertainty region where the evidence supports one, otherwise "unavailable".

All of it goes into a versioned `result.json` (5.5) and an HTML report.

**Verdicts:**
- **located**: one location-and-clock mode survives the competitor test (Phase 4), and its region fits within the practical resolution (decision 1).
- **ambiguous**: two or more separated modes remain plausible, or a single mode's region is wider than the resolution. Each mode is reported.
- **insufficient evidence**: any of
  - fewer than two usable flyovers (or one without a start time);
  - flight data missing over the recording or the box;
  - no surviving hypothesis;
  - no meaningful uncertainty region.

Execution errors (unreadable audio, a missing ffmpeg, a network failure) are reported as errors, never as verdicts. The verdict and region are labelled experimental until M3.

## 2. Starting point

**What works:**
- **The method reproduces both published results from saved event fits.**
  - Oyster Bay: the true flight pair ranks 1st of 328, the top candidate is 123 m off and the refined peak 43 m off. With `--harmonics 2 1` this matches the committed tables exactly (4.9 % margin); the default gives the same ranking and distances with a 4.0 % margin.
  - Eagle cam: the true pair ranks 1st of 607 at 917 m, with a 2.5 % margin. With three extra flyovers (the committed `detect` candidates #2, #3 and #10) the refined peak is 567 m from the nest. With two events only, the score surface is flat and the peak 877 m off.
- **Upstream fixes.** [PR #2](https://github.com/mjshiggins/dopplertrack/pull/2) is waiting for the maintainer. It fixes `fetch-day` on split archives, restores `fit`'s brightness objective as the default, and adds tests.
- **The CPA cache** is done in `dev`; sending it upstream is deferred.
  - **How it works.** It is keyed on its inputs' contents, it writes CPA tables and terrain tiles atomically, it treats an unreadable file as a miss, and it holds a lock per table.
  - **Check.** Re-running the Oyster Bay search reproduced the earlier output byte for byte, and loading a cached table takes 3 s instead of a 5.6 min rebuild.
  - **Windows.** The lock uses `fcntl`, so on Windows it is skipped. Atomic writes still keep the cache correct; two processes may just build the same table.
- **Infrastructure.** Data and caches live outside the repo, run folders record their provenance, and raw files are read-only. `bench/manifest.json` lists every raw file's size, hash, source and licence (an integrity inventory, not full provenance).

**What doesn't work:**
- From raw audio alone, `detect`'s fits don't pass the search's gates at the true location (gaps E1, E2). The tool can't yet locate a recording without hand-picked windows.
- Every failure is silent: there is no verdict, no abstention and no uncertainty.

**How the pipeline works today:**
1. **`spectrogram`**: an STFT with a 2.048 s Hann window and a 0.25 s hop (0.49 Hz bins) over 40–450 Hz, whitened by a running median.
2. **`detect` and `fit`**: a grid search plus Nelder–Mead over (f0, speed, distance, CPA time), maximising mean brightness or ridge contrast under an ideal straight-pass curve. No frequency track is extracted; `tracks.ridge()` exists but nothing calls it.
3. **`fetch-day`**: streams one UTC day of adsb.lol traces, keeping propeller and unknown types that enter the box.
4. **`search`**: builds a CPA table (grid point × flight) within 12 km, then:
   - gates flight pairs on the heard-CPA time between the two events (±6 s), speed (±35 %) and distance (0.4–2.5×);
   - drops pairs where another flight passes within 6 km between the events (the silence filter);
   - scores each surviving triple by brightness along the curves modelled from the actual trajectories, with event 1 setting the clock (±8 s shift) and each event's f0 swept by ±5 %.
5. **`refine`**: a 50 m grid around one candidate, with extra flyovers scored at event 1's clock.

**Data on hand** (the data root's `MANIFEST.md`):
- the two development recordings, Oyster Bay (1 h) and the eagle cam (12 h);
- four Eclipse Soundscapes sites recorded on 2024-04-07, CC BY 4.0;
- seven xeno-canto recordings: one usable single-flyover case, and three Essex recordings that contain only jets;
- flight data for each recording's day: 2024-04-07 for the Eclipse sites, but not yet 04-08, which two of them run into. The development cases also have the day before, plus METAR reports and upper-air soundings;
- 16 papers and books.

None of the non-development audio has been searched yet. A recording session in Seattle is being planned.

**Costs on this Mac** (M4 Pro, 48 GB RAM, 183 GB free disk at the time of writing):

| Stage | Time | Disk |
|---|---|---|
| `spectrogram`, 1 h of audio | 9 s | 45 MB |
| `detect`, 1 h | 1.5 min | – |
| `fetch-day`, one day, 100 × 150 km box | 4.8 min (3.9 GB streamed) | 29 MB |
| `search`, 200 m grid over that box | 7.6 min, 5.5 of them building the CPA table | 874 MB CPA cache, 10 MB results |
| `refine`, 50 m grid | 4 s | – |

The CPA table depends only on the grid and the flight data, not on the events. So once a case has its table, re-running the search with different fits, pairing rules or scoring takes about 2 minutes instead of 8, and all clips from one day and box share a table. That is what makes fast iteration possible. Plan on about 1 GB of CPA tables per case-day; the data root holds about 47 GB.

## 3. What stands in the way

Open problems, grouped by theme. The IDs are used throughout.

**Event evidence: detection and fits**

| ID | Problem | Evidence |
|---|---|---|
| E1 | Fits of real passes are biased, and the search turns each fit into hard gates: ±35 % speed, 0.4–2.5× distance, ±6 s between the events, and a ±5 % f0 sweep. A bad fit removes the true answer with no warning. Oyster Bay's event 2 fits with f0 5, 10 and 11 % high under three fitting setups, and the time between the events 5.0, 9.0 and 10.1 s short. The discrepancy persists under both objectives tested | [event2-bias](docs/experiments/2026-11-03-event2-bias.md); `pipeline.py:122`, `score.py:65` |
| E2 | Pairing compares fitted heard-CPA times (emission CPA + d/c) with the CPA table's `t_heard`. A distance error moves the gate by Δd/c, and an f0 error by δf0/g_max, where g_max is the curve's peak slope. For Oyster Bay's event 2 that is about 1 s per 1 % of f0, consistent with E1's timing errors | `pipeline.py:138`, `search.py:198`; [timing-conventions](docs/experiments/2026-11-03-timing-conventions.md) |
| E3 | No frequency track, so there is nothing to fit by least squares, weight by reliability, or check for gaps, crossings and harmonic jumps | `tracks.py:36` is never called |
| E4 | `detect` always returns its top N, even on silence | `tracks.py:212` |
| E5 | `detect` scores jet tones as highly as propeller flyovers. The Essex recordings have no prop pass within 12 km, 9–14 jet passes each, and strong detections | data root `MANIFEST.md` |
| E6 | The model assumes a straight pass at constant speed and constant propeller speed, with the speed of sound fixed at 15 °C and no wind. One eagle-cam flight's heard curve falls fastest 16.6 s after its geometric CPA | `doppler.py:12`; [timing-conventions](docs/experiments/2026-11-03-timing-conventions.md) |

**Search and decision**

| ID | Problem | Evidence |
|---|---|---|
| S1 | Choosing the two search events and the extras is manual, and extras are applied to one candidate at a time | `refine --rank`, `pipeline.py:179` |
| S2 | Scores from different event pairs aren't on one scale. Each sums brightness in its own two windows, and every candidate fits the pair that proposed it, so merging candidates by raw score favours the loudest events | `score.py:32`, `score.py:82` |
| S3 | The clock comes from event 1 alone: the time shift that maximises event 1's score is applied to event 2 and to every extra flyover | `score.py:79`, `pipeline.py:219` |
| S4 | The silence filter drops a pair at a point if any other flight passes within 6 km between the events. An automatically chosen pair with flyovers between them loses the true location, and adjacent detections don't make it safe either, since a pass in between may have been inaudible or missed. Props pass every few minutes at the eagle cam | `search.py:199`, `README.md:139` |
| S5 | No verdict, abstention or uncertainty. The winning margins were 4.9 % and 2.5 %, and the eagle cam's two-event refinement was 877 m off here (1.7 km in the README). A 50 m grid is not 50 m accuracy | README results |
| S6 | No up-front check that a recording is usable before a 4 GB download and a search: enough flyovers, continuity, a stationary microphone | – |

**Data handling**

| ID | Problem | Evidence |
|---|---|---|
| D1 | The download keeps flights that enter the box, but the search uses flights up to 12 km outside it | `adsb.py:152` vs `pipeline.py:132` |
| D2 | Malformed traces are skipped silently, with no report of coverage or missing data | `fetch.py:88`, `adsb.py:129` |
| D3 | The elevation tiles' no-data value (−32768 m) isn't masked: `Grid.make` clamps it to 0 m, and `refine` uses it raw. One such pixel is in the ESID 937 box | `terrain.py:61`, `search.py:37`, `pipeline.py:200` |

**Workflow and output**

| ID | Problem | Evidence |
|---|---|---|
| W1 | No single audio-to-result command: five or more steps, with windows and bands chosen by eye | README Usage |
| W2 | `detect` writes a list, but `search` and `refine` need two single-event files, and the README says the entries pass "as they are" | `cli.py:107`, `cli.py:123`, `README.md:79` |
| W3 | Output is CSV and terminal tables, with no versioned result record. No command uses `plots.py`, so there is no map, flight list, start time or curve overlay | `plots.py:21` |
| W4 | ffmpeg must be installed separately. CI runs only on Ubuntu, for pull requests and pushes to `main` (not `dev`), and nothing tests a fresh install | `audio.py:14`, `.github/workflows/ci.yml` |
| W5 | The 4 GB stream survives dropped connections but not a killed process. Low priority at 5 min here | – |

**Validation**

| ID | Problem | Evidence |
|---|---|---|
| V1 | Only two recordings have been searched, and both were used to build the method. There is no held-out data and no negative case, and nothing in CI would have caught the event-2 regression | `tests/test_pipeline_synthetic.py`, `README.md:174` |
| V2 | ADS-B passes are possible events, not acoustic labels. A pass within 12 km may be inaudible, and an audible aircraft may have no ADS-B. At the eagle cam, 20 of `detect`'s top 40 candidates coincide with a known prop pass | `README.md:142` |

**Limits we accept, detect and report rather than fix:**
- **L1.** It needs the UTC date and a region. Each search covers one day of flight data, at about 12 min per extra day here.
- **L2.** adsb.lol history starts in 2023 and covers only aircraft broadcasting ADS-B near volunteer receivers.
- **L3.** It needs two unedited flyovers, or one with a known time. Phone voice processing, noise suppression and bass cut-off can remove the 60–400 Hz band.
- **L4.** Moving microphones and edited recordings. An edit between flyovers usually breaks the shared clock, so it can be flagged, but not reliably detected.

## 4. The route

**Principles:**
- **Measure first.** Every change is judged by numbers on a fixed benchmark, in loops of seconds to minutes (section 5). The full end-to-end run is the final check, not the inner loop.
- **Keep evaluation clean.** Development recordings may be tuned on. Evaluation recordings never are, and claims come only from them.
- **Fail explicitly.** A recording the tool can't locate gets a verdict and a reason, never a guess.
- **Simple, checkable models first.** Complexity is added only when a measured bias calls for it.
- **Stay mergeable with upstream.** New capabilities go in new modules, and upstream defaults are kept. Small core fixes go upstream; `AGENTS.md` has the branch recipe.

| Milestone | Delivers | Phases | Depends on | Rough size |
|---|---|---|---|---|
| **M1: a measuring stick we can trust** | the small known bugs fixed, the result record, and the seed benchmark with both baselines | 0, 1 | – | 1–2 weeks |
| **M2: first usable release** | `locate`, from audio, date and box to a verdict and a report, with explicit failures and the alternatives it considered, installable from a release in the fork | 2, 3, 5, 6 and the machinery of Phase 4 | M1 | 3–4 more weeks |
| **M3: validated claims** | the confident-wrong rate and region coverage measured on independent recordings, against criteria fixed in advance | 4 (claims) | M2, plus enough independent recordings (5.6) | no date: it waits on evidence |
| **M4: toward the destination** | the extensions in section 1, each when a measurement calls for it | Later | M2 | open |

Sizes assume Claude writes most of the code and you review: S is a day or less, M is 2–5 days, L is 1–2 weeks of part-time work. The critical path is Phase 1 → Phase 2 → Phase 3 (step B) → Phase 4. These run in parallel:
- Phase 0's fixes, alongside Phase 1;
- Phase 3's step A, alongside Phase 2;
- Phase 5, once the result record exists;
- Phase 6's packaging and install test, at any time, though its release test needs `locate`;
- collecting independent recordings (5.6), from now on.

Each phase below gives its goal, the approach we expect to take given what we know, and when it's done. The phases with real uncertainty (1–4) also say what to do if they don't work out.

### M1: a measuring stick we can trust

#### Phase 0: quick fixes (S each, independent)

- **Download margin** (D1). Derive the margin from the search range (`max_range_m`), and record it with the flight data as its coverage envelope. `search` warns when the data doesn't cover the box plus that margin. Test it with a synthetic flight that passes outside the box but within range of an edge point.
- **Hand-off** (W2). `search` and `refine` take `detect` output directly, e.g. `--events detected.json --pick 1 2`, and the README sentence is fixed.
- **An empty result** (E4). `detect` can return "no flyovers found" instead of a padded top-N list. That is plumbing; choosing the threshold needs positive and negative recordings, so it happens in Phase 2.
- **Data report** (D2). `fetch-day` and `search` report traces kept, traces skipped as malformed, and gaps near the candidates. The report also says what it can't know: a complete download doesn't mean every aircraft overhead broadcast ADS-B (L2).
- **Elevation no-data** (D3). Mask −32768 in `Terrain`, with a test on the ESID 937 pixel.
- **Platform** (W4). A macOS CI job, a fresh-install smoke test, and a clear error when ffmpeg is missing. If `dev` is ever pushed, CI has to run on it too.

**Done when** each fix has its test and is in `dev`.

#### Phase 1: minimal benchmark (M)

1. **Result record v1** (5.5).
2. **A case manifest, a runner, and the four seed cases** from 5.1. Each case's entry carries:
   - exact source identifiers and acquisition details;
   - clip offsets and transformation recipes;
   - the flight-data assets (date, pod and archive asset names), the box, and the search parameters;
   - labels, with who checked them;
   - the expected outcome and the case's group and set;
   - the code revision it was built with;
   - links to its raw files' entries in `bench/manifest.json`.

   Changing a case makes a new version of it. A fetch script rebuilds `raw/` on another machine.
3. **Both baselines** at upstream a16b700, and `bench compare`.
4. **Tiers 0–2** (5.4).
5. **Sets for the clean recordings** (5.2), written into the case manifest before any of them is searched (decision 2).
6. **Any new cache** (detections, spectrograms) follows the CPA cache's rules: keyed on its inputs' contents, written atomically, and locked. Use `filelock` and a library cache such as `joblib.Memory` or `diskcache` rather than repeating the hand-written pattern.

**Done when:**
- the seed cases have both baselines, with every input and cache hash recorded;
- Tier 1 runs in under 3 min and Tier 2 on the seed set in under 15 min;
- every clean recording has its set.

The benchmark then grows alongside Phases 2–4, as they need cases. **If the budget can't be met:** Tier 1 runs fewer cases.

### M2: first usable release

#### Phase 2: event evidence that survives real passes (M–L; research, time-box 2 weeks)

**Goal:** from `detect` output, with no hand-picked windows, event evidence that lets the true flights through on every positive development case without letting wrong pairs win. It depends on Phase 1's Tiers 1–2 and labels.

The experiments run in this order. Each is judged in Tiers 1–2 against labelled events, kept, reverted or deferred by the stop rule below, and recorded in `docs/experiments/`.

1. **Timing convention** (S; E2). This comes first because it is cheap and the measurements so far point at it.
   - **Gate.** Pair on emission-CPA times against the CPA table's `t_emit`, with a looser gate.
   - **Scoring.** Compare like with like: the steepest-fall time of the fitted curve against that of the curve modelled from the actual trajectory.
   - **Measurement.** On every confirmed pass, measure how far the modelled curve's steepest fall is from the geometric CPA. That shows how often a flight isn't straight enough for `t_emit` to stand in.
2. **Model error** (S; E1, E6). Fit the straight-pass model to three kinds of curve: noiseless curves made from the real trajectories of confirmed passes, the same curves with noise, and ideal straight passes. That separates model bias, measurement noise and optimiser failure before any fit changes.
   - **Perturbations**, one at a time: f0 drifting through a pass, sound speed (METAR temperature), wind (soundings), trajectory sampling, altitude and terrain.
   - **A check on real fits.** Fit each pass's approach and recede halves separately. A straight, constant-speed pass gives the same f0 and speed from both, so a difference measures model error (a two-estimator comparison of the kind White 1982 recommends).
   - **Heavier models** (turns, acceleration, weather) come only after a measured bias they would remove.
3. **Frequency track** (M; E3). One track per event:
   - times, and frequencies refined below the bin width (quadratic interpolation, or Quinn's estimators);
   - an amplitude or quality per point, and valid and missing samples;
   - explicit start, end and gaps;
   - links between the harmonics of one pass.

   Start from `tracks.ridge()`, restricted to spectral peaks. Ridge extraction joins unrelated components when tones come and go, and the literature offers no stopping rule (6.3). So starts, stops and crossings get their own rules and tests, and false continuations and false bridges are measured alongside frequency error. An adaptive tracker is tried only if track errors turn out to limit the fits.
4. **Least-squares fit** (M; E1, E3). Fit the track with f(t) = α + β·z(t; τ_c, s) (6.1). At each (τ_c, s), α and β are solved in closed form, so the search is over those two parameters only (variable projection).
   - **Losses.** Start with ordinary least squares, then weight points by amplitude, then try a robust loss if outliers call for one.
   - **Safeguards:**
     - a stable linear solve, with a check that z varies enough over the track, since flat and partial tracks make α and β inseparable;
     - physical bounds on speed and distance;
     - a grid of starts over (τ_c, s), since variable projection doesn't remove local optima;
     - convergence and conditioning diagnostics in the result record;
     - a synthetic test that the reduced fit's optimum matches the full four-parameter fit.
   - **Comparison.** Compare it with today's brightness and contrast fits on the same cases.
5. **Window length** (S). The 2.048 s window smears the steepest part of a typical pass. A window matched to a sweep rate g is about 1/√g, which is 0.9 s for Oyster Bay's event 2 (6.1). Compare:
   - 2.048 s against about 1 s and 0.5 s;
   - a two-window version, short near CPA and long in the tails, where a longer window measures the steady tone far better.

   Zero padding only interpolates the spectrum; resolution comes from the window length.
6. **Harmonics and extent** (S–M).
   - Compare harmonic assignments, allow for a missing fundamental, and merge the harmonics of one pass into one event. Their evidence is correlated, so they aren't separate votes.
   - Mask the unreliable stretches of a track instead of cropping to a fixed width ([rewindow](docs/experiments/2026-11-03-rewindow.md)).
   - Set `detect`'s threshold here, as a curve of detections against false alarms per audio hour on the development background recordings, the Essex ones (E4, E5).
7. **Joint hypotheses instead of gates** (M; E1). Replace the independent speed, distance, time and f0 gates with each event's own hypotheses: its best few local optima, each with the joint region its data supports.
   - **Why joint.** Time and f0 trade off along the curve's slope, and distance follows speed (6.1). Marginal ranges combined freely admit combinations the event never supported.
   - **Profiles.** Derive the regions from profiles, re-optimising the other parameters, and call them sensitivity ranges until the objective is a calibrated likelihood.
   - **Weak identification.** A flat or one-sided profile marks a weakly identified parameter. A poorly fixed distance widens the distance constraint but keeps the timing evidence. A range that ends where the optimiser hit a bound isn't a range.
   - **Overlapping frames.** Consecutive STFT frames share 88 % of their samples, so counting them as independent would understate the spread roughly threefold.

**Acceptance.** A change is kept only if all of these hold on the development cases and the synthetic failure matrix:
- the true flights pass the filters on every positive case, using `detect` output with no hand-picked windows;
- on Oyster Bay from raw audio, the true pair ranks first, with the refined peak within the practical resolution of the truth;
- candidate counts stay within 2× the baseline's, and Tier 2 stays within its budget;
- no wrong pair beats the true one where it didn't before, and the top candidate's location error doesn't grow;
- partial and degenerate passes give an explicit weak or unusable fit, not a confident one.

These thresholds are provisional, and they are fixed before the experiments run. Every knob tuned on the development cases is counted, because tuning many knobs on two recordings overfits them.

**Stop rule.**
- An experiment is kept if it meets the criteria and reverted if it doesn't. It is deferred if two recordings can't decide it.
- If the time box ends without a variant that meets them, the fallback is the best measured variant, or else the ±10 s / ±12 % gates ([gate-tolerances](docs/experiments/2026-11-03-gate-tolerances.md)).
- Under the fallback, raw-audio localisation is documented as a known limitation, the verdict abstains more, and E1 stays open.

#### Phase 3: `dopplertrack locate` (M–L; step A can start alongside Phase 2)

**Step A: a thin `locate` with explicit failures.** One command over today's pieces:
1. audio → spectrogram → `detect` → usability check (S6);
2. flight data (with margin, cached) → CPA table (cached);
3. search with one automatically chosen pair of adjacent detected flyovers. Tier 2 checks it with and without the silence filter, which is off by default in `locate` (S4);
4. refine the winner with the other flyovers;
5. verdict and `result.json`.

Each failure is an outcome with a stated reason:
- no usable flyovers;
- flight data missing over the recording's time or the box;
- a matched clock that puts part of the recording past UTC midnight. `locate` searches one day, and `--days` fetches the adjacent one;
- no candidate surviving.

**Step B: search over several pairs.** Choosing pairs automatically breaks assumptions the single-pair search relies on:
- **Silence filter** (S4). Off by default in `locate`. Close passes that no detected flyover explains become a weak penalty at re-ranking, validated separately. `search` keeps upstream's default.
- **Assignment** (S1, S2). Each candidate assigns events to flights one to one:
  - a detection explains at most one pass, and a pass at most one detection;
  - the harmonics of one pass are one event;
  - a detection can stay unmatched at a fixed cost: a jet, a bird, or an aircraft without ADS-B.

  Every candidate is scored on the same detections with the same normalisation. The record shows how much support comes from the proposing pair and how much from the other flyovers.
- **One clock, fitted to every event** (S3). The audio-to-UTC offset is optimised over all assigned events jointly.
  - **Drift.** On long recordings, test a bounded clock drift and add it only if it improves consistency. Sample clocks drift by tens of ppm, about 1 s in 12 h at 20 ppm.
  - **Edits.** A flyover that fits only with a different clock suggests an edit, as a diagnostic.
- **Final score on the actual trajectory**, with propagation delay and the shared clock. Each event's f0 is solved conditionally: as a 1-D sweep, or in closed form for a least-squares track.
- **Several modes through refinement.** Keep separated location-and-clock modes, including several from the same flight pair, and refine each before choosing.
  - Two geometries are degenerate, and `locate` checks for both (6.1): a single flight can't tell which side of its track the microphone is on, and parallel flights at the same speed leave the position along the tracks open.
  - More flyovers on other headings resolve both.
- **Edges.** A candidate whose support or region reaches the box edge, or the edge of the flight data's coverage, is flagged.
- **Confidence on the final output.** Trying many pairs and keeping the best inflates the winner's score, so confidence is computed after all the pair selection and re-ranking, never per pair.

**Done when**, from audio, date and box alone, two things hold. First, on both development recordings the top-ranked mode holds the true flight pair, with its refined peak within the practical resolution of the truth. Second, each failure case gives its expected outcome with no confident wrong answer:
- no usable flyovers;
- incomplete flight data;
- a recording crossing UTC midnight;
- the moved box.

Motion and edit checks are diagnostics and not part of this.

**If step B slips:** release step A's single-pair `locate`, and document multi-pair search as a known limitation.

#### Phase 4, machinery: verdicts and abstention (L; time-box 2 weeks)

- **Modes first.** Two candidates are distinct modes when their locations are farther apart than the practical resolution (decision 1), or their clocks differ by more than a pass can resolve.
  - "Ambiguous" then means a distinct mode is still plausible, and no rule depends on the radius being estimated.
  - A single radius is reported only when one mode sums up the result; otherwise every region is listed.
- **A starting feature.** The time-gated extra-flyover consistency is the strongest lead so far ([extra-consistency](docs/experiments/2026-11-03-extra-consistency.md)). Its ±15 s gate is a development hypothesis until it holds on recordings it wasn't chosen on.
- **Other candidate features:**
  - the margin over the strongest distinct competing mode, from any pair;
  - the number of extra flyovers explained, and their scores;
  - close passes that no flyover explains;
  - peak width after refinement;
  - event fit quality;
  - clock consistency.
- **Thresholds.** Fit them on the calibration groups' positives against their negatives, never on the evaluation group. A region that is unavailable or wider than the resolution means no "located".
- **Whole-process evaluation.** Each evaluated case runs pair selection, refinement and abstention; nothing is scored per pair.
- **Done when** the verdict and region come out of `locate`, labelled experimental, and the benchmark reports confident-wrong and abstention rates for each group.
- **If the time box runs out** before any features separate the calibration positives from the negatives:
  - `locate` uses conservative fixed rules instead: "located" only for a single surviving mode with at least one extra flyover explained within ±15 s and a region inside the resolution;
  - the region is reported as unavailable otherwise;
  - the limitation is documented.

#### Phase 5: report (S–M; independent once the result record exists)

One HTML page per `result.json`:
- a map of the candidate regions and the score map;
- the matched flights, with registration and type;
- the inferred recording start time;
- a measured-against-modelled curve overlay for each event (`plots.py` already draws these);
- the data report and diagnostics: flight-data coverage, clock consistency, possible edits;
- GeoJSON and KML export.

**Done when** every seed case's `result.json` renders, failures included.

#### Phase 6: release (S–M)

A README covering install (including ffmpeg), requirements and limits, and how to read the verdict, including what "experimental" means. Release in the fork, and send upstream PRs as the author accepts them.

**Acceptance test**, run before each release:
- install the built package in a clean environment on macOS and Linux (in CI), run the quickstart, and check its expected output;
- a clear diagnostic when ffmpeg is missing or too old;
- progress reporting, and resource estimates (download size, CPA table size, time) before the long stages, with a disk-space check before writing;
- cancellation at any point, and a re-run that resumes from completed cached stages;
- defined behaviour for an unavailable archive, a network failure or a partial download: retry a fixed number of times, then stop with an error.

**Done when** the acceptance test passes on macOS and Linux.

### M3: validated claims

A claim is made only on evaluation recordings, against criteria and thresholds fixed before any evaluation recording is run:
- **Three numbers, reported together:**
  - the confident-wrong rate among located answers;
  - region coverage among located answers;
  - the share located, with the location error and the abstention rate.

  Coverage over all cases says nothing about the located subset, so it's computed on that subset.
- **Independence.** Each group counts once (5.2). Candidate pairs or clips from one recording are not independent.
- **What the numbers can show.**
  - Zero confident wrong answers among n located groups bounds the true rate below about 3/n at 95 % confidence: under 10 % after 30, under 5 % after 60. Abstentions don't count toward n, so the more the tool abstains, the more recordings this takes.
  - A 90 % region that holds in 27 of 30 groups is consistent with a true coverage of 74–98 %; 54 of 60 narrows that to 80–96 %.
- **What they can't guarantee.** Those numbers describe the evaluation group, not the method that sets the region. A guarantee needs more:
  - Split conformal calibration on held-out groups gives coverage averaged over all cases.
  - A guarantee among located answers needs a selective method such as Learn-then-Test. With zero errors it takes about 22 located calibration groups at α = δ = 0.1, and about 59 at 0.05.
  - Leave-one-group-out tuning gives neither guarantee.
  - Reaching 30 cases doesn't calibrate a region by itself. With 30 calibration cases, a nominal 90 % region's realised coverage spans about 80–97 % (5th to 95th percentile).

Until then the verdict and region stay labelled experimental. Gathering the evaluation group is evidence work with no fixed date.

### M4: toward the destination

Each item waits for a measurement that calls for it:
- a ±N-day search for recordings whose date is uncertain, at about 12 min per extra day here. Converting each day once into propeller-only tiles would make extra days and boxes cheap;
- temperature and wind corrections from METAR and soundings, if Phase 2 finds a bias they remove;
- models of turning and accelerating flight, on the same condition;
- jets as a signal source, with their own detection and matching;
- choosing extra flyovers by how well their geometry pins down the location;
- downloads that resume across restarts;
- multipath delays, microphone arrays, and advanced time-frequency methods, each if a measured bottleneck points to it.

## 5. Measuring progress

The measuring stick has to be trustworthy before it gets big: caches that can't go stale, labels checked against the audio, and evaluation data kept apart from the data we tune on.

### 5.1 Cases

**Seed set**, one for each kind of outcome:

| Case | Expected outcome | What it tests |
|---|---|---|
| Oyster Bay, 1 h | located | the reference result |
| An eagle-cam clip of 1–2 h holding its two search events | located | another site, geometry and noise level |
| Oyster Bay audio with the box moved 150 km, over land with similar traffic | not located | the truth is outside the box by construction, so any confident answer is wrong |
| A degraded copy of one of these, e.g. high-passed at 150 Hz and encoded as low-bitrate AAC | located or abstain | abstaining passes; a confident wrong answer fails |

**Growth**, cheapest first:
1. **More eagle-cam clips**: the 12 h archive cut into 1–2 h clips, giving roughly 6–12 positive cases with different geometry. They share a site, a microphone and a day, so they count as one group.
2. **Augmented copies**, made with ffmpeg: low-bitrate AAC, Opus and MP3; high-pass at 100 and 150 Hz; noise suppression; added wind noise; trims to 30 and 15 min; a 30 s cut between two flyovers. Expected outcome: located or abstain.
3. **Negative controls**, expected not to be located:
   - the right audio with another day's flight data;
   - the right day with the box moved 150 km;
   - stretches with no flyovers, confirmed in the spectrogram;
   - real background recordings with other tonal sources and no prop passes: the three Essex recordings (jets) and ESID 937 (no prop within 20 km all day). These also give `detect`'s false alarms per audio hour.
4. **Stress tests**, inspected rather than scored as plain negatives:
   - time-reversed audio. Its curves mostly rise, which turns, climbs and power changes can also produce, so it isn't a guaranteed negative;
   - incomplete flight data (an hour of traces removed);
   - a recording crossing UTC midnight: ESID 375 and 937 do;
   - a true location within a few km of the box edge.
5. **Independent recordings** (5.6), the only source of calibration and evaluation data.

**Synthetic failure matrix.** Small cases that run in seconds as Tier 0–1 tests. Each phase adds the ones it needs.
- **For the fits (Phase 2):**
  - a partial pass, with its CPA outside the recording or masked;
  - a nearly flat curve, from a distant or slow pass;
  - a crossing tone;
  - a missing fundamental;
  - a harmonic mistaken for the fundamental;
  - a turning or descending pass made from a real trace.
- **For the search (Phase 3):**
  - one flight that could be on either side of the microphone;
  - two flights on parallel tracks at the same speed and heading;
  - two plausible clock offsets;
  - a true location near the box edge;
  - a gap in a flight trace;
  - a sample clock drifting 50 ppm over 12 h.

### 5.2 Groups and sets

A group holds everything that shares a site, a microphone installation, a session (day) or flights, and groups are assigned whole.
- **What travels together.** Clips, augmented copies and negatives made from one recording stay in its group. So do recordings made together, such as several devices recording one Seattle session, or the two Essex recordings 400 m apart that hear the same jet.
- **Familiar and unseen sites.** Results on new sessions at a familiar site are reported apart from results at unseen sites. Only the second measures how the tool does somewhere new.

Each group belongs to one set:
- **Development**: Oyster Bay and the eagle cam. They have shaped the method, so they never count as evaluation.
- **Calibration**: groups used to fit Phase 4's thresholds. While there are few, fit them leaving one group out at a time, and redo every tuned choice inside each fold. That is a development method, not a guarantee (M3).
- **Evaluation**: whole groups held out, from other sites and days where possible, run only at milestones and never tuned on.

### 5.3 Labels

Three layers, labelled separately:
1. **Acoustic event.** Is a tone or flyover present in the window? The classes are clear, uncertain, overlapping (two flyovers, or a crossing tone), masked (wind, birds, an edit) and absent. Labelled from the spectrogram.
2. **Flight association.** Which ADS-B pass made it, if any. "Unmatched" is a label on both sides (V2).
3. **Physical truth.** What the observer should hear, from the curve modelled on the actual trajectory: its steepest-fall and heard-CPA times, and the slant range and speed at CPA.
   - This is not the parameters of a straight pass, which don't exist for a turning, climbing or descending aircraft. The propeller's rest frequency is never observed directly.
   - A pass whose curve falls fastest far from its geometric CPA is flagged as not straight.

Steps:
- **Propose** a window for each ADS-B pass, as one contact sheet per case.
- **Label blind first.** For every seed window and a sample of the rest, label layer 1 without the modelled curve, then reveal it and label layer 2. Seeing the expected curve first biases the eye toward finding it.
- **Confirm the rest with the overlay**, which takes minutes per case. A Claude session can do the first pass, with you spot-checking it. Each label records who made it and whether it was blind.
- **Score by class.**
  - detection recall and precision on layer 1;
  - association accuracy on layer 2;
  - fit errors against layer 3, with flagged passes and synthetic events reported separately.

  Unverified passes are reported but never tuned on.

### 5.4 Tiers

| Tier | Runs | Time | When |
|---|---|---|---|
| 0 | unit tests, including the cache tests and the synthetic failure matrix | < 1 min | every change |
| 1 | `detect` and `fit` against labels, and the known-point check, on the seed set | < 3 min | every change to detection, fitting or scoring |
| 2 | blind search on the seed set from cached CPA tables | 2–3 min per case | before keeping a change |
| 3 | everything from scratch on all development cases, negatives and stress tests | hours, in the background | nightly and before a PR |
| E | the evaluation set, end to end | hours | at milestones only |

Tier 1 runs its cases in parallel, and detections are cached by audio and detector version, so changes to fitting or scoring skip detection. A case joins Tier 1 only if Tier 1 stays under 3 min.

### 5.5 The result record and the scoreboard

**The result record.** Every run of `locate` or of a benchmark case writes one `result.json` with a schema version. It holds the decisions themselves, so the report and the benchmark never reconstruct them from logs. Version 1 holds what today's pipeline can fill. Later fields arrive with the features that produce them, each with a version bump.

What it records:
- **conventions**:
  - WGS-84 coordinates, and which height;
  - times in audio seconds and UTC, saying which CPA time each one is (emission, heard or steepest fall);
  - distances as slant range at CPA, not altitude or ground range;
- **provenance**: code revision, parameters, and the hash of every input and cache used;
- **events**: each detection's fit, harmonic, fit diagnostics, and assignment to a flight or to "unmatched";
- **candidates**: location, flight pair, clock and drift, score per event, and the mode each one belongs to;
- **the funnel**: how many hypotheses each filter removed, and for benchmark cases whether the true one survived;
- **the verdict**: its reasons, and the uncertainty region with the method and version that made it, or why there is none;
- **data limitations**: flight-data coverage over the recording and the box, skipped traces, possible edits;
- **execution errors**, kept apart from the verdict.

**The scoreboard.** A benchmark run collects the records into one `results.json` in its own run folder, `$DOPPLERTRACK_DATA/runs/<date>-bench-<commit>-<tier>/`. It reports by case and by group:
- the expected outcome, and whether it was met;
- **detection**: recall on confirmed events, and false alarms per audio hour on background recordings, as a curve over thresholds;
- **association**: the share of confirmed events assigned to the right flight;
- **fits**: errors against layer-3 truth by label class, and the known-point result;
- **the funnel**: candidate counts after each filter, and where the true hypothesis dropped out;
- **search**: the true pair's rank, the margin, and the location error of the top and refined candidates as quantiles over cases;
- **verdicts**:
  - the share of positive cases located;
  - the confident-wrong rate among located answers;
  - the abstention rate;
  - region coverage, always next to region size;
- **stage timings**.

A tool that always abstains has no confident wrong answers, so the share of positive cases located is a target of its own.

`bench compare <a> <b>` prints the difference between two runs. There are two baselines, both at upstream a16b700:
- **saved-fit**: the event fits committed in `docs/results/`. It isolates search and physics.
- **raw-audio**: `detect` output with no hand-picked windows. It is what a user gets.

A fitting change shows only in the raw-audio numbers; a search or scoring change is judged on both.

### 5.6 Independent recordings

The evaluation set is what limits M3, and collecting it takes calendar time rather than engineering, so it starts now.

**A recording counts if it has:**
- the microphone's location to about ±10 m (a phone's GPS fix or a known point), and its height above the ground;
- the start time in UTC to the second, from a network-synced clock or a time chime, and no pauses except at known times. AudioMoth's 5 s gap per minute is fine once the spectrogram handles gaps;
- the original file, not a re-encode, with the device, app and settings noted. Voice processing, noise suppression and bass cut-off should be off where possible;
- no edits, or each one noted;
- adsb.lol coverage of the place and day, checked with `tools/data/site_traffic.py`, with at least two prop passes expected within about 6 km;
- a site and session ID, for the groups.

**Variety matters more than volume**: new sites, devices, traffic levels (quiet airspace especially) and pass geometries (crossing tracks, not one airway).

**Where to look:**
- public livestream archives with published locations;
- long field recordings with location and time, such as Eclipse Soundscapes and xeno-canto;
- your own controlled recordings. These are the only source of moving, edited and phone-processed cases, which the motion and edit diagnostics (L4, S6) need for testing.

**On disk now:**

| Source | What it is | Use |
|---|---|---|
| Eclipse Soundscapes ESID 375, 740, 710 | AudioMoths with clocks set by a time chime, 2024-04-07; 6, 7 and 19 prop passes within 12 km | calibration or evaluation (decision 2). 740 and 710 record 55 s of every minute, so they need a gap-aware spectrogram first |
| Eclipse ESID 937 | about 25 h from 05:40 UTC on 2024-04-07, with no prop pass within 20 km that day | a negative that must abstain, once 04-08's flight data is fetched |
| xeno-canto XC979185 | one prop pass, start time known to the minute | a single-flyover case |
| xeno-canto XC990819, XC990820, XC986433 | Essex, jets only | development: background negatives for `detect`'s threshold; the first two are one group |

ESID 375 and 937 both run past UTC midnight into 2024-04-08, so they also test the midnight case, and they need that day's flight data.
| Seattle (planned) | your recordings, several devices at one spot | one group per session: it tests devices, not new sites |

Aircraft-audio datasets without location, timing and matching trajectories can train or test detection, but can't validate a location.

## 6. What we know

### 6.1 The physics of a pass

For a straight pass at constant speed v and closest slant range R_c, the frequency heard at time t is

f(t) = α + β·z(t), with z(t) = (t − τ_c) / √(s² + (t − τ_c)²), where:
- α = f0·c²/(c² − v²);
- β = −f0·c·v/(c² − v²);
- s = R_c·√(c² − v²)/(v·c).

Sources: Ferguson & Quinn 1994, eqs. 15–16; Ferguson & Lo 2000, eqs. 1–4. What follows from it:

- **Three landmarks.**
  - The curve falls fastest, and passes the midpoint of its two asymptotes, at τ_c, the instant the aircraft is at closest approach (the emission CPA).
  - It passes f0, the heard CPA, R_c/c later. At 1–9 km that is 3–26 s.
  - The CPA table's `t_emit` matches the steepest fall only for straight, constant-speed flight.
- **What each parameter rests on.** Speed comes from the frequency span (v = −c·β/α), f0 from α, and distance from the sweep's duration s together with v. Distance is therefore the weakest parameter. It is also coupled to timing through the heard CPA, which is why pairing on heard-CPA times is fragile (E2).
- **f0 and time trade off.** Near the steepest point, raising f0 by δf0 looks like shifting the curve by δf0/g_max, where g_max = f0·c²·v²/(R_c·(c² − v²)^{3/2}). For the four development flights g_max is 0.8–1.4 Hz/s, so 1 % of f0 is worth 0.8–1.7 s.
- **Window length.** At g_max, a window of length T smears the tone by g_max·T. The 2.048 s window spreads 1.6–2.9 Hz (3–6 bins) at the steepest point of the development passes. The best compromise between smear and frequency resolution is T ≈ 1/√g_max, about 0.85–1.1 s here. For controlled overhead passes at 5–21 Hz/s it is about 0.2–0.45 s, which is why the reference work used 0.256 s. In the flat tails, longer windows win: frequency variance falls as 1/N³ (Kay I, eq. 3.41).
- **Geometry.**
  - A single pass is mirror-symmetric: the curve depends only on the slant range, not on which side of the track the microphone is.
  - With an unknown clock, one pass fixes only a distance from its track. Two passes on different headings fix a few discrete points, and more remove the ghosts.
  - Two flights on parallel tracks at the same speed and heading leave the position along the tracks open.
- **Ground reflection.** For a microphone well above the ground, the direct and ground-reflected sound can cancel at some elevation angles, so a tone can fade in and out during a close pass. This hasn't been checked in our recordings yet. Tracks must tolerate gaps, and the recording checklist notes microphone height.

### 6.2 What our experiments showed

All on the two development recordings:
- **The event-2 bias** persists under both fit objectives tested, and fitted timing errors grow with the f0 error ([event2-bias](docs/experiments/2026-11-03-event2-bias.md)).
- **Wider gates**: ±10 s / ±12 % kept the true pair first on both recordings with the README windows. ±12 s let a wrong pair win on both, and candidate counts grew up to 2× ([gate-tolerances](docs/experiments/2026-11-03-gate-tolerances.md)).
- **Narrower re-fit windows** help one recording and hurt the other. Neither window rule tested suits both ([rewindow](docs/experiments/2026-11-03-rewindow.md)).
- **Extra flyovers** behind a time gate of about ±15 s were explained only for the true pair, on Oyster Bay. That is the best confidence lead so far ([extra-consistency](docs/experiments/2026-11-03-extra-consistency.md)).
- **Timing conventions.** Pairing on emission-CPA times helps some fits and hurts others. The like-for-like steepest-fall comparison agreed within 0.5–2.7 s for the contrast and `detect` fits on both recordings, but not for every fit: the committed Oyster Bay fits were 8.7 s off ([timing-conventions](docs/experiments/2026-11-03-timing-conventions.md)).

### 6.3 What the literature supports, and its limits

Equations cited here were checked against the PDFs.

| Source | What we take from it | Caveat |
|---|---|---|
| Ferguson 1992; Ferguson & Quinn 1994; Ferguson & Lo 2000; Ferguson 2016 | The pass model, the least-squares fit with α and β eliminated, and starting values from the asymptotes and peak slope | Controlled overhead passes at about 70–610 m, flown straight and level at set speeds. Single-sensor errors were 5–9 kn and 54–100 ft, yet about 12 % of altitude estimates were more than 20 % off. Our passes are opportunistic, at 1–9 km, so expect worse. Ferguson 2016's printed eq. 14 squares each term inside the sum; take the reduced objective from Ferguson & Quinn 1994 eq. 20 |
| Quinn 1995 | Weighting each frequency estimate by amplitude squared, a covariance for the fitted parameters, and fits of partial tracks | Amplitude is a reliability weight, not a range measurement. The covariance assumes independent errors from non-overlapping blocks |
| Timlelt et al. 2017 | A closed-form comparator | Eq. 19 takes the argmax of f′ although f′ is negative (its eq. 15), and eq. 20 drops a square. Its simulations show a 7 % f0 error, and its experiments use a loudspeaker moving at 1–1.6 m/s |
| Chan & Towers 1992 | Keeping several low-cost solutions, because of ghost solutions and noise | Written for five or more simultaneous sensors; their sensor counts don't transfer |
| Iatsenko et al. 2016 | Ridge-extraction schemes, adaptive penalties, and error measures | Built for components present throughout a signal. With transient ones it hops between components, and it has no stopping rule. Harmonics aren't covered |
| Kay I (1993) | The frequency-estimation bound (eq. 3.41), separable least squares (§8.9), and the threshold effect at low SNR | Bounds hold above a threshold SNR; below it, outliers dominate |
| Kay II (1998) | False alarms grow roughly in proportion to the cells searched (eqs. 7.36–7.37) | Assumes independent cells and known noise; ours overlap, so the rate has to be measured |
| White 1982 | A wrong model's fit converges to the best approximation for that objective and window | Even a sandwich covariance measures spread around that approximation, not distance to the truth, and the usual covariance can be wrong in either direction. It applies to likelihoods, which a brightness score isn't |
| Raue et al. 2009 | Profile likelihood, and structural against practical non-identifiability | χ² thresholds need Gaussian noise of known variance and an adequate model. For a brightness score, read profile shapes only |
| Golub & Pereyra 2003 | Variable projection for the least-squares fit | Applies to sums of squares only, doesn't remove local minima, and isn't always faster |
| Angelopoulos & Bates 2021 | Split conformal regions, and Learn-then-Test for guarantees among non-abstained answers | Coverage is averaged over exchangeable cases, here groups of recordings. It doesn't cover thresholds tuned by leave-one-out |
| Cawley & Talbot 2010 | Tuning and reporting on the same cases biases results by as much as the differences between methods | Their smallest data set has 64 points; with two recordings the risk is larger |
| Lo & Ferguson 2003 | Ground-reflection delay as a constraint on elevation and range | Written for broadband jets over hard ground. Its interference fringes are one plausible source of `detect`'s jet false positives (E5) |

## 7. Risks and open questions

- **Event fits may stay too weak on real passes.** If Phase 2's model-error experiment shows that most passes aren't straight enough, the route shifts toward scoring on actual trajectories and wider joint hypotheses, at the cost of more candidates and more abstentions.
- **Ground truth stays scarce.** Slices and augmented copies of one recording aren't independent, and both development recordings are in busy US airspace. M3 waits until there are enough independent groups, including quiet airspace.
- **Tuning to the benchmark.** Development numbers will flatter the method. Only the evaluation set counts for claims, and Phase 2's acceptance criteria are fixed before its experiments run.
- **Detection precision.** Jets and other tonal sources score like props (E5). If they can't be separated, more assignments end unmatched and fewer recordings are located.
- **ADS-B coverage.** Light aircraft without ADS-B are invisible (L2), so an unmatched acoustic event isn't evidence against a location.
- **Labels from ADS-B.** Unchecked passes would reward detecting aircraft that aren't in the audio, so only confirmed events are tuned on.
- **Upstream moves fast.** Merge upstream into `dev` often and keep changes modular.
- **Test recordings disappear from YouTube.** The downloaded audio is kept in the data root.

## 8. Decisions needed

1. **The practical resolution behind "located".** Proposed: a 1 km radius. A smaller radius makes the tool abstain more; a larger one makes "located" less useful.
2. **Which clean recordings go to calibration and which to evaluation.** This has to be decided before any of them is searched. Proposed:
   - evaluation: ESID 375 (quiet, continuous) and ESID 710 (moderate traffic);
   - calibration: ESID 740, ESID 937 (the must-abstain negative) and XC979185;
   - development: the three Essex recordings, since Phase 2 tunes `detect`'s threshold on them;
   - Seattle sessions go to evaluation by default.
3. **Recording ground truth yourself.** The checklist in 5.6 applies. Several devices at one session form one group, so a second site is worth more than a fourth device. Deliberately moved, edited and phone-processed clips are worth a session of their own.
