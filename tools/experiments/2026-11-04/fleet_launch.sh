#!/bin/sh
# SDE-C's six fleet boxes, all at once (cloud_jobs.md): the whitening arms (Tier 2 and Tier 1 for each of time and
# frequency) and the tracker's whole job under each whitening, so whichever whitening wins, its tracker result
# exists. Run from a clean checkout; RUNS is the runs wrapper (default tools/aws/runs). Collect with
# fleet_merge.py once they are done.
set -eu
RUNS=${RUNS:-tools/aws/runs}
REPO=$(git rev-parse --show-toplevel)
D=tools/experiments/2026-11-04
CACHES="--cache detections --cache window_fits --cache terrarium"
SEED="--case oyster-bay --case eagle-cam-clip-18000s --case oyster-bay-hp150-aac32k --case oyster-bay-moved-north150 --case oyster-bay-moved-wsw150"
HMM_INPUTS="--input derived/livermore --input runs/2026-11-04-livermore-audit
  --input raw/audio/livermore/zenodo-23424278/final_results_40_cases.csv
  --input raw/audio/youtube/oyster_bay.webm --input raw/audio/youtube/swfl_2024-12-28.webm
  --input derived/oyster_bay/traces_ny.npz --input derived/swfl/traces_swfl.npz --cache terrarium"

for arm in time frequency; do
    # shellcheck disable=SC2086
    "$RUNS" launch "whiten-$arm-t2" --repo "$REPO" $SEED --input derived/whiten_frequency $CACHES \
        -- "uv run --frozen python $D/whiten_frequency.py \"\$RUN\" t2 $arm"
    # shellcheck disable=SC2086
    "$RUNS" launch "whiten-$arm-t1" --repo "$REPO" --inputs-from "uv run --frozen python -m bench inputs --tier1" \
        --input derived/whiten_frequency $CACHES \
        -- "uv run --frozen python $D/whiten_frequency.py \"\$RUN\" t1 $arm"
    # shellcheck disable=SC2086
    "$RUNS" launch "hmm-$arm" --repo "$REPO" $HMM_INPUTS -- "sh $D/hmm_box.sh $arm"
done
