# Window length

## Question

PLAN Phase 2 item 5. The 2.048 s STFT window smears a pass's steepest part by g·T. Does a shorter
window, or a short-near-CPA/long-in-the-tails composite, give the same or smaller f0, speed and
slant-range errors from `fit_event`?

**Criterion,** fixed before running. A variant is kept if, for each objective (contrast, brightness) and
each of f0, v and d, its median |relative error| is at most 1.05× the 2.048 s window's:
- on the 29 primary Livermore passes (f0, v and d);
- on the development events with an ADS-B truth (v and d; ADS-B gives no rest frequency).

The paired sign test is reported alongside.

## Setup

- **Spectrograms.**
  - 4 kHz sampling, a Hann window of T = 2.048, 1.024 or 0.512 s (nperseg 8192, 4096, 2048), each
    zero-padded to 8192 points, 0.25 s hop, default whitening, 40–1900 Hz.
  - Every variant shares one grid of 0.488 Hz bins and one set of frame centres: a shorter window's
    samples are offset by (8192 − N)/2. The resolution stays 1/T (0.49, 0.98 and 1.95 Hz); the
    padding only interpolates.
  - New code: `nfft` in `compute_spectrogram` and `spectrogram_from_blocks`. With nfft = nperseg the
    output is byte-identical to before (Oyster Bay's `rec.npz` re-checked). freqtrack's `SampleSTFT`
    pads too, and its sub-bin estimators evaluate their three samples one resolution bin apart on the
    DTFT.
- **Hop.** The criterion runs use 0.25 s at every window: 88 %, 76 % and 51 % overlap. For
  information only, two more:
  - hop T/8 at each window (0.256, 0.128 and 0.064 s);
  - the 2.048 s window at a 1 s hop.
- **Two-window composite**, the rule fixed before running.
  - (a) `fit_event` on 2.048 s.
  - (b) That fit's sweep rate |g(t)| picks, frame by frame, the window in {2.048, 1.024, 0.512} closest
    to 1/√|g|, that is argmin |ln(T·√|g|)| (PLAN 6.1).
  - (c) The chosen windows' whitened columns form one spectrogram.
  - (d) `fit_event` again on it, initialised from (a).
  - An **oracle composite** does the same with g taken from the reference curve. It decides nothing:
    it bounds what the first fit's bias costs the selection.
- **Fits.** `fit_event` (SDE-A's, called unchanged), both objectives, c at 15 °C.
  - **Livermore:** harmonics 1, the window is the published ridge's span, the band is 0.85–1.15× the
    reference's range (the oracle band, as in [freqtrack](2026-11-04-freqtrack.md)).
  - **Development events:**
    - Oyster Bay events 1 and 2, with the README windows and bands;
    - eagle-cam events 1 and 2, with their committed windows and a 60–300 Hz band;
    - the blind-labelled events matched to a pass: ob-e03 (clear, N360NY at 7.3 km) and sw-e01
      (labelled overlapping, N4956N). sw-e01 is not a clear event; it is included as designed.
- **Truth.**
  - **Livermore:**
    - f0: the [audit](2026-11-04-livermore-audit.md)'s f0_15C, the rest frequency of the published
      line;
    - v: the PCHIP trajectory's 3-D speed at the emission CPA;
    - d: slant_m_15C.

    None of these depend on the clock.
  - **Development events:** v (ground speed) and d from the CPA table at the true location.
- **Sources.** PLAN 6.1's window paragraph: smear g_max·T, T ≈ 1/√g_max, tail variance ∝ 1/N³
  (Kay I eq. 3.41).
  - **Ferguson & Quinn 1994 §V:** 889 Hz sampling, a rectangular window of 2M = 256 samples (0.288 s),
    a 64-sample hop (0.072 s, 75 % overlap), a 32,768-point FFT with peak picking, for overhead passes
    at a 68 Hz blade rate.
  - **Ferguson & Lo 2000 §I.D** gives no STFT settings; it cites Ferguson & Quinn. Its 256-sample
    blocks at 50 % overlap (§II.E) are for the broadband cross-correlation, not the STFT. PLAN never
    carried the wrong version.

## Numbers

### Livermore, 29 primary passes

Median |relative error|, contrast / brightness:

| | f0 | v | d |
|---|---|---|---|
| **2.048 s** (baseline) | 1.28 % / 1.13 % | 12.3 % / 9.8 % | 27.1 % / 18.6 % |
| 1.024 s | 1.23 / 1.27 | 9.2 / 9.8 | 24.0 / 20.4 |
| **0.512 s** | 1.26 / 1.12 | 9.4 / **4.4** | 23.6 / **13.1** |
| two-window (two-stage) | 1.23 / 1.44 | 10.1 / 7.2 | **19.3** / 17.5 |
| oracle composite | 1.29 / 1.52 | 12.9 / 9.3 | 38.2 / 19.0 |
| *2.048 s at a 1 s hop* | 1.90 / 1.46 | 13.0 / 10.5 | 30.0 / 22.5 |
| *hop T/8: 2.048 / 1.024 / 0.512 s* | 1.41, 1.36, 1.19 / 1.18, 1.51, 1.16 | 10.4, 10.0, 10.3 / 10.0, 9.7, 4.8 | 24.9, 21.5, 18.7 / 16.1, 20.6, 13.8 |

- **Sign tests.** Passes where 0.512 s beats 2.048 s, contrast / brightness:
  - f0: 16 / 17;
  - v: 15 / 14;
  - d: 14 / 16.

  Every p-value is at least 0.46. The two-stage composite's contrast d is the only paired gain that
  stands out: 21 of 29, p = 0.02.
- **Composite frames**, contrast, as 2.048 / 1.024 / 0.512 s:
  - two-stage: 3,567 / 4,717 / 2,531;
  - oracle: 2,278 / 5,011 / 3,526.
- **The 11 flagged passes** (turns, climbs, a jet), 2.048 s against 0.512 s:
  - contrast: v 17.2 % against 16.6 %, d 15.4 % against 30.8 %;
  - brightness: v 21.6 % against 33.0 %, d 9.1 % against 17.1 %.

  0.512 s is worse on them, as is every other variant. They are reported, not in the criterion.

### Development events, v and d

| event | truth v, d | 2.048 s contrast / brightness | 0.512 s contrast / brightness |
|---|---|---|---|
| Oyster Bay ev1 | 137 m/s, 6,090 m | v 2 %, d 4 % / v 2 %, d 6 % | 1 %, 1 % / 2 %, 5 % |
| Oyster Bay ev2 | 104, 3,638 | 21, 55 / 36, 62 | 21, 54 / 27, 43 |
| eagle ev1 | 99, 2,536 | 0, 10 / 0, 8 | 12, 14 / 10, 7 |
| eagle ev2 | 103, 5,986 | 21, 45 / 5, 3 | 32, 62 / 4, 6 |
| ob-e03 (clear) | 95, 7,252 | 89, 95 / 70, 90 | 18, 74 / 35, 141 |
| sw-e01 (overlapping) | 60, 1,890 | 34, 114 / 96, 352 | 17, 4 / 210, 1487 |

Medians over the six:
- 2.048 s: v 21.0 % and d 49.9 % (contrast); v 20.5 % and d 35.2 % (brightness);
- 0.512 s: v 17.5 % and d 33.9 % (contrast); v 18.5 % and d 25.0 % (brightness).

Six events on two recordings can't decide much. Two of the six are weak or overlapping, with fit
failures at both windows (sw-e01's brightness fit at 0.512 s is off by 15×). The medians hide that.

### Criterion

| variant | Livermore contrast | Livermore brightness | development contrast | development brightness | verdict |
|---|---|---|---|---|---|
| 1.024 s | OK | worse (f0 1.27 % > 1.05 × 1.13 %) | OK | OK | not kept |
| **0.512 s** | OK | OK | OK | OK | **kept** |
| two-window | OK | worse (f0 1.44 %) | OK | OK | not kept |

### Resolution against effective sample count (Harris 1978 eq. 17)

Correlation of a Hann window with itself shifted by k hops, ρ_k, and the factor 1 + 2Σρ_k² by which
overlap shrinks the count of independent frames:

| | ρ₁, ρ₂, ρ₃, ρ₄ | factor |
|---|---|---|
| 2.048 s at 0.25 s | 0.91, 0.67, 0.40, 0.18 | 3.94 |
| 1.024 s at 0.25 s | 0.67, 0.18, 0.01 | 1.97 |
| 0.512 s at 0.25 s | 0.18 | 1.07 |
| 2.048 s at 1 s | 0.18 | 1.07 |

The 2.048 s window at a 1 s hop has as many independent frames as 0.512 s at 0.25 s. It is worse
than the baseline on every parameter: d 30.0 % / 22.5 % against 27.1 % / 18.6 %. So 0.512 s's gain is
not an effective-sample-count gain on the flat tails. It is the resolution of the steep part, the
smear g·T.

### Selection by sweep rate: two-stage against oracle

The oracle selection, which uses the true curve's sweep rate, is worse than the two-stage selection
(contrast d 38.2 % against 19.3 %). It is also worse than the baseline. Choosing windows by sweep rate
doesn't help in itself. The two-stage composite's one significant gain (contrast d, 21 of 29) most
likely comes from its second fit, which is initialised from the first and searches a narrowed grid,
not from the windows it picks. The rule is not safe to adopt on this evidence.

### Noise and gain in the whitened image

| window | white-noise SD | Oyster Bay "absent" stretches, SD (555 s) | 0.05 tone at 200 Hz in unit noise |
|---|---|---|---|
| 2.048 s | 5.57 dB | 6.67 dB | 4.9 dB |
| 1.024 s | 5.57 | 6.67 | 3.2 |
| 0.512 s | 5.57 | 6.64 | 1.6 |

- **Equal noise, unequal signal.** The whitened cells' spread is the same at every window: the
  log-power of Gaussian noise, about 5.6 dB. What changes is a steady tone's excess, which falls by
  about 1.6 dB per halving of T.
- **What the composite mixes**, then, is frames of equal noise spread but unequal signal gain. Under
  the brightness objective, its long-window frames carry more weight than a fixed tone's evidence
  warrants. That is one reason the composite's brightness fits are worse.

### The tracker at each window (informational)

freqtrack with run 1's knobs. θ was re-derived per window on noise (two hours of white noise, 1 false
track per hour per 100 Hz, birth 6) and is counted as a knob:
- 2.048 s: 9.5 dB;
- 1.024 s: 8.5 dB;
- 0.512 s: 7.0 dB.

The shorter windows' frames are less correlated, so noise peaks persist for less long and a lower
threshold reaches the same rate. A first θ grid started at 8.5 dB, too high to find the shorter
windows' values; it was re-run from 5 dB.

29 primary passes, 2 %:

| window | ridge() error, bridges, fragments, coverage | freqtrack error, bridges, fragments (≥ 3 s), coverage |
|---|---|---|
| 2.048 s | 0.48 %, 36, 12, 0.97 | 0.45 %, 13, 204 (76), 0.50 |
| 1.024 s | 0.47 %, 35, 14, 0.97 | **0.38 %**, 15, 198 (69), 0.55 |
| 0.512 s | 0.46 %, 40, 16, 0.96 | 0.43 %, **9**, 212 (86), 0.44 |

The shorter windows don't fix freqtrack's fragmentation. Its error is lowest at 1.024 s and its
bridges fewest at 0.512 s; the rise and hop cuts still fire.

### Runtime

- **Contended run.** The criterion run shared the machine with three other sessions' jobs (load 35–200
  on 14 cores). Its 284 s median per pass, for all 18 fits, is contention, not cost.
  - A 10-worker attempt and a serial one were each stopped for scheduling.
  - The results are from the 2-worker run. Results don't depend on the worker count.
- **Quiet re-timing** (`window_timing.py`, load about 9): five primary passes, one process.
  - `fit_event` costs the same at 2.048 s and 0.512 s, from 3 to 60 s per fit. The cost is set by the
    span (39–142 s) and the band (180–390 Hz), not by the window. One pair, R35's contrast fit at
    104 s against 59 s, coincided with the load rising to 16.
  - The STFT is under 0.1 s at either window.

## Outcome

- **The 0.512 s window meets the criterion. 1.024 s and the two-window composite don't.**
  - At 0.512 s, Livermore's median errors fall for v (brightness 9.8 % → 4.4 %) and d
    (18.6 % → 13.1 %), with f0 unchanged. The development events' medians fall too.
  - But no paired test separates 0.512 s from 2.048 s on Livermore (p ≥ 0.46). On the manoeuvring
    passes it is worse.
  - The criterion as fixed says keep it. The evidence for a large, consistent gain is weak: the median
    moves while about half the passes get worse.
- **Gain from resolution.** Where 0.512 s helps, the gain is resolution near CPA, not effective sample
  count (the 2.048 s window at a 1 s hop is worse).
- **The two-window rule isn't safe.** Choosing windows from the true sweep rate does worse than from
  the first fit, so the composite's one significant gain is likely its narrowed second fit.
- **Recommendation**, for the PM:
  - keep 0.512 s as the criterion says, as the window for `fit_event`'s steep-part evidence;
  - leave the package default at 2.048 s until Phase 2 item 4's least-squares fit is measured at
    both windows. Errors of 13–27 % in d are dominated by model error, not by the window
    (dopplerprint reports 14 % on this corpus).
  - freqtrack doesn't benefit enough to change its verdict.
- **Limits.**
  - Livermore is one group, development only. The six development events are too few to decide
    alone, and two are weak.
  - The oracle band is used on Livermore.
  - Neither objective is a likelihood, so the errors are point estimates against an ADS-B truth that
    itself carries interpolation error across 8–16 s KML gaps.

## Script and run folder

- Code: `src/dopplertrack/audio.py` (`nfft`) and `src/dopplertrack/freqtrack.py` (padded `SampleSTFT`
  and `refine`).
- Scripts, in `tools/experiments/2026-11-04/`:
  - `window_length.py`: the criterion run; passes and events in parallel, `JOBS` workers;
  - `window_noise_tracker.py`: Harris, noise, θ per window, the tracker;
  - `window_timing.py`.
- Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-04-window-length/`.
  - **Criterion run:** `window_summary.txt`, `window_livermore.json`, `window_dev.json`, `window.log`
    (the 2-worker run).
  - **Stopped runs:** `window_serial_stopped.log` and `window_jobs10_stopped.log`.
  - **Companions:** `window_noise_tracker.json` and `.log`, `window_tracker_summary.txt`, and the
    first θ grid's `*_grid1.*`.
  - **Timing:** `window_timing.json` and `.log`.
  - `commit.txt`.
