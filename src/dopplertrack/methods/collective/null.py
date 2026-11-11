"""The collective search's control draws: the same search on the same recording with another day's traffic, each
reduced to one row. Collecting them refuses what would make the rows values of something else than the own-day
statistic: an incomplete or partial unit, a different statistic identity, domain or recording, a day that is missing,
repeated or not asked for. What threshold the draws give is research (PLAN.md), not done here."""
from __future__ import annotations

import json

import numpy as np

from dopplertrack.methods.collective.units import IncompleteUnit, read_units, same_search

FIELDS = ("day", "max_Z", "second_Z", "lat", "lon", "n_matched", "clock_audio_minus_unix")


def draw_row(result: dict, day: str | None = None) -> dict:
    """One search as a draw: its winner's Z (max_Z), place, clock and matched windows, and the best other mode's Z
    (second_Z; the mode rule already keeps modes distinct). NaN where the search has no winner or no second mode."""
    w = result.get("winner") or {}
    others = (result.get("modes") or [])[1:]
    nan = float("nan")
    return {"day": day or "", "max_Z": float(w.get("Z", nan)), "second_Z": float(others[0]["Z"]) if others else nan,
            "lat": float(w.get("lat", nan)), "lon": float(w.get("lon", nan)), "n_matched": int(w.get("n_matched", 0)),
            "clock_audio_minus_unix": float(w.get("clock_audio_minus_unix", nan))}


def _whole(u: dict) -> bool:
    kept = u["result"].get("kept")
    return kept is None or sorted(u["result"].get("fine_ranks", [])) == list(range(len(kept)))


def collect_draws(own_path, draw_paths, days) -> dict:
    """The own-day search and its control draws as one table. own_path and each of draw_paths is a complete unit
    folder holding a whole search (a full run, or merge's output); days lists the control days expected, each exactly
    once among the draws. Raises IncompleteUnit, naming the trouble, rather than leave anything out."""
    own, *draws = read_units([own_path, *draw_paths])
    same_search([own, *draws], traffic=False)
    partial = [u["path"] for u in (own, *draws) if not _whole(u)]
    if partial:
        raise IncompleteUnit(f"only part of the fine stage (merge the search's units first): {', '.join(partial)}")
    if own["result"].get("control"):
        raise IncompleteUnit(f"{own['path']} is itself a control draw, not the own-day search")
    by_day: dict[str, dict] = {}
    for u in draws:
        control = u["result"].get("control")
        if not control:
            raise IncompleteUnit(f"{u['path']} records no control day")
        if control["traffic_day"] in by_day:
            raise IncompleteUnit(f"two draws for {control['traffic_day']}: {by_day[control['traffic_day']]['path']} and {u['path']}")
        by_day[control["traffic_day"]] = u
    days = [str(d) for d in days]
    missing, extra = sorted(set(days) - set(by_day)), sorted(set(by_day) - set(days))
    if missing or extra or len(set(days)) != len(days):
        raise IncompleteUnit(f"the draws are not the days asked for: missing {missing}, not asked for {extra}")
    recording = {u["result"]["control"]["recording_day"] for u in draws}
    if len(recording) > 1:
        raise IncompleteUnit(f"the draws are mapped onto different recording days: {sorted(recording)}")
    return {"statistic_identity": own["result"]["statistic_identity"], "domain": own["result"]["domain"],
            "recording_day": next(iter(recording), None), "own": draw_row(own["result"]),
            "draws": [draw_row(by_day[d]["result"], d) for d in days],
            "units": {"own": own["result_sha256"], **{d: by_day[d]["result_sha256"] for d in days}}}


def save_draws(path, table: dict) -> None:
    """collect_draws' table as an NPZ: one array per field over the draws, own_<field> for the own day, and the
    statistic identity (its name, its id, and the whole of it, the domain and the recording day as JSON)."""
    ident = table["statistic_identity"]
    arrays = {f: np.array([r[f] for r in table["draws"]]) for f in FIELDS}
    arrays.update({f"own_{f}": np.array(table["own"][f]) for f in FIELDS if f != "day"})
    np.savez(path, statistic=np.array(ident["name"]), statistic_id=np.array(ident["id"]),
             identity_json=np.array(json.dumps({k: table[k] for k in ("statistic_identity", "domain", "recording_day", "units")},
                                               sort_keys=True)), **arrays)


def load_draws(path, identity: dict) -> dict:
    """The draws of an NPZ written by save_draws, as {field: array}, with the own day's under own_<field>. Refused
    when the file names no statistic identity (an export from before readiness R5) or another one than `identity`."""
    with np.load(path, allow_pickle=False) as z:
        if "statistic_id" not in z.files or "identity_json" not in z.files:
            raise IncompleteUnit(f"{path} names no statistic identity")
        if str(z["statistic_id"]) != identity["id"]:
            raise IncompleteUnit(f"{path} holds draws of {str(z['statistic'])} {str(z['statistic_id'])[:12]}, "
                                 f"not {identity['name']} {identity['id'][:12]}")
        out = {k: z[k] for k in z.files if k not in ("identity_json",)}
        out.update(json.loads(str(z["identity_json"])))
        return out
