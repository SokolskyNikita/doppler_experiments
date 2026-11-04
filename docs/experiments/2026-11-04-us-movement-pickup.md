# U.S. aircraft movements and low-frequency pickup at the Seattle phone

<!-- index
question: How far from the Seattle pilot would U.S. aircraft types reach the measured low-frequency background?
outcome: With 15 dB of indoor loss, modeled departure crossovers are about 1 km for a C172R and 3.3 km for a 737-800. Tone detection and nationwide coverage by aircraft type remain uncalibrated.
-->

These are conditional slant distances for the Seattle home pilot. The endpoint is equal aircraft and background power in **any one** of seven one-third-octave bands (100, 125, 160, 200, 250, 315 and 400 Hz). A full-band noise event and an extractable Doppler tone are different observations. No detector probability or false-alarm rate was fitted here.

## What the movement counts cover

Summing fiscal 2024 in `AirportsOperations.xlsx` in the FAA’s 2025 Terminal Area Forecast gives 103,412,779 takeoffs and landings across 3,319 airport records. The sum excludes the separate 2,793,409 overflights. General aviation accounts for 72,829,526 movements, air carriers for 17,332,371, air taxi/commuter for 9,012,593 and military for 4,238,289. The first three are 95.90% of this national airport-planning population. Non-towered counts include estimates. Private sites and many stand-alone military fields fall outside its scope. These service classes do not identify airframes. [FAA TAF data download](https://taf.faa.gov/Downloads/APO100_TAF_Final_2025.zip) · [Definitions, Appendix A](https://taf.faa.gov/Downloads/TAFSummaryFY2025-FY2055.pdf)

The FAA’s calendar 2024 GA and Part 135 survey estimates 43,186,019 landings, including water and touch-and-go landings. Fixed-wing single-engine piston accounts for 56.9%, twin piston 5.4%, turboprop 8.0%, turbojet 8.0%, piston rotorcraft 4.3%, single-engine turbine rotorcraft 7.9% and multi-engine turbine rotorcraft 2.9%. Those explicitly identified engine categories cover 93.40%. Special light-sport certification adds 1.67 percentage points, taking the count to 95.07%, but it supplies no unique spectrum. Experimental certificates account for another 4.45%. The survey follows U.S.-based registered aircraft rather than counting all movements on U.S. soil. [FAA Table 2.3](https://www.faa.gov/data_research/aviation_data_statistics/general_aviation/cy2024/2024GASurveyCh2.xlsx) · [Survey methodology](https://www.faa.gov/data_research/aviation_data_statistics/general_aviation/cy2024/2024GASurveyAppendixAMethodology.pdf)

For calendar 2024, BTS T-100 Segment (All Carriers) gives 19,546,342 U.S.-airport movements after counting each domestic departure performed as two U.S. airport movements and each international segment as one. Grouping equipment codes gives 11,603,706 narrowbody and other airline jet movements, 4,847,531 regional jet, 1,503,426 widebody and 924,887 turboprop. Together they account for 96.59% of this commercial reporting population. These calendar-year snapshots must not be added to the fiscal-year TAF or each other, since their units, coverage and Part 135 reporting differ. [BTS segment definitions](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FMG) · [BTS aircraft codes](https://www.transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_NVePeNSg_glcR)

## How the acoustic estimates were calculated

The Seattle pilot’s original 1 kHz capture supplied the noise floor. I integrated one-sided spectral power in each band using nonoverlapping 2.048 s Hann windows and took the median over 878 windows. The listening export has about 29 dB of gain relative to the source. The levels below retain the original gain. The conversion to sound pressure assumes nominal Android unprocessed sensitivity (+130 dB) and a flat microphone response. The device requested unprocessed capture, but its absolute sensitivity and in-room response were not measured. Android permits roughly ±10 dB response variation across these frequencies for devices supporting unprocessed capture. [Android CDD, §5.11](https://source.android.com/docs/compatibility/16/android-16-cdd#5_11_capture_for_unprocessed)

| Band center (Hz) | 100 | 125 | 160 | 200 | 250 | 315 | 400 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Recorded background (dBFS) | −80.41 | −82.07 | −87.46 | −84.70 | −87.10 | −91.51 | −89.81 |
| Standard air absorption (dB/km) | 0.66 | 0.66 | 0.98 | 1.31 | 1.31 | 1.97 | 2.30 |

For fixed-wing aircraft, the EASA legacy ANP v2.3 aircraft table assigns arrival and departure spectral classes. For each published power setting, take the maximum A-weighted level at 1,000 ft (304.8 m). Shift its unweighted class spectrum so that the energy sum of the 24 A-weighted bands reproduces that maximum. In band b, the reference level is Lb = LAmax + Sb − 10 log10(Σj 10^((Sj+Aj)/10)), where A is the standard frequency-dependent A-weighting. The class spectrum is a profile shared by similar aircraft. It does not measure the strength of a single propeller or fan harmonic. [EASA ANP v2.3](https://www.easa.europa.eu/en/downloads/138164/en) · [ECAC Doc 29, Vol. 2, Appendices D and G](https://www.ecac-ceac.org/images/documents/ECAC-Doc_29_4th_edition_Dec_2016_Volume_2.pdf)

With reference distance r0 and trial slant distance r, both in km, solve Lb(r0) − 20 log10(r/r0) − αb(r−r0) − 15 = Nb + 130. The **15 dB** is an assumed outdoor-to-phone loss for this placement, and α is the standard airborne attenuation tabulated above. Take the most favorable band for each aircraft, mode and power setting. Listed medians weight the published power settings equally, without assuming that they reflect the actual distribution of national flights. Flight phase and power dominate many differences. A 737-800's full departure-grid range is 2.15–5.23 km even before uncertainty in the phone or building. Airframe aspect, lateral ground effects, weather and detector integration are not modeled individually. This is an airport arrival/departure comparison. At height h, the corresponding ideal horizontal radius is √(r²−h²) if h≤r.

## Fixed-wing results

| ANP model | Approach median, km | Departure median, km | Approach settings, min–max km | Departure settings, min–max km |
|---|---:|---:|---:|---:|
| CNA172 | 0.58 | 0.97 | 0.34–0.82 | 0.89–1.06 |
| PA28 | 0.32 | 0.99 | 0.28–0.47 | 0.48–1.12 |
| CNA182 | 0.53 | 1.70 | 0.51–0.55 | 1.13–2.26 |
| PA30 | 1.04 | 1.13 | 1.00–1.08 | 0.88–1.89 |
| BEC58P | 3.05 | 2.12 | 1.45–4.64 | 1.07–3.18 |
| CNA208 | 2.70 | 1.92 | 2.70–2.74 | 1.76–2.08 |
| PA42 | 1.59 | 1.46 | 1.59–1.59 | 1.30–1.62 |
| CNA441 | 2.10 | 2.22 | 1.70–2.51 | 1.71–2.73 |
| DHC830 | 2.39 | 2.57 | 1.98–2.80 | 1.87–4.07 |
| ATR72 | 1.06 | 2.54 | 1.06–1.13 | 1.58–3.22 |
| 1900D | 2.44 | 1.78 | 2.32–2.56 | 1.63–1.92 |
| CIT3 | 1.26 | 2.52 | 0.64–1.88 | 2.00–3.04 |
| GV | 1.88 | 3.29 | 0.85–3.53 | 1.38–4.70 |
| EMB175 | 1.30 | 2.72 | 1.24–1.35 | 2.01–3.49 |
| CRJ9-ER | 1.22 | 2.79 | 1.13–1.31 | 1.90–3.67 |
| 737800 | 1.43 | 3.25 | 1.32–1.50 | 2.15–5.23 |
| 7378MAX | 1.16 | 2.42 | 1.13–1.24 | 1.72–3.18 |
| A320-211 | 1.20 | 3.15 | 1.16–1.25 | 2.31–4.12 |
| A320-232 | 1.11 | 2.50 | 1.10–1.18 | 1.48–3.73 |
| 777200 | 1.72 | 4.32 | 1.48–1.95 | 2.99–7.36 |
| 767300 | 1.70 | 3.34 | 1.63–1.78 | 2.63–4.70 |

## Rotorcraft and light-sport limitations

The Hughes 300C piston-helicopter flyovers gave 0.26, 0.33 and 0.40 km (median 0.33). The Bell 206L single-turbine flyovers gave 0.95, 1.07 and 1.96 km (median 1.07). These use measured spectra at overhead time on a microphone 150 m to the side, at slant ranges of 214–232 m. Other aspects can be louder. For a twin-turbine Bell 412, the modeled 1,500 ft undertrack spectra in ACRP Fig. 4-2 give about 2.3 km at 78 knots and 3.0 km at 128 knots, assuming the reference slant distance equals the height. [FAA measured spectra, Tables D-VI and the Hughes 300C run tables on printed pp. 59–61](https://rosap.ntl.bts.gov/view/dot/10026/dot_10026_DS1.pdf) · [ACRP 02-44, Fig. 4-2](https://onlinepubs.trb.org/onlinepubs/acrp/docs/ACRP02-44_FR.pdf#page=25)

Special light-sport and experimental are certificate categories. The EASA light-aircraft certification tables include overall A-weighted takeoff levels for individual light designs such as the Flight Design CTLS, but those levels cannot identify the unweighted 100–400 Hz energy or the Doppler tone. Their certification flight geometry can differ. For instance, two 600 kg Pipistrel Virus SW121 variants in the Chapter 10 takeoff table are 70.0 and 65.6 dBA. Their receiver distances during climb and band spectra are required to convert those levels into comparable distances. Published low passes have spectral peaks within the pilot band, but the audio in that paper was level-matched for listening tests. [TU Delft flyover study](https://research.tudelft.nl/en/publications/noise-emissions-and-noise-annoyance-of-a-single-propeller-electri/) [EASA light-aircraft certification data](https://www.easa.europa.eu/en/downloads/16973/en)

Our earlier 2.1 km Cessna example used one especially strong measured 160 Hz climbing pass and geometric spreading with 15 dB total extra loss. With 15 dB building loss plus the standard air term used here, the same 124 dB reference at 1 m gives 1.73 km. The ANP 172R row uses a generic class spectrum across published engine settings. The two estimates describe different sources and operating conditions. [Measured climb, Fig. 14](https://www.icas.org/icas_archive/ICAS1976/Page%20575.pdf#page=7)


## Sensitivity to the assumed indoor loss

At 5, 15 and 25 dB of loss the C172R departure medians are 2.46, 0.97 and 0.34 km. The 737-800 medians are 6.32, 3.25 and 1.52 km. Only the middle scenario is in the aircraft comparison. A narrow tone can cross a detector threshold at a different distance. At 160 Hz the one-third-octave band is about 37 Hz wide. With locally flat noise, a 1 Hz filter contains about 1/37 of that noise. At the band crossover, a stable tone bearing even 1/37 of the aircraft band power would equal the noise within that 1 Hz filter. Actual detection also depends on duration, frequency drift and the chosen false-alarm rate.

## Reproducing the fixed-wing comparison

Run [movement_pickup.py](../../tools/experiments/2026-11-04/movement_pickup.py) with the original Seattle pilot directory, the EASA ANP v2.3 ZIP and a new output CSV path. It concatenates the two original pilot segments and solves each of the 144 model, flight phase and power combinations at three assumed indoor losses. The run directory is `$DOPPLERTRACK_DATA/runs/2026-11-04-us-movement-pickup/`. It contains the power-by-power results, band noise, helicopter inputs and commercial movement totals. The independent rerun agreed with every original 15 dB calculation within 0.002 km.
