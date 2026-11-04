"""Compute fixed-wing third-octave crossover ranges from the original pilot and ANP 2.3."""
import argparse
import csv
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import soundfile as sf
from scipy.optimize import brentq


BANDS = np.array([100, 125, 160, 200, 250, 315, 400])
ABSORPTION = [0.66, 0.66, 0.98, 1.31, 1.31, 1.97, 2.30]  # dB/km, ECAC Doc 29
MODELS = set("""
    CNA172 PA28 CNA182 PA30 BEC58P CNA208 PA42 CNA441 DHC830 ATR72 1900D
    CIT3 GV EMB175 CRJ9-ER 737800 7378MAX A320-211 A320-232 777200 767300
""".split())


def background(pilot):
    segments = []
    for filename in sorted(pilot.glob("*.flac")):
        samples, rate = sf.read(filename)
        if rate != 1000 or samples.ndim != 1:
            raise ValueError(f"Expected 1 kHz mono pilot in {filename}")
        segments.append(samples)
    signal = np.concatenate(segments)
    window = np.hanning(2048)
    size = len(window)
    frames = signal[:len(signal) // size * size].reshape(-1, size)
    power = 2 * abs(np.fft.rfft(frames * window, axis=1))**2 / (size * (window**2).sum())
    frequencies = np.fft.rfftfreq(size, d=1 / 1000)
    noise = []
    for center in BANDS:
        inside = (frequencies >= center / 2**(1/6)) & (frequencies < center * 2**(1/6))
        noise.append(10 * np.log10(np.median(power[:, inside].sum(axis=1))))
    return np.array(noise)


def a_weight(frequencies):
    squared = frequencies**2
    numerator = 12194**2 * squared**2
    denominator = ((squared + 20.6**2) * np.sqrt((squared + 107.7**2) * (squared + 737.9**2))
                   * (squared + 12194**2))
    return 20 * np.log10(numerator / denominator) + 2


def table(archive, name):
    text = archive.read(f"ANP2.3_{name}.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def crossing(margin, absorption):
    reference_km = 0.3048

    def remaining(distance):
        return (margin - 20 * np.log10(distance / reference_km)
                - absorption * (distance - reference_km))

    return brentq(remaining, 0.001, 200)


def model_levels(anp_zip):
    """Yield unweighted band levels at the 1,000 ft reference range for each engine setting."""
    with ZipFile(anp_zip) as archive:
        aircraft = table(archive, "Aircraft")
        spectra = {row["Spectral Class ID"]: row for row in table(archive, "Spectral_classes")}
        settings = table(archive, "NPD_data")
    for aircraft_row in aircraft:
        model = aircraft_row["ACFT_ID"]
        if model not in MODELS:
            continue
        for setting in settings:
            if (setting["NPD_ID"] != aircraft_row["NPD_ID"] or setting["Noise Metric"] != "LAmax"):
                continue
            mode = {"A": "Approach", "D": "Departure"}[setting["Op Mode"]]
            shape = spectra[aircraft_row[f"{mode} Spectral Class ID"]]
            bands = {int(k[2:-2]): float(v) for k, v in shape.items() if k.startswith("L_")}
            weighted = np.array(list(bands.values())) + a_weight(np.array(list(bands), dtype=float))
            norm = 10 * np.log10(np.sum(10**(weighted/10)))
            levels = np.array([bands[b] for b in BANDS]) + float(setting["L_1000ft"]) - norm
            yield model, mode, setting["Power Setting"], levels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("anp_zip", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    noise = background(args.pilot)
    columns = ["model", "operation", "power_setting", "indoor_loss_dB", "band_Hz", "radius_km"]
    with args.output_csv.open("x") as output:
        writer = csv.writer(output)
        writer.writerow(columns)
        for model, mode, power, levels in model_levels(args.anp_zip):
            for loss in [5, 15, 25]:
                margins = levels - (noise + 130) - loss
                radii = [crossing(m, a) for m, a in zip(margins, ABSORPTION)]
                best = np.argmax(radii)
                writer.writerow([model, mode, power, loss, BANDS[best], round(radii[best], 4)])


if __name__ == "__main__":
    main()
