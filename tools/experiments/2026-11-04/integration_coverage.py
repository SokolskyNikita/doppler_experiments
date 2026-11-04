"""Map a detector threshold, in dB below band equality, to U.S. propeller-plane proximity.

The "all" band option assumes the specified net margin is available in any modeled band.
A numbered band limits the source assumption and threshold to that one band. The U.S.
coverage calculation uses the earlier experiment's resident locations and the same 12 dates.
"""
import argparse
import io
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

import movement_pickup as sound
import residential_aircraft as coverage


def source_radii(levels, required_exterior_dB, band):
    selected = sound.BANDS == int(band) if band != "all" else np.ones(len(sound.BANDS), dtype=bool)
    absorption = np.array(sound.ABSORPTION)[selected]
    rows = []
    for model, mode, power, band_levels in levels:
        margins = (band_levels - required_exterior_dB)[selected]
        radii = [sound.crossing(m, a) for m, a in zip(margins, absorption)]
        rows.append((model, mode, power, 15, round(max(radii), 4)))
    return pd.DataFrame(rows, columns=["model", "operation", "power", "indoor_loss_dB", "radius_km"])


def load_homes(inputs):
    return coverage.Homes(pd.read_csv(inputs / "coverage-pop-CenPop2020_Mean_BG.txt"),
                           np.load(inputs / "coverage-dem-bg.npz"),
                           np.load(inputs / "coverage-tz-population-zones.npy"))


def prop_days(inputs, types_csv):
    catalogue = {r.Designator: r for r in pd.read_csv(types_csv, dtype=str, keep_default_na=False).itertuples()}
    props = {code for code, row in catalogue.items()
             if coverage.classify(code, row) in {"piston single", "piston multi", "turboprop single", "turboprop multi"}}
    # Read each source day once, keeping only types that could enter the propeller result.
    with tarfile.open(inputs / "public-2025-airborne-csv.tgz", "r|gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith("2025-") or not member.name.endswith("-standard.csv"):
                continue
            fixes = pd.read_csv(io.BytesIO(archive.extractfile(member).read()),
                                usecols=["typ", "utc_epoch", "lat", "lon", "height_m", "height_source", "vertical_rate_fpm"])
            fixes = fixes[fixes.typ.isin(props)].copy()
            fixes["alt_m"] = fixes.height_m
            fixes["alt_reference"] = np.where(fixes.height_source == "geometric", 1, 2)
            fixes["vertical_rate_mps"] = fixes.vertical_rate_fpm * 0.00508
            types, codes = np.unique(fixes.typ, return_inverse=True)
            fixes["code"] = codes
            by_instant = list(fixes.groupby("utc_epoch"))
            if len(by_instant) != 24:
                raise ValueError(f"Missing snapshots in {member.name}")
            yield catalogue, types, by_instant


def monthly_exposure(args, radii):
    homes = load_homes(args.inputs)
    scored = []
    for catalogue, types, by_instant in prop_days(args.inputs, args.types):
        for scenario, model in radii.items():
            classes, approach, departure = coverage.lookup(types, catalogue, model, loss=15)
            for epoch, positions in by_instant:
                result = coverage.score_instant(epoch, 3600, positions, homes, classes, approach, departure,
                                                prop_only=True)
                scored.append((scenario, *result[0]))
    frame = pd.DataFrame(scored, columns=["scenario", "epoch", "group", "scale", "day", "night", "day_denom", "night_denom"])
    if frame.epoch.nunique() != 288:
        raise ValueError("Expected 12 complete hourly UTC days")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("inputs", "types", "pilot", "anp", "output_prefix"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("scenario", nargs="+", help="Name, band (all or e.g. 160 Hz), net dB credit, comma-separated.")
    args = parser.parse_args()
    noise = sound.background(args.pilot)
    levels = list(sound.model_levels(args.anp))
    radii = {}
    for spec in args.scenario:
        name, band, credit = spec.split(",")
        if band != "all" and int(band) not in sound.BANDS:
            raise ValueError(f"Unknown band {band}")
        radii[name] = source_radii(levels, noise + 130 + 15 - float(credit), band)
    outputs = [args.output_prefix.with_name(args.output_prefix.name + suffix)
               for suffix in ("-radii.csv", "-snapshots.csv", "-pooled.csv")]
    if any(p.exists() for p in outputs):
        raise FileExistsError(args.output_prefix)
    frames = monthly_exposure(args, radii)
    sums = frames.groupby("scenario")[["day", "night", "day_denom", "night_denom"]].sum()
    pct = pd.DataFrame({"day_pct": 100 * sums.day / sums.day_denom,
                        "night_pct": 100 * sums.night / sums.night_denom,
                        "whole_pct": 100 * (sums.day + sums.night) / (sums.day_denom + sums.night_denom)})
    pd.concat(radii, names=["scenario", "row"]).to_csv(outputs[0])
    frames.to_csv(outputs[1], index=False)
    pct.to_csv(outputs[2])
    print(pct.round(4))


if __name__ == "__main__":
    main()
