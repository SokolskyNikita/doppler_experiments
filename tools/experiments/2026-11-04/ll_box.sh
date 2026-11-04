#!/bin/sh
# Round 3's fleet steps (docs/proposals/2026-11-04-tracker-likelihood.md), in order, every one skipping its finished
# units so the same command resumes a stopped box:
#   roc         the development references and constants, then this box's grid points of the synthetic ROC
#               (runs launch --shards n splits them, units.shard)
#   pick SRC    the pre-registered pick, over the ROC units collected into runs/SRC (ll_collect.sh)
#   passes SRC  this box's Livermore passes and development events at SRC's pick (--shards n splits them)
#   merge SRC   the summary over the pass units collected into runs/SRC
#   all         every step on this one box
# Each step's inputs come over with `runs launch --input runs/SRC`. RETUNE=retune1 in the command selects ll_roc.py's
# retune for the constants (and so for every later step, which reads them).
#
# usage: ll_box.sh roc | pick SRC | passes SRC | merge SRC | all          (in $RUN, which the box sets)
set -eu
D=$(dirname "$0")
PY="uv run --frozen python"
STEP=$1
SRC=${2:-}

from_src() {
    [ -n "$SRC" ] || { echo "$STEP needs SRC" >&2; exit 2; }
    cp -Rn "$DOPPLERTRACK_DATA/runs/$SRC/." "$RUN/"
}

case $STEP in
roc|all)
    $PY "$D/hmm_livermore.py" "$RUN" references
    $PY "$D/ll_roc.py" "$RUN" constants ${RETUNE:+"$RETUNE"}
    $PY "$D/ll_roc.py" "$RUN" roc > "$RUN/roc.log" 2>&1
    [ "$STEP" = roc ] && exit 0
    ;;
pick|passes|merge) from_src ;;
*) echo "unknown step $STEP" >&2; exit 2 ;;
esac

case $STEP in
pick|all) $PY "$D/ll_roc.py" "$RUN" pick ;;
esac
case $STEP in
passes|all)
    $PY -c "import json, sys; sys.exit(json.load(open(sys.argv[1]))['chosen'] is None)" "$RUN/ll_chosen.json"
    $PY "$D/ll_livermore.py" "$RUN" livermore > "$RUN/livermore.log" 2>&1
    $PY "$D/ll_livermore.py" "$RUN" dev > "$RUN/dev.log" 2>&1
    ;;
esac
case $STEP in
merge|all) $PY "$D/ll_livermore.py" "$RUN" merge ;;
esac
