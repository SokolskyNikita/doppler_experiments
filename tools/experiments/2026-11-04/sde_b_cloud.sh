#!/usr/bin/env bash
# the benchmark study's five benchmark jobs on the AWS fleet, all at once, one box per case or Tier 1 unit
# (tools/experiments/2026-11-04/cloud_jobs.md). Run from the repo root with `runs` on dev:
#   tools/experiments/2026-11-04/sde_b_cloud.sh launch          seed the new derived files, start every job
#   tools/experiments/2026-11-04/sde_b_cloud.sh launch-locate   jobs 1 and 2 only (with LOC=<new prefix> to rerun them)
#   tools/experiments/2026-11-04/sde_b_cloud.sh collect-locate  pull, merge and compare jobs 1 and 2 as soon as they finish
#   tools/experiments/2026-11-04/sde_b_cloud.sh collect         the same for every job, with the Tier 1 compare
# BASELINE is the commit before the case bump (legacy cuts, station temperatures): job 3 runs there, from a worktree
# outside the repo, and job 4 runs the bumped cases at HEAD. Both must be clean commits.
# Never edit this file while it runs: bash reads a script as it goes.
set -euo pipefail
BASELINE=${BASELINE:-d90c807}
WT=${WT:-${TMPDIR:-/tmp}/dopplertrack-baseline-$BASELINE}
DAY=${DAY:-$(date +%Y-%m-%d)}
RUNS=tools/aws/runs
LOC=${LOC:-locate-t2}     # the locate jobs' topic prefix; a rerun at a fixed commit takes a new one
DATA=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}
# 4xlarge boxes: spot is 256 vCPUs a region, so 44 boxes fit at 16 vCPUs, with on-demand for any spot can't place.
# Each command runs under bash -c on its box, where $DOPPLERTRACK_SHARD_SPEC is that box's I/N.
BOX=(--size 4xlarge --fallback-on-demand)

LOCATE_CASES=$(uv run python -c "from bench import cases; print(len(cases.case_ids(profile='locate')))")
FIT_CASES=$(uv run python -c "from bench import cases; print(len(cases.case_ids(profile='saved-fit')))")
T1_UNITS=$(uv run python -c "from bench import tier1; print(len(tier1.unit_ids()))")

clean() { [ -z "$(git status --porcelain)" ] || { echo "commit first: the boxes run a clean commit"; exit 1; }; }

launch_locate() {   # 1, 2. every case, both pair rules in one pass, the silence filter off and on, one case per box
  clean
  $RUNS launch "$LOC-off" --shards "$LOCATE_CASES" "${BOX[@]}" \
    --inputs-from "uv run python -m bench inputs --profile locate" \
    -- 'uv run python -m bench run --profile locate --search-param pair_rule=both --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS launch "$LOC-on" --shards "$LOCATE_CASES" "${BOX[@]}" \
    --inputs-from "uv run python -m bench inputs --profile locate" \
    -- 'uv run python -m bench run --profile locate --search-param pair_rule=both --search-param silence_d_m=6000 --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
}

launch() {
  clean
  $RUNS seed        # the files a box reads come from the bucket's seed: upload what this branch added under derived/
  [ -d "$WT" ] || git worktree add --detach "$WT" "$BASELINE"
  launch_locate
  # 3. saved fits on the legacy cuts, at the commit before the bump; 4. the same on the bumped cases
  $RUNS launch savedfit-legacy-cut --repo "$WT" --shards "$FIT_CASES" "${BOX[@]}" \
    --inputs-from "uv run python -m bench inputs --profile saved-fit" \
    -- 'uv run python -m bench run --profile saved-fit --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS launch savedfit-margin-cut --shards "$FIT_CASES" "${BOX[@]}" \
    --inputs-from "uv run python -m bench inputs --profile saved-fit" \
    -- 'uv run python -m bench run --profile saved-fit --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  # 5. Tier 1, cold: the boxes get no detection or window-fit cache, only terrain; one unit per box, blind only
  $RUNS launch tier1-cold --shards "$T1_UNITS" "${BOX[@]}" --cache terrarium \
    --inputs-from "uv run python -m bench inputs --tier1 | python3 -c 'import json,sys; d=json.load(sys.stdin); d[\"cache_kinds\"]=[\"terrarium\"]; print(json.dumps(d))'" \
    -- 'uv run python -m bench tier1 --shard "$DOPPLERTRACK_SHARD_SPEC" --resume'
  $RUNS status
}

shards() {   # the run folders of one sharded job, as runs pull leaves them
  local topic=$1 n=$2
  for k in $(seq 1 "$n"); do echo "$DATA/runs/$DAY-$topic-s${k}of$n"; done
}

pull() {     # pull every shard of a job
  for job in $(shards "$1" "$2"); do $RUNS pull "$(basename "$job")"; done
}

merged() {   # a new run folder holding a job's merged shards; prints its path
  local out
  out=$(uv run python tools/data/new_run.py "$1-merged")
  uv run python -m bench merge "$out" $(shards "$1" "$2") >&2
  echo "$out"
}

collect_locate() {   # jobs 1 and 2 first: they decide step A and the pair rule, so they don't wait for the rest
  pull "$LOC-off" "$LOCATE_CASES"; pull "$LOC-on" "$LOCATE_CASES"
  local off on
  off=$(merged "$LOC-off" "$LOCATE_CASES"); on=$(merged "$LOC-on" "$LOCATE_CASES")
  uv run python -m bench compare "$off" "$on" > "$on/compare-silence-off-on.txt"
  for r in "$off" "$on"; do uv run python -m bench report "$r"; done
  echo "locate off: $off"; echo "locate on: $on"
}

collect() {
  collect_locate
  pull savedfit-legacy-cut "$FIT_CASES"; pull savedfit-margin-cut "$FIT_CASES"; pull tier1-cold "$T1_UNITS"
  local leg cut t1
  leg=$(merged savedfit-legacy-cut "$FIT_CASES"); cut=$(merged savedfit-margin-cut "$FIT_CASES"); t1=$(merged tier1-cold "$T1_UNITS")
  uv run python -m bench tier1 --run-dir "$t1" --resume        # compares the merged blind records
  uv run python -m bench compare "$leg" "$cut" > "$cut/compare-legacy-margin-cut.txt"
  for r in "$leg" "$cut"; do uv run python -m bench report "$r"; done
  echo "saved-fit legacy: $leg"; echo "saved-fit margin: $cut"; echo "tier1: $t1"
}

cmd=${1//-/_}; shift; "$cmd" "$@"
