#!/usr/bin/env bash
# SDE-D's fleet jobs (cloud_jobs_sde_d.md), each sharded over its own boxes, launched at once, and the merges after.
# Needs tools/aws/runs on this branch.
#
#   launch_sde_d.sh launch                   both jobs: the turn model's bootstrap and the Alaska rerun at three sound
#                                            speeds. A launch that fails is reported and the other goes on.
#   launch_sde_d.sh merge KIND S1 S2 ...     after `runs pull` of a job's shards (their run folders): the merged result
#                                            in a new run folder. KIND: boot, alaska
#
# Shards (boxes) per job, overridable from the environment.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$HERE"
RUNS=${RUNS:-tools/aws/runs}           # RUNS=echo prints the launches instead
P=tools/experiments/2026-11-04
PY="uv run --frozen python"
SHARDS_BOOT=${SHARDS_BOOT:-20} SHARDS_ALASKA=${SHARDS_ALASKA:-20}
# each job's settings; a merge must repeat them exactly (they are part of its units' parameters)
BOOT="$P/turn_model.py boot --replicates 200"
ALASKA="$P/model_error_alaska.py --band narrow --band-factors 0.70 1.50"

clean() { [ -z "$(git -C "$1" status --porcelain)" ] || { echo "$1 has uncommitted changes; runs would ship them"; exit 1; }; }
launch() {        # topic shards inputs-command -- command; a failure is reported, not fatal
    local topic=$1 shards=$2 inputs=$3; shift 3
    $RUNS launch "$topic" --shards "$shards" --inputs-from "$inputs" -- "$@" || echo "LAUNCH FAILED: $topic"
}

case "${1:-}" in
launch)
    clean "$HERE"
    # shellcheck disable=SC2086
    launch turn-model-boot "$SHARDS_BOOT" "$PY $BOOT --inputs" $PY $BOOT
    # shellcheck disable=SC2086
    launch model-error-alaska "$SHARDS_ALASKA" "$PY $ALASKA --inputs" $PY $ALASKA
    ;;
merge)
    KIND=${2:?boot or alaska}; shift 2
    [ $# -ge 1 ] || { echo "give the job's pulled shard folders"; exit 1; }
    SHARDS=(); for s in "$@"; do SHARDS+=("$(cd "$s" && pwd)"); done
    RUN=$($PY tools/data/new_run.py "merge-$KIND")
    case "$KIND" in
        # shellcheck disable=SC2086
        boot) $PY $BOOT "$RUN" --merge --resume "${SHARDS[@]}" ;;
        # shellcheck disable=SC2086
        alaska) $PY $ALASKA "$RUN" --merge --resume "${SHARDS[@]}" && $PY $P/model_error_alaska_summary.py "$RUN" ;;
        *) echo "unknown kind $KIND"; exit 1 ;;
    esac
    echo "$RUN"
    ;;
*)
    sed -n '2,10p' "$0"; exit 1 ;;
esac
