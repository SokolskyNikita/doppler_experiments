# Detection and fit cache keys from the code that runs (2026-11-04)

<!-- index
question: Can the detection and fit caches key on the code detect and fit run, so edits elsewhere stop costing a cold run?
outcome: Yes: over ten recent revisions the old key changed eight times and the new one three, each time for a change to what the cache holds
-->

## Question

The detection and window-fit caches were keyed on the whole source of `tracks.py`, `doppler.py` and `audio.py`, so any
edit there, a docstring, a message or a function detection never calls, made the next Tier 1 a cold run of about 50
minutes under load for every session. Can the key cover only the code that decides a detection or a fit?

## What changed

- `cache.code_sha256(DETECTOR_CODE)` hashes the named top-level functions and classes, read from source without
  importing them: each definition's AST less its docstrings and the messages of `raise` and `warnings.warn`, plus the
  module-level constants it reads. Comments never reach the AST. `DETECTOR_CODE` lists, per module, what
  `detect_events` and `fit_event` can reach: in `tracks.py`, `EventFit`, `ScanRequest`, `Candidate`, `local_whiten`,
  `sweep_weights`, `curve_contrast`, `_shape`, `grid_search`, `fit_event`, `_scan_window`, `merge_candidates` and
  `detect_events`; in `doppler.py`, `speed_of_sound`, `observed_frequency` and `ideal_curve`; in `audio.py`, the
  `Spectrogram` class. `parallel.py` is left out, since results don't depend on the number of workers.
- `cache.detection_parts`, and so `cached_detections`, and Tier 1's window-fit cache use it in place of
  `source_sha256(*DETECTOR_MODULES)`. The key's other parts, the spectrogram's content hash, the parameters, the
  producer and the numpy and scipy versions, are as before, under the cache rules.
- `tests/test_cache.py` walks the AST from `detect_events` and `fit_event`, following every name a definition reads to a
  definition of its own module or to one imported from another listed module, and fails if the closure holds anything
  `DETECTOR_CODE` doesn't list. It covers branches a trace wouldn't take and runs in milliseconds. Today the closure and
  the list are equal. A second test checks that a docstring, a raise message or a comment leaves the key unchanged, and
  that a code change or a constant change doesn't.
- A docstring or message is ignored only where it can't reach a result. The reason `fit_event` passes to
  `EventFit.unfit` is stored in the fit's `weak` field, so it is part of the cached value and changes the key.
- Tier 1 now turns a weak fit into a missing fit with `fit_event`'s own reason, instead of relying on its NaNs.

## The old and new keys over recent revisions

Both keys, computed from each revision's three files by `tools/experiments/2026-11-04/cache_key_revisions.py`
(output in `runs/2026-11-04-cache-key-revisions/keys.txt`):

| Revision | Change | Old key | New key | Why |
|---|---|---|---|---|
| 2f23318 | audio: zero-pad the STFT window to nfft | changed | **same** | detection takes a finished spectrogram; the change is in `compute_spectrogram` |
| 51f59ce, cfd466a, b5b5afa | tracks: ridge_track and the track fit | changed ×3 | **same** | detect and fit never call them |
| c2193d2 | tracks: return a weak fit when fit_event has nothing to search | changed | changed | code that runs |
| ca4c405, 4ae8612 | tracks: the unfit reason's wording | changed ×2 | changed ×2 | the reason is stored in the result's `weak` field |
| 785d360 | doppler.py restored byte for byte | changed | **same** | |
| edfd778 | no detector file touched | same | same | |

Over the ten revisions the old key changed eight times and the new one three, each of the three for a change to what
the cache holds. For an unchanged function the two keys agree on what hits: the new key differs only where the old one
also does.

The switch itself costs one cold run: the stored entries carry the old key's parts, so none of them hit under the new
key. The cache was already cold at dev's tip, after the revisions above.

## Files

`src/dopplertrack/cache.py`, `bench/tier1.py`, `tests/test_cache.py`, `tests/test_tier1.py`; script
`tools/experiments/2026-11-04/cache_key_revisions.py`; run `runs/2026-11-04-cache-key-revisions/`.
