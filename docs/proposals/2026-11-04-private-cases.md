# Private cases: a site-relative benchmark interface (historical proposal)

> **Documentation correction, 2026-11-04.** Identifying examples and personal operational details are
> removed. The original proposal is privately hash-preserved at source revision `17758a5`, SHA-256
> `84a58f9abab602645dcbe0caf951e245b75742df92b981dba0cdd2af2d1ea2af`. This summary preserves the interface and implementation limits; it authorizes no run or upload.

The proposal separates a public benchmark definition from private audio, site references, trajectory cuts,
derived products and absolute results. A trajectory cut centered on a private site is itself private even
when its source is public. Repeated sessions from one site/device share a development group; their count
cannot be used as an independent-site validation sample.

## Interface and provenance

- Public definitions may describe the generic method and schema. Concrete private case IDs, session spans,
  site aliases, paths and recording provenance belong in the private registry; an opaque alias alone is not
  a privacy guarantee. The original proposal allowed more public metadata, and that allowance is withdrawn.
- Private registries resolve a site's reference in place and keep inputs, recipes and hashes outside the
  repository. `bench/private.py` implements resolution and validation. The public tree may hold synthetic
  fixtures that contain no real private site or recording facts.
- Private runs/reports go under `$DOPPLERTRACK_DATA/private/runs/`; caches go under
  `$DOPPLERTRACK_DATA/private/cache/`, isolated from shared-cache upload paths.
- Result schema v2 has a `frame: "site-relative"` variant with `offset_m` instead of latitude/longitude.
  Candidates, refinement, boxes and triples use east/north offsets. The comparison reads the reference in
  place. Reports use this relative frame and omit absolute GeoJSON/KML exports.
- `assert_no_site` rejects a container with latitude/longitude near the reference. It is an implementation
  guard, not proof that metadata, a flight/time/range combination or an unlabeled map cannot identify a site.
  Relative results and derived data still require privacy review before publication.

## Historical implementation and limits

The original record reports private-manifest support at `8bffd51` and fleet guards at `78c4b9a`.
`bench` resolves private cases in-process, uses private cache scope, separates them from public cases, and
rejects conflicting concrete input/reference fields. Reports draw offsets; `--reveal` was a local diagnostic
that writes absolute coordinates and marks its provenance. Its outputs remain private.

The original built/unbuilt distinction remains: the benchmark can invoke the locator for a resolved private
case, but `locate --site` was **not built**. `tools/data/session_spectrogram.py` creates private derived products.
These are historical implementation reports, not a fresh test of the current guards or remote storage.

The historical guard design refuses private cases in `bench inputs` and public fleet launch paths, and
excludes private inputs from seeding and shared caches. Path-prefix checks, private mode and exact per-file
approval must be inspected in the current implementation before any authorized transfer. An old statement
that nothing had been uploaded was a dated observation, not a current remote-state claim.

The scientific pilot's failed top-candidate criterion and later changed-grid diagnostic remain in
[its sanitized record](../experiments/2026-11-04-seattle-home-pilot.md). Concrete examples and execution
instructions remain only in the hash-preserved original. Experiments and private transfers remain paused.
