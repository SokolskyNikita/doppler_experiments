# U.S. propeller-aircraft exposure with housing and outdoor time

<!-- index
question: How do measured house attenuation and hourly outdoor activity change U.S. person-time within modeled acoustic range of a tracked propeller airplane?
outcome: Central person-time is 0.64% by day and 0.025% overnight for a carried phone, versus 0.15% and 0.016% for a stationary indoor phone.
-->

This calculation follows a hypothetical phone carried by its owner through the day. The [prior model](2026-11-04-us-residential-aircraft-coverage.md) put the phone indoors all day with 15 dB outdoor-to-indoor loss. We retain its 288 aircraft snapshots from the first UTC day of each month of 2025, 2020 Census population weights for the 50 states and DC, flight-phase ranges and deduplication of simultaneous aircraft. We now model closed and open houses, other buildings and outdoor locations. Census residential centroids still serve as the geographic proxy for where people spend each hour. Moving from house to yard changes the acoustic environment. Commuting to work or visiting a park can change the actual flight traffic overhead, which this calculation does not capture. Rates describe proximity to one tracked fixed-wing piston or turboprop aircraft. A successful location estimate requires the phone to record informative passes.

## Results

| Scenario | 06:00–22:00 | 22:00–06:00 | Full day |
|---|---:|---:|---:|
| Previous flat 15 dB, always indoors | 0.295% | 0.0310% | 0.207% |
| Stationary indoor phone, realistic house loss and window mix | 0.155% | 0.0162% | 0.109% |
| Carried phone, hourly indoor/outdoor activity and band equality | 0.640% | 0.0246% | 0.435% |
| Carried phone, applying the preceding eight-pass median replay threshold | 0.588% | 0.0222% | 0.399% |

The carried-phone band-equality scenario corresponds to 6.14 minutes during the daytime interval and 7.1 seconds overnight, averaged over residents and days. These seconds cluster into flyovers. While a person is actually outdoors, the corresponding conditional rates are 5.06% by day and 0.89% overnight; the model's outdoor activity occurs disproportionately during busy flight hours. Outdoors supplies 0.543 percentage points out of the daytime 0.640% (85%) and 0.00936 points out of the nighttime 0.0246% (38%). A phone sitting beside a router follows the stationary row even when its owner goes outside.

Increasing both modeled outdoor spectra by 5 dB gives 0.327% by day and 0.0188% at night. Decreasing them by 5 dB gives 1.172% and 0.0336%. These are scenarios, not statistical intervals. Changing the fraction of indoor residential time with open windows from 10% to 30% gives 0.616–0.645% daytime and 0.0199–0.0258% nighttime. Treating vehicle and unspecified time as closed-house exposure instead of zero gives 0.647% and 0.0248%. Reweighting the diaries with Oxford's recommended quality filters yields 0.623% and 0.0238%.

## Outdoor time

