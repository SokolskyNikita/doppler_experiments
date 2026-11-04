"""Checks the adsbfetch 0.3.7 outputs against the record's criteria (docs/experiments/2026-11-05-adsbfetch-0-3-7.md).

For each site: every aircraft's minimum 3D distance to the --near point over its in-window positions, recomputed from
the unfiltered output (the preserved observations where that run exists, since the tool qualifies on unmerged rows),
twice: with the tool's own formula (spherical great circle, hypot with the height difference) and in WGS-84 ECEF. Then
the --near sets against it, the single networks' union against the four-network set, the in-radius witness in every
kept track, --preserve-observations, --props-only, the altitude fields, and each call's requests from its manifest.

usage: uv run python tools/experiments/2026-11-05/adsbfetch_check.py RUN
"""
import datetime
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

SITES = {
    "ob": dict(window=("2026-09-08T20:45:00Z", "2026-09-08T21:15:00Z"), near=(40.876466, -73.524951, -30.0),
               truth=["a1dfeb", "ace391"]),
    "eg": dict(window=("2024-12-28T19:50:00Z", "2024-12-28T20:10:00Z"), near=(26.702359, -81.847766, -22.0),
               truth=["a2baea", "a336e4"]),
    "ec": dict(window=("2024-04-07T01:39:34Z", "2024-04-07T02:09:34Z"), near=(40.7831545, -84.0028968, 250.0), truth=[]),
    "ex": dict(window=("2025-04-20T04:10:00Z", "2025-04-20T04:40:00Z"), near=(51.6483, 0.4953, 103.0), truth=[]),
}
NETS = ["adsbfi", "airplaneslive", "adsblol", "adsbx"]
A, F = 6378137.0, 1 / 298.257223563


def epoch(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load(path):
    out = {}
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out.setdefault(r.get("hex"), []).append(r)
    return out


def ecef(lat, lon, h):
    e2 = F * (2 - F)
    la, lo = np.radians(lat), np.radians(lon)
    n = A / np.sqrt(1 - e2 * np.sin(la) ** 2)
    return np.stack([(n + h) * np.cos(la) * np.cos(lo), (n + h) * np.cos(la) * np.sin(lo), (n * (1 - e2) + h) * np.sin(la)], -1)


def height(r):
    for k in ("alt_geom_m", "alt_baro_m"):
        v = r.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            return float(v), k
    return None, None


def min_dist(rows, near, w):
    """(tool's km, ECEF km, the height kind at the tool's minimum, ts, whether any in-window point lacked height)."""
    best, best_e, kind, ts, unknown = None, None, None, None, False
    p0 = ecef(near[0], near[1], near[2])
    for r in rows:
        if not (w[0] <= r["ts_epoch"] < w[1]) or not isinstance(r.get("lat"), (int, float)):
            continue
        h, k = height(r)
        if h is None:
            unknown = True
            continue
        phi1, phi2 = math.radians(r["lat"]), math.radians(near[0])
        a = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(near[1] - r["lon"]) / 2) ** 2
        horiz = 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(a)))
        d = math.hypot(horiz, (h - near[2]) / 1000)
        de = float(np.linalg.norm(ecef(r["lat"], r["lon"], h) - p0)) / 1000
        if best is None or d < best:
            best, kind, ts = d, k, r["ts"]
        best_e = de if best_e is None else min(best_e, de)
    return best, best_e, kind, ts, unknown


def manifest(path):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
    summ = next((r for r in rows if r.get("summary")), {})
    reqs = [r for r in rows if not r.get("summary")]
    kinds = Counter((r.get("status") or r.get("outcome") or r.get("result") or "?", r.get("host") or r.get("source") or "?") for r in reqs)
    return dict(summary={k: summ.get(k) for k in ("ok", "cached", "validated", "absent", "failed", "bytes")},
                requests=len(reqs), by_kind={f"{k[0]}@{k[1]}": v for k, v in kinds.items()}), reqs


def baro_slack(rows_by_hex, w):
    d = [r["alt_geom_m"] - r["alt_baro_m"] for rows in rows_by_hex.values() for r in rows
         if w[0] <= r["ts_epoch"] < w[1] and isinstance(r.get("alt_geom_m"), (int, float)) and isinstance(r.get("alt_baro_m"), (int, float))]
    return (float(np.median(d)), float(np.percentile(np.abs(d), 95))) if d else (None, None)


