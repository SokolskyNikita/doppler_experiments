"""The windowed aircraft list for the adsbfetch comparison: every propeller or unknown-type hex seen in
the box's replay slices (any mirror) during the recording +-30 min, one hex per line in
window_<site>.txt, and per-site unique-aircraft counts for the whole day.

usage: uv run python tools/experiments/2026-11-04/adsbfetch_window.py "$RUN"
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dopplertrack.adsb import AircraftTypes

# recording start (from the known-point clocks) and length, s
SITES = {"ny": ("2026-09-08T20:17:30Z", 3600.0), "swfl": ("2024-12-28T19:21:08Z", 5400.0)}   # swfl: the 18,000 s clip
PAD = 1800.0


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()


def main(run: Path):
    types = AircraftTypes()
    out = {}
    for site, (start, length) in SITES.items():
        t0, t1 = utc(start) - PAD, utc(start) + length + PAD
        day, window = {}, set()
        for f in sorted((run / "replay").glob(f"{site}_*.jsonl")):
            src = f.stem.split("_", 1)[1]
            for line in open(f):
                r = json.loads(line)
                typ = r.get("type_code")
                day.setdefault(src, {})[r["hex"]] = typ
                if t0 <= utc(r["ts"]) <= t1 and types.is_prop(typ):
                    window.add(r["hex"])
        (run / f"window_{site}.txt").write_text("".join(f"{h}\n" for h in sorted(window)))
        union = {h: t for d in day.values() for h, t in d.items()}
        out[site] = dict(window=[start, length, PAD], window_hexes=len(window),
                         day_unique={s: len(d) for s, d in day.items()},
                         day_unique_prop={s: sum(types.is_prop(t) for t in d.values()) for s, d in day.items()},
                         day_union=len(union), day_union_prop=sum(types.is_prop(t) for t in union.values()))
        print(site, out[site], flush=True)
    json.dump(out, open(run / "window.json", "w"), indent=1)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
