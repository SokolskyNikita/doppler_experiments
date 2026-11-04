# Plan: from today's dopplertrack to a dependable acoustic geolocator

This is the route from what dopplertrack does today to the tool we want, written from what we currently know. It will change as we learn: each experiment gets a record in [docs/experiments/](docs/experiments/README.md), and its conclusion is folded in here.
- [AGENTS.md](AGENTS.md) has the working rules.
- [docs/reference/README.md](docs/reference/README.md) has the papers and video-reference guide.
- Code references are to `dev` at 5a617ff.

## 1. Destination

### The tool we're aiming for

Given a recording made at one fixed spot, on any device and of any length, plus roughly when and where it was made, the tool says where it was recorded, how sure it is and why. When the recording doesn't hold enough to tell, it says so plainly.

What "good" means, in terms we can measure:
- **Trustworthy when it answers.** Confident wrong answers are rare, and that rate is measured on recordings never used to build the tool.
- **Useful.** It locates most recordings that hold two or more matchable propeller flyovers (or one, with a known time), to within the resolution in decision 1.
- **Honest about uncertainty.** Each answer has a region whose stated coverage holds on independent recordings, and separated alternatives are shown, not hidden.
- **Holds up** under what real recordings go through:
  - lossy codecs and phone processing;
  - wind, and other tonal noise such as jets and machinery;
  - edits;
  - aircraft that turn, climb or change speed.
- **Explains itself.** A report shows the matched flights, the measured and modelled curves, and the alternatives with why they lost.
- **Practical.** It installs with pip and runs on a laptop in minutes once a day's flight data is cached. It survives interruptions and fails with clear messages.

Further out, if the first releases work: uncertain dates (a search over ±N days), larger regions, jets as a signal source (most traffic is jets) and single-flyover recordings with only a rough time.

**Out of reach or not planned:**
- aircraft without ADS-B, which can be heard but not matched;
- moving microphones;
- no date or region at all: a worldwide index is about 1.4 TB of ADS-B per year, with far more compute;
- real-time use;
- a GUI, since a static report covers most of it.

### The first usable release

The first usable release, milestone M2 in section 4, is a `locate` command.

**Inputs:**
- **The recording.** Any file ffmpeg can decode. Channels are averaged to mono, the audio is resampled to 4 kHz and only 40–450 Hz is analysed (`audio.py:14`, `cli.py:24`). Searches have run on 1 h and 12 h recordings, and `detect` on clips of 5–92 min. At about 1.5 min of `detect` per audio hour, long recordings are slow but allowed.
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
  - a search cut short by a budget, so that hypotheses went unevaluated;
  - no meaningful uncertainty region.

Execution errors (unreadable audio, a missing ffmpeg, a network failure) are reported as errors, never as verdicts. The verdict and region are labelled experimental until M3.

## 2. Starting point

