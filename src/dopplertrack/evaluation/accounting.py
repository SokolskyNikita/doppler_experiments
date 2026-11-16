"""Complete case accounting for a benchmark run (research readiness R6.4).

Every scheduled case falls in exactly one class:
- answered: a scored record with a candidate (a collective winner) and no abstaining verdict;
- abstained: a scored record with candidates whose verdict is not "located";
- no_candidate: a scored record with no candidate (no collective winner);
- failed: the run of the case ended in an error (an error or discarded entry, or its process crashed);
- incomplete: started and not finished: stopped at the wall-time cap, or a folder with no entry;
- missing: scheduled, and nothing of it on disk.
The denominator is the scheduled list the run recorded, never what finished. A run from before that list has an
unknown denominator: its entries are counted, and nothing is said about what else was scheduled."""
from __future__ import annotations

import json
from pathlib import Path

CLASSES = ("answered", "abstained", "no_candidate", "failed", "incomplete", "missing")
COMPLETE = ("answered", "abstained", "no_candidate")       # the case ran to a record that can be compared


def classify(entry: dict) -> str:
    """The class of a case that has a scoreboard entry."""
    if entry.get("status") != "scored":
        return "failed"
    n = entry.get("candidates", entry.get("flight_pairs"))
    if n == 0:
        return "no_candidate"
    verdict = entry.get("verdict")
    if isinstance(verdict, dict) and verdict.get("outcome") != "located":
        return "abstained"
    return "answered"


def account(run_dir, scheduled: list[dict] | None = None) -> dict:
    """The run's accounting: {"scheduled": [{"case", "group"}] or None when unknown, "classes": {case: class},
    "groups": {case: group}, "why": {case: reason} for what did not finish}. `scheduled` overrides the run's own list
    (a study knows what each arm was to run even when the arm never started); a run folder that does not exist has
    every scheduled case missing."""
    from .runner import INCOMPLETE_FILE
    run_dir = Path(run_dir)
    doc = json.loads((run_dir / "results.json").read_text()) if (run_dir / "results.json").exists() else {}
    if scheduled is None:
        scheduled = doc.get("scheduled")
    entries = {e["case"]: e for e in doc.get("cases", [])}
    classes = {c: classify(e) for c, e in entries.items()}
    groups = {c: e.get("group") for c, e in entries.items()}
    why = {c: "; ".join(e.get("errors") or [e.get("reason") or e.get("status", "")]) for c, e in entries.items()
           if classes[c] == "failed"}
    for c, reason in doc.get("crashed", {}).items():
        if c not in classes:
            classes[c], why[c] = "failed", reason
    for item in scheduled or []:
        c = item["case"]
        groups.setdefault(c, item.get("group"))
        if c in classes:
            continue
        marker = run_dir / c / INCOMPLETE_FILE
        if marker.exists():
            classes[c], why[c] = "incomplete", json.loads(marker.read_text()).get("reason", "")
        elif (run_dir / c).is_dir():
            classes[c], why[c] = "incomplete", "started; no entry was written"
        else:
            classes[c] = "missing"
    return {"scheduled": scheduled, "classes": classes, "groups": groups, "why": why}


def counts(acct: dict) -> dict:
    """{group: {"scheduled": n or None, class: n, ...}} with the total under "all"."""
    out: dict = {}
    known = acct["scheduled"] is not None
    for c, cls in acct["classes"].items():
        for g in (str(acct["groups"].get(c) or "?"), "all"):
            row = out.setdefault(g, {"scheduled": 0 if known else None, **{k: 0 for k in CLASSES}})
            row[cls] += 1
            if known:
                row["scheduled"] += 1
    out.setdefault("all", {"scheduled": 0 if known else None, **{k: 0 for k in CLASSES}})
    return dict(sorted(out.items(), key=lambda kv: (kv[0] == "all", kv[0])))


def table(acct: dict, indent: str = "  ") -> list[str]:
    """The counts as text, one row per case group and one for all of them."""
    rows = counts(acct)
    width = max(len(g) for g in rows)
    out = [f"{indent}{'group':<{width}}  {'scheduled':>9} " + " ".join(f"{k:>12}" for k in CLASSES)]
    for g, row in rows.items():
        sched = "unknown" if row["scheduled"] is None else str(row["scheduled"])
        out.append(f"{indent}{g:<{width}}  {sched:>9} "
                   + " ".join(f"{'unknown' if k == 'missing' and row['scheduled'] is None else row[k]:>12}" for k in CLASSES))
    if acct["scheduled"] is None:
        out.append(f"{indent}no scheduled list in this run: the denominator is unknown")
    out += [f"{indent}{c}: {acct['classes'][c]}: {why}" for c, why in sorted(acct["why"].items()) if why]
    return out


def paired_cases(a: dict, b: dict) -> list[str]:
    """The cases complete in both runs: the only ones a paired difference may use."""
    return sorted(c for c in a["classes"] if a["classes"][c] in COMPLETE and b["classes"].get(c) in COMPLETE)


def paired_differences(entries_a: dict, entries_b: dict, cases: list[str]) -> dict:
    """{metric: {"n": pairs with a number in both, "mean": mean of b - a, "cases": {case: b - a}}} over `cases`."""
    from .runner import entry_metrics
    out: dict = {}
    for c in cases:
        ea, eb = entries_a[c], entries_b[c]
        for m in entry_metrics(ea):
            va, vb = ea.get(m), eb.get(m)
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (va, vb)):
                out.setdefault(m, {"cases": {}})["cases"][c] = vb - va
    for m, d in out.items():
        d["n"] = len(d["cases"])
        d["mean"] = sum(d["cases"].values()) / d["n"]
    return out


def paired_lines(diffs: dict, n_cases: int, indent: str = "") -> list[str]:
    out = [f"{indent}paired differences (b - a) over the {n_cases} cases complete in both:"]
    out += [f"{indent}  {m:<20} n={d['n']:<3} mean {d['mean']:+.2f}" for m, d in diffs.items()]
    return out if diffs else out + [f"{indent}  none"]
