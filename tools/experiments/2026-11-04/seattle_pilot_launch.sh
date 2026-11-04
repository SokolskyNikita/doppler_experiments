#!/usr/bin/env bash
# The home recorder pilot (docs/experiments/2026-11-04-seattle-home-pilot.md) on one fleet box, shipping exactly the
# files the owner approved, one --input per path, nothing else.
#   tools/experiments/2026-11-04/seattle_pilot_launch.sh APPROVED_LIST
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
RUNS=tools/aws/runs
[ -z "$(git status --porcelain)" ] || { echo "commit first: the box runs a clean commit"; exit 1; }
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
INPUTS=()
for p in "${REQUIRED[@]}"; do INPUTS+=(--input "$p"); done
# On the box: the spectrogram from the FLACs, the known-point check, then locate on the case; all under private/.
BOX_CMD=$(cat <<EOF2
set -e
S=private/derived/$CASE/rec.npz
uv run python -I tools/data/session_spectrogram.py "\$DOPPLERTRACK_DATA/raw/seattle-home/20261104-ha-pilot-2" "\$DOPPLERTRACK_DATA/\$S"
uv run python tools/experiments/2026-11-04/known_point_site.py $CASE "\$RUN/known_point"
uv run python -m bench run --profile locate $CASE --run-dir "\$RUN/locate"
EOF2
)
$RUNS launch seattle-home-pilot --private --size 4xlarge --fallback-on-demand "${INPUTS[@]}" -- "$BOX_CMD"
