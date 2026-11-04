# The owner's home recorder: what an indoor phone hears (pilot, 2026-11-04)

<!-- index
question: What does the owner's indoor phone recorder hear of the propeller traffic around it, and what does locate make of a 2.3 h session?
outcome: Pending: the criteria below were written before the run
-->

## Question

The first independent recording of our own (PLAN 5.6): 2.32 h from the owner's home recorder, session
`20261104-ha-pilot-2`, 17:40:35–19:59:51Z. It is a private case (`seattle-home-20261104-ha-pilot-2`,
`docs/proposals/2026-11-04-private-cases.md`): this record gives no position, no per-flight time or range, nothing that
with public ADS-B would place the site. Two questions: which of the propeller passes near the site does the phone
hear, and what does `locate` find on its own?

## The recording

- **Device and chain:** the phone's microphone through Android's unprocessed source (no noise suppression, gain
  control or EQ), 48 kHz, low-passed to 450 Hz (linear-phase FIR, 80 dB from 550 Hz) and stored as 1 kHz mono FLAC,
  one file an hour (data root MANIFEST.md, private section).
- **Clock:** the phone's ADC sample clock, mapped to UTC each minute from scrcpy timestamps against the NTP-synced Mac,
  less a 0.19 s latency from vibration tests; the stated start is good to about 1 s.
- **Placement:** indoors, the phone flat and screen down on a drawer, the Wi-Fi router 1 m below it, not at a window,
  its main microphone facing west.
- **Traffic, from the ADS-B cut** (PM's count): in the 2.3 h, 105 aircraft within 6 km ground range, 83 of them jets
  and 21 propeller aircraft (14 piston, 7 turboprop).

The owner listened to the session and approved its run on the fleet's private bucket (2026-11-04).

## Criteria, written before the run

A pilot: no criterion for "located" is set, and nothing here is tuned on its result.

1. **Known point first** (`tools/experiments/2026-11-04/known_point_site.py`). Each propeller or unknown-type pass whose
   closest approach is within 6 km of ground range during the recording is scored at the site on the recording's own
   clock: its own heard curve, brightness over ±60 s of the heard CPA, swept over the tone (60–300 Hz) and ±8 s, against
   its own null of 200 placements at wrong times. A pass is heard when it scores above every null draw. Reported: how
   many of the passes are heard, by ground-range bin (0–1, 1–2, 2–4, 4–6 km) and engine type, with each pass's z.
2. **Then `locate`** with its defaults (comparable, silence filter on) and the clock gate (the stated start ±1 s plus
   6 s), weather off: its verdict, its top candidate's and refined point's distance from the site (site-relative),
   whether its matched flights are among the heard passes, and its funnel.

Both run on one 4xlarge box from the private bucket, with the caches under `private/cache`; the per-flight table and
the records stay in `private/runs/`.

## Results

**Runs.** On the fleet's private bucket and one c7g.4xlarge per run, under the owner's per-file approval: run 3
(`private/runs/2026-11-04-seattle-home-pilot-3/`) built the spectrogram on the box (33,416 frames, none invalid, from
the three FLACs) and ran the known-point check, then stopped as `locate` began, on a run folder nothing had created;
`locate` follows in run 4. Runs 1 and 2 failed before any result, on a cache the box couldn't fill (the aircraft type
table) and on a private path my code resolved under the repo. All three are fixed.

### Known point

23 propeller or unknown-type passes came within 6 km of ground range during the recording: 14 piston, 6 turboprop and 3
of unknown type. Each was scored at the site on the recorder's clock against 200 placements of its own curve at wrong
times.

| Ground range | Passes | Heard |
|---|---|---|
| 0–1 km | 4 | 2 |
| 1–2 km | 2 | 0 |
| 2–4 km | 10 | 0 |
| 4–6 km | 7 | 0 |
| all | 23 | 2 |

- **Heard: 2 of 23, both within 1 km,** one piston and one turboprop, at z 7.4 and 8.1. Two other passes within 1 km
  were not heard.
- **Beyond 1 km, none of 19.** The criterion is strict (above every one of the 200 null draws), and below it the
  evidence is weak but not absent: the median pass scores 2.1 robust σ above its null, and 10 of the 21 unheard passes
  are above 2 σ. So the farther passes leave a weak trace, above the typical wrong-time placement, but none clears the
  best of the recording's own wrong-time placements.
- The 83 jets in the same 2.3 h were not scored: the check takes propeller and unknown types only.

The per-flight table (flight, time, range, height, z) stays in the private run folder: with public ADS-B it would place
the site.

### Locate

**Run 4** (`private/runs/2026-11-04-seattle-home-pilot-4/locate/`, 541 s for the box, $0.05): `locate` detected 10
flyovers, all 10 usable, on a recording with every frame valid. It then stopped before searching, `insufficient_evidence`
with `flight_data_missing_time`. The case's ADS-B cut was fetched on the day itself and ends at 20:13Z, while
`locate` required data for the whole UTC day, and that rule doesn't depend on the clock gate. There are no candidates,
no refined point and no funnel, so there is nothing to place and no measure of the site's distance yet.

The whole-day rule is there for a search with no stated start, whose clock can fall anywhere in the day. Under the clock
gate in the criteria above, every triple whose start is more than the stated 1 s plus `tol_s` from the stated start
is dropped, so only the recording's own window of flight data can reach a candidate. `locate` now asks for that
window when a start is stated: the stated start ± (its tolerance + `tol_s` + 300 s) across the recording, capped at the
whole-day bounds, so no case it passed before now fails. The cut covers the window. One thing changes slightly: the
comparable score's null draws wrong flights from the whole CPA table, which here lacks the day after 20:13Z. Run 5
reruns `locate` alone on the same case.

## Outcome

Pending.

## Files

`tools/experiments/2026-11-04/known_point_site.py`, `tools/data/session_spectrogram.py`, `bench/private.py`; the case
in `bench/cases.json` and its private file. Runs: under `$DOPPLERTRACK_DATA/private/runs/`, named in the results.
