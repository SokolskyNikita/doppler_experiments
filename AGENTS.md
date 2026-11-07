# Working in this repository

Independent research workspace derived from [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack): acoustic geolocation from the
Doppler curves of propeller aircraft. `README.md` explains the method; `docs/experiments/` is the record of what
has been measured.

**Two plans, in order.** [docs/plans/research-readiness.md](docs/plans/research-readiness.md) is the engineering
plan: one method per file, configurable recipes, a minimal study runner. It must close (its §5 exit checks) before
any research starts. [PLAN.md](PLAN.md) is the research plan that builds on it: claim boundary, evidence, gates,
owner decisions. Both are short enough to read whole. Work that seeks accuracy or a scientific verdict belongs in
PLAN.md; an engineering need found during research is handled inside that research item.
[docs/architecture.md](docs/architecture.md) traces the current code paths.

| Document | Owns |
|---|---|
| `AGENTS.md` | working, privacy, compute and verification rules |
| `README.md` | installed user-facing behavior and limitations |
| `docs/plans/research-readiness.md` | the engineering plan and its exit checks |
| `PLAN.md` | research decisions, gates, open questions and owner decisions |
| `docs/architecture.md` | current implementation paths and verification gaps |
| `docs/experiments/` | dated records of evidence, failures, retunes and corrections; `designs/` holds the frozen designs of experiments that ran |

**Handoff.** `$DOPPLERTRACK_DATA/private/handoff-2026-11-05.md` (outside the repo: it names the owner's machine, accounts and transcript locations, none of which belong in a public fork) is the state of play at the end of the first fleet day: the owner's standing rules that are not written elsewhere, who owned what and what is open, what was established, the Seattle pilot, the procedures a fresh operator needs, and the decisions pending on the owner. A session taking over coordination reads it first; a session on a narrow task reads only the parts that bear on it (the file is about 25 KB). Handoffs, like everything else under `private/`, never go into the tree.

## Setup

- `uv sync` creates `.venv` in this checkout. Every worktree has its own; uv's shared cache makes it quick.
- `ffmpeg` must be on `PATH` (`brew install ffmpeg`).
- Data and caches live outside the repo, so every worktree sees the same files:
  - `DOPPLERTRACK_DATA` (default `~/data/dopplertrack`): `raw/` inputs, `derived/` pipeline outputs,
    `runs/` experiment outputs, `reference/` papers. Its `MANIFEST.md` says what each file is.
  - `DOPPLERTRACK_CACHE` (default `~/.cache/dopplertrack`): regenerable files. The code already keeps
    terrain tiles there; CPA tables go in `cpa/`.
  - In the main checkout `data` is a symlink to `$DOPPLERTRACK_DATA`. In a worktree, use the variable.
- Long jobs run on AWS, one spot box per job in us-west-2, not on the shared Mac: `tools/aws/runs launch
  <topic> --case ID -- <command>` ships the branch (bundle plus diff, nothing pushed), runs it with `$RUN`
  set, and `runs pull` brings the run folder back; `runs dev run -- tools/check.sh` uses the dev box.
  Profile `dopplertrack`; costs, inputs and the bucket's layout are in [tools/aws/README.md](tools/aws/README.md).
  Run `tools/aws/check.sh` before any `cdk deploy`.
  - Before a new or changed job's real launch, run the same command with `--check` (inputs, guard, capacity; seconds)
    and then `--rehearse` (the job on the dev box in a fleet box's layout, for long enough to reach its first full
    stage). A rehearsal catches layout, path and network bugs that the Mac can't show.

## Tests

- Run targeted tests locally while editing. For example:
  - detector/CLI: `uv run pytest -q tests/test_phase0_cli.py`;
  - CPA cache: `uv run pytest -q tests/test_cache.py`.
- Run the full `tools/check.sh` on the AWS dev box with `tools/aws/runs dev run -- tools/check.sh`; it covers
  lint, typing, the offline suite, and the installed-wheel smoke check. Follow the fleet check and rehearsal
  rules in Setup above before any real job launch.
- Real data, opt-in, about 2 min:
  `DOPPLERTRACK_OYSTER_BAY="$DOPPLERTRACK_DATA/derived/oyster_bay" uv run pytest -q tests/test_oyster_bay.py`.
  It downloads terrain tiles the first time, so it needs the network on a cold cache.
  `test_detect_output_passes_the_filters_at_truth` is a strict expected failure until a research gate fixes
  that path.
- The benchmark: `uv run python -m bench run [case ...]` makes a run folder, writes each case's `result.json`
  and its hash before reading any label, and collects `results.json`; `bench compare <a> <b>` diffs two runs.
  With a cold CPA table it is a long job: say so first and run it in the background.
  `--profile saved-fit|raw-audio` picks the events; `--revision a16b700` runs another commit through its own
  CLI in an exported, hash-verified environment under `$DOPPLERTRACK_CACHE/revisions/` (`src/dopplertrack/evaluation/revisions.py`).
  Run Python from that export only with `-B`: bytecode in its tree fails the check.

## Data rules

- Never write data, caches or run outputs inside the repo, and never commit them.
- Files in `raw/` are read-only; add new downloads beside them and never modify one. Record each new
  download in the data root's `MANIFEST.md` (source, licence), then refresh the hashes with
  `uv run python tools/data/manifest.py`; `--check` verifies them.
- Each experiment writes to a new run folder: `RUN=$(uv run python tools/data/new_run.py <topic>)` creates
  `$DOPPLERTRACK_DATA/runs/<yyyy-mm-dd>-<topic>[-n]/` with a `run.json` recording the commit and whether the
  tree had uncommitted changes. Add the command and parameters there, and never write into an older run.
- Keep out of git: the papers in `reference/` (copyrighted), xeno-canto audio (CC BY-NC-SA), the YouTube
  audio, and anything derived from them. Eclipse Soundscapes audio is CC BY 4.0; small crops may become
  test fixtures, with attribution.
- Secrets, such as the xeno-canto API key, come from the environment. Never write them into a file here or
  in the data root.
- `--cpa-cache` rejects a table built from different inputs and rebuilds it, so give every combination of
  grid, flight data and DEM setting its own cache file, or each switch costs a rebuild.

## Git

- `origin` is the independent repo (SokolskyNikita/doppler_experiments), `upstream` is mjshiggins. Pushes use the SokolskyNikita
  account through a repo-local credential helper; leave it alone.
- `main` is the independent repository's default and development branch; create work branches from `main`.
  The former upstream baseline is preserved under the tag
  `archive/upstream-main-before-independence`. Evaluate upstream changes as explicit method imports; do not
  routinely merge upstream into `main`. Never rebase or force-push `main`.
- `.claude/` is ignored and never committed: it holds the app's worktrees, this checkout's settings and the
  PM's landing helper, none of which belong in the fork. History was rewritten on 2026-11-05 to drop it and the
  handoff; every branch SHA from before then changed.
- Fork-only files: `PLAN.md`, `AGENTS.md`, `CLAUDE.md`, `tools/`, `bench/`, `docs/reference/`,
  `docs/experiments/`, `docs/plans/`, `docs/architecture.md`, `docs/layout.md`. They may share a commit with upstream code; drop them when sending work upstream.
- To send work upstream, branch `up/<topic>` from `upstream/main`, cherry-pick the topic's upstream commits
  by SHA, compare the series with `git range-diff`, and re-run the tests there. Don't use
  `git rebase --onto upstream/main dev <topic>`: it drops every commit `dev` already contains.
- A fix that needs nothing from the fork can instead start from `upstream/main` and be merged into `main`.
- Never push, open a pull request or post upstream without the user's go-ahead.
- Commit messages follow upstream's `<area>: <summary>` style.

## Parallel work

- Start each new session in a dedicated worktree and topic branch based on `main` before editing or
  running jobs; create them without asking. Reuse the session's worktree if one is already assigned.
- One agent per worktree and branch. The main checkout is the user's: don't switch its branch or commit there
  unless asked.
- New Claude worktrees start from the HEAD of the checkout they're created from (normally `main`, set in
  `.claude/settings.json`), and uncommitted changes don't follow, so commit what a new session needs first.
