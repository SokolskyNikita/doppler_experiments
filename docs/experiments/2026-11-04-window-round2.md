# The analysis window after the overlap finding

<!-- index
question: Does a window or hop with nearly independent frames (w → 1) detect and track synthetic passes as well as today's 2.048 s Hann at 0.25 s?
outcome: No candidate passes the synthetic gate: C1, C2 and C3h each miss one of nine 0.03 passes at 1 false alarm per hour, and C2, C3r and C4 exceed 1.05× today's ridge() error; the package window stays. fit_event's brightness objective is bimodal across seeds under every window
-->

## Question

PLAN Phase 2 item 5, second round, to the design in
[the proposal](../proposals/2026-11-04-window.md) (written before any code ran).

Item 3's third round found that per-frame evidence over eightfold-overlapping frames is not independent
(Harris's weight w = 0.254 today). At a given window the hop only resamples: about 61 independent frames a minute
at 2.048 s, whatever the hop up to 1 s. The trade the window makes is independent frames and smear against bin
width and per-frame gain.

Candidates, all on the 0.488 Hz grid:

| | Window, hop, taper | w |
|---|---|---|
| C0 | 2.048 s, 0.25 s, Hann (today) | 0.254 |
| C1 | 2.048 s, 1 s, Hann | 0.937 |
| C2 | 1.024 s, 0.512 s, Hann | 0.947 |
| C3h | 1.024 s, 1.024 s, Hann | 1 |
| C3r | 1.024 s, 1.024 s, rectangular | 1 |
| C4 | 4.096/2.048 s Hann for the tails, 0.512/0.512 s Hann where the long image's ridge slope exceeds 0.477 Hz/s | 0.95 / 1 |

**Gate, fixed in the proposal:** a candidate goes on to real data if, at 1 false alarm per hour, its detection
probability on the 0.03 passes is no lower than C0's and its `ridge()` median error on them is at most 1.05× C0's.

## Setup

- **Code:** commits 5a2f0d5 and 968aa46.
  - `compute_spectrogram(window=...)` is a new option, default Hann, so today's output is unchanged; the
    rectangular blocks use `"boxcar"`.
  - The script is `tools/experiments/2026-11-04/window_roc.py`.
- **Noise:** 2 h of white noise (std 0.4) through `detect_events` (90–230 Hz). The threshold for 1 false alarm per
  hour is the third-highest noise score.
- **Passes:** synthesised from the propagation delay alone, x(t) = A sin(2π f0 t_e(t)), at constant amplitude, in
  the same noise, 240 s each. There are three geometries (f0, v, d) = (200 Hz, 55 m/s, 600 m), (120, 65, 1500) and
  Oyster Bay event 2's fit (140, 79, 1590), three seeds, and amplitudes 0.06, 0.03 and 0.015.
- **Measures:**
  - a detection is one within 10 s of the heard CPA;
  - `ridge()` is scored at 2 % with `freqtrack_livermore.score`, with its step limit per frame scaled with the hop
    so every candidate allows the same Hz/s;
  - `fit_event` is run under contrast and brightness, and a weak fit counts as 100 % error.
- **Fleet:** 4xlarge boxes, one candidate each (`--shards 6`), 4–5 min per box. The first launch (window-roc)
  lost its pass units to a naming bug: `units.path` used `with_suffix`, which cut "0.06_1" off the names. That is
  fixed in 968aa46. Its noise units were correct, and the rerun (window-roc-2) reused them. The gate ran on
  window-gate.

## Numbers

**At the gate's amplitude, 0.03.**

| | Threshold | Detected | `ridge()` error (× C0) | Contrast v, d | Brightness v, d | Gate |
|---|---|---|---|---|---|---|
| C0 | 1.10 | 9/9 | 0.091 % (1.00) | 0.09 %, 0.71 % | 8.5 %, 9.6 % | baseline |
| C1 | 1.21 | 8/9 | 0.087 % (0.96) | 0.19 %, 1.2 % | 21 %, 22 % | stops: detection |
| C2 | 0.98 | 8/9 | 0.098 % (1.08) | 0.17 %, 1.0 % | 0.41 %, 1.8 % | stops: both |
| C3h | 1.10 | 8/9 | 0.124 % (1.37) | 0.28 %, 2.3 % | 0.48 %, 2.6 % | stops: both |
| C3r | 1.10 | 9/9 | 0.097 % (1.07) | 0.18 %, 1.0 % | 8.8 %, 13 % | stops: error |
| C4 | 1.20 | 9/9 | 0.113 % (1.24) | 0.20 %, 1.7 % | 27 %, 13 % | stops: error |

**At 0.06,** every candidate detects 9/9, with `ridge()` errors between 0.08 % and 0.10 %. **At 0.015,** detection
is 0–2 of 9 everywhere: C0, C1, C2 and C3r 1/9, C3h 2/9, C4 0/9.

`ridge()`'s coverage is not comparable across hops, because the score counts reference frames on a 0.25 s grid
(1 s hops read 0.25). It is not part of the gate.

**The brightness objective is bimodal under every window.** Per seed, a pass's brightness fit lands either within
about 0.5 % or 20–80 % off. For example, C0 on the 1500 m pass gives v errors of 21 %, 0.2 % and 68 % over the
three seeds. So the brightness medians above say which basin most of nine fits fell into; they don't compare
windows.

## Outcome

No candidate passes the gate, so nothing goes on to the Livermore passes, Tier 1 or Tier 2. The package's window
and hop stay at 2.048 s Hann at 0.25 s. The retune was not spent: no candidate failed by a margin that points to a
setting worth trying, and with nine passes a single miss is the whole difference in detection.

- **What the synthetic run says.** Near-independent frames buy nothing measurable on detection or `ridge()`. The
  detector's ROC (thresholds 0.98–1.21) and `ridge()`'s errors (0.087–0.124 %) are close across all six
  candidates, so the overlap finding is a matter for statistics that sum frames (item 3's trackers, which can
  weight by w), not a reason to change the image.
- **For SDE-D's step** (brightness to find, gate to measure, least squares to fit). `fit_event`'s brightness
  objective falls into a wrong basin on about half of these synthetic passes at 0.03 under every window,
  and the contrast objective doesn't (≤ 2.3 % in v and d). The finding step should not trust a single brightness
  fit. No candidate here changes that, so no basin shift comes from the window.
- **A package switch** would have invalidated the saved fits, the detections cache and Tier 1's spans. It doesn't
  happen.

## Script and run folder

- **Script:** `tools/experiments/2026-11-04/window_roc.py`, with units in `units.py` and copies by `copy_new.py`.
- **Run folders** (in `$DOPPLERTRACK_DATA/runs/`):
  - 2026-11-04-window-roc-s{1..6}of6: the first launch, whose noise units were reused;
  - 2026-11-04-window-roc-2-s{1..6}of6;
  - 2026-11-04-window-roc-collect;
  - 2026-11-04-window-gate: `window_gate.json` and the gate's table in `command.log`.
- **Cost:** about $0.50 on 4xlarge spot.
