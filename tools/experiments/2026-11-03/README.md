# Experiments, 2026-11-03

The scripts behind the numbers in PLAN.md (gap 4, Phase 2, section 7) and in upstream PR #2. They were run from
the repo root against the checkout's old `data/` layout, so running one again needs the path mapping below.
They are records, not tools: nothing imports them.

| Script | What it measured | Numbers in |
|---|---|---|
| `truth_ev2.py` | Oyster Bay at the known point: the true heard gap between the two flights, each event's trajectory-matched f0, and how far each set of fits is off | PLAN gap 4, PR #2 |
| `ev2_identifiability.py` | the best straight-pass curve at the ADS-B speed and distance, against the free fits, under both fit objectives | PLAN gap 4 |
| `old_objective_port.py` | that the pre-f890572 objective, ported with its comparison quirk fixed, reproduces the committed fits | PR #2 |
| `tol_grid.py` | the known-point check over `--tol` × `--f0-tol`; needs the knobs on branch `exp/gate-tolerances` | PLAN Phase 2, gate table |
| `summarise.py` | rank of the true pair, distance of the top candidate, and margin, from a search's CSV | PLAN Phase 2 tables |
| `extra_consistency.py` | whether extra detected flyovers separate the true flight pair from wrong ones | PLAN section 7 |
| `swfl_extras.py` | which committed `detect` candidates were the README's three extra eagle-cam flyovers | PLAN section 2 |
| `rewindow.py` | re-fitting detected flyovers in automatic windows, scored at the true location | PLAN Phase 2, re-fit table |
| `swfl_truth.py` | which search filter each eagle-cam fit trips at the nest | PLAN Phase 2 |

## Old paths

| Old (checkout `data/`) | Now |
|---|---|
| `data/rec.npz`, `rec_aac.npz`, `traces_ny.npz`, `detected.json` | `$DOPPLERTRACK_DATA/derived/oyster_bay/` |
| `data/swfl/rec.npz`, `traces_swfl.npz`, `detected.json` | `$DOPPLERTRACK_DATA/derived/swfl/` |
| `data/ev*.json`, `known_point*.csv`, `results.csv`, `res_*.csv`, `fine*.csv`, `*.log` | `$DOPPLERTRACK_DATA/runs/2026-11-03-issue-1/` (eagle-cam ones in `swfl/`) |
| `data/rewin/` | `$DOPPLERTRACK_DATA/runs/2026-11-03-rewindow/` |
| `data/cpa_cache.npz`, `data/swfl/cpa_cache.npz` | `$DOPPLERTRACK_CACHE/cpa/ny_40.4_41.3_-74.4_-72.6_200m.npz`, `swfl_26.1_27.3_-82.5_-81.2_200m.npz` |
| `data/patches/gate-tolerances.patch` | branch `exp/gate-tolerances` (the patch is kept in the issue-1 run folder) |
