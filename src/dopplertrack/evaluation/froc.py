"""Free-response ROC (FROC) curves (Chakraborty 2017, ch. 12, §12.4.4): at each detection score taken as the
threshold, matches (lesion localizations), misses, and extras (non-lesion localizations) per countable hour,
where Chakraborty's NLF is per case (p. 45) (ours). Not an ROC, which needs P_FA (Kay 1998, §3.4)."""
# old module: dopplertrack.evaluation.roc
from __future__ import annotations

from dopplertrack.evaluation.label_matching import match, outside_model
from dopplertrack.evaluation.tier1_knobs import COUNTED, EXCLUDED


def countable_hours(span: tuple[float, float], windows: list[dict]) -> float:
    """The audio that can hold a false alarm: the span less its uncertain, masked and outside-model windows."""
    gone = sorted((max(w["start"], span[0]), min(w["end"], span[1])) for w in windows
                  if w["class"] in EXCLUDED or (w["class"] in COUNTED and outside_model(w)))
    lost, reach = 0.0, span[0]
    for a, b in gone:
        a = max(a, reach)
        if b > a:
            lost += b - a
            reach = b
    return max(span[1] - span[0] - lost, 0.0) / 3600.0


# old name: pooled_curve
def pooled_froc_curve(units: list[tuple[list[dict], list[dict], float]]) -> list[dict]:
    """The FROC table over several spans together: at each detection score taken as the threshold, the summed
    matches, misses and extras, and extras per countable hour of all of them. Matched and missed are None
    when the pool has no counted window."""
    hours = sum(h for _, _, h in units)
    counted = any(w["class"] in COUNTED and not outside_model(w) for _, ws, _ in units for w in ws)
    rows = []
    for s in sorted({0.0, *(d["score"] for dets, _, _ in units for d in dets)}):
        ms = [match(dets, ws, s) for dets, ws, _ in units]
        extra = sum(m["extra"]["total"] for m in ms)
        rows.append({"min_score": s, "extra": extra, "extra_per_hour": extra / hours if hours else None,
                     "matched": sum(m[c]["matched"] for m in ms for c in COUNTED) if counted else None,
                     "missed": sum(m[c]["missed"] for m in ms for c in COUNTED) if counted else None})
    return rows


# old name: threshold_curve
def froc_curve(detections: list[dict], windows: list[dict], hours: float) -> list[dict]:
    """The FROC curve of one span, as a table: the match counts and extras at each detection score taken as the
    threshold."""
    rows = []
    for s in sorted({0.0, *(d["score"] for d in detections)}):
        m = match(detections, windows, s)
        rows.append({"min_score": s, "matched": sum(m[c]["matched"] for c in COUNTED),
                     "missed": sum(m[c]["missed"] for c in COUNTED), "extra": m["extra"]["total"],
                     "extra_per_hour": m["extra"]["total"] / hours if hours else None})
    return rows
