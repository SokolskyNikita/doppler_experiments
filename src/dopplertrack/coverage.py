"""Flight-data extraction envelopes and diagnostics (not ADS-B completeness guarantees)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .geo import haversine_m
from .doppler import MAX_TRACE_GAP_S

DEFAULT_MAX_RANGE_M = 12000.0
ADS_B_LIMITATION = "A complete archive download does not mean every aircraft broadcast ADS-B."


@dataclass
class ScanReport:
    seen: int = 0
    malformed: int = 0
    empty: int = 0
    outside_bbox: int = 0
    excluded_types: int = 0
    kept: int = 0

    def to_dict(self):
        return asdict(self)


def padded_bbox(bbox, max_range_m=DEFAULT_MAX_RANGE_M):
    """Conservatively enclose points within range of a WGS-84 latitude/longitude box.

    The minimum Earth curvature radius bounds the angular distance. At a pole or
    across the date line we retain all longitudes rather than under-fetching.
    """
    south, north, west, east = map(float, bbox)
    if not (-90 <= south <= north <= 90 and -180 <= west <= east <= 180):
        raise ValueError("bbox must be ordered LATMIN LATMAX LONMIN LONMAX within WGS-84 bounds")
    if not np.isfinite(max_range_m) or max_range_m < 0:
        raise ValueError("max_range_m must be finite and non-negative")
    angle = max_range_m / 6335439.0
    if angle >= np.pi / 2:
        return (-90.0, 90.0, -180.0, 180.0)
    dlat = np.degrees(angle)
    lo, hi = max(-90.0, south - dlat), min(90.0, north + dlat)
    if lo <= -90 or hi >= 90:
        return (lo, hi, -180.0, 180.0)
    dlon = np.degrees(np.arcsin(min(1.0, np.sin(angle) / np.cos(np.radians(max(abs(south), abs(north)))))))
    if west - dlon < -180 or east + dlon > 180:
        return (lo, hi, -180.0, 180.0)
    return (lo, hi, west - dlon, east + dlon)


def extraction_metadata(bbox, max_range_m, report, **source):
    return dict(version=1, requested_bbox=list(bbox), coverage_bbox=list(padded_bbox(bbox, max_range_m)),
                max_range_m=max_range_m, scan=report.to_dict(),
                height_datums={"geometric": "WGS-84 ellipsoidal", "barometric": "pressure altitude",
                               "terrain": "orthometric (Terrarium); no geoid correction applied"}, **source)


def report_altitude_sources(traces, log):
    counts = dict(geometric=0, barometric=0, none=0, unknown=0)
    for tr in traces:
        if tr.alt_source is None:
            counts["unknown"] += len(tr)
        else:
            for source, n in zip(*np.unique(tr.alt_source, return_counts=True)):
                key = source if source in counts else "unknown"
                counts[key] += int(n)
    total = sum(counts.values())
    fraction = counts["barometric"] / total if total else 0.0
    log(f"altitudes: {counts['barometric']}/{total} points barometric-only ({fraction:.1%}); "
        f"{counts['geometric']} geometric (WGS-84 ellipsoidal); {counts['none']} missing; "
        f"{counts['unknown']} source unknown. Pressure altitude and orthometric terrain are not the same datum.")


def report_coverage(metadata, bbox, max_range_m, log):
    """Warn about insufficient or unknown extraction coverage, including legacy files."""
    scan = metadata.get("scan")
    if scan:
        log(f"flight data: {scan['seen']} traces scanned; {scan['kept']} kept; "
            f"{scan['malformed']} skipped as malformed; {scan['empty']} empty; "
            f"{scan['outside_bbox']} outside envelope; {scan['excluded_types']} excluded by aircraft type")
    else:
        log("flight data: scan counts unavailable (legacy file or unrecorded extraction)")
    envelope = metadata.get("coverage_bbox")
    required = padded_bbox(bbox, max_range_m)
    if envelope is None:
        log("WARNING: flight-data coverage envelope is unknown; re-extract with the search range margin")
    elif not (envelope[0] <= required[0] and envelope[1] >= required[1]
              and envelope[2] <= required[2] and envelope[3] >= required[3]):
        log(f"WARNING: flight-data envelope {envelope} does not cover the search box plus "
            f"{max_range_m:g} m range; required envelope {required}")
    log(ADS_B_LIMITATION)


def candidate_gaps(traces, lat, lon, t_start, t_end, max_range_m, max_gap_s=MAX_TRACE_GAP_S):
    """Known interior airborne trace gaps near a candidate during its inferred recording.

    Proximity uses the endpoints, not interpolation across missing observations.
    Unobserved aircraft and gaps beyond the endpoints cannot be diagnosed here.
    """
    gaps = []
    for tr in traces:
        for left, right, reason in tr.coverage_gaps(max_gap_s):
            if tr.t[left] > t_end or tr.t[right] < t_start:
                continue
            distance = haversine_m(lat, lon, tr.lat[[left, right]], tr.lon[[left, right]])
            if np.min(distance) <= max_range_m:
                gaps.append((tr.icao, float(tr.t[left]), float(tr.t[right]), reason))
    return gaps


def report_candidate_gaps(traces, results, sp, ev, max_range_m, c, log):
    """Report the top 20 scored rows; empty results still get an explicit diagnostic."""
    rows = results.head(20)
    affected = 0
    log(f"checking trace coverage gaps (time gaps >{MAX_TRACE_GAP_S:g} s, missing positions/heights, new legs) "
        f"near the top {len(rows)} candidates "
        "(endpoint proximity only; this cannot establish complete coverage)")
    for rank, row in enumerate(rows.itertuples(), 1):
        offset = ev.t_cpa - row.t_heard1 + row.shift
        gaps = candidate_gaps(traces, row.lat, row.lon, sp.t[0] - offset - max_range_m / c,
                              sp.t[-1] - offset, max_range_m)
        if gaps:
            affected += 1
            detail = "; ".join(f"{icao} {start:.0f}–{end:.0f} UTC unix s ({reason})"
                               for icao, start, end, reason in gaps[:3])
            log(f"WARNING: candidate {rank}: {len(gaps)} known nearby trace gaps: {detail}")
    if rows.empty:
        log("no candidates; candidate-local trace gaps cannot be checked")
    else:
        log(f"{affected} of {len(rows)} checked candidates have known nearby trace gaps")
