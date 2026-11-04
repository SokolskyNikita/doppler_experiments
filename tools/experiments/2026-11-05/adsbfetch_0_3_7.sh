#!/usr/bin/env bash
# The adsbfetch 0.3.7 acceptance test (docs/experiments/2026-11-05-adsbfetch-0-3-7.md). Serial `area` calls, run the
# way the README's wrapper runs them: from the fetcher's checkout (its own .env loader and automatic session), the
# default cache, the tool's own pacing (--interval left at its default), one provenance manifest and one metadata
# sidecar per call. Nothing here reads .env, the session file or a cookie, and no command line carries one.
#
# usage: RUN=<run folder> tools/experiments/2026-11-05/adsbfetch_0_3_7.sh [part ...]   parts: past repeat recent
set -uo pipefail
RUN=${RUN:?}
FETCHER=$HOME/projects2/adsb_data_fetcher
CLI=$FETCHER/.venv/bin/adsbfetch
ALL=adsbfi,airplaneslive,adsblol,adsbx
mkdir -p "$RUN/out" "$RUN/meta" "$RUN/manifests" "$RUN/logs"

call() { # name, then area args; records the exit code and wall time beside the log
  name=$1; shift
  [ -s "$RUN/logs/$name.rc" ] && { echo "done before: $name"; return 0; }
  t0=$(date +%s)
  (cd "$FETCHER" && ADSBFETCH_OUTDIR=$RUN "$CLI" area "$@" --out "$RUN/out/$name.jsonl" \
     --metadata "$RUN/meta/$name.json" --manifest "$RUN/manifests/$name.jsonl" < /dev/null > "$RUN/logs/$name.log" 2>&1)
  rc=$?
  echo "$rc $(( $(date +%s) - t0 ))" > "$RUN/logs/$name.rc"
  echo "$(date -u +%FT%TZ) $name rc=$rc wall=$(( $(date +%s) - t0 ))s"
}

# sites: window, box, --near (lat,lon,ellipsoidal m = DEM ground + 1.5 m + approximate EGM2008 undulation)
OB_W=2026-09-08T20:45:00Z/2026-09-08T21:15:00Z;  OB_B=40.70,41.05,-73.75,-73.30;  OB_N=40.876466,-73.524951,-30
EG_W=2024-12-28T19:50:00Z/2024-12-28T20:10:00Z;  EG_B=26.55,26.85,-82.05,-81.65;  EG_N=26.702359,-81.847766,-22
EC_W=2024-04-07T01:39:34Z/2024-04-07T02:09:34Z;  EC_B=40.63,40.93,-84.20,-83.80;  EC_N=40.7831545,-84.0028968,250
EX_W=2025-04-20T04:10:00Z/2025-04-20T04:40:00Z;  EX_B=51.50,51.80,0.25,0.75;     EX_N=51.6483,0.4953,103
LV_B=37.55,37.85,-122.00,-121.65;  LV_N=37.6934,-121.8205,85

past() {
  call ob_all       --window $OB_W --bbox $OB_B --source $ALL --discoveries "$RUN/meta/ob_all.discoveries.json" --holes "$RUN/meta/ob_all.holes.json"
  call ob_near10    --window $OB_W --bbox $OB_B --source $ALL --near $OB_N --radius-km 10
  call ob_near4     --window $OB_W --bbox $OB_B --source $ALL --near $OB_N --radius-km 4
  for s in ${ALL//,/ }; do call ob_near10_$s --window $OB_W --bbox $OB_B --source $s --near $OB_N --radius-km 10; done
  call ob_near10_preserve --window $OB_W --bbox $OB_B --source $ALL --near $OB_N --radius-km 10 --preserve-observations
  call ob_near10_props    --window $OB_W --bbox $OB_B --source $ALL --near $OB_N --radius-km 10 --props-only
  call eg_all       --window $EG_W --bbox $EG_B --source $ALL
  call eg_near10    --window $EG_W --bbox $EG_B --source $ALL --near $EG_N --radius-km 10
  call ec_all       --window $EC_W --bbox $EC_B --source $ALL
  call ec_near10    --window $EC_W --bbox $EC_B --source $ALL --near $EC_N --radius-km 10
  call ex_all       --window $EX_W --bbox $EX_B --source $ALL
  call ex_near10    --window $EX_W --bbox $EX_B --source $ALL --near $EX_N --radius-km 10
}

repeat() { # the same queries again: what a settled history costs on a warm cache
  call ob_all_again --window $OB_W --bbox $OB_B --source $ALL
  call eg_all_again --window $EG_W --bbox $EG_B --source $ALL
  call ob_shifted   --window $OB_W --bbox 40.75,41.00,-73.65,-73.40 --source $ALL    # a smaller view of the same snapshots
}

recent() { # Livermore, today; the windows are passed in LV_WINDOWS as name=START/END pairs
  for nw in ${LV_WINDOWS:?}; do
    call "lv_${nw%%=*}" --window "${nw#*=}" --bbox $LV_B --source $ALL --near $LV_N --radius-km 10 ${LV_EXTRA:-}
  done
}

for part in "${@:-past}"; do "$part"; done
