#!/bin/sh
# One fleet box's whole tracker job for one whitening setting (cloud_jobs.md, SDE-C job 2 then 3): the
# development references, the theta pairs on synthetic noise (the seven theta_cont at once, 12 workers each),
# the pick on the synthetic weak pass, then the Livermore passes and the development events at the picked pair,
# and the merge. The knobs are set before any real recording is tracked. Every step skips its finished units,
# so the same command resumes a stopped box (runs launch --resume).
#
# usage: hmm_box.sh time|frequency          (in $RUN, which the box sets)
set -eu
W=$1
D=$(dirname "$0")
PY="uv run --frozen python"
JOBS=${DOPPLERTRACK_JOBS:-$($PY -c 'from dopplertrack.parallel import default_jobs; print(default_jobs())')}

$PY "$D/hmm_livermore.py" "$RUN" references

pids=""
for tc in 3 4 5 6 7 8 9; do
    DOPPLERTRACK_JOBS=12 $PY "$D/hmm_knobs.py" "$RUN" pairs "$W" "$tc" > "$RUN/pairs_${W}_$tc.log" 2>&1 &
    pids="$pids $!"
done
for p in $pids; do wait "$p"; done                                     # set -e stops on the first failed pair
$PY "$D/hmm_knobs.py" "$RUN" pick "$W"

read -r TC TB <<EOF
$($PY -c "import json, sys; c = json.load(open(sys.argv[1]))['chosen']; print(c[0], c[1])" "$RUN/hmm_knobs/$W/chosen.json")
EOF
echo "picked theta_cont $TC theta_birth $TB"

DEV=6
DOPPLERTRACK_JOBS=$((JOBS > DEV + 1 ? JOBS - DEV : 1)) $PY "$D/hmm_livermore.py" "$RUN" livermore "$W" "$TC" "$TB" \
    > "$RUN/livermore_$W.log" 2>&1 &
liv=$!
DOPPLERTRACK_JOBS=$DEV $PY "$D/hmm_livermore.py" "$RUN" dev "$W" "$TC" "$TB" > "$RUN/dev_$W.log" 2>&1
wait "$liv"
$PY "$D/hmm_livermore.py" "$RUN" merge "$W" "$TC" "$TB"
