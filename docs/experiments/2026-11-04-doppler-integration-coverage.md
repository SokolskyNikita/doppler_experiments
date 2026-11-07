# How much could Doppler-matched integration change U.S. residential aircraft coverage?

<!-- index
question: How do coherent Doppler tracking and phase-independent integration change the reference threshold and the daytime and overnight propeller-aircraft opportunities?
outcome: In reference background an exactly shaped 18 s synthetic tone required 7 dB less power than a 2 s matched detector. Eight real pass replays required a median band level near background with a fitted ADS-B template.
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `235b01a695718d502ccb8c4e2216aeea2c37a520918baca94056aae9da898216`.

## National sensitivity to a detector threshold

The [previous coverage calculation](2026-11-04-us-residential-aircraft-coverage.md) asked when total aircraft power in any of seven third-octave bands from 100 to 400 Hz equals the reference microphone’s median background in that band. This study retains the aircraft spectra, phone background, 15 dB assumed outdoor-to-indoor loss, atmospheric absorption, 12 monthly sample days in 2025, and Census residential weighting. It varies the aircraft-to-background power ratio required for detection. All percentages below count **one or more tracked fixed-wing propeller aircraft in range at an instant**. They do not measure correct receiver locations or the probability of getting multiple passes within a recording.

| Required total aircraft power in a usable band | Day, 06:00–22:00 | Night, 22:00–06:00 | Full day | C172R median departure slant range |
|---|---:|---:|---:|---:|
| Equal to background | 0.295% | 0.0310% | 0.207% | 0.97 km |
| 4.77 dB below background (one-third the power) | 0.858% | 0.0876% | 0.601% | 1.55 km |
| 9.54 dB below background (one-ninth the power) | 2.123% | 0.213% | 1.486% | 2.37 km |

These are net credits relative to the old band-power threshold. The last two rows assume the aircraft provides usable tonal structure in whichever modeled band yields the longest range, and that the detector achieves the stated threshold there. They are scenarios. Neither 18 seconds of audio nor the injection result below establishes those assumptions. The model solves for each radius anew. With fixed band and source power, added margin G buys a radius satisfying 20 log10(r₁/r₀) + α(r₁−r₀) = G, where α is absorption in dB/km. The spatial calculation deduplicates overlapping aircraft and splits each snapshot at the 6 a.m. and 10 p.m. local boundaries. The input radii reproduced byte for byte when the original script was rerun, and the final zero-credit union reproduced the previous baseline.

## Replaying real flyovers in the reference recording

Eight systematically selected Livermore propeller passes were mixed at progressively lower amplitudes into 49 held-out reference background intervals. The clip’s original ambient sound remains in each replay. The reference band was selected to contain its labeled harmonic, at 200, 250, 315 or 400 Hz. Gain was measured against the unwhitened third-octave power of the entire added clip relative to the median reference calibration background in that band. A fixed noise-whitening filter was learned from a different set of 49 reference intervals. The correct pass time and fitted ADS-B geometry were supplied, and a residual ±2 Hz frequency search was calibrated into the per-candidate threshold. The target was 80% recovery with a nominal 5% noise exceedance per candidate. Held-out false positives varied by pass and method. This experiment uses a different operating point from the 160 Hz synthetic test below.

| Input used for the 18 s template | Median detectable clip band level | Across the eight passes | Illustrative U.S. daytime | Illustrative U.S. overnight |
|---|---:|---:|---:|---:|
| ADS-B curve, with fitted timing and source frequency | 0.5 dB above background | 5 dB below to 14 dB above | 0.262% | 0.0276% |
| Pitch track hand-traced from the original louder audio | 3.5 dB below background | 9 dB below to 14 dB above | 0.656% | 0.0674% |

