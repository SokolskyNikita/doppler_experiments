#!/usr/bin/env bash
# SDE-B's five benchmark jobs on the AWS fleet, all at once, one box per case or Tier 1 unit
# (tools/experiments/2026-11-04/cloud_jobs.md). Run from the repo root with `runs` on dev:
#   tools/experiments/2026-11-04/sde_b_cloud.sh launch   seed the new derived files, start every job
#   tools/experiments/2026-11-04/sde_b_cloud.sh collect  pull, merge the shards, compare, render the reports
# BASELINE is the commit before the case bump (legacy cuts, station temperatures): job 3 runs there, from a worktree
# outside the repo, and job 4 runs the bumped cases at HEAD. Both must be clean commits.
set -euo pipefail
BASELINE=${BASELINE:-d90c807}
WT=${WT:-${TMPDIR:-/tmp}/dopplertrack-baseline-$BASELINE}
DAY=$(date +%Y-%m-%d)
RUNS=tools/aws/runs
DATA=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}

LOCATE_CASES=$(uv run python -c "from bench import cases; print(len(cases.case_ids(profile='locate')))")
FIT_CASES=$(uv run python -c "from bench import cases; print(len(cases.case_ids(profile='saved-fit')))")
T1_UNITS=$(uv run python -c "from bench import tier1; print(len(tier1.unit_ids()))")

launch() {
  [ -z "$(git status --porcelain)" ] || { echo "commit first: the boxes run a clean commit"; exit 1; }
  # the files a box reads come from the bucket's seed: upload what this branch added under derived/
  $RUNS seed
  [ -d "$WT" ] || git worktree add --detach "$WT" "$BASELINE"
  # 1, 2. locate on every case, both pair rules in one pass, the silence filter off and on, one case per box.
  # 4xlarge boxes: spot is 256 vCPUs a region, so 44 boxes fit at 16 vCPUs, with on-demand for any spot can't place.
  # The command runs under bash -c on the box, where $DOPPLERTRACK_SHARD_SPEC is this box's I/N.
  local box=(--size 4xlarge --fallback-on-demand)
  $RUNS launch locate-t2-off --shards "$LOCATE_CASES" "${box[@]}" \
    --inputs-from "uv run python -m bench inputs --profile locate" \
    -- 'uv run python -m bench run --profile locate --search-param pair_rule=both --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS launch locate-t2-on --shards "$LOCATE_CASES" "${box[@]}" \
    --inputs-from "uv run python -m bench inputs --profile locate" \
    -- 'uv run python -m bench run --profile locate --search-param pair_rule=both --search-param silence_d_m=6000 --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  # 3. saved fits on the legacy cuts, at the commit before the bump; 4. the same on the bumped cases
  $RUNS launch savedfit-legacy-cut --repo "$WT" --shards "$FIT_CASES" "${box[@]}" \
    --inputs-from "uv run python -m bench inputs --profile saved-fit" \
    -- 'uv run python -m bench run --profile saved-fit --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS launch savedfit-margin-cut --shards "$FIT_CASES" "${box[@]}" \
    --inputs-from "uv run python -m bench inputs --profile saved-fit" \
    -- 'uv run python -m bench run --profile saved-fit --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  # 5. Tier 1, cold: the boxes get no detection or window-fit cache, only terrain; one unit per box, blind only
  $RUNS launch tier1-cold --shards "$T1_UNITS" "${box[@]}" --cache terrarium \
    --inputs-from "uv run python -m bench inputs --tier1 | python3 -c 'import json,sys; d=json.load(sys.stdin); d[\"cache_kinds\"]=[\"terrarium\"]; print(json.dumps(d))'" \
    -- 'uv run python -m bench tier1 --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS status
}

shards() {   # the run folders of one sharded job, as runs pull leaves them
  local topic=$1 n=$2
  for k in $(seq 1 "$n"); do echo "$DATA/runs/$DAY-$topic-s${k}of$n"; done
}

collect() {
  for t in locate-t2-off:$LOCATE_CASES locate-t2-on:$LOCATE_CASES savedfit-legacy-cut:$FIT_CASES \
           savedfit-margin-cut:$FIT_CASES tier1-cold:$T1_UNITS; do
    for job in $(shards "${t%%:*}" "${t##*:}"); do $RUNS pull "$(basename "$job")"; done
  done
  merged() { local out; out=$(uv run python tools/data/new_run.py "$1-merged"); uv run python -m bench merge "$out" $(shards "$1" "$2") >&2; echo "$out"; }
  OFF=$(merged locate-t2-off "$LOCATE_CASES"); ON=$(merged locate-t2-on "$LOCATE_CASES")
  LEG=$(merged savedfit-legacy-cut "$FIT_CASES"); CUT=$(merged savedfit-margin-cut "$FIT_CASES")
  T1=$(merged tier1-cold "$T1_UNITS")
  uv run python -m bench tier1 --run-dir "$T1" --resume        # compares the merged blind records
  uv run python -m bench compare "$OFF" "$ON" > "$ON/compare-silence-off-on.txt"
  uv run python -m bench compare "$LEG" "$CUT" > "$CUT/compare-legacy-margin-cut.txt"
  for r in "$OFF" "$ON" "$LEG" "$CUT"; do uv run python -m bench report "$r"; done
  echo "locate off: $OFF"; echo "locate on: $ON"; echo "saved-fit legacy: $LEG"; echo "saved-fit margin: $CUT"; echo "tier1: $T1"
}

"$@"
