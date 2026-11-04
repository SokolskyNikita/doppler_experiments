"""Count population in the union of aircraft range spheres at sampled instants."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_KM = 6371.009
SCALE = (0.5, 1.0, 2.0)
PROXIES = {
    "piston single": ["CNA172", "PA28", "CNA182"],
    "piston multi": ["PA30", "BEC58P"],
    "turboprop single": ["CNA208"],
    "turboprop multi": ["CNA441", "PA42", "1900D", "ATR72", "DHC830"],
    "business jet": ["CIT3", "GV"],
    "regional jet": ["EMB175", "CRJ9-ER"],
    "narrowbody": ["737800", "7378MAX", "A320-211", "A320-232"],
    "heavy jet": ["767300", "777200"],
}
DIRECT = {
    "C172": "CNA172", "C182": "CNA182", "P28A": "PA28", "P28B": "PA28",
    "PA30": "PA30", "BE58": "BEC58P", "C208": "CNA208", "PA42": "PA42",
    "C441": "CNA441", "B190": "1900D", "AT72": "ATR72", "DH8C": "DHC830",
    "C650": "CIT3", "GLF5": "GV", "E75L": "EMB175", "E75S": "EMB175",
    "CRJ9": "CRJ9-ER", "B738": "737800", "B38M": "7378MAX",
    "B763": "767300", "B772": "777200",
}
REGIONAL = {"E135", "E145", "E170", "E75L", "E75S", "E190", "E195", "E290", "E295",
            "CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "ARJ1", "ARJ2", "ARJ8"}
NARROW = ("A31", "A32", "A19", "A20", "A21", "BCS", "B71", "B72", "B73", "B37",
          "B38", "B39", "B75", "MD8", "MD9", "DC9", "B70")


def classify(designator, row):
    if row is None:
        return "unknown"
    category = row.AircraftDescription
    engine = row.EngineType
    single = row.EngineCount == "1"
    if category in ("Helicopter", "Gyrocopter", "Tilt-wing"):
        if engine == "Piston":
            return "piston rotor"
        if engine == "Turboprop/Turboshaft":
            return "single turbine rotor" if single else "multi turbine rotor"
        return "unknown"
    if category not in ("LandPlane", "Amphibian", "SeaPlane"):
        return "other"
    if engine == "Piston":
        return "piston single" if single else "piston multi"
    if engine == "Turboprop/Turboshaft":
        return "turboprop single" if single else "turboprop multi"
    if engine != "Jet":
        return "other"
    if designator in REGIONAL:
        return "regional jet"
    if designator.startswith(NARROW):
        return "narrowbody"
    if row.WTC in ("H", "J"):
        return "heavy jet"
    return "business jet"


def lookup(designators, catalogue, radii, loss):
    models = radii[radii.indoor_loss_dB == loss].groupby(["model", "operation"]).radius_km.median().unstack()
    generic = {key: models.loc[examples, ["Approach", "Departure"]].median().values
               for key, examples in PROXIES.items()}
    for key, km in [("piston rotor", 0.33), ("single turbine rotor", 1.07),
                    ("multi turbine rotor", 2.6), ("unknown", 1.0), ("other", 0.0)]:
        generic[key] = (km, km)
    classes, approach, departure = [], [], []
    for code in designators:
        name = classify(code, catalogue.get(code))
        a, d = generic[name]
        if code in DIRECT:
            a, d = models.loc[DIRECT[code], ["Approach", "Departure"]]
        classes.append(name)
        approach.append(a)
        departure.append(d)
    return np.array(classes), np.array(approach), np.array(departure)


def xyz(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return EARTH_KM * np.column_stack((np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)))


class Homes:
    def __init__(self, census, terrain, zones):
        keep = (census.STATEFP != 72) & (census.POPULATION > 0)
        self.pop = census.POPULATION.values[keep].astype(np.int64)
        self.points = xyz(census.LATITUDE[keep], census.LONGITUDE[keep])
        self.ground = np.maximum(terrain["elevation_m"][keep], 0)
        self.geoid = terrain["geoid_separation_m"][keep]
        self.zones, self.zone_ids = np.unique(zones[keep], return_inverse=True)
        self.zone_pop = np.bincount(self.zone_ids, weights=self.pop)
        self.tree = cKDTree(self.points)

    def night_weights(self, epoch, spacing):
        timestamp = datetime.fromtimestamp(epoch, timezone.utc)
        local = [timestamp.astimezone(ZoneInfo(str(zone))) for zone in self.zones]
        seconds = np.array([t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6 for t in local])
        # The sample represents its centered time interval. Split intervals that straddle 6 or 22.
        lo, hi = seconds - spacing / 2, seconds + spacing / 2
        day_seconds = np.maximum(0, np.minimum(hi, 22 * 3600) - np.maximum(lo, 6 * 3600))
        return np.clip(1 - day_seconds / spacing, 0, 1)


def range_matches(fixes, homes, classes, approach, departure, scales):
    """Return resident indices, range ratios, and aircraft kinds for nearby aircraft."""
    codes = fixes.code.values
    rates = fixes.vertical_rate_mps.values
    # Geometric mean for level flight and missing vertical rate.
    radius = np.where(rates > 2, departure[codes],
                      np.where(rates < -2, approach[codes], np.sqrt(departure[codes] * approach[codes])))
    valid = np.isfinite(fixes.alt_m.values) & (fixes.alt_m.values < 5000 + 2000 * radius) & (radius > 0)
    subset = fixes[valid]
    radius = radius[valid]
    apoints = xyz(subset.lat.values, subset.lon.values)
    nearby = homes.tree.query_ball_point(apoints, max(scales) * radius)
    sizes = np.fromiter((len(ids) for ids in nearby), dtype=np.int64, count=len(nearby))
    if sizes.sum():
        b = np.concatenate(nearby[sizes > 0]).astype(np.intp, copy=False)
        a = np.repeat(np.arange(len(nearby)), sizes)
        ellipsoid = subset.alt_reference.values[a] == 1
        dz = (subset.alt_m.values[a] - homes.ground[b] - ellipsoid * homes.geoid[b]) / 1000
        dist = np.sqrt(((apoints[a] - homes.points[b])**2).sum(axis=1) + dz**2)
        ratio = dist / radius[a]
        kind = classes[subset.code.values[a]]
    else:
        b = np.empty(0, dtype=np.intp)
        ratio = np.empty(0)
        kind = np.empty(0, dtype=str)
    return b, ratio, kind


def score_instant(epoch, spacing, fixes, homes, classes, approach, departure, *, prop_only=False):
    scales = (1.0,) if prop_only else SCALE
    b, ratio, kind = range_matches(fixes, homes, classes, approach, departure, scales)
    night_zones = homes.night_weights(epoch, spacing)
    night_denom = np.dot(homes.zone_pop, night_zones)
    day_denom = homes.zone_pop.sum() - night_denom
    rows = []
    groups = {
        "props": np.isin(kind, ["piston single", "piston multi", "turboprop single", "turboprop multi"]),
        "fixed_wing": np.isin(kind, list(PROXIES)),
        "all_typed": kind != "unknown",
        "typed_or_untyped_1km": np.ones(len(kind), dtype=bool),
    }
    if prop_only:
        groups = {"props": groups["props"]}
    for group, eligible in groups.items():
        for scale in scales:
            inside = np.unique(b[eligible & (ratio <= scale)])
            night = night_zones[homes.zone_ids[inside]]
            pop = homes.pop[inside]
            night_total = np.dot(pop, night)
            rows.append((epoch, group, scale, pop.sum() - night_total, night_total, day_denom, night_denom))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("census", "terrain", "zones", "types", "radii", "fixes", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--fixed-wing-loss", choices=[5, 15, 25], default=15, type=int,
                        help="Indoor loss in dB. Alternative losses report only fixed-wing results.")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    homes = Homes(pd.read_csv(args.census), np.load(args.terrain), np.load(args.zones))
    assert homes.pop.sum() == 331449281
    types = pd.read_csv(args.types, dtype=str, keep_default_na=False)
    catalogue = {r.Designator:r for r in types.itertuples()}
    if args.fixes.suffix == ".npz":
        snapshot = np.load(args.fixes)
        spacing = 300
        epoch0 = int(datetime.fromisoformat(args.fixes.stem[:10]).replace(tzinfo=timezone.utc).timestamp())
        fixes = pd.DataFrame({k:snapshot[k] for k in ["lat", "lon", "alt_m", "vertical_rate_mps", "alt_reference", "type"]})
        fixes["epoch"] = epoch0 + snapshot["seconds"].astype("int64")
    else:
        spacing = 3600
        fixes = pd.read_csv(args.fixes, keep_default_na=False)
        fixes = fixes.rename(columns={"typ": "type", "utc_epoch": "epoch", "height_m": "alt_m"})
        fixes["vertical_rate_mps"] = pd.to_numeric(fixes.vertical_rate_fpm, errors="coerce") * 0.00508
        fixes["alt_reference"] = np.where(fixes.height_source == "geometric", 1, 2)
    # Refresh radii only when a distinct airframe designator appears.
    designators, codes = np.unique(fixes.type, return_inverse=True)
    fixes["code"] = codes
    classes, approach, departure = lookup(designators, catalogue, pd.read_csv(args.radii), args.fixed_wing_loss)
    scored = []
    instants = fixes.groupby("epoch")
    if len(instants) != 86400 // spacing:
        raise ValueError(f"Incomplete UTC sampling grid in {args.fixes} ({len(instants)} instants)")
    for epoch, frame in instants:
        scored.extend(score_instant(epoch, spacing, frame, homes, classes, approach, departure))
    out = pd.DataFrame(scored, columns=["epoch","group","scale","day","night","day_denom","night_denom"])
    if args.fixed_wing_loss != 15:
        out = out[out.group.isin(["props", "fixed_wing"]) & (out.scale == 1)]
    out.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
