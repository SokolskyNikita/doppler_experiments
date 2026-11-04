# The owner's home recorder: what an indoor phone hears (pilot, 2026-11-04)

<!-- index
question: What does the owner's indoor phone recorder hear of the propeller traffic around it, and what does locate make of a 2.3 h session?
outcome: Indoors the phone carries passes within about 1 km, as lines; locate's top is 480 m off the site at 200 m spacing in boxes to 12 km (fails the 300 m criterion), 294 m at 50 m
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

**The ear's reference**, from the owner, who listened to the session: the passes they could hear were easy to hear for
8–12 s each, the larger ones longest. They heard nothing beyond about 3–3.5 km of ground range, or beyond about 2 km for
turboprops. Below, piston and unknown-type passes are counted audible to the ear within 3.5 km, and turboprops within 2
km.

## The microphone

Three 120 s samples were recorded at 22:09–22:16Z, after the session, with the placement unchanged. They show what the
phone's two microphones contribute.

| Floor, lines removed (dBFS) | 20–40 Hz | 40–80 | 80–160 | 160–300 | 300–450 |
|---|---|---|---|---|---|
| bottom mic, raw | −66 | −64 | −70 | −78 | −87 |
| back mic, raw | −65 | −64 | −73 | −81 | −88 |
| voice-performance stereo, ch0 (bottom) | −77 | −77 | −85 | −94 | −100 |
| voice-performance stereo, ch1 (back) | −74 | −76 | −85 | −94 | −99 |

- **Gain:** voice-performance capture has 11–16 dB less digital gain, which is harmless at 24 bit.
- **Lines more than 10 dB above the floor:**
  - bottom mic: 26.4 and 467.8 Hz;
  - back mic: 64.5, 193.8 and 195.8 Hz;
  - voice-performance: none.
- **Coherence between the two mics:** 0.98 below 80 Hz, and 0.24–0.42 at 160–450 Hz.
  - Averaging the two mics lowers the 160–450 Hz floor by only 0.5 dB.
  - In that band the mics' own noise is incoherent, while a far-field aircraft is coherent at both. So coherence between
    the mics around a pass's predicted CPA is a third detector, beside the tonal and broadband ones, and the phone's
    self-noise cannot fake it.
  - **Planned for the first stereo session:** that coherence measurement, judged against the same ear reference.
- **Recommendation to the recorder project:** voice-performance stereo capture, with the back mic as the primary
  channel.

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

Both ran on one 4xlarge box from the private bucket, with the caches under `private/cache`; the per-flight table and
the records stay in `private/runs/`.

### Added before run 5: the broadband check

The owner's ear heard the passes within 2–3.5 km as a roar, while the tonal check heard 2 of them. The broadband check
asks whether the recording carries those passes as broadband energy without the harmonic lines the tonal score looks
for (`tools/experiments/2026-11-04/broadband_site.py`). It covers every airborne pass within 6 km of ground range,
jets included.

- **Spectrogram:** the unwhitened one, rebuilt from the FLACs on the stored spectrogram's frames. The running-median
  whitening removes part of a slow broadband rise.
- **Statistic:**
  - the band power over ±15 s of the predicted heard CPA, against the same 30 s power at every centre 30–150 s away on
    either side;
  - z = (centre − median) / (1.4826 MAD), with the rise in dB beside it;
  - bands: 40–450 Hz, 40–100, 100–200 and 200–450 Hz.
- **Marked:** a pass is marked when its 40–450 Hz z ≥ 3. The sub-bands are reported beside it, not used to mark.
- **Null:** the share of 200 random times that the same z marks. The traffic is dense, about one aircraft within 6 km
  every 80 s, so this is the share a pass would get marked with no pass chosen at all.
- **Crowding:** each pass carries how many other aircraft have a heard CPA within 30 s and within 150 s of its own.
- **Judged against the ear:**
  - A broadband detector that matches the ear marks the propeller passes inside the ear's range and not those beyond
    it, at well above the null's share.
  - The gap to close is the 9 passes the ear heard and the tonal check didn't: 1–3.5 km for pistons and unknown types,
    plus the two pistons within 1 km.
  - If broadband marks most of them, the indoor recording carries the roar and not the lines the detector assumes. The
    detector's first stage for this site would then have to be broadband: the problem is the signal's form, not
    sensitivity.
  - If broadband marks few of them, the recording carries little of either, and placement and gain are the problem.
