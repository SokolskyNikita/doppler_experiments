#!/usr/bin/env bash
# Offline checks for a provisioned checkout (`uv sync` done, ffmpeg on PATH); any failure fails the script.
# usage: tools/check.sh
set -euo pipefail

cd "$(dirname "$0")/.."
start=$SECONDS

echo "== ruff (pyflakes rules)"
uv run --frozen ruff check --select F src tests

echo "== mypy (tracks.py, search.py, parallel.py)"
uv run --frozen mypy --follow-imports=silent --ignore-missing-imports src/dopplertrack/tracks.py \
    src/dopplertrack/search.py src/dopplertrack/parallel.py

echo "== pytest (offline; the opt-in recording is excluded)"
pytest_start=$SECONDS
env -u DOPPLERTRACK_OYSTER_BAY uv run --frozen pytest -q
pytest_s=$((SECONDS - pytest_start))

echo "== installed-wheel smoke check"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
uv build --wheel --out-dir "$tmp/dist" --quiet
uv venv --quiet "$tmp/venv"
uv pip install --quiet --python "$tmp/venv/bin/python" "$tmp"/dist/*.whl
cp tests/install_smoke.py "$tmp/"
(cd "$tmp" && "$tmp/venv/bin/python" -I install_smoke.py)

echo "pytest: ${pytest_s} s (Tier 0 target: 60 s)"
echo "total: $((SECONDS - start)) s"
