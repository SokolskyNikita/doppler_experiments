# Private recording pilot: limited location evidence (2026-11-04)

<!-- index
question: What do the pilot's tonal checks and location searches establish before a calibrated verdict exists?
outcome: Development evidence only: the 200 m-grid box series fails its original 300 m top-candidate criterion; a later 50 m diagnostic improves the error but does not reverse that failure
-->

> **Documentation correction, 2026-11-04.** Internal attribution and identifying recording/site metadata
> have been removed. The original was privately preserved before this replacement. Its source is revision
> `17758a5`, SHA-256 `9fbc2ff7707cde99b6f83680f2c608bc8adec43ee9bc8151607b2deb17a9e27e`. Scientific failures and changes of design are retained below.

## Question and original criterion

The pilot asked what tonal evidence a recording carries and what the automatic locator returns. It is one
**development group**, with no independent confident-wrong-rate or uncertainty-region calibration.
Known-point checks supply the reference location and clock; they measure assisted audibility, not blind
source detection or location.

A later box-size series fixed a different criterion before its run: with a 200 m grid and the reference
point deliberately off the grid, the **top-ranked candidate must lie within 300 m** of the reference.
The series stops at the first failing box size. A refined point alone cannot satisfy that criterion.

## Results retained from the original record

| Stage | Observation | Interpretation |
|---|---|---|
| Known-point tonal check | 2 tonal detections among 11 ear-audible passes | The detector does not recover all audible evidence; a known-point score is an assisted diagnostic. |
| Broadband follow-up | 3 of those 11 exceed the broadband threshold; median rise 0.8 dB; the null marks 10% of 200 random times | Placement, stored band, source spectrum and detection remain confounded; no single cause established. |
| Default silence filter | 44 time-joined candidates reduced to 0; none scored | `insufficient_evidence` / `no_surviving_candidate`; clock gating never reached. Another site’s default did not transfer. |
| Initial geometry | A winning point coincided with a grid node at the reference | Not independent evidence of fine accuracy; the off-grid rerun is the deciding check. |
| First off-grid box, 200 m spacing | Top candidate 482 m from reference; refinement 294 m | **Fails** the pre-registered 300 m top-candidate criterion; the judged size series stops here. |
| Larger boxes, 200 m spacing | Top errors 480 m and 477 m; refinements 238 m and 273 m | Reported diagnostics after the stop; cannot turn the series into a pass. |
| Denser grid, 50 m spacing | Top candidate 294 m; refinement 241 m | A later sampling diagnostic. It meets the distance line under a changed grid, not the original series criterion. |

The smaller error on a denser grid supports a sampling-sensitivity diagnosis. It does not establish the
absence of a stronger wrong mode in a larger search, reliable flight association, a calibrated verdict,
or a position-uncertainty region. All displayed candidate verdicts remain experimental; the word “found”
in earlier narrative must not be read as a validated “located” outcome.

## Status and unresolved decisions

- The original 300 m criterion remains **failed**. The later denser-grid result is not a rescue or a held-out test.
- A wider-box search and a broader-band comparison were proposed; their results are not established here.
- New recordings, different bands and different detector settings require a frozen successor design and
  group-aware evaluation. Reusing the same site/device does not create independent groups.
- Source audio, per-flight evidence, site details, absolute candidates and operational instructions remain
  in the privately preserved original and associated private artifacts. They were not reprocessed for this audit.

The implementation used the existing known-point, broadband and pilot-launch experiment scripts. Their
presence does not authorize a new run. See [research reset](2026-11-04-research-reset.md) for the wider
method lineage, full-search null requirements and limits on inference.
