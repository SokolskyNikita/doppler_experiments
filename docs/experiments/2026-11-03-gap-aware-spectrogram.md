# Gap-aware spectrogram

## Question

PLAN Phase 1 item 8. Can the spectrogram keep a recording's timeline through gaps in the audio,
with frames over a gap marked invalid rather than dropped, so that fits neither bridge a gap nor
have their whitening dragged by it? Three checks:
- A synthetic pass with 5 s cut from every minute should fit to the parameters of the uncut pass.
- A gap over the pass's steepest part should give a weak fit.
- ESID 740's spectrogram should keep its timeline.

Before building for ESID 740 and 710, the item also needs to know what their gaps actually are.

## Setup

- **Code.** `Spectrogram` gains a per-frame `valid` mask and an optional `start_utc`.
  `spectrogram_from_files` places several files on one timeline and streams the audio chunk by
  chunk; `spectrogram_from_audiomoth` places them by their UTC names. `dopplertrack spectrogram`
  takes a folder of AudioMoth files. In `tracks.py`, `local_whiten` takes its median over valid
  frames and keeps the mask, and so does `grid_search`'s max filter.
- **Placing files.** Gaps come from each file's decoded length against its name's offset, never from
  CONFIG.TXT. A name within 1 s of the previous file's end (the names' resolution) abuts it. A later
  start is a hole, and an earlier one by more than 1 s is an error.
- **What a gap means to a fit.** A gap carries no evidence. `sample()` returns its fill value (0)
  wherever the interpolation would take weight from an invalid frame, and the fit's mean still counts
  that sample. So a gap dilutes the score and is never renormalised away, as with `sweep_scores`
  (half the evidence, half the score). The rule is written into `Spectrogram`'s docstring.
- **Synthetic pass** (`tests/test_gaps.py`). A straight pass at f0 110 Hz, v 80 m/s, d 400 m, made by
  integrating the phase of `doppler.ideal_curve`'s frequency.
  - It is 300 s at 4 kHz, with a 0.03 tone in 0.4 white noise. The uncut contrast score is about
    5 dB, inside the 4–16 dB of Oyster Bay's `detect` events.
  - The pass is close and fast, so most of its sweep lies within ±10 s of CPA and one 5 s gap can
    cover the steep part.
  - Fits are `fit_event` with its default contrast objective, over CPA ±45 s, band 90–135 Hz.
    The spectrogram uses `nperseg` 8192, hop 0.25 s and global whitening.
  - Each 5 s gap makes about 7 s of frames invalid: the 2.05 s STFT window overlaps it for that
    long. That is 11–12 % of the timeline.
  - The seeds are fixed, so the tests are deterministic.
- **Real data.** Both hours of 2024-04-07 were unzipped with `tools/data/eclipse_extract.py` to
  `$DOPPLERTRACK_DATA/derived/eclipse/`:
  - ESID 740, 04:00–05:00 UTC: 58 files, in `ESID_740/2024-04-07_04h/`;
  - ESID 710, 03:00–04:00 UTC: 59 files, in `ESID_710/2024-04-07_03h/`.

  The CONFIG.TXT files and WAV headers of ESID 375, 710, 740 and 937 were read from the zips in
  `raw/`, along with ESID 740's README.md and data dictionaries.
- **Byte-for-byte check.** Oyster Bay's `raw/audio/youtube/oyster_bay.webm` built with
  `dopplertrack spectrogram`, before (dev `1cb9c34`) and after the change, compared with
  `derived/oyster_bay/rec.npz`.

## Numbers

### ESID 740 and 710 have no gap each minute

- **CONFIG.TXT.** Every copy reads "Recording duration 55 s, Sleep duration 5 s" (AudioMoth Basic
  1.9.2, 48 kHz, UTC). That includes ESID 375 and 937, which hold two continuous 44,739 s files each,
  with AudioMoth's own comment chunk ("Recorded at 01:39:34 07/04/2024 (UTC) by AudioMoth …"). A
  55 s / 5 s schedule can't produce those, so at least there the copied CONFIG.TXT doesn't describe
  what the device did.