**What works:**
- **The method reproduces both published results from saved event fits.**
  - Oyster Bay: the true flight pair ranks 1st of 328, the top candidate is 123 m off and the refined peak 43 m off. With `--harmonics 2 1` this matches the committed tables exactly (4.9 % margin); the default gives the same ranking and distances with a 4.0 % margin.
  - Eagle cam: the true pair ranks 1st of 607 at 917 m, with a 2.5 % margin. With three extra flyovers (the committed `detect` candidates #2, #3 and #10) the refined peak is 567 m from the nest. With two events only, the score surface is flat and the peak 877 m off.
- **Upstream fixes.** [PR #2](https://github.com/mjshiggins/dopplertrack/pull/2) is waiting for the maintainer. It fixes `fetch-day` on split archives, restores `fit`'s brightness objective as the default, and adds tests.
- **The CPA cache** is done in `dev`; sending it upstream is deferred.
  - **How it works.** It is keyed on its inputs' contents, it writes CPA tables and terrain tiles atomically, it treats an unreadable file as a miss and it holds a lock per table.
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
- the Livermore corpus (Pathak 2026, CC BY 4.0): 40 phone recordings of one light-aircraft pass each, with the published frequency track, the ADS-B track and a results table. Real passes with trajectory truth, for Phase 2 (5.6);
- aircraft and environmental audio for detection work only, acquired 2026-11-03: AeroSonicDB v1.1.2, DataSED, DataSEC and about 6 h of A2O audio from three sites. None has precise microphone positions (A2O's are shifted by up to a few hundred metres), DataSEC and DataSED include edited clips, and none but Livermore has flight data on disk. All but A2O are non-commercial licences. Sources, licences, inventories and the pending AeroSonicDB 3K access request are in the data root's `MANIFEST.md`;
- flight data for each recording's day: 2024-04-07 for the Eclipse sites, but not yet 04-08, which two of them run into. The development cases also have the day before, plus METAR reports and upper-air soundings;
- 16 papers and books, plus colsto's Doppler-geolocation walkthrough with a local annotated transcript and visual evidence (see the reference guide).

None of the non-development audio has been searched yet. A recording session in Seattle is being planned.

Three open-source projects attack the same problem, all started in November 2026. What they report and what we take from them is in [docs/reference/related-projects.md](docs/reference/related-projects.md). We treat their numbers as hypotheses to reproduce.

**Costs on this Mac** (M4 Pro, 48 GB RAM, 183 GB free disk at the time of writing):

| Stage | Time | Disk |
|---|---|---|
| `spectrogram`, 1 h of audio | 9 s | 45 MB |
| `detect`, 1 h | 1.5 min | – |
| `fetch-day`, one day, 100 × 150 km box | 4.8 min (3.9 GB streamed) | 29 MB |
| `search`, 200 m grid over that box | 7.6 min, 5.5 of them building the CPA table, before Phase 1; with `--jobs 10` the cold-cache build is about 27 s and the search from a cached table 64 s | 874 MB CPA cache compressed, 2.76 GB since the cache is written uncompressed (the compressed save alone took 69 s); 10 MB results |
| `refine`, 50 m grid | 4 s | – |

The CPA table depends only on the grid and the flight data, not on the events. So once a case has its table, re-running the search with different fits, pairing rules or scoring takes about a minute at 10 jobs instead of 8 minutes serial, and all clips from one day and box share a table. That is what makes fast iteration possible. Plan on about 3 GB of CPA tables per case-day (uncompressed; dropping the derivable `t_heard` column at the next cache-version bump would save a third); the data root holds about 47 GB and the cache is regenerable.

## 3. What stands in the way

Open problems, grouped by theme. The IDs are used throughout.

**Event evidence: detection and fits**

| ID | Problem | Evidence |
|---|---|---|
| E1 | Fits of real passes are biased, and the search turns each fit into hard gates: ±35 % speed, 0.4–2.5× distance, ±6 s between the events and a ±5 % f0 sweep. A bad fit removes the true answer with no warning. Oyster Bay's event 2 fits with f0 5, 10 and 11 % high under three fitting setups, and the time between the events 5.0, 9.0 and 10.1 s short. The discrepancy persists under both objectives tested | [event2-bias](docs/experiments/2026-11-03-event2-bias.md); `pipeline.py:122`, `score.py:65` |
| E2 | Pairing compares fitted heard-CPA times (emission CPA + d/c) with the CPA table's `t_heard`. A distance error moves the gate by Δd/c, and an f0 error by δf0/g_max, where g_max is the curve's peak slope. For Oyster Bay's event 2 that is about 1 s per 1 % of f0, consistent with E1's timing errors | `pipeline.py:138`, `search.py:198`; [timing-conventions](docs/experiments/2026-11-03-timing-conventions.md) |
| E3 | No frequency track, so there is nothing to fit by least squares, weight by reliability or check for gaps, crossings and harmonic jumps | `tracks.py:36` is never called |
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
| D4 | The loader takes geometric altitude when present and otherwise barometric, without recording which, and ignores the trace flags that mark a reception gap before a fresh fix or a geometric value in slot 3. Geometric ADS-B altitude is WGS-84 ellipsoidal, the terrain tiles are orthometric and pressure altitude is neither, so three datums meet in the ENU conversion. At 1–9 km that is a few percent of slant range and a few tenths of a second of heard-CPA time | `adsb.py:108`, `terrain.py:13`, `geo.py:33` |

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
- **Stay mergeable with upstream.** Fork internals may be restructured while preserving existing behavior and documented defaults through explicit profiles. Keep self-contained fixes easy to adapt upstream; `AGENTS.md` has the branch recipe.

| Milestone | Delivers | Phases | Depends on | Rough size |
|---|---|---|---|---|
| **M1: a measuring stick we can trust** | the small known bugs fixed, a typed detector worker interface, a local check command, the result record, and the seed benchmark with both baselines | 0, architecture preparation, 1 | – | 1–2 weeks + preparation |
| **M2: first usable release** | `locate`, from audio, date and box to a verdict and a report, with explicit failures and the alternatives it considered, installable from a release in the fork | 2, 3, 5, 6 and the machinery of Phase 4 | M1 | 3–4 more weeks |
| **M3: validated claims** | the confident-wrong rate and region coverage measured on independent recordings, against criteria fixed in advance | 4 (claims) | M2, plus enough independent recordings (5.6) | no date: it waits on evidence |
| **M4: toward the destination** | the extensions in section 1, each when a measurement calls for it | Later | M2 | open |

Sizes assume Claude writes most of the code and you review: S is a day or less, M is 2–5 days, L is 1–2 weeks of part-time work. The critical path is Phase 0 → architecture preparation → Phase 1 → Phase 2 → Phase 3 (step B) → Phase 4. Phase 1, including its parallelism item, starts only after architecture preparation completes. These can run independently of that ordering:
- Phase 0's individual fixes, alongside each other;
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
- **Data report** (D2). `fetch-day` and `search` report traces kept, traces skipped as malformed and gaps near the candidates. A curve modelled from a trajectory carries a validity mask: inside the trace's span, no local evidence gap over 30 s and a valid retarded-time map (computed directly by the forward model). Resampling preserves the evidence mask while geometry retains the 90 s segment bound for CPA proposals; missing positions/heights and new-leg boundaries use the same rules in segmentation and diagnostics. The report also says what it can't know: a complete download doesn't mean every aircraft overhead broadcast ADS-B (L2).
- **Elevation no-data** (D3). Mask −32768 in `Terrain`, with a test on the ESID 937 pixel.
- **Altitude source** (D4). Keep each point's altitude source (geometric, barometric, none) and its position source (ADS-B, MLAT, TIS-B: slot 9 of the trace), and honour the trace flags: bit 1 marks a new reliable fix after a reception gap over 20 s (the fix remains valid), and bit 8 marks a geometric altitude in slot 3. The data report (D2) gives the share of barometric-only points, and the result record names the height datum (5.5). A geoid correction waits for Phase 2's altitude perturbation to show it matters.
- **Platform** (W4). A fresh-install smoke test and a clear error when ffmpeg is missing, both run locally on this Mac as part of Tier 0. No GitHub CI for now: setting it up and waiting on it would slow the work down, and a local run on the development machine covers what it would check. `.github/workflows/` stays as upstream has it until a release needs more.

**Done when** each fix has its test and is in `dev`.

#### Between Phases 0 and 1: architecture preparation

Give the detector worker named inputs and outputs. Test which candidate survives a score tie when
overlapping windows propose nearby events, and exercise the records through the process pool.
The [preparation spec](docs/phase1-preparation.md) describes the worker change and checks.

**Done when** the worker checks pass as part of the offline command and the edit map
(`docs/architecture.md`) points to the detector, CPA computation and cache tests. Phase 1 starts with parallelism.

#### Phase 1: minimal benchmark (M)

1. **Parallelism first** (S–M). Everything after this is measured against the Tier budgets in 5.4, so the machine has to be used properly before the budgets mean anything. Today trace loading and `detect`'s window scan use a process pool and nothing else does; the CPA table, 5.5 of the search's 7.6 minutes, is single-threaded geometry over grid points, flights and samples.
   - One knob, `--jobs`, with an environment default of the performance-core count (10 on this M4 Pro; its 4 efficiency cores would set the pace for 14 equal workers).
   - Parallelism at the coarsest independent level only: cases in the runner, windows in `detect`, grid chunks in the CPA table. A worker always runs with jobs=1 and its BLAS threads pinned to 1, so pools never nest and 14 cores never carry 100 threads.
   - The CPA table build vectorised over a chunk of grid points at a time, then chunks across the pool.
   - When changing the CPA build, run the previous serial implementation and the new implementation on the same grid, segments, range and sound speed. Compare the ordered rows, columns, dtypes and values. Check the resulting saved-fit search rankings and scores on Oyster Bay and the eagle cam. For the Oyster Bay speed comparison, time the same build operation on both revisions with a fresh CPA cache path for each run.
   - The scoreboard's stage timings (5.5) record wall time and CPU time per stage, so a missed budget points at a stage.
   - Acceptance: a CPA table for the Oyster Bay box in under 1 min from a cold cache; Tier 1 on the seed set under 3 min with the performance cores busy; the same results, byte for byte, at jobs=1 and jobs=10.
   - Not the GPU. The Metal backends (MLX, PyTorch MPS) have no float64, our timestamps are seconds since 1970 and our coordinates span 100 km, and the CPA table is built once per case-day and cached. The GPU is considered in M4 only if a Tier budget is still missed after this item, and only for the CPA table, curve scoring or the STFT.
2. **Result record v1** (5.5).
3. **A case manifest, a runner, and the four seed cases** from 5.1. Each case's entry carries:
   - exact source identifiers and acquisition details;
   - the start time's source and its uncertainty in seconds, with no default: a case without one can't be built;
   - clip offsets and transformation recipes;
   - the flight-data assets (date, pod and archive asset names), the box and the search parameters;
   - labels, with who checked them;
   - the expected outcome and the case's group and set;
   - the code revision it was built with;
   - links to its raw files' entries in `bench/manifest.json`.

   Changing a case makes a new version of it. A fetch script rebuilds `raw/` on another machine.
4. **Both baselines** at upstream a16b700, and `bench compare`. **Status (2026-11-04): done, both profiles** ([bench-baselines](docs/experiments/2026-11-04-bench-baselines.md)). `bench run --revision a16b700` runs the upstream commit through its own CLI in an exported, hash-verified environment. Saved-fit: a16b700 and the Phase 1 tree agree exactly on all four seed cases (refined 43 m, 877 m, 182 km and 43 m; margins 4.9, 2.5, 10.7 and 4.6 %; 328, 607, 61 and 328 flight pairs), so Phase 1 changed nothing on that path. Raw-audio (`detect`'s top two by score, earlier first, no hand-picked windows), identical at a16b700 and the Phase 1 tree on every case: on Oyster Bay `detect` picks the right two flyovers, but event 2's fitted f0 is 6 % high (the E1 bias), so the true pair ranks 10th of 448 and a pair 77 km away wins by 5.9 %, with and without the 150 Hz high-pass and AAC; on the eagle-cam clip one of the two is the wrong flyover (`detect`'s ranks 2 and 5 where the committed fits are 5 and 13), so the true pair never passes the gates and a pair 54 km away wins by 1.0 %; the moved-box negative lands 92 km out with a 13 % margin. So on raw audio today's pipeline locates neither development recording, for two different reasons: the fit and its gate on Oyster Bay (items 1 and 4), event choice on the eagle cam (items 6 and 7). That is the gap M2 closes.
5. **Tiers 0–2** (5.4).
6. **Sets for the clean recordings** (5.2), written into the case manifest before any of them is searched (decision 2).
7. **Any new cache** (detections, spectrograms) follows the CPA cache's rules: keyed on its inputs' contents and on the hash of the code that produced it (the detector's own source, as hermes does), written atomically and locked. Use `filelock` and a library cache such as `joblib.Memory` or `diskcache` instead of repeating the hand-written pattern.
8. **Gaps in the audio** (S–M). Real recordings have holes: ESID 740 and 710 each lose about 2.5 min twice in the day where a file is missing and the recorder restarted, AudioMoths can be configured to sleep between files (their CONFIG says 55 s on, 5 s off, although these two sites' files are continuous 60 s), and decision 2 puts one of them in calibration and one in evaluation, so the benchmark can't run without this. The spectrogram keeps the recording's timeline: frames inside a gap are marked invalid, never dropped, so audio seconds stay convertible to UTC, and tracks, fits, whitening and scoring skip invalid frames. Acceptance: a synthetic pass with 5 s cut from every minute, the gaps at least 20 s from CPA, fits to the same f0, speed and distance as the uncut one with no bias (the mean shift over noise seeds within 2 standard errors of zero) and bounded scatter (each seed within 4 % of the parameter), and to within one hop in time; a gap over a pass's steepest part gives a weak fit, not a confident one, meaning a score no higher than the uncut score times the share of frames left valid. "Within the fit's spread" was the first wording; the uncut fit's noise spread turned out tighter (0.5 % in distance) than what removing 12 % of the frames does to the distance (1.2 % rms), so the bias-and-scatter form replaced it. A gap carries zero evidence and dilutes the score; renormalising by the valid frames would let a fit on the tails alone look as confident as a full curve.

**Done when:**
- the seed cases have both baselines, with every input and cache hash recorded;
- Tier 1 runs in under 3 min and Tier 2 on the seed set in under 15 min, with the Oyster Bay CPA table built in under 1 min;
- every clean recording has its set;
- the gap test passes, and ESID 740's spectrogram keeps its timeline.

The benchmark then grows alongside Phases 2–4, as they need cases. **If the budget can't be met:** Tier 1 runs fewer cases.

### M2: first usable release

#### Phase 2: event evidence that survives real passes (M–L; research, time-box 2 weeks)

**Goal:** from `detect` output, with no hand-picked windows, event evidence that lets the true flights through on every positive development case without letting wrong pairs win. It depends on Phase 1's Tiers 1–2 and labels.

The experiments run in this order. Each is judged in Tiers 1–2 against labelled events, kept, reverted or deferred by the stop rule below, and recorded in `docs/experiments/`.

1. **Timing convention** (S; E2). This comes first because it is cheap and the measurements so far point at it.
   - **Gate.** Pair on emission-CPA times against the CPA table's `t_emit`, with a looser gate.
   - **Scoring.** Compare like with like: the steepest-fall time of the fitted curve against that of the curve modelled from the actual trajectory.
   - **Measurement.** On every confirmed pass, measure how far the modelled curve's steepest fall is from the geometric CPA. That shows how often a flight isn't straight enough for `t_emit` to stand in.
   **Status (2026-11-04): code landed, development grid promising, runner sweep pending** ([timing-convention](docs/experiments/2026-11-04-timing-convention.md)). `run_search` and `search` take the convention, the steepest-fall gap tolerance and the clock anchor, all defaulting to today's behaviour; one estimator places the steepest fall of fitted and modelled curves alike, and a curve too flat, holed or out of window to place is counted `unplaceable` instead of tested. The measurement answered itself first: at the reference point two of the four development flights put the modelled steepest fall within 0.2 s of `t_emit` and one 18 s off, and Livermore's 40 passes sit a robust 6 s away (6.2), so `t_emit` alone cannot carry a tight gate. An emission gate wide enough for the worst flight (about ±16 s) admits 2.5× today's triples, and the like-for-like check is what brings the count back: on the two development recordings with `detect`'s events, only (gate ±16 s, steepest-fall tolerance 4 s) keeps the true pair at a grid point within 250 m of the reference on both while reaching scoring with about half of today's triples (9,401 against 19,188 on Oyster Bay, 30,245 against 50,682 on the eagle cam); today's heard gate fails Oyster Bay at 250 m and passes only at 600 m. Chosen from 16 cells on two recordings, so a development setting until the Eclipse cases exist. The deciding table comes from the runner on the three positive seed cases at raw-audio, the saved-fit prediction (the committed Oyster Bay brightness fits fail the check, the objective's known tail-weighting bias) being on record before the run.
2. **Model error** (S; E1, E6). Fit the straight-pass model to three kinds of curve: noiseless curves made from the real trajectories of confirmed passes, the same curves with noise and ideal straight passes. That separates model bias, measurement noise and optimiser failure before any fit changes.
   - **Perturbations**, one at a time: f0 drifting through a pass, sound speed (METAR temperature), wind (soundings), trajectory interpolation, the altitude datum, terrain and the whitening floor and window. `local_whiten` subtracts each bin's median over the window, so a tone that sits in one bin for more than half the window is removed, flat asymptotes included, and those carry f0 and speed. That one runs on today's brightness fit, before any track exists. Trajectory interpolation compares today's linear resampling with cubic Hermite using the reported ground speed and track as derivatives (blending to linear over gaps longer than 30 s, as doppler-locate does) and with a smoothing spline, and checks the speed from differentiated positions near a trace's ends, where `np.gradient` gives about half the true value in the first and last samples.
   - **Synthesised waveforms.** Besides noiseless curves, synthesise audio from the propagation delay alone (emitted at t_e, heard at t_e + r/c) and run it through the real STFT. That exercises window smear and the whitening as well as the model, and it is the oracle for item 5.
   - **Livermore first.** The 40 Livermore passes have trajectories and published frequency tracks, in constant and varying speed and height, so they are this experiment's main real data (5.6). Their ridge clock is good to about ±1 s per pass, so every timing comparison on them fits a per-pass shift, and the steepest fall is already known to be a poor landmark there (6.2). dopplerprint reports that a straight-pass fit to the noise-free ADS-B curve misses slant range there by a median 14 %, and by 40–90 % on some passes ([related projects](docs/reference/related-projects.md)). That is a hypothesis to reproduce, not a result.
   - **A check on real fits.** Fit each pass's approach and recede halves separately. A straight, constant-speed pass gives the same f0 and speed from both, so a difference measures model error (a two-estimator comparison of the kind White 1982 recommends).
   - **Heavier models** (turns, acceleration, weather) come only after a measured bias they would remove.
   **Status (2026-11-04): stage 1 done, with the information limit** ([model-error](docs/experiments/2026-11-04-model-error.md)). The Cramér–Rao bound of the straight-pass curve fixes one pass's slant range to a median 4 % (73 m) on the 29 primary Livermore passes and 1.6 % (76 m) on the four development events, so information is not what limits 1 km. (The package-grid version of that bound, built from Harris's frame correlation, first used a truncated correlation whose matrix was not positive semi-definite; recomputed from the full correlation it is 3.4–4.0 % (63–74 m) depending on whether the frames' correlation is taken as c or c², provisional until the covariance is measured from synthesised waveforms through the tracker; the version built from each pass's own measured ridge noise, a median 3.9 %, stands.) A single noisy fit's spread is about 4 % in slant range (75 m), and the model error below is measured against that. Model error is: the straight-pass fit of the noiseless trajectory curve misses slant range by a median 15.6 % (229 m, about 3× the bound, over 1 km on 5 of 40 passes) and speed by 3 %, as much as the real ridges miss (15.0 % and 4.8 %); the optimiser is exact on ideal curves and noise moves the fit by a fraction of a percent, at the bound. Of the perturbations, only f0 drift enters (0.5 % over a pass moves speed by more than the fit's spread on 21 of 29 passes, and the approach-against-recede halves allow drifts of that size but can't separate them from model error); sound speed, interpolation, the geoid datum and the recorder height stay below the spread, wind moves f0 only, and fitting the full ±150 s window instead of the tone's span makes the miss worse (35.6 %), so dopplerprint's 14 % is reproduced on the ridge span only. One pass fixes a distance from a track, not a position, and its error is model error: a 1 km answer has to come from several events per recording (item 7) and a model or weighting that copes with passes that aren't straight; the one-parameter candidates are a linear f0 drift and a kinematic term, to be tested on the trajectory curves against the bound. Stage 2 (`fit_event` on rendered curves and the real audio) and Alaska are to come.
3. **Frequency track** (M; E3). One track per event:
   - times, and frequencies refined below the bin width (quadratic interpolation, Quinn's estimators or Candan's three-sample estimator), measured on the original STFT, not the whitened image;
   - an amplitude or quality per point, and valid and missing samples;
   - explicit start, end and gaps;
   - links between the harmonics of one pass.

   Start from `tracks.ridge()`, a Viterbi path through the spectrogram that today must span the whole window, restricted to spectral peaks, and make it local, so that a path may begin and end at any frame: add an explicit "off" state with birth and death penalties (hermes's form), which is equivalent to dopplerprint's clamp of the accumulated score at zero but keeps the start and end of each path explicit. Ridge extraction joins unrelated components when tones come and go, and the literature offers no stopping rule (6.3); the off state is one. It needs an unclipped, zero-mean image, and `local_whiten` clips at zero, so on today's image a path would never end. Segment cuts (a weak run, a rise, a hop) are untested heuristics and get their own rules and tests, as do crossings. Frequency error, false bridges, fragmentation and missed tails are measured on labelled events. The comparator is ssqueezepy's `extract_ridges`, an implementation of Iatsenko's method that installs with pip; it runs in Tier 1 beside ours, and an adaptive tracker of our own is written only if track errors turn out to limit the fits.

   **Status (2026-11-04): built as `freqtrack.py`, experimental, criterion not met** ([freqtrack](docs/experiments/2026-11-04-freqtrack.md)). On the 29 good Livermore passes the off-state tracker has a lower frequency error than `ridge()` (0.45 % against 0.48 %) and 2.8× fewer false bridges (13 against 36), and on the 11 manoeuvring passes it holds 0.84 % where `ridge()` wanders to 15 %, but it covers only half of each pass: a per-frame threshold set for one false track per hour on noise ends a track wherever a real tone dips under it, and lowering the threshold with a higher birth cost (one counted retune) traded fragments for bridges. Hysteresis through costs alone has a floor near the noise peak, about 8 dB, so the next step is hysteresis in states (a stricter birth level than continuation level), after item 5's window, since the rise and hop cuts fire where the 2.048 s window smears the steep part. `ridge()` remains the fitting path's tracker until the criterion is met. ssqueezepy's `extract_ridges` gave a 14 % median error and 0.39 coverage in an oracle band on the same passes, locking onto other lines: the no-stopping-rule failure 6.3 predicted.
   - **Whitened for finding, original for measuring.** Whitening shifts a peak that sits near a floor it has partly subtracted; dopplerprint measured 0.4–0.9 bin on slow passes. Tracks are found on the whitened image and each frame's frequency is then measured on the original STFT.
4. **Least-squares fit** (M; E1, E3). Fit the track with f(t) = α + β·z(t; τ_c, s) (6.1). At each (τ_c, s), α and β are solved in closed form, so the search is over those two parameters only (variable projection).
   - **Losses.** Start with ordinary least squares, then weight points by amplitude, then try a robust loss if outliers call for one.
   - **Safeguards:**
     - a stable linear solve, with a check that z varies enough over the track, since flat and partial tracks make α and β inseparable;
     - physical bounds on speed and distance;
     - a grid of starts over (τ_c, s), since variable projection doesn't remove local optima;
     - convergence and conditioning diagnostics in the result record;
     - a synthetic test that the reduced fit's optimum matches the full four-parameter fit.
   - **Comparison.** Compare it with today's brightness and contrast fits on the same cases.
   **Status (2026-11-04): built as `tracks.fit_track`, criterion not met, deferred until a track meets item 3's criterion** ([least-squares-fit](docs/experiments/2026-11-04-least-squares-fit.md)). The estimator is right: it recovers noiseless passes exactly, its reduced optimum matches the full four-parameter fit, and D's independent implementation puts the straight-pass fit at the Cramér–Rao bound. On `ridge()`'s tracks of the 29 primary Livermore passes the amplitude-weighted fit beats both objectives on speed (6.7 % against 9.8 %) and slant range (15.2 % against 18.6 %) and misses only on f0 (1.34 % against 1.13 %); the event-2 timing criterion fails on both development recordings (+17 s and +28 s against the contrast fit's −9 s and +6 s). Every failure traces to the track, not the fit: `ridge()` follows another line inside the band on two primary passes (rising curves, negative speed) and in the event-2 windows, and on the 11 manoeuvring passes it wanders off (range error 78 % against 9 %). The one retune was not spent; the positive-speed bound the item lists was found missing and goes in for the re-run, counted. `fit_track` stays library code until item 3's tracker passes, then the same comparison runs with the criterion unchanged.
5. **Window length** (S). The 2.048 s window smears the steepest part of a typical pass. A window matched to a sweep rate g is about 1/√g, which is 0.9 s for Oyster Bay's event 2 (6.1). Compare:
   - 2.048 s against about 1 s and 0.5 s;
   - a two-window version, short near CPA and long in the tails, where a longer window measures the steady tone far better.

   Zero padding only interpolates the spectrum; resolution comes from the window length.
6. **Harmonics and extent** (S–M).
   - Compare harmonic assignments, allow for a missing fundamental, and merge the harmonics of one pass into one event. Their evidence is correlated, so they aren't separate votes. The fundamental is the greatest common divisor of the orders present, so lines at 2, 4 and 6 read as 1, 2 and 3 (hermes).
   - **Explain away.** Take detections strongest first. One whose curve mostly runs through cells an accepted detection already claims is a harmonic, a duplicate or a borrowed ridge: drop it, or rescore it on the unclaimed cells only (doppler-locate). This is also what stops a candidate flight from borrowing another source's ridge (unheard).
   - **Controls per event.** Besides the linear chirp below, compare each curve's support with the same curve shifted in frequency and with the curve reversed in time (echotrace). These are diagnostics first; they get statistical meaning only from the threshold curve.
   - Mask the unreliable stretches of a track instead of cropping to a fixed width ([rewindow](docs/experiments/2026-11-03-rewindow.md)).
   - Set `detect`'s threshold here, as a curve of detections against false alarms per audio hour on the development background recordings: the Essex ones, AeroSonicDB's six continuous hours with aircraft marked every 5 s, and DataSEC's helicopter, machinery and vehicle clips as confusers (E4, E5). AeroSonicDB's 467 turbofan clips against its 150 propeller clips are the labelled set for E5, jets scoring like props. One input to that curve: the ideal-curve score against the best linear chirp on the same support, since smooth clutter beats a stationary-tone null (echolocate). Short genuine passes look linear too, so it is a feature, never a gate.
7. **Joint hypotheses instead of gates** (M; E1). Replace the independent speed, distance, time and f0 gates with each event's own hypotheses: its best few local optima, each with the joint region its data supports.
   - **Why joint.** Time and f0 trade off along the curve's slope, and distance follows speed (6.1). Marginal ranges combined freely admit combinations the event never supported.
   - **Partial passes.** When the tails are faint, speed and distance are each ill-determined but k = v²/d = c·|f′|max/f0 is pinned by the steep middle. Parametrise such a hypothesis by k and a wide speed range; each candidate flight's own ground speed then gives the distance it implies, d = v²/k (audio-flyover-geolocation). Report the speed–distance correlation of every fit.
   - **Profiles.** Derive the regions from profiles, re-optimising the other parameters, and call them sensitivity ranges until the objective is a calibrated likelihood.
   - **Weak identification.** A flat or one-sided profile marks a weakly identified parameter. A poorly fixed distance widens the distance constraint but keeps the timing evidence. A range that ends where the optimiser hit a bound isn't a range.
   - **Overlapping frames.** Consecutive STFT frames share 88 % of their samples, so counting them as independent would understate the spread roughly threefold.

8. **Emission-time resampling** (M; E1, E3). Today's scorer samples brightness along a predicted curve in a spectrogram that was computed first, so once a steep sweep has spread over several bins inside one window, drawing the right curve can't gather that energy back. The alternative, from the flyover-noise literature (Kelly & Wilson 1993; Gao et al. 2021; Ramseier & Pieren 2024; 6.3), is to undo the Doppler shift in the waveform for each candidate: for an observer x, a recording start T and emission times u on a uniform grid, evaluate the recording at u + |aircraft(u) − x|/c − T with band-limited interpolation, so that a steady emitted tone from the right geometry becomes a nearly stationary line at an unknown frequency; then take spectra of short blocks of the corrected signal and pool their power over the harmonics. Proposed on an outside reviewer's advice (2026-11-04); not started.
   - **The experiment**, on the confirmed Oyster Bay events with the windows frozen and a candidate set holding the reference location and the strongest spatially distinct wrong alternatives, all scorers given the same candidates, audio support, usable band and search freedom: (1) today's curve score with a wider source-frequency search and a clock chosen jointly across the two events (event 2's fitted tone is 6 % high, so this control matters); (2) a direct least-squares fit of the tracked frequencies to each actual trajectory, solving each aircraft's rest frequency in closed form at each trial location and clock (f0 = Σ wᵢDᵢfᵢ / Σ wᵢDᵢ², echolocate's form); (3) the warp with short-block harmonic power, a constant tone within each block. Report the reference's rank, its margin over the strongest spatially distinct wrong answer, the refined error and the runtime. The same three on the eagle cam once its events are chosen jointly (B's event-pairs test).
   - **Whitening.** `local_whiten` subtracts each bin's median over time. After a successful warp the line is stationary, so that whitener erases exactly what the warp made; the warped scorer needs a background estimated across frequency at each instant (Ramseier & Pieren's eq. 11), and the unwarped control gets the same estimate so the two changes are separable.
   - **What makes it lose**, to be controlled for: an unconstrained source-frequency history explains any geometry, so the tone is constant within a block with bounded drift between blocks, and the gain from extra drift freedom is compared on true and wrong trajectories; reflected paths warp differently from the direct one (Fatela et al. 2024); local stationary tones score well for geometries with little predicted Doppler, so the unwarped control stays; and a trajectory's validity mask gates both the input and the interpolator's support.
   - **Criterion**, fixed now: the warp is adopted only if, on the development events, it ranks the reference first with a larger margin over the strongest wrong alternative than control (1) does, within the Tier 2 budget, and the gain survives the broader-tone, joint-clock control. If all three scorers agree over kilometres, that is the ambiguity to report, and the answer is a pass on another heading, not another scorer.
   - **Band.** Run the comparison a second time on development audio band-limited to the phone's 40–450 Hz, the home recorder's usable band, so the Seattle session's mode is exercised before its data exists; Seattle itself stays evaluation.

**Each experiment has its own criterion**, fixed before it runs and measured in Tiers 1–2 on labelled events. A better tracker is kept for better tracks, whether or not the downstream gates are fixed yet:
- timing convention: the true pair survives the pairing gate on every positive case at no wider a gate than today's;
- model error: each bias is measured, and a perturbation enters the model only if it moves a fitted parameter by more than the fit's own spread;
- frequency track: lower frequency error against the trajectory-derived reference on labelled events, and no more false bridges or fragments than `ridge()` makes today;
- least-squares fit: smaller f0, speed and timing errors than the brightness and contrast fits on the same events, and the reduced fit's optimum matching the full fit on the synthetic cases;
- window length: the same errors, on the same events;
- harmonics and extent: fewer duplicate events per pass, and a threshold curve that reaches the chosen false-alarm rate;
- joint hypotheses: the true flights inside every event's hypotheses on every positive case, with no more hypotheses per event than today's gates admit.
- emission-time resampling: the reference ranked first with a larger margin than the broader-tone, joint-clock curve score on the same candidates, within the Tier 2 budget.

An experiment is kept if it meets its criterion, reverted if it doesn't, and deferred if two recordings can't decide it.

**Phase exit.** The phase is done when all of these hold on the development cases and the synthetic failure matrix:
- the true flights pass the filters on every positive case, using `detect` output with no hand-picked windows;
- on Oyster Bay from raw audio, the true pair ranks first, with the refined peak within the practical resolution of the truth;
- Tier 2 stays within its time budget (the candidate count is not a criterion: the baseline it would be measured against drops the truth);
- no wrong pair beats the true one where it didn't before, and the top candidate's location error doesn't grow;
- partial and degenerate passes give an explicit weak or unusable fit, not a confident one.

These thresholds are provisional, and they are fixed before the experiments run. Every knob tuned on the development cases is counted, because tuning many knobs on two recordings overfits them.

**Stop rule.** If the time box ends before the exit criteria hold, the fallback is the kept experiments as they stand, or else the ±10 s / ±12 % gates ([gate-tolerances](docs/experiments/2026-11-03-gate-tolerances.md)). Under the fallback, raw-audio localisation is documented as a known limitation, the verdict abstains more and E1 stays open.

#### Phase 3: `dopplertrack locate` (M–L; step A can start alongside Phase 2)

**Step A: a thin `locate` with explicit failures.** One command over today's pieces:
1. audio → spectrogram → `detect` → usability check (S6);
2. flight data (with margin, cached) → CPA table (cached);
3. search with one automatically chosen pair of adjacent detected flyovers. Tier 2 checks it with and without the silence filter, which is off by default in `locate` (S4);
4. refine the winner with the other flyovers;
5. verdict and `result.json`.

Step A refines only the winner, so it never rules out a competing mode. Its verdict is capped at "ambiguous": it reports the candidates and its reasons, and "located" waits for step B's competitor search.

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

  Implement it as a one-to-one assignment with SciPy's `linear_sum_assignment` over a cost matrix padded with dummy "unmatched" rows and columns at the fixed cost (the pattern Stone-Soup uses); a per-event argmin under a shared hypothesis is not an assignment. Every candidate is scored on the same detections with the same normalisation: each event's score in units of the spread of its own wrong guesses, the median and MAD of the (shift, f0) sweep `search` already runs for every candidate (unheard's form; S2). Noise alone then scores a few units, because the best of many guesses wins, which is one more reason confidence is computed after selection. The record shows how much support comes from the proposing pair and how much from the other flyovers.
- **One clock, fitted to every event** (S3). The audio-to-UTC offset is optimised over all assigned events jointly.
  - **Drift.** On long recordings, test a bounded clock drift and add it only if it improves consistency. Sample clocks drift by tens of ppm, about 1 s in 12 h at 20 ppm.
  - **Edits.** A flyover that fits only with a different clock suggests an edit, as a diagnostic.
- **Final score on the actual trajectory**, with propagation delay and the shared clock. Each event's f0 is solved conditionally: as a 1-D sweep, or in closed form for a least-squares track.
- **Several modes through refinement.** Keep separated location-and-clock modes, including several from the same flight pair, and refine each before choosing.
  - Two geometries are degenerate, and `locate` checks for both (6.1): a single flight can't tell which side of its track the microphone is on, and parallel flights at the same speed leave the position along the tracks open.
  - More flyovers on other headings resolve both.
  - Each mode's record gives the crossing angle between the matched flights' tracks and the axis and length of the score plateau around it. A low crossing angle, or a plateau stretched along the tracks, marks an along-track ambiguity (audio-flyover-geolocation).
- **Edges.** A candidate whose support or region reaches the box edge, or the edge of the flight data's coverage, is flagged.
- **Confidence on the final output.** Trying many pairs and keeping the best inflates the winner's score, so confidence is computed after all the pair selection and re-ranking, never per pair.

**Done when**, from audio, date and box alone, two things hold. First, on both development recordings the top-ranked mode holds the true flight pair, with its refined peak within the practical resolution of the truth. Second, each failure case gives its expected outcome with no confident wrong answer:
- no usable flyovers;
- incomplete flight data;
- a recording crossing UTC midnight;
- the moved box;
- a source aircraft removed from the flight data, with the traffic around it kept.

Motion and edit checks are diagnostics and not part of this.

**If step B slips:** release step A's single-pair `locate`, whose verdicts are "ambiguous" or "insufficient evidence" only, and say so in the release's README (Phase 6).

#### Phase 4, machinery: verdicts and abstention (L; time-box 2 weeks)

- **Modes first.** Two candidates are distinct modes when their locations are farther apart than the practical resolution (decision 1), or their clocks differ by more than a pass can resolve.
  - "Ambiguous" then means a distinct mode is still plausible, and no rule depends on the radius being estimated.
  - A single radius is reported only when one mode sums up the result; otherwise every region is listed.
- **Region construction**, an experiment of its own, since the region decides what can be called "located". Three constructions, compared on the calibration groups:
  - a sensitivity region: the contour around the refined peak inside which the final score stays within a fixed fraction of the peak, with the clock re-optimised at every point and the flight assignment held fixed;
  - the pass-level bootstrap region from the feature below, which carries measurement noise but not model error;
  - a radius calibrated by split conformal on the calibration groups, the only one with stated coverage, and only on groups it wasn't tuned on.

  Alternative assignments give separate modes, never a wider region. Model error enters before the search, through each event's hypothesis: a fit whose approach and recede halves disagree (Phase 2 item 2) widens its own hypothesis, and the region inherits that. Until a construction is calibrated, the record calls its region a sensitivity region, and coverage is stated only for the conformal radius.
- **A starting feature.** The time-gated extra-flyover consistency is the strongest lead so far ([extra-consistency](docs/experiments/2026-11-03-extra-consistency.md)). Its ±15 s gate is a development hypothesis until it holds on recordings it wasn't chosen on.
- **Other candidate features:**
  - the margin over the strongest distinct competing mode, from any pair;
  - the number of extra flyovers explained, and their scores;
  - close passes that no flyover explains;
  - peak width after refinement;
  - the leave-one-pass-out shift: refine again with each assigned flyover removed, and record the largest move of the mode and whether it survives (aircraft-doppler);
  - a radius from resampling whole passes, grouped by aircraft, rather than ridge points, since the points of one pass are not independent;
  - event fit quality;
  - clock consistency.
- **Thresholds.** Fit them on the calibration groups' positives against their negatives, never on the evaluation group. A region that is unavailable or wider than the resolution means no "located".
- **Whole-process evaluation.** Each evaluated case runs pair selection, refinement and abstention; nothing is scored per pair.
- **Done when** the verdict and region come out of `locate`, labelled experimental, and the benchmark reports confident-wrong and abstention rates for each group.
- **If the time box runs out** before any features separate the calibration positives from the negatives:
  - `locate` uses conservative fixed rules instead: "located" only for a single surviving mode with at least one extra flyover explained within ±15 s and a region inside the resolution;
  - the region is reported as unavailable otherwise;
  - that rule needs a third flyover, so under it a recording with two flyovers, or one flyover with a known start time, is never "located", only "ambiguous". Section 1 promises those cases, so the release's README lists this as a limit of the release, not of the method (Phase 6).

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

A README covering install (including ffmpeg), requirements, limits and how to read the verdict, including what "experimental" means. Release in the fork, and send upstream PRs as the author accepts them.

**Acceptance test**, run before each release:
- install the built package in a clean environment on macOS, and on Linux in a container, run the quickstart, and check its expected output. GitHub CI is set up for this only when a release warrants it;
- a clear diagnostic when ffmpeg is missing or too old;
- progress reporting, and resource estimates (download size, CPA table size, time) before the long stages, with a disk-space check before writing;
- cancellation at any point, and a re-run that resumes from completed cached stages;
- defined behaviour for an unavailable archive, a network failure or a partial download: retry a fixed number of times, then stop with an error;
- the README's stated limits match the shipped fallbacks: no "located" without step B's competitor search, and none for a two-flyover or single-flyover recording while Phase 4's fixed rules are in force.

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
- the GPU, through MLX or PyTorch's Metal backend, for the CPA table, curve scoring or the STFT, only if a Tier budget is still missed after Phase 1's parallelism;
- multipath delays, microphone arrays, and advanced time-frequency methods, each if a measured bottleneck points to it.

## 5. Measuring progress

The measuring stick has to be trustworthy before it gets big: caches that can't go stale, labels checked against the audio, and evaluation data kept apart from the data we tune on.

### 5.1 Cases

**Seed set**, one for each kind of outcome:

| Case | Expected outcome | What it tests |
|---|---|---|
| Oyster Bay, 1 h | located | the reference result |
| An eagle-cam clip of 1–2 h holding its two search events | located | another site, geometry and noise level |
| Oyster Bay audio with the box moved 150 km, over land with at least as much propeller traffic | not located | the truth is outside the box by construction, so any confident answer is wrong. No 150 km move over land matches Oyster Bay's traffic (158 prop passes within 12 km that day); the box 150 km WSW has about twice as many, which gives the search more wrong pairs to be tempted by, and the box 150 km north about a third, kept as a second, easier negative |
| A degraded copy of one of these, e.g. high-passed at 150 Hz and encoded as low-bitrate AAC | located or abstain | abstaining passes; a confident wrong answer fails |

**Growth**, cheapest first:
1. **More eagle-cam clips**: the 12 h archive cut into 1–2 h clips, which gives roughly 6–12 positive cases with different geometry. They share a site, a microphone and a day, so they count as one group.
2. **Augmented copies**, made with ffmpeg: low-bitrate AAC, Opus and MP3; high-pass at 100 and 150 Hz; noise suppression; added wind noise; trims to 30 and 15 min; a 30 s cut between two flyovers. Expected outcome: located or abstain.
3. **Negative controls**, expected not to be located:
   - the right audio with another day's flight data;
   - the right day with the box moved 150 km;
   - the right day and box with one confirmed source aircraft removed and the surrounding traffic kept, for each confirmed flyover in turn, and once with both search events' flights removed. This is the substitution L2 makes likely: a wrong flight standing in for an audible one that has no ADS-B. Expected: abstain, or locate from the remaining flyovers; a confident answer from a substituted flight fails. Mask the flight's column in the CPA table rather than rebuilding it per variant;
   - stretches with no flyovers, confirmed in the spectrogram;
   - real background recordings with other tonal sources and no prop passes: the three Essex recordings (jets), ESID 937 (no prop within 20 km all day), and the stretches of AeroSonicDB's six soundscape hours marked as having no aircraft. These also give `detect`'s false alarms per audio hour.
4. **Stress tests**, inspected rather than scored as plain negatives:
   - time-reversed audio. Its curves mostly rise, which turns, climbs and power changes can also produce, so it isn't a guaranteed negative;
   - incomplete flight data (an hour of traces removed);
   - a recording crossing UTC midnight: ESID 375 and 937 do;
   - a true location within a few km of the box edge;
   - the three A2O soundscapes, whose published coordinates are shifted by up to about 270 m and whose aircraft are unlabelled: a coarse check of the 1 km verdict at unseen sites in other airspace, once their days' flight data is fetched and `site_traffic.py` confirms propeller passes. Never calibration or evaluation (decided 2026-11-04: the Townsville filename GPS fix stays the unverified working position, and no A2O site is asked for its true coordinates unless one is ever to count).
5. **Independent recordings** (5.6), the only source of calibration and evaluation data.

**Synthetic failure matrix.** Small cases that run in seconds as Tier 0–1 tests. Each phase adds the ones it needs.
- **For the fits (Phase 2):**
  - a partial pass, with its CPA outside the recording or masked;
  - a nearly flat curve, from a distant or slow pass;
  - a crossing tone;
  - a missing fundamental;
  - a harmonic mistaken for the fundamental;
  - a turning or descending pass made from a real trace;
  - curves rendered from real ADS-B segments onto real quiet stretches of the background recordings, at controlled levels, so detection recall has positives with known truth (overpass's training trick, used here for the threshold curve only).
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
1. **Acoustic event.** Is a tone or flyover present in the window? The classes are clear, uncertain, overlapping (two flyovers or a crossing tone), masked (wind, birds, an edit) and absent. Labelled from the spectrogram.
2. **Flight association.** Which ADS-B pass made it, if any. "Unmatched" is a label on both sides (V2).
3. **Trajectory-derived reference.** What the observer should hear, from the curve modelled on the actual trajectory: its steepest-fall and heard-CPA times, and the slant range and speed at CPA. It is a prediction from the trace under the assumptions Phase 2 item 2 tests (interpolation, sound speed, wind, altitude datum), not an observation, which is why it isn't called truth.
   - This is not the parameters of a straight pass, which don't exist for a turning, climbing or descending aircraft. The propeller's rest frequency is never observed directly.
   - A pass whose curve falls fastest far from its geometric CPA is flagged as not straight.

Steps:
- **Annotate whole clips blind, first.** Before any proposal, label layer 1 across a few complete short clips, say 10–20 min from each development recording and from one Eclipse site, with no ADS-B in view. Windows proposed from passes can't show what the passes miss, so these clips are the only basis for detection precision, and they catch the events with no trace that V2 warns about.
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
- **events**: each detection's fit, harmonic, fit diagnostics and assignment to a flight or to "unmatched";
- **candidates**: location, flight pair, clock and drift, score per event and the mode each one belongs to;
- **the funnel**: how many hypotheses each filter removed, how many went unevaluated because a budget was hit, and for benchmark cases whether the true one survived;
- **the verdict**: its reasons, and the uncertainty region with the method and version that made it, or why there is none;
- **data limitations**: flight-data coverage over the recording and the box, skipped traces, possible edits;
- **execution errors**, kept apart from the verdict.

**The scoreboard.** A benchmark run collects the records into one `results.json` in its own run folder, `$DOPPLERTRACK_DATA/runs/<date>-bench-<commit>-<tier>/`. It reports by case and by group:
- the expected outcome, and whether it was met;
- **detection**: recall on confirmed events, and false alarms per audio hour on background recordings, as a curve over thresholds;
- **association**: the share of confirmed events assigned to the right flight;
- **fits**: errors against the layer-3 reference by label class, and the known-point result;
- **the funnel**: candidate counts after each filter, and where the true hypothesis dropped out;
- **search**: the true pair's rank, the margin, and the location error of the top and refined candidates as quantiles over cases, always beside the error of the box centre, the answer that uses no audio at all;
- **verdicts**:
  - the share of positive cases located;
  - the confident-wrong rate among located answers;
  - the abstention rate;
  - region coverage, always next to region size;
- **stage timings**.

A tool that always abstains has no confident wrong answers, so the share of positive cases located is a target of its own.

The runner writes each case's `result.json` and its hash before it reads any reference coordinate, and the comparison step checks the hash. A result that changed after the truth was visible doesn't count.

`bench compare <a> <b>` prints the difference between two runs. There are two baselines, both at upstream a16b700:
- **saved-fit**: the event fits committed in `docs/results/`. It isolates search and physics.
- **raw-audio**: `detect` output with no hand-picked windows. It is what a user gets.

A fitting change shows only in the raw-audio numbers; a search or scoring change is judged on both.

### 5.6 Independent recordings

The evaluation set is what limits M3, and collecting it takes calendar time rather than engineering, so it starts now.

**A recording counts if it has:**
- the microphone's location to about ±10 m (a phone's GPS fix or a known point), and its height above the ground;
- the start time in UTC to the second, from a network-synced clock or a time chime, and no pauses except at known times. An AudioMoth configured to sleep between files is fine once the spectrogram handles gaps, as long as the file names carry the clock. For a livestream, record the HLS playlist's program-date-time tag and segment durations alongside the audio, and keep the first segment's stamp as the clock evidence;
- the original file, not a re-encode, with the device, app and settings noted. Voice processing, noise suppression and bass cut-off should be off where possible;
- no edits, or each one noted;
- adsb.lol coverage of the place and day, checked with `tools/data/site_traffic.py`, with at least two prop passes expected within about 6 km;
- a site and session ID, for the groups.

**Variety matters more than volume**: new sites, devices, traffic levels (quiet airspace especially) and pass geometries (crossing tracks, not one airway).

**Where to look** ([datasets.md](docs/reference/datasets.md) records every search so far, the leads not yet taken and the sources rejected):
- public livestream archives with published locations;
- long field recordings with location and time, such as Eclipse Soundscapes and xeno-canto;
- your own controlled recordings. These are the only source of moving, edited and phone-processed cases, which the motion and edit diagnostics (L4, S6) need for testing. A local ADS-B receiver at the session (an RTL-SDR running readsb, with planefence logging passes) records aircraft that adsb.lol's volunteers may have missed, which is the only direct measurement of L2 available to us.

**On disk now:**

| Source | What it is | Use |
|---|---|---|
| Eclipse Soundscapes ESID 375, 740, 710 | AudioMoths with clocks set by a time chime, 2024-04-07; 6, 7 and 19 prop passes within 12 km | calibration or evaluation (decision 2). 740 and 710 are 1,437 one-minute files each, continuous across the seams despite a CONFIG that says 55 s on and 5 s off, with two missing-file holes of about 2.5 min per site and a restart after each, so they need the gap-aware spectrogram (Phase 1 item 8) first |
| Eclipse ESID 937 | about 25 h from 05:40 UTC on 2024-04-07, with no prop pass within 20 km that day | evaluation's negative, which must abstain, once 04-08's flight data is fetched (decision 2, amended 2026-11-04) |
| xeno-canto XC979185 | one prop pass, start time known to the minute | a single-flyover case |
| xeno-canto XC990819, XC990820, XC986433 | Essex, jets only | development: background negatives for `detect`'s threshold; the first two are one group |
| Seattle (planned) | your recordings, several devices at one spot; and a continuous band-limited recorder at a home in Seattle, about 70 prop passes a day within 6 km, being built in a separate project | one group per session: it tests devices, not new sites. The home recorder is one site, so one group however many days it runs: evaluation (decided 2026-11-04), so its audio is never opened during Phase 2 tuning. Its audio stays out of git |
| Lorain Lighthouse cam, YouTube `my6GvU6lG0U` | a fixed 24/7 cam with audio, 2.6 h archived from 2026-06-15; position from aerial imagery, clock from YouTube's release time with a 10.4 s offset measured by another project | development (decided 2026-11-04) while its clock rests on YouTube's release time: a real livestream case, with 5 prop passes within 12 km during it and 2 within 6 km. A later Lorain session recorded live with HLS program-date-time meets this checklist and would become a calibration or evaluation group |
| Alaska seismic nodes (Seppi, Tape & Fee 2025) | 303 surveyed GPS-timed nodes, 500 samples/s, 2019; 20,313 crossings of 1,216 flights within 2 km with their CPA parameters, and the authors' 1,987 fitted crossings, whose `DPZ` windows are on disk | development, one group (decided 2026-11-04): Phase 2 item 2's fits and tracks beside Livermore, and the per-type tones as an f0 prior. A geophone with a 250 Hz Nyquist and only CPA parameters from Flightradar24, so never a `locate` case, calibration or evaluation |
| Sussex/Gatwick sample | jet clips named by aircraft and second, Gatwick, 2026-07-03, no microphone coordinates | development, one group (decided 2026-11-04): jet confusers for E5, like the Essex recordings |
| AeroLoop | Adelaide aircraft and negative clips with labels | development (decided 2026-11-04): detection labels only, and kept out of the threshold curve until its overlap with AeroSonicDB is checked; if they share sources they are one group and are never split, as with DataSED and DataSEC |
| Livermore (Pathak 2026) | 40 phone recordings of one light-aircraft pass each, May 2026, one site: WAV, the published frequency track, the ADS-B track as KML and a results table. The microphone position is not published; the author's recorder point was recovered from the published offsets to under a metre, with the three 2026-05-09 passes at a second site 6.6 km away ([livermore-audit](docs/experiments/2026-11-04-livermore-audit.md)) | development for Phase 2's fits and tracks, as one group. Single passes, so not a `locate` case, and three other projects have tuned on it ([related projects](docs/reference/related-projects.md)), so never evaluation. Every WAV is the published ridge ±5.00 s, and the ridge clock agrees with ADS-B to about ±1 s per pass with no common offset beyond half a second, so f0, speed and slant range can be fitted directly, while anything timed below a second needs a fitted per-pass time shift |
| AeroSonicDB, DataSED, DataSEC | labelled aircraft and environmental clips, and AeroSonicDB's six continuous hours with aircraft marked every 5 s; positions deliberately shifted or absent | detection only, in Phase 2 item 6: the false-alarm curve and the jet confusers (E4, E5). Not location truth |
| A2O, three soundscapes | Australian Acoustic Observatory recordings, about 6 h, with coordinates shifted by up to about 270 m and no aircraft labels | a 5.1 stress test of the 1 km verdict at unseen sites, once their flight data is fetched. Never calibration or evaluation |

ESID 375 and 937 both run past UTC midnight into 2024-04-08 (to 02:31 and 06:32), so they also test the midnight case, and they need that day's flight data; 740 and 710 cross it by 59 s and 20 s, so a pass in their last minute needs it too.

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

From the first benchmark run of the seed cases:
- **Margin alone can't carry a verdict.** With Oyster Bay's audio and the box moved 150 km north, the search still returns a top pair, 148 km from the truth, with a 3.2 % margin over the runner-up; the eagle cam's true positive wins by 2.5 %. Moved 150 km west-south-west into a box with twice the traffic, the wrong answer is 182 km out and wins by 10.7 %, twice Oyster Bay's true positive (4.9 %). A busier box gives a more confident wrong answer, so Phase 4's features have to come from elsewhere (extra-flyover consistency, competing modes, fit quality), with the margin at most one input ([bench-seed-cases](docs/experiments/2026-11-04-bench-seed-cases.md)).
- **The seed cases reproduce section 2.** The Oyster Bay runner result is exact on ranks and coordinates (1st of 328, 122.9 m, refined 43.3 m, 4.94 % margin); scores differ from the committed tables in the fourth significant figure because Phase 0's evidence masks changed a handful of triples (40,889 against 40,885). The 1.5 h eagle-cam clip gives the same result as the full 12 h recording.
- **Phase 1 is a no-op on the saved-fit path.** Upstream a16b700, run through its own CLI in a hash-verified export, and the Phase 1 tree give the same refined positions, margins and flight-pair counts on all four seed cases (run folders `2026-11-04-bench-a16b700-saved-fit-t2` and `2026-11-04-bench-5314396-saved-fit-t2`). On raw audio both fail on both recordings, in two ways: on Oyster Bay `detect` finds the right flyovers and the biased event-2 fit drops the true pair to 10th of 448; on the eagle cam `detect`'s second-best event is another flyover and the true pair never enters. The saved-fit path succeeds where raw audio fails, which is the gap M2 has to close.

On the Livermore corpus (one group, 40 single passes, development only):
- **Information is not the limit; model error is.** One pass's Doppler curve carries enough information to fix its slant range to about 50–500 m at 0.3–6 km (a median 63–74 m by Cramér–Rao, on the package's grid with the full Hann frame correlation, and the same from each pass's own measured ridge noise), and the optimiser recovers ideal curves exactly, but the straight-pass model applied to the real trajectories misses slant range by a median 229 m, about 3× the bound, and by over 1 km on 5 of 40 passes; the real ridges miss by the same amount. Noise, sound speed, interpolation, the geoid and the recorder height are all below the fit's spread; an f0 drift of 0.5 % is not ([model-error](docs/experiments/2026-11-04-model-error.md)).
- **A longer fit window is worse on real passes.** Fitting ±150 s instead of the tone's own span raises the median slant-range miss from 15.6 % to 35.6 %, because the aircraft turn and change height over five minutes; the fit window stays with the observed tone (same record).
- **The textbook covariance isn't the spread.** On the real ridges the classical form is 0.86–0.90 of the bootstrap spread and a Newey–West sandwich 1.3–1.6× it, both by accident of the misfit it counts as noise (White 1982 §3); the bootstrap, or the bound for the straight part, is what to report (same record).
- **The steepest fall is a poor timing landmark on real passes.** On the curves modelled from the actual trajectories, the steepest fall sits a robust 6 s from the emission CPA, and ridge noise widens the ridge-against-model difference to 6.7 s; many passes turn, or are far enough (4–6 km) that the slope peak is too broad to place. A whole-curve least-squares fit with a per-pass time shift is the timing measurement that works there; it puts the ridge clock within about ±1 s of ADS-B per pass ([livermore-audit](docs/experiments/2026-11-04-livermore-audit.md)). This is the measurement Phase 2 item 1 asked for, and it means `t_emit` can stand in for the steepest fall only to within several seconds on such passes.
- **The 11 passes whose trajectory curve fits the published ridge worst** (RMS over 1.6 % of f0: R37, R41, R44, R15, R36, R07, R21, R16, R03, R50, R51) are flagged, not dropped. They are where trajectory and ridge disagree most, so they are the model-error candidates for Phase 2 item 2; R50 is a jet at 5 km.
- **Interpolation matters across sparse tracks.** The KML has 8–16 s gaps across CPA; cubic interpolation can overshoot there (one pass moved 9.7 s in fitted clock between PCHIP and linear), so Phase 2 item 2's interpolation perturbation is not optional on this corpus.
- **The fit is at the bound; the track is the limit.** Least squares with variable projection on `ridge()`'s tracks beats the brightness and contrast objectives on speed and slant range but not on f0 or event-2 timing, and every miss is the track following another line or leaving a manoeuvring pass; with a correct track the estimator sits at the Cramér–Rao bound ([least-squares-fit](docs/experiments/2026-11-04-least-squares-fit.md)). So item 3's tracker, not the fit, is what the fitting path waits on, and item 8's warp, which makes the line stationary before tracking, is the other way to the same end.
- **A stopping rule works, and costs coverage.** Phase 2 item 3's off-state Viterbi tracker, with every knob set on synthetic data before one run, beat `ridge()` on frequency error (0.45 % against 0.48 %) and false bridges (13 against 36) but fragmented ten times as often, because a tone that dips under the per-frame threshold on 41 % of its frames ends the track there; a forced path finds it anyway. The threshold can't drop below the noise's own peak level (about 8 dB) without false tracks, however high the birth cost. On the 11 manoeuvring passes the off state is what keeps the tracker honest: 0.84 % error against `ridge()`'s 15 % and ssqueezepy's 21 %. Sub-bin estimators on synthetic chirps: Quinn's FTI(2) 0.33 Hz RMS, Candan 0.35, quadratic interpolation 0.38 ([freqtrack](docs/experiments/2026-11-04-freqtrack.md)).

### 6.3 What the literature supports, and its limits

Equations cited here were checked against the PDFs.

| Source | What we take from it | Caveat |
|---|---|---|
| Ferguson 1992; Ferguson & Quinn 1994; Ferguson & Lo 2000; Ferguson 2016 | The pass model, the least-squares fit with α and β eliminated, and starting values from the asymptotes and peak slope | Controlled overhead passes at about 70–610 m, flown straight and level at set speeds. Single-sensor errors were 5–9 kn and 54–100 ft, yet about 12 % of altitude estimates were more than 20 % off. Our passes are opportunistic, at 1–9 km, so expect worse. Ferguson 2016's printed eq. 14 squares each term inside the sum; take the reduced objective from Ferguson & Quinn 1994 eq. 20 |
| Quinn 1995 | Weighting each frequency estimate by amplitude squared, a covariance for the fitted parameters, and fits of partial tracks | Amplitude is a reliability weight, not a range measurement. The covariance assumes independent errors from non-overlapping blocks |
| Timlelt et al. 2017 | A closed-form comparator | Eq. 19 takes the argmax of f′ although f′ is negative (its eq. 15), and eq. 20 drops a square. Its simulations show a 7 % f0 error, and its experiments use a loudspeaker moving at 1–1.6 m/s |
| Chan & Towers 1992 | Keeping several low-cost solutions, because of ghost solutions and noise | Written for five or more simultaneous sensors; their sensor counts don't transfer |
| Iatsenko et al. 2016 | Ridge-extraction schemes, adaptive penalties and error measures | Built for components present throughout a signal. With transient ones it hops between components, and it has no stopping rule. Harmonics aren't covered |
| Kay I (1993) | The frequency-estimation bound (eq. 3.41), separable least squares (§8.9), and the threshold effect at low SNR | Bounds hold above a threshold SNR; below it, outliers dominate |
| Kay II (1998) | False alarms grow roughly in proportion to the cells searched (eqs. 7.36–7.37) | Assumes independent cells and known noise; ours overlap, so the rate has to be measured |
| White 1982 | A wrong model's fit converges to the best approximation for that objective and window | Even a sandwich covariance measures spread around that approximation, not distance to the truth, and the usual covariance can be wrong in either direction. It applies to likelihoods, which a brightness score isn't |
| Raue et al. 2009 | Profile likelihood, and structural against practical non-identifiability | χ² thresholds need Gaussian noise of known variance and an adequate model. For a brightness score, read profile shapes only |
| Golub & Pereyra 2003 | Variable projection for the least-squares fit | Applies to sums of squares only, doesn't remove local minima, and isn't always faster |
| Harris 1978 | The correlation between overlapped STFT frames (eq. 17): at our 87.8 % Hann overlap a frame correlates 0.91, 0.67, 0.40 and 0.18 with the next four, so the effective number of independent frames is the frame count over 1 + 2Σc² ≈ 3.9 (1.9 at a 1 s window, 1.06 at 0.5 s, same hop) | A correlation of periodogram noise under a flat spectrum; the correlation of per-frame frequency estimates follows it only to first order, so the factor corrects Quinn 1995's covariance, it doesn't replace measuring it |
| Quinn & Hannan 2001 | Frequency tracking at low SNR as a hidden Markov model with Viterbi and forward–backward recursions (ch. 7), the Fourier-coefficient interpolators (§6.2.2), the periodogram maximiser's bound (ch. 3) | Their tracker assumes a slowly varying frequency present throughout and known noise statistics; a pass starts and ends, so the off state item 3 added has to stay |
| Angelopoulos & Bates 2021 | Split conformal regions, and Learn-then-Test for guarantees among non-abstained answers | Coverage is averaged over exchangeable cases, here groups of recordings. It doesn't cover thresholds tuned by leave-one-out |
| Cawley & Talbot 2010 | Tuning and reporting on the same cases biases results by as much as the differences between methods | Their smallest data set has 64 points; with two recordings the risk is larger |
| Lo & Ferguson 2003 | Ground-reflection delay as a constraint on elevation and range | Written for broadband jets over hard ground. Its interference fringes are one plausible source of `detect`'s jet false positives (E5) |
| Howell et al. 1986 | The single-microphone warp on a propeller aircraft: sample the recording at the reception times of equally spaced emissions (eq. 1); a Shackleton's blade-passing harmonics resolve to the 17th after correction; the interpolator sets the noise floor (nearest sample 10 dB, linear at twice the analysis rate about 35 dB) | Overhead passes with tracked aircraft; the corrected history is right only for the assumed emission point, and reflections are apparent sources that warp differently |
| Kelly & Wilson 1993 | De-Dopplerisation of one microphone's recording from a tracked position history: resample onto a uniform emission-time grid at the reception time each emission reaches the microphone, scale by range and Doppler factor, transform (eqs. 12, 30–31); on an XV-15 the harmonics that smearing erased reappear | Overhead passes at 250 ft with radar tracking; assumes a quasi-stationary source, no absorption, a uniform atmosphere and no ground effect |
| Gao et al. 2021 | The warp as an estimator: for each candidate motion, resample, take the spectrum and minimise its entropy over the line's band (eqs. 6–9); a fishing boat's speed to 4 % against a frequency-fit comparator's 16 % | One hydrophone, one line, closest range and CPA time assumed known; a marine example, so the gain on aircraft and on competing locations is untested |
| Axelrad et al. 2011 | Collective detection: map every point of a position-and-clock grid to each source's observables, sum the sources' correlation powers non-coherently there, search coarse to fine; four weak satellites detect where one can't | Satellites have known codes and are all present; our events have unknown tones, some flights are inaudible and several can explain one line, so the sum needs an assignment rule and an unmatched alternative, and the null tail is fatter than the simple model |
| Ramseier & Pieren 2024 | Time-domain de-Dopplerisation by windowed-sinc resampling (eq. 7), a background estimated across frequency at each instant (eq. 11), and harmonics tracked jointly by dynamic programming with a slope bound (eq. 14); N1 to about 2 % against the flight recorder near the runway | Known trajectories and turbofans at 44.1 kHz; their tones become undetectable at larger distances on landings, and nothing in it ranks competing geometries |

### 6.4 What related projects report

Three open-source projects (dopplerprint, echolocate, unheard) started in November 2026 on the same problem. [docs/reference/related-projects.md](docs/reference/related-projects.md) records the commits inspected, what each reports and what we take. Whitening biases frequency measurements, so find tracks whitened and measure them on the original STFT; a local Viterbi gives the tracker a stopping rule; scores in units of each event's own wrong guesses put pairs on one scale; and removing the source aircraft while keeping the traffic is the negative that catches confident substitutions. Their numbers are self-reported, unreviewed and tuned on the shared Livermore corpus, so each one is an experiment to run here.

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

1. **The practical resolution behind "located".** Decided 2026-11-04: a 1 km radius. A smaller radius makes the tool abstain more; a larger one makes "located" less useful. The development results sit inside it (Oyster Bay 123 m and 43 m refined, the eagle cam 917 m and 567 m). To be revisited only with M3 evidence.
2. **Which clean recordings go to calibration and which to evaluation.** Decided 2026-11-04, before any of them was searched:
   - evaluation: ESID 375 (quiet, continuous), ESID 710 (moderate traffic) and ESID 937 (the must-abstain negative; moved from calibration on 2026-11-04, still before any of them was searched, because an evaluation set with no clean recording can't measure a false "located");
   - calibration: ESID 740 and XC979185, with the Essex recordings and AeroSonicDB's no-aircraft stretches as its negatives;
   - development: the three Essex recordings, since Phase 2 tunes `detect`'s threshold on them, and the Livermore corpus, which Phase 2 fits on;
   - Seattle sessions go to evaluation by default.
   The evaluation set has no negative yet; the first Seattle session or another quiet-airspace recording should supply one.
3. **Recording ground truth yourself.** The checklist in 5.6 applies. Several devices at one session form one group, so a second site is worth more than a fourth device. Deliberately moved, edited and phone-processed clips are worth a session of their own. A local ADS-B receiver at the session is optional hardware, but it is what turns L2 from an assumption into a number.
