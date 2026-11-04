#!/usr/bin/env bash
# SDE-A's fleet jobs (cloud_jobs.md, "## SDE-A"), every one sharded over its own boxes at once, and the steps after.
# Needs tools/aws/runs on this branch. Calendar time is the scarce thing (PM, 2026-11-04), so stage B's null-N
# follow-up launches with the rest; its result is read only if A1 needs it (docs/experiments/2026-11-04-hypotheses.md).
#
#   launch_sde_a.sh launch PINNED          every job: stage B's A1/A3 and its N follow-up from PINNED (a clean checkout
#                                          of claude/sde-stageb-pairs-45d0bd8), stage A, B1/B2 and the timing sweep
#                                          from this checkout. A launch that fails is reported and the rest go on.
#   launch_sde_a.sh merge KIND S1 S2 ...   after `runs pull` of a job's shards (their run folders): the merged
#                                          result in a new run folder. KIND: pairs-b, pairs-n (run them with
#                                          PINNED=<checkout> set), pairs-a, b1b2, sweep
#   launch_sde_a.sh a1 MERGED_B [MERGED_N] A1 from the merged A1/A3 run; if it is inside the null's noise, from the
#                                          merged N run too, when its N covers what the gap needs
#
# Shards per job (boxes), overridable from the environment: the pairs jobs are 30 searches, B1/B2 3 cases, the sweep
# 45 cells.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$HERE"
RUNS=${RUNS:-tools/aws/runs}           # RUNS=echo prints the launches instead
P=tools/experiments/2026-11-04
PY="uv run --frozen python"
DATA=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}
BASE=runs/2026-11-04-bench-5314396-raw-audio-t2
CASES="eagle-cam-clip-18000s oyster-bay oyster-bay-moved-wsw150"
BRANCH=claude/sde-stageb-pairs-45d0bd8
NULL_N_CAP=250000                         # the PM's cap on the follow-up's N
SHARDS_B=${SHARDS_B:-10} SHARDS_N=${SHARDS_N:-30} SHARDS_A=${SHARDS_A:-5} SHARDS_B12=${SHARDS_B12:-3}
SHARDS_SWEEP=${SHARDS_SWEEP:-15}
# each pairs job's own settings; a merge must repeat them exactly (they are part of its units' parameters)
ARGS_B="--hypotheses --workers-per-search 16"
ARGS_N="--hypotheses --workers-per-search 64 --null-n $NULL_N_CAP"
ARGS_A="--workers-per-search 16"

pairs() { echo "$P/event_pairs_z.py --detected $1/$BASE --case $CASES"; }    # $1: the data root, here or on the box
clean() { [ -z "$(git -C "$1" status --porcelain)" ] || { echo "$1 has uncommitted changes; runs would ship them"; exit 1; }; }
pinned() {
    local pin; pin=$(cd "${1:?a clean checkout of $BRANCH}" && pwd)
    [ "$(git -C "$pin" rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "$pin isn't on $BRANCH"; exit 1; }
    echo "$pin"
}
launch() {        # topic shards extra-runs-flags inputs-command -- command; a failure is reported, not fatal
    local topic=$1 shards=$2 flags=$3 inputs=$4; shift 4
    # shellcheck disable=SC2086
    $RUNS launch "$topic" --shards "$shards" $flags --inputs-from "$inputs" -- "$@" || echo "LAUNCH FAILED: $topic"
}

case "${1:-}" in
launch)
    PIN=$(pinned "${2:-}")
    clean "$PIN"; clean "$HERE"
    BOX='$DOPPLERTRACK_DATA'      # expanded on the box
    launch hypotheses-pairs "$SHARDS_B" "--on-demand --repo $PIN" "$PY $(pairs "$DATA") $ARGS_B --inputs" \
        $PY $(pairs "$BOX") $ARGS_B
    launch hypotheses-pairs-n$NULL_N_CAP "$SHARDS_N" "--on-demand --repo $PIN" "$PY $(pairs "$DATA") $ARGS_N --inputs" \
        $PY $(pairs "$BOX") $ARGS_N
    launch comparable-score "$SHARDS_A" "" "$PY $(pairs "$DATA") $ARGS_A --inputs" $PY $(pairs "$BOX") $ARGS_A
    launch hypotheses-b1b2 "$SHARDS_B12" "" "$PY $P/hypotheses_b1b2.py --detected $DATA/$BASE --inputs" \
        $PY $P/hypotheses_b1b2.py --detected "$BOX/$BASE"
    launch timing-sweep "$SHARDS_SWEEP" "" "$PY $P/timing_sweep.py --inputs" $PY $P/timing_sweep.py
    ;;
merge)
    KIND=${2:?pairs-b, pairs-n, pairs-a, b1b2 or sweep}; shift 2
    [ $# -ge 1 ] || { echo "give the job's pulled shard folders"; exit 1; }
    SHARDS=(); for s in "$@"; do SHARDS+=("$(cd "$s" && pwd)"); done
    case "$KIND" in
        pairs-b|pairs-n) cd "$(pinned "${PINNED:-}")"; [ "$KIND" = pairs-b ] && A=$ARGS_B || A=$ARGS_N ;;
        pairs-a) A=$ARGS_A ;;
    esac
    RUN=$($PY tools/data/new_run.py "merge-$KIND")
    case "$KIND" in
        pairs-*) $PY $(pairs "$DATA") $A "$RUN" --merge --resume "${SHARDS[@]}" ;;
        b1b2) $PY $P/hypotheses_b1b2.py "$RUN" --detected "$DATA/$BASE" --merge --resume "${SHARDS[@]}" ;;
        sweep) $PY $P/timing_sweep.py "$RUN" --merge --resume "${SHARDS[@]}" ;;
        *) echo "unknown kind $KIND"; exit 1 ;;
    esac
    echo "$RUN"
    ;;
a1)
    RUN=$(cd "${2:?the merged A1/A3 run}" && pwd)
    $PY $P/a1_noise.py "$RUN"
    NEED=$($PY -c "import json; print(json.load(open('$RUN/a1_noise.json'))['n_needed_for_gap_at_2_sd'] or '')")
    [ -z "$NEED" ] && exit 0
    if [ "$NEED" -gt "$NULL_N_CAP" ]; then
        echo "A1 is inside the null's noise and needs N = $NEED, over the cap of $NULL_N_CAP: the test can't decide at any affordable N."
    elif [ -n "${3:-}" ]; then
        echo "A1 is inside the null's noise at N = 1,000 and needs N = $NEED; reading the N = $NULL_N_CAP run:"
        $PY $P/a1_noise.py "$(cd "$3" && pwd)"
    else
        echo "A1 is inside the null's noise and needs N = $NEED: merge the N = $NULL_N_CAP run and pass it as the second argument."
    fi
    ;;
*)
    sed -n '2,17p' "$0"; exit 1 ;;
esac
