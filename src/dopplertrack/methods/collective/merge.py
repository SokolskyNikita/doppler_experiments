"""One collective result from the units of a search split by only_cells: the fine stage's cells run as separate units
(each repeats the deterministic coarse stage), and their results combine by maximum. Every kept cell must be there
exactly once, in a complete unit of the same search; a missing, repeated, unfinished or foreign unit is refused."""
from __future__ import annotations

from dopplertrack.components.planning.modes import distinct_modes
from dopplertrack.methods.collective.parameters import from_record
from dopplertrack.methods.collective.units import IncompleteUnit, read_units, same_search

COARSE_KEYS = ("coarse_map", "kept", "margin", "windows", "sweeps", "parameters")   # the same in every unit of a search


def merge_results(units: list[dict]) -> dict:
    """The merged result of read_units' units. Its winner is the unit winner with the highest Z (the earlier-ranked
    unit on a tie); its modes follow planning.merge_modes: "best_unit" keeps the winning unit's list, "all_units"
    applies the mode rule again to every unit's modes together. The second sees only what each unit listed (at most
    max_modes each), so a peak one unit suppressed under a neighbour that another unit's peak then suppresses is not
    recovered."""
    same_search(units)
    first = units[0]["result"]
    for u in units[1:]:
        differs = [k for k in COARSE_KEYS if u["result"].get(k) != first.get(k)]
        if differs:
            raise IncompleteUnit(f"{u['path']} has a different coarse stage from {units[0]['path']}: {', '.join(differs)}")
    kept = first.get("kept")
    out = {k: first[k] for k in ("statistic", "statistic_identity", "domain", *COARSE_KEYS) if k in first}
    if "control" in first:
        out["control"] = first["control"]
    out["merged_from"] = [{"path": u["path"], "result_sha256": u["result_sha256"],
                           "fine_ranks": u["result"].get("fine_ranks"),
                           "Z": (u["result"].get("winner") or {}).get("Z")} for u in units]
    if kept is None:                           # the coarse stage ended the search: every unit says the same
        if len(units) > 1 and any(u["result"].get("reason") != first.get("reason") for u in units):
            raise IncompleteUnit("units of one search end their coarse stage for different reasons")
        return dict(out, winner=None, reason=first.get("reason"), fine_ranks=[])
    ranks = [r for u in units for r in u["result"].get("fine_ranks", [])]
    missing = sorted(set(range(len(kept))) - set(ranks))
    repeated = sorted({r for r in ranks if ranks.count(r) > 1})
    if missing or repeated:
        raise IncompleteUnit(f"the units do not cover the {len(kept)} kept cells once each: "
                             f"missing ranks {missing}, repeated ranks {repeated}")
    won = [u for u in units if u["result"].get("winner")]
    out["fine_ranks"] = sorted(ranks)
    out["fine_cells"] = sorted((c for u in units for c in u["result"].get("fine_cells", [])), key=lambda c: -c["Z"])
    out["counts"] = {k: sum(u["result"]["counts"].get(k, 0) for u in units)
                     for k in ("fine_points", "fine_cells", "fine_points_without_terrain", "fine_cpa_rows", "fine_candidates")}
    if not won:
        return dict(out, winner=None, reason="no fine point has a window above its null")
    best = max(won, key=lambda u: (u["result"]["winner"]["Z"], -min(u["result"]["fine_ranks"])))
    pl = from_record(first["parameters"]).planning
    if pl.merge_modes == "all_units":
        peaks = sorted((m for u in won for m in u["result"].get("modes", [])), key=lambda m: -m["Z"])
        found = distinct_modes(peaks, pl.mode_separation_m, pl.max_modes, pl.mode_clock_separation_s)
    else:
        found = best["result"].get("modes", [])
    return dict(out, winner=best["result"]["winner"], modes=found, merge_modes=pl.merge_modes,
                coarse_max=first["margin"]["coarse_max"])


def merge_units(paths) -> dict:
    """merge_results of the unit folders at paths (units.read_units checks each is complete)."""
    return merge_results(read_units(paths))
