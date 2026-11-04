# Working in this repository

Fork of [mjshiggins/dopplertrack](https://github.com/mjshiggins/dopplertrack): acoustic geolocation from the
Doppler curves of propeller aircraft. `README.md` explains the method; `PLAN.md` is the fork's roadmap and the
record of what has been measured. Read PLAN.md's sections 2 and 6 before starting work.

## Setup

- `uv sync` creates `.venv` in this checkout. Every worktree has its own; uv's shared cache makes it quick.
- `ffmpeg` must be on `PATH` (`brew install ffmpeg`).
- Data and caches live outside the repo, so every worktree sees the same files:
  - `DOPPLERTRACK_DATA` (default `~/data/dopplertrack`): `raw/` inputs, `derived/` pipeline outputs,
    `runs/` experiment outputs, `reference/` papers. Its `MANIFEST.md` says what each file is.
  - `DOPPLERTRACK_CACHE` (default `~/.cache/dopplertrack`): regenerable files. The code already keeps
    terrain tiles there; CPA tables go in `cpa/`.
  - In the main checkout `data` is a symlink to `$DOPPLERTRACK_DATA`. In a worktree, use the variable.

## Tests

- `uv run pytest -q`: about 45 s, no data or network needed. CI runs the same on Ubuntu.
- Real data, opt-in, about 2 min:
  `DOPPLERTRACK_OYSTER_BAY="$DOPPLERTRACK_DATA/derived/oyster_bay" uv run pytest -q tests/test_oyster_bay.py`.
  `test_detect_output` is a strict expected failure until PLAN Phase 2 fixes that path.

## Data rules

- Never write data, caches or run outputs inside the repo, and never commit them.
- `raw/` is read-only. Record any new download in the data root's `MANIFEST.md` (source, licence), then
  refresh the hashes with `uv run python tools/data/manifest.py`; `--check` verifies them.
- Each experiment writes to a new `$DOPPLERTRACK_DATA/runs/<yyyy-mm-dd>-<topic>/`. Never overwrite a run.
- Keep out of git: the papers in `reference/` (copyrighted), xeno-canto audio (CC BY-NC-SA), the YouTube
  audio, and anything derived from them. Eclipse Soundscapes audio is CC BY 4.0; small crops may become
  test fixtures, with attribution.
- Secrets, such as the xeno-canto API key, come from the environment. Never write them into a file here or
  in the data root.
- `--cpa-cache` matches a table by array sizes, not contents (PLAN gap 19), so give every combination of
  grid, flight data and DEM setting its own cache file.

## Git

- `origin` is the fork (SokolskyNikita/dopplertrack), `upstream` is mjshiggins. Pushes use the SokolskyNikita
  account through a repo-local credential helper; leave it alone.
- `main` mirrors upstream; never commit to it. `dev` is the fork's line, and all work branches off `dev`.
  Merge upstream into `dev`; never rebase or force-push `dev`.
- Fork-only files: `PLAN.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/`, `tools/`, `bench/`, `docs/reference/`.
  Work meant for upstream goes in commits that touch only `src/`, `tests/`, `README.md` and `docs/results/`.
  To send it, move those commits onto upstream main (`git rebase --onto upstream/main dev <topic>`, as
  `up/<topic>`) and re-run the tests there.
- Never push, open a pull request or post upstream without the user's go-ahead.
- Commit messages follow upstream's `<area>: <summary>` style.

## Parallel work

- One agent per worktree and branch. The main checkout is the user's: don't switch its branch or commit there
  unless asked.
- Say before starting a long job (`fetch-day`, `detect` on hours of audio, blind searches), run it in the
  background, and keep its log in the run folder.
- Don't edit or move files another session created; ask it or the user.
- Log every experiment's numbers in PLAN.md (until `bench/LOG.md` exists): what ran, on which recordings,
  and that Oyster Bay and the eagle cam are development data, not evaluation.

## Layout

| Path | What |
|---|---|
| `src/dopplertrack/` | the package (upstream's) |
| `tests/` | unit tests, plus the opt-in real-data test |
| `docs/results/` | upstream's committed results |
| `tools/data/` | cutting flight data to boxes, counting passes near sites, the raw-data manifest |
| `tools/reference/` | scripts that converted the papers to Markdown |
| `tools/experiments/<date>/` | scripts behind PLAN.md's numbers; records, not tools |
| `bench/manifest.json` | size, SHA-256, source and licence of every raw input |
| `docs/reference/README.md` | reading list for the papers in `$DOPPLERTRACK_DATA/reference/` |
