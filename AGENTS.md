# Working in this repository

Independent research workspace derived from [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack):
acoustic geolocation from the Doppler curves of propeller aircraft.

## What to read

Read only what the task needs, and only the section it touches: list headings with `rg -n '^#{2,3} ' FILE`.
A subagent reads only the sections its task names.

- **Engineering work:** [docs/plans/research-readiness.md](docs/plans/research-readiness.md), the plan that must
  close (its §5 exit checks) before any research starts. Read §2 (rules) and the item you are working on.
- **Research work:** [PLAN.md](PLAN.md), which builds on the readiness plan. Read §1 and the gate you are working on.
  Work that seeks accuracy or a scientific verdict belongs here; an engineering need found during research is
  handled inside that research item.
- **Code paths:** [docs/architecture.md](docs/architecture.md) (current paths and verification gaps) and
  [docs/layout.md](docs/layout.md) (package layers).
- **Never read whole:** `bench/manifest.json` and `bench/cases.json` (hundreds of KB; query by case ID with `jq` or
  `rg`), `docs/experiments/README.md` and `docs/reference/README.md` (search them), and the private handoff
  `$DOPPLERTRACK_DATA/private/handoff-2026-11-05.md` (about 25 KB; a session taking over coordination reads its
  §4 standing rules and §10 pending decisions, others only the part that bears on the task). Nothing under
  `private/` goes into the tree.

## Setup

- `uv sync` creates `.venv` in this checkout; every worktree has its own. `ffmpeg` must be on `PATH`.
- Data and caches live outside the repo, so every worktree sees the same files:
  `DOPPLERTRACK_DATA` (default `~/data/dopplertrack`: `raw/`, `derived/`, `runs/`, `reference/`; its `MANIFEST.md`
  says what each file is) and `DOPPLERTRACK_CACHE` (default `~/.cache/dopplertrack`: regenerable files, CPA tables
  in `cpa/`). In a worktree, use the variables.
- Long jobs run on AWS, not on the Mac: `tools/aws/runs launch <topic> --case ID -- <command>` ships the branch and
  runs it with `$RUN` set; `runs pull` brings the run folder back. Profile `dopplertrack`; details in
  [tools/aws/README.md](tools/aws/README.md). Run `tools/aws/check.sh` before any `cdk deploy`.
- Before a new or changed job's real launch, run it with `--check` (inputs, guard, capacity) and then `--rehearse`
  (on the dev box in a fleet box's layout, until its first full stage).

## Tests

- Run targeted tests locally while editing, e.g. `uv run pytest -q tests/test_phase0_cli.py` or `tests/test_cache.py`.
- Run the full `tools/check.sh` (lint, typing, offline suite, installed-wheel smoke) on the dev box:
  `tools/aws/runs dev run -- tools/check.sh`. Not on the Mac.
- Real data, opt-in: `DOPPLERTRACK_OYSTER_BAY="$DOPPLERTRACK_DATA/derived/oyster_bay" uv run pytest -q tests/test_oyster_bay.py`
  (needs the network on a cold terrain cache). `test_detect_output_passes_the_filters_at_truth` is a strict expected
  failure until a research gate fixes that path.
- The benchmark: `uv run python -m bench run [case ...]` writes each `result.json` and its hash before reading any
  label; `bench compare <a> <b>` diffs two runs; `--profile` picks the events; `--revision <commit>` runs another
  commit in an exported, hash-verified environment (run Python there only with `-B`). With a cold CPA table it is a
  long job: say so first and run it in the background.

## Data rules

- Never write data, caches or run outputs inside the repo, and never commit them.
- `raw/` is read-only: add new downloads beside it, record each in `MANIFEST.md` (source, licence), then run
  `uv run python tools/data/manifest.py` (`--check` verifies).
- Each experiment writes to a new run folder: `RUN=$(uv run python tools/data/new_run.py <topic>)`. Add the command
  and parameters to its `run.json`; never write into an older run.
- Keep out of git: the papers in `reference/`, xeno-canto audio (CC BY-NC-SA), YouTube audio, and anything derived
  from them. Eclipse Soundscapes audio is CC BY 4.0; small crops may become fixtures, with attribution.
- Secrets come from the environment; never write them into a file here or in the data root.
- Give every combination of grid, flight data and DEM setting its own `--cpa-cache` file, or each switch rebuilds.

## Git

- `origin` is SokolskyNikita/doppler_experiments (pushes use its repo-local credential helper; leave it alone);
  `upstream` is mjshiggins. `main` is the development branch: branch from it, never rebase or force-push it.
- Upstream changes come in as explicit method imports, not routine merges. To send work upstream, branch
  `up/<topic>` from `upstream/main`, cherry-pick the topic's upstream commits, check with `git range-diff`, and drop
  fork-only files (`PLAN.md`, `AGENTS.md`, `CLAUDE.md`, `tools/`, `bench/`, `docs/` except upstream's
  `docs/results/`, `docs/superpowers/` and `docs/experiments.md`).
- `.claude/` is ignored and never committed. Never push, open a pull request or post upstream without the owner's
  go-ahead. Commit messages use `<area>: <summary>`.

## Parallel work

- Each session works in its own worktree and topic branch from `main`; create them without asking. The main
  checkout is the owner's: don't switch its branch or commit there unless asked. Commit what a new session needs
  first: uncommitted changes don't follow into a new worktree.
- Worktrees share data and caches: never write a cache file or run output where another session could read it
  half-written.
- Say before starting a long job, run it in the background, and keep its log in the run folder.
- Don't edit or move files another session created, cancel its jobs, or delete cloud objects without asking.
- Before retiring a worktree, save its uncommitted changes as a patch outside the repo; removed files go to the Trash.
- Record every experiment as `docs/experiments/<date>-<topic>.md` (question, recordings, numbers, outcome, script,
  run folder), with its index block (`<!-- index`, `question: …`, `outcome: …`, `-->`) under the title, then run
  `uv run python tools/data/experiments_index.py`; never edit that table by hand. Oyster Bay and the eagle cam are
  development data, not evaluation. PLAN.md keeps only conclusions.

## Layout

| Path | What |
|---|---|
| `src/dopplertrack/` | the package |
| `tests/` | unit tests, plus the opt-in real-data test |
| `bench/` | the benchmark CLI (`python -m bench`), `cases.json` (cases and labels) and `manifest.json` (raw-input hashes) |
| `tools/data/`, `tools/aws/` | data handling and the AWS fleet |
| `tools/experiments/<date>/` | scripts behind the numbers in `docs/experiments/`; records of their revision, not tools |
| `docs/plans/` | the research-readiness plan |
| `docs/experiments/` | one record per experiment; `designs/` holds the frozen designs of experiments that ran |
| `docs/reference/` | reading lists for the papers in `$DOPPLERTRACK_DATA/reference/` |
| `docs/results/` | upstream's committed results |