def site(run, s, cfg):
    out = run / "out"
    w = (epoch(cfg["window"][0]), epoch(cfg["window"][1]))
    base = load(out / f"{s}_all_preserve.jsonl") or load(out / f"{s}_all.jsonl")
    if base is None:
        return None
    rep = dict(base="preserve" if (out / f"{s}_all_preserve.jsonl").exists() else "merged", aircraft=len(base))
    med, p95 = baro_slack(base, w)
    rep["geom_minus_baro_m"] = dict(median=med, p95_abs=p95)
    slack_km = (p95 or 0) / 1000
    dist = {h: min_dist(rows, cfg["near"], w) for h, rows in base.items()}
    rep["formula_vs_ecef_max_m"] = max([abs(d[0] - d[1]) * 1000 for d in dist.values() if d[0] is not None], default=None)
    for rad in (4, 10):
        got = load(out / f"{s}_near{rad}.jsonl")
        if got is None:
            continue
        want = {h for h, d in dist.items() if d[0] is not None and d[0] <= rad}
        miss, extra = sorted(want - set(got)), sorted(set(got) - want)
        boundary = lambda h: dist.get(h, (None,))[0] is not None and abs(dist[h][0] - rad) <= slack_km and dist[h][2] == "alt_baro_m"  # noqa: E731
        no_witness = [h for h, rows in got.items() if (min_dist(rows, cfg["near"], w)[0] or 1e9) > rad + 1e-9]
        rep[f"near{rad}"] = dict(n=len(got), expected=len(want), missing=[(h, dist.get(h)) for h in miss],
                                 extra=[(h, dist.get(h)) for h in extra], boundary=[h for h in miss + extra if boundary(h)],
                                 no_witness=no_witness, truth={t: (t in got, dist.get(t)) for t in cfg["truth"]},
                                 not_in_base=[h for h in got if h not in base])
    combined = load(out / f"{s}_near10.jsonl")
    singles = {n: load(out / f"{s}_near10_{n}.jsonl") for n in NETS}
    if combined is not None and all(v is not None for v in singles.values()):
        union = set().union(*[set(v) for v in singles.values()])
        rep["union_vs_combined"] = dict(union=len(union), combined=len(combined), lost=sorted(union - set(combined)),
                                        only_combined=sorted(set(combined) - union),
                                        per_net={n: len(v) for n, v in singles.items()})
    pres = load(out / f"{s}_near10_preserve.jsonl")
    if combined is not None and pres is not None:
        rep["preserve"] = dict(aircraft=(len(pres), len(combined)), same_set=set(pres) == set(combined),
                               rows=(sum(map(len, pres.values())), sum(map(len, combined.values()))),
                               equal_ts_rows=sum(len(r) - len({x["ts_epoch"] for x in r}) for r in pres.values()))
    props = load(out / f"{s}_near10_props.jsonl")
    if combined is not None and props is not None:
        dropped = sorted(set(combined) - set(props))
        info = {h: {k: combined[h][0].get(k) for k in ("type", "typ", "desc", "category", "engine", "class", "reg") if k in combined[h][0]}
                for h in dropped}
        rep["props_only"] = dict(kept=len(props), dropped=info, added=sorted(set(props) - set(combined)))
    alt = Counter()
    for rows in base.values():
        for r in rows:
            g, b = r.get("alt_geom_m"), r.get("alt_baro_m")
            alt[("geom" if g is not None else "-") + "/" + ("baro" if b is not None else "-") + f" is_geom={r.get('alt_is_geom')}"] += 1
    rep["alt_fields"] = dict(alt)
    return rep, dist


def main():
    run = Path(sys.argv[1])
    report = {}
    for s, cfg in SITES.items():
        r = site(run, s, cfg)
        if r:
            report[s] = r[0]
            (run / f"check_{s}_distances.json").write_text(json.dumps(r[1], indent=0, default=float))
    report["manifests"] = {p.stem: manifest(p)[0] for p in sorted((run / "manifests").glob("*.jsonl"))}
    (run / "check.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    print(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()
