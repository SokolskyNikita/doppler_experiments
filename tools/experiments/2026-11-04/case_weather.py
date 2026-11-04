"""The `weather` block of every bench case from the nearest airport's reading at the recording's midpoint.

For each case: the IEM ASOS stations of the networks around its reference point, sorted by distance; the
first with a report within 1 h of the midpoint gives the temperature, from the report nearest in time. The
temperature is the METAR's T group (0.1 C) when there is one, else IEM's tmpc. A station-day not already in
raw/aux/metar/ is fetched there as <ICAO>_<first day>.csv, the recording's UTC day and the days either side.
The midpoint is the recording start (the audio clock where the case has one) plus half its length; for the
day-long Eclipse recordings one reading stands for the day, and the day's range at that station is reported.
aircraft_height_m is the true flights' typical height above the ground at their CPA, set only when the
case has a true pair and the two agree within 30 %; otherwise null.

usage: uv run python tools/experiments/2026-11-04/case_weather.py RUN [--apply]
  RUN       a run folder: the station lists, the fetch log and weather.json go there
  --apply   write them into bench/cases.json (otherwise only weather.json). A change to a case is a new version
            of it, so each case's latest version stays as it is and a copy one version up carries the weather,
            with its own CPA cache file (the sound speed is part of the table's fingerprint): <name>_<T>C.npz
"""
import argparse
import copy
import csv
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from dopplertrack.adsb import load_traces
from dopplertrack.geo import haversine_m, lla_to_enu
from dopplertrack.terrain import Terrain

REPO = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
METAR = DATA / "raw/aux/metar"
IEM = "https://mesonet.agron.iastate.edu"
MAX_DT = 3600.0
# networks around each site; the recording's length in s where the case doesn't carry one
SITES = {
    "oyster-bay": (("NY_ASOS", "CT_ASOS", "NJ_ASOS"), 3600.0),
    "eagle-cam": (("FL_ASOS",), None),
    "eclipse-esid375": (("OH_ASOS", "IN_ASOS"), 2 * 12.4 * 3600),
    "eclipse-esid710": (("IL_ASOS",), 1437 * 60.0),
    "eclipse-esid740": (("IL_ASOS", "MO_ASOS", "KY_ASOS"), 1437 * 60.0),
    "eclipse-esid937": (("MO_ASOS", "IL_ASOS", "KY_ASOS", "AR_ASOS", "TN_ASOS"), 2 * 12.4 * 3600),
    "xenocanto-xc979185": (("GB__ASOS",), 33 * 60.0),
    "xenocanto-xc990819": (("GB__ASOS",), 92 * 60.0),
    "xenocanto-xc990820": (("GB__ASOS",), 61 * 60.0),
    "xenocanto-xc986433": (("GB__ASOS",), 46 * 60.0),
}
SITE_OF = {"oyster-bay-moved-wsw150": "oyster-bay", "oyster-bay-hp150-aac32k": "oyster-bay",
           "oyster-bay-moved-north150": "oyster-bay", "eagle-cam-clip-18000s": "eagle-cam"}


def get(url, out):
    for k in range(6):
        r = subprocess.run(["curl", "-sS", "-w", "%{http_code}", "-o", str(out), url], capture_output=True, text=True)
        if r.stdout.strip() == "200":
            return
        time.sleep(10 * (k + 1))
    raise RuntimeError(f"{url}: HTTP {r.stdout.strip()} {r.stderr.strip()}")


def stations(run, networks):
    out = []
    for n in networks:
        f = run / "stations" / f"{n}.geojson"
        if not f.exists():
            f.parent.mkdir(exist_ok=True)
            get(f"{IEM}/geojson/network/{n}.geojson", f); time.sleep(2)
        for s in json.load(open(f))["features"]:
            p = s["properties"]; lon, lat = s["geometry"]["coordinates"]
            sid = p["sid"]
            icao = sid if len(sid) == 4 else "K" + sid
            out.append(dict(sid=sid, icao=icao, name=p.get("sname"), lat=lat, lon=lon, elev=p.get("elevation"), network=n))
    return out


def readings(run, st, day, log):
    """The station's reports for day-1..day+1: from a file already in raw/ that covers them, else fetched."""
    first = (day - timedelta(days=1)).strftime("%Y-%m-%d")
    f = METAR / f"{st['icao']}_{first}.csv"
    if not f.exists():
        a, b = day - timedelta(days=1), day + timedelta(days=2)
        url = (f"{IEM}/cgi-bin/request/asos.py?station={st['sid']}&data=tmpc&data=metar&year1={a.year}&month1={a.month}&day1={a.day}"
               f"&year2={b.year}&month2={b.month}&day2={b.day}&tz=Etc/UTC&format=onlycomma&latlon=yes&elev=yes&missing=M&trace=T"
               f"&direct=no&report_type=3&report_type=4")
        tmp = run / "stage" / f.name
        tmp.parent.mkdir(exist_ok=True)
        get(url, tmp); time.sleep(2)
        if sum(1 for _ in open(tmp)) <= 1:
            log.append(dict(station=st["icao"], day=str(day), url=url, rows=0, kept="no (empty)"))
            return []
        os.replace(tmp, f)
        log.append(dict(station=st["icao"], day=str(day), url=url, file=str(f.relative_to(DATA)), kept="yes"))
    out = []
    for r in csv.DictReader(open(f)):
        t = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
        m = re.search(r"\sT([01])(\d{3})([01])(\d{3})", r.get("metar") or "")
        if m:
            temp, basis = (-1 if m.group(1) == "1" else 1) * int(m.group(2)) / 10, "METAR T group"
        elif r.get("tmpc") not in (None, "", "M"):
            temp, basis = float(r["tmpc"]), "IEM tmpc"
        elif r.get("tmpf") not in (None, "", "M"):
            temp, basis = (float(r["tmpf"]) - 32) * 5 / 9, "IEM tmpf"
        else:
            continue
        out.append((t, temp, basis, r["valid"], str(f.relative_to(DATA))))
    return out


