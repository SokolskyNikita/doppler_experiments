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
| Collective find, other-day null (`collective-null`) | `tools/experiments/2026-11-04/collective_run.py --null` | 245 (case, day) draws: four NY and SWFL cases × 50, Essex × 45 | `null_draws.json`; then A's `collective_null.py` on the units |

**Collective find, other-day null.**
- **decision:** the collective find's criterion 3 and its decision line ([proposal](../../../docs/proposals/2026-11-04-collective-find.md) §5–6).
  - Each case's own-day maximum Z is judged against γ, the 1 % point of the maximum Z over other days' traffic. γ is fitted by A's `collective_null.py`, Gumbel or the empirical tail by KS.
  - If the negatives stay below γ and the positives clear it, `locate`'s step B becomes the collective find. If a negative clears it, the floor's design (§6's last line) is what changes.
- **Pinned.** Commit 661c10f, from a detached checkout. Its `collective.py` is 40454ae's, so the draws use the own-day units' statistic: the top-5 coarse cells, ±10 % f0 for every case, k = 10 windows, and the same detection.
- **oyster-bay-sources-removed has no units of its own.** It shares oyster-bay's spectrogram, box, range and DEM setting; only its own day's traces differ, with the true pair removed. On any other day its draw is oyster-bay's computation exactly, so `collective_null.py` reads oyster-bay's 50 draws for it.
- **Launch.** 35 × 8xlarge (Oyster Bay's units need more than 32 GB); shard 1 first as the smoke shard.
- **Inputs** (`--null --inputs`): the five cases' locate inputs, plus each null day's cut of the case's box, `derived/traces/<day>/<box>.npz`. That's 253 paths in all. CPA tables are built per day on the box, under `cpa/collective/null/<day>/`.

**Turn model, bootstrap.**
- **decision: none, so cancelled.** It would inform PLAN Phase 2 item 2's turn-model sentence. That sentence rejects the model on slant range (criteria 1–4) whatever the bootstrap shows, so no outcome changes it. Launched on 2026-11-04 as 8 × 4xlarge and cancelled under the PM's rule that a run which changes no PLAN sentence is stopped. One shard had already finished (`runs/2026-11-04-turn-model-boot-s1of8` in the bucket); its 1,000 replicates are kept, not merged.
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
- **decision:** PLAN Phase 2 item 2, stage 3, and whether station temperatures become the fitter's default. Stage 3 is the external check against Flightradar24, today on 50 crossings.
  - If the 789 reproduce the 50's ordering (the station-temperature c gives the smallest speed bias, the 15 °C default's range bias is a cancellation, and the authors' c is worse), stage 3's numbers in PLAN become the 789's, with intervals.
  - If they don't, PLAN's sound-speed conclusion is restated on the larger sample.
  - The narrow band's weak-fit count also says how often `fit_event` can't fit a band placed on a known tone (item 6).
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

**Collective null, SWFL and Essex (the first design's statistic).**
- **The NY smoke unit** (oyster-bay--null--2026-07-10) read clean at Z 22.84 in 31 min. The shard was then cancelled, before any held NY draw.
- **The PM's option 2.** The 95 SWFL and Essex draws were launched as `collective_run.py --null --null-cases eagle-cam-clip-18000s,xenocanto-xc990819` at a225ac8, whose `collective.py` is 40454ae's, on 24 × 8xlarge.
- **decision:** whether the eagle cam's 0.5 km find under the first design clears γ, and whether Essex's negative stays below it. The NY draws wait for the second design.

**Collective find, second design: the coarse stage (`collective-coarse-v2`).**
- **decision:** the second design step's cap and the fine stage's launch ([record](../../../docs/experiments/2026-11-04-collective-find.md), "A design step, written before the next rerun").
  - Each case's whole coarse map at ±25 % gives the true cell's rank and the margin rule's kept count.
  - The highest kept cell's fine stage gives the per-cell time the PM asked for before the fine stage launches.
- **Units:** "<case>--cell0", one per case, 8 in all. Shard 1 (oyster-bay) runs first as the smoke shard. 8xlarge.
