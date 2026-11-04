# Propeller traffic during the Eclipse and A2O recordings (2026-11-04)

**Question.** Which of the Eclipse Soundscapes and A2O recordings have propeller passes close enough to use (PLAN 5.6 asks for at least two within about 6 km), counted over the hours each recording actually covers rather than the whole UTC day?

**Setup.** No change to the package.
- **`tools/data/site_traffic.py`** gained optional per-row columns: `elev_m`, and `start_utc` and `end_utc` for the recording.
  - Trace points count from 60 s before the start to the end, and slant range is measured from the site's elevation (Terrarium).
  - The output keeps `id`, `lat` and `lon` and passes any other input columns through. `derived/eclipse/site_traffic_2024-04-07.csv`, the earlier whole-day count with site elevation 0, has the old header.
- **Definition of a pass.** It is unchanged: one airborne segment of a prop or unknown-type trace whose 3-D distance to the site drops below 12 km (and, separately, 6 km), below 4 km MSL.
- **Flight data.** New this session:
  - 2024-04-08, for ESID 375 and 937, which run past midnight, and 740 and 710, which cross it by 59 s and 20 s;
  - 2025-04-22, 2025-09-30 and 2025-09-19, for the A2O recordings, each inside one UTC day.

  All four were fetched with `tools/data/fetch_day_tar.sh` (staged, size-checked against the release API, read-only). The four Eclipse boxes and three A2O boxes were cut with `extract_boxes.py`, which now writes fetch-day's coverage metadata into each file.
- **Townsville's two points.**
  - Its original file name, `BGB1_20250930T100000+1000_REC_-19.1967+146.7311.flac`, carries the recorder's GPS fix (Frontier Labs naming).
  - The user decided this fix is the working position, unverified, and that the published point is the obfuscated one.
  - Both points are counted here.
  - Duval's and Aroona's file names (`20250422T140000+1000_REC.flac`, `20250919T140000+1000_REC.flac`) carry no coordinates.

**Numbers.**

| Recording | Window (UTC) | Site elevation | Passes ≤12 km / ≤6 km | Nearest |
|---|---|---|---|---|
| ESID 375 | 04-07 01:39:34 → 04-08 02:30:54 | 283 m | 7 / 3 (04-08 adds 1 / 0: N63366 at 01:34, 9.0 km) | 1.8 km |
| ESID 937 | 04-07 05:40:21 → 04-08 06:31:41 | 103 m | 0 / 0 | 20.9 km |
| ESID 740 | 04-07 00:00:46 → 04-08 00:00:59 | 140 m | 7 / 3 | 1.1 km |
| ESID 710 | 04-07 00:00:06 → 04-08 00:00:20 | 155 m | 19 / 10 | 0.60 km |
| A2O Duval (91) | 2025-04-22 04:00–06:00 | 1,168 m | 0 / 0 | – |
| A2O Townsville (137), published point | 2025-09-30 00:00–02:00 | 5 m | 24 / 10 | 1.34 km |
| A2O Townsville (137), file-name fix | same | 33 m | 24 / 12 | 0.70 km |
| A2O Aroona (426) | 2025-09-19 04:00–06:00 | 194 m | 1 / 1 | 2.05 km |

- **Eclipse 04-07 versus the whole-day count.** The recording-window counts match it: 6/3, 0/0, 7/3, 19/10. Every pass falls inside the recordings, and measuring from the site's elevation changes no count.
- **No double counts at midnight.** The one 04-08 pass at ESID 375 is a separate flight, not a 04-07 pass counted twice.
- **The two Townsville points are 1.77 km apart.** They differ in the passes within 6 km (10 against 12) and in the nearest pass (1.34 against 0.70 km), not in the 12 km count.

**Outcome.**
- **Eclipse.** The 04-08 data adds one distant pass at ESID 375 and none elsewhere.
  - 375 (7/3), 740 (7/3) and 710 (19/10) meet PLAN 5.6's two passes within 6 km.
  - 937 stays a negative over its whole 25 h: no prop pass within 12 km, and the nearest at 20.9 km on 04-07 and 39 km on 04-08.
  - The flight data these recordings need is now on disk.
- **A2O.**
  - Townsville is busy, with 12 passes within 6 km of the fix in two hours: Townsville airport and RAAF Base Townsville are nearby.
  - Aroona has one close pass, short of the two PLAN asks for.
  - Duval has none in its two hours. As a stress case (PLAN 5.1) it is a site with no prop traffic, so `locate` must abstain there.
- **A question for the user: Townsville's published point is off by more than MANIFEST's bound.** It is 1.77 km from the recorder's own fix. MANIFEST quotes the A2O server's default obfuscation as at most about 270 m, with a 367 m allowance. If the file name's fix is right, that bound does not hold for this site, and maybe not for others with custom offsets. So the "coarse check of the 1 km verdict" PLAN 5.1 plans at A2O sites isn't a check at Townsville until the position is settled. A 1.77 km error in the truth is larger than the verdict it would test.
  - The fix is the working position, as decided, but unverified. It could be a GPS fix taken elsewhere, or a deployment-time position.
  - Duval and Aroona carry no fix, so their published points can't be checked this way. Their true error is unknown and may be as large.
- **Metadata.** Duval's site record names it Dry A while its notes JSON says Dry B. That is recorded, not resolved.

**Script:** `tools/data/site_traffic.py` (and `tools/data/fetch_day_tar.sh`, `tools/data/extract_boxes.py`). **Outputs:** `runs/2026-11-03-site-traffic/`: `sites_<day>.csv` (the windows), `traffic_<day>.csv` and logs, `command.sh`. Downloads and cuts: `runs/2026-11-04-adsb-<date>/`.