The two national columns assume the median credit from the eight clips applies to every propeller aircraft’s most favorable modeled band. These transfers show the size of the effect only. The sample is small, the tested harmonic can differ from the strongest one, the clip includes original ambient power, and the hand-traced pitch was supplied before the signal was attenuated. A blind algorithm would need to infer that pitch from the quieter audio. With the fitted ADS-B template, 18 s coherent detection reached a median threshold near that of averaging nine 2 s powers (band equality for the latter). The wide spread across real passes matters more here than the difference of those medians. Individual ADS-B replay thresholds (`$DOPPLERTRACK_DATA/runs/2026-11-04-real-pass-seattle-replay/results-whitened-adsb.csv`) · Results with the hand-traced pitch supplied (`$DOPPLERTRACK_DATA/runs/2026-11-04-real-pass-seattle-replay/results-whitened-ridge.csv`)

## Why two seconds is a different reference point

For a tone with fixed but unknown phase, an ideal complex quadrature detector gives a noncentrality parameter λ = 2η C BT (P_aircraft,band / P_noise,band). This uses a locally flat, one-sided noise spectrum, an unweighted rectangular interval of duration T, band width B, fraction η of the aircraft band power in the modeled tone, and phase-match power fraction C. With colored noise the optimal detector weights frequencies by the inverse noise spectrum. The detection probability and false-alarm criterion determine the required λ. A broader search over frequency, timing, trajectories and receiver locations also changes the threshold. Kay, *Detection Theory*, §§4.3 and 7.6 (`$DOPPLERTRACK_DATA/reference/pdf/kay-1998-ssp-vol2-detection-theory.pdf`)

Comparing 18 seconds to 2 seconds yields +9.54 dB of energy for a perfectly coherent, known shape at fixed per-template operating point. In geometric spreading this corresponds to 3× distance. Integrating the powers of nine independent 2 s blocks gives approximately +4.77 dB or 1.73× distance under the weak-signal approximation. Its finite-sample gain also depends on the threshold and target detection probability. For an uncompensated constant frequency error the coherent power fraction is sinc²(π Δf T), with sinc(x) = sin(x)/x. At 18 s half power occurs at 0.0246 Hz. A frequency search can recover that constant offset. Residual changes in RPM, path length or sound propagation still cause phase loss.

## Injected tones on the original reference background

The input was a band-limited reference recording. The tests digitally add a tone following the retarded-time phase of a 60 m/s straight pass at 2 km slant CPA. The 2 km is a template shape, independent of the injected signal amplitude. The correct trajectory and time were supplied. Source frequency was searched within ±1 Hz. The statistic divides maximum in-bank power by median power in adjacent frequency-template sidebands. All detectors were calibrated to a nominal 1% false-alarm probability per opportunity. Calibration used 46 disjoint noise intervals with nine carrier frequencies each. The 47 held-out 18 s intervals came from later in the same recording. Sixteen phase replicates per interval do not create more independent noise intervals.

At a 90% hit target, thresholds on the 1 dB injection grid were as follows for the exact synthetic shape. A hit means some frequency in the correct geometry’s search bank crossed threshold.

| Detector | Required tone RMS level | Tone power below 160 Hz third-octave background |
|---|---:|---:|
| 2 s coherent waveform | −93 dBFS | 5.54 dB |
| 8 s coherent waveform | −97 dBFS | 9.54 dB |
| 18 s coherent waveform | −100 dBFS | 12.54 dB |
| Nine 2 s blocks with powers averaged | −95 dBFS | 7.54 dB |

The background was −87.458 dBFS in the 160 Hz band. The searched 2 s and 18 s waveform detectors each had one positive noise-only trial in 47 held-out opportunities. The 8 s detector had two, and block-power integration had zero. These small counts do not establish a common blind-search false-alarm rate per hour. The exact-shape 18 s detector was 7 dB more sensitive than the 2 s matched detector under this calibration. The 2 s comparator also uses waveform phase within its span. The [existing Oyster Bay warp experiment](2026-11-04-warp.md) pooled spectra from short blocks and found little separation from the best wrong location under the strict warp. It did not test this long coherent detector. Injection source and recovery curves (`$DOPPLERTRACK_DATA/runs/2026-11-04-seattle-matched-injection/results.json`)

