# Private cases: the owner's recordings in the benchmark without their place leaving the Mac (proposal)

PLAN 5.6 (independent recordings) under its privacy rule: the owner's Seattle home recordings and the site's
coordinates never leave this Mac, never go to the fleet or its bucket, and never appear in git. This is a design,
written before any code.

**decision:** whether the benchmark takes private cases as below. The alternative is keeping the home recordings out
of the benchmark and checking them by hand.

## What is private

- **The audio** (household sound): the sessions archived under `raw/seattle-home/<session>/`, and anything derived
  from it (spectrograms, detections, crops, report figures of it).
- **The site:** `site.json`, the home's coordinates to ±3 m, read in place and never copied.
- **The flight data cut around the site:** the recorder's 20 km circle in `derived/traces/<session>/` is public
  traffic, but its centre is the home, so it is treated as private too.
- **Anything that pairs them with a position:** a case's reference point, a result's absolute candidates and refined
  point, a report's map with the site marked.

Public, and kept in git: that a private case exists, its id, set and group, its session's UTC span and clock method,
its flight-data provenance, and the record's relative numbers.

## Where things live

- `$DOPPLERTRACK_DATA/private/sites/<site>.json`, one per site: `{"site_json": "incoming/seattle-home/site.json"}`, a
  pointer to the owner's file read in place, plus the elevation and datum if site.json lacks them.
- `$DOPPLERTRACK_DATA/private/cases/<case>.json`, one per case: the audio's path (`raw/seattle-home/<session>/`), the
  derived files' paths under `private/derived/<case>/` with their recipes and hashes, and the trace folder.
- `$DOPPLERTRACK_DATA/private/manifest.json`: the private raw files' hashes (`tools/data/manifest.py`, since 8bffd51).
- Nothing of this is under `raw/audio/`, `derived/` (except the recorder's own trace folders, listed in the site
  file so the guards below can find them) or in the repo.

## The case entry

In `bench/cases.json` a private case carries `"site": "<site>"` and `"private": true`, with no coordinates, no audio
path and no derived entries. Its labels name the site instead of a point: `"reference": {"site": "<site>"}`. The set
is `development`, the group `seattle-home-pilot`: one group however many days, since every session shares the
site, the device and the household's sound. `bench validate` refuses a case with `site` that also carries a
coordinate, an audio path or a derived path.

## Reading them at run time

- `bench` resolves a private case's audio, derived files and reference from `private/cases/<case>.json` and
  `private/sites/<site>.json` when it runs, on this Mac only. A missing private file is an error naming the file, not
  a skipped case.
- `locate` takes `--site <site>` in place of `--bbox`'s centre where a box is built around a site, and reads it the
  same way.
- **The record:** `case` holds the site id. Candidates, modes and the refined point are stored as east and north
  offsets in metres from the site (`"frame": "site-relative"`), not lat and lon, unless the run was given
  `--reveal`, which the owner sets for a local look; a revealed record says so in its provenance. The comparison
  scores distances from the offsets, which need no coordinates.
- **The report** draws the map in the site-relative frame, without the site marker or a lat/lon grid, unless the
  record is revealed. GeoJSON and KML are not written for an unrevealed record, since they are absolute by nature.
- **Records and reports of private cases** go to `private/runs/`, not `runs/`, since `runs/` is where the fleet's
  results come back and what a later `--input-run` could send up.
- **Caches, a rule:** every private case runs with `DOPPLERTRACK_CACHE` set to `$DOPPLERTRACK_DATA/private/cache/` by
  `bench` itself (`runner.private_cache`, around the case's execution and `bench prepare`), never the shared cache
  root. A detection or window-fit entry computed from household audio carries no private marker, and `runs seed`
  uploads the shared caches; the CPA table, built around the site, lands there too. Terrain tiles for the site's box
  are fetched into the private cache from the public tile server, as the recorder's ADS-B fetch already queries the
  area.

## Guards (SDE-E, for the fleet)

Built by SDE-E in 78c4b9a: private paths are private/, incoming/, raw/seattle-home/, any path with a `private`
folder, the prefixes in `$DOPPLERTRACK_DATA/private/fleet-exclude.txt`, and everything under derived/traces/ but the
YYYY-MM-DD day traces; `--case` refuses `private: true` or a `site`. What it guards:

- `runs launch --case` refuses a case with `site` outright.
- `runs seed`, `fetch-sources`, `--input` and `--input-run` refuse or skip `private/`, `incoming/`,
  `raw/seattle-home/` and every trace folder a site file lists. Today `runs seed` would upload the recorder's trace
  folders with the rest of `derived/`; nothing has been uploaded (the bucket's `derived/traces/` holds none of them,
  checked 2026-11-04).
- `bench inputs` refuses a private case, so a job listing can never name one.
- A test in each repo's Tier 0: a fixture private case (a fake site, fake audio) that every guard refuses.

## Built (2026-11-04, after acceptance)

- `bench/private.py`: the site read in place, a case resolved from its private file, the record put in the site's
  frame (candidates, the refined point and every box as offsets, the triples sidecar as east and north arrays), and
  `assert_no_site`, which refuses to write a record holding a latitude and a longitude near the site in any one
  container, whatever the field is called.
- Result schema: v2's site-relative variant (`frame: "site-relative"`, `site`, `offset_m` in place of lat and lon),
  chosen by the record's frame; no v3 needed.
- `bench`: a private case runs only in-process, never with a public case, into `private/runs/`, with its caches in
  `private/cache/`; `--reveal` writes absolute coordinates and marks the record so; the comparison scores distances
  from the offsets (or from the site, read in place, when revealed); `bench inputs` refuses a private case;
  `bench validate` refuses a private entry that carries a coordinate, an audio path, a box or a derived file.
- The report draws a site-relative record in east and north km from an unmarked site and writes no GeoJSON or KML.
- `tools/data/session_spectrogram.py`: a recorder session's spectrogram, written only under `private/`.
- The first case, `seattle-home-20261104-ha-pilot-2`, blocked until the owner approves a local run: its public entry,
  and its private file (spectrogram recipe, flight data, a 4 km search box whose 12 km padding stays inside the
  recorder's 20 km circle, the traffic notes).
- Not built: `locate --site` on the command line; the benchmark runs `locate` on a private case already.

## Order

1. Archive the sessions under `raw/seattle-home/` once `manifest.py`'s private manifest (8bffd51) is on dev, so no
   run of it writes their names into `bench/manifest.json`.
2. E's guards, before anyone runs `runs seed` again.
3. The case fields, `bench`'s and `locate`'s resolution, the site-relative record and report: one change, with the
   fixture tests.
4. The first private case (`seattle-home-20261104-ha-pilot-2`), scored only when the owner approves a local run.
