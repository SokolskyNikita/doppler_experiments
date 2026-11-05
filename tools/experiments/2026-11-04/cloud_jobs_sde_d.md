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

## Handoff (2026-11-04, about 23:45Z)

The branch is `claude/sde-c-pm-coordination-cbbe43`. Every change is committed. The tip passes `tools/aws/runs dev run -- tools/check.sh` (pytest 74 s).

**Running on the fleet.**
- **SWFL and Essex null, first design** (`2026-11-04-collective-null-s1of24` … `s24of24`, commit a225ac8, 24 × 8xlarge).
  - 95 units: `eagle-cam-clip-18000s--null--<day>` × 50 and `xenocanto-xc990819--null--<day>` × 45.
  - Each writes `units/<unit>/null_draws.npz` (day, max_S, second_S, lat, lon, n_matched, clock_audio_minus_utc_s).
  - The run's `collective.py` is 40454ae's, the own-day units' statistic: the top 5 coarse cells, ±10 % f0.
  - **To collect:**
    1. `tools/aws/runs pull` each job, or `runs wait` first; a waiter was running in this session.
    2. Optionally merge with `collective_run.py <new run> --null --null-cases eagle-cam-clip-18000s,xenocanto-xc990819 --merge --resume <the 24 folders>`, from a checkout at a225ac8 (`null_draws.json`).
    3. Give A's `tools/experiments/2026-11-04/collective_null.py OUT_RUN OWN.json DIR...` the 24 folders. It reads every `units/*--null--*/null_draws.npz`. `OWN.json` is `runs/2026-11-04-collective-find-merge/OWN.json`.
  - A fits γ (Gumbel or the empirical tail by KS) and writes the verdicts before reading labels.
  - Spot-interrupted shards relaunch with `--only-shard K` from a checkout at a225ac8; finished units are kept through `--resume`.
- **Second design, coarse stage smoke** (`2026-11-04-collective-coarse-v2-s1of8`, commit 91fb1c1, 8xlarge): unit `oyster-bay--cell0`.

