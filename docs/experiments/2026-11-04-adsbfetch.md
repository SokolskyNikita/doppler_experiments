# adsbfetch as a flight-data source (2026-11-04)

<!-- index
question: Is the user's adsbfetch CLI (free tar1090 mirrors) a better flight-data source than our adsb.lol tars?
outcome: Not as a replacement: denser tracks at CPA (gap ~10 s against ~20 s, 2–3× points), Oyster Bay unchanged, but the eagle cam flips to a wrong pair 14 km off on the mirrors' trajectories. 13 bugs found, 11 fixed
-->

**Question.** The user's `adsbfetch` CLI (/Users/nsokolsky/projects2/adsb_data_fetcher) reads tar1090 globe history from four networks: adsbx, which needs a session cookie the user supplies by hand, and three free mirrors, adsbfi, airplanes.live and adsb.lol. Three questions:
1. Does it work?
2. Is its data better than our adsb.lol day-tar cuts where we need it?
3. Does it change search results?

**Criterion**, fixed by the PM before the runs. The source is worth adopting if:
- on the true flights, the mirror union has at least as many points within ±60 s of CPA as our cut, and no larger gap there;
- and the saved-fit results are the same or better.

A fuller day-box count alone doesn't decide.

**Rules kept.**
- The fetcher's checkout was read and run, never edited.
- `.env` and the captured curl files were never opened.
- No adsbx data was fetched, with one exception: the fixed smoke script used the `.env` session for one request (part 1).
- Requests were serial, but **not all 2 s apart** (corrected later the same day). The CLI's throttle holds within one process only, and the scripts started one `trace` process per aircraft and source, so consecutive traces went out as fast as a process starts. Replays were one process each and kept the 2 s pace.
  - This morning's runs have no request log. The windowed traces in `wtraces2/` (914 files, 03:53–04:04) imply about 0.7 s per request.
  - In the afternoon's adsbx refetch, which has per-call manifests, 562 of 651 network requests came under 2 s apart (median 0.61 s).
  - The free-mirror refetch was stopped at 14:19Z, after 206 of its first 409 network requests came under 2 s, and resumed with 2 s after every call.
- Outputs went to run folders. While bug 13 was open, every source got its own `--cache-dir`; with 0.3.0 that's no longer needed.

## 1. Does it work

**Tested twice.**
- **0.2.0, as found at about 03:20.** The smoke script passes 10/10. 70 unit tests pass. `coverage` runs. Replay of the NY box at 2026-09-08 20:53Z returns 128 aircraft on adsbfi and 157 on airplanes.live. a1dfeb's trace that day has 1,076 points on adsbfi and 1,723 on airplanes.live.
- **The fixed checkout,** still labelled 0.2.0 and with no git history; sha256 of its .py files is 0a86aa97b871. Smoke passes 10/10 and now fetches all four networks. 127 unit tests pass.

**Bugs reported, and their state on the fixed checkout:**

| # | Bug | Command that showed it | Fixed? |
|---|---|---|---|
| 1 | `trace --days` ignored without `--end` | `trace --source adsbfi --icao a1dfeb --start 2026-09-07 --days 2` fetched one day | yes, two days |
| 2 | trace times truncated to whole seconds (1,069 of 1,076 offsets fractional) | `trace … a1dfeb … 2026-09-08` | yes: ms `ts` and `ts_epoch` |
| 3 | geometric altitude, vertical rate and position source dropped; `alt_baro` wrong when flag 8 set | same | yes: `alt_geom`, `baro_rate`/`geom_rate`, `source_type`, `alt_is_geom`; flag 8 gives `alt_baro` null |
| 4 | a missing chunk or day exits 0 with 0 rows | `replay --source adsblol` on the NY box at 20:53Z | yes, exit 3 |
| 5 | adsb.lol's "since 2023-01-27" overstates it: it has holes | adsblol 404 on 2026-09-08 and 2026-05-13..17, though our adsb.lol GitHub tar has those flights; it serves 2024-12-28 | yes, `coverage` notes the holes |
| 6 | replay's progress line counts positions as "aircraft" | `replay --for 10m` | yes |
| 7 | `dates` help said "oldest last"; README duplicated and contradicted | `dates --help` | yes |
| 8 | `trace` with no `--start` silently fetches the first day on record | `trace --icao a1dfeb` | yes, now refuses |
| 9 | docs pointed at a missing script and a missing procedure; ruff absent from the venv | – | yes |
| 10 | smoke fetched one network only | `scripts/smoke.py` | yes; but see below |
| 11 | `--for` takes one unit only | `replay … --for 23h59m`, `--for 1h30m` | yes, in 0.3.0: `--for 1h30m` gives 181 slices, 20:53–22:23Z |
| 12 | non-ICAO (`~`, TIS-B) addresses fetched the wrong file (tilde stripped) | 54 `~` hexes all "nothing found" | yes, fixed during the run |
| 13 | **cache keyed on the URL path alone**: every mirror got whichever mirror's copy was cached first | `trace --source airplaneslive --icao a2baea --start 2024-12-28 --end 2024-12-28` gave 283 points (adsbfi's) against 326 with an isolated cache; 328 of 381 windowed pairs byte-identical | yes, in 0.3.0: the key is host + path; adsbfi and airplanes.live into one cache folder give 283 and 326 rows, two entries |

