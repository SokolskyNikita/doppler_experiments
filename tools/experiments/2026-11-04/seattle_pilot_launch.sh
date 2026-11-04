#!/usr/bin/env bash
# The home recorder pilot (docs/experiments/2026-11-04-seattle-home-pilot.md) on one fleet box, shipping exactly the
# files the owner approved, one --input per path, nothing else.
#   tools/experiments/2026-11-04/seattle_pilot_launch.sh APPROVED_LIST [all|broadband|locate|bandtest] [--session ID]
#       [--silence off] [--box KM] [--spacing M]
# all (the default): the spectrogram, the known point, locate, the broadband check. broadband: no locate. locate: the
# spectrogram and locate only. bandtest (a full-band session's pre-registered band test): the spectrogram at 40-450 Hz
# and at the case's wide edge (its spectrogram_wide recipe), then the known-point and broadband checks on each, no
# locate. --session ID: another session of the recorder (default the pilot's), its case seattle-home-<ID> made by
# tools/data/home_session_case.py. --silence off runs locate with the silence filter off, into $RUN/locate-silence-off.
# --box KM (the box series): locate's box becomes a KM-km square around the site, its centre 73 m west and 131 m south
# of it so the site is off every 200 m node, with the metro box the cut was fetched for (adsbfetch's own record of
# the query, public) as the flight data's envelope; into $RUN/locate[-silence-off]-box<KM>km. --spacing M (with
# --box) sets the grid spacing in metres, into ...-box<KM>km-sp<M>m.
# APPROVED_LIST: one path per line, relative to $DOPPLERTRACK_DATA, as the owner cleared them (blank lines and # comments
# ignored). The pilot's run needs every one of these, so a missing one stops the launch before anything ships; another
# session needs its case, the site files, its session.json and timeline.jsonl, and ships every approved file under its
# raw/ and private/traces/ folders:
PILOT_REQUIRED=(
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
LIST=${1:?give the approved list from the owner}
MODE=${2:-all}
case "$MODE" in all|broadband|locate|bandtest) ;; *) echo "unknown mode: $MODE"; exit 1 ;; esac
LOCATE_ARGS="" LOCATE_DIR=locate SESSION=20261104-ha-pilot-2
shift $(( $# < 2 ? $# : 2 ))
while [ $# -gt 0 ]; do
  case "$1 ${2:-}" in
    "--session "?*) SESSION=$2 ;;
    "--silence off") LOCATE_ARGS="$LOCATE_ARGS --search-param silence_d_m=null"; LOCATE_DIR=$LOCATE_DIR-silence-off ;;
    "--box "[0-9]*) KM=$2
      LOCATE_ARGS="$LOCATE_ARGS --search-param box_m=$((KM * 1000)) --search-param box_offset_m=[73.0,131.0]"
      LOCATE_ARGS="$LOCATE_ARGS --search-param extraction_box=[47.45,47.80,-122.60,-122.05]"
      BOX_SUFFIX=-box${KM}km${BOX_SUFFIX:-} ;;
    "--spacing "[0-9]*) LOCATE_ARGS="$LOCATE_ARGS --search-param spacing_m=$2"; BOX_SUFFIX=${BOX_SUFFIX:-}-sp${2}m ;;
    *) echo "unknown option: $1 ${2:-}"; exit 1 ;;
  esac
  shift 2
done
LOCATE_DIR=$LOCATE_DIR${BOX_SUFFIX:-}
CASE=seattle-home-$SESSION
SDIR=raw/seattle-home/$SESSION
RUNS=tools/aws/runs
[ -z "$(git status --porcelain)" ] || { echo "commit first: the box runs a clean commit"; exit 1; }
# RUNS_EXTRA passes extra runs flags through, e.g. RUNS_EXTRA="--check" or "--rehearse --rehearse-minutes 6" (AGENTS: both before a changed job's real launch).
$RUNS launch --help | grep -q -- "--private" || { echo "runs has no private mode yet (SDE-E): not launching"; exit 1; }
APPROVED=()
while IFS= read -r line; do
  case "$line" in ''|\#*) continue ;; esac
  APPROVED+=("$line")
done < "$LIST"
if [ "$SESSION" = 20261104-ha-pilot-2 ]; then
  REQUIRED=("${PILOT_REQUIRED[@]}")
