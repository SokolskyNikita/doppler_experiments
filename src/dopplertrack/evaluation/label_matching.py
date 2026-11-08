"""Label-to-detection matching: true positives (matched), false negatives (missed) and false positives (extra) per
window class, by heard CPA and a harmonic of f0 on a labelled line, as FROC scoring marks them (Chakraborty 2017,
§12.4.3); uncertain and masked windows are don't-care regions (ours)."""
from __future__ import annotations

from dopplertrack.evaluation.tier1_knobs import COUNTED, EXCLUDED, KNOBS


def rising(line) -> bool:
    """A labelled line whose exit frequency is above its entry: no straight pass makes that."""
    return float(line[1]) > float(line[0])


def outside_model(w: dict) -> bool:
    """A counted window none of whose lines a straight pass could make: it can't be a flyover, so it is
    neither matched nor missed, and detections inside it count nowhere."""
    return not any(not rising(line) for line in w["lines"])


def _in_band(f: float, line) -> bool:
    tol = KNOBS["line_tolerance"]
    return min(line) * (1 - tol) <= f <= max(line) * (1 + tol)


def line_match(f0: float, lines: list[list[float]]) -> bool:
    """Whether a detection's f0 is a window's fundamental: for some k in harmonic_ratios, f0 * k lies in
    exactly one line's band, and no other k puts it on that line; and when the window has two or more falling
    lines, the next harmonic, 2 * f0 * k, lies in another line's band. Rising lines take no part."""
    falling = [line for line in lines if not rising(line)]
    ks = KNOBS["harmonic_ratios"]
    for k in ks:
        on = [j for j, line in enumerate(falling) if _in_band(f0 * k, line)]
        if len(on) != 1:
            continue
        j = on[0]
        if any(_in_band(f0 * k2, falling[j]) for k2 in ks if k2 != k):
            continue                      # the line's band spans a factor of two: which harmonic is ambiguous
        if len(falling) < 2 or any(_in_band(2 * f0 * k, line) for i, line in enumerate(falling) if i != j):
            return True
    return False


def match(detections: list[dict], windows: list[dict], min_score: float = 0.0) -> dict:
    """Matched, missed and extra per window class for the detections scoring at least min_score.
    A detection matches a counted window when its heard CPA lies in the window (with slack) and its f0, or a
    harmonic ratio of it, lies on one of the window's lines. One that matches none is excluded if its heard
    CPA lies in an uncertain or masked window, and extra otherwise."""
    slack = KNOBS["cpa_slack_s"]
    dets = [d for d in detections if d["score"] >= min_score]
    hit, extra_by = set(), {}
    excluded = 0
    for d in dets:
        inside = [w for w in windows if w["start"] - slack <= d["t_cpa"] <= w["end"] + slack]
        matches = [w for w in inside if w["class"] in COUNTED and not outside_model(w) and line_match(d["f0"], w["lines"])]
        if matches:
            hit.update(w["index"] for w in matches)
        elif any(w["class"] in EXCLUDED or (w["class"] in COUNTED and outside_model(w)) for w in inside):
            excluded += 1
        else:
            home = min(inside, key=lambda w: abs((w["start"] + w["end"]) / 2 - d["t_cpa"]))["class"] if inside else "outside"
            extra_by[home] = extra_by.get(home, 0) + 1
    out = {}
    for cls in COUNTED:
        ws = [w for w in windows if w["class"] == cls and not outside_model(w)]
        out[cls] = {"windows": len(ws), "matched": sum(w["index"] in hit for w in ws),
                    "missed": sum(w["index"] not in hit for w in ws),
                    "outside_model": sum(1 for w in windows if w["class"] == cls and outside_model(w))}
    out["extra"] = {"total": sum(extra_by.values()), "by_window_class": extra_by}
    out["excluded_detections"] = excluded
    out["detections"] = len(dets)
    return out