The paired drift run used the same eight synthetic, smoothly varying pitch errors for each detector (0.2 Hz RMS, 3 s correlation time). The searched 2 s, 8 s and 18 s coherent thresholds became −92, −95 and −96 dBFS. Nine phase-independent blocks needed −93 dBFS. An 18 s, single-harmonic comparison using the project's 2.048 s Hann spectrogram, 0.25 s hop and 600 s median whitening needed −93 dBFS for both the perfectly modeled and the drifting tone. The 18 s waveform detector therefore gained 7 dB and 3 dB, respectively, relative to that spectrogram comparison. The comparison averages brightness at frame times with the whitening baseline held fixed. The full production fit also interpolates on a different time grid, explores geometry and may score multiple harmonics. Paired waveform results (`$DOPPLERTRACK_DATA/runs/2026-11-04-seattle-matched-paired/results.json`) · Spectrogram comparison (`$DOPPLERTRACK_DATA/runs/2026-11-04-seattle-matched-paired/brightness.json`)

## Converting a measured tone threshold to a band-power threshold

If the detectable tone lies D dB below the reference band background and comprises fraction η of the aircraft power in that same band, the net credit versus band equality is G = D + 10 log10(η). For the exact 18 s injection at 160 Hz, D = 12.54 dB. When the tone carries 10% of aircraft band power this buys 2.54 dB. At 50% it buys 9.53 dB. A tone carrying less than about 5.6% would need more total band power than the old equality point at this operating point.

To show the effect of restricting the calculation to the band actually tested, the following scenarios permit **only** the 160 Hz band for every aircraft, even when it has a stronger band elsewhere. Aircraft spectral models supply total band levels. Neither a fleet-wide fraction η nor a universally present tone at that frequency was measured.

| 160 Hz scenario | Daytime | Overnight | C172R median departure |
|---|---:|---:|---:|
| Equality in this band alone | 0.0473% | 0.0038% | 0.33 km |
| 10% tone fraction, 2 s exact synthetic track threshold | 0.0109% | 0.0011% | 0.20 km |
| 10% tone fraction, 18 s exact synthetic track threshold | 0.102% | 0.0082% | 0.44 km |
| 50% tone fraction, 2 s exact synthetic track threshold | 0.102% | 0.0082% | 0.44 km |
| 50% tone fraction, 18 s exact synthetic track threshold | 0.626% | 0.0506% | 0.93 km |

## Phase consistency on recorded aircraft

On 28 eligible Livermore recordings with 18 s around fitted CPA and a tracked frequency between 50 and 440 Hz, the known ADS-B shape, previously fitted timing and frequency, plus an additional ±2 Hz frequency search yielded median 18 s phase concentration 0.363. Its interquartile range was 0.279–0.417. The same calculation with a published hand-extracted frequency ridge gave median 0.425. With the extra frequency search disabled the medians were 0.110 and 0.115. This diagnostic divides the squared magnitude of the mean of nine complex 2 s coefficients by the mean of their squared magnitudes. Perfectly aligned, equal-amplitude blocks give one. Independent random phases at a prespecified frequency give an expectation of one-ninth. Searching frequency raises the noise result, and amplitude variation also affects the ratio. The concentration cannot by itself supply a detection credit. Most of the labeled harmonics were above 200 Hz. The sample includes one jet and cannot supply a U.S. fleet estimate of η at 160 Hz. Livermore calculations (`$DOPPLERTRACK_DATA/runs/2026-11-04-real-tone-coherence/README.md`)

The [housing and outdoor-time follow-up](2026-11-04-indoor-outdoor-coverage.md) applies the equality and replay thresholds to realistic house transmission, hourly activity and geographic outdoor noise scenarios.

## Reproduction

The [coverage calculation](../../tools/experiments/2026-11-04/integration_coverage.py) reads the cached 2025 flight snapshots, Census centroids, terrain and time zones from the prior residential experiment. Give it the ICAO catalogue, original pilot folder, EASA ANP 2.3 ZIP, a new output prefix, then scenarios of the form `name,band,net_dB_credit`. The run at `$DOPPLERTRACK_DATA/runs/2026-11-04-us-doppler-integration-coverage/` includes aircraft-by-power radii and counts at all 288 instants. The original [aircraft spectra and background levels](2026-11-04-us-movement-pickup.md) and [population and traffic sources](2026-11-04-us-residential-aircraft-coverage.md) still apply.
