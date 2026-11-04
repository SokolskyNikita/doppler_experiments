# Experiment records

One file per experiment, named `<date>-<topic>.md`. Each record gives:
- the question;
- the setup and the recordings;
- the numbers;
- the outcome;
- where the script (`tools/experiments/<date>/`) and the outputs (`$DOPPLERTRACK_DATA/runs/`) are.

[PLAN.md](../../PLAN.md) cites only the conclusions.

Oyster Bay and the eagle cam shaped the method, so every result on them is development data: it can guide work but never counts as evaluation.

| Record | Question | Outcome |
|---|---|---|
| [2026-11-03-phase0-review-regression](2026-11-03-phase0-review-regression.md) | Do the review fixes preserve CPA geometry while masking unsupported evidence? | 66 offline tests pass; Oyster Bay has 2 passes and 1 expected failure; reception holes preserve CPA proposals and mask curve evidence |
| [2026-11-03-phase0-regression](2026-11-03-phase0-regression.md) | Do Phase 0's data and trajectory masks preserve the Oyster Bay checks? | 2 passed, 1 expected failure; the detector-fit bias remains Phase 2 work |
| [2026-11-03-event2-bias](2026-11-03-event2-bias.md) | Why does Oyster Bay's event 2 fail the search gates? | Its f0 fits 5–11 % high and its timing 5–10 s short, under both objectives tested |
| [2026-11-03-extra-consistency](2026-11-03-extra-consistency.md) | Can the flyovers a search didn't use tell the true flight pair from wrong ones? | A lead: with a ±15 s time gate, only the true pair explained any |
| [2026-11-03-gate-tolerances](2026-11-03-gate-tolerances.md) | Do wider search gates let the true pair through safely? | No: at ±12 s a wrong pair wins on both recordings |
| [2026-11-03-rewindow](2026-11-03-rewindow.md) | Does re-fitting `detect`'s flyovers in narrower windows help? | No: neither window rule tested suits both recordings |
| [2026-11-03-timing-conventions](2026-11-03-timing-conventions.md) | Which event time should pairing compare? | A lead: like-for-like steepest-fall times agree within 0.5–2.7 s for the contrast and `detect` fits on both recordings, though not for every fit |
