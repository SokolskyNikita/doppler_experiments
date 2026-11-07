# How often is an aircraft within acoustic range of a U.S. residence?

<!-- index
question: At a random local instant, how often is a tracked aircraft within the reference recording’s modeled range of a U.S. resident at home?
outcome: Across 12 sampled days in 2025, fixed-wing propeller coverage averaged 0.30% from 6 a.m. to 10 p.m. and 0.031% overnight. The assumed indoor loss dominates those estimates.
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `bdfd6bae17488aba059907169e7b48fbd8b773e94a08a146530b9928b9e3121e`.

## Estimate from 12 monthly samples

We placed the 2020 population of the 50 states and DC at its residential Census block-group population centers, then counted the people within the modeled slant distance of at least one aircraft. The denominator is person-time, separately for 06:00–22:00 and 22:00–06:00 in each resident’s local civil time. Two aircraft simultaneously near the same resident count once. Sampling aircraft against homes captures the clustering of both people and aircraft around cities. It does not follow people to work, school or elsewhere.

| Aircraft counted | Daytime | Overnight | Whole day |
|---|---:|---:|---:|
| Fixed-wing piston and turboprop | 0.295% | 0.0310% | 0.207% |
| All modeled fixed-wing, including jets | 1.235% | 0.258% | 0.909% |
| Fixed-wing plus modeled helicopters and other rotorcraft | 1.492% | 0.374% | 1.119% |

The first row is the relevant fleet for the current propeller-tone method. It corresponds to 2.83 minutes during the 16 daytime hours and 8.9 seconds during the eight nighttime hours, averaged over all residents and sampled days. Presence at an instant is one opportunity for a signal. To locate the recorder, the pipeline needs usable Doppler curves from multiple suitable passes in the same recording.

The [Doppler integration follow-up](2026-11-04-doppler-integration-coverage.md) reruns the union for below-background thresholds and tests tones injected into the original reference recording.

## Traffic, population and range model

