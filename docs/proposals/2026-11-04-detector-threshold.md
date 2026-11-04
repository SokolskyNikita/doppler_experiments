# The detector's statistic, threshold and band (proposal)

PLAN Phase 2 item 6: the band and the threshold curve. This is a design, written before any code or run.

**decision:** whether `detect`'s statistic, threshold and band change.

## Why now

The collective find takes the top k = 10 detected windows per recording, so the detector's false-alarm rate and
its recall on weak passes decide what the find has to work with. The measured starting point (PLAN item 6, from
the [tier1](../experiments/2026-11-04-tier1.md) background spans) is that the shipped score doesn't separate
flyovers from background at any threshold:
- 7.2 countable hours with no propeller pass raise 30.6 false alarms per hour at min_score 0, 1.0 at 6 and 0.3
  at 7.
- The two nulls differ: Essex's jets top out at 6.8, while AeroSonicDB's soundscape keeps tones up to 14.8.
- The flyovers `detect` does find score 4.28 and 2.46.

## 1. The statistic

- **S₀, today.** For the best ideal curve in the window, the sweep-weighted mean of ridge contrast at 80 points in
  time, in dB. Its noise spread depends on how many independent frames the curve spans, which the mean ignores. A
  short curve in an empty window and a long one through a busy window are put on one scale only by accident.
- **S₁, the w-weighted sum.** The same curve and the same contrast c_k, evaluated at the spectrogram's frames k
  along the curve, with the sweep weights a_k:

  S₁ = Σ_k a_k c_k / (σ_c · √(Σ_k a_k² / w)),

  where w is Harris's overlap weight (0.254 at today's window). σ_c is the frame's contrast spread in noise,
  estimated per window from the robust spread (MAD) of the same contrast at frequencies off the curve. S₁ is a
  z-score: in noise it has unit spread whatever the curve's length, the window's clutter or the frame overlap.
  This is the one place in the pipeline where item 3's overlap finding pays.
- **Search unchanged.** The grid search and Nelder–Mead still maximise S₀'s objective, so the fits are unchanged.
  S₁ is computed on the fitted curve and replaces only the score that ranks and thresholds. A statistic maximised
  over the grid would carry the search's ln L into the threshold; this one carries it once, through the threshold
  set on the null below.

## 2. The threshold

- **Synthetic ROC first,** on 4xlarge boxes sharded by setting, with item 5's machinery: 2 h of white noise and
  delay-synthesised passes (three geometries, three seeds, amplitudes 0.06, 0.03 and 0.015, and f0 up to 800 Hz
  for the band question). For each setting the outputs are the detection probability against false alarms per
  hour, and the threshold at 1 per hour.
- **Then the real null:** Tier 1's background spans (Essex 3.3 h, AeroSonicDB 3.8 h), with `--shards 11`. The
  threshold for each setting is the score that gives 1 false alarm per countable hour on the two pooled,
  reported per null as well. A threshold set on the jets alone would pass the soundscape's tones.

## 3. The band

*Amended before any run:* `detect`'s band is the fundamental band. Today's raw-audio profile searches 60–300 Hz
fundamentals on the 40–450 Hz image, so the bands are B0 = 60–300 Hz on the 40–450 Hz image (today), B1 = 60–900 Hz
on a 40–1000 Hz image, and B2 = 60–300 and 300–900 Hz searched apart. The gate's low passes are those with
f0 ≤ 300 Hz. The original draft's 40–450 and 450–900 read the image's range as the search band.

- **B0, today:** 40–450 Hz.
- **B1:** 40–900 Hz in one search, on a spectrogram to 1 kHz (PLAN item 6: 40–450 makes 8 of 40 Livermore passes
  invisible and truncates 9 more; rest frequencies go up to 868 Hz). It tests more hypotheses, so it needs a
  higher threshold for the same false-alarm rate.
- **B2:** 40–450 and 450–900 Hz searched separately, each with its own threshold at 0.5 per hour, so the low
  band's threshold doesn't pay for the high band's hypotheses.
- **Livermore recall.** Detection on each of the 40 Livermore passes at each setting's threshold is reported. It
  is a recall measure only, since those recordings hold one pass each and give no false-alarm count.