- **WAV headers.** Every WAV in ESID 740's and 710's 2024-04-07 zips holds 2,880,000 samples:
  60.000 s at 48 kHz. The header is an extensible-format one with a fact chunk and no AudioMoth
  comment chunk.
- **Names.** They step 60 s, 1,434 times out of 1,436 per site. Each site has two longer steps,
  after which the start second jumps:
  - ESID 740: 04:24:46 → 04:27:22 and 16:50:22 → 16:52:59, holes of 96 s and 97 s;
  - ESID 710: 03:09:06 → 03:11:43 and 15:34:43 → 15:37:20, 97 s each.
- **Seam test** (`gap_seams.py`). An order-32 linear predictor, fitted to the end of each file,
  predicts the next file's first sample. The error is in units of the predictor's in-file residual:

| Hour | Abutting seams | RMS error at seams | Mid-file control | If unrelated | At the hole |
|---|---|---|---|---|---|
| ESID 740, 04:00–05:00 | 56 | 1.00 | 0.80 | 2.15 | 5.0 |
| ESID 710, 03:00–04:00 | 57 | 0.80 | 1.27 | 2.27 | 2.7 |

- No file shows a splice at a consistent position inside it (six files of ESID 740 scanned).
- **Documentation.** ESID 740's README says the archive holds "only raw, unprocessed audio data
  files", and that Stage 2 processing preserved "all raw audio data without modification". The
  data dictionaries define the sleep duration as the pause between recordings in a minute. Neither
  documents a change to the 55 s setting, a firmware change, concatenation or resampling. ESID
  710's README is the same apart from the site details.

