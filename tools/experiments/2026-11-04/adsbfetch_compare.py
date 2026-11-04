"""Part 2 of the adsbfetch comparison: the true flights of the two development recordings and eight
Livermore passes, per free mirror, their union, and our reference track.

For each flight, around its emission CPA at the true point (development: the CPA of our adsb.lol cut's
trace at the known microphone; Livermore: the audit's emission CPA at the reconstructed one):
  points within +-60 s, the largest gap within +-60 s (counting the stretch to the first point outside
  the window on each side), and the horizontal distance from each source's positions to the reference
  track's, linearly interpolated between reference points at most 25 s apart.
References: our adsb.lol tar cut (derived/oyster_bay/traces_ny.npz, derived/swfl/traces_swfl.npz) and,
for Livermore, the author's KML (positions only). Traces come from the fixed adsbfetch's rows in traces2/
(fetched per source into separate caches; tools/data/adsbfetch_to_npz.from_fixed_rows), to the millisecond.

usage: uv run python tools/experiments/2026-11-04/adsbfetch_compare.py "$RUN" [--adsbx DIR]
  --adsbx DIR: also adsbx's rows from DIR/traces2/, a row of their own and a "union with adsbx" beside the
  free mirrors' union
"""
import argparse
import csv
import importlib.util
import json
from datetime import date
from pathlib import Path

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.geo import haversine_m, lla_to_enu

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location("conv", REPO / "tools/data/adsbfetch_to_npz.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
spec = importlib.util.spec_from_file_location("audit", HERE / "livermore_audit.py")
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
DATA = Path.home() / "data" / "dopplertrack"
MIRRORS = ("adsbfi", "airplaneslive", "adsblol")
HALF = 60.0
DEV = [("ob", "a1dfeb", date(2026, 9, 8), DATA / "derived/oyster_bay/traces_ny.npz", (40.876466, -73.524951)),
       ("ob", "ace391", date(2026, 9, 8), DATA / "derived/oyster_bay/traces_ny.npz", (40.876466, -73.524951)),
       ("swfl", "a2baea", date(2024, 12, 28), DATA / "derived/swfl/traces_swfl.npz", (26.702359, -81.847766)),
       ("swfl", "a336e4", date(2024, 12, 28), DATA / "derived/swfl/traces_swfl.npz", (26.702359, -81.847766))]


def mirror(hex_, day, src, folder):
    """One source's trace from the fixed adsbfetch's rows (traces2/<tag>_<hex>_<source>.jsonl), or None."""
    files = list(folder.glob(f"*_{hex_}_{src}.jsonl"))
    rows = [json.loads(line) for f in files for line in open(f) if line.strip()]
    return conv.from_fixed_rows(rows, hex_) if rows else None


def stats(t, lat, lon, tc, ref=None):
    t = np.asarray(t); order = np.argsort(t); t = t[order]; lat = np.asarray(lat)[order]; lon = np.asarray(lon)[order]
    inside = np.abs(t - tc) <= HALF
    out = dict(points=int(inside.sum()))
    before, after = t[t < tc - HALF], t[t > tc + HALF]
    edges = np.r_[before[-1:] if len(before) else [tc - HALF], t[inside], after[:1] if len(after) else [tc + HALF]]
    out["max_gap_s"] = float(np.diff(edges).max()) if len(edges) > 1 else 2 * HALF
    if ref is not None and inside.any():
        rt, rlat, rlon = ref
        k = np.searchsorted(rt, t[inside])
        ok = (k > 0) & (k < len(rt))
        k = k[ok]; ti = t[inside][ok]
        near = rt[k] - rt[k - 1] <= 25.0        # bracketed by reference points at most 25 s apart
        if near.any():
            w = (ti[near] - rt[k - 1][near]) / (rt[k][near] - rt[k - 1][near])
            la = rlat[k - 1][near] + w * (rlat[k][near] - rlat[k - 1][near])
            lo = rlon[k - 1][near] + w * (rlon[k][near] - rlon[k - 1][near])
            d = haversine_m(lat[inside][ok][near], lon[inside][ok][near], la, lo)
            out.update(pos_median_m=float(np.median(d)), pos_p95_m=float(np.percentile(d, 95)), pos_n=int(near.sum()))
    return out


def union_rows(got, adsbx, **row):
    """The free mirrors' union, and with adsbx's trace too when there is one."""
    free = [tr for src, tr in got if src != "adsbx"]
    out = [dict(row, source="mirror union", tr=conv.merge(free))] if free else []
    if any(src == "adsbx" for src, _ in got):
        out.append(dict(row, source="union with adsbx", tr=conv.merge([tr for _, tr in got])))
    return out


def main(run: Path, adsbx: Path | None = None):
    folders = {src: run / "traces2" for src in MIRRORS}
    if adsbx:
        folders["adsbx"] = adsbx / "traces2"
    rows = []
    for site, hex_, day, cut_path, point in DEV:
        cut = [tr for tr in load_traces(cut_path) if tr.icao == hex_]
        ct = np.concatenate([tr.t for tr in cut]); clat = np.concatenate([tr.lat for tr in cut]); clon = np.concatenate([tr.lon for tr in cut])
        calt = np.concatenate([tr.alt for tr in cut]); o = np.argsort(ct)
        ct, clat, clon, calt = ct[o], clat[o], clon[o], calt[o]
        enu = lla_to_enu(clat, clon, np.nan_to_num(calt), point[0], point[1], 0.0)
        tc = float(ct[np.nanargmin(np.linalg.norm(enu, axis=1))])
        ref = (ct, clat, clon)
        rows.append(dict(site=site, hex=hex_, source="adsblol-tar (our cut)", tc=tc, **stats(ct, clat, clon, tc)))
        got = []
        for src, folder in folders.items():
            tr = mirror(hex_, day, src, folder)
            if tr is None:
                rows.append(dict(site=site, hex=hex_, source=src, tc=tc, points=0, error="no track")); continue
            got.append((src, tr))
            rows.append(dict(site=site, hex=hex_, source=src, tc=tc, **stats(tr.t, tr.lat, tr.lon, tc, ref)))
        for r in union_rows(got, adsbx, site=site, hex=hex_, tc=tc):
            u = r.pop("tr"); rows.append(dict(r, **stats(u.t, u.lat, u.lon, tc, ref)))
        uc = conv.merge([tr for src, tr in got if src != "adsbx"] + cut)
        rows.append(dict(site=site, hex=hex_, source="union with our cut", tc=tc, **stats(uc.t, uc.lat, uc.lon, tc, ref)))
    audit_rows = {r["id"]: r for r in csv.DictReader(open(DATA / "runs/2026-11-04-livermore-audit/passes.csv"))}
    nn_spec = importlib.util.spec_from_file_location("nn", REPO / "tools/data/nnumber.py")
    nn = importlib.util.module_from_spec(nn_spec); nn_spec.loader.exec_module(nn)
    passes = {p["id"]: p for p in audit.load_passes()}
    for pid in sorted(audit_rows, key=lambda k: -float(audit_rows[k]["max_kml_gap_s"]))[:8]:
        a = audit_rows[pid]; p = passes[pid]
        hex_ = nn.icao(pid.split("_")[0]); day = date.fromisoformat(a["day"])
        tc = float(a["emit_cpa_utc"])
        kt, klat, klon = p["track"][:, 0], p["track"][:, 1], p["track"][:, 2]
        ref = (kt, klat, klon)
        rows.append(dict(site="livermore", hex=hex_, id=pid, source="KML (author)", tc=tc, **stats(kt, klat, klon, tc)))
        got = []
        for src, folder in folders.items():
            tr = mirror(hex_, day, src, folder)
            if tr is None:
                rows.append(dict(site="livermore", hex=hex_, id=pid, source=src, tc=tc, points=0, error="no track")); continue
            got.append((src, tr))
            rows.append(dict(site="livermore", hex=hex_, id=pid, source=src, tc=tc, **stats(tr.t, tr.lat, tr.lon, tc, ref)))
        for r in union_rows(got, adsbx, site="livermore", hex=hex_, id=pid, tc=tc):
            u = r.pop("tr"); rows.append(dict(r, **stats(u.t, u.lat, u.lon, tc, ref)))
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(run / "compare_flights.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(f"{r['site']:9s} {r.get('id', r['hex']):12s} {r['source']:22s} pts {r.get('points', 0):4d}  gap {r.get('max_gap_s', float('nan')):5.1f} s  "
              f"pos {r.get('pos_median_m', float('nan')):6.1f} / {r.get('pos_p95_m', float('nan')):6.1f} m {r.get('error', '')}")
    json.dump(rows, open(run / "compare_flights.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("run", type=Path); ap.add_argument("--adsbx", type=Path)
    a = ap.parse_args()
    main(a.run, a.adsbx)
