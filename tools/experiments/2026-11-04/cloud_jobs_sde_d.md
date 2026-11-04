# Cloud jobs from SDE-D (Phase 2 item 2: the turn model's bootstrap, the Alaska rerun)

Both drivers use [`tools/data/shards.py`](../../data/shards.py), the repo's shared shard, resume and merge mechanism; SDE-A's
`cloud_jobs.md` describes it.
- **Units.** Each one writes `RUN/units/<id>/result.json`, then `unit.json` by rename.
- **Options.** `--shard K/N` splits the units across boxes; `--resume DIR ...` keeps an earlier run's finished units.
- **Merge.** `--merge` checks that every unit is finished, at the same parameters and commit, and then writes the merged CSV.
- **Inputs.** `--inputs` prints the data-root paths a box needs.
- **Workers.** From `$DOPPLERTRACK_JOBS`. No result depends on them.

Both jobs launch at once from one script, [`launch_sde_d.sh`](launch_sde_d.sh): `launch_sde_d.sh launch` (20 boxes each by default; `SHARDS_BOOT`, `SHARDS_ALASKA`), then after `runs pull`, `launch_sde_d.sh merge boot|alaska S1 ... SN`. The Alaska merge also writes the three-setting table (`model_error_alaska_summary.py`, which counts weak fits and errors per setting).

Under the hood a sharded job is N launches with `--shard k/N`, each into its own `$RUN`. After `runs pull`, the merge runs on the Mac: the same
command with `--merge RUN_1 --resume RUN_2 ... RUN_N`. A spot interruption is resumed by a new launch with `--resume` on the
pulled folder.

## The jobs

| Job | Command (from the repo root) | Units | Merged output |
|---|---|---|---|
| Turn model, bootstrap (`turn-model-boot`) | `tools/experiments/2026-11-04/turn_model.py boot --replicates 200` | 40 passes × 200 replicates = 8,000 | `boot.csv`, `boot_summary.csv` (per pass: SDs of R, Q and the turn rate, and their correlations) |
| Alaska, all crossings (`model-error-alaska`) | `tools/experiments/2026-11-04/model_error_alaska.py --band narrow --band-factors 0.70 1.50` | 789 crossings (one per FR24-matched crossing) | `alaska.csv`; then `model_error_alaska_summary.py` on it |

**Turn model, bootstrap.**
- **One unit** is one replicate of one pass: curve A plus a moving-block replicate (2 s blocks) of that pass's sub-5 s
  residuals, refitted.
- **Seeds.** Each replicate's seed is sha256("pass:replicate"), so a unit gives the same numbers on any box and in any shard.
- **Form.** It fits the identifiable form, r² = R² + Q·u²·sinc²(ωu/2π), so its SDs and correlations are of R, Q and the turn rate. The turn model didn't enter (see the record), so this job is the trade-off diagnosis only: how strongly the turn rate trades with R.
- **Inputs** (`turn_model.py boot --inputs`):
  - `raw/audio/livermore/zenodo-23424278/final_results_40_cases.csv`;
  - `runs/2026-11-04-livermore-audit/passes.csv` and `sites.json`;
  - `runs/2026-11-04-model-error-2/fits.csv`;
  - each pass's KML and `frequency_vs_time_used.csv` under `derived/livermore/`.

  No cases, cache kinds or CPA tables. The two run folders under `runs/` are outside `raw/` and `derived/`, so `--input` needs
  them in the bucket.

**Alaska, all crossings.**
- **Sound speeds.** Each crossing is fitted at the three: 340.3 m/s, the authors' fitted c, and the nearest station's air
  temperature.
- **The band.** 0.70–1.50 × the authors' best-determined tone. A band too narrow for `fit_event` gives a weak fit, recorded as
  `weak_<setting>`, not an error.
- **Inputs** (`--inputs`):
  - `raw/seismic/alaska-ze2019/zenodo-16997158/`;
  - `derived/alaska/` (the obspy-converted waveforms);
  - `raw/aux/metar/PA{EC,IN,NN,TK}_2019-02-12.csv`.

  No cases, cache kinds or CPA tables.

**Checked here.**
- The Alaska driver ran 2 crossings as two shards plus a merge (`runs/2026-11-04-alaska-shards-smoke/`).
- The turn model's synth, fit and profile stages ran here as units (`runs/2026-11-04-turn-model-{synth,fit,profile}/`). Two boot units ran as shard 1/20 of a one-replicate job (`runs/2026-11-04-turn-model-boot-smoke/`).
