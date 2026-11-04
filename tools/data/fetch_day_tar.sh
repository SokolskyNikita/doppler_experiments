#!/usr/bin/env bash
# Download one UTC day's adsb.lol tar (all parts) into $DOPPLERTRACK_DATA/raw/adsb/<date>/.
# Staged in raw/adsb/.staging-<date>/, each part's size checked against the GitHub release API, made
# read-only, then moved into place; refuses to start if the day's folder already exists.
# usage: tools/data/fetch_day_tar.sh YYYY-MM-DD
set -euo pipefail
day=$1
root=${DOPPLERTRACK_DATA:-$HOME/data/dopplertrack}
year=${day%%-*}
tag="v${day//-/.}-planes-readsb-prod-0"
dest="$root/raw/adsb/$day"
stage="$root/raw/adsb/.staging-$day"
[ -e "$dest" ] && { echo "refusing: $dest exists" >&2; exit 1; }
mkdir -p "$stage"
gh release download "$tag" -R "adsblol/globe_history_$year" -p '*.tar*' -D "$stage" --skip-existing
gh api "repos/adsblol/globe_history_$year/releases/tags/$tag" --jq '.assets[] | select(.name|test("tar")) | "\(.name) \(.size)"' |
while read -r name size; do
    got=$(stat -f %z "$stage/$name")
    [ "$got" = "$size" ] || { echo "size mismatch: $name $got != $size" >&2; exit 1; }
    echo "ok $name $size"
done
chmod a-w "$stage"/*
mv "$stage" "$dest"
echo "published $dest"