**Final checkout,** checked after both rounds: 0.3.0+9e61db56, sha256 of its .py files 508300c486c1. 249 unit tests pass. Smoke passes 9 checks, and adsbx is skipped: it now sends no session unless `--session` is passed. Every reported bug is fixed.
- **The per-source cache folders are no longer needed.** One cache folder keeps the mirrors apart.
- **The cache migration left nothing else missing for us.** The converter and the comparison read the CLI's own jsonl rows, not its cache. The only casualty was the 0.2.0-era bodies behind the first part-2 run, already re-fetched into `traces2/`.

**New issues found on the intermediate fixed checkout** (0a86aa97b871), all resolved in 0.3.0:
- **smoke.py used the session.** It loaded `.env` and made one adsbx request with the user's session whenever a cookie was present, while its docstring said it needed no cookie. My first re-verification run did that once. Fixed in 0.3.0: the session is opt-in.
- **It changed while being tested.** 34 of my requests hit half-edited code:
  - 22 × `TypeError: _client() takes from 3 to 5 positional arguments but 7 were given`;
  - 8 × `'Client' object has no attribute '_note'`;
  - 2 × `'Store' object has no attribute 'put_body'`;
  - 1 × `NameError` in trace.py;
  - 1 × `IndentationError`, which still failed on retry.

  All but the last were re-fetched cleanly. Its version string never changed.
- **The cache was migrated.** The new cache code rewrote the shared `~/.cache/adsbfetch` (1,219 files became 441), so bodies fetched before it can't be reread. Part 2 was re-fetched for that reason.

**Converter.** `tools/data/adsbfetch_to_npz.py` writes our trace npz.
- **Reading the rows.** It reads the fixed CLI's rows directly. On a1dfeb's 1,076 points those rows give a trace identical to our `parse_trace_bytes` on the raw body: times, positions, heights, sources, flags and ground marker. Rows in the old 0.2.0 schema go through the cached body instead.
- **Merging mirrors** keeps every point, with a 50 ms dedupe.
- **Metadata.** It writes fetch-day's extraction metadata, with the replay box as the envelope and `coverage_basis` naming how the aircraft were chosen. Empty files count as empty; unreadable bodies count as malformed.

## 2. Is the data better where we need it

**True flights** of the two development recordings and the 8 Livermore passes with the widest KML gaps across CPA. Within ±60 s of CPA:

| Flight | Reference | Ref. points / largest gap | Mirror union points / largest gap | Union position against reference, median / p95 |
|---|---|---|---|---|
| a1dfeb (Oyster Bay) | our cut | 7 / 20.0 s | 19 / 9.9 s | 4.0 / 7.8 m |
| ace391 (Oyster Bay) | our cut | 21 / 19.8 s | 42 / 9.8 s | 4.0 / 15.3 m |
| a2baea (eagle cam) | our cut | 7 / 20.0 s | 17 / 18.2 s | 2.8 / 12.0 m |
| a336e4 (eagle cam) | our cut | 11 / 18.0 s | 32 / 11.1 s | 3.2 / 10.1 m |
| 8 Livermore passes | author's KML | 6–21 / 19.5–20.0 s | 18–52 / 8.6–10.0 s | 3.1–14.8 / 8–42 m |

