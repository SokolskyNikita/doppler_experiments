"""Summarise blind-search result CSVs: triples, flight pairs, true-pair rank, distance of the top
candidate from the truth, margin over the best wrong pair.
Usage: summarise.py LAT LON ICAO1 ICAO2 CSV [CSV ...]"""
import sys

import numpy as np
import pandas as pd

lat, lon, i1, i2 = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3], sys.argv[4]


def dist_m(la, lo):
    a = np.sin(np.radians(la - lat) / 2) ** 2 + np.cos(np.radians(lat)) * np.cos(np.radians(la)) * np.sin(np.radians(lo - lon) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


print(f"{'run':28s} {'triples':>8s} {'pairs':>6s} {'rank':>5s} {'top m':>7s} {'true':>7s} {'wrong':>7s} {'margin':>7s}  runner-up")
for p in sys.argv[5:]:
    r = pd.read_csv(p).sort_values("score", ascending=False)
    best = r.drop_duplicates(["icao1", "icao2"]).reset_index(drop=True)
    is_true = (best.icao1 == i1) & (best.icao2 == i2)
    rank = int(np.flatnonzero(is_true)[0]) + 1 if is_true.any() else None
    true_s = float(best.score[is_true].iloc[0]) if rank else float("nan")
    wrong = best[~is_true].iloc[0]
    top = r.iloc[0]
    print(f"{p.split('/')[-1]:28s} {len(r):8d} {len(best):6d} {str(rank):>5s} {dist_m(top.lat, top.lon):7.0f} {true_s:7.2f} {wrong.score:7.2f} "
          f"{100 * (true_s / wrong.score - 1):6.1f}%  {wrong.icao1}/{wrong.icao2} {dist_m(wrong.lat, wrong.lon) / 1000:.0f} km away")
