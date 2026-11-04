#!/bin/sh
# Copies the unit files of pulled round-3 jobs (runs pull) into one new run folder, without replacing a file
# already there, for ll_box.sh's pick or merge step to read through `runs launch --input-run runs/<that folder>`.
# Copying only; nothing is computed here.
#
# usage: ll_collect.sh TOPIC JOB ...          (prints the new folder's name)
set -eu
TOPIC=$1; shift
DATA=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}
OUT=$(uv run --frozen python tools/data/new_run.py "$TOPIC")
for job in "$@"; do
    [ -d "$DATA/runs/$job" ] || { echo "$DATA/runs/$job missing: runs pull $job first" >&2; exit 1; }
    python3 "$(dirname "$0")/copy_new.py" "$DATA/runs/$job" "$OUT" constants.json dev_references.json ll_chosen.json ll_roc ll
done
printf '%s\n' "$@" > "$OUT/collected_from.txt"
basename "$OUT"