- **airplanes.live alone** gives most of the gain, with points about every 10 s where our cut and the KML have one every 20 s.
- **adsbfi** has a 374 s hole at a2baea's CPA.
- **adsb.lol's web mirror** serves the eagle-cam day but not the Oyster Bay or Livermore days.
- **The union closes the KML's gaps at CPA** on all 8 Livermore passes, to about 10 s.

**Box-day,** NY on 2026-09-08 and SWFL on 2024-12-28, unique propeller and unknown-type aircraft from the 48 replay chunks:

| Site | adsbfi | airplanes.live | adsb.lol | Union | Our cut |
|---|---|---|---|---|---|
| NY | 988 | 1,019 | – (the day is a hole) | 1,035 | 1,016 traces |
| SWFL | 317 | 559 | 549 | 560 | 557 traces |

- **Points** on the same windowed aircraft: the union has 1.79–1.80× our cut's points (NY: 278 aircraft, 1,097,393 against 612,570; SWFL: 155, 225,408 against 125,399).
- **Aircraft only in the union:** 21 in NY and 1 in SWFL, against none only in the cut.

## 3. Does it change results

**Setup.**
- **Windowed set.** Every propeller or unknown-type aircraft seen in the box's replay slices during each recording ±30 min: 300 in NY and 157 in SWFL. Their day traces come from adsbfi and airplanes.live.
- **Completeness check.** Every flight in our cut heard within 12 km during the recording is in the windowed set: 9 of 9 for Oyster Bay, 31 of 31 for the eagle cam. The eagle cam's union adds two our cut lacks: a06b8a at 11.2 km and a6bc8f at 7.4 km.
- **The runs** use today's runner (`bench.runner.bench_case`) on the cases as committed, with only `flight_data.traces` and a private `search.cpa_cache` changed in memory.

| Case, traces | True pair rank | Flight pairs | Refined error | Margin |
|---|---|---|---|---|
| oyster-bay, our cut | 1 | 328 | 43.3 m | 4.9 % |
| oyster-bay, mirror union | 1 | 55 | 43.3 m | 40.9 % |
| eagle-cam, our cut | 1 | 607 | 877 m | 2.5 % |
| eagle-cam, our cut restricted to the window | 1 | – | 877 m | 2.5 % |
| eagle-cam, mirror union | 3 | 174 | 14,087 m | 5.7 % (wrong pair) |
| eagle-cam, airplanes.live only | 2 | – | 14,097 m | 2.9 % (wrong pair) |
| eagle-cam, adsbfi only | 11 | – | 54,701 m | 0.8 % (wrong pair) |

- **Oyster Bay is unchanged.** Its larger margin comes from having fewer competitors (55 flight pairs against 328), not from better data.
- **Windowing doesn't matter on the eagle cam.** The window-restricted cut reproduces the baseline exactly, scores 10.297 and 10.042.
- **The eagle cam's flip comes from the trajectories themselves.**
  - With our cut, the true pair scores 10.30 and the runner-up 10.04: a0e90b+a25807 at 26.731, −81.987.
  - On airplanes.live's tracks the true pair drops to 10.16 and that same pair rises to 10.46.
  - On the union, 9.85 against 10.44.
  - On adsbfi, the true flight a2baea has a 374 s hole at CPA, and the true pair falls to rank 11.
- **Merging two networks adds jitter.** The speed implied by consecutive positions against the reported ground speed, for a2baea, a336e4, a0e90b and a25807:

  | Track | Median | p95 |
  |---|---|---|
  | Our cut | 0.5–0.8 m/s | 2.9–4.4 m/s |
  | adsbfi alone | 0.6 m/s | 3.1–4.8 m/s |
  | airplanes.live alone | 0.5–1.0 m/s | 2.7–7.9 m/s |
  | Union | 0.9–1.2 m/s | 7.9–10.7 m/s |

  Their positions for nearly the same instant differ by tens of metres. That jitter isn't the whole story, though, since airplanes.live alone also flips the case.

