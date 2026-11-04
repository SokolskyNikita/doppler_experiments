# Frequency tracks with hysteresis in states

<!-- index
question: Does a Viterbi over fundamentals with BORN and ON states (θ_birth above θ_cont) beat `ridge()` on the Livermore passes, under either whitening?
outcome: Not met under either whitening or either pick. The best case, frequency whitening at θ 9/9.14, has lower error (0.37 % against 0.74 %) and one fewer bridge, but 5× the fragments; the counted retune raised bridges to 144. Next: the tracker's objective, not a third configuration
-->

## Question

PLAN Phase 2 item 3, round 2. Round 1 ([freqtrack](2026-11-04-freqtrack.md)) failed on fragments: a per-frame
threshold set on noise ends a track wherever a real tone dips under it.

`dopplertrack.hmmtrack` decodes a grid of fundamentals (a quarter of a bin apart) on each frame's harmonic
evidence, pooled first (`warp.pooled`, h = 1..3). It has three kinds of state:
- **OFF.**
- **BORN_a**, for n_born = 4 frames rewarded E − θ_birth.
- **ON**, rewarded E − θ_cont, with θ_cont below θ_birth.

A run of noise can't afford four frames above θ_birth, while a tone that is already ON continues through a dip.
Births cost 6 and deaths cost 6. Moves between fundamentals cost 0.1 dB per bin, capped at 0.25·f per second.
Two families are decoded, the second after excluding the first's cells (±4 bins), and round 1's
`resolve_crossings` and harmonic links follow.

Criterion, round 1's and fixed before anything ran: on the 29 primary Livermore passes, at 2 % tolerance, a lower
median error than `ridge()`, no more false bridges and no more fragments. The development events are reported
only.

The knobs were set on synthetic data before any real recording was tracked (`hmm_knobs.py`):
- **Pairs:** for each θ_cont from 3 to 9 dB, the smallest θ_birth (bisected to 0.25 dB over max(θ_cont, 6) to
  18 dB) that gives at most 1 false track per hour per 100 Hz. The test signal is two hours of white noise, in
  12 windows of 10 min over 150–250 Hz.
- **Pick:** the pair with the fewest fragments on round 1's synthetic weak pass, then the most coverage.

## Setup

- **Code:**
  - commit 02d705f, and 3438552 for the retune;
  - `src/dopplertrack/hmmtrack.py`;
  - `tests/test_hmmtrack.py`: five pass, and the noise test is a strict xfail because no defaults were adopted.
- **Whitening:** both settings, at once, each on its own fleet box (`hmm_box.sh`), so that the whitening record's
  outcome has a tracker result either way. Under frequency whitening, `ridge()` and round 1's run 1 also run on
  the frequency-whitened image.
- **Development references:** f0 and shift by `EventWindow.sweep_scores`, written before any tracker ran. The
  references are the same on every box.
- **Retune 1 (counted):** written after the time-whitening box picked θ_cont 9, a pair that covers none of the
  weak pass and so counts no fragments. Only pairs covering at least half the weak pass are eligible; the rule is
  otherwise the same.

## Numbers

**Noise pairs.** Under both whitenings, θ_cont of 3 to 6 dB give 12 false tracks per hour per 100 Hz even at
θ_birth 18 dB. A track that noise holds ON never dies, because the best of about 800 correlated fundamentals
stays above θ_cont. The hysteresis floor is therefore θ_cont of about 7 dB, close to round 1's 8 dB.

| θ_cont | θ_birth, time | weak pass (time): coverage, fragments | θ_birth, frequency | weak pass (frequency): coverage, fragments |
|---|---|---|---|---|
| 7 | 8.55 | 0.80, 31 | 8.72 | 0.75, 24 |
| 8 | 8.16 | 0.08, 1 | 8.16 | 0.07, 2 |
| 9 | 9.14 | 0.00, 0 | 9.14 | 0.00, 0 |

The weak pass is the faintest at which `ridge()` covers 95 % of the span. At a false-track rate of 1 per hour,
the tracker sees 0–8 % of it at θ_cont 8 and 9.

**Livermore, the 29 primary passes, 2 % tolerance.** A is `ridge()`, H is `hmmtrack` and B1 is round 1's run 1.

