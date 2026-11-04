"""Prepare a reproducible population-proportional resident sample and the earlier propeller radii."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from indoor_outdoor_coverage import required_spectra
from integration_coverage import load_homes, source_radii
from movement_pickup import model_levels
from residential_aircraft import lookup

parser = argparse.ArgumentParser(description=__doc__)
for item in ("residential_inputs", "acoustics_run", "anp", "catalogue", "destination"):
    parser.add_argument(item, type=Path)
args = parser.parse_args()
homes = load_homes(args.residential_inputs)
census = pd.read_csv(args.residential_inputs / "coverage-pop-CenPop2020_Mean_BG.txt")
included = (census.STATEFP != 72) & (census.POPULATION > 0)
region = np.load(args.acoustics_run / "inputs/large-cbsa.npy")[included]
rng = np.random.default_rng(750424)
res = rng.choice(len(homes.pop), 32768, p=homes.pop / homes.pop.sum())
np.savez_compressed(args.destination / "residents.npz", xyz=homes.points[res], region=region[res],
                    height=homes.ground[res]/1000, geoid=homes.geoid[res]/1000,
                    zones=homes.zones, zone_index=homes.zone_ids[res], site_index=res)
config = json.loads((args.acoustics_run / "acoustics.json").read_text())
levels = list(model_levels(args.anp))
table = pd.read_csv(args.catalogue, dtype=str, keep_default_na=False)
catalogue = {r.Designator:r for r in table.itertuples()}
types = np.array(sorted(catalogue))
# env 0 contributes no opportunity. Others are 1 + habitat + 3*day_noise + 6*large_CBSA.
radii = np.zeros((len(types), 3, 13))
spectra = required_spectra(config)
for large, prefix in enumerate(("r","u")):
    for day, period in enumerate(("night","day")):
        for habitat, setting in enumerate(("closed","open","outside")):
            model = source_radii(levels, spectra[f"{prefix}_{period}_main.{setting}"], "all")
            _, app, dep = lookup(types, catalogue, model, loss=15)
            radii[:, :, 1 + habitat + 3*day + 6*large] = np.column_stack([app, np.sqrt(app*dep), dep])
np.savez_compressed(args.destination / "radii.npz", types=types, radii=radii)
