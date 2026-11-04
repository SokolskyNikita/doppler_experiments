# Station temperatures for the bench cases (2026-11-04)

<!-- index
question: Which station temperature belongs in each bench case's `weather` block?
outcome: The nearest ASOS within 1 h of the recording's midpoint, 4.9–24.3 km away, as version 2 of every case; one reading serves the short recordings to 1 °C, but the day-long Eclipse recordings swing 9–15 °C (±1.3 % in c)
-->

**Question.** Which air temperature belongs in each bench case's `weather` block ([sound-speed](2026-11-04-sound-speed.md)), and how well does one reading stand for its recording?

**Method.**
- **Station:** IEM ASOS, the nearest station to the case's reference point with a report within 1 h of the recording's midpoint. The reading is the report nearest that midpoint.
- **Temperature:** from the METAR's T group (0.1 °C) when the report has one, else IEM's `tmpc` (whole °C for the UK METARs and for Marion's).
- **Midpoint:** the recording start plus half its length. The start is the audio clock where a case has one (Oyster Bay and the eagle cam), else the case's start time. The length comes from the case's description.
- **`aircraft_height_m`:** set only where the case has a true pair whose two heights above ground at CPA agree within 30 %. None do, so it stays null everywhere:
  - Oyster Bay's a1dfeb and ace391: 5.5 and 1.1 km;
  - the eagle cam's a2baea and a336e4: 2.5 and 5.7 km.
- **Versions:** a change to a case is a new version of it (`bench/cases.json`'s note). Every case's version 1 is left as it was, and a version 2 carries the weather.
  - The runner takes the latest version, so every run now uses the measured temperature.
  - Version 1 stays runnable by id and version, and by the a16b700 CLI, which refuses a temperature.
  - Each version 2 with a CPA cache gets its own file, `<name>_<T>C.npz`, because the sound speed is part of the table's fingerprint.

**Numbers.**

| Case | Station | Distance | Reading (UTC) | From midpoint | Temperature | Range over the recording |
|---|---|---|---|---|---|---|
| oyster-bay, and its three variants | KFRG Farmingdale | 18.9 km | 2026-09-08 20:53 | +5 min | 25.6 °C | one report |
| eagle-cam-clip-18000s | KFMY Fort Myers Page Field | 13.1 km | 2024-12-28 19:53 | −13 min | 26.1 °C | one report |
| eclipse-esid375 (evaluation) | KAOH Lima | 8.7 km | 2024-04-07 13:53 | −11 min | 8.9 °C | 1.1 to 15.6 °C |
| eclipse-esid710 (evaluation) | KPIA Peoria | 8.4 km | 2024-04-07 11:54 | −5 min | 7.2 °C | 7.2 to 16.7 °C |
| eclipse-esid740 (calibration) | KMWA Marion Regional | 4.9 km | 2024-04-07 11:45 | −14 min | 10.0 °C | 7.9 to 23.0 °C |
| eclipse-esid937 (evaluation) | KPOF Poplar Bluff | 24.3 km | 2024-04-07 17:53 | −11 min | 20.0 °C | 10.0 to 24.4 °C |
| xenocanto-xc979185 (calibration) | EGMC Southend | 21.0 km | 2025-03-10 06:20 | +14 min | 6.0 °C | 6 to 7 °C |
| xenocanto-xc990819 | EGMC Southend | 16.3 km | 2025-04-20 04:50 | −6 min | 6.0 °C | 6 °C |
| xenocanto-xc990820 | EGMC Southend | 16.0 km | 2025-04-20 04:50 | +10 min | 6.0 °C | 6 °C |
| xenocanto-xc986433 | EGMC Southend | 19.0 km | 2025-04-07 05:20 | +12 min | 3.0 °C | 3 °C |

The Oyster Bay variants take Oyster Bay's reading: their audio is Oyster Bay's, and only the search box moved.

**Outcome.**
- **Every case now has a measured temperature,** from a station 4.9–24.3 km away and within 14 min of the recording's midpoint.
- **The short recordings are well served.** Within Oyster Bay's, the eagle cam's and the Essex recordings the station's reports vary by at most 1 °C, under 0.2 % in c.
- **The day-long Eclipse recordings aren't.** One reading at the midpoint stands for 24 h over which the station's temperature swung 9–15 °C. That is up to ±1.3 % in c, the same as ±1.3 % in speed and range (the fit passes c through unattenuated; [model-error](2026-11-04-model-error.md), stage 3). A per-event temperature would fix this, but the schema holds one value per case. That is a follow-up for the schema, not something to work around here.
- **Ground temperature only.** No mid-height correction applies anywhere, since `aircraft_height_m` is null, and inversions are invisible to a station.

**Script:** `tools/experiments/2026-11-04/case_weather.py` (`--apply` writes the version 2 cases). **Run:** `runs/2026-11-04-case-weather/`, with the station lists, `weather.json` (every case's numbers and the fetch URLs) and the logs. **Fetched:** `raw/aux/metar/KAOH_2024-04-06.csv`, `KPIA_2024-04-06.csv`, `KMWA_2024-04-06.csv`, `KPOF_2024-04-06.csv`, `EGMC_2025-03-09.csv`, `EGMC_2025-04-06.csv` and `EGMC_2025-04-19.csv`, in the data root's MANIFEST.md. KFRG and KFMY were already there.
