"""Pool window hits over the four sampled days, keeping each duration's denominator explicit."""
import argparse
import csv
from pathlib import Path

import numpy as np

DURATIONS = [5, 10, 15, 30, 60]
POPULATION = 341_784_857
PHONE_DAY = .80 * .88
PHONE_NIGHT = .80 * .89


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("scores", nargs="+", type=Path)
    args = parser.parse_args()
    dates = [f.name[:10] for f in args.scores]
    if len(set(dates)) != len(dates):
        raise ValueError("One output per distinct date required")
    samples = []
    for date, file in zip(dates,args.scores):
        with np.load(file) as result:
            n = len(result["unique_seconds_day"])
            day_sec = result["unique_seconds_day"].mean()/57600
            night_sec = result["unique_seconds_night"].mean()/28800
            print(date, "residents", n, "instantaneous fractions", round(day_sec,6), round(night_sec,6))
            for length in DURATIONS:
                day = result[f"day_{length}"].mean() / (960/length)
                night = result[f"night_{length}"].mean() / (480/length)
                assert day+1e-9>=day_sec and night+1e-9>=night_sec
                assert not np.any(result[f"day_{length}"] > 960/length)
                assert not np.any(result[f"night_{length}"] > 480/length)
                samples.append((date,length,day,night))
            for small,big in [(5,10),(5,15),(10,30),(15,30),(30,60)]:
                for p in ["day","night"]:
                    a,b=result[f"{p}_{small}"],result[f"{p}_{big}"]
                    assert (b<=a).all() and (b*(big//small)>=a).all()
    with args.output.open("x") as fp:
        writer = csv.writer(fp)
        writer.writerow(["sample","window_min","day_pct","night_pct","full_day_pct_if_phone_near",
                         "pct_all_windows_both","predicted_windows_per_US_day_both"])
        for date in [*dates, "pooled"]:
            for length in DURATIONS:
                rows=[(day,night) for d,w,day,night in samples if w==length and (date=="pooled" or date==d)]
                day,night=np.mean(rows,axis=0)
                both=(16*PHONE_DAY*day + 8*PHONE_NIGHT*night)/24
                phone=(16*PHONE_DAY + 8*PHONE_NIGHT)/24
                writer.writerow([date,length,100*day,100*night,100*both/phone,100*both,
                                 round(POPULATION*1440/length*both)])
                if date=="pooled":
                    print(f"{length:2d} min: {100*day:.3f}%, {100*night:.3f}%, {100*both/phone:.3f}%, {100*both:.3f}%, {POPULATION*1440/length*both/1e6:.2f}M")


if __name__ == "__main__":
    main()
