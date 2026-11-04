"""Residential-centroid aircraft coverage with frequency-specific noise and hourly activity."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import integration_coverage as integration
import movement_pickup as sound
import residential_aircraft as coverage


def hourly_weights(epoch, zones):
    # One aircraft snapshot represents an hour centered on its actual time.
    local = [datetime.fromtimestamp(epoch, timezone.utc).astimezone(ZoneInfo(str(zone))) for zone in zones]
    center = np.array([t.hour + t.minute / 60 + (t.second + t.microsecond / 1e6) / 3600 for t in local])
    first = np.floor(center - 0.5).astype(int)
    second_weight = center - 0.5 - first
    weights = np.zeros((len(zones), 24))
    weights[np.arange(len(zones)), first % 24] = 1 - second_weight
    weights[np.arange(len(zones)), (first + 1) % 24] = second_weight
    return weights


def required_spectra(config):
    interior = np.asarray(config['interior_floor_dB'])
    required = {"old_15dB": interior + 15}
    # A passive facade attenuates both the aircraft and the exterior background.
    # In exterior SPL units, independent interior power is shifted UP by the facade loss.
    for site, outside in config['outdoor_floor_dB'].items():
        outside = np.asarray(outside)
        required[f"{site}.outside"] = outside
        for state, attenuation in config['facade_dB'].items():
            if state == 'outside':
                raise ValueError("outside is a reserved facade state")
            received = 10 ** ((interior + np.asarray(attenuation)) / 10) + 10 ** (outside / 10)
            required[f"{site}.{state}"] = 10 * np.log10(received)
    return required


def exposures(args, config):
    homes = integration.load_homes(args.inputs)
    census = pd.read_csv(args.inputs / "coverage-pop-CenPop2020_Mean_BG.txt")
    keep = (census.STATEFP != 72) & (census.POPULATION > 0)
    metro = np.load(args.metro)[keep].astype(bool)
    strata = ("small", "large")
    strata_zone = 2 * homes.zone_ids + metro
    levels = list(sound.model_levels(args.anp))
    radii = {}
    for name, external_threshold in required_spectra(config).items():
        radii[name] = integration.source_radii(levels, external_threshold - config['credit_dB'], "all")
    num = {name: np.zeros((2,24)) for name in radii}
    den = np.zeros(24)
    instants = 0
    for catalogue, types, by_instant in integration.prop_days(args.inputs, args.types):
        for epoch, _ in by_instant:
            den += homes.zone_pop @ hourly_weights(epoch, homes.zones)
            instants += 1
        for name, model in radii.items():
            classes, approach, departure = coverage.lookup(types, catalogue, model, loss=15)
            for epoch, fixes in by_instant:
                resident, ratio, _ = coverage.range_matches(fixes, homes, classes, approach, departure, (1.,))
                covered = np.unique(resident[ratio <= 1])
                counts = np.bincount(strata_zone[covered], weights=homes.pop[covered],
                                     minlength=2 * len(homes.zones)).reshape(-1, 2)
                num[name] += counts.T @ hourly_weights(epoch, homes.zones)
    if instants != 288 or not np.isclose(den.sum(), 288 * 331449281):
        raise ValueError("Unexpected population-time denominator")
    percentages = pd.DataFrame({f"{name}.{region}": 100 * counts[i] / den
                                for name, counts in num.items() for i, region in enumerate(strata)})
    percentages.index.name = 'hour'
    return percentages


def mix(hours, activity, settings):
    table = pd.DataFrame(index=range(24))
    # Use the published noise windows for acoustics, independent of the reporting periods.
    acoustic_day = (hours.index >= 7) & (hours.index < 19)

    def environment(state):
        curve = pd.Series(0., index=hours.index)
        for region, pair in settings['floor_by_region'].items():
            d, n = [hours[f"{label}.{state}.{region}"] for label in pair]
            curve += d.where(acoustic_day, n)
        return curve

    outside = environment('outside')
    closed = environment('closed')
    opened = environment('open')
    open_rate = np.broadcast_to(np.asarray(settings['open_fraction']), 24)
    table['home'] = (activity.own_home_indoor + activity.other_home_indoor) * ((1 - open_rate) * closed + open_rate * opened)
    table['other_building'] = activity.other_building_indoor * closed
    table['outdoors'] = activity.outdoor * outside
    table['transit_or_unspecified'] = (activity.vehicle + activity.unknown) * settings.get('transit_as_closed', 0) * closed
    table['total'] = table.sum(axis=1)
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acoustics', type=Path)
    parser.add_argument('inputs', type=Path)
    parser.add_argument('types', type=Path)
    parser.add_argument('anp', type=Path)
    parser.add_argument('metro', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--activity', type=Path)
    parser.add_argument('--mixes', type=Path)
    parser.add_argument('--reuse-hours', type=Path)
    args = parser.parse_args()
    config = json.loads(args.acoustics.read_text())
    if args.reuse_hours:
        hours = pd.read_csv(args.reuse_hours, index_col='hour')
    else:
        hours = exposures(args, config)
        hours.to_csv(args.out.with_suffix('.hours.csv'), mode='x')
    if bool(args.activity) != bool(args.mixes):
        parser.error('Provide both activity and mixes')
    if args.activity:
        activity = pd.read_csv(args.activity, index_col='hour')
        if list(activity.index) != list(range(24)) or not np.allclose(activity.sum(axis=1), 1, atol=1e-6):
            raise ValueError('Hourly activity fractions must sum to one')
        outputs = []
        for name, settings in json.loads(args.mixes.read_text()).items():
            contributions = mix(hours, activity, settings)
            for period, clock_hours in [('day', range(6,22)), ('night', [22,23,*range(6)]), ('whole', range(24))]:
                outputs.append({'scenario': name, 'period': period, **contributions.loc[clock_hours].mean().to_dict()})
        pd.DataFrame(outputs).to_csv(args.out.with_suffix('.mix.csv'), index=False, mode='x')


if __name__ == '__main__':
    main()
