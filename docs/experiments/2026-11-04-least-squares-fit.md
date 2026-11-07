# Least-squares fit of a frequency track

<!-- index
question: Does a least-squares fit of a frequency track give smaller f0, speed, distance and timing errors than today's fits (item 4)?
outcome: Not met; deferred until a track meets item 3's criterion: it beats both objectives on speed and slant range, not on f0 or timing
-->

> **Documentation privacy correction, 2026-11-04.** Personal provenance and internal attribution
> are neutralized; numerical outcomes and artifact identifiers are retained. The original is privately
> hash-preserved at source revision `17758a5`, SHA-256 `b5ba7610af8682a1d37c20ee00c88bbacadba05fdf41f2be0131ab208571e22c`.

> **Research reset provenance note, 2026-11-04.** The failed f0/timing criterion stands. Saved
> livermore_summary.json contains NaN slant-range medians; the record's stated convention of counting
> nonfinite fits as infinite error reproduces the printed primary medians (16.7% ordinary,15.2% weighted) from
> livermore.json. Treat the narrative convention and raw per-fit values as explicit provenance, not as a
> finite value present in that saved summary. See [the audit](2026-11-04-research-reset.md).

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

Script: [`lsfit_compare.py`](../../tools/experiments/2026-11-04/lsfit_compare.py). Outputs in
`$DOPPLERTRACK_DATA/runs/2026-11-04-least-squares-fit/`.

**Run 1, set aside as a bug.** `ridge_track` padded its band by 30 % on each side, copying `fit_event`'s
crop. But `fit_event` keeps its curve inside the band and `ridge()` takes the strongest path through
whatever it is given, so it locked onto lines outside the stated band: 100–148 Hz on R06 for a 156–344 Hz
band. The least-squares f0 errors came out at a median 33 %.
- This broke the criterion's own definition ("the same window and band"). The fix (`51f59ce`) crops the
  band exactly, is tested without real data (a strong line just outside the band), and changes no knob.
- So it isn't counted as the retune. Run 1's outputs are kept as `run1_padded_band_*`.

Before run 2 was read, `t_c` was reparametrised relative to the track's first point (`cfd466a`), after
the geometry study found least squares stopping early on unix-scale times. Refitting all 44 tracks of run 2 with both
versions changed no parameter by more than 2 × 10⁻¹³ relative or 10⁻¹¹ s (`lsfit_reparam_check.py`,
`reparam_check.json`), so run 2 stands.

**Run 2, Livermore.** Median absolute relative error against the reference. A fit whose speed falls
outside 0 < v < c has no distance and counts as an infinite error:

| | f0 | speed | slant range | not identified |
|---|---|---|---|---|
| 29 primary passes | | | | |
| brightness | **1.13 %** | 9.8 % | 18.6 % | – |
| contrast | 1.28 % | 12.3 % | 27.1 % | – |
| least squares | 1.70 % | 9.6 % | 16.7 % | 2 |
| least squares, weighted | 1.34 % | **6.7 %** | **15.2 %** | 2 |
| 11 flagged passes | | | | |
| brightness | 3.1 % | 21.6 % | 9.1 % | – |
| contrast | 3.3 % | 17.2 % | 15.4 % | – |
| least squares | 10.3 % | 61.4 % | 78.2 % | 2 |
| least squares, weighted | 12.5 % | 63.7 % | 92.8 % | 5 |

- **Criterion 1: not met.** Both variants beat both objectives on speed and slant range, but neither on f0.
- **Residuals.** OLS residuals call for no robust loss: no primary pass has more than 2 % of points beyond
  4 robust SDs.
- **Speed and distance are strongly coupled**, as 6.1 says: the median speed–distance correlation is 0.96
  (OLS) and 0.98 (weighted) on the primary passes.
- **The two failures** (R12, R45) fit a rising curve (v < 0), with f0 12–23 % low. `ridge()` followed
  another line in the band; the fit then did what it was given.
- **The flagged passes** are far worse than either objective, not merely no better. `ridge()` wanders on
  manoeuvring passes (15 % median frequency error in [freqtrack](2026-11-04-freqtrack.md)), and a track
  that leaves the pass drags the whole-curve fit with it.

**Run 2, development recordings.** Heard-CPA gap error, event 2 against event 1, with both events fitted
by the same method. True gaps: 922.96 s and 331.61 s.

| | Oyster Bay | Eagle cam |
|---|---|---|
| brightness | −5.0 s | +29.8 s |
| contrast | −9.0 s | +6.3 s |
| least squares | +16.8 s | +27.5 s |
| least squares, weighted | no heard CPA (v < 0 on event 2) | no heard CPA (v < 0 on event 2) |

- **Criterion 2: not met** on either recording.
- **Event 2's OLS fits are slow and close on both recordings:** 52 m/s at 457 m, and 42 m/s at 424 m.
  Their weighted fits rise. In windows of 110–240 s holding other tones, `ridge()` follows the strongest
  path, and the weights favour exactly the stronger, wrong line.

**Outcome: not met; deferred until a track meets item 3's criterion.** The retune was not spent.
- **The weighted fit is the better measurement of speed and distance.** On the 29 primary passes it beats
  both objectives on speed and slant range by a clear margin: 6.7 % against brightness's 9.8 % and
  contrast's 12.3 %, and 15.2 % against 18.6 % and 27.1 %. It misses only f0 and the event-2 timing, and
  both failures are the track following another line: R12 and R45 among the passes, and event 2 on both
  development recordings. That moves item 3 up the route. A track that stays on the pass is what this fit
  needs, and it is what the comparison will be re-run on, with the criterion unchanged.
- **The estimator is right.**
  - It recovers noiseless passes exactly.
  - Its optimum matches a direct four-parameter fit, weighted and not.
  - It agrees with the geometry study’s independent implementation (`straight_pass_ls.py`) to 10⁻⁷ on ideal curves,
    and to a thousandth of its own SD on a noisy one (`tests/test_track_fit.py`).
  - the geometry study’s item 2 finds a straight-pass fit at the Cramér–Rao bound, with model error setting what real
    passes allow.
- **The prediction** held on the straight passes for speed and distance, not for f0. On the flagged passes
  and the development recordings it was too kind: there the fit is only as good as `ridge()`'s track, and
  `ridge()` leaves the pass.
- **Kept as library code**, not wired into `detect`: `fit_track`, `ridge_track` and `Track`.

**Changes after run 2 was read.** The re-run after item 3 counts these together as its one change.
- **The positive-speed bound.** It was in PLAN item 4's safeguards ("physical bounds on speed and
  distance") and was missing, as the rising fits showed. The reduced fit now enforces β ≤ 0 inside the
  variable projection: where the best unbounded β would be positive, the bounded optimum is a flat line.
  A time-reversed pass now fits as flat and not identified, never with a negative speed.
- **A polish of the best optimum.** `least_squares`, to numerical precision, which the agreement test with
  the geometry study’s fit needed: Nelder-Mead alone stopped at about 10⁻⁷ relative on ideal curves.
- **Their effect on run 2's tracks** (`bound_polish_change.json`, parameters only):
  - The bound changes exactly the 8 fits that rose (6 Livermore fits, and the two weighted event-2 fits).
    They now fit flat or barely falling curves on the same wrong line.
  - The polish moves the other 80 by at most 1.2 × 10⁻⁵ relative and 3 × 10⁻⁵ s.
