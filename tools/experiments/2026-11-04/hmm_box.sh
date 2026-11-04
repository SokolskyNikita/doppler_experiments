#!/bin/sh
# One fleet box's whole tracker job for one whitening setting (cloud_jobs.md, SDE-C job 2 then 3): the
# development references, the theta pairs on synthetic noise (the seven theta_cont at once, 12 workers each),
# the pick on the synthetic weak pass, then the Livermore passes and the development events at the picked pair,
# and the merge. The knobs are set before any real recording is tracked. Every step skips its finished units,
# so the same command resumes a stopped box (runs launch --resume).
#
# With MIN_COVERAGE, the pick is hmm_knobs.py's retune 1 (pairs covering at least that much of the weak pass).
#
# usage: hmm_box.sh time|frequency [MIN_COVERAGE]          (in $RUN, which the box sets)
set -eu
W=$1
COV=${2:-}
CHOSEN=chosen.json
[ -n "$COV" ] && CHOSEN=chosen_cov$COV.json
D=$(dirname "$0")
PY="uv run --frozen python"
JOBS=${DOPPLERTRACK_JOBS:-$($PY -c 'from dopplertrack.parallel import default_jobs; print(default_jobs())')}

$PY "$D/hmm_livermore.py" "$RUN" references

# Each pairs process holds 12 workers, each with the whole 2 h noise image (about 1.3 GB at its peak), so as many
# theta_cont run at once as 16 GB each allows: all seven on a 128 GB box, four on a 64 GB one.
MEM_GB=$(awk '/MemTotal/ {print int($2 / 1048576)}' /proc/meminfo 2>/dev/null || echo 16)
PAR=$((MEM_GB / 16)); [ "$PAR" -lt 1 ] && PAR=1; [ "$PAR" -gt 7 ] && PAR=7
export PY D RUN W
# shellcheck disable=SC2016
printf '%s\n' 3 4 5 6 7 8 9 | xargs -P "$PAR" -I TC \
    sh -c 'DOPPLERTRACK_JOBS=12 $PY "$D/hmm_knobs.py" "$RUN" pairs "$W" TC > "$RUN/pairs_${W}_TC.log" 2>&1'
$PY "$D/hmm_knobs.py" "$RUN" pick "$W" ${COV:+"$COV"}

read -r TC TB <<EOF
$($PY -c "import json, sys; c = json.load(open(sys.argv[1]))['chosen']; print(c[0], c[1])" "$RUN/hmm_knobs/$W/$CHOSEN")
EOF
echo "picked theta_cont $TC theta_birth $TB"

DEV=6
DOPPLERTRACK_JOBS=$((JOBS > DEV + 1 ? JOBS - DEV : 1)) $PY "$D/hmm_livermore.py" "$RUN" livermore "$W" "$TC" "$TB" \
    > "$RUN/livermore_$W.log" 2>&1 &
liv=$!
DOPPLERTRACK_JOBS=$DEV $PY "$D/hmm_livermore.py" "$RUN" dev "$W" "$TC" "$TB" > "$RUN/dev_$W.log" 2>&1
wait "$liv"
$PY "$D/hmm_livermore.py" "$RUN" merge "$W" "$TC" "$TB"
