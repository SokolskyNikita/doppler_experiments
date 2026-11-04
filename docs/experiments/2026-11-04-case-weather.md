# Station temperatures for the bench cases (2026-11-04)

<!-- index
question: Which station temperature belongs in each bench case's `weather` block?
outcome: The nearest ASOS within 1 h of the recording's midpoint, 4.9–24.3 km away, as each case's next version; but applied as one c per case, as the runner does today, it costs both positive seed cases their true pair (Oyster Bay rank 1 to 3, the eagle cam 1 to 6), because the aircraft fly 1–6 km up; it needs the runner to pass the temperature to A's per-flight path
-->

**Question.** Which air temperature belongs in each bench case's `weather` block ([sound-speed](2026-11-04-sound-speed.md)), and how well does one reading stand for its recording?

**Method.**
- **Station:** IEM ASOS, the nearest station to the case's reference point with a report within 1 h of the recording's midpoint. The reading is the report nearest that midpoint.
- **Temperature:** from the METAR's T group (0.1 °C) when the report has one, else IEM's `tmpc` (whole °C for the UK METARs and for Marion's).
- **Midpoint:** the recording start plus half its length. The start is the audio clock where a case has one (Oyster Bay and the eagle cam), else the case's start time. The length comes from the case's description.
- **`aircraft_height_m`:** set only where the case has a true pair whose two heights above ground at CPA agree within 30 %. None do, so it stays null everywhere:
  - Oyster Bay's a1dfeb and ace391: 5.5 and 1.1 km;
  - the eagle cam's a2baea and a336e4: 2.5 and 5.7 km.
- **Versions:** a change to a case is a new version of it (`bench/cases.json`'s note). Each case's latest version is left as it was, and the next version carries the weather.
  - On dev the weather is version 2 of every case: B merged this record's first commit (0e95a3a) and put its locate changes on top as version 3, then a version 4 (`_cut2` CPA tables) for some. B's cases.json is taken as is, and this branch's own interim renumbering, with weather as v3, was dropped.
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
- **Ground temperature only, per case.** `aircraft_height_m` stays null, since A's per-flight correction from each flight's own altitude supersedes it. Inversions are invisible to a station.

**The temperature's effect on the seed results** (saved-fit Tier 2, the five seed cases, two workers, warm caches).

*First pass, before A's per-flight sound speed:* runs/2026-11-04-bench-a9613d9-saved-fit-t2-2 (case version 1) against runs/2026-11-04-bench-fd7f3b1-saved-fit-t2 (version 2). At this code the runner applied the case's ground temperature as one c for every flight.

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
- **Why.** A's per-flight sound speed is `pipeline.run_search(temperature_c=...)`. It keeps the fits' c and propagates each emission point at its mid-height temperature.
- **The runner never uses it.** `bench.runner.sound_speed` still turns the case's temperature into one `c=speed_of_sound(T)` and passes that to search and refine. With saved fits made at 15 °C it also changes c on only one side of the comparison.
- **So the case temperatures can't land as the runner's default until the runner passes `temperature_c` instead of `c`.** Until then, every positive seed case loses its true pair.
- **A direct check of the per-flight path was stopped before it scored.** It used `--search-param temperature_c=T` on the no-weather versions, but those share their CPA cache files with everyone's default runs, and `temperature_c` changes the table's fingerprint (`runs/2026-11-04-bench-1166c88-saved-fit-t2-perflight-*`, marked STOPPED). It needs its own cache names, which the versions here already carry, once the runner passes `temperature_c`.


**Script:** `tools/experiments/2026-11-04/case_weather.py` (`--apply` writes the version 2 cases). **Run:** `runs/2026-11-04-case-weather/`, with the station lists, `weather.json` (every case's numbers and the fetch URLs) and the logs. **Fetched:** `raw/aux/metar/KAOH_2024-04-06.csv`, `KPIA_2024-04-06.csv`, `KMWA_2024-04-06.csv`, `KPOF_2024-04-06.csv`, `EGMC_2025-03-09.csv`, `EGMC_2025-04-06.csv` and `EGMC_2025-04-19.csv`, in the data root's MANIFEST.md. KFRG and KFMY were already there.
