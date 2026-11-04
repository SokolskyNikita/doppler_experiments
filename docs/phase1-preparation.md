# Before Phase 1

Phase 1 will change how workers build the closest point of approach (CPA) table and scan detector
windows. Two changes are useful beforehand. Give the detector worker named inputs and outputs so
an agent can see what crosses the process boundary. Give the agent one offline check command and
a short guide to the code it will edit.

## 1. Name the detector worker inputs and outputs

In `tracks.py`, `detect_events` packs 14 values into a tuple for `_scan_window`, which unpacks
them in the same order. Several have the same Python type but different meanings. Swapping the
frequency step in hertz and the time step in seconds still produces a valid call. Both default
to 2, so a run with default settings could even produce the expected numbers. Give the request
typed fields with names that make the units apparent. Construct it by name and read its fields
by name in the worker. The serial map and the process pool should use the same request.
[Detector implementation](../src/dopplertrack/tracks.py)

Give the coarse candidate returned by the worker named fields as well. The merge currently reads
the fifth tuple item to decide whether two proposals are too close together. That field is the
**emission CPA time in recording seconds**. The final separation check after refinement uses the
**heard CPA time**. Naming the coarse field makes it clear which time to use when editing either
stage. Keep the public detector arguments, refinement defaults and saved event format compatible
with existing callers.

### Preserve which candidate wins a tie

Today's detector merges coarse candidates from all windows using a descending tuple sort. The
fields are compared in order by score, fundamental frequency, speed, slant range and emission
CPA time. The first candidate kept can suppress a nearby one. Sorting a new record by score
alone could therefore consistently keep a different candidate even though both runs report the
same winning score. Move this merge out of `detect_events` into a small function that takes the
coarse candidates, the minimum separation and the number to keep, and make the existing sort key
explicit there.

Add one focused regression test with the record change, calling the merge function directly.
Supply two candidates, as if from different windows, with equal scores and emission times closer
than the minimum separation. Present the 120 Hz proposal first and the 121 Hz proposal second.
Assert that the 121 Hz proposal survives. This exercises the user-visible consequence of the sort
order while allowing the within-window and final refined-score sorts to keep their own rules. The
existing tests already cover silence and applying the score threshold after refinement.
[Detector tests](../tests/test_phase0_cli.py)

Exercise the new records through the real process pool on a small synthetic input that produces a
candidate. Run `detect_events` with `workers=2` and with `workers=1`, and require the two event
lists to be equal. Two workers are enough to cross the process boundary; the default starts one
process per core and spends the Tier 0 budget on startup. This checks that the request reaches
the worker and that its result makes the return trip, and it is the first form of Phase 1's
check that `jobs=1` and `jobs=10` give the same results byte for byte. The tie test above
independently specifies which candidate the merge must keep.

## 2. Give the next agent one check command and an edit map

Add `tools/check.sh` so a provisioned checkout can run the following checks offline with one
command. A failure in any step should cause the command to fail. Add ruff and mypy to the `dev`
dependency group, so `uv sync` provides everything the command runs.

| Check | What it establishes |
|---|---|
| Ruff and scoped mypy | Ruff, limited to its pyflakes rules (`--select F`) on `src/` and `tests/`, catches stale imports and unused variables left by the worker edit. Fix what it reports today in the same change. Mypy runs on `tracks.py` only, following imports silently, so it checks that the producer and consumer agree on the record fields and their types without reporting the rest of the package, which has few annotations. |
| Ordinary offline pytest suite | The detector regression and existing cache, coverage and search tests pass together. Exclude opt-in recordings even when a developer has exported their data path. |
| [Installed-wheel smoke check](../tests/install_smoke.py) | Outside the checkout, the installed command can invoke ffmpeg, turn a local WAV into a spectrogram and run detection. This exercises the package that a caller actually installs. |

Time the command on this Mac without competing jobs, with dependencies already available locally.
Report the pytest time against the one-minute Tier 0 test target and give the total command time
separately. In the Tests section of [AGENTS.md](../AGENTS.md), beside `tools/check.sh`, document
how to run the detector test or the existing cache tests on their own so an agent can check a
single edit before running the full suite.

Write a short edit map, `docs/architecture.md`, and link it from AGENTS.md. Add it to AGENTS.md's
fork-only files. Organize it around the two edits a Phase 1 agent is about to make.

- **Changing detector scheduling.** Trace a request from `detect_events` into `_scan_window` and a
  candidate back through merging and refinement. Point to the tie test and the process-pool check.
  Explain that fits use recording seconds and the CPA table uses Unix seconds. Locked scoring
  aligns the candidate flight's heard time with the first event's heard time in the recording.
  [Scoring implementation](../src/dopplertrack/score.py)
- **Changing the CPA build.** Trace the call from `pipeline.run_search` through
  `pipeline.cached_cpa_table` to `search.cpa_table`. Identify where the cache lock is held, where
  the fingerprint is computed and where the rows are built. Link the existing cache tests so the
  next agent can check cache reuse and recovery when it changes the build.
  [Pipeline](../src/dopplertrack/pipeline.py) · [CPA computation](../src/dopplertrack/search.py) · [Cache tests](../tests/test_cache.py)

**Ready for Phase 1** when the named records work in the detector, the tie test and offline
command pass, and the edit map leads from each worker task to its code and checks. The parallelism
item in [PLAN.md](../PLAN.md) owns the CPA comparison and performance measurements.
