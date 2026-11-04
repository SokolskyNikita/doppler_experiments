#!/bin/bash
# The fleet's checks, before any `cdk deploy`: shellcheck on the box scripts, pyflakes, the offline tests of
# runs and the supervisor, and assertions on the synthesized stack. No AWS call.
set -euo pipefail
cd "$(dirname "$0")"
echo "== shellcheck"
shellcheck -S warning box/*.sh runs
echo "== ruff (pyflakes rules)"
uvx ruff check -q --select F ./*.py box/*.py stack_checks.py ../../tests/test_aws_runs.py
echo "== the stack"
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 uv run --frozen pytest -q -p no:cacheprovider stack_checks.py
echo "== runs and the supervisor"
(cd ../.. && uv run --frozen pytest -q -p no:cacheprovider tests/test_aws_runs.py)
