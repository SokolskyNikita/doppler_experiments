# Edit map for Phase 1

Phase 1 changes two pieces of code: how the detector schedules its windows, and how the CPA table is
built. This page traces each one through the code and names the tests that check it. Run
`tools/check.sh` before handing a change over; [AGENTS.md](../AGENTS.md) shows how to run one test file
on its own.

## Changing detector scheduling

All of this is in [tracks.py](../src/dopplertrack/tracks.py).

1. **`detect_events`** cuts the spectrogram into windows of `window_s`, `step_s` apart. For each one,
   its `jobs()` generator crops the band, whitens the crop with `local_whiten` and builds a
   **`ScanRequest`** by keyword. A request holds the whitened window, the scored span
   (`window_start_s`, `window_end_s`), the band, the speed of sound, the speed and slant-range grids, the
   f0 and t0 steps, and how many maxima to keep and how far apart.
2. The requests go to **`_scan_window`**, through the built-in `map` when `workers=1` and through
   `parallel.process_pool` otherwise. Both consume the same requests, so everything in a request must
   pickle. `_scan_window` runs `grid_search(..., per_t0=True)` and returns up to `per_window`
   **`Candidate`s**, taking the best score first (`argsort(-bs)`) and skipping any within `min_sep_s`
   of one already kept.
3. **`merge_candidates`** pools the candidates of every window, ranks them by (score, f0, speed, slant
   range, emission CPA time), all descending, and keeps the first `2 * top` (or `top` without refinement)
   whose emission CPA times are `min_sep_s` apart. The full key decides which of two equal scores wins.
4. **`fit_event`** refines each kept candidate in a window of ±120 s around it: a grid search narrowed
   to ±30 s and ±12 Hz of the candidate, then Nelder-Mead on the unfiltered spectrogram. It returns an
   `EventFit`.
5. Back in `detect_events`, fits with a non-finite score or one not above `min_score` are dropped. The
   rest are sorted by score, and any fit within `min_sep_s` of a better one's **heard** CPA time
   (`EventFit.t_cpa`) is dropped, since refinement can pull two candidates onto one pass.

Steps 3 and 5 use different times. A `Candidate`'s `t_cpa_emit_s` is when the aircraft was at its
closest point; an `EventFit`'s `t_cpa` is when that sound reached the microphone, `d / c` later. Keep
each stage on the time it uses now.

Tests, in [tests/test_phase0_cli.py](../tests/test_phase0_cli.py):

- `test_merge_breaks_score_ties_as_the_tuple_sort_did` calls `merge_candidates` with two candidates of
  equal score 10 s apart and requires the 121 Hz one to beat the 120 Hz one presented first. A merge
  that sorts by score alone keeps the wrong one.
- `tests/test_parallel.py` checks the `--jobs` default and that pool workers start with one BLAS thread.
- `test_worker_pool_matches_serial_scan` plants one straight pass in a synthetic spectrogram and
  requires `workers=2` and `workers=1` to return equal events, refinement included. It is the first
  form of Phase 1's check that `jobs=1` and `jobs=10` agree byte for byte.
- `test_min_score_is_applied_to_refined_scores` and `test_silent_audio_has_no_detections` cover the
  score threshold after refinement and an empty recording.

### Recording seconds and Unix seconds

Everything in `tracks.py` is in **recording seconds**: seconds from the start of the spectrogram. The
flight data, and so the CPA table, are in **Unix seconds**. The two meet in
[score.py](../src/dopplertrack/score.py): `locked_score` takes event 1's measured heard CPA time
(`ev1.fit.t_cpa`, recording seconds) and the candidate flight's modelled heard CPA time (`t_heard1`,
Unix seconds) and sets `t0_map = ev1.fit.t_cpa - t_heard1`. Adding `t0_map` to a modelled Unix time
gives the recording time at which it would be heard, so both events' modelled curves are placed on the
recording with that one offset, plus the small shift swept for event 1. `pipeline.refine` and
`pipeline.pick_flight` reuse the same mapping. Before scoring, `search.pair_candidates` compares only
differences, `ev2.t_cpa - ev1.t_cpa` against `t_heard2 - t_heard1`, so it needs no offset.

