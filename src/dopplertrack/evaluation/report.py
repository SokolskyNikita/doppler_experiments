"""`bench report RUN [case ...]`: the Phase 5 page for every case of a run folder, and an index.html linking them.

The pages go to a new run folder (runs/<date>-report-<RUN's name>/<case>/), never into RUN: an older run is not
written into. The page reads RUN's records and sidecars where they are."""
from __future__ import annotations

import json
from pathlib import Path

from .cases import data_root, load_cases


def _case_set(doc: dict, case: dict) -> str | None:
    for c in doc["cases"]:
        if c["id"] == case.get("id") and c["version"] == case.get("version"):
            return c["set"]
    return None


def report_run(run_dir: Path, case_ids: list[str] | None = None, out_dir: Path | None = None, log=print) -> Path:
    """Render each case's result.json in run_dir (all of them, or case_ids) into out_dir/<case>/ (default: a new
    run folder), then out_dir/index.html. A case whose page fails is listed in the index with the error, and the
    others still render."""
    from dopplertrack.reporting.html import render_index, render_report

    from .runner import new_run
    doc = load_cases()
    if out_dir is None:
        out_dir = new_run(f"report-{run_dir.name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dirs = [run_dir / c for c in case_ids] if case_ids else sorted(p.parent for p in run_dir.glob("*/result.json"))
    pages = []
    for d in dirs:
        row = {"case": d.name}
        entry = d / "entry.json"
        if entry.exists():
            e = json.loads(entry.read_text())
            row["status"] = e.get("status")
            v = e.get("verdict")
            row["verdict"] = f"{v['outcome']} {' '.join(v['reason_codes'])}" if isinstance(v, dict) else ""
        else:
            row["status"] = "no entry (the run stopped before scoring it)"
        if not (d / "result.json").exists():
            pages.append({**row, "note": "no result.json"})
            continue
        try:
            case = json.loads((d / "result.json").read_text()).get("case") or {}
            row["set"] = _case_set(doc, case)
            page = render_report(d / "result.json", out_dir=out_dir / d.name, case_meta={"set": row["set"]},
                                 data_root=data_root())
            row["page"] = str(page.relative_to(out_dir))
            log(f"{d.name}: {page}")
        except Exception as exc:
            row["note"] = f"report failed: {type(exc).__name__}: {exc}"
            log(f"{d.name}: {row['note']}")
        pages.append(row)
    return render_index(out_dir, pages, title=f"{run_dir.name}")
