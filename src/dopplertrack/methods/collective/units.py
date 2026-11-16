"""A collective run's folder, the unit that merging and the null read: request.json (written before the search: the
config, the inputs' hashes, the statistic identity and its launcher label), result.json with its hash beside it, and
completed.json, written last. A folder is complete only with all four and a matching hash; anything else is refused
by name, never skipped."""
from __future__ import annotations

import json
from pathlib import Path

FILES = ("request.json", "result.json", "result.json.sha256", "completed.json")


class IncompleteUnit(ValueError):
    """A run folder that is not a complete unit, or units that can't be combined."""


def start_unit(out, request: dict) -> None:
    """Create the folder (it must not exist) and write the request, marked running."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "request.json").write_text(json.dumps({**request, "status": "running"}, indent=2) + "\n")


def finish_unit(out, result: dict) -> None:
    """Write the result as a versioned collective record (runtime/records.COLLECTIVE_V1), its hash, and then the
    completion marker."""
    from dopplertrack.runtime.cache import file_sha256
    from dopplertrack.runtime.records import versioned_collective
    out = Path(out)
    output = out / "result.json"
    result = json.loads(json.dumps(result, default=float))       # numpy scalars as plain numbers, as written
    output.write_text(json.dumps(versioned_collective(result), indent=2) + "\n")
    (out / "result.json.sha256").write_text(f"{file_sha256(output)}  result.json\n")
    (out / "completed.json").write_text('{"status": "completed"}\n')


def unit_problem(path) -> str | None:
    """Why the folder is not a complete unit, or None when it is."""
    from dopplertrack.runtime.cache import file_sha256
    path = Path(path)
    missing = [f for f in FILES if not (path / f).is_file()]
    if missing:
        return f"no {', '.join(missing)}"
    try:
        if json.loads((path / "completed.json").read_text()).get("status") != "completed":
            return "completed.json does not say completed"
    except (ValueError, AttributeError):
        return "completed.json is not readable"
    stored = (path / "result.json.sha256").read_text().split()
    if not stored or stored[0] != file_sha256(path / "result.json"):
        return "result.json does not match its recorded hash"
    return None


def read_units(paths) -> list[dict]:
    """Each folder as {"path", "request", "result", "result_sha256"}; IncompleteUnit names every folder that is not a
    complete unit, or whose result carries no statistic identity (written before readiness R5)."""
    units, bad = [], []
    for path in (Path(p) for p in paths):
        why = unit_problem(path)
        if why is None:
            request, result = (json.loads((path / f).read_text()) for f in ("request.json", "result.json"))
            if not isinstance(result.get("statistic_identity"), dict) or "domain" not in result:
                why = "result.json has no statistic identity"
        if why is not None:
            bad.append(f"{path}: {why}")
            continue
        units.append({"path": str(path), "request": request, "result": result,
                      "result_sha256": (path / "result.json.sha256").read_text().split()[0]})
    if bad:
        raise IncompleteUnit("not complete units: " + "; ".join(bad))
    return units


def same_search(units: list[dict], traffic: bool = True) -> None:
    """Refuse units that are not one search: a different statistic identity, domain or spectrogram and, with traffic,
    different trace files or control day."""
    def key(u):
        inputs = u["request"].get("inputs") or {}
        k = {"statistic_identity": u["result"]["statistic_identity"], "domain": u["result"]["domain"],
             "spectrogram": inputs.get("spectrogram")}
        if traffic:
            k.update(traces=inputs.get("traces"), control=u["result"].get("control"))
        return k
    first = key(units[0])
    for u in units[1:]:
        differs = [name for name, value in key(u).items() if value != first[name]]
        if differs:
            raise IncompleteUnit(f"{u['path']} is not the same search as {units[0]['path']}: "
                                 f"{', '.join(differs)} differ")
