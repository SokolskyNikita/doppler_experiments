# Whitening across frequency

<!-- index
question: Does whitening each frame against its ±10 Hz median across frequency beat today's per-bin running median on the benchmark?
outcome: Not met: Tier 2's eagle-cam margin falls from 2.54 % to 1.16 %, and Tier 1's background false alarms rise from 7.0 to 18.8 per hour at each arm's threshold, and the detector loses Oyster Bay event 2. The retune was not spent; the package default stays
-->

## Question

PLAN item 8's lead: on the frozen Oyster Bay events, today's curve score on an across-frequency background
separated the reference best of every scorer ([warp](2026-11-04-warp.md): z +3.33, against +2.41 for today's
background). Does that background beat today's whitening on the benchmark?

The option is `compute_spectrogram(whiten="frequency")`. Each frame is reduced by its own median over
±`bg_hz` = 10 Hz (Ramseier & Pieren eq. 11), instead of each bin by its running median over time. `local_whiten`
follows the spectrogram's mode.

Criterion, fixed before anything ran (`whiten_frequency.py`'s docstring):
- **Tier 2**, saved-fit profile, the five seed cases. On every positive case (oyster-bay, eagle-cam-clip-18000s,
  oyster-bay-hp150-aac32k), the true pair's rank is no worse and its margin no smaller than today's. The
  moved-box negatives are reported only.
- **Tier 1**, the development spans:
  - at min_score 0, the detector matches no fewer counted windows;
  - the background spans have no more false alarms per countable hour, each arm at its own threshold (the lowest
    score among its matched detections).

  Fewer false alarms would be the gain.
- One retune at most (bg_hz), counted.

## Setup

- **Code:** commit 02d705f. The option itself is 5aadae1, in `audio.py`. Its default output is byte-identical
  to the Oyster Bay spectrogram.
- **Spectrograms:** each case's and span's spectrogram was rebuilt with `whiten="frequency"` from the audio its
  recipe names, into `$DOPPLERTRACK_DATA/derived/whiten_frequency/` (13 files).
  - The frequency arm ran the benchmark runner with `bench.cases.resolve` pointed at those files.
  - The time arm ran today's files on the same code.
- **Fleet:** one box per arm and tier: 2026-11-04-whiten-{time,frequency}-t2, -whiten-time-t1 and
  -whiten-frequency-t1-2.
- **Tier 1, frequency arm:** its known-point step raised before the comparison. On oyster-bay-hp150-aac32k,
  raw-audio-windows profile, it reported "detect found nothing inside the saved window 3020–3130 s".
  - Every span's blind record had been written and hashed by then.
  - So both arms' spans were compared by `span_results` in `whiten_frequency.py`, which uses Tier 1's own
    `compare_span` and `pooled_curve`.
  - On the time arm this reproduces its `results.json` exactly: 2 matched, threshold 2.463, 6.98 per hour.

## Numbers

**Tier 2, saved-fit.**

| Case | Rank (time / frequency) | Margin, time | Margin, frequency | Refined error, time | Refined error, frequency |
|---|---|---|---|---|---|
| oyster-bay | 1 / 1 | 4.94 % | 5.02 % | 43 m | 43 m |
| eagle-cam-clip-18000s | 1 / 1 | 2.54 % | **1.16 %** | 877 m | 917 m |
| oyster-bay-hp150-aac32k | 1 / 1 | 4.620 % | **4.619 %** | 43 m | 43 m |
| oyster-bay-moved-north150 (negative) | — | 3.25 % | 2.32 % | 148 km | 148 km |
| oyster-bay-moved-wsw150 (negative) | — | 10.7 % | 12.5 % | 182 km | 182 km |

**Tier 1, the 11 development spans.**

| | Time | Frequency |
|---|---|---|
| Matched counted windows at min_score 0 | 2 | 2 |
| The arm's threshold (lowest matched score) | 2.46 | 4.00 |
| Background false alarms per countable hour at that threshold | 6.98 | **18.85** |

**Known point, raw-audio-windows profile.** In each saved event's window ± the crop margin, the profile takes the
best-scoring detection whose heard CPA lies inside the window. Oyster Bay event 2's saved window is 3020–3130 s,
and its saved fit has CPA 3068.4 s.

| Case, event 2 | Time whitening | Frequency whitening |
|---|---|---|
| oyster-bay | CPA 3068.5 s, f0 140.1 Hz, v 79 m/s, d 1.59 km, score 9.98 | CPA 3122.0 s, f0 106.3 Hz, v 150 m/s, d 0.26 km, score 10.23: another pass |
| oyster-bay-hp150-aac32k | CPA 3068.5 s, f0 140.1 Hz, v 79 m/s, d 1.59 km, score 9.84 | nothing in the window (Tier 1 raised here) |

Event 1 is found alike by both arms (CPA 2155.8 s, f0 112.8 Hz).

## Outcome

Not met, on both tiers:
- **Tier 2:** the eagle cam's margin halves, and the degraded Oyster Bay's is a hair smaller.
- **Tier 1:** matches are unchanged, but false alarms on background nearly triple. The frequency arm's scores sit
  on a higher scale (its threshold is 4.0 against 2.5), so the comparison at each arm's own threshold is the fair
  one, and it is worse even there.
- **Detector:** under frequency whitening it loses Oyster Bay's event 2 outright. On the clean recording it picks
  another pass in the window, 54 s later and 34 Hz lower, and on the degraded one it finds nothing.

The background that separated the reference best on the frozen Oyster Bay events does not carry over to the
detector and the full scorer. The retune was not spent: neither tier pointed to a bg_hz worth trying, and the eagle
cam and the background spans moved the wrong way together. The package default stays the per-bin running median.

The option stays in `audio.py` as a named choice. It is the better image for the frequency trackers
([hmm-tracker](2026-11-04-hmm-tracker.md): under it `hmmtrack`'s median error is 0.37 % against 0.49 %, and round
1's is 0.37 % against 0.45 %). It is worse for `ridge()` (0.74 % against 0.48 %). So whether a tracker whitens
across frequency is that tracker's choice, separate from the package default.

## Script and run folder

`tools/experiments/2026-11-04/whiten_frequency.py`, launched with `tools/aws/runs` (`fleet_launch.sh`) and merged by
`fleet_merge.py`. The merged run folder is `$DOPPLERTRACK_DATA/runs/2026-11-04-sde-c-fleet-merge/` (`summary.txt`,
`side_by_side.txt`); each job's own folder keeps its `run.json` and log. The Tier 2 time-arm attempts that were
stopped before the reboot and for the migration were never read; they are kept in `runs/2026-11-04-whiten-frequency/`.