- The primary sample uses the ADS-B Exchange global hourly snapshots from the first UTC date of each month of 2025, 288 instants. The source offers those dates for evaluation. The North America filter retains 1,316,558 airborne rows across the 288 instants, including points outside the U.S. that could cover a U.S. resident. The calculation rejects explicitly grounded aircraft, absent altitudes and positions more than 15 seconds old. There are 14,520 rows without a type designator. Restricting the headline to classified aircraft avoids assigning those a sound level. Assigning every unknown-class aircraft a 1 km radius instead moves the broadest row to 1.501% by day and 0.376% by night. The dates are a convenience sample across seasons. January 1 and September 1 were U.S. holidays. The day-specific fixed-wing prop estimates span 0.136–0.391% by day and 0.0158–0.0531% overnight. [ADS-B Exchange evaluation snapshots](https://www.adsbexchange.com/data-products/sample-data/)
- The Census file contains 239,780 block groups in the states and DC, totaling 331,449,281 people. We discard zero-population rows. Each remaining point represents its block group’s population-weighted mean location. This approximates spatial density at the short ranges of interest, particularly in large rural or coastal groups. The GMT 30-arcsecond terrain grid gives residential ground height. At each point, EGM96 geoid separation reconciles ADS-B geometric heights with terrain elevations above mean sea level. Pressure altitude is used as reported when geometric height is unavailable. Terrain elevations below zero are clamped to zero to handle offshore centroids. The model does not account for intervening ridges or individual buildings. [Census population centers and methods](https://www.census.gov/geographies/reference-files/time-series/geo/centers-population.html) · [GMT Earth relief](https://oceania.generic-mapping-tools.org/server/earth/earth_relief/earth_relief_server.txt) · [EGM96 grid](https://download.osgeo.org/proj/vdatum/egm96_15/egm96_15.gtx)
- Each population center has an IANA time zone. The local-time calculation handles DST, including Arizona, and assigns three offshore or cross-border weighted centroids to the corresponding U.S. zone. Each hourly snapshot represents the centered hour. An interval crossing 06:00 or 22:00 contributes proportionately to both periods. This prevents a one-second archive timestamp offset from assigning an entire hour to the other period. [Timezone Boundary Builder](https://github.com/evansiroky/timezone-boundary-builder)
- Fixed-wing radii come from the [reference low-frequency calculation](2026-11-04-us-movement-pickup.md). Approach and departure use each model’s median across published power settings. An aircraft descending or climbing over 2 m/s uses the corresponding radius. For level flight or absent vertical rate, the geometric mean of the two radii is a modeling choice. Known ICAO designators use a matching model when available. Other classified aircraft use the median of the available reference models for their propulsion, size and engine-count category. Aircraft types modeled only by a proxy, particularly military aircraft, can deviate from those assumptions. Rotorcraft use the prior level-flight estimates. The central case assumes a 15 dB outdoor-to-phone loss and the same reference noise floor at all hours and homes. It makes no allowance for changes in engine power outside an airport flight profile. [ICAO type catalogue mirror](https://opensky-network.org/datasets/metadata/doc8643AircraftTypes.csv)
- The spatial calculation tests horizontal separation and vertical separation together. A plane at 10 km altitude cannot satisfy a 3 km slant range even when directly overhead. Pooled percentages are the total exposed population divided by the corresponding total population across equally spaced instants. Expected elapsed person-time is that fraction multiplied by the period duration. Shifting from source-emission time to acoustic-arrival time would displace boundaries by seconds and was omitted.

## Five-minute cross-check on four other dates

We repeated the spatial calculation using the adsb.lol global archives on April 7, 2024 and March 10, April 22 and September 19, 2025. Each archive was sampled at 00:01:57 UTC and every five minutes thereafter, interpolating between consecutive airborne fixes at most 120 seconds apart. All 1,152 instants were populated. The 4,569,457 North American positions contained no repeated aircraft address within an instant. More than 97% of heights were geometric on every day. The two archive providers can receive broadcasts from the same aircraft. These four additional dates cross-check the sample cadence and provider together, without independently calibrating reception completeness. [adsb.lol 2024 archive](https://github.com/adsblol/globe_history_2024) · [2025 archive](https://github.com/adsblol/globe_history_2025)

| Aircraft counted | Daytime | Overnight | Whole day |
|---|---:|---:|---:|
| Fixed-wing piston and turboprop | 0.279% | 0.0215% | 0.193% |
| All modeled fixed-wing, including jets | 1.227% | 0.225% | 0.893% |
| Fixed-wing plus modeled rotorcraft | 1.469% | 0.312% | 1.084% |

The four-day snapshots and extraction metadata are in `$DOPPLERTRACK_DATA/runs/2026-11-04-us-coverage-snapshots-2/`. The extraction script is in the `2026-11-04-us-coverage-snapshots/` run. The per-source results remain separate so the denser five-minute grid cannot give these four dates 12 times the weight of each monthly day.

## Indoor loss and nighttime background

Each row reruns the spatial union using the model-specific radii calculated at that loss. Nothing else changes. The range of scenarios is not a confidence interval.

| Outdoor-to-phone loss | Fixed-wing prop, daytime | Fixed-wing prop, overnight |
|---|---:|---:|
| 5 dB | 2.299% | 0.230% |
| 15 dB | 0.295% | 0.0310% |
| 25 dB | 0.0188% | 0.00234% |

If the effective background were 10 dB quieter across the relevant bands overnight, with flight activity and building transmission unchanged, the 5 dB row gives the corresponding night scenario. The reference recording supplies no such paired overnight measurement. This sensitivity includes cases where a slightly greater radius brings a whole flight altitude into range. The estimate is more sensitive to these acoustic assumptions than to the sampled month.

## Flights missing from ADS-B

The primary sample averaged 1,408 reporting U.S. civil-address fixed-wing propeller aircraft per instant in its broad North American box. The components were 1,118 single-engine piston, 97 twin piston, 114 single-engine turboprop and 79 multi-engine turboprop. The FAA’s 2024 survey estimated 18.99 million annual flight hours in the corresponding fixed-wing categories, or 2,162 flight-hour equivalents at an average instant (8,784 hours in the year). The ratio is 1.54. Sources differ in year, geography, operating rules and the treatment of experimental aircraft. The survey does not specify an airborne-versus-taxi convention for this item. The ratio therefore cannot establish the network’s capture rate for low flights over homes. If the unobserved hours had the same day/night split and the same exposure per hour as observed aircraft, scaling the sparse-occupancy propeller result gives about 0.45% by day and 0.048% by night. This is an illustrative all-traffic scenario. Flights absent from the trajectory archive cannot directly support a track match in the current pipeline. [FAA Table 2.1](https://www.faa.gov/data_research/aviation_data_statistics/general_aviation/cy2024/2024GASurveyCh2.xlsx) · [Survey question 3](https://www.faa.gov/data_research/aviation_data_statistics/general_aviation/cy2024/2024GASurveyAppendixBDocuments.pdf#page=2)

## Reproduction

[residential_aircraft.py](../../tools/experiments/2026-11-04/residential_aircraft.py) accepts the Census CSV, terrain/geoid NPZ, aligned timezone NPY, type catalogue, prior model-by-power radius CSV, one day’s aircraft fixes, and a new output filename. The optional `--fixed-wing-loss` selects the 5 or 25 dB alternative. Regenerating the default calculation produces per-instant daytime and nighttime numerators and denominators, including the extra half- and double-radius scenarios. Sources, inputs, preprocessing scripts, per-day outputs and aggregate results are under `$DOPPLERTRACK_DATA/runs/2026-11-04-us-residential-aircraft-coverage/`. The April and June `public-*` files in that run were preliminary checks. The completed estimates use the `centered/` files, which split time at the civil-time boundaries.
