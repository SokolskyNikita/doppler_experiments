#!/bin/sh
# One fleet box's whole round-3 job (docs/proposals/2026-11-04-tracker-likelihood.md): the development
# references and constants, the synthetic ROC, the pre-registered pick, and only then the Livermore passes and the
# development events at the picked knobs, and the merge. With `knobs` it stops after the pick. Every step skips
# its finished units, so the same command resumes a stopped box.
#
# usage: ll_box.sh [knobs]          (in $RUN, which the box sets)
set -eu
D=$(dirname "$0")
PY="uv run --frozen python"

$PY "$D/hmm_livermore.py" "$RUN" references
$PY "$D/ll_roc.py" "$RUN" constants
$PY "$D/ll_roc.py" "$RUN" roc > "$RUN/roc.log" 2>&1
$PY "$D/ll_roc.py" "$RUN" pick
[ "${1:-}" = knobs ] && exit 0
$PY -c "import json, sys; sys.exit(json.load(open(sys.argv[1]))['chosen'] is None)" "$RUN/ll_chosen.json"

$PY "$D/ll_livermore.py" "$RUN" livermore > "$RUN/livermore.log" 2>&1
$PY "$D/ll_livermore.py" "$RUN" dev > "$RUN/dev.log" 2>&1
$PY "$D/ll_livermore.py" "$RUN" merge
