# Station temperatures for the bench cases (2026-11-04)

<!-- index
question: Which station temperature belongs in each bench case's `weather` block?
outcome: The nearest ASOS within 1 h of the recording's midpoint, 4.9–24.3 km away; as one c per case it costs both positive seed cases their true pair (Oyster Bay rank 1 to 3, the eagle cam 1 to 6), because the aircraft fly 1–6 km up, and even through the per-flight path, which keeps Oyster Bay at rank 1, the eagle cam's true pair ranks 2nd, and refitting at the station temperature shows why: the event fits sit on a flat v–d ridge with dozens of near-equal optima, so a 1.9 % change of c moves them 14–45 % between basins; the temperature stays off by default until the event fit is well-conditioned (item 4)
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `a5b04cea0257f0942851a2b0dcaa94c6638f8d1579b305edad87b9c3fba2f346`.

**Question.** Which air temperature belongs in each bench case's `weather` block ([sound-speed](2026-11-04-sound-speed.md)), and how well does one reading stand for its recording?

**Method.**
- **Station:** IEM ASOS, the nearest station to the case's reference point with a report within 1 h of the recording's midpoint. The reading is the report nearest that midpoint.
- **Temperature:** from the METAR's T group (0.1 °C) when the report has one, else IEM's `tmpc` (whole °C for the UK METARs and for Marion's).
- **Midpoint:** the recording start plus half its length. The start is the audio clock where a case has one (Oyster Bay and the eagle cam), else the case's start time. The length comes from the case's description.
- **`aircraft_height_m`:** set only where the case has a true pair whose two heights above ground at CPA agree within 30 %. None do, so it stays null everywhere:
  - Oyster Bay's a1dfeb and ace391: 5.5 and 1.1 km;
  - the eagle cam's a2baea and a336e4: 2.5 and 5.7 km.
- **Versions:** a change to a case is a new version of it (`bench/cases.json`'s note). Each case's latest version is left as it was, and the next version carries the weather.
  - On dev the weather is version 2 of every case: The integration merged this record’s first commit (0e95a3a) and put its locate changes on top as version 3, then a version 4 (`_cut2` CPA tables) for some. The integrated cases.json is taken as is, and this branch's own interim renumbering, with weather as v3, was dropped.
  - The runner takes the latest version, so every run now uses the measured temperature.
  - Earlier versions stay runnable by id and version, and by the a16b700 CLI, which refuses a temperature.
  - Each new version with a CPA cache gets its own file, `<name>_<T>C.npz`, because the sound speed is part of the table's fingerprint.
- **Variants without an audio clock.** oyster-bay-traces-end-early and oyster-bay-sources-removed have none, so they take oyster-bay's.
- **Google's Weather API can't serve these cases.** Its `history.hours` endpoint covers only the last 24 h, and every recording here is months older. Don't try it for recordings older than a day.

**Numbers.**

| Case | Station | Distance | Reading (UTC) | From midpoint | Temperature | Range over the recording |
|---|---|---|---|---|---|---|
| oyster-bay, and its five variants | KFRG Farmingdale | 18.9 km | 2026-09-08 20:53 | +5 min | 25.6 °C | one report |
| eagle-cam-clip-18000s | KFMY Fort Myers Page Field | 13.1 km | 2024-12-28 19:53 | −13 min | 26.1 °C | one report |
| eagle-cam-midnight, eagle-cam-midnight-days0 | KFMY Fort Myers Page Field | 13.1 km | 2024-12-28 23:53 | −7 min | 22.2 °C | over the 3 h |
| eclipse-esid375 (evaluation) | KAOH Lima | 8.7 km | 2024-04-07 13:53 | −11 min | 8.9 °C | 1.1 to 15.6 °C |
| eclipse-esid710 (evaluation) | KPIA Peoria | 8.4 km | 2024-04-07 11:54 | −5 min | 7.2 °C | 7.2 to 16.7 °C |
| eclipse-esid740 (calibration) | KMWA Marion Regional | 4.9 km | 2024-04-07 11:45 | −14 min | 10.0 °C | 7.9 to 23.0 °C |
| eclipse-esid937 (evaluation) | KPOF Poplar Bluff | 24.3 km | 2024-04-07 17:53 | −11 min | 20.0 °C | 10.0 to 24.4 °C |
| xenocanto-xc979185 (calibration) | EGMC Southend | 21.0 km | 2025-03-10 06:20 | +14 min | 6.0 °C | 6 to 7 °C |
| xenocanto-xc990819 | EGMC Southend | 16.3 km | 2025-04-20 04:50 | −6 min | 6.0 °C | 6 °C |
| xenocanto-xc990820 | EGMC Southend | 16.0 km | 2025-04-20 04:50 | +10 min | 6.0 °C | 6 °C |
| xenocanto-xc986433 | EGMC Southend | 19.0 km | 2025-04-07 05:20 | +12 min | 3.0 °C | 3 °C |

The Oyster Bay variants take Oyster Bay's reading: their audio is Oyster Bay's, and only the search box or the flight data changed.

**Outcome.**
- **Every case now has a measured temperature,** from a station 4.9–24.3 km away and within 14 min of the recording's midpoint.
- **The short recordings are well served.** Within Oyster Bay's, the eagle cam's and the Essex recordings the station's reports vary by at most 1 °C, under 0.2 % in c.
- **The day-long Eclipse recordings aren't.** One reading at the midpoint stands for 24 h over which the station's temperature swung 9–15 °C. That is up to ±1.3 % in c, the same as ±1.3 % in speed and range (the fit passes c through unattenuated; [model-error](2026-11-04-model-error.md), stage 3). A per-event temperature would fix this, but the schema holds one value per case. That is a follow-up for the schema, not something to work around here.
- **Ground temperature only, per case.** `aircraft_height_m` stays null, since the per-flight correction from each flight's own altitude supersedes it. Inversions are invisible to a station.

**The temperature's effect on the seed results** (saved-fit Tier 2, the five seed cases, two workers, warm caches).

*First pass, before the per-flight sound speed:* runs/2026-11-04-bench-a9613d9-saved-fit-t2-2 (case version 1) against runs/2026-11-04-bench-fd7f3b1-saved-fit-t2 (version 2). At this code the runner applied the case's ground temperature as one c for every flight.

| Case | Version 1 (15 °C) | Version 2 (ground temperature) |
|---|---|---|
| oyster-bay | rank 1, 328 pairs, 43.3 m, margin 4.9 % | rank 3, 329 pairs, top pair 70.7 km off, margin 4.6 % |
| oyster-bay-hp150-aac32k | rank 1, 43.3 m, 4.6 % | rank 3, top pair 70.7 km off, 4.9 % |
| eagle-cam-clip-18000s | rank 1, 607 pairs, 876 m, 2.5 % | rank 6, 605 pairs, top pair 58.7 km off, 0.8 % |
| oyster-bay-moved-wsw150 | 61 pairs, margin 10.7 % | 61 pairs, 7.9 % |
| oyster-bay-moved-north150 | 35 pairs, margin 3.2 % | 35 pairs, 2.6 % |

Scored triples change by under 0.1 %: Oyster Bay 40,889 to 40,861, the eagle cam 50,682 to 50,604.

- **Read this as the cost of the wrong c, not of the temperature.** The true pairs fly high: Oyster Bay's at 5.5 and 1.1 km, the eagle cam's at 2.5 and 5.7 km.
- **Path c is below the ground value.** With the documented mid-height lapse (−3.25 °C per km), their path temperatures put c at about 336–344 m/s. That is below the ground's 346.5 and 346.8, and straddles the 15 °C default's 340.3.
- **So one ground-temperature c is too fast for every high flight,** and the 15 °C default sits closer to their average by accident. The scored true pairs drop from 27.10 to 22.08 (Oyster Bay) and from 10.30 to below the runner-up's 9.71 (the eagle cam).
- **That is the case for the per-flight correction.** One c per recording can't serve flights at 1 and 5 km.

*Second pass, at the landing code* (dev 1166c88 against this branch, fa29d4a): runs/2026-11-04-bench-1166c88-saved-fit-t2 against runs/2026-11-04-bench-fa29d4a-saved-fit-t2. Every number is identical to the first pass, to the last digit.
- **Why.** the per-flight sound speed is `pipeline.run_search(temperature_c=...)`. It keeps the fits' c and propagates each emission point at its mid-height temperature.
- **The runner never uses it.** `bench.runner.sound_speed` still turns the case's temperature into one `c=speed_of_sound(T)` and passes that to search and refine. With saved fits made at 15 °C it also changes c on only one side of the comparison.
- **So the case temperatures can't land as the runner's default until the runner passes `temperature_c` instead of `c`.** Until then, every positive seed case loses its true pair.
- **A direct check of the per-flight path was stopped before it scored.** It used `--search-param temperature_c=T` on the no-weather versions, but those share their CPA cache files with everyone's default runs, and `temperature_c` changes the table's fingerprint (`runs/2026-11-04-bench-1166c88-saved-fit-t2-perflight-*`, marked STOPPED). It needs its own cache names, which the versions here already carry, once the runner passes `temperature_c`.

*Third pass, at the per-flight runner* (dev df0e202, runner change 60bf173: the fits keep their 15 °C c and each flight propagates at its own mid-height temperature).
- **Runs.** runs/2026-11-04-bench-df0e202-saved-fit-t2-noweather (each case's latest version with its weather nulled and its CPA cache renamed without the temperature, so that run is marked dirty) against runs/2026-11-04-bench-df0e202-saved-fit-t2-weather (the case as on dev).
- **Stopped part way.** Both runs were stopped under the user's rule that no compute runs on the Mac, after four of the five cases. hp150 and north150 are missing, and neither can change the outcome below.
- **The criterion,** fixed by review before the run: the weather versions keep both positives at rank 1 with the true pair, and the negatives stay negative.

| Case | Without weather | With weather, per flight |
|---|---|---|
| oyster-bay | rank 1, 43.3 m, margin 4.9 % (true pair 27.10) | rank 1, 146 m, margin 2.0 % (26.03 against 25.53) |
| eagle-cam-clip-18000s | rank 1, 876 m, margin 2.5 % (10.30) | **rank 2**, top pair a0e90b+a25807 14.1 km off, margin 0.6 % (true pair 10.15 against 10.21) |
| oyster-bay-moved-wsw150 | negative, margin 10.7 % | negative, margin 9.8 % |

**Outcome: the criterion fails, so the station temperature doesn't become the runner's default.**
- **What the per-flight path did.** It recovers most of what one ground-temperature c lost: Oyster Bay goes back to rank 1, and the eagle cam's true pair from rank 6 to rank 2. It doesn't recover the seeds.
- **The 15 °C default still gives the better seed results.** That isn't evidence the default is right. The committed saved fits were made at 15 °C, so the fits and the search share that c only in the default run.
- **The next question,** fixed by review: are the 15 °C saved fits the mismatch? Refit one case's events at the station temperature, then search them at the per-flight speed.
**Are the 15 °C saved fits the mismatch? The refit test** (`runs/2026-11-04-merge-refit-savedfit/`, merged from `runs/2026-11-04-refit-savedfit-s{1..8}of8`; fleet, commit 0734635; `tools/experiments/2026-11-04/refit_savedfit.py`).
- **Setup.** Each positive case's two events were refitted with `fit_event` as the committed fits were made, at 15 °C (the procedure's check) and at the case's ground temperature, then searched. The committed fits were run with the weather off and on as controls.
- **The criterion,** fixed before the run: with the ground-temperature refits searched through the per-flight path, the eagle cam's true pair returns to rank 1, and Oyster Bay's margin comes back to within 1 point of 4.9 %.

| Case, events, weather | True pair rank | Margin | Refined error |
|---|---|---|---|
| oyster-bay, committed, off | 1 | 4.9 % | 43 m |
| oyster-bay, refitted at 15 °C, off | 1 | 5.0 % | 43 m |
| oyster-bay, committed, on | 1 | 2.0 % | 146 m |
| oyster-bay, refitted at 25.6 °C, on | 1 | 8.7 % | 84 m |
| eagle-cam, committed, off | 1 | 2.5 % | 877 m |
| eagle-cam, refitted at 15 °C, off | 392 | 0.3 % | 14.1 km (wrong pair) |
| eagle-cam, committed, on | 2 | 0.6 % | 14.1 km (wrong pair) |
| eagle-cam, refitted at 26.1 °C, on | not ranked | 2.3 % | 14.2 km (wrong pair) |

- **Oyster Bay.** The refit procedure reproduces the committed fits (f0, v, d and t_cpa to the second decimal), so the comparison is fair.
  - Refitted at the ground temperature and searched per flight, the true pair keeps rank 1 with a margin of 8.7 %: above both the default's 4.9 % and the committed fits' 2.0 % with the weather on. Refined error is 84 m against the default's 43 m.
  - Event 2's refit moves more than c alone would: v 141 to 121 m/s, d 5.9 to 4.3 km. The contrast optimum shifts with c.
  - **Criterion met on margin, as intended.** The review's intent was recovery: a margin back to at least 3.9 %. 8.7 % at rank 1 meets that. The cost is the refined error, 84 m against the default's 43 m. This supports the 15 °C fits being the mismatch for Oyster Bay.
  - **The size of event 2's move is the open point.** A 1.9 % change in c should move v and d by 1.9 % (d ln v / d ln c = 1, model-error stage 3). They moved 14 % and 28 %. So the fit has probably landed in another basin of its objective, and the profile that tests this follows.
- **The eagle cam can't be judged, and that is a provenance problem for the benchmark: the case's saved fits can't be reproduced from the case's own inputs.** Its check fails: refitting the committed fits at 15 °C, by `detect`'s refine step on the clip's spectrogram, doesn't reproduce them.
  - Event 2's CPA moves 2.8 s and its distance from 3.1 to 3.3 km, and the true pair falls from rank 1 to rank 392.
  - The committed fits came from `detect` on the full 12-hour recording, whose spectrogram and whitening differ from the clip's.
  - So the temperature refit, with the true pair not ranked, says nothing about temperature. It does show again how fragile the eagle cam's result is: a 3 s shift in one fit takes the true pair from first to 392nd.
- **Outcome: the eagle cam half isn't met, and the temperature stays off by default** until Oyster Bay's event 2 is profiled and the eagle cam's fits are remade from the full recording.
  - Oyster Bay says the per-flight path wants fits made at the same temperature.
  - The eagle cam needs its fits remade the way they were made, with `detect` on the full recording at each temperature, before it can answer.

**Why the correct c made the fits worse: the event fits sit on a flat ridge with many near-equal optima** (`runs/2026-11-04-merge-basin-profile/`, merged from `runs/2026-11-04-basin-profile-s{1..4}of4`; fleet, commit 2559728; `tools/experiments/2026-11-04/basin_profile.py`).
- **Oyster Bay event 2's objective along v and d.** The brightness objective its committed fit used was maximised over f0 and t0 at each point of a grid (v 100–170 m/s, d 3–8 km), at 15 °C and at 25.6 °C.
- **Many local maxima of nearly the same height.** The surface has 51 local maxima at 15 °C and 50 at 25.6 °C, strung along a ridge on which d/v stays within about 32–45 s.

| Surface | Best grid point | Next two | The 15 °C fit (141 m/s, 5.9 km) | The 25.6 °C refit (121 m/s, 4.3 km) |
|---|---|---|---|---|
| 15 °C | 140 m/s, 5.75 km: 11.084 | 125 m/s, 4.63 km: 11.050; 130 m/s, 5.0 km: 11.035 | 11.099 | 10.708 |
| 25.6 °C | 132.5 m/s, 5.13 km: 11.115 | 130 m/s, 4.88 km: 11.063; 142.5 m/s, 5.88 km: 11.054 | 10.730 | 10.952 |

- **The ridge is flat.** The best three optima on each surface differ by under 0.5 %. Points 1.5 km apart in distance score within 1 % of each other.
- **The refit didn't find the best basin.** At 25.6 °C, `fit_event`'s refit landed at 10.952, below that surface's best grid point (11.115 at 132.5 m/s, 5.1 km). So a 1.9 % change of c didn't move the optimum by 1.9 %: it moved the optimiser to another local maximum on the ridge, 14 % lower in v and 28 % lower in d.
- **The eagle cam shows the same, and its provenance is now settled.**
  - **The control passes.** `detect` on the full 12 h spectrogram at 15 °C reproduces the committed events: ranks 5 and 12, against the committed 5 and 13, with v and d within 0.1 %. Searched, the true pair is at rank 1, margin 2.5 % and refined 1.0 km, against the committed 877 m. The case's recipe should therefore be this `detect` run on the full recording, not anything on the clip.
  - **At 26.1 °C the remade events land elsewhere on their ridges.** Event 1 moves from 99 m/s, 2.29 km to 112 m/s, 3.31 km; event 2 from 79 m/s, 3.07 km to 64 m/s, 1.77 km. Searched with the weather on, the true pair isn't ranked. The criterion (rank 1 at 26.1 °C) fails.
- **Outcome.**
  - **The temperature stays off by default.** The reason isn't the temperature itself: neither the correct c nor any other single value can be trusted while the event fit is this ill-conditioned.
  - **The saved-fit path has a non-identifiability the bound work hasn't seen.** The brightness and contrast objectives that `fit_event` and `detect` maximise have a flat ridge along v and d with many near-equal local maxima. A 1.9 % change in c moves the chosen fit by 14–45 % in v and d. The Cramér–Rao bound, being local, measures a single maximum's curvature, not the choice between maxima.
  - **This bears on Phase 2 item 4, the event fit's replacement.** A least-squares fit on a tracked ridge has one well-conditioned minimum on Livermore's straight passes (model-error stage 1), so it should be tested here for whether it makes the event fit stable under c. Until then a station temperature can't be tested fairly, because any change in c reshuffles the fits.

**Is the least-squares fit on a tracked ridge stable instead?** (`runs/2026-11-04-merge-ls-stability/`, from `runs/2026-11-04-ls-stability-s{1..6}of6`; fleet, commit e4e4695; `tools/experiments/2026-11-04/ls_stability.py`).
- **Setup.** The four events were fitted with `tracks.ridge_track` + `tracks.fit_track` (unweighted) in the committed windows, at 15 °C and at the station temperature, then searched. Oyster Bay used the README's bands. The eagle cam used 0.9 × f_post to 1.1 × f_pre of its committed curve.
- **Expectation, written before the run.** `fit_track` solves the curve's α, β, t_c and s with no c in them, and c only maps them to v and d, both proportional to c. So on one track the criterion (v and d move 2 ± 1 % on all four events) holds by construction.
- **Stable, as constructed.** v and d move by 1.82 % on both Oyster Bay events and 1.91 % on both eagle-cam events. Each fit has one optimum (`n_optima` 1).
- **One minimum against fifty.** Oyster Bay event 2's least-squares objective over the brightness profile's v–d grid has a single local minimum at either temperature, against fifty maxima for brightness.

**But the tracks are wrong, so the fits are too.**
- **The fits are far from the committed ones.**

| Event | Least squares (15 °C) | Committed (brightness, 15 °C) | Track RMS |
|---|---|---|---|
| Oyster Bay 1 (harmonic 2) | 26 m/s, 108 m | 140 m/s, 6.43 km | 4.3 Hz |
| Oyster Bay 2 | 52 m/s, 457 m | 141 m/s, 5.92 km | 15.2 Hz |
| eagle cam 1 | 90 m/s, 1.60 km | 99 m/s, 2.29 km | 11.2 Hz |
| eagle cam 2 | 40 m/s, 461 m | 79 m/s, 3.07 km | 14.5 Hz |

- **No true pair in the searches.** With these events, neither case ranks its true pair at either temperature. Oyster Bay keeps 6 flight pairs, and the eagle cam's top pair is 21.8 km off.
- **The single minimum sits at the grid's edge.** On Oyster Bay event 2's surface it is at v = 100 m/s, d 3.9–4.0 km, with an RSS of about 1.2 × 10⁵ Hz² over 440 points: the track, not the curve.

**Outcome.**
- **The least-squares fit does what it should with c.** It has one basin and moves exactly with c, unlike brightness.
- **On these recordings `ridge()` doesn't follow the aircraft's line.** Its tracks give fits 2–60 times too close. So the event fit can move to least squares only on a tracker that holds the line. That is the case review named: the ridge tracker is the suspect, and the switch waits for a reliable tracker.
- **The temperature stays off by default.**

- **"Weather on" is now a run switch, not a case version.** Each case keeps its station reading as data. The runner uses it only when a run sets `use_case_weather`: `bench run --weather`. That run's overrides, run.json and folder tag record the switch.
  - The default is the 15 °C path, with the case's reading recorded in the record's `speed_of_sound` (`case_temperature_c`) but unused.
  - Tier 1 always runs the default.
  - The compare above is now one flag: `bench run --profile saved-fit` against the same with `--weather`.


**Script:** `tools/experiments/2026-11-04/case_weather.py` (`--apply` writes the version 2 cases). **Run:** `runs/2026-11-04-case-weather/`, with the station lists, `weather.json` (every case's numbers and the fetch URLs) and the logs. **Fetched:** `raw/aux/metar/KAOH_2024-04-06.csv`, `KPIA_2024-04-06.csv`, `KMWA_2024-04-06.csv`, `KPOF_2024-04-06.csv`, `EGMC_2025-03-09.csv`, `EGMC_2025-04-06.csv` and `EGMC_2025-04-19.csv`, in the data root's MANIFEST.md. KFRG and KFMY were already there.
