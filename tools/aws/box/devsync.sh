#!/bin/bash
# Puts an engineer's branch on the dev box: devsync.sh <s3 code prefix> <commit> <checkout>. The prefix holds
# what `runs launch` ships to a job box (code.bundle, dirty.patch, untracked.tar); the old checkout is replaced.
set -euo pipefail
src=$1 commit=$2 dest=$3
mkdir -p "$(dirname "$dest")"
work=$(mktemp -d)
trap 'rm -rf "$work" "$dest.new"' EXIT
s5cmd --log error cp "$src/*" "$work/"
git clone -q --no-checkout "$work/code.bundle" "$dest.new"
git -C "$dest.new" checkout -q --detach "$commit"
if [ -s "$work/dirty.patch" ]; then git -C "$dest.new" apply --binary "$work/dirty.patch"; fi
if [ -s "$work/untracked.tar" ]; then tar xf "$work/untracked.tar" -C "$dest.new"; fi
rm -rf "$dest"
mv "$dest.new" "$dest"
cd "$dest" && uv sync --frozen -q