- **Pictures, under `private/` only:** the two passes the tonal check heard, and the four nearest that the ear heard and
  it did not. Each shows the unwhitened spectrogram and the tonal scorer's view, with the predicted curve at the sweep's
  best tone overlaid, to show whether any lines exist at all.

## Results

**Runs.** On the fleet's private bucket and one c7g.4xlarge per run, under the owner's per-file approval: run 3
(`private/runs/2026-11-04-seattle-home-pilot-3/`) built the spectrogram on the box (33,416 frames, none invalid, from
the three FLACs) and ran the known-point check, then stopped as `locate` began, on a run folder nothing had created;
`locate` follows in run 4. Runs 1 and 2 failed before any result, on a cache the box couldn't fill (the aircraft type
table) and on a private path my code resolved under the repo. All three are fixed.

### Known point

23 propeller or unknown-type passes came within 6 km of ground range during the recording: 14 piston, 6 turboprop and 3
of unknown type. Each was scored at the site on the recorder's clock against 200 placements of its own curve at wrong
times. The bins carry the ear's lines, 2 km for turboprops and 3.5 km for the rest. Each cell is the passes heard by
the tonal check, out of the passes in that bin.

| Ground range | Piston | Unknown | Turboprop | All |
|---|---|---|---|---|
| 0–1 km | 1 / 3 | – | 1 / 1 | 2 / 4 |
| 1–2 km | 0 / 2 | – | – | 0 / 2 |
| 2–3.5 km | 0 / 3 | 0 / 2 | 0 / 5 | 0 / 10 |
| 3.5–6 km | 0 / 6 | 0 / 1 | – | 0 / 7 |
| all | 1 / 14 | 0 / 3 | 1 / 6 | 2 / 23 |

- **Against the ear: the tonal check heard 2 of the 11 passes the ear heard.** Those 11 are the pistons and unknown
  types within 3.5 km (10) and the turboprops within 2 km (1).
  - Heard: one piston and one turboprop, both within 1 km, at z 7.4 and 8.1.
  - Not heard: two pistons within 1 km, and all 7 pistons and unknown types at 1–3.5 km.
- **Beyond the ear's range, neither heard anything:** 12 passes (the 5 turboprops at 2–3.5 km and the 7 passes beyond
  3.5 km).
- **No turboprop gap in this session:** none passed at 1–2 km. The gap to close is the pistons and unknown types at
  1–3.5 km, plus the two pistons within 1 km.
- **Beyond 1 km, none of 19.** The criterion is strict (above every one of the 200 null draws), and below it the
  evidence is weak but not absent: the median pass scores 2.1 robust σ above its null, and 10 of the 21 unheard passes
  are above 2 σ. So the farther passes leave a weak trace, above the typical wrong-time placement, but none clears the
  best of the recording's own wrong-time placements.
- The 83 jets in the same 2.3 h were not scored: the check takes propeller and unknown types only.

The per-flight table (flight, time, range, height, z) stays in the private run folder: with public ADS-B it would place
the site.

### Broadband

Run 8 (`private/runs/2026-11-04-seattle-home-pilot-8/broadband/`, at the PM's fix of b8802ee's JSON writing, 361 s,
$0.03). Run 6 had failed at its last step.

**Baseline:** the 40–450 Hz z ≥ 3 marks 10 % of 200 random times, with a median z of −0.15. The traffic here is dense
enough that a tenth of all moments look like a pass.

| | Passes | Broadband marked | Tonal heard | Median z | Median rise |
|---|---|---|---|---|---|
| Ear-audible propeller passes | 11 | 3 | 2 | 1.03 | 0.8 dB |
| Ear-inaudible propeller passes | 12 | 0 | 0 | −0.14 | −0.2 dB |

By engine class and ground range, broadband-marked and tonal-heard out of passes:

| Ground range | Piston | Unknown | Turboprop | Jet |
|---|---|---|---|---|
| 0–1 km | 2 and 1 of 3 | – | 0 and 1 of 1 | 2 of 9 |
| 1–2 km | 0 and 0 of 2 | – | – | 6 of 56 |
| 2–3.5 km | 1 and 0 of 3 | 0 and 0 of 2 | 0 and 0 of 5 | 0 of 9 |
| 3.5–6 km | 0 and 0 of 6 | 0 and 0 of 1 | – | 0 of 5 |

The tonal check scores propeller passes only, so the jets have broadband counts alone.

**The three marked passes the ear heard:**
- Two are within 1 km. One is a pass the tonal check heard: z 3.2, a 5.2 dB rise. The other it missed: z 4.9, a 5.4 dB
  rise in every sub-band.
- The third, at 2–3.5 km, rises 8.7 dB in 40–100 Hz alone, with 100–450 Hz flat and a tonal z of −0.3. That reads as
  something low-frequency near the house, not the aircraft.
- At the null's 10 %, about one of the eleven would be marked by chance.

**Jets:** 8 of 79 marked, the null's share.

**The pictures** (`pass-1.png` to `pass-6.png`, private) show the near passes as harmonic lines, not as a roar:
- The tonal check's heard piston (0.5 km) has a full stack of Doppler-shifted harmonics from 100 to 450 Hz.
- The piston it missed at 0.8 km has clear lines too, with the predicted curve on one of them. It failed the check's
  strict rule (above every one of 200 null draws) at z 4.1.
- Beyond 1 km the lines are faint or absent, at 1.4 and 1.8 km.
- Sharp broadband transients, door or knock-like, appear in four of the six windows. Two fall inside the missed 0.8
  km pass's ±15 s, so its broadband mark may be partly theirs.

**What it settles:**
- The gap to the ear is not a missing harmonic line that a broadband detector would catch within the stored band.
  Where the recording carries a pass, within about 1 km, it carries lines.
- Beyond 1 km the stored 40–450 Hz holds a median broadband rise of 0.8 dB over the surrounding minutes of traffic,
  and faint or absent lines: too little for either statistic.

**What it leaves open.** The owner judged audibility live, in the room, not from the 1 kHz recording. So the
listener's reference includes sound above 450 Hz that the recorder never stored, and whether audibility at 1–3.5 km
rests on that band is untested. The gap is therefore placement, detection or the stored band, and the stored band is
the cheapest to test.

Two further limits on the statistic: the ±15 s window averages over an 8–12 s audible pass, and household transients
add to both the pass and its background.

**Answering it for this session:** the owner re-listens to the band-limited listening copy at the audible passes'
times. If they are still audible there, the content is in 40–450 Hz and the gap is detection. If not, the band above
450 Hz carries them.

