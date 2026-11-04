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
- Every request went at the CLI's own pace: serial, 2 s apart.
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
