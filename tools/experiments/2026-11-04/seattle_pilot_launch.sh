#!/usr/bin/env bash
# The home recorder pilot (docs/experiments/2026-11-04-seattle-home-pilot.md) on one fleet box, shipping exactly the
# files the owner approved, one --input per path, nothing else.
#   tools/experiments/2026-11-04/seattle_pilot_launch.sh APPROVED_LIST [all|broadband|locate] [--silence off] [--box KM]
# all (the default): the spectrogram, the known point, locate, the broadband check. broadband: no locate. locate: the
# spectrogram and locate only. --silence off runs locate with the silence filter off, into $RUN/locate-silence-off.
# --box KM (the box series): locate's box becomes a KM-km square around the site, its centre 73 m west and 131 m south
# of it so the site is off every 200 m node, with the metro box the cut was fetched for (adsbfetch's own record of
# the query, public) as the flight data's envelope; into $RUN/locate[-silence-off]-box<KM>km.
# APPROVED_LIST: one path per line, relative to $DOPPLERTRACK_DATA, as the owner cleared them (blank lines and # comments
# ignored). The run needs every one of these, so a missing one stops the launch before anything ships:
REQUIRED=(
  raw/seattle-home/20261104-ha-pilot-2/20261104T174035Z.flac
  raw/seattle-home/20261104-ha-pilot-2/20261104T180000Z.flac
  raw/seattle-home/20261104-ha-pilot-2/20261104T190000Z.flac
  raw/seattle-home/20261104-ha-pilot-2/session.json
  raw/seattle-home/20261104-ha-pilot-2/timeline.jsonl
  private/traces/20261104-ha-pilot-2/area.npz
  private/traces/20261104-ha-pilot-2/types.jsonl
  private/cases/seattle-home-20261104-ha-pilot-2.json
  private/sites/seattle-home.json
  incoming/seattle-home/site.json
)
# If the owner withholds the site or the case file, this script doesn't run: the relocation fallback (a stand-in
# origin, pseudonymised ICAOs, DEM off) is built first, and ships its own relocated files.
# Before running: the case unblocked in bench/cases.json and committed; `runs` able to run a private job (its $RUN and
# DOPPLERTRACK_CACHE under the box's private/, and `runs pull` into $DOPPLERTRACK_DATA/private/runs/).
set -euo pipefail
CASE=seattle-home-20261104-ha-pilot-2
LIST=${1:?give the approved list from the owner}
MODE=${2:-all}
case "$MODE" in all|broadband|locate) ;; *) echo "unknown mode: $MODE"; exit 1 ;; esac
LOCATE_ARGS="" LOCATE_DIR=locate
shift $(( $# < 2 ? $# : 2 ))
while [ $# -gt 0 ]; do
  case "$1 ${2:-}" in
    "--silence off") LOCATE_ARGS="$LOCATE_ARGS --search-param silence_d_m=null"; LOCATE_DIR=$LOCATE_DIR-silence-off ;;
    "--box "[0-9]*) KM=$2
      LOCATE_ARGS="$LOCATE_ARGS --search-param box_m=$((KM * 1000)) --search-param box_offset_m=[73.0,131.0]"
      LOCATE_ARGS="$LOCATE_ARGS --search-param extraction_box=[47.45,47.80,-122.60,-122.05]"
      BOX_SUFFIX=-box${KM}km ;;
    *) echo "unknown option: $1 ${2:-}"; exit 1 ;;
  esac
  shift 2
done
LOCATE_DIR=$LOCATE_DIR${BOX_SUFFIX:-}
RUNS=tools/aws/runs
[ -z "$(git status --porcelain)" ] || { echo "commit first: the box runs a clean commit"; exit 1; }
# RUNS_EXTRA passes extra runs flags through, e.g. RUNS_EXTRA="--check" or "--rehearse --rehearse-minutes 6" (AGENTS: both before a changed job's real launch).
$RUNS launch --help | grep -q -- "--private" || { echo "runs has no private mode yet (SDE-E): not launching"; exit 1; }
APPROVED=()
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  APPROVED+=("$line")
done < "$LIST"
for p in "${REQUIRED[@]}"; do
  printf '%s\n' "${APPROVED[@]}" | grep -qxF "$p" || { echo "not approved: $p; nothing shipped"; exit 1; }
done
for p in "${APPROVED[@]}"; do
  printf '%s\n' "${REQUIRED[@]}" | grep -qxF "$p" || echo "approved but not needed, not shipped: $p"
done
# Public inputs the box cannot fetch itself (opensky-network.org is unreachable from the boxes); no approval needed.
PUBLIC=(raw/aux/opensky/doc8643AircraftTypes.csv)
INPUTS=()
for p in "${REQUIRED[@]}" "${PUBLIC[@]}"; do INPUTS+=(--input "$p"); done
# On the box: the spectrogram from the FLACs, the known-point check, locate on the case, then the broadband check
# (last, so its failure can't cost locate's record); all under private/. Runs 3-4 ran the first three only.
BOX_CMD=$(cat <<EOF2
set -e
# AircraftTypes() reads the Doc 8643 table from \$DOPPLERTRACK_CACHE and would otherwise fetch it from OpenSky.
mkdir -p "\$DOPPLERTRACK_CACHE" && cp "\$DOPPLERTRACK_DATA/raw/aux/opensky/doc8643AircraftTypes.csv" "\$DOPPLERTRACK_CACHE/"
S=private/derived/$CASE/rec.npz
uv run python -I tools/data/session_spectrogram.py "\$DOPPLERTRACK_DATA/raw/seattle-home/20261104-ha-pilot-2" "\$DOPPLERTRACK_DATA/\$S"
[ "$MODE" = locate ] || uv run python tools/experiments/2026-11-04/known_point_site.py $CASE "\$RUN/known_point"
[ "$MODE" = broadband ] || uv run python -m bench run --profile locate $CASE $LOCATE_ARGS --run-dir "\$RUN/$LOCATE_DIR"
[ "$MODE" = locate ] || uv run python tools/experiments/2026-11-04/broadband_site.py $CASE "\$DOPPLERTRACK_DATA/raw/seattle-home/20261104-ha-pilot-2" "\$RUN/known_point" "\$RUN/broadband"
EOF2
)
$RUNS launch ${RUNS_EXTRA:-} seattle-home-pilot --private --size 4xlarge --fallback-on-demand "${INPUTS[@]}" -- "$BOX_CMD"