- Worktrees isolate source edits, not the shared data and caches: never write a cache file or run output in
  place where another session could read it half-written.
- Say before starting a long job (`fetch-day`, `detect` on hours of audio, blind searches), run it in the
  background, and keep its log in the run folder.
- Don't edit or move files another session created; ask it or the user.
- Never cancel another session's jobs or delete cloud objects without the owner's explicit approval.
- Before retiring a worktree, check its starting revision and save its uncommitted changes as a patch outside the
  repo; removed files go to the Trash.
- Record every experiment as `docs/experiments/<date>-<topic>.md`: the question, what ran on which recordings,
  the numbers, the outcome, and the script and run folder. Oyster Bay and the eagle cam are development data, not
  evaluation. PLAN.md keeps only the conclusions.
- Right under a record's title, put its index block, `<!-- index`, `question: <one line>`, `outcome: <one line>`,
  `-->`, then run `uv run python tools/data/experiments_index.py` to rebuild `docs/experiments/README.md`'s table. Never
  edit the table by hand; after a merge that conflicts on it, rerun the script. `tools/check.sh` fails when the table and
  the blocks disagree.

## Layout

| Path | What |
|---|---|
| `src/dopplertrack/` | the package (upstream's) |
| `tests/` | unit tests, plus the opt-in real-data test |
| `docs/results/` | upstream's committed results |
| `tools/data/` | cutting flight data to boxes, counting passes near sites, the raw-data manifest, new run folders |
| `tools/reference/` | scripts that converted the papers to Markdown |
| `tools/experiments/<date>/` | scripts behind the numbers in `docs/experiments/`; records, not tools |
| `bench/manifest.json` | size, SHA-256, source and licence of every raw input |
| `bench/cases.json` | benchmark cases: sources, start times, recipes for derived files, search parameters, labels |
| `bench/*.py` | `uv run python -m bench validate\|build\|run\|merge\|inputs\|tier1\|report\|compare`: rebuild a case's derived files, run cases blind into a run folder (`--shard`, `--resume`), merge shards, list a job's inputs, render each record's HTML report into a new run folder, compare two runs |
| `docs/architecture.md` | edit map: the detector and CPA-build code paths and the tests that check them |
| `docs/experiments/` | one record per experiment: question, setup, numbers, outcome, script and run folder; `designs/` the frozen designs of experiments that ran |
| `docs/plans/` | the research-readiness plan |
| `docs/reference/README.md` | reading list for the papers in `$DOPPLERTRACK_DATA/reference/` |
