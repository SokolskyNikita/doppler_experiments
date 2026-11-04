# Least-squares fit of a frequency track

## Question and criterion

PLAN Phase 2, item 4 (E1, E3). Does fitting the straight-pass model to a frequency track by least
squares give smaller f0, speed, distance and timing errors than today's brightness and contrast fits of
the spectrogram? Written, with the prediction below, before any real data was fitted.

**Criterion.** A least-squares variant meets it if both hold:
1. On Livermore's 29 primary passes, its median absolute relative errors in f0, speed and slant range
   against the trajectory-derived reference are each no larger than the better of the brightness and
   contrast fits' median for that quantity, on the same windows and bands.
2. On each development recording, Oyster Bay and the eagle cam, its event-2 heard-CPA timing error is no
   larger than the contrast fit's.

The synthetic part of the item's criterion, that the reduced fit's optimum matches the full
four-parameter fit, is a test (`tests/test_track_fit.py`) and holds.

Ordinary least squares is judged first, amplitude weights second. A robust loss is tried only if the OLS
residuals call for one: more than 2 % of points beyond 4 robust SDs (1.4826 × MAD) on the 29 passes. At
most one retune after the first run, counted here.

**Definitions, fixed with the criterion.**
- **Livermore reference, per pass** (from the [Livermore audit](2026-11-04-livermore-audit.md)'s
  `passes.csv`, read, not changed): f0 is `f0_15C`, the scale that fits the trajectory curve to the
  published ridge. Slant range is `slant_m_15C`. Speed is the 3D speed of the PCHIP-interpolated KML
  trajectory at its emission CPA, the instant of least range to the reconstructed microphone, computed
  as the audit's `heard_curve` interpolates.
- **Livermore windows and bands**, the same for every method and as the
  [frequency-track experiment](2026-11-04-freqtrack.md) set them:
  - the window is the published ridge's span;
  - the band is the reference's range over it, 0.85× to 1.15×;
  - the spectrogram is the package STFT at 4 kHz (2.048 s Hann, 0.25 s hop, 40–1900 Hz);
  - one harmonic;
  - c at 15 °C, as in the reference.
- **The methods.**
  - Brightness and contrast are `fit_event` with `objective="brightness"` / `"contrast"`.
  - Least squares is `fit_track` on `ridge_track` over the same window and band, OLS and amplitude-weighted.
  - Every fit counts, including those flagged as not identified; the flagged count is reported.
- **Development recordings.**
  - Oyster Bay: the README windows and bands, event 1 2090–2200 s at 95–200 Hz and event 2 3020–3130 s at
    95–195 Hz. The objectives use the README's harmonics (2 for event 1, 1 for event 2); least squares
    tracks the fundamental in the same window and band.
  - Eagle cam: `detect`'s ranks 5 and 13 in `docs/results/swfl_detected.json`, the windows `detect` gave
    them, and bands of 0.85 × f_post to 1.15 × f_pre of `detect`'s fit, with one harmonic.
- **Event-2 heard-CPA timing error.** The recordings have no independent clock, so it is the error in
  the heard-CPA gap between events 1 and 2, both fitted by the same method:
  (t_cpa₂ − t_cpa₁) − the true gap. The true gaps are 922.96 s for Oyster Bay and 331.61 s for the eagle
  cam, from the trajectories ([timing-conventions](2026-11-03-timing-conventions.md)).
- **Reported but not judged.**
  - The 11 flagged Livermore passes, separately.
  - Each fit's speed–distance correlation (for item 7) and its diagnostics.
  - Emission-CPA and steepest-fall gap errors on the development recordings.

**Fixed knobs**, set a priori and unchanged unless the one retune says otherwise:

| Knob | Value | Why |
|---|---|---|
| starts, t_c | 24 over the track's span ± half of it | a partial track's CPA can lie outside it |
| starts, s | 24, log-spaced over the speed (10–300 m/s) and distance (100 m–30 km) bounds | `fit_event`'s bounds |
| refined starts | the 5 best grid cells, Nelder-Mead on (t_c, log s) | variable projection keeps local optima |
| `LS_Z_SPAN_MIN` | 0.5 | below half of z's range, α and β are confounded |
| weights | amplitude², amplitude = 10^(dB/20) of the whitened level on the ridge | Quinn 1995 |

## Prediction

PLAN 6.1 says a whole-curve fit uses the whole sweep, while the brightness objective weights the flat tails
as much as the sweep and the contrast objective weights the sweep but scores an image. So:
- **Livermore.** On the 29 primary passes, least squares should beat both objectives on all three
  quantities. On the 11 flagged passes (turns, climbs, a jet), it should do no better than the better
  objective, since the straight-pass model is wrong there whichever way it is fitted.
- **Development recordings.** Less confident. Oyster Bay's event-2 bias (f0 5–11 % high) persisted under
  both objectives, and the true straight pass fitted its window worse than either free fit
  ([event2-bias](2026-11-03-event2-bias.md)). That points at the curve, not the objective, so least squares
  may share the bias. My prediction is an event-2 gap error under the contrast fit's −9.0 s on Oyster Bay,
  and about the same as the contrast fit's on the eagle cam.
- **Weights.** Amplitude weighting should help most on the long, faint tails of distant passes.

## Results

Pending.