**Held: the NY null draws** (oyster-bay, wsw150 and north150 × 50; sources-removed reads oyster-bay's, see above).
- Criterion 1 fails on Oyster Bay under the first design, so its statistic is being replaced. NY draws made on it would be redrawn.
- The one NY smoke unit (oyster-bay--null--2026-07-10, Z 22.84, 31 min) is in the cancelled `collective-null-s1of35` job's folder in the bucket. It isn't needed.

**The own-day result, first design:** `runs/2026-11-04-collective-find-merge/` (`collective.json`, `OWN.json`), recorded in docs/experiments/2026-11-04-collective-find.md.
- The eagle cam clip is found at 0.5 km with both true flights.
- Oyster Bay and hp150 are lost: their true cell isn't among the top 5 coarse cells, and ace391's detected tone is 11.5 % off.
- Criteria 1 and 4 fail; criterion 3 waits for γ.

**Built: the second design** (03c6a39 `collective.py`, 91fb1c1 driver; the design step and the gather's timing are in the record).
- Each candidate's tone over ±25 % through `LogView`, 3.8× cheaper per f0 point.
- Coarse cells kept by margin (Z ≥ Z_max − 2σ_c, at most 20), with the whole coarse map in `result.json["coarse_map"]`.
- Fine nulls drawn over the whole box; `only_cells` runs one kept cell per unit.

**What the ±25 % coarse map should show.**
- **On each case:** the margin rule's `margin` block (cells within it, kept, capped) and `coarse_truth`, the true cell's rank and whether it is within the margin.
- **On the positives:** whether Oyster Bay's true cell now ranks inside the margin, since ace391 is reachable at −10.4 %, and whether the eagle cam's stays in.
- **The PM's runtime check:** the `oyster-bay--cell0` unit's `walls.fine` is one cell's time. It must be read before the fine stage launches; the estimate is about 5.5 min.

**Not yet run or built.**
- **The coarse stage's other seven units.** After the smoke reads clean: `runs launch collective-coarse-v2 --shards 8 --only-shard K` for K = 2–8, with `--repo` a checkout at 91fb1c1.
- **The merge:** `collective_run.py <run> --merge --resume <8 folders>`. It writes `collective.json` and `KEPT.json`.
- **The fine stage:** `collective_run.py --fine-from KEPT.json`, one unit per (case, kept cell k ≥ 1), launched as its own job. Then merge it with `--extra-units <the coarse run>`, so each case takes its best cell over both stages.
- **The second design's null.** `--null` now runs the new statistic with every kept cell in one unit. With up to 20 cells per draw that's long, so before launching it, split the null units per cell as the fine stage does, or bound the cells.
- **Whether the old SWFL/Essex draws still apply.** Those running draws price the first design only. If the second design is adopted, they're redrawn under it.

**Smoke read, about 23:55Z** (`oyster-bay--cell0`).
- **Times:** coarse 167 s; one fine cell 284 s.
- **Margin:** 114 cells within the margin; the cap keeps 20.
- **The true cell** ranks 1,698 of 3,852 (Z 7.36, the map's median), so it isn't pruned, it doesn't score. A kept cell 2.0 km from the truth is rank 13.
- **Recorded** in the collective-find record.
- **Coarse units 2–8** are launched (`2026-11-04-collective-coarse-v2-s2of8` … `s8of8`, 91fb1c1).

**Done since the smoke read** (all recorded in the collective-find record):
- **The true-cell diagnostic** (`2026-11-04-collective-truth`, 75a8e02). The fine grid reaches Z 17.54 in OB's true cell, so the coarse sampler is the fault; ace391's window is weak (z 1.97).
- **The eight coarse units,** merged into `runs/2026-11-04-collective-coarse-v2-merge/` (`collective.json`, `KEPT.json`).

**Running:** the fine stage.
- OB's cells 1–19: `2026-11-04-collective-fine-v2-s1of19` … `s19of19`, 75a8e02, `--fine-from tools/experiments/2026-11-04/collective_kept_ob.json`.
- The other seven cases' 120 cells: `…-s1of20` … `s20of20`, 80599d3, `--fine-from …/collective_kept_rest.json`.
- Both run 91fb1c1's `collective.py`.

**Next step:**
1. Pull every fine job.
2. Merge each case over both stages, from a checkout at 80599d3:
   `collective_run.py <new run> --fine-from tools/experiments/2026-11-04/collective_kept_rest.json --merge --resume <the 20 …-s*of20 folders> --extra-units <the 8 collective-coarse-v2-s*of8 folders> <the 19 …-s*of19 folders>`.
   Each case takes its best cell over the coarse stage's cell 0 and every fine cell.
3. Report each case's best cell.
4. **The diagnostics are read** (record, "The follow-ups' results").
   - Both true lines lose about half their brightness to the 240 s window's length.
   - The coarse stage misses position: a 1 km grid lifts OB's true cell to 16.61 and a 667 m sub-grid to 20.76, against today's 7.36 and map maximum 14.80.
5. **The third design step is built and approved** (2170d9c): a 1 km coarse grid with 25-point fine cells, and each (flight, window) scored over its best 120 s stretch, nulls alike. Recorded before its run; check.sh passes.
   - **The v3 coarse smoke** (`2026-11-04-collective-coarse-v3-s1of8`, oyster-bay, 68a906c) is running.
   - **After it reads clean:**
     1. launch shards 2–8 with `--only-shard K` from a checkout at 68a906c;
     2. merge the eight into a new run (`--merge --resume <8 folders>`), which writes `KEPT.json` and the ranks;
     3. report the ranks, the cost per case and the eagle cam's z to the PM;
     4. commit `KEPT.json` as `tools/experiments/2026-11-04/collective_kept_v3.json` and launch `--fine-from` it. The PM has approved the fine stage.
   - **The v2 fine stage** (2 km, whole-window score) is superseded by v3. Merge it for the record only.

**SWFL and Essex null (first design), status about 00:40Z:** 20 of the 24 shards are done.
- s4, s19, s20 and s23 were spot-interrupted and relaunched on demand as `…-s{4,19,20,23}of24-2` (a225ac8).
- 84 of the 95 draws are pulled; the relaunches give the rest.
- **To judge,** give A's `collective_null.py` the 24 first-run folders plus the four `-2` folders, and `runs/2026-11-04-collective-find-merge/OWN.json`.
- The draws price the first design's statistic (2 km, top 5 cells, ±10 %), so their γ applies to that design's eagle cam result (Z 16.27), not to the third design's.

**The third design, about 00:50Z.**
- **Coarse stage:** merged into `runs/2026-11-04-collective-coarse-v3-merge/` (`collective.json`, `KEPT.json`).
- **Fine stage, running:**
  - OB's 19 cells: `2026-11-04-collective-fine-v3-s*of19`, 9334fab, `--fine-from …/collective_kept_v3_ob.json`.
  - The other seven cases' 106 cells: `…-s*of20`, 337f23f, `--fine-from …/collective_kept_v3_rest.json`.
- **The eagle cam's true-point diagnostic:** `2026-11-04-collective-truth-s2of2`, 337f23f.
- **Next:**
  1. Merge the fine stage per case, from a checkout at 337f23f: `collective_run.py <run> --fine-from tools/experiments/2026-11-04/collective_kept_v3_rest.json --merge --resume <the 20 …-s*of20 folders> --extra-units <the 8 coarse-v3 folders> <the 19 …-s*of19 folders>`.
  2. Read the eagle cam's diagnostic: whether the 1 km cells or the 120 s stretch cost it.
  3. The third design's own null, NY's 150 units first: `--null`, every kept cell per draw. Split it per cell or bound the cells before launching.
