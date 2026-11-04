# Livermore corpus: provenance audit (2026-11-04)

<!-- index
question: Can the Livermore microphone and start times be recovered, and do ridge, WAV and ADS-B agree in time?
outcome: Yes: the author's recorder point to under 1 m, WAVs are the ridge ±5.00 s, and the ridge clock matches ADS-B to about 1 s per pass with no common offset beyond 0.5 s
-->

**Question.** The Livermore corpus (Pathak 2026, [Zenodo 23424278](https://zenodo.org/records/23424278), CC BY 4.0) is meant to be Phase 2's main real data for fits and tracks ([PLAN](../../PLAN.md) 5.6, Phase 2 item 2). It doesn't publish the microphone position or the WAVs' start times. Can both be recovered, and do the published frequency tracks, the WAVs and the ADS-B tracks agree in time?

**Setup.** No change to the package. `tools/data/site_traffic.py` gained optional elevation and recording-window columns in the same commit; its output columns changed with it: the hard-coded `title`, `time_setting` and `zips` became pass-through extras, so `derived/eclipse/site_traffic_2024-04-07.csv` has the old header. All 40 passes, from the four zips unpacked into `$DOPPLERTRACK_DATA/derived/livermore/`. Each pass has `audio.wav` (48 kHz mono, no metadata chunk), `frequency_vs_time_used.csv` (the author's ridge of one harmonic, UTC, about one point per 0.19 s), a KML track (positions only, EGM96 MSL), and a row of `final_results_40_cases.csv` with L (the horizontal distance from the recorder to the track at closest approach) and H (the track's height above the recorder there). The author's extraction tool (`frequency_extraction_tool.html`) reads the recording's start time from the phone's file name, so the ridge clock is the phone clock, to the second.
1. **Microphone.** This finds the point whose horizontal distance to every KML polyline matches its L. It uses robust least squares (soft L1, 50 m scale) from the ten best cells of a 500 m grid, and refits any pass more than 150 m off as a second site. Height is the median of track altitude minus H. The same method as unheard's `trilaterate` and dopplerprint's corpus builder, reimplemented.
2. **ADS-B clock against the ridge clock.** At the reconstructed point, this takes the curve heard from the trajectory: PCHIP through the KML points, emission-time kinematics (`curve_from_trajectory`), c at 15 °C. It is shifted in time and scaled in f0 to fit the published ridge by least squares. The shift is the ridge clock minus the ADS-B clock: a common clock error appears as one offset, misaligned clips as scatter. Sensitivities: linear interpolation instead of PCHIP, and c at 25 °C. The steepest-fall times of both curves are also compared, as asked, and turn out to be a poor measure here.
3. **WAV start.** This is the start that lays the UTC ridge on the WAV's own whitened spectrogram (±2 bins, every 10 ms). The first and last halves of the ridge are also aligned separately, to bound any stretch.

**Numbers.**

Microphone:

| | Main site | Second site |
|---|---|---|
| Passes | 37 | 3, all on 2026-05-09 (R08, R44, R45) |
| Residual to L, RMS (max) | 0.57 m (1.21 m) | 0.003 m (exactly determined but one) |
| Position 1σ (east, north), formal | 0.16, 0.12 m | 0.02, 0.005 m |
| Largest leave-one-out move | 0.08 m | 0.09 m |
| Height, MSL, from H; spread over passes (IQR) | 153.24 m; 0.013 m | 110.53 m; 0.029 m |
| Terrarium ground at the point | 148.1 m | 109.5 m |
| Distance to dopplerprint's published point | 2.3 m | 7.9 m |

The two sites are 6.6 km apart. The coordinates are in the run folder's `sites.json`, not here: unheard keeps them out of its repository because one may be a private address.

Clock shift, on the 29 passes whose trajectory curve fits the ridge within 1.6 % RMS of f0:

| | Median | Robust SD | IQR |
|---|---|---|---|
| Shift, PCHIP, 15 °C | −0.44 s | 1.07 s | −1.09 to +0.28 s |
| Shift, PCHIP, 25 °C | −0.44 s | 0.85 s | −1.35 to 0.00 s |
| Linear minus PCHIP | +0.02 s | 0.28 s | −0.17 to +0.21 s |
| Ridge steepest fall minus model steepest fall | −1.8 s | 6.7 s | −4.8 to +2.7 s |

| Day | 05-09 | 05-13 | 05-14 | 05-16 | 05-17 |
|---|---|---|---|---|---|
| Passes, median shift | 2, −1.01 s | 2, +0.21 s | 3, −0.28 s | 9, −0.53 s | 13, −0.44 s |

- **Scatter.** Three good fits have |shift| > 2 s: R49 −2.6 s, R17 +3.1 s, R46 −2.2 s. Two of those are passes at 3.9 and 5.7 km.
- **Unrelated quantities.** The shift is uncorrelated with the largest KML gap near CPA (r = 0.09) and with the paper's `timing_difference_s` (r = 0.25).
- **KML sampling.** Across CPA the KML points are sparse: the largest gap within 30 s of the emission CPA is 12.6 s at the median (IQR 8.9–16.0 s).
- **Poor fits.** The 11 passes with an RMS of 1.6 % or more are R37, R41, R44, R15, R36, R07, R21, R16, R03, R50 and R51 (1.65 to 5.74 %). Two of them have unstable shifts:
  - R03: −9.6 s with PCHIP and +0.1 s with linear interpolation, because PCHIP overshoots across a KML gap at CPA.
  - R50: +3.7 s, a jet at 5.1 km.

WAV start, all 40:
- **Pads.** The first sample is 4.99 s before the first ridge stamp (median; robust SD 0.03 s), and the last is 5.01 s after the last.
- **Start outliers.** Four starts are off 5 s by more than 0.1 s: R06 4.49 s, R05 4.75 s, R46 5.17 s, R41 6.81 s. R05 and R46 have among the weakest alignment contrasts in the set (1.5 and 1.3).
- **Long tails.** Five WAVs run on past ridge + 5 s: R41 by 22.3 s, R59 60.2 s, R01 8.2 s, R06 5.9 s, R05 5.3 s.
- **Stretch.** Aligning the two halves separately agrees within 0.7 s wherever the contrast is above 2.5, and to 0.04 s at the median.

**Outcome: usable as Phase 2 fit data, with the clock as a nuisance parameter.**
- **Microphone.** The point the author computed L from is recovered to a fraction of a metre, and its height is a single value the author used for every pass. That is the author's coordinate. How far the phone actually was from it can't be recovered from the corpus. Its height sits 5.1 m above Terrarium ground (1.0 m at the second site), so dopplerprint's ground + 1.5 m is 3.7 m lower than the author's. The 05-09 passes were recorded elsewhere, as both projects found, and should carry their own site.
- **The clips are aligned, not scattered.** Every WAV is the ridge's span plus 5 s either side, so its first sample is the first ridge stamp less 5.00 s on the phone clock, to a few hundredths of a second.
- **The ridge clock agrees with ADS-B to about a second per pass, with no common offset beyond half a second.**
  - The median of −0.44 s ± 0.20 s (standard error) is what truncating the file-name time to the second predicts, which puts the stamps 0 to 1 s early.
  - The per-day medians stay within −1.0 to +0.2 s.
  - The ±1 s spread per pass is about what a 1 s file-name clock plus 8–16 s KML gaps across CPA would give. The corpus can't separate those two: neither the interpolation method nor the gap size explains it.
- **What that limits.** Fits of f0, speed and slant range can use the corpus directly. Anything that measures timing below a second can't use the ridge's absolute time:
  - Phase 2 item 1's measurement of the steepest fall against the geometric CPA;
  - tests of the pairing gate.
  Such experiments should fit a per-pass time shift. Phase 2's model-error experiment should report its interpolation sensitivity, because the KML is a sparse track.
- **Steepest-fall times are not a usable check here.** On real trajectories the model's own steepest fall sits a robust SD of 6 s from its emission CPA, and ridge noise widens that. Many passes are turning or far enough to be nearly linear over the ridge. The whole-curve fit is the measurement to use.
- **The 11 poor fits are kept and flagged, not dropped.** They are the passes where the trajectory and the ridge disagree most, so they are candidates for Phase 2's model-error set (turns, climbs, a jet). R03 and R50 can't support a clock estimate at all.
- **Group.** One group, development only, as PLAN 5.6 says. The second site doesn't make it two groups: same phone, recorder and month.

**Script:** `tools/experiments/2026-11-04/livermore_audit.py`. **Outputs:** `runs/2026-11-04-livermore-audit/` (`sites.json`, `passes.csv`, `summary.json`, one overlay per pass in `passes/`, `audit.log`). The two earlier runs in `runs/2026-11-03-livermore-audit*/` came from drafts of the script with a broken steepest-fall window and are superseded.
