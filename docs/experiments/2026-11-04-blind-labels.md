# Blind layer-1 labels and their flight association (2026-11-04)

**Question.** PLAN 5.3 asks for whole clips labelled blind (layer 1: is a tone or flyover there?) before any ADS-B is shown, then associated with the passes (layer 2). In a few short clips, how many tonal events are there, and how many of them does an ADS-B pass explain?

**Setup.** No change to the package. New tool `tools/data/label_sheet.py`, with three steps:
- `sheet` draws the blind contact sheets.
- `overlay` draws, after the blind pass, each ADS-B pass within 12 km as its modelled curve, plus a close-up per event and nearby pass.
- `check` validates a label file.

The sheets use the package's STFT: a 2.048 s Hann window every 0.25 s from 40 to 450 Hz. Display-only processing then comes in four steps:
1. less each bin's median over the sheet;
2. less each frame's median over frequency, which removes broadband bursts;
3. a 2 s running mean along time;
4. a 3-bin maximum along frequency.

Each sheet covers 10 min in 2 min strips. Clips were chosen by fixed rules before any flight data was opened:

| Clip | Span | Why |
|---|---|---|
| Oyster Bay (development) | 0–1200 s | the recording's first 20 min |
| Eagle cam (development) | 3600–4800 s | the second hour's first 20 min |
| ESID 740, 2024-04-07 | 17:00–17:20 UTC (local noon) | the Eclipse site decision 2 proposes for calibration, not evaluation. Read straight from the zip. The grey band at each minute on its sheets is the STFT losing about 1 s at each file's edges: the files are 60 s and abut (SDE-C's header check), not 55 s with 5 s gaps as MANIFEST then said. The tool now joins abutting files |

I labelled all three clips by looking at the sheets, as the PM asked. These are first-pass labels for the user to spot-check, not checked ones. Each window records its class, start and end, the lines seen (entry and exit frequency) and the number of harmonics, plus who labelled it and whether it was blind. Windows tile the span, so "absent" is explicit. Layer 2 used the clocks from the known-point fits (Oyster Bay 2026-09-08 20:17:30.3 UTC, eagle cam 2024-12-28 14:21:08.5 UTC, good to about a second) and the AudioMoth file names for ESID 740.

**Numbers.**

| Clip | Events labelled blind (clear / overlapping / uncertain / masked) | ADS-B passes within 12 km heard in the span | Events matched: probable / possible | Passes matched |
|---|---|---|---|---|
| Oyster Bay | 12 (4 / 0 / 7 / 1) | 5, at 4.1–11.8 km | 1 / 0 | 1 of 5 |
| Eagle cam | 9 (1 / 1 / 4 / 3) | 15, at 0.5–10.4 km (2 are heard after the span ends) | 1 / 3 (two of them ambiguous between two passes heard 1.6 s apart) | 1 probable, 3 possible |
| ESID 740 | 6 (1 / 0 / 5 / 0) | 0 | – | – |

- **Oyster Bay.**
  - **Matched.** Only ob-e03 matches a pass: N360NY at 7.3 km, whose curve at f0 293 Hz follows a 345 to 255 Hz line.
  - **Unmatched.** Three of the four clear events have no pass within 40 s (ob-e05, ob-e08, ob-e10). Two uncertain events rise and then flatten, which is not a Doppler shape; a boat engine is likelier.
  - **Unheard.** The closest pass, N829RP at 4.1 km, shows no visible curve.
- **Eagle cam.**
  - **Matched.** The overlapping event sw-e01 holds a steep fall that matches N4956N (1.9 km) and a slow fall that N8073G (2.3 km) and N110DP (3.7 km) fit equally.
  - **Unmatched.** The clear event sw-e07 is unmatched: the only pass nearby is 10.2 km away and flat over the window, while its lines fall 16–19 %.
  - **Masked.** The closest passes of all, N250FM at 0.5 km and N1045 at 1.5 km, fall inside stretches labelled masked (bird calls and broadband bursts), and no curve could be traced there.
- **ESID 740.** It has six tonal events and no ADS-B pass within 12 km during those 20 minutes, so all six are unmatched.

**Outcome: a lead for V2 and E5, from first-pass labels.**
- **Most events have no ADS-B pass.** In these clips most tonal events have no pass: 10 of 11 at Oyster Bay, 6 of 6 at ESID 740, and 3 of 6 events outside the masked stretches at the eagle cam (two more only possibly matched). And most passes within 12 km aren't visible (Oyster Bay: 4 of 5). An ADS-B pass is a weak proxy for an acoustic event in both directions. Detection precision measured against ADS-B would count all of these unmatched events as false alarms, so the blind labels, not the passes, are its denominator.
- **Several unmatched events don't look like flyovers.** Some rise and flatten; one at ESID 740 falls and then rises in a V. Detection needs a shape check, or the threshold curve of Phase 2 item 6 will be set by boats and vehicles as much as by jets.
- **Caveats.**
  - The labels come from downscaled images, and many are "uncertain".
  - Lines and boundaries are read to a few seconds and about 5–10 Hz.
  - The clocks for the two development clips come from a fit.
  - The user's spot-check comes before any of this is scored. Nothing has been tuned on the ESID 740 labels.
- **What to spot-check first.**
  - the four Oyster Bay clear events: ob-e03, ob-e05, ob-e08, ob-e10;
  - eagle cam sw-e01 and sw-e07;
  - ESID 740's e740-e06;
  - the two masked eagle-cam stretches with close passes: sw-e05 and sw-e06.

**Files.** Labels: `bench/labels/oyster_bay-0000-1200.json`, `swfl_2024-12-28-3600-4800.json` and `ESID_740_2024-04-07-61200-62400.json`. ESID 740's recording seconds count from 2024-04-07 00:00:00 UTC; its blind sheets were drawn with 17:00 as second 0. **Tool:** `tools/data/label_sheet.py`. **Outputs:** `runs/2026-11-04-blind-labels/`: the blind sheets in `oyster_bay/`, `swfl/` and `esid740/`, and the layer-2 sheets, close-ups and `passes.json` in `*_overlay/`.
