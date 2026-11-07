# Experiment tooling

Scripts here are retained as provenance for the dated experiment records under [`docs/experiments/`](../../docs/experiments/README.md). They show how a recorded measurement was produced; they are not a supported general-purpose CLI or authorization to repeat a run.

## Dated folders

- [`2026-11-03/`](2026-11-03/README.md): early detector, fitting, timing and spectrogram investigations. Scripts are historical implementations behind the November 3 records.
- `2026-11-04/`: the bulk of the first research/fleet day. Scripts cover the detector, tracker, event fitting, collective search, benchmark cases, AWS orchestration, data coverage and site pilot. Use the matching `docs/experiments/2026-11-04-*.md` record to identify inputs, criteria, results and run folders.
- `2026-11-05/`: small acceptance/check scripts associated with the dated records; retain their original context when inspecting them.

The experiment index in [`docs/experiments/README.md`](../../docs/experiments/README.md) is generated from the records' index blocks. Rebuild it with `uv run python tools/data/experiments_index.py`; use `--check` for a read-only consistency check.

## Fleet ledgers and launchers

The former `cloud_jobs.md` and `cloud_jobs_sde_d.md` files were team handoff and fleet ledgers. Their proposed launches, “next steps,” run states and cost/capacity notes are historical. Short tombstones retain their original revision and hash; their full contents are preserved in the private local archive. Do not treat archived commands as current instructions or resume jobs from them. Fleet mechanics and current safeguards are documented in [`tools/aws/README.md`](../aws/README.md).

Dated launch scripts (for example `fleet_launch.sh`, `launch_sde_*.sh`, and `sde_b_cloud.sh`) are reproducibility artifacts. They may contain old defaults, case identifiers, branches, input paths or assumptions. The concrete private pilot launcher and session-case helper are fail-closed historical notices; their originals remain private, and the concrete private benchmark registration has been removed. Do not run historical scripts as the current workflow. A new research job needs a current decision/authorization, a new run folder and record, then the `--check` and `--rehearse` steps in the AWS operator guide.

## Reproducing a result

Start with the linked experiment record. It should state the question and pre-run criterion, recordings/cases, command and parameters, results, outcome, script and run folder. Confirm that its inputs are still available and licensed in the data manifest and that code/data hashes match before attempting reproduction. Each reproduction is a new run; never write into a previous run folder. Development recordings are not evaluation evidence.