**Next session's levers, in order:**
1. **The stored band.** This is the owner's privacy measure for a microphone in the home, not a pipeline setting, so
   the test's session exists only if the owner chooses a wider band in the recorder project. Three options were put to
   them: 2 kHz (flat to about 900 Hz, which covers Livermore's harmonics up to 868 Hz), 4 kHz (flat to about 1.8 kHz),
   and the full band. The owner chose the full band for the next sessions.
2. **Placement:** a window or outdoor placement, to lower the floor.
3. **Stereo:** stereo capture, for the coherence cue between the two mics, which household self-noise and single-mic
   transients can't fake.
4. **Algorithm:** the collective find, which sums evidence over many weak passes instead of needing two strong ones.

**Pre-registered test of the band, on the first session stored at 4 kHz:**
- The known-point check (tonal, its sweep widened to the band's harmonics) and the broadband check both run twice on
  the same passes and the same ear reference: once on the stored 40–450 Hz, once on 40–1800 Hz. A session stored
  narrower than 1.8 kHz uses its own passband edge, stated with the result.
- **The band is the lever if** the wide band marks at least half of the ear-audible propeller passes beyond 1 km, while
  40–450 Hz marks no more of them than its null share.
- **The band is not the lever if** the wide band marks no more of them than its null share.
- Anything between is reported as it falls.

**Ready before the session, so the test needs no new code** (2026-11-05):
- **Wide spectrogram:** `tools/data/session_spectrogram.py --fmax HZ` builds it with the package's STFT. It keeps the
  2.048 s Hann window, the 0.25 s hop and the 0.49 Hz bins, decodes at 4 kHz up to a 1.8 kHz edge (in 1 kHz steps above
  it), and whitens with the same 600 s running median.
- **Both checks take `--fmax` and `--spectrogram`:**
  - The tonal check scores floor(fmax / 300) harmonics, every one of which stays in band for any 60–300 Hz tone: 6 at
    1.8 kHz, 1 at 450 Hz.
  - The broadband check marks on 40 Hz to fmax and adds 450–900 and 900–fmax to its sub-bands.
- **Case builder:** `tools/data/home_session_case.py SESSION_ID --traces PATH` writes the session's private case (a
  `spectrogram_wide` at the band's edge when the session stores more than 450 Hz) and its public entry. The box is the
  series' off-node 4 km square.
- **Launch:** the launch script's `--session ID bandtest` runs both checks on both bands. Like every launch, it ships
  only the files the owner names.

### Locate

**Run 4: the pipeline refused, and nothing was searched.** Run 4 (`private/runs/2026-11-04-seattle-home-pilot-4/locate/`, 541 s for the box, $0.05): `locate` detected 10
flyovers, all 10 usable, on a recording with every frame valid. It then stopped before searching, `insufficient_evidence`
with `flight_data_missing_time`. The case's ADS-B cut was fetched on the day itself and ends at 20:13Z, while
`locate` required data for the whole UTC day, and that rule doesn't depend on the clock gate. There are no candidates,
no refined point and no funnel, so there is nothing to place and no measure of the site's distance yet.

The whole-day rule is there for a search with no stated start, whose clock can fall anywhere in the day. Under the clock
gate in the criteria above, every triple whose start is more than the stated 1 s plus `tol_s` from the stated start
is dropped, so only the recording's own window of flight data can reach a candidate. `locate` now asks for that
window when a start is stated: the stated start ± (its tolerance + `tol_s` + 300 s) across the recording, capped at the
whole-day bounds, so no case it passed before now fails. The cut covers the window. One thing changes slightly: the
comparable score's null draws wrong flights from the whole CPA table, which here lacks the day after 20:13Z. 

**Run 5: the silence filter removed the true pair.** Run 5 (`private/runs/2026-11-04-seattle-home-pilot-5/`, at 34fab9e
with the fix, 661 s, $0.06) searched and ended `insufficient_evidence` with `no_surviving_candidate`. The funnel:

| Stage | Count |
|---|---|
| CPA records | 129,069 |
| After the speed and distance gates | 2,315 (event 1), 2,330 (event 2) |
| Time join | 44 |
| Silence filter | 0 |
| Scored | 0 |

The clock gate acts on scored triples, so it never ran. The comparable rule searched one event pair.

**The 44 time-join triples (read afterwards, as a diagnosis):**
- They are a single flight pair, and both of its flights are the two passes the known-point check heard: the true pair.
- They sit at 44 grid points from 200 m to several km from the site, median 1.4 km, 6 of them within 500 m. The grid
  node nearest the site is not among them.
- The filter drops a triple whenever another flight's CPA within 6 km of the grid point falls between the two events'
  CPAs, more than 40 s from each. The pair's two events are tens of minutes apart, and about 105 aircraft passed within
  6 km in the 2.3 h, so at this site some flight always falls in between.

The filter took S4's risk (PLAN section 4): it assumes every flight within 6 km is heard. Here the indoor phone heard
2 of the 23 propeller passes, and none of the 83 jets were scored. The filter was made the default on one recording,
Oyster Bay, and is judged again on the next positive; this is a recording where it is certain to fire.

**Run 7: with the filter off, the top candidate is the site.** Run 7 (`private/runs/2026-11-04-seattle-home-pilot-7/
locate-silence-off/`, at 34d9743, 361 s, $0.03) ended `ambiguous` with `winner_only_refined` and `silence_filter_off`.
Those reasons come by construction: step A refines only the winner, and the filter was off.

The funnel:

| Stage | Count |
|---|---|
| CPA records | 129,069 |
| After the speed and distance gates | 2,315 / 2,330 |
| Time join | 6 |
| Clock gate | 6 |
| Scored | 6 |

This time the comparable rule chose a different event pair, and the time join kept 6 triples. All 6 are the same
flight pair: one of the two passes the known-point check heard (about 0.5 km), and the 0.8 km piston it missed at z
4.1 (pass picture 4).

**The scored triples' surface (from the site-relative sidecar):**

| Grid node | Distance from the site | Score |
|---|---|---|
| top | 0 m | 5.95 |
| the three next | 200 m each | 1.97, 1.79, 1.66 |
| | 283 m | 0.92 |
| | 400 m | 0.81 |

- **Clock:** the winning pair's clock puts the recording's start 0.31 s from the stated one, inside its 1 s.
- **Refine:** the 50 m refine over ±600 m, with 8 more flyovers, stayed on the winning node. Those flyovers were
  assigned 7 distinct flights, all among the 23 propeller passes within 6 km.
- **Margin:** the winning node scores 3 times the best of its neighbours.
- **What the 0.0 means:** the box was centred on the site, so the site is a grid node by construction. The 0.0 says the
  top node is the site's own node and the refine's peak is within its 50 m step, so within about 25 m. It doesn't say
  the error is zero. The refine's own surface isn't saved, so its margin can't be read.
- **No verdict yet:** the top candidate was judged among 6 triples of one flight pair. A verdict waits for Phase 4's
  null of the maximum.
- **The silence filter:** its rule should depend on the traffic. It would be off where the expected count of other
  flights within 6 km between two events exceeds about one, a number the case's own flight data gives before any
  search, and on, as already judged, at quiet sites.
- **Privacy:** run 7's `run.log` and `summary.txt` (under `private/` only) carry the refined point in absolute
  coordinates, from `locate`'s summary line. A private run's log and summary now give it only as an offset from the
  site.

**Run 6** (at b8802ee) ran `locate` and then failed at the end of the broadband check, on a numpy integer in its JSON.
The PM's fix reruns the check in `broadband` mode.

**Run 9: off the grid, the 4 km box fails the criterion.** Run 9 (`private/runs/2026-11-04-seattle-home-pilot-9/
locate-silence-off-box4km/`) is the series' 4 km box, with the site 73 m east and 131 m north of its centre, off the
grid. It ended `ambiguous` (`winner_only_refined`, `silence_filter_off`).

The funnel:

| Stage | Count |
|---|---|
| CPA records | 134,641 |
| Time join | 36 |
| Clock gate | 20 |
| Scored | 20 |

The comparable rule chose another event pair: the same 0.8 km piston with the 1.8 km piston of pass picture 6. Both
are real passes near the site, and neither cleared the tonal check's strict rule.

- **Top candidate:** 482 m from the site, score 5.13. The grid node nearest the site, 100 m away, scores 3.13 for this
  pair.
- **Clock:** the pair's clock puts the start 0.49 s from the stated one, well inside the gate. The −6.0 s is the
  residual shift of the curve against the events, at the edge of its ±6 s sweep, so the winning node needed the
  largest time slip allowed. At the site in run 7 it was −1.0 s.
- **Refine:** 294 m from the site, score 35.1 with 8 more flyovers. Its ±600 m window covered the site, but it inherits
  the winning triple's clock.
- **Verdict:** by the criterion written first (rank 1 within 300 m), the 4 km size fails, and the judged series stops
  here.

The scored surface (this pair only):

| Node | Distance from the site | Score |
|---|---|---|
| top | 482 m | 5.13 |
| second | 141 m | 4.88 |
| | 294 m | 4.79 |
| | 677 m | 4.52 |
| | 331 m | 4.29 |
| | 472 m | 4.15 |
| nearest the site | 100 m | 3.13 |

This pair's surface is broad: four nodes from 141 to 677 m are within 12 % of the top.

**What moved the answer: sampling, not the clock.** The comparable rule searches every pair of the top 5 events and
keeps the pair whose top node scores highest.
- In run 7, run 7's pair scored 5.95 on the site's own node and about 2 at the nodes 200 m away: a peak narrower than
  the grid.
- In run 9, that pair can't have scored above 5.13 at any node, or it would have won. With the site 150 m off the grid,
  its peak fell between nodes, and a pair with a broader, displaced surface won instead.
- So the true point doesn't lose on its clock. At the site, run 7's pair has the clock 0.31 s from the stated start
  and a 1 s residual shift. It loses on the 200 m grid's sampling of a sharp peak.
- So run 7's 0 m was partly the node artefact. The record keeps both runs.

**Run 10, the direct test:** the same off-node 4 km box at 50 m spacing (`--box 4 --spacing 50`). If run 7's pair wins
again with the top within 300 m of the site, the failure is sampling. If not, it is the method.

The method's fix would choose among pairs after each pair's top is refined, not on the coarse grid. That is
recorded here, not built.

**Run 12: the off-node 4 km box at 50 m spacing.** (`private/runs/2026-11-04-seattle-home-pilot-12/
locate-silence-off-box4km-sp50m/`, 2,003,797 CPA records, 334 triples scored.) The criterion was written for the case's
200 m grid, so this is the diagnosis, not the judged series.

- **Top candidate:** 294 m from the site, score 6.46, inside the 300 m line by 6 m.
- **Clock:** the residual shift is +0.5 s, no longer at the sweep's edge.
- **Refine:** 241 m from the site.
- **Margin:** the best node beyond 300 m is 387 m from the site at 5.96, 8 % below the top and part of the same mode.
  The best node within 150 m of the site scores 4.75.
- **Pair:** the winner is still the 1.8 and 0.8 km pistons (events 4 and 3), not run 7's pair.

So the 200 m grid mismeasured this pair's peak by about 200 m and forced the −6 s slip. At 50 m the pair's own mode is
about 250–300 m from the site. The sharper on-site peak of run 7's pair doesn't win at 50 m either, so run 7's 0 m
was mostly the node coinciding with the site. The working error of this session's best pair is a few hundred metres.

**8 and 12 km (runs 10 and 11), reported, not judged.** They ran at 200 m, as the owner asked, outside the
pre-registered rule, with the same off-node placement:

| Box | Run | CPA records | Top candidate from the site | Score | Residual shift | Refined from the site |
|---|---|---|---|---|---|---|
| 4 km | 9 | 134,641 | 482 m | 5.13 | −6.0 s | 294 m |
| 8 km | 10 | 499,475 | 480 m | 5.03 | −6.0 s | 238 m |
| 12 km | 11 | 1,091,510 | 477 m | 4.64 | −6.0 s | 273 m |

- **Same answer at every size:** the same event pair (the 1.8 and 0.8 km pistons) wins at the same node.
- **No better candidate anywhere:** in each box that node beat the best of all ten event-pair searches, so no
  candidate anywhere in a box of up to 12 km (about 3,600 nodes) scored higher.
- **Score drift:** the top score falls with the box, because the comparable z's null is drawn from a CPA table that
  grows with the grid. Scores at different box sizes are not comparable.
- **What stops a pass:** at 200 m, the grid's sampling of the winning pair's peak (run 12: at 50 m the same pair's top
  is 294 m from the site). No wrong location wins across nine times the area.
- **20 km:** the next size, once adsb.lol's 2026-11-04 archive is out. It needs a `fetch-day --keep-jets` cut of a wide
  public Puget Sound box and a private case pointing at it.

### The box series: criterion, written before any run

The owner asked for the true limit once a box under 4 km succeeds. The series runs `locate` with the filter off on
the same case and the same flight data, at boxes of 4, 8, 12 and then 20 km.

- **Placement:** each box is a square around the site, its centre 73 m west and 131 m south of it, so the site sits 73 m
  east and 131 m north of the centre, off every 200 m node. The 4 km box is rerun this way, which tests the run 7
  artefact directly.
- **The site counts as the top mode when** the top-ranked candidate is within 300 m of the site (a grid diagonal plus
  the offset).
- **Reported at each size:**
  - the top candidate's distance from the site, and the refined point's;
  - the margin from the top node to the best node outside 300 m;
  - the best candidate at least 1 km from the top: its distance from the site, and its score as a share of the top's.
- **Stop rule:** the series stops at the first size where the site is not the top mode. Sizes beyond it are moot even
  if they ran.
- **Flight data:** the case's cut. Its declared envelope (±14 km) is a rectangle inside a 20 km circle. The adsbfetch
  record of the query names the public metro box (47.45–47.80 N, 122.60–122.05 W), and the cut holds the archive's
  count of propeller aircraft in every ring of it during the recording's hours:

  | Ring around the site | 11-01 (archive) | 11-02 (archive) | 11-04 (case cut) |
  |---|---|---|---|
  | within 6 km | 27 | 19 | 23 |
  | within 14 km | 46 | 27 | 45 |
  | 14–18 km | 11 | 1 | 17 |
  | beyond 18 km | 14 | 12 | 10 |

  So the series declares the metro box as the envelope (`extraction_box`). The 4, 8 and 12 km boxes plus `locate`'s
  12 km reach fit inside it; the 12 km box has 99 m to spare. The 20 km box needs a wider cut: adsb.lol's archive for
  2026-11-04, which appears after the day ends, cut wide with `fetch-day`.
- **Mechanism:** the box comes from the runner's `box_m` override, built from the site file the owner approved, so no
  new private file is shipped. The launch script's `locate --silence off --box KM` runs each size.

## Outcome

So far, from runs 4, 5 and 7:
- The tonal check hears 2 of the 11 passes the owner's ear heard, both within 1 km. The rest of the ear's range, 1–3.5
  km, gets nothing.
- Run 4: `locate` refused before searching. The flight data stopped short of the whole day, a defect in its coverage
  rule, now fixed.
- Run 5: `locate`'s time join found the true pair, the two heard passes, and then the silence filter removed it. The
  traffic here, about one aircraft within 6 km every 80 s, makes that certain for events tens of minutes apart.

- Run 7, with the filter off: the top candidate is the site's own grid node, with the clock 0.31 s from the stated
  start. The refine stayed there. The site was a node by construction, so the box series reruns 4 km with the site
  off the grid.
- Run 8, the broadband check: it marks 3 of the 11 ear-audible passes against a null of 10 %, two of them within 1 km,
  and none of the 12 beyond the ear's range.
  - Where the indoor phone carries a pass, it carries harmonic lines. Beyond about 1 km it carries little in 40–450 Hz
    of either kind.
  - The owner judged audibility live, so their reference includes sound above 450 Hz that the recorder never
    stored. The gap is placement, detection or the stored band, and the band is the cheapest to test: store 4 kHz
    next session, rerun the known-point and broadband checks on both bands (pre-registered above), and meanwhile
    the owner re-listens to the band-limited copy.

- Run 9, the box series' first size: 4 km with the site off the grid fails the criterion. Its top is 482 m away, on
  a different event pair with a broader surface. Run 7's sharp pair can't score above it on a 200 m grid that misses
  its peak. So the judged series stops at 4 km.
- Runs 10 and 11 (8 and 12 km, reported, not judged): the same node, 480 and 477 m from the site, wins every box.
  No location in a 12 km box scores higher.
- Run 12 (4 km at 50 m spacing): the same pair's top is 294 m from the site, inside the 300 m line, with the clock's
  residual shift back to +0.5 s. The 200 m grid had displaced it by about 200 m.
  - This session's best pair places the site to a few hundred metres, and nothing in a 12 km box beats it.
  - 20 km waits for the archive.

## Files

`tools/experiments/2026-11-04/known_point_site.py`, `tools/experiments/2026-11-04/broadband_site.py`,
`tools/experiments/2026-11-04/seattle_pilot_launch.sh`, `tools/data/session_spectrogram.py`, `bench/private.py`; the case
in `bench/cases.json` and its private file. Runs: under `$DOPPLERTRACK_DATA/private/runs/`, named in the results.