So in both sites the minute files abut, and the audio is continuous across each seam. The only gaps
are the missing-file holes. Why the files hold 60 s against a 55 s setting is **undetermined**.
Either the copied CONFIG.TXT doesn't reflect the settings used (ESID 375 and 937 show that it can
fail to), or the 60 s files were produced from the recordings by an undocumented step (their
header is not AudioMoth's). ESID 375 and 937 have one real 2 s hole between their two files
(375: 14:05:13 → 14:05:15; 937: 18:06:00 → 18:06:02).

### ESID 740 and 710 keep their timelines

`dopplertrack spectrogram` on each hour folder runs in about 7 s:

| | ESID 740, 04:00–05:00 | ESID 710, 03:00–04:00 |
|---|---|---|
| frames (840 bins) | 14,296 | 14,540 |
| expected, (span × 4,000 − 8,192) / 1,000 + 1 | 14,296 (span 3,576 s) | 14,540 (span 3,637 s) |
| `start_utc`, the first file's name | 04:00:46 | 03:00:06 |
| hole, UTC | 04:25:46–04:27:22 | 03:10:06–03:11:43 |
| invalid frames | 392, in one run | 396, in one run |
| invalid exactly where a window overlaps the hole | yes | yes |
| invalid frames at the abutting seams | 0 of 56 | 0 of 57 |

- Frame 0's window starts at `start_utc`.
- Every decoded ESID 740 file has 240,000 samples at 4 kHz, so no name needed snapping.
- The largest per-bin median of ESID 740's whitened valid frames is 0.19 dB.
- `tests/test_eclipse.py` checks the ESID 740 hour (opt-in, `DOPPLERTRACK_ESID740`).

### Oyster Bay, single-file path

- dev's `dopplertrack spectrogram` reproduces `derived/oyster_bay/rec.npz` byte for byte (t, f and S).
- After the change, the same command gives arrays byte-identical to it, plus an all-true `valid`.
- The streaming multi-file path, given the one file, is also byte-identical.
- On an all-valid spectrogram, `local_whiten` is byte-identical to the expression it replaced
  (`test_local_whiten_unchanged_without_gaps`).
- `tests/test_oyster_bay.py`: 2 passed, 1 expected failure, as before.

### Fits through gaps

All fit numbers are from runs with the mask reaching the fit window. Without the `tracks.py` change,
`local_whiten` drops the mask inside every fit.

The uncut fit's own spread, over 8 noise seeds (`gap_window_spread.py`):

| | f0 (Hz) | v (m/s) | d (m) | t_cpa (s) |
|---|---|---|---|---|
| σ over seeds | 0.02 | 0.04 | 2.3 | 0.07 |
| mean σ over window shifts of ±5 and ±10 s | 0.02 | 0.04 | 2.3 | 0.05 |
| worst range over window shifts | 0.07 | 0.15 | 11 | 0.19 |

That is d to about 0.5 %.

**Phase scan** (`gap_phase_scan.py`): gapped against uncut, 8 seeds, with the gap start stepped by
3 s from CPA−30 to CPA+27 s.

| Gap starts at (s from CPA) | max \|Δv\| (m/s) | max \|Δd\| (m) | max \|Δt_cpa\| (s) | off optimum | score / uncut |
|---|---|---|---|---|---|
| −30 | 0.12 | 10.5 | 0.19 | 0/8 | 0.91 |
| −27 | 0.07 | 4.5 | 0.13 | 0/8 | 0.90 |
| −24 | 0.09 | 9.9 | 0.14 | 0/8 | 0.89 |
| −21 | 0.10 | 10.8 | 0.14 | 0/8 | 0.88 |
| −18 | 0.09 | 11.5 | 0.13 | 0/8 | 0.88 |
| −15 | 0.12 | 13.1 | 0.13 | 0/8 | 0.88 |
| −12 | 2.68 | 25.8 | 0.26 | 1/8 | 0.83 |
| −9 | 0.13 | 16.1 | 0.23 | 0/8 | 0.85 |
| −6 | 0.05 | 6.8 | 0.17 | 0/8 | 0.83 |
| −3 | 0.06 | 6.3 | 0.15 | 0/8 | 0.81 |
| 0 | 0.10 | 11.2 | 0.19 | 0/8 | 0.82 |
| +3 | 0.25 | 24.9 | **0.54** | 0/8 | 0.83 |
| +6 | 0.08 | 10.8 | 0.19 | 0/8 | 0.88 |
| +9 | 0.05 | 6.6 | 0.22 | 0/8 | 0.89 |
| +12 | 2.31 | 28.6 | 0.11 | 1/8 | 0.86 |
| +15 | 0.14 | 12.3 | 0.23 | 0/8 | 0.89 |
| +18 | 2.13 | 28.0 | 0.10 | 1/8 | 0.85 |
| +21 | 0.09 | 6.5 | 0.23 | 0/8 | 0.90 |
| +24 | 0.13 | 12.2 | 0.18 | 0/8 | 0.92 |
| +27 | 0.10 | 5.3 | 0.14 | 0/8 | 0.92 |

"Off optimum" means |Δv| > 0.5 m/s. The scan doesn't record f0.

- **Off-optimum fits.** 3 of 160 gapped fits (2 %), all with the gap 12–18 s from CPA at the sweep's
  edge, land in another local optimum: Δv ≈ +2.3 m/s, Δd ≈ +28 m (7 %), and a lower score. The grid
  stage finds the right cell each time; Nelder-Mead slips from it.
- **t_cpa.** With the gap 3 s after CPA, t_cpa moves by up to 0.54 s, more than one 0.25 s hop.
- **d.** Even with the gaps away from the sweep, d moves by up to 13 m, several times its noise σ.

**The test's six fits** (`gap_test_fits.py`), with every gap at least 20 s from CPA (starting
20–35 s after it):

| | f0 (Hz) | v (m/s) | d (m) | t_cpa (s) |
|---|---|---|---|---|
| uncut σ over the 6 seeds | 0.023 | 0.049 | 1.3 | 0.073 |
| mean shift | −0.013 | −0.018 | −2.5 | +0.055 |
| 2 standard errors of the mean shift | 0.015 | 0.051 | 3.8 | – |
| worst shift | 0.035 | 0.092 | 11.9 (3.0 %) | 0.224 |

- With a gap centred on CPA, the score is 0.78–0.84 of uncut, against 0.90–0.93 with the gaps
  elsewhere.
- The steep-gap score is below the gapped-elsewhere score on every seed.
- The steep-gap score is below (1 − invalid share) × uncut on every seed, with a margin of about 0.04.
- The f0 mean shift sits at 87 % of its 2-standard-error bound, so that bound is the tightest
  margin in the test.

