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

Pending.

## Outcome

Pending.

## Files

`tools/experiments/2026-11-04/known_point_site.py`, `tools/data/session_spectrogram.py`, `bench/private.py`; the case
in `bench/cases.json` and its private file. Runs: under `$DOPPLERTRACK_DATA/private/runs/`, named in the results.
