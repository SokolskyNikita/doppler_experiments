# Frequency tracks with an off state

## Question

PLAN Phase 2 item 3. Does a local tracker beat `tracks.ridge()` against the trajectory-derived
reference on the Livermore passes? The tracker is a Viterbi with an "off" state and birth and death
penalties. Each frequency is measured below the bin width on the original STFT, and segment rules and
harmonic links are applied as separate steps.

Criterion, fixed before anything ran: on the 29 primary passes, at 2 % tolerance, lower median frequency
error than `ridge()`, with no more false bridges and no more fragments.

## Setup

- **Code.** New module `src/dopplertrack/freqtrack.py`; `tracks.py` is untouched.
  - **Finding.** A Viterbi runs over each frame's 8 strongest local maxima of the whitened, unclipped
    image (`local_whiten(..., floor=-inf)`), plus an off state. A cell's reward is its level less θ.
    Transitions:
    - off to peak: −birth;
    - peak to off: −death;
    - peak to peak: −0.1 dB per bin, capped at 0.25·f per second (PLAN 6.1, v ≤ 110 m/s, R ≥ 150 m).
  - **Invalid frames.** The path crosses them with no measurement, for up to 5 s.
  - **Several tracks.** Paths are taken in turn, each one's cells (±2 bins) removed before the next.
  - **Measuring.** Each point is refined on the original STFT (`SampleSTFT`, the samples on the
    Spectrogram's frame grid) with quadratic, Candan or Quinn FTI(2) interpolation.
    - For a Hann window, Candan's ratio is exact as N grows: δ = 2·Re[(X₋₁ − X₊₁)/(2X₀ − X₋₁ − X₊₁)].
      Its coefficients go as 1/((δ−m)(1−(δ−m)²)).
    - Quinn's FTI(2) uses the unwindowed DFT of the same frame (Quinn 1995 §IV.B).
  - **Segment rules**, each a separate tested function:
    - weak run (cut);
    - rise and hop (a cut in run 1, a flag in run 2);
    - gap link;
    - crossing re-pair.
  - **Harmonics.** Overlapping tracks with a stable ratio near p/q (p, q ≤ 6) are linked. A group's
    orders are the smallest integers with gcd 1, so lines at 2, 4 and 6 read 1, 2 and 3.
  - **Future change.** The module docstring notes that the Spectrogram may later carry the un-whitened
    dB in place of the samples.
- **Reference**, one per pass and the same for every tracker. The curve heard at the reconstructed
  microphone from the KML trajectory (PCHIP, 15 °C), shifted and scaled by the clock shift and f0 that
  the [Livermore audit](2026-11-04-livermore-audit.md) fitted to the published ridge. Its span is the
  published ridge's span.
  - **Mild circularity.** The shift was fitted to the author's ridge, which is one tracker's output.
    So the reference clock is tied to that tracker to about ±1 s. The comparison is unaffected,
    because the error is in relative frequency, not timing.
- **Spectrogram.** The package STFT at 4 kHz: a 2.048 s Hann window, 0.25 s hop, default whitening,
  40–1900 Hz.
- **Band.** For the criterion, the oracle band per pass: the reference's range over its span, 0.85× to
  1.15×.
- **Trackers:**
  - (A) `ridge()` on `local_whiten` over the whole clip: the criterion baseline;
  - (A\*) `ridge()` on the published span only: its oracle best case, reported only;
  - (B) the new tracker over the whole clip;
  - (C) ssqueezepy 0.6.6 `extract_ridges` on |STFT|, with defaults and one ridge. It is Iatsenko's
    method and sits in the dev dependency group;
  - B over 40–450 Hz, the package band with no oracle band: informational only.
- **Metrics,** fixed before running, on frames inside the reference span:
  - **on:** |f − f_ref| ≤ max(2 bins, 2 % f_ref); 1 % and 4 % are also reported.
  - **pass tracks:** tracks with at least half their in-span points on. A, A\* and C always count
    their one path.
  - **error:** the median relative error over all in-span points of the pass tracks.
  - **false bridge:** an off-run of 1 s or more in a track that holds an on-run of 1 s or more.
  - **fragment:** a hole of 1 s or more in the union of on points.
  - Informational, added before run 2: holes of 3 s or more, coverage (on frames as a share of the
    span), and the tails missed.
- **Passes.** Primary: the 29 with audit fit RMS < 1.6 % of f0. The 11 flagged passes are reported
  separately.
- **Order of work.** Livermore was tracked once with the knobs below (run 1). After it, one retune was
  recorded and agreed, and run 2 used it. No other run looked at Livermore.

## Knobs

`TrackParams` has 23 fields. The 21 I quoted to the PM missed two: `exclusion_bins` and `max_tracks`.

| Knob | Run 1 | Run 2 | How it was set |
|---|---|---|---|
| `theta_db` | 9.5 | **9.0** | noise only (below) |
| `birth` | 6 | **20** | noise only (below) |
| `death` | 6 | 6 | a priori, the same as run 1's birth |
| `estimator` | quinn2 | quinn2 | synthetic chirps (below) |
| `peaks_per_frame` | 8 | 8 | a priori (Iatsenko works on peaks; 8 covers harmonics in a band) |
| `jump_cost` | 0.1 dB/bin | 0.1 | a priori, low enough that the physical cap, not the cost, limits a steep sweep |
| `max_rel_slope` | 0.25 /s | 0.25 | physics: PLAN 6.1's g_max/f0 at v ≤ 110 m/s, R ≥ 150 m |
| `max_bridge_s` | 5 | 5 | a priori |
| `exclusion_bins` | 2 | 2 | a priori |
| `max_tracks` | 12 | 12 | a priori |
| `min_track_s` | 1 | 1 | a priori |
| `weak_db`, `weak_run_s` | 3 dB, 3 s | same | dopplerprint's weak-run cut |
| `rise_bins`, `rise_window_s` | 4 bins, 3 s | same, as a flag | dopplerprint's rise cut |
| `hop_factor`, `hop_window_s` | ×4, 2 s | same, as a flag | dopplerprint's hop rule |
| `link_gap_s`, `link_tol_bins` | 5 s, 3 bins | same | a priori |
| `crossing_bins` | 1 | 1 | a priori |
| `harmonic_tol`, `harmonic_iqr`, `max_order` | 1 %, 0.5 %, 6 | same | a priori (hermes's small ratios) |

The module's defaults are run 1's (θ 9.5, birth 6, rise and hop cutting), its best measured
configuration; run 2's settings remain available through `TrackParams` and `flag=("rise", "hop")`.

So 4 knobs were derived and 19 were set a priori. The retune changed 2 knobs and 2 rules (rise and hop
from cutting to flagging). None of them was tuned on Livermore.

**Estimator** (`freqtrack_knobs.py`). The rule, fixed beforehand: the lowest RMS error over all frames of
synthetic tones and linear chirps, at −10 dB per-sample SNR, 5 seeds. RMS error in Hz:

| Hz/s | 0 | 0.5 | 2 | 5 | 10 | 20 |
|---|---|---|---|---|---|---|
| quadratic | 0.016 | 0.020 | 0.071 | 0.44 | 0.57 | 0.60 |
| Candan (Hann, 3 iterations) | 0.016 | 0.020 | 0.066 | 0.36 | 0.52 | 0.57 |
| Quinn FTI(2) | 0.011 | 0.015 | 0.153 | 0.39 | 0.48 | 0.50 |

Overall, Quinn is lowest (0.33 Hz, against 0.35 for Candan and 0.38 for quadratic), so it is the
default. Candan is best at 2–5 Hz/s. Above that, all three are limited by the window's smear of a fast
sweep (PLAN item 5).

**θ, run 1.** Two hours of white noise through the package STFT, a 100 Hz band, M 8, birth and death 6,
every rule cutting, 10 min windows. Tracks per hour per 100 Hz:
- θ 6 dB: 2,316
- θ 7: 1,464
- θ 8: 316
- θ 9: 14
- θ 9.25: 6
- θ 9.5: 1.0 (the chosen value)

The target was one false track per hour per 100 Hz. It holds only for this window, hop, band and M:
the rate grows with the cells searched (Kay II).

**θ and birth, run 2** (`freqtrack_retune.py`, the one recorded retune). The idea is hysteresis
through costs: a lower per-frame θ, made safe by a higher birth cost at the same false-track rate, with
death kept at 6. A tone that persists can then continue through weak frames, as the path sums over N
frames (Kay II §7.6).
- **Noise.** The same noise images, with rise and hop as flags. The smallest birth meeting the target
  at each θ:
  - θ 8 → birth 65;
  - θ 8.5 → 30;
  - θ 9 → 20;
  - θ 9.5 → 6.
- **No birth works below about 8 dB.** A first grid at θ 5, 6 and 7 was stopped: at birth 80 noise
  still gave 307, 143 and over 100 tracks per hour. Below the noise's own peak level, the best path
  through noise gains on average, so it repays any birth cost (`retune_grid1_stopped.log`).
- **Weak pass.** Two synthetic straight passes (f0 200 Hz, v 55 m/s, d 600 m; f0 120 Hz, 65 m/s,
  1500 m), 3 seeds each, scored like Livermore. The test amplitude was the lowest at which `ridge()`
  still covers at least 95 % of every span: 0.03 in 0.4 noise, since 0.02 drops its coverage to 0.36.
- **Pick.** At that amplitude, the fewest fragments, then the most coverage:
  - (9, 20): 27 fragments, coverage 0.79, the pick;
  - (8.5, 30): 28, 0.84;
  - (8, 65): 28, 0.82;
  - (9.5, 6): 28, 0.55.

## Numbers

### Livermore, 29 primary passes, 2 % tolerance

| | median error | false bridges | fragments ≥ 1 s | ≥ 3 s | coverage | tails missed |
|---|---|---|---|---|---|---|
| A `ridge()`, whole clip | 0.48 % | 36 | 12 | 4 | 0.97 | 0.01 |
| A\* `ridge()`, oracle span | 0.48 % | 25 | 14 | 6 | 0.97 | 0.01 |
| B run 1 (θ 9.5, birth 6, all rules cutting) | **0.45 %** | **13** | 204 | 76 | 0.50 | 0.14 |
| B, run 1 with rise as a flag (the agreed fallback) | 0.51 % | 24 | 164 | – | 0.58 | 0.14 |
| B run 2 (θ 9, birth 20, rise and hop flagging) | 0.60 % | 209 | 106 | 44 | 0.75 | 0.11 |
| C ssqueezepy | 14.3 % | 28 | 4 | 3 | 0.39 | 0.61 |

- **Run 1:** (error, bridges, fragments) = (met, met, **not met**). B beats A on 15 of 29 passes.
- **Run 2:** (**not met**, **not met**, **not met**). B beats A on 8 of 29.
- **At 1 % tolerance**, run 1 has B 0.37 % against A 0.48 %, with 57 bridges against 112 and 217
  fragments against 70.
- **The 11 flagged passes**, at 2 % (turns, climbs, a jet): run 1's B has 0.84 % error against A's
  15.0 %, with 16 bridges against 37. A and C wander off these passes; run 2's B has 1.27 %.
- **All 40, run 1:** B 0.53 % against A 0.57 %, 29 bridges against 73, 272 fragments against 32.
- **Runtime per pass** (median, max):
  - A: 0.009 s, 0.04 s;
  - B: 0.25–0.29 s, 0.55 s;
  - C: 0.12 s, 0.65 s;
  - B over 40–450 Hz: 0.27–0.31 s.

### Where run 1 fragments

Diagnosis after run 1, with no knob changed (`freqtrack_diagnose.py`):
- **Below θ.** At the reference cell, a median 41 % of the span's frames are below θ = 9.5 dB. The off
  state ends the track there, while `ridge()` is forced on and still finds the tone. With no segment
  rule at all, B has coverage 0.73 and 124 fragments.
- **Rule ablation**, as coverage / fragments:
  - all rules: 0.50 / 204;
  - without rise: 0.58 / 164;
  - without hop: 0.71 / 121;
  - without the weak-run cut or the gap link: unchanged.
- **Rise and hop cut true curves.** Both fire where the 2.048 s window smears a pass's steep part, so
  the measured frequency wobbles and jumps there. That is PLAN item 5's window-length issue.

### Rise and hop as flags

| | rise flagged | of them on the reference | hop flagged | on the reference | points |
|---|---|---|---|---|---|
| Livermore, run 1 knobs, all 40 | 11,172 | 3,956 (40 passes) | 8,765 | 3,274 (40 passes) | 48,881 |
| Livermore, run 2 knobs | 12,168 | 4,126 | 9,148 | 3,312 | 48,363 |

Blind clear events (`bench/labels`, no reference), run 2 knobs:

| event | tracks | points | rise flagged | hop flagged |
|---|---|---|---|---|
| ob-e03 | 60 | 865 | 201 | 129 |
| ob-e05 | 24 | 471 | 170 | 104 |
| ob-e08 | 63 | 1,072 | 395 | 239 |
| ob-e10 | 40 | 549 | 213 | 127 |
| sw-e07 | 33 | 532 | 99 | 90 |
| e740-e06 | 19 | 268 | 82 | 55 |

Run 1's knobs give similar counts (`freqtrack_blind_rise_run1.json`). Real curves rise and hop often
enough that neither rule can cut without losing true points, so both now flag.

### 40–450 Hz, no oracle band

The published line lies within 40–450 Hz on 23 passes, and some B track lies on it on all 23. The
strongest harmonic group contains it on 14 of them in run 1, and on 19 in run 2.

### ssqueezepy

It is called correctly: on a synthetic 300 → 210 Hz chirp its median error is 0.18 Hz. On Livermore,
inside the oracle band, it has 14 % median error and covers 0.39. It locks onto other lines. That is
the failure 6.3 predicts for Iatsenko's method without a stopping rule when components come and go.

## Outcome

**Not met (option 4).** Neither run meets the criterion, so `tracks.ridge()` stays the tracker.
`freqtrack` is kept as an experimental module, with its tests.
- **Run 1 met two parts of three.** It had lower error than `ridge()` (0.45 % against 0.48 %) and
  2.8× fewer false bridges. But it left 17× more fragments, at half the coverage.
- **The bar.** "No more fragments than a forced path" is a hard bar for a tracker designed to end where
  the tone ends. The criterion was kept as fixed.
- **Run 2's retune didn't work.** It traded fragments for bridges: tracks ran on through weak frames
  and onto other lines once hop no longer cut, and the error rose. The noise-derived θ–birth trade-off
  has a floor near 8 dB: below it no birth cost stops noise paths, so costs alone can't give much
  hysteresis.

Two results to keep, whatever comes next:
- **The off state keeps a tracker on the pass.** On the 11 flagged passes, which manoeuvre, run 1's B
  is at 0.84 % error against `ridge()`'s 15 % and ssqueezepy's 22 %. A forced path wanders off a
  turning or climbing pass; a local one stops.
- **Iatsenko without a stopping rule fails.** ssqueezepy's 14 % error and 0.39 coverage in an oracle
  band is that failure (PLAN 6.3).

Leads:
- **Option 3.** A true hysteresis in states: a just-born state with its own stricter threshold, and a
  looser continuation threshold. It is the next step, since run 1 landed close on two of three.
- **Item 5.** Rise and hop fire where the 2.048 s window smears the steep part. A shorter window near CPA
  may let both rules cut again.
- **Estimator.** Quinn is the best sub-bin estimator on chirps overall, but Candan beats it at 2–5 Hz/s.
  Item 5's window changes the regime, so the choice should be re-measured there.

## Script and run folder

- Code: `src/dopplertrack/freqtrack.py`. Tests: `tests/test_freqtrack.py` (Tier 0, 12 tests, about
  1.5 s).
- Scripts in `tools/experiments/2026-11-04/`:
  - `freqtrack_knobs.py`: run 1's θ and the estimator;
  - `freqtrack_livermore.py`: both runs; modes `""`, `rise-flag` and `run2`;
  - `freqtrack_diagnose.py`;
  - `freqtrack_retune.py`;
  - `freqtrack_blind_rise.py`.
- Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-04-freqtrack/`.
  - **Run 1:**
    - `livermore_summary.txt`, re-scored with the 3 s and hop counts. The metrics are identical to
      the first scoring, `livermore_summary_run1_first_scoring.txt`.
    - `livermore.log`.
    - `livermore_crashed_run.log`: the first attempt, which crashed on pass 21 on a script bug, a
      variable name reused.
  - **Rise fallback:** `livermore_summary_rise_flag.txt`.
  - **Run 2:** `livermore_summary_run2.txt`.
  - **Knobs:** `freqtrack_knobs_*.json`, `theta.log`, `retune.log`, `retune_grid1_stopped.log`.
  - **Diagnosis:** `freqtrack_diagnose.json`.
  - **Blind events:** `freqtrack_blind_rise_run1.json` and `_run2.json`.
  - **Before the flag fix:** the `*_before_flag_fix.*` files predate the fix to the flag bookkeeping
    (pieces copied their parent's flags). Only the flag counts changed.
  - **Commits:** `commit_at_*.txt` holds the commits each run started from, and `run2_source.patch`
    the uncommitted defaults run 2 used.