**Outcome: not adopted as a replacement, by the criterion as fixed.**
- **The first half passes.** On all four true flights the union has 2–3× the points within ±60 s of CPA and a smaller largest gap: about 10 s against about 20 s.
- **The second half fails.** Oyster Bay is the same, but the eagle cam goes from rank 1 at 877 m to a wrong pair 14 km off.
- **What the eagle-cam result means.** The case's 2.5 % margin is smaller than the change a different but equally plausible trajectory makes to the scores: about ±4 %. Its rank depends on which network's track is used. That says more about the fragility of the eagle-cam result (a pass known to fall fastest 16.6 s after its geometric CPA; timing-conventions record) than about which network is right. Nothing here shows our cut is closer to the truth there.
- **Where the tool helps now.**
  - Denser trajectories at CPA for model-error and timing work (Phase 2 items 1 and 2), as a sensitivity alongside our cut. The Livermore gaps close to about 10 s.
  - Flights our cut lacks: 21 in NY and 2 near the eagle cam.
- **What a union would need first.** A merge that keeps one network per stretch and fills only that network's gaps, not an interleave, so it doesn't add jitter. Bug 13 is fixed in 0.3.0.
- **Limits.**
  - Free mirrors start at 2023-01-27, and adsb.lol's mirror has holes.
  - A box-day of per-aircraft traces takes hours at 2 s per request.
  - Fetched bodies live outside `raw/` and the manifest.
  - The mirrors' terms of use weren't checked; adsb.lol's are ODbL.
- **adsbx comparison: ready to run.** It needs the user's fresh token in the fetcher's `.env`. It would repeat part 2's true-flight table and part 3's two cases with `--source adsbx`: about 15 trace requests and about 450 for the windowed sets.

## 4. The refetch on 0.3.1, and adsbx

**Question.** Does anything above change when every byte is fetched again with the audited release, and what does adsbx add?

**Setup.**
- **Version.** A copy of the frozen checkout, `$DOPPLERTRACK_CACHE/adsbfetch-snapshot-0.3.1+ae2519c6`, copied without `.env` and identical to the checkout by `diff -rq`. `--version` reports 0.3.1+ae2519c6, and its code fingerprint (sha256 of the sorted per-file sha256 list of its .py files) is 4354ce361d69, the same at the start and end of both runs.
  - Its 348 unit tests pass from the copy. The 7 `test_docs` tests launch `ROOT/.venv/bin/adsbfetch`, so the copy carries one launcher there: the checkout's venv python on the copy's code.
  - Every manifest row names that build.
