# A sound-speed input (2026-11-04)

## Question

PLAN Phase 2 item 2's engineering outcome: the pipeline fixes the speed of sound at its 15 °C value in every caller,
although stage 3 found that an x % error in c is an x % error in fitted speed and slant range. Can it take a measured
temperature, from the command line and from a case, without changing anything when none is given?

## What changed

- `doppler.speed_of_sound(temp_c=15.0)`, 331.3 √(1 + T/273.15), was already there and is unchanged. The new
  `atmosphere.mid_height_temperature(ground_c, aircraft_height_m)` gives the temperature halfway up the path, ground −
  3.25 °C per km of the aircraft's height, which the path's harmonic-mean sound speed follows to about 0.2 %.
  It lives in its own module because `doppler.py`'s source is part of the detection and fit caches' key: putting it
  there would have invalidated every cached detection for every session that merged it.
- `fit`, `detect`, `search`, `refine` and `search-single` take `--temperature C`, and `--aircraft-height METRES` with it
  for the mid-height temperature. The speed of sound is passed to the pipeline only when a temperature is given, so the
  default path is today's code path, unchanged. `detect` caches its result under a key that includes c only when c is
  given.
- The mid-height correction is per case, a typical aircraft height for the box, not per flight. Per flight would need a
  different c per segment, but the CPA table, the scoring and the CPA fingerprint each take one c. The paragraph puts
  the correction at 0.2–1.2 % for heights of 0.3–2 km; per flight is a follow-up if a measurement shows it matters.
- Every case in `bench/cases.json` has a `weather` block: `temperature_c`, `source`, `station`,
  `station_distance_km`, `observed_utc`, `aircraft_height_m`. All are null for now; D owns the weather files and will
  add the station readings for the seed cases. The validator requires source, station and distance with a temperature,
  and refuses a height without one. The runner turns a temperature into c for `detect` (raw-audio), `search` and
  `refine`, and Tier 1's known point and trajectory reference use the reference case's. Every record's
  `parameters.speed_of_sound` says which c was used and why ("the pipeline's default, 15 C" when null).
  a16b700's CLI has no temperature input, so it refuses a case that sets one. A changed c already changes the CPA
  table's fingerprint, so the table rebuilds in place.

## Checks

Tier 0, `tests/test_sound_speed.py` (25 tests):
- for each of the five commands, with no temperature the pipeline is called without `c`, so the call is today's; with
  `--temperature 15` it gets 340.275 m/s, the default's own value; with 30 °C and with a 2 km aircraft height it gets
  speed_of_sound(30) and speed_of_sound(8.5);
- `--aircraft-height` without `--temperature` is refused;
- the CPA fingerprint differs between 15 °C and 20 °C;
- the case validator and the runner's c and provenance.

`tools/check.sh` is green at 785d360: 235 passed, 4 skipped.

No case sets a temperature, so no benchmark result can change. An end-to-end warm Tier 1 comparison wasn't possible:
dev's own changes to `tracks.py` and `audio.py` (A's fit_event messages, C's zero-padded STFT) since the last warm run
had already changed the detection cache's key, so the run would have been a cold one with a changed detector; it was
stopped rather than tie up the shared machine for an hour. Its partial folders (`runs/2026-11-04-bench-9f094a1-t1/`,
`-785d360-t1/`, `-785d360-t1-2/`) hold nothing to use.

## Files

`src/dopplertrack/atmosphere.py`, `src/dopplertrack/cli.py`, `bench/runner.py`, `bench/tier1.py`, `bench/cases.py`,
`bench/cases.json`, `tests/test_sound_speed.py`.