else
  REQUIRED=(private/cases/$CASE.json private/sites/seattle-home.json incoming/seattle-home/site.json
            $SDIR/session.json $SDIR/timeline.jsonl)
  for p in "${APPROVED[@]}"; do
    case "$p" in "$SDIR"/*.flac|private/traces/"$SESSION"/*) REQUIRED+=("$p") ;; esac
  done
  printf '%s\n' "${REQUIRED[@]}" | grep -q "\.flac$" || { echo "no approved audio under $SDIR; nothing shipped"; exit 1; }
fi
for p in "${REQUIRED[@]}"; do
  printf '%s\n' "${APPROVED[@]}" | grep -qxF "$p" || { echo "not approved: $p; nothing shipped"; exit 1; }
done
for p in "${APPROVED[@]}"; do
  printf '%s\n' "${REQUIRED[@]}" | grep -qxF "$p" || echo "approved but not needed, not shipped: $p"
done
# Public inputs the box cannot fetch itself (opensky-network.org is unreachable from the boxes); no approval needed.
PUBLIC=(raw/aux/opensky/doc8643AircraftTypes.csv)
# A case whose flight data is a public cut (derived/ or raw/, e.g. fetch-day --keep-jets) ships it as a public input.
# The private case file is read here only for those paths and the band test's edge, nothing else of it is printed.
read -r TRACES WIDE < <(uv run python - "$CASE" <<'EOF3'
import json, os, sys
from pathlib import Path
d = json.loads((Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data/dopplertrack")) / "private/cases" / f"{sys.argv[1]}.json").read_text())
t = d["flight_data"]["traces"]
t = t if isinstance(t, str) else " ".join(t)
w = next((x.get("fmax_hz") for x in d.get("derived", []) if x["path"] == d.get("spectrogram_wide")), None)
print(",".join(p for p in t.split() if p.startswith(("derived/", "raw/"))) or "-", w or "-")
EOF3
)
[ "$TRACES" = - ] || IFS=, read -r -a PUB_TRACES <<< "$TRACES"
[ "$TRACES" = - ] || PUBLIC+=("${PUB_TRACES[@]}")
[ "$MODE" != bandtest ] || [ "$WIDE" != - ] || { echo "$CASE has no spectrogram_wide: nothing to test"; exit 1; }
INPUTS=()
for p in "${REQUIRED[@]}" "${PUBLIC[@]}"; do INPUTS+=(--input "$p"); done
# On the box: the spectrogram from the FLACs, the known-point check, locate on the case, then the broadband check
# (last, so its failure can't cost locate's record); all under private/. Runs 3-4 ran the first three only. bandtest
# adds the wide spectrogram and both checks on it, and skips locate.
BOX_CMD=$(cat <<EOF2
set -e
# AircraftTypes() reads the Doc 8643 table from \$DOPPLERTRACK_CACHE and would otherwise fetch it from OpenSky.
mkdir -p "\$DOPPLERTRACK_CACHE" && cp "\$DOPPLERTRACK_DATA/raw/aux/opensky/doc8643AircraftTypes.csv" "\$DOPPLERTRACK_CACHE/"
S=private/derived/$CASE/rec.npz
uv run python -I tools/data/session_spectrogram.py "\$DOPPLERTRACK_DATA/$SDIR" "\$DOPPLERTRACK_DATA/\$S"
[ "$MODE" = locate ] || uv run python tools/experiments/2026-11-04/known_point_site.py $CASE "\$RUN/known_point"
[ "$MODE" = broadband ] || [ "$MODE" = bandtest ] || uv run python -m bench run --profile locate $CASE $LOCATE_ARGS --run-dir "\$RUN/$LOCATE_DIR"
[ "$MODE" = locate ] || uv run python tools/experiments/2026-11-04/broadband_site.py $CASE "\$DOPPLERTRACK_DATA/$SDIR" "\$RUN/known_point" "\$RUN/broadband"
if [ "$MODE" = bandtest ]; then
  W=private/derived/$CASE/rec-wide.npz
  uv run python -I tools/data/session_spectrogram.py "\$DOPPLERTRACK_DATA/$SDIR" "\$DOPPLERTRACK_DATA/\$W" --fmax $WIDE
  uv run python tools/experiments/2026-11-04/known_point_site.py $CASE "\$RUN/known_point_wide" --fmax $WIDE --spectrogram "\$W"
  uv run python tools/experiments/2026-11-04/broadband_site.py $CASE "\$DOPPLERTRACK_DATA/$SDIR" "\$RUN/known_point_wide" "\$RUN/broadband_wide" --fmax $WIDE --spectrogram "\$W"
fi
EOF2
)
$RUNS launch ${RUNS_EXTRA:-} seattle-home-pilot --private --size 4xlarge --fallback-on-demand "${INPUTS[@]}" -- "$BOX_CMD"