| Whitening, pick | Tracker | Median error | Bridges | Fragments (≥ 3 s) | Coverage | Criterion (error, bridges, fragments) |
|---|---|---|---|---|---|---|
| time, θ 9/9.14 | A | 0.48 % | 36 | 12 (4) | 0.97 | |
| | H | 0.49 % | 59 | 63 (43) | 0.51 | not met (no, no, no) |
| | B1 | 0.45 % | 13 | 204 (76) | 0.50 | |
| time, retune 7/8.55 | H | 0.55 % | 144 | 63 (42) | 0.65 | not met (no, no, no) |
| frequency, θ 9/9.14 | A | 0.74 % | 29 | 12 (5) | 0.86 | |
| | H | 0.37 % | 28 | 59 (40) | 0.43 | not met (yes, yes, no) |
| | B1 | 0.37 % | 8 | 209 (82) | 0.45 | |
| frequency, retune 7/8.72 | H | 0.50 % | 144 | 77 (36) | 0.70 | not met (yes, no, no) |

**The 11 flagged (manoeuvring) passes.** Median error:

| Whitening, pick | A | H | B1 |
|---|---|---|---|
| time, θ 9 | 15 % | 1.4 % | 0.84 % |
| time, retune | 15 % | 1.6 % | 0.84 % |
| frequency, θ 9 | 18 % | 0.68 % | 0.76 % |
| frequency, retune | 18 % | 12 % | 0.76 % |

**H over 40–450 Hz, with no oracle band:** its strongest group holds the published line on 6, 3, 1 and 1 of 23
passes (the four runs in the order above).

**Development events, summed over the six judged events.** Reported only.

| Whitening, pick | A: bridges, fragments | H: bridges, fragments | B1: bridges, fragments |
|---|---|---|---|
| time, θ 9 | 48, 18 | 44, 17 | 21, 37 |
| time, retune | 48, 18 | 100, 34 | 21, 37 |
| frequency, θ 9 | 52, 20 | 33, 16 | 18, 42 |
| frequency, retune | 52, 20 | 154, 53 | 18, 42 |

H's error on the eagle cam's two events at θ 9:
- time whitening: 0.2 % and 0.7 %, against A's 2.6 % and 12 %;
- frequency whitening: 0.2 % and 0.3 %, against A's 3.0 % and 9.8 %.

On ob-e03, H follows the wrong line under every setting (28–31 %).

Runtime: H takes a median 0.7–1.2 s per pass, against 0.01 s for A.

## Outcome

Not met, under either whitening and either pick, so no defaults change and `ridge()` stays the fitting path's
tracker. The round's own finding is that **hysteresis in states doesn't move the floor**:
- θ_cont can't go below about 7 dB without false tracks that never end.
- At the θ_cont the noise allows, the tracker is either blind to a pass `ridge()` covers (θ 8–9) or bridges
  freely (θ 7: 144 bridges).

So a threshold on the whitened dB image, whether per frame (round 1) or with hysteresis (round 2), has no setting
that is both quiet on noise and continuous on a real pass. Item 3 has had two rounds and one counted retune, so
there is no third configuration. The next step is the tracker's objective: a likelihood for the ridge (Kay I
Ex. 7.16; Quinn & Hannan ch. 7), proposed as a design before any run.

What carries forward:
- **The best H setting:** under frequency whitening at θ 9, H halves `ridge()`'s error and matches its bridges.
  Its failure there is coverage (0.43), the same failure as round 1.
- **The off state on manoeuvring passes:** it still keeps H honest there (0.7–1.6 % against 15–18 %).
- **The tracker's whitening:** frequency whitening helps H and B1 but hurts `ridge()` (0.48 % to 0.74 %). The
  tracker's whitening is therefore a choice separate from the package default, and it is the
  [whitening record](2026-11-04-whiten-frequency.md)'s to make.

## Script and run folder

- **Scripts:** `tools/experiments/2026-11-04/hmm_knobs.py`, `hmm_livermore.py` and `hmm_box.sh`, launched with
  `tools/aws/runs` and merged by `fleet_merge.py`.
- **Run folders** (in `$DOPPLERTRACK_DATA/runs/`), each holding its own `run.json`:
  - 2026-11-04-hmm-time (θ 9);
  - 2026-11-04-hmm-time-retune1-2;
  - 2026-11-04-hmm-frequency-2 (θ 9);
  - 2026-11-04-hmm-frequency-retune1-2.
- **Failed launches:** the first hmm-frequency and the two first retune boxes ran out of memory on 64 GB
  boxes during the pairs step, before any real recording was tracked. That is fixed in 63a90db, and their
  folders are kept as they are.
- **Merged folder:** `2026-11-04-sde-c-fleet-merge/` (`side_by_side.txt`, and `hmm/<whitening>_tc.._tb../hmm_summary.txt`).
