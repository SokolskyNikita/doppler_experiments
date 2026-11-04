"""The refetch's headline: per development case, each source and the unions against our adsb.lol tar cut and
against the morning's fetch (runs/2026-11-04-adsbfetch), in percent; then, per source, how many of the
morning's traces the refetch changed.

Per case and source:
  window aircraft   propeller and unknown-type hexes seen in the source's box replay during the recording
                    +-30 min (adsbfetch_window.py's rule); for the cut, its traces of those types with a point
                    in the box in that time
  trace points      every point of those aircraft's day traces inside the case box (our cut is a box cut, so
                    the mirrors' day traces are clipped to the same box)
  at CPA            the true flights' points within +-60 s of CPA and the largest gap there, from
                    compare_flights.json (adsbfetch_compare.py), summed and maximised over the case's two flights
  only here / only in the cut   window hexes the source has that the cut lacks, and the reverse
The unions: "free union" merges adsbfi and airplanes.live (the morning's union), "free union + adsblol" adds
adsb.lol where it has the day, "four-mirror union" adds adsbx. A trace changed when its set of (time to the
ms, lat, lon to 1e-6 deg, height to 0.1 m) points differs; the share of points changed is the symmetric
difference over the union of the two point sets, summed over traces.

usage: uv run python tools/experiments/2026-11-04/adsbfetch_refetch_summary.py NEW_RUN ADSBX_RUN [OLD_RUN]
"""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dopplertrack.adsb import AircraftTypes, load_traces

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location("conv", REPO / "tools/data/adsbfetch_to_npz.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
DATA = Path.home() / "data" / "dopplertrack"
OLD_DEFAULT = DATA / "runs/2026-11-04-adsbfetch"
PAD = 1800.0
CASES = {"ny": dict(start="2026-09-08T20:17:30Z", length=3600.0, box=(40.4, 41.3, -74.4, -72.6), cut=DATA / "derived/oyster_bay/traces_ny.npz",
                    compare_site="ob", flights=("a1dfeb", "ace391")),
         "swfl": dict(start="2024-12-28T19:21:08Z", length=5400.0, box=(26.1, 27.3, -82.5, -81.2), cut=DATA / "derived/swfl/traces_swfl.npz",
                      compare_site="swfl", flights=("a2baea", "a336e4"))}
FREE = ("adsbfi", "airplaneslive", "adsblol")
UNIONS = {"free union": ("adsbfi", "airplaneslive"), "free union + adsblol": FREE, "four-mirror union": FREE + ("adsbx",)}


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()


def replay_window(path, t0, t1, types):
    if not path.exists():
        return None
    out = set()
    for line in open(path):
        r = json.loads(line)
        if t0 <= utc(r["ts"]) <= t1 and types.is_prop(r.get("type_code")):
            out.add(r["hex"].lower())
    return out


def rows_trace(path, hex_):
    rows = [json.loads(line) for line in open(path) if line.strip()] if path.exists() else []
    if not rows:
        return None, "empty"
    if "ts_epoch" not in rows[0]:
        return None, "old schema"
    return conv.from_fixed_rows(rows, hex_), "ok"


def in_box(tr, box):
    s, n, w, e = box
    return (tr.lat >= s) & (tr.lat <= n) & (tr.lon >= w) & (tr.lon <= e)


def points_set(tr):
    alt = np.where(np.isfinite(tr.alt), np.round(tr.alt, 1), -1e9)
    return set(zip(np.round(tr.t, 3), np.round(tr.lat, 6), np.round(tr.lon, 6), alt))


def pct(a, b):
    return None if not b else 100.0 * (a - b) / b


def source_traces(folder, site, hexes, src):
    out = {}
    for h in hexes:
        tr, _ = rows_trace(folder / f"{site}_{h.lstrip('~')}_{src}.jsonl", h)
        if tr is not None and len(tr.t):
            out[h] = tr
    return out


def cpa_numbers(compare, site, flights, source):
    rs = [r for r in compare if r["site"] == site and r["hex"] in flights and r["source"] == source]
    if len(rs) < len(flights):
        return None
    return dict(points=sum(r.get("points", 0) for r in rs), max_gap_s=max(r.get("max_gap_s", 120.0) for r in rs))


def case(site, c, new, adsbx, old, types):
    t0, t1 = utc(c["start"]) - PAD, utc(c["start"]) + c["length"] + PAD
    cut = [tr for tr in load_traces(c["cut"]) if types.is_prop(tr.typ)]
    cut_w = {}
    for tr in cut:
        m = in_box(tr, c["box"]) & (tr.t >= t0) & (tr.t <= t1)
        if m.any():
            cut_w.setdefault(tr.icao.lower(), []).append(tr)
    cut_points = sum(int(in_box(tr, c["box"]).sum()) for v in cut_w.values() for tr in v)
    folders = {s: new / "wtraces2" for s in FREE} | {"adsbx": adsbx / "wtraces2"}
    replays = {s: new / f"replay/{site}_{s}.jsonl" for s in FREE} | {"adsbx": adsbx / f"replay/{site}_adsbx.jsonl"}
    cmp_new = json.load(open(new / "compare_flights.json"))
    cmp_old = json.load(open(old / "compare_flights.json"))
    cut_cpa = cpa_numbers(cmp_new, c["compare_site"], c["flights"], "adsblol-tar (our cut)")
    win, trs, out = {}, {}, {}
    for s in folders:
        w = replay_window(replays[s], t0, t1, types)
        if not w:
            continue
        win[s] = w
        trs[s] = source_traces(folders[s], site, w, s)
    for name, members in UNIONS.items():
        have = [s for s in members if s in win]
        if len(have) < 2 or (name == "free union + adsblol" and "adsblol" not in have) or (name == "four-mirror union" and "adsbx" not in have):
            continue
        win[name] = set().union(*(win[s] for s in have))
        trs[name] = {h: conv.merge([trs[s][h] for s in have if h in trs[s]]) for h in win[name] if any(h in trs[s] for s in have)}
    old_win = {s: replay_window(old / f"replay/{site}_{s}.jsonl", t0, t1, types) for s in FREE}
    old_win = {s: w for s, w in old_win.items() if w}
    old_trs = {s: source_traces(old / "wtraces2", site, old_win[s], s) for s in ("adsbfi", "airplaneslive") if s in old_win}
    if len(old_trs) == 2:
        old_win["free union"] = old_win["adsbfi"] | old_win["airplaneslive"]
        old_trs["free union"] = {h: conv.merge([old_trs[s][h] for s in old_trs if h in old_trs[s]])
                                 for h in old_win["free union"] if any(h in old_trs[s] for s in ("adsbfi", "airplaneslive"))}
    cpa_label = {"free union + adsblol": "mirror union", "four-mirror union": "union with adsbx"}
    for s in win:
        pts = sum(int(in_box(tr, c["box"]).sum()) for tr in trs[s].values())
        cpa = cpa_numbers(cmp_new, c["compare_site"], c["flights"], cpa_label.get(s, s))
        # the morning's "mirror union" in part 2 merged the three free mirrors
        cpa_o = cpa_numbers(cmp_old, c["compare_site"], c["flights"], cpa_label.get(s, s)) if s != "adsbx" else None
        o_pts = sum(int(in_box(tr, c["box"]).sum()) for tr in old_trs[s].values()) if s in old_trs else None
        out[s] = dict(window_aircraft=len(win[s]), window_vs_cut_pct=pct(len(win[s]), len(cut_w)),
                      window_vs_morning_pct=pct(len(win[s]), len(old_win[s])) if s in old_win else None,
                      traced_aircraft=len(trs[s]), box_points=pts, points_vs_cut_pct=pct(pts, cut_points),
                      points_vs_morning_pct=pct(pts, o_pts) if o_pts is not None else None,
                      cpa=cpa, cpa_points_vs_cut_pct=pct(cpa["points"], cut_cpa["points"]) if cpa and cut_cpa else None,
                      cpa_points_vs_morning_pct=pct(cpa["points"], cpa_o["points"]) if cpa and cpa_o else None,
                      cpa_morning=cpa_o, only_here=len(set(trs[s]) - set(cut_w)), only_in_cut=len(set(cut_w) - set(trs[s])),
                      only_here_hexes=sorted(set(trs[s]) - set(cut_w)), only_in_cut_hexes=sorted(set(cut_w) - set(trs[s])))
    return dict(cut=dict(window_aircraft=len(cut_w), box_points=cut_points, cpa=cut_cpa), sources=out)


def changed(new, old):
    """Per source, the morning's windowed and true-flight traces against the refetch's copy of the same trace."""
    out = {}
    for s in ("adsbfi", "airplaneslive", "adsblol"):
        n = same = diff = only_old = only_new = old_schema = 0
        sym = tot = 0
        for sub in ("wtraces2", "traces2"):
            for f in sorted((old / sub).glob(f"*_{s}.jsonl")):
                g = new / sub / f.name
                hex_ = f.stem.split("_")[1]
                a, sa = rows_trace(f, hex_); b, sb = rows_trace(g, hex_) if g.exists() else (None, "missing")
                if "old schema" in (sa, sb):
                    old_schema += 1; continue
                if a is None and b is None:
                    continue
                n += 1
                if a is None:
                    only_new += 1; continue
                if b is None:
                    only_old += 1; continue
                pa, pb = points_set(a), points_set(b)
                sym += len(pa ^ pb); tot += len(pa | pb)
                same += pa == pb; diff += pa != pb
        out[s] = dict(traces_compared=n, identical=same, changed=diff, only_morning=only_old, only_refetch=only_new,
                      old_schema_skipped=old_schema, points_changed_pct=100.0 * sym / tot if tot else None)
    return out


def main(new: Path, adsbx: Path, old: Path):
    types = AircraftTypes()
    out = {site: case(site, c, new, adsbx, old, types) for site, c in CASES.items()}
    out["changed_vs_morning"] = changed(new, old)
    json.dump(out, open(new / "headline.json", "w"), indent=1, default=float)
    f = lambda v, d=1: "–" if v is None else f"{v:+.{d}f} %"
    for site in CASES:
        cut = out[site]["cut"]
        print(f"\n{site}: cut {cut['window_aircraft']} window aircraft, {cut['box_points']} box points, CPA {cut['cpa']}")
        for s, r in out[site]["sources"].items():
            cpa = r["cpa"] or {}
            print(f"  {s:22s} win {r['window_aircraft']:4d} ({f(r['window_vs_cut_pct'])} cut, {f(r['window_vs_morning_pct'])} morning)  "
                  f"pts {r['box_points']:8d} ({f(r['points_vs_cut_pct'])}, {f(r['points_vs_morning_pct'])})  "
                  f"cpa {cpa.get('points', '–')} ({f(r['cpa_points_vs_cut_pct'])}, {f(r['cpa_points_vs_morning_pct'])}) gap {cpa.get('max_gap_s', float('nan')):.1f}  "
                  f"only here {r['only_here']} / only cut {r['only_in_cut']}")
    print(json.dumps(out["changed_vs_morning"], indent=1, default=float))


if __name__ == "__main__":
    a = [Path(x) for x in sys.argv[1:]]
    main(a[0], a[1], a[2] if len(a) > 2 else OLD_DEFAULT)