## Changing the CPA build

1. **`pipeline.run_search`** ([pipeline.py](../src/dopplertrack/pipeline.py)) builds flight segments
   clipped to the grid plus `max_range_m`, then calls `cached_cpa_table(grid, segs, max_range_m, c,
   cpa_cache)`.
2. **`pipeline.cached_cpa_table`** calls `cpa_table` directly when no cache path is given. Otherwise it
   computes **`search.cpa_fingerprint`**, a SHA-256 of the grid's coordinates and elevations, every
   segment's times, positions and speeds, the range, the speed of sound and `CPA_CACHE_VERSION`, before
   taking the lock. It then holds an exclusive `fcntl` lock on `<path>.lock` (`_file_lock`) for the rest
   of the call: while it loads the cached table, checks the fingerprint, and on a miss builds and saves a
   new one. A second process asking for the same path waits on that lock instead of building the table
   again.
3. **`search.cpa_table`** ([search.py](../src/dopplertrack/search.py)) builds the rows. Each segment is
   one task, run by **`_segment_cpa`** in the calling process when `workers=1` and otherwise in a
   `parallel.process_pool` whose workers each hold the grid and its KD-tree (`_init_cpa_worker`). Tasks
   are handed out longest segment first, and the results are put back in segment order. For one segment:
   - **`_corridor`**: a KD-tree over the grid's horizontal coordinates finds the points within
     `1.05 * max_range_m` of probe samples spaced at most `max_range_m / 4` apart along the track, which
     covers the corridor around it;
   - those points are handled `chunk` (20 000) at a time, in grid-index order. Coordinates are centred on
     the chunk's mean, so which points share a chunk is part of the result's bits; keep the chunks when
     changing anything else;
   - **`_nearest_samples`** splits a chunk into tiles of `CPA_TILE_M` (4 km) and compares each tile only
     with the samples within `max_range_m` + 1 m of it, using `|g|² + |p|² − 2 g·p` with one matrix
     product per block of about 10⁷ entries. The nearest sample is the CPA; on a tie, the first;
   - a row is kept when the CPA is within `max_range_m` and not at either end of the segment. It records
     the emission time `t_emit`, the heard time `t_heard = t_emit + d / c` (both Unix seconds), the slant
     distance `d` and the ground speed `v`.

   Rows come out ordered by segment, then grid index, the same bytes for any `workers`.
4. **`search.save_cpa_table`** writes the table to a temporary file in the same folder and renames it
   into place, and **`search.load_cpa_table`** treats a mismatched fingerprint or an unreadable file as a
   miss.

If a change alters the table built from the same inputs, bump `CPA_CACHE_VERSION` so old cache files
are rebuilt.

[tests/test_cpa_build.py](../tests/test_cpa_build.py) compares `cpa_table`, at one and two workers, with
the brute-force code it replaced, on tracks that include exact ties and an end inside the range. Cache
tests, in [tests/test_cache.py](../tests/test_cache.py):

- `test_fingerprint_follows_contents_not_sizes`: a change of elevation, position, time, range or speed
  of sound changes the fingerprint even when no array changes size.
- `test_cached_table_is_reused_only_for_identical_inputs`: a second call with the same inputs loads the
  table; different inputs rebuild it.
- `test_unreadable_cache_file_is_a_miss` and `test_failed_save_leaves_nothing_behind` cover recovery
  from a damaged cache file and an interrupted save.

[tests/test_search_pairs.py](../tests/test_search_pairs.py) checks pairing and a save/load round trip,
and [tests/test_pipeline_synthetic.py](../tests/test_pipeline_synthetic.py) builds a table for two
synthetic flights and requires the true observer to rank first.
