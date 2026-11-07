# AWS operations

This directory contains the AWS CDK stack, the `runs` operator CLI and the scripts used on the dev box and job boxes. The fleet was built for isolated, reproducible research jobs; the operational design and its measurements are recorded in [the fleet experiment](../../docs/experiments/2026-11-04-aws-fleet.md).

This page describes the code's workflow. It does not report live AWS state, capacity, quotas, costs or running jobs. Check live state with the relevant `runs` read command when needed. Historical fleet plans and outcomes belong in dated experiment records; they do not authorize a launch. The research campaign is paused. Only explicitly authorized reset/check work should use the dev box; a research job needs its own current decision and authorization.

## Credentials and data boundaries

`runs` uses the AWS profile named by `AWS_PROFILE`, defaulting to `dopplertrack`, in us-west-2. Do not use the personal root profile. AWS credentials are read from the configured profile and are never stored in the repository.

The data root and caches are outside the checkout. Fleet launch inputs are resolved by `tools/aws/runs.py`; private paths are refused by default. Seed uploads apply the code's private-prefix and owner exclusion filters, with date-named day traces as the documented exception. Private allow-list entries are exact-file approvals and do not authorize folders. See `is_private()`, `seed_excludes()`, `refuse_private()` and `seed()` in `runs.py` for the active rules. Never put private data, credentials, site coordinates or handoff material in source, docs, run logs or untracked files.

## Dev box workflow

The dev box is for the repository's offline check and explicitly approved development tasks. It is reached through Systems Manager; there is no SSH ingress. These commands read or operate the box:

```sh
tools/aws/runs dev status
tools/aws/runs dev run -- tools/check.sh
tools/aws/runs dev stop
```

`dev run` creates a unique temporary checkout under the box's `~/runs/`, runs the command there, then removes that checkout. `dev sync` instead refreshes a persistent checkout at `~/branch`; use it only when an interactive checkout is needed.

Inspect the complete upload before syncing. A sync transfers code, not the data root: `runs.py` uploads a bundle of HEAD and its reachable history, the tracked working diff, and a tarball of untracked non-ignored files to the private bucket's `dev/` prefix. The box reconstructs that checkout and runs `uv sync --frozen`. A local `data` symlink is transferred as a link, not followed into the external data root. Do not leave private or unrelated material in untracked non-ignored files before a dev sync.

`tools/check.sh` is the repository's authorized offline check. It runs Ruff's F rules on `src/` and `tests/`, checks the generated experiment index, runs scoped mypy, runs pytest with the opt-in Oyster Bay environment variable unset, then builds a wheel and runs `tests/install_smoke.py` from a fresh temporary environment outside the checkout. The suite does not require research recordings or a data-root upload. The remote `uv sync --frozen` may need package access if the required packages are not cached; offline refers to test data and test behavior.

A systemd timer runs `tools/aws/box/devbox-idle.sh` once per minute. After 30 consecutive idle minutes—no temporary `dev run` checkout, no Systems Manager command/session and load average below 0.5—it powers off the box. This replaced the earlier CloudWatch idle alarm. Stopping the instance preserves its attached root volume and data. The idle timer is a code-level behavior; check `runs dev status` for actual state.

## Running a research job

Research jobs use one fleet box per job or shard. A launch is an external, billable action and requires a current, explicit decision. `AGENTS.md` also requires both preflight and rehearsal before a new or changed job:

1. Run the exact proposed launch with `--check`. This resolves inputs, checks private-data guards, bucket/cache/code availability and placement capacity without running the job.
2. Run it with `--rehearse` for long enough to reach the first full stage. This uploads the job bundle and runs the command through the job supervisor on the dev box in a private `/scratch` layout. Rehearsal can use network and can write a rehearsal record to the bucket; it is not a read-only check.
3. Only then launch the approved job. Each experiment needs a decision criterion, a fresh run folder, a recorded command and parameters, and an experiment record with the generated index block.

Typical command shape (reference only; it is not approval to run):

```sh
tools/aws/runs launch TOPIC --case CASE_ID --check -- COMMAND
# Repeat the same proposed command with --rehearse, then remove those flags for an authorized launch.
```

The CLI also supports named inputs, caches, shards, wait/pull/log/status and resume. Inspect `tools/aws/runs --help` and the parser in `runs.py` for current flags. `--resume` normally reuses the saved job bundle and inputs from that job; an explicit `--repo` overrides its code source. It does not implicitly mean “run the current branch.” Never resume a historical job solely because a ledger mentions it.

## Data and run flow

- Job code is bundled from the chosen checkout (HEAD, tracked diff and untracked non-ignored files) and uploaded to the private bucket. Nothing is pushed to GitHub.
- Inputs are individually named; run folders are outputs and only a named prior run can be supplied as input. `runs/` is never uploaded wholesale.
- The job supervisor prepares the checkout and dependencies, stages approved inputs/caches under its isolated scratch/data layout, writes provenance to a new run folder, and uploads run outputs/checkpoints. `runs pull` copies a completed job's run folder to a new local run path and merges eligible cache deltas without overwriting existing cache entries.
- For jobs involving private inputs, the exact-file allow list and private run/cache handling apply. Read the guards in `runs.py` and `tools/aws/README.md` source history before changing these rules.

## Infrastructure changes

Before a deployment, run `tools/aws/check.sh` as required by `AGENTS.md`. It performs local shell/static and synthesized-stack assertions; it does not deploy or contact AWS. A deployment, stack teardown, bucket deletion, quota request, IAM change, or removal of stored data requires explicit authorization. Current prices, quota grants, stack outputs, instances and bucket contents must be checked live; dated values in experiment records are historical measurements only.
