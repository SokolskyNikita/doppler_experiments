# ridge()'s frame covariance, measured

<!-- index
question: Does ridge()'s per-frame frequency error on synthesised passes correlate across frames as Harris's c or c² predicts, so that the provisional 63–74 m slant-range bound stands?
outcome: Not met as pre-registered: the pooled N_eff is 2.2 against 3.94 (c²) and 5.46 (c), and the implied bound is 48 m. The 5 s detrend drives the long lags negative, and the measured σ (0.04–0.34 % of f0) is far below the 0.45 % the bound assumes, so σ, not the correlation, is the open input
-->

## Question

PLAN item 2's Cramér–Rao bound for one pass, on the package grid (2.048 s Hann every 0.25 s), is provisional
([model-error](2026-11-04-model-error.md)). Its frame correlation is Harris's model, not a measurement. As the
complex coefficients' correlation c(r) it gives 74 m; as c(r)², for an estimate taken from magnitudes, it gives
63 m. Both are medians over the 29 primary Livermore passes, with σ = 0.45 % of f0, `ridge()`'s error measured on
Livermore.

Criterion, fixed before the run (`cov_measure.py`): the measured correlation matches one prediction within 20 %
in N_eff = 1 + 2 Σ_r ρ(r) (r = 1..8 hops), and the bound it implies has a median between 63 and 74 m. Otherwise
this record says which numbers replace them.

## Setup

- **Passes:** synthesised from the propagation delay alone (`window_roc.synth`), with constant amplitude, in noise
  of std 0.4, 240 s each. There are three geometries (f0, v, d) = (200 Hz, 55 m/s, 600 m), (120, 65, 1500) and
  (140, 79, 1590), amplitudes 0.06, 0.03 and 0.015, and seeds 0–2.
- **Measurement:** each pass goes through `compute_spectrogram`'s defaults, `local_whiten` over the pass's band
  (±15 %) and `tracks.ridge`. The per-frame error is e = ridge frequency − true heard frequency.
- **Noise part:** e less its 5 s running median, as `crb.py`'s ridge model treats it. Frames beyond 5 MADs are
  dropped as bridges.
- **ρ:** the autocorrelation pooled over the seeds of a cell, and over all cells for the bound.
- **Bound:** `crb.py`'s package bound on the 29 primary passes, with σ = 0.45 % of f0 and the pooled ρ in place
  of Harris's (positive definite as measured, so no taper).
- **Fleet:** 4xlarge boxes, one geometry × amplitude each (`--shards 9`, under a minute each); the bound ran on
  cov-bound.

## Numbers

| Cell | σ (Hz, % of f0) | ρ at lags 1–4 | N_eff |
|---|---|---|---|
| 600 m, 0.06 | 0.140, 0.070 % | 0.25, −0.10, −0.01, 0.04 | 0.26 |
| 600 m, 0.03 | 0.016, 0.008 % | 0.29, 0.14, 0.17, 0.03 | 2.27 |
| 600 m, 0.015 | 0.303, 0.152 % | 0.66, 0.36, 0.10, −0.06 | 1.66 |
| 1500 m, 0.06 | 0.050, 0.042 % | 0.11, 0.06, −0.04, −0.11 | 0.64 |
| 1500 m, 0.03 | 0.087, 0.072 % | 0.25, 0.13, 0.01, −0.06 | 0.52 |
| 1500 m, 0.015 | 0.326, 0.272 % | 0.67, 0.35, 0.11, −0.02 | 2.10 |
| ob-ev2, 0.06 | 0.075, 0.054 % | 0.15, 0.07, −0.05, −0.06 | 0.54 |
| ob-ev2, 0.03 | 0.126, 0.090 % | 0.36, 0.10, −0.09, −0.12 | 0.42 |
| ob-ev2, 0.015 | 0.482, 0.344 % | 0.74, 0.46, 0.24, 0.06 | 2.84 |

**Pooled ρ against Harris:**

| Lag | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Measured (pooled) | 0.656 | 0.369 | 0.155 | 0.007 | −0.099 | −0.150 | −0.173 | −0.166 |
| Harris c | 0.906 | 0.672 | 0.400 | 0.183 | 0.058 | 0.010 | 0.001 | 0 |
| Harris c² | 0.822 | 0.452 | 0.160 | 0.033 | 0.003 | 0 | 0 | 0 |

The pooled N_eff is 2.20, against 3.94 for c² and 5.46 for c: a match to neither. The implied slant-range bound is
a median of **48 m**, against 63 m for c² and 74 m for c, recomputed here on the same passes.

## Outcome

Not met as pre-registered, so the record says what replaces the numbers. Under the pre-registered method the
measured correlation gives 48 m. That number shouldn't be quoted as the bound, for two reasons the measurement
shows:
- **The negative tail is the detrend's.** ρ goes negative from lag 5 (−0.10 to −0.17). A 5 s running median
  (20 frames) removes the correlated part at lags approaching its length, which biases N_eff low. At the short
  lags, the measured ρ is below both predictions at lags 1–2 (0.66 and 0.37, against c²'s 0.82 and 0.45) and at c²
  at lag 3 (0.155 against 0.160). The finding Harris's model
  needs is a weak-signal one: at 0.015 the cells' ρ (0.66–0.74 at lag 1) approaches c², and at 0.03–0.06
  `ridge()`'s error is mostly bin quantisation (σ well under a bin, 0.49 Hz), with little frame correlation.
- **σ is the larger open input.** `ridge()`'s noise on these passes is 0.04–0.34 % of f0, not the 0.45 % the bound
  takes from Livermore. Livermore's 0.45 % mostly isn't frame noise: it includes the track's own excursions and
  model error. The bound scales linearly with σ, so a σ of 0.15 % would cut it by a factor of 3 whatever the
  correlation.

The bound stays provisional, and items 2 and 4 keep quoting 63–74 m (σ 0.45 %, Harris's range). Taking
"provisional" off needs a covariance measured with a detrend longer than the correlation length (or none, against
the exact synthetic curve). It also needs σ measured on the Livermore passes' own SNR, not assumed from the ridge
residual. Both are one script change on these units; the units are kept.

## Script and run folder

- **Script:** `tools/experiments/2026-11-04/cov_measure.py` (measure, bound), using `crb.py` and `window_roc.synth`.
- **Run folders** (in `$DOPPLERTRACK_DATA/runs/`):
  - 2026-11-04-cov-measure-s{1..9}of9;
  - 2026-11-04-cov-collect;
  - 2026-11-04-cov-bound (`cov_bound.json`).
- **Cost:** under $0.10 on 4xlarge spot.
