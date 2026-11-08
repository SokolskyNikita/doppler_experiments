"""Tier 1's evaluation hyper-parameters (knobs) and window classes, set before any detection was matched against a
label, to avoid selection bias in the performance estimate (Cawley & Talbot 2010)."""
from __future__ import annotations

KNOBS = {
    "crop_margin_s": 240.0,      # detect sees the span plus this either side; a detection belongs to the span by its
                                 # heard CPA, so one whose window straddles an edge is judged on partial evidence
    "cpa_slack_s": 5.0,          # a detection's heard CPA may lie this far outside a window: labels are read to seconds
    "line_tolerance": 0.10,      # f0 * k within this fraction of a labelled line's entry-exit band
    "harmonic_ratios": [0.5, 1.0, 2.0],  # f0 * k on exactly one line for one k, and with two or more lines its next
                                 # harmonic on another (see line_match); tightened before the full spans were matched
    "fit_band_margin": 0.10,     # a labelled line is fitted in its band widened by this fraction
    "association_dt_s": 10.0,    # a detection agrees with its associated flight within this heard-CPA difference
    "association_df": 0.10,      # and this fraction of f0
}


COUNTED = ("clear", "overlapping")           # matched or missed
EXCLUDED = ("uncertain", "masked")           # in neither count, nor are detections inside them
