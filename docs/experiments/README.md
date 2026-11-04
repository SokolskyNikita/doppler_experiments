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
| [2026-11-04-bench-baselines](2026-11-04-bench-baselines.md) | What do the seed cases give at upstream a16b700, from saved fits and from raw audio, and does the current code match? | Identical on both profiles. Saved fits reproduce the published results; raw audio locates no positive: Oyster Bay's fit is biased (true pair 10th), and the eagle cam's second event is the wrong flyover |
| [2026-11-04-freqtrack](2026-11-04-freqtrack.md) | Does a local tracker with an off state beat `ridge()` against the trajectory reference on the Livermore passes? | Not met: run 1 had lower error (0.45 % against 0.48 %) and 2.8× fewer bridges but 17× more fragments; the one retune (run 2) failed all three. The off state keeps it on manoeuvring passes (0.84 % against 15 %); ssqueezepy locks onto other lines (14 %) |
| [2026-11-04-parallel-cpa](2026-11-04-parallel-cpa.md) | Does the parallel CPA build give the serial table byte for byte, and does any output depend on `--jobs`? | Yes and no: every table, search CSV and detection is identical; Oyster Bay's cold CPA build takes 26 s at 10 jobs (405 s before), once the cache is saved uncompressed |
| [2026-11-04-bench-seed-cases](2026-11-04-bench-seed-cases.md) | Does the benchmark runner reproduce the saved-fit results, and what do the seed cases give? | Yes: Oyster Bay 1st of 328, 123 m / 43 m, 4.9 %, locations bit-identical; the eagle-cam clip matches the full recording; both moved-box negatives return wrong answers (north 148 km off by 3.2 %, WSW 182 km off by 10.7 %) with margins above the true positives' |
| [2026-11-04-site-traffic](2026-11-04-site-traffic.md) | Which Eclipse and A2O recordings have prop passes within 6 and 12 km during their actual hours? | ESID 375, 740 and 710 have 3–10 within 6 km and 937 none in 25 h; A2O Townsville 10–12, Aroona 1, Duval 0. Townsville's published point is 1.77 km from its file-name GPS fix, beyond MANIFEST's obfuscation bound |
| [2026-11-04-blind-labels](2026-11-04-blind-labels.md) | In three blind-labelled 20 min clips, how many tonal events does an ADS-B pass explain? | A lead, from first-pass labels: few. 1 of 11 at Oyster Bay, 0 of 6 at ESID 740, 1–3 of 6 at the eagle cam; most passes within 12 km aren't visible |
| [2026-11-04-livermore-audit](2026-11-04-livermore-audit.md) | Can the Livermore microphone and start times be recovered, and do ridge, WAV and ADS-B agree in time? | Yes: the author's recorder point to under 1 m, WAVs are the ridge ±5.00 s, and the ridge clock matches ADS-B to about 1 s per pass with no common offset beyond 0.5 s |
| [2026-11-03-gap-aware-spectrogram](2026-11-03-gap-aware-spectrogram.md) | Can the spectrogram keep a recording's timeline through gaps, and what are the Eclipse sites' gaps? | Yes: frames over a gap are invalid, Oyster Bay is unchanged byte for byte, and a gap over the steep part weakens the fit. ESID 740's and 710's minute files abut; their only gaps are two missing-file holes a day |
| [2026-11-03-phase1-prep-regression](2026-11-03-phase1-prep-regression.md) | Do the detector's named records leave `detect`'s output unchanged? | Yes: Oyster Bay's `detect` JSON is byte-identical before and after; 2 passed, 1 expected failure |
| [2026-11-03-phase0-review-regression](2026-11-03-phase0-review-regression.md) | Do the review fixes preserve CPA geometry while masking unsupported evidence? | 66 offline tests pass; Oyster Bay has 2 passes and 1 expected failure; reception holes preserve CPA proposals and mask curve evidence |
| [2026-11-03-phase0-regression](2026-11-03-phase0-regression.md) | Do Phase 0's data and trajectory masks preserve the Oyster Bay checks? | 2 passed, 1 expected failure; the detector-fit bias remains Phase 2 work |
| [2026-11-03-event2-bias](2026-11-03-event2-bias.md) | Why does Oyster Bay's event 2 fail the search gates? | Its f0 fits 5–11 % high and its timing 5–10 s short, under both objectives tested |
| [2026-11-03-extra-consistency](2026-11-03-extra-consistency.md) | Can the flyovers a search didn't use tell the true flight pair from wrong ones? | A lead: with a ±15 s time gate, only the true pair explained any |
| [2026-11-03-gate-tolerances](2026-11-03-gate-tolerances.md) | Do wider search gates let the true pair through safely? | No: at ±12 s a wrong pair wins on both recordings |
| [2026-11-03-rewindow](2026-11-03-rewindow.md) | Does re-fitting `detect`'s flyovers in narrower windows help? | No: neither window rule tested suits both recordings |
| [2026-11-03-timing-conventions](2026-11-03-timing-conventions.md) | Which event time should pairing compare? | A lead: like-for-like steepest-fall times agree within 0.5–2.7 s for the contrast and `detect` fits on both recordings, though not for every fit |
