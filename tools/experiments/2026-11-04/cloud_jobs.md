# SDE-C's jobs for the AWS fleet

Three jobs, each run through `tools/aws/runs launch` from a committed head, so the box gets that commit and no
uncommitted diff. The box sets `$RUN` to `runs/<id>/` and writes its `run.json`; each command below takes that
folder as its first argument.

Every job is a list of units (`units.py`). Each unit writes one JSON file, atomically, when it finishes, and a
unit whose file already exists is skipped:
- **Resume:** running the same command again on the same `$RUN` finishes the job.
- **Split:** each box names its own disjoint units.
- **Merge:** pull every box's run folder, copy the units into one folder with `cp -Rn`, which works because
  their paths are relative to `$RUN`, then run the merge step there.

Every process pool sizes itself from `DOPPLERTRACK_JOBS` (`--jobs`), defaulting to the box's physical cores.

The jobs depend on each other in order: job 1 decides `WHITEN`, job 2 decides `THETA_CONT` and `THETA_BIRTH`,
and job 3 uses both.

## 1. Whitening across frequency (`whiten_frequency.py`)

The criterion is in the script's docstring and was fixed before anything ran.

| Step | Units | Command |
|---|---|---|
| build | one per variant spectrogram (13) | `whiten_frequency.py "$RUN" build [SPECTROGRAM ...]` |
| Tier 2 | one per (arm, case): 2 × 5 | `whiten_frequency.py "$RUN" t2 time\|frequency [CASE ...]` |
| Tier 1 | one per arm: 2 | `whiten_frequency.py "$RUN" t1 time\|frequency` |
| merge | — | `whiten_frequency.py "$RUN" merge` |

Inputs:
- The five seed cases, passed with `--case oyster-bay --case eagle-cam-clip-18000s --case oyster-bay-hp150-aac32k
  --case oyster-bay-moved-north150 --case oyster-bay-moved-wsw150`.
- The development spans' spectrograms and traces, from `bench/tier1.json`. All of them are under `derived/`.
- The variant spectrograms in `derived/whiten_frequency/`. They are already built locally and are seeded with
  `derived/`, so the build step is a no-op on the box. If the seed predates them, build writes them on the
  box: it needs the audio in `raw/audio/youtube/` and `derived/`.
- Cache: `--cache terrarium`. CPA tables rebuild on the box.

Split: put each arm on its own box (`t2 time` with `t1 time`, and the same for `frequency`). For a finer split,
name the Tier 2 cases. A Tier 1 arm that stops part-way restarts in a fresh folder, and the partial one is kept
as `<arm>-t1_stopped`.

## 2. The tracker's noise-image θ (`hmm_knobs.py`)

| Step | Units | Command |
|---|---|---|
| pairs | one per θ_cont in 3..9 dB (7) | `hmm_knobs.py "$RUN" pairs WHITEN [THETA_CONT ...]` |
| pick | — | `hmm_knobs.py "$RUN" pick WHITEN` |

Inputs: none. The noise and the weak passes are synthetic, with fixed seeds.

Each unit is a bisection whose steps run one after another. Each step uses 12 noise windows in parallel, so a
single process can't use more than 12 workers. To fill a box, run several θ_cont in parallel:

```sh
for tc in 3 4 5 6 7 8 9; do DOPPLERTRACK_JOBS=12 uv run python tools/experiments/2026-11-04/hmm_knobs.py "$RUN" pairs WHITEN $tc & done; wait
```

On a box with fewer cores, split the θ_cont across boxes instead. The pick is cheap and runs after the merge.
Its result, `chosen.json`, sets the `HMMParams` defaults, which makes `test_noise_and_a_short_tone_make_no_track`
pass.

## 3. The tracker on Livermore and the development events (`hmm_livermore.py`)

| Step | Units | Command |
|---|---|---|
| references | one file | `hmm_livermore.py "$RUN" references` |
| livermore | one per primary pass (29) | `hmm_livermore.py "$RUN" livermore WHITEN TC TB [PASS ...]` |
| dev | one per event (6) | `hmm_livermore.py "$RUN" dev WHITEN TC TB [EVENT ...]` |
| merge | — | `hmm_livermore.py "$RUN" merge WHITEN TC TB` |

The references must exist before any dev unit runs, and before the dev units are split. Run that step once,
then copy `dev_references.json` to every dev box.

Inputs:
- `derived/livermore/`, the unpacked corpus.
- `runs/2026-11-04-livermore-audit/`: its `passes.csv` and `sites.json`. `--input` reads from the bucket's
  `data/`, and `runs/` isn't seeded there, so this folder has to be seeded once before the job can run.
- `raw/audio/youtube/oyster_bay.webm` and `raw/audio/youtube/swfl_2024-12-28.webm`.
- `derived/oyster_bay/traces_ny.npz` and `derived/swfl/traces_swfl.npz`.

Split: by pass, for example 15 and 14 passes on two boxes, with the dev events on either of them.