We reconstructed all 24 local-clock-hour fractions from the National Human Activity Pattern Survey diaries. The original survey weights were applied separately to 7,514 adults and 1,872 children, combining the two groups with the 2020 Census under-18 share of 22.06%. Each diary had 1,440 consecutive minutes. These data measure 1992–94 behavior rather than contemporary minute-by-minute mobility. The original EPA activity summary independently gives 7.58% of the full day outdoors. The harmonized, age-adjusted calculation gives 7.51%. Modern ATUS puts home and yard in a single location code and therefore cannot update this particular quantity directly. [Oxford harmonized data](https://www.timeuse.org/ahtus/data) · [Original EPA survey and Figure 6-49](https://nepis.epa.gov/Exe/ZyPDF.cgi/9101VZRG.PDF?Dockey=9101VZRG.PDF) · [ATUS Table 10](https://www.bls.gov/news.release/archives/atus_07222021.htm)

| Time use | 06:00–22:00 | 22:00–06:00 |
|---|---:|---:|
| Outdoors | 10.74% | 1.05% |
| Inside own or another residence | 54.81% | 93.46% |
| Other indoor location | 25.65% | 3.92% |
| Vehicle | 7.89% | 1.40% |
| Unknown | 0.90% | 0.17% |

The estimator multiplies each hour's flight exposure by that hour's environment fractions, before averaging separately over the 16 daytime and 8 nighttime hours. The vehicle and unknown rows contribute zero opportunities in the central scenario. A sensitivity calculation assigns both the closed-house opportunity. Moving vehicles often have much higher low-frequency background. A U.S. road test recorded 64–66 dBA even with the windows up and music off. That supports an unfavorable assumption, although it cannot quantify detection in a parked vehicle. [NHTSA, Table 1](https://www.nhtsa.gov/sites/nhtsa.gov/files/812209-cwim-warngandmessagepresepambntnoiseon-road.pdf#page=12)

## House transmission

EPA Table 5-3 reports measurements in warm and cold U.S. climates under 60 closed-window and 46 open-window conditions. These are octave-band averages rather than a representative sample weighted by the present U.S. housing stock. Interpolating in dB versus log frequency gives the following values. A modern FAA study of eight rooms in two houses shows substantial irregularities from room to room at these frequencies. [EPA, Table 5-3](https://www.nonoise.org/epa%20index/roll19/roll19doc43.pdf#page=81) · [National Bureau of Standards, Appendix E](https://www.govinfo.gov/content/pkg/GOVPUB-C13-501b90f7a7a1849445211742d1642cf6/pdf/GOVPUB-C13-501b90f7a7a1849445211742d1642cf6.pdf#page=181) · [FAA measurements, Fig. 20](https://rosap.ntl.bts.gov/view/dot/68585/dot_68585_DS1.pdf#page=52)

| Band center, Hz | 100 | 125 | 160 | 200 | 250 | 315 | 400 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Closed, dB loss | 18.0 | 18.4 | 19.4 | 20.2 | 21.1 | 22.2 | 23.3 |
| Open, dB loss | 12.8 | 12.6 | 13.2 | 13.8 | 14.4 | 14.7 | 14.9 |

For time spent inside a residence, we use open windows 26.6% of daytime and 25.9% of nighttime. These are room-window duty estimates derived from Appendix I of an LBNL survey of 1,515 new detached California houses, using bedroom responses, equal seasons, and 5/7 weekday weights. They approximate exposure in an occupied room and are not nationally measured. A 2022 national survey found that 43.9% of respondents had opened a window during the preceding day. That number measures daily occurrence, not hours open. Other indoor locations use closed-house acoustics as a proxy. [LBNL report, Appendix I](https://www.aivc.org/sites/default/files/members_area/medias/pdf/CR/CR10_ventilation_behavior.pdf) · [Morrison et al., U.S. window-opening survey](https://pubmed.ncbi.nlm.nih.gov/34554621/)

## Indoor and outdoor background

The model retains the Seattle pilot noise spectrum as a proxy for internally generated room and phone noise. The pilot's two original 1 kHz files yielded nominal band levels of 49.6, 47.9, 42.5, 45.3, 42.9, 38.5 and 40.2 dB SPL at 100 through 400 Hz. Absolute calibration and the fraction generated inside were not measured. Adding a transmitted outdoor contribution could double-count some outdoor noise already in the Seattle recording. For a house loss A, internally generated noise N, and outdoor background O, the aircraft level required outside the wall is 10 log10[10^((N+A)/10) + 10^(O/10)] at total-band equality. The aircraft and the outdoor background pass through the same wall. Outdoors the required exterior level is simply O. This assumes an exposed microphone and omits pocket attenuation, wind across the phone, handling and speech. [Original phone and aircraft calculation](2026-11-04-us-movement-pickup.md)

Outdoor spectral shape comes from roughly one month of calibrated January measurements at Rock Creek Park in D.C. For a residential proxy, we shift its day and night spectra to match the published population-weighted outdoor broadband medians for larger and smaller U.S. communities. Casey et al. give 48.0/44.3 dBA for 07:00–19:00/19:00–07:00 in CBSAs above 100,000 residents and 37.0/38.8 elsewhere. Both studies' noise periods are respected when selecting the spectrum; exposure is separately reported at the user's 06:00 and 22:00 boundaries. The national study models summer anthropogenic sound while the park measured total sound in winter. Transferring the spectral shape is an assumption. The smaller-community night median being higher than its day median follows the published values. We use population-weighted medians within each of the two geographic groups, not an address-specific background field. [NPS, Fig. 2](https://irma.nps.gov/DataStore/FileSource/Get/2229086?filename=NRR_ROCR_AcousticFinal.pdf) · [Casey et al., Table 1 and Results](https://pmc.ncbi.nlm.nih.gov/articles/PMC5744659/)

The 2020 Census county-to-CBSA delineation and population counts place 86.79% of the modeled U.S. population in a CBSA above 100,000. Applying the region-specific spectra at each residential centroid preserves the relationship between population centers and nearby air traffic. The contiguous-U.S. noise literature is extended by assumption to Alaska and Hawaii. [Census March 2020 delineation](https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2020/delineation-files/list1_2020.xls)

The [nonoverlapping-window follow-up](2026-11-04-us-phone-interval-coverage.md) uses continuous flight tracks to estimate the chance of a pass in a 5–60 minute recording.

## Reproduction

The [calculation script](../../tools/experiments/2026-11-04/indoor_outdoor_coverage.py) operates on the previous experiment's Census centers, terrain, local time zones, flight observations and source spectra. The run directory is `$DOPPLERTRACK_DATA/runs/2026-11-04-us-indoor-outdoor-coverage/`. It includes the scenario configuration, local-hour tables, geographic classification, activity diary calculations, measurement inputs, reproduction command and summary outputs. The [Doppler detector tests](2026-11-04-doppler-integration-coverage.md) motivate the additional half-decibel replay-threshold scenario. Neither detector performance nor false alarms were remeasured here.