def midpoint(case, site, clocks):
    """clocks: the audio clock of each site's base case, for variants of its audio that carry none."""
    rc = (case.get("reference_clock_utc") or {}).get("audio_zero_utc_unix_s")
    if rc is None and (case.get("audio") or {}).get("duration_s") is None:
        rc = clocks.get(site)
    t0 = rc if rc is not None else datetime.fromisoformat(case["start_time"]["utc"].replace("Z", "+00:00")).timestamp()
    length = (case.get("audio") or {}).get("duration_s") or SITES[site][1]
    return t0, length, t0 + length / 2


def true_heights(case):
    """The true flights' height above the ground at their CPA to the reference point, metres."""
    pair = (case.get("labels") or {}).get("true_pair")
    ref = (case.get("labels") or {}).get("reference")
    if not pair or not ref:
        return None
    trs = load_traces(DATA / case["flight_data"]["traces"])
    ground = float(Terrain().elevation(np.array([ref["lat"]]), np.array([ref["lon"]]))[0])
    out = []
    for h in pair:
        tr = [t for t in trs if t.icao == h]
        lat = np.concatenate([t.lat for t in tr]); lon = np.concatenate([t.lon for t in tr]); alt = np.concatenate([t.alt for t in tr])
        ok = np.isfinite(alt)
        enu = lla_to_enu(lat[ok], lon[ok], alt[ok], ref["lat"], ref["lon"], ground)
        k = int(np.argmin(np.linalg.norm(enu, axis=1)))
        out.append(float(enu[k, 2]))
    return out


def main(run, apply):
    cases_path = REPO / "bench/cases.json"
    doc = json.load(open(cases_path))
    log, out, cases = [], {}, []
    latest = {}
    for c in doc["cases"]:
        latest[c["id"]] = max(latest.get(c["id"], 0), c["version"])
    clocks = {c["id"]: (c.get("reference_clock_utc") or {}).get("audio_zero_utc_unix_s") for c in doc["cases"] if c["id"] == "oyster-bay"}
    for case in doc["cases"]:
        cases.append(case)
        if case["version"] != latest[case["id"]] or (case.get("weather") or {}).get("temperature_c") is not None:
            continue
        site = SITE_OF.get(case["id"]) or next((k for k in ("oyster-bay", "eagle-cam") if case["id"].startswith(k)), case["id"])
        ref = case["labels"]["reference"]
        t0, length, tm = midpoint(case, site, clocks)
        day = datetime.fromtimestamp(tm, timezone.utc).date()
        cand = sorted(stations(run, SITES[site][0]), key=lambda s: haversine_m(ref["lat"], ref["lon"], s["lat"], s["lon"]))
        pick = None
        for st in cand[:8]:
            rs = readings(run, st, day, log)
            if not rs:
                continue
            k = int(np.argmin([abs(r[0] - tm) for r in rs]))
            if abs(rs[k][0] - tm) <= MAX_DT:
                in_rec = [r[1] for r in rs if t0 <= r[0] <= t0 + length]
                pick = dict(st=st, r=rs[k], dist=haversine_m(ref["lat"], ref["lon"], st["lat"], st["lon"]) / 1e3,
                            range_c=(min(in_rec), max(in_rec)) if in_rec else None, n_in_rec=len(in_rec))
                break
        if pick is None:
            out[case["id"]] = dict(error="no station within the first 8 has a report within 1 h of the midpoint")
            continue
        hs = true_heights(case)
        height = None
        if hs and min(hs) > 0 and max(hs) / min(hs) <= 1.3:
            height = float(round(np.mean(hs) / 10) * 10)
        st, r = pick["st"], pick["r"]
        w = dict(temperature_c=r[1], source=f"IEM ASOS ({r[2]}), {r[4]}", station=f"{st['icao']} {st['name']}",
                 station_distance_km=round(pick["dist"], 1),
                 observed_utc=datetime.fromtimestamp(r[0], timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), aircraft_height_m=height)
        out[case["id"]] = dict(weather=w, midpoint_utc=datetime.fromtimestamp(tm, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               length_s=length, report_minus_midpoint_s=r[0] - tm, station_elev_m=st["elev"],
                               recording_range_c=pick["range_c"], reports_in_recording=pick["n_in_rec"], true_heights_m=hs)
        print(case["id"], json.dumps(out[case["id"]], default=float))
        if apply:
            v = copy.deepcopy(case)
            v["version"] += 1
            v["weather"] = w
            cache = (v.get("search") or {}).get("cpa_cache")
            if cache:
                v["search"]["cpa_cache"] = cache.removesuffix(".npz") + f"_{w['temperature_c']:g}C.npz"
            cases.append(v)
    doc["cases"] = cases
    json.dump(dict(cases=out, fetched=log), open(run / "weather.json", "w"), indent=1, default=float)
    if apply:
        with open(cases_path, "w") as fh:
            json.dump(doc, fh, indent=1); fh.write("\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("run", type=Path); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    main(a.run, a.apply)
