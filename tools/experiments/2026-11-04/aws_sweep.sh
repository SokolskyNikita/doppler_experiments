#!/usr/bin/env bash
# The timing-convention sweep (runs/2026-11-04-timing-convention/sweep.sh then sweep2.sh: the same 45 settings
# and cases) on one AWS box, PARALLEL settings at once with DOPPLERTRACK_JOBS=JOBS each, instead of one after
# another. Run by `runs launch` from a checkout at 51f59ce, the sweep's commit; each setting's bench run goes
# to $RUN/<label>/ with its log beside it, and $RUN/sweep.log records each start and end.
set -u
PARALLEL=${PARALLEL:-6}
JOBS=${JOBS:-10}
POS="oyster-bay eagle-cam-clip-18000s oyster-bay-hp150-aac32k"
NEG="oyster-bay-moved-wsw150 oyster-bay-moved-north150"
E="--search-param time_convention=emission"
settings() {
  echo "raw-defaults --profile raw-audio $POS $NEG"
  for g in 8 12 16 20; do
    echo "raw-g${g}-off --profile raw-audio $E --search-param tol_s=$g $POS"
    for t in 2 3 4 6; do
      echo "raw-g${g}-t${t} --profile raw-audio $E --search-param tol_s=$g --search-param sf_tol_s=$t $POS"
    done
  done
  echo "raw-g16-t4-steepest --profile raw-audio $E --search-param tol_s=16 --search-param sf_tol_s=4 --search-param clock_anchor=steepest $POS"
  echo "raw-g16-t4-negatives --profile raw-audio $E --search-param tol_s=16 --search-param sf_tol_s=4 $NEG"
  echo "saved-defaults --profile saved-fit $POS"
  echo "saved-g16-t4 --profile saved-fit $E --search-param tol_s=16 --search-param sf_tol_s=4 $POS"
  for g in 8 12 16 20; do
    echo "saved-eagle-g${g}-off --profile saved-fit $E --search-param tol_s=$g eagle-cam-clip-18000s"
    for t in 2 3 4 6; do
      echo "saved-eagle-g${g}-t${t} --profile saved-fit $E --search-param tol_s=$g --search-param sf_tol_s=$t eagle-cam-clip-18000s"
    done
  done
}
one() { local label=$1; shift
  mkdir -p "$RUN/$label"
  echo "== $label start $(date +%s) load $(cut -d' ' -f1-3 /proc/loadavg)" >> "$RUN/sweep.log"
  DOPPLERTRACK_JOBS=$JOBS .venv/bin/python -m bench run --tier t2 --run-dir "$RUN/$label" "$@" > "$RUN/$label.log" 2>&1
  echo "== $label end $(date +%s) exit $?" >> "$RUN/sweep.log"
}
export -f one
export RUN JOBS
echo "== sweep start $(date +%s) settings $(settings | wc -l) parallel $PARALLEL jobs $JOBS" >> "$RUN/sweep.log"
settings | xargs -P "$PARALLEL" -L 1 bash -c 'one "$@"' _
echo "== done $(date +%s)" >> "$RUN/sweep.log"
