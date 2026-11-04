# Evaluation prep: ESID 375, 710 and 937 made ready without a search (2026-11-04)

<!-- index
question: Can the evaluation cases be made ready to run, before any search and without reading a label, so a design that passes development is judged on them the same hour?
outcome: Yes for the three Eclipse sites: spectrograms, flight data, weather and 1 km CPA tables in about 0.2 box-hours; Seattle's sites wait on their data and the private-case design
-->

## Question

PLAN decision 2 writes the sets before any search. The evaluation cases (ESID 375, 710 and 937, of the Eclipse
Soundscapes sites) had their flight data and station temperatures but no spectrogram, search settings or CPA table,
so the first design to pass development couldn't have been judged on them without hours of preparation. Can that be
done now, reading no label and running no search?

## What ran

Version 3 of each case (`bench/cases.json`), at 162a759, on fleet boxes, one job per case and file:
- **Spectrogram:** `tools/data/eclipse_spectrogram.py` on the whole day zip. It unzips the AudioMoth WAVs into a
  temporary folder, builds the gap-aware spectrogram at the CLI defaults (0.25 s hop, 40–450 Hz, holes between files
  marked invalid), and removes the folder. One c7a/c8g.8xlarge per case.
- **CPA table:** `bench prepare <case>`, which builds the table a search of the case would build: the search box at
  1 km with the DEM, both days' flight data joined at midnight, 12 km range, 15 °C (weather is off by default), with
  the segments built as `run_search` builds them so the fingerprint matches. One c7g.4xlarge per case.
- The case is read without its labels (`prepare_case` drops them before anything else), and no audio, event or
  search is touched by the table job.

## What each case now has

| Case | Spectrogram (frames, invalid) | Flight data | Weather | 1 km CPA table (points, segments, records, build) |
|---|---|---|---|---|
| eclipse-esid375 | 357,912, 16 | 2024-04-07 v2 and 04-08 cuts, metadata, margin | KAOH 8.9 °C | 15,099, 1,622, 816,919, 8.3 s |
| eclipse-esid710 | 345,648, 792 (its missing-file holes) | the same for its box | KPIA 7.2 °C | 15,000, 999, 1,068,428, 7.8 s |
| eclipse-esid937 | 357,912, 16 | the same for its box | KPOF 20.0 °C | 15,049, 753, 510,537, 7.2 s |

Each case also has a full search block (1 km grid, tol_s 6 s, the speed and distance gates, silence 6 km, 12 km
range, DEM, its own table name `cpa/bench/eclipse-esid<n>_1000m_dem.npz`), refine settings, detect-mode events and the
profiles `locate` and `raw-audio`. All three stay blocked: evaluation cases run only at milestones.

**The CPA tables are not stored.** `runs` doesn't bring `cpa/` back from a box, by design, since a table rebuilds on
any box in seconds; these took 7–8 s at 1 km. So the tables were built and timed, and a run on the fleet rebuilds each
in about 8 s.

## Cost

Six jobs: three spectrograms of 3 min each on 8xlarge boxes ($0.04 each) and three tables of 1 min each on 4xlarge
boxes; about 0.2 box-hours and $0.15 in all. `runs fleet --util --history`: the spectrograms peaked at 3.9–4.4 GB of
their 64 GB, so a 4xlarge would have done; the table jobs at 1.8–2.0 GB of 32 GB.

## Outcome

The three Eclipse evaluation cases are ready: a passing design runs on them as soon as the milestone opens, with only
the CPA table's 8 s to rebuild. Seattle's two sites aren't prepared: their data arrived as the owner's private
recordings, which wait on the private-case design (`docs/proposals/2026-11-04-private-cases.md`) and the fleet guard.

## Files

`tools/data/eclipse_spectrogram.py`, `bench/prepare.py` (`bench prepare`), `bench/cases.json` (version 3 of the three
cases), `tests/test_bench.py`. Runs: `runs/2026-11-04-eval-spec-esid{375,710,937}/` and
`runs/2026-11-04-eval-cpa-esid{375,710,937}/` (`prepare.json`); launches in `runs/2026-11-04-sde-b-fleet-launch/`.
The spectrograms are filed under `derived/eclipse/ESID_<n>/rec_full.npz` (data root MANIFEST.md).