**Renormalised alternative** (`gap_renorm_prototype.py`), with the mean over valid samples only,
same seeds:
- Parameter shifts don't improve, and the same off-optimum fit appears.
- With a gap centred on CPA, the renormalised score is **1.10–1.17 × uncut**. That is a confident
  fit with the steep part missing, which is exactly what PLAN's acceptance forbids.
- Multiplying by the share of sweep weight on valid samples gives back the zero-evidence score.

### Tests and timings

- `tests/test_gaps.py`: 10 tests in about 9 s wall time. The 18 fits run in a 6-process pool.
- `tests/test_eclipse.py`: 1 test in about 5 s.

## Outcome

- **Timeline kept.** Gap frames are invalid and hold 0 dB; whitening, `local_whiten` and `sample`
  skip them. Old .npz files load as all valid, and Oyster Bay's single-file spectrogram is unchanged
  byte for byte.
- **Real gaps.** ESID 740 and 710 keep their timelines. Neither has AudioMoth's 5 s gap per
  minute: each file holds 60 s of continuous audio, and the real gaps are two missing-file holes of
  96–97 s per site-day, each followed by a jump in the start second that looks like a device
  restart. ESID 375 and 937 have one 2 s hole between their two files. The cause of the 60 s files
  is undetermined (see above).
- **Acceptance, as agreed with the PM.** For f0, v and d, the mean shift over seeds is within 2
  standard errors of zero and each seed's shift within 4 % of the parameter, with every gap at least
  20 s from CPA. t_cpa is within one hop on every seed. A gap centred on CPA weakens the score below
  (1 − invalid share) × uncut, and below the same pass with its gaps elsewhere. Both pass.
- **Not "within the fit's spread".** PLAN's wording was written before the spread was measured. The
  uncut fit's noise spread (0.5 % in d) is tighter than what losing 12 % of the frames does to d
  (about 1.2 % rms, worst 3.0 %). Meeting that wording would mean weakening the tone until it
  passed.
- **Zero evidence kept.** Renormalising turns the steep-gap fit into a confident one (1.15 × uncut).
- **Lead for Phase 2 item 4.** About 2 % of gapped fits at the sweep's edge slip into a wrong
  optimum while the grid stage is right. That argues for that item's grid of starts as a safeguard.
  `fit_event` is unchanged here.
- **Proposed wording for PLAN 5.6**, the Eclipse Soundscapes ESID 375, 740, 710 row, Use column:
  > calibration or evaluation (decision 2). 740 and 710 hold 60 s files that abut, with two
  > missing-file holes a day; 375 has a 2 s hole between its two files. All need the gap-aware
  > spectrogram (Phase 1 item 8), which marks the holes invalid
- **MANIFEST.md.** SDE-D has already written the corrected ESID 740/710 note (data root
  MANIFEST.md, lines 49–55), and it agrees with these numbers. It cites this record as
  `2026-11-04-gap-aware-spectrogram.md`; the record's name is `2026-11-03-gap-aware-spectrogram.md`.
  The note could also add 710's holes (03:09:06 → 03:11:43 and 15:34:43 → 15:37:20) and 375's and
  937's 2 s hole.

## Script and run folder

- Tests: `tests/test_gaps.py` (Tier 0), and `tests/test_eclipse.py` (opt-in: `DOPPLERTRACK_ESID740`).
- Scripts in `tools/experiments/2026-11-03/`: `gap_seams.py`, `gap_phase_scan.py`,
  `gap_window_spread.py`, `gap_test_fits.py`, `gap_renorm_prototype.py`.
- Data tool: `tools/data/eclipse_extract.py`.
- Run folder: `$DOPPLERTRACK_DATA/runs/2026-11-03-gap-aware-spectrogram/`. It holds:
  - `run.json`, with the commands;
  - the logs;
  - the before and after Oyster Bay spectrograms;
  - the ESID 740 and 710 spectrograms;
  - `source.patch`, the tree while the fit numbers were taken;
  - `oyster_bay_pytest.log`.