- **Fetch.** Into empty cache roots, with a `--manifest` per call and 2 s after every call. The CLI paces only within one process; the first 14 minutes of the free run weren't paced between calls, then it was stopped and resumed on its own cache.
  - Free mirrors: the box-day replays on adsbfi, airplanes.live and adsb.lol; the windows rebuilt from them; every windowed hex's day trace on each mirror that has the day (adsb.lol has 2024-12-28 but not 2026-09-08); and the 12 true flights on all three.
    - 1,113 calls: 1,458 network requests (1,352 ok, 106 absent, 0 failed) and 280 from cache, from 14:05:43 to 15:19:34Z.
    - The replays include 343 requests to `globe.adsbexchange.com/db-current/*.js`, the aircraft-type tables `--details` loads. They are keyless and sent no session.
  - adsbx: the 12 true flights, both box-day replays and the windowed traces (adsbx's own window plus 3 NY hexes from the free one). The session comes from the fetcher checkout's `.env`, read by the CLI from its working directory and written nowhere here.
    - 489 calls: 652 network requests (651 ok, 1 absent) and 70 from cache, 14:07:50–14:18:33Z.
    - 562 of 651 requests came under 2 s apart (median 0.61 s). It was left as is.
- **Measures.** Defined in `adsbfetch_refetch_summary.py`.
  - Window aircraft: propeller and unknown-type hexes seen in the source's replay during the recording ±30 min; for our cut, its traces of those types with a point in the box then.
  - Trace points: every point of those aircraft's day traces inside the case box. Our cut is a box cut, so the mirrors' traces are clipped to the same box.
  - CPA: the two true flights' points within ±60 s of CPA, summed, and the larger of their largest gaps.
  - Only here: traced window aircraft with no trace at all in our cut. Only in cut: the cut's window aircraft the source didn't see in the box during the window at all.
  - Type disagrees: aircraft the cut has as unknown type that the source types as a jet, so they fall out of its propeller window. Most of the cut's extra window aircraft are these.
- **The unions.** Free: adsbfi + airplanes.live, as this morning. Free + adsb.lol: SWFL only. Four-mirror: all of them.

**Numbers.** Per case, each source against our adsb.lol tar cut and against this morning's fetch of the same thing.

NY, 2026-09-08 (our cut: 298 window aircraft, 409,701 box points, 28 points at CPA, largest gap 20.0 s):

| Source | Window aircraft | vs cut | vs morning | Box points | vs cut | vs morning | CPA points | vs cut | Largest gap | Only here / only in cut (type disagrees) |
|---|---|---|---|---|---|---|---|---|---|---|
| adsbfi | 290 | −2.7 % | 0 % | 310,482 | −24.2 % | 0 % | 27 | −3.6 % | 19.9 s | 15 / 4 (21) |
| airplanes.live | 295 | −1.0 % | 0 % | 472,190 | +15.3 % | 0 % | 35 | +25.0 % | 10.0 s | 17 / 2 (21) |
| adsbx | 312 | +4.7 % | – | 420,156 | +2.6 % | – | 24 | −14.3 % | 20.0 s | 30 / 2 (21) |
| free union | 300 | +0.7 % | 0 % | 707,393 | +72.7 % | 0 % | 61 | +117.9 % | 9.9 s | 22 / 2 (21) |
| four-mirror union | 315 | +5.7 % | – | 993,102 | +142.4 % | – | 81 | +189.3 % | 9.9 s | 32 / 1 (21) |

adsb.lol's web mirror has no 2026-09-08.

SWFL, 2024-12-28 (our cut: 157 window aircraft, 45,780 box points, 18 points at CPA, largest gap 20.0 s):

| Source | Window aircraft | vs cut | vs morning | Box points | vs cut | vs morning | CPA points | vs cut | Largest gap | Only here / only in cut (type disagrees) |
|---|---|---|---|---|---|---|---|---|---|---|
| adsbfi | 88 | −43.9 % | 0 % | 6,308 | −86.2 % | 0 % | 15 | −16.7 % | 374.5 s | 1 / 66 (4) |
| airplanes.live | 156 | −0.6 % | 0 % | 61,395 | +34.1 % | 0 % | 16 | −11.1 % | 19.9 s | 2 / 1 (4) |
| adsb.lol (web mirror) | 154 | −1.9 % | 0 % | 45,243 | −1.2 % | – | 18 | 0 % | 20.0 s | 1 / 0 (4) |
| adsbx | 160 | +1.9 % | – | 66,695 | +45.7 % | – | 17 | −5.6 % | 19.9 s | 5 / 0 (4) |
| free union | 156 | −0.6 % | 0 % | 67,107 | +46.6 % | 0 % | – | – | – | 2 / 1 (4) |
| free union + adsb.lol | 157 | 0 % | – | 101,594 | +121.9 % | – | 49 | +172.2 % | 18.2 s | 2 / 0 (4) |
| four-mirror union | 160 | +1.9 % | – | 160,430 | +250.4 % | – | 65 | +261.1 % | 18.2 s | 5 / 0 (4) |

Part 2 has no row for the SWFL free union of two; its "mirror union" includes adsb.lol. Every CPA number that exists for this morning is unchanged (0 %).

**Did the version matter? No.** Against this morning's copy of the same trace:
- adsbfi: 426 traces compared, 0 changed, 0 % of points.
- airplanes.live: 464 traces compared, 0 changed, 0 % of points.
- adsb.lol: 2 compared, 0 changed. This morning fetched only the 2 SWFL true flights from it.
- Comparison basis: the windowed traces and the true flights, on (time to the ms, position to 1e-6°, height to 0.1 m). The replays give the same row counts on all five mirror-days with data; the windows are identical. The rebuilt unions (NY 299, SWFL 156) and SWFL's per-mirror files are identical to this morning's, trace for trace: times, positions, heights and speeds.
- Completeness is unchanged: 9 of 9 and 31 of 31, and the same two extra eagle-cam flights.

**Reading the numbers.**
- **Points are not information.** A union's point count grows with every network merged in, because their timestamps interleave. The SWFL union with adsb.lol has +122 % points but adds no aircraft, and adsb.lol's web mirror is the same network as our cut: −1.2 % points, 0 % at CPA.
- **At CPA, airplanes.live is the densest single network in NY,** with a 10 s largest gap. Its SWFL CPA isn't denser than the cut's, though airplanes.live has the most points overall. adsbx is no denser at CPA than our cut on either case.
- **Aircraft.** adsbx sees the most window aircraft: +4.7 % in NY and +1.9 % in SWFL. The four-mirror union has 32 NY aircraft our cut lacks, against 1 the other way.

**Saved-fit searches on the refetch** (part 3's setup, fresh CPA cache names `cpa/adsbfetch/<case>_r031_*.npz`, one process). The record's rows from section 3 come first for comparison:

| Case, traces | True pair rank | Flight pairs | Refined error | Margin | Top pair, if not the true one |
|---|---|---|---|---|---|
| oyster-bay, our cut (section 3) | 1 | 328 | 43.3 m | 4.9 % | |
| oyster-bay, free union (section 3) | 1 | 55 | 43.3 m | 40.9 % | |
| oyster-bay, free union, refetched | 1 | 55 | 43.3 m | 40.9 % | |
| oyster-bay, adsbx | 1 | 44 | 43.3 m | 36.7 % | |
| oyster-bay, four-mirror union | 1 | 58 | 43.3 m | 35.3 % | |
| eagle-cam, our cut (section 3) | 1 | 607 | 877 m | 2.5 % | |
| eagle-cam, free union (section 3) | 3 | 174 | 14,087 m | 5.7 % | a0e90b+a25807 |
| eagle-cam, free union, refetched | 3 | 174 | 14,087 m | 5.7 % | a0e90b+a25807 |
| eagle-cam, adsbx | 1 | 187 | 1,173 m | 4.1 % | |
| eagle-cam, free union + adsb.lol | 1 | 182 | 1,824 m | 2.8 % | |
| eagle-cam, four-mirror union | 1 | 230 | 1,906 m | 5.2 % | |

- **Deterministic.** The refetched free unions reproduce section 3 exactly, as identical inputs should.
- **Oyster Bay is unchanged on every source:** rank 1 at 43.3 m, margin 35–41 %.
- **The eagle cam's flip is specific to adsbfi + airplanes.live.**
  - adsbx alone puts the true pair back at rank 1: 10.56 against 10.14 for the same runner-up, a0e90b+a25807.
  - So do both unions that include adsb.lol, the network of our cut (10.19 against 9.91; 10.06 against 9.56).
  - The refined error grows from 877 m to 1.2–1.9 km.
  - The margin stays small, 2.8–5.2 %.
- **Section 3's reading stands, now from both sides.** The eagle cam's rank depends on which networks' tracks are used, and its margin is within the change a different track makes. adsbx doesn't settle it, any more than the free union unsettled it.

**Scripts:** `tools/experiments/2026-11-04/adsbfetch_refetch_summary.py`; `adsbfetch_compare.py --adsbx`; the fetch and build scripts are in the run folders.

**Outputs:**
- `runs/2026-11-04-adsbfetch-refetch/`: `fetch.sh`, `command.sh`, `snapshot.txt`, `snapshot_unittest.log`, `manifests/`, `logs/`, `replay/`, `wtraces2/`, `traces2/`, `window_*.txt`, `build_npz.sh`, the `*_mirror_*.npz`, `compare_flights.*`, `completeness.json`, `headline.json`.
- `runs/2026-11-04-adsbfetch-refetch-adsbx/`: the same for adsbx.
- `runs/2026-11-04-adsbfetch-refetch-savedfit-2/`: the saved-fit runs (`-refetch-savedfit/` failed at argument parsing; nothing ran).

**Scripts:**
- `tools/data/adsbfetch_to_npz.py`, `tools/data/nnumber.py`;
- `tools/experiments/2026-11-04/adsbfetch_window.py`, `adsbfetch_compare.py`, `adsbfetch_completeness.py`, `adsbfetch_savedfit.py`.

**Outputs:**
- `runs/2026-11-04-adsbfetch/`:
  - `replay/`: day replays;
  - `window_*.txt`, `window.json`;
  - `wtraces2/` and `traces2/`: the trace rows, fetched with per-source caches;
  - `wtraces/`, `contaminated/`: before the cache fix;
  - `*_mirror_*.npz`, `completeness.json`, `compare_flights.csv`;
  - `reverify/`, `smoke.log`, `unittest.log`.
- `runs/2026-11-04-adsbfetch-savedfit/`, `-savedfit-diag/`, `-savedfit-control/`: result records.