## Settings and gate

The six settings are {S₀, S₁} × {B0, B1, B2}.

**Synthetic gate, fixed now.** A setting goes on to Tier 1 if, at 1 false alarm per hour on the synthetic noise:
- its detection of the 0.03 passes with f0 ≤ 450 Hz is no lower than S₀/B0's;
- for B1 and B2, it also detects at least half of the 0.03 passes above 450 Hz.

S₀/B0 always goes on as the baseline.

## Criterion

From PLAN item 6, on Tier 1, each setting at its own real-null threshold:
- **Background:** at most 1 false alarm per countable hour on the pooled background spans.
- **Positives:** the matched windows on Tier 1's positive spans stay at today's count (2: Oyster Bay's and the eagle
  cam's labelled flyovers).
- **Development events:** every labelled development event's window is retained among the top k = 10 detections
  of its span.

**Also:**
- **One counted retune** after the first result, written down before it runs.
- **Several settings passing:** S₁ over S₀ (it is the calibrated one), then the narrower band.
- **Reported:** Livermore recall, the per-null rates and the score each labelled flyover gets.
- **What a change invalidates:** a change to `detect` invalidates the detections cache and Tier 1's span records
  (re-run, not edited); the saved fits are untouched.

## Retune 1 (counted, written before it runs)

The first gate: S₁ stopped. Its threshold at 1 false alarm per hour on noise was 9–11, not the ~2 a unit-spread
score predicts. Two things made its spread wrong:
- S₁ is unit-spread for a fixed curve, but the search maximises S₀ over many curves, so the winner's S₁ carries
  the best-of-many tail;
- its null level σ_c was unstable: the robust and the cross-window estimates differ by more than 20 % on 33–41 %
  of events.

**S₂ replaces σ_c with the null of the maximum** (Kay II's ln L; the same principle as the verdict null one level
up). For each event, `fit_event` (the same grid search and Nelder–Mead that `detect` refines with) runs on K = 8
null copies of the event's window and band, and S₂ = (S₀ − μ) / σ, where μ and σ are the mean and spread of the 8
null maxima.
- **The null copies** are the window reversed in time, then circularly shifted by i/8 of its length for
  i = 0..7.
- **Why reversal.** Reversal keeps every steady tone, burst and level, but turns a falling Doppler curve into a
  rising one that the model can't fit. It is the time-reversed control PLAN item 6 lists (echotrace).
- **Why not a frequency shift**, as the earlier note said: a Doppler curve shifted in frequency is still a Doppler
  curve at another f0, so the search would find the event again.

S₂ is computed by `tracks.rescore_null`, kept apart from `detect_events` so that the detections cache stays valid.
The settings are S₂ × {B0, B1, B2}, on the same synthetic data.

*Amended before any run.* The Tier 0 test of the eight-copy null gave S₂ = 6 on pure noise. Eight circular shifts
of one 180 s window share most of their content, so their maxima are strongly correlated and their spread is far
too small. One window gives one independent null sample. So:
- D = S₀ − (`fit_event`'s maximum on the window reversed in time), the event against its own window's clutter;
- S₂ = (D − μ_null) / σ_null, with μ_null and σ_null the mean and spread of every null candidate's D: the 2 h of synthetic noise in the ROC, and
  the pooled background spans in Tier 1.

`tracks.rescore_null` returns D. The criterion below is unchanged.

**The retune's criterion,** fixed now (the gate's second half is unchanged):
- **Threshold calibration.** S₂'s threshold at 1 false alarm per hour lands within a factor of 1.5 of the
  unit-spread prediction, Φ⁻¹(1 − 1/n), where n is the noise candidates per hour that `detect` returns (the
  prediction is computed from the run's own n and reported).
- **Detection.** At the gate's amplitude, its detection counts are no lower than S₀'s: f0 ≤ 300 Hz for all three
  bands, and above 300 Hz for B1 and B2.

Tier 1 then runs, with `--shards 11`, for every setting past the gate, plus S₀/B0, S₀/B1 and the 300–900 Hz half,
to set the band from its false-alarm cost.
