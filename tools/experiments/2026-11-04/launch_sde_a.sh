#!/usr/bin/env bash
# SDE-A's fleet jobs (cloud_jobs.md, "## SDE-A"), every one on its own box at once, and the steps after them.
# Needs tools/aws/runs on this branch. From any directory:
#
#   launch_sde_a.sh launch PINNED       stage B's A1/A3 (from PINNED, a clean checkout of
#                                       claude/sde-stageb-pairs-45d0bd8), stage A, B1/B2 and the timing sweep's
#                                       three shards, from this checkout
#   launch_sde_a.sh a1 RUN              after `runs pull` of the A1/A3 job: a1_noise.py on it, and if A1 is inside
#                                       the null's noise, the follow-up's launch command (printed, not run)
#   launch_sde_a.sh merge-sweep S1 S2 S3   after `runs pull` of the sweep's three jobs (their run folders): the table,
#                                       in a new run folder, from a checkout at the commit the sweep ran
set -euo pipefail
HERE=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$HERE"
RUNS=tools/aws/runs
P=tools/experiments/2026-11-04
PY="uv run --frozen python"
DATA=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}
BASE=runs/2026-11-04-bench-5314396-raw-audio-t2
CASES="eagle-cam-clip-18000s oyster-bay oyster-bay-moved-wsw150"
PAIRS_BOX="$P/event_pairs_z.py --detected \$DOPPLERTRACK_DATA/$BASE --case $CASES"    # expanded on the box
PAIRS_HERE="$P/event_pairs_z.py --detected $DATA/$BASE --case $CASES"
BRANCH=claude/sde-stageb-pairs-45d0bd8

clean() { [ -z "$(git -C "$1" status --porcelain)" ] || { echo "$1 has uncommitted changes; runs would ship them"; exit 1; }; }

case "${1:-}" in
launch)
    PIN=$(cd "${2:?a clean checkout of $BRANCH}" && pwd)
    [ "$(git -C "$PIN" rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "$PIN isn't on $BRANCH"; exit 1; }
    clean "$PIN"; clean "$HERE"
    # the deciding run, on demand so no spot interruption delays it
    $RUNS launch hypotheses-pairs --on-demand --repo "$PIN" \
        --inputs-from "$PY $PAIRS_HERE --hypotheses --inputs" -- $PY $PAIRS_BOX --hypotheses
    $RUNS launch comparable-score --inputs-from "$PY $PAIRS_HERE --inputs" -- $PY $PAIRS_BOX
    $RUNS launch hypotheses-b1b2 --inputs-from "$PY $P/hypotheses_b1b2.py --detected $DATA/$BASE --inputs" \
        -- $PY $P/hypotheses_b1b2.py --detected "\$DOPPLERTRACK_DATA/$BASE"
    $RUNS launch timing-sweep --shards 3 --inputs-from "$PY $P/timing_sweep.py --inputs" -- $PY $P/timing_sweep.py
    ;;
a1)
    RUN=$(cd "${2:?the pulled A1/A3 run folder}" && pwd)
    $PY $P/a1_noise.py "$RUN"
    N=$($PY -c "import json, math; d = json.load(open('$RUN/a1_noise.json')); n = d['n_needed_for_gap_at_2_sd']; print(math.ceil(n / 10000) * 10000 if n else '')")
    if [ -n "$N" ]; then
        echo "A1 is inside the null's noise. The follow-up, the same search at N = $N (stage A's one retune, spent on N):"
        echo "  $RUNS launch hypotheses-pairs-n$N --on-demand --repo PINNED --inputs-from \"$PY $PAIRS_HERE --hypotheses --inputs\" -- '$PY $PAIRS_BOX --hypotheses --null-n $N'"
    fi
    ;;
merge-sweep)
    shift
    [ $# -eq 3 ] || { echo "give the sweep's three pulled run folders"; exit 1; }
    RUN=$($PY tools/data/new_run.py timing-sweep-merge)
    $PY $P/timing_sweep.py "$RUN" --merge --resume "$@"
    echo "$RUN"
    ;;
*)
    sed -n '2,12p' "$0"; exit 1 ;;
esac
