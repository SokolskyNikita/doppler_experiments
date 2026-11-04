"""Convert the Alaska ZE 2019 vertical-channel miniSEED files to npz, once, so the rest of Phase 2 item 2
can read them without obspy. obspy is not a dependency of the package; run this with it added for the
one call:

    uv run --with obspy python tools/experiments/2026-11-04/alaska_to_npz.py "$RUN"

Each raw/seismic/alaska-ze2019/earthscope-ze/ZE.<node>..DPZ.<start>.mseed becomes
derived/alaska/<node>_<start>.npz with the samples in raw counts (float32, gaps between traces filled
with NaN), the sampling rate, the UTC of the first sample (unix seconds) and the trace count. Instrument
response is not removed: frequency tracks don't need it. Each file is written under a temporary name and
renamed into place, the output folder must not exist yet, and the run folder gets the obspy version and
the file list.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import obspy

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
SRC = DATA / "raw/seismic/alaska-ze2019/earthscope-ze"
DST = DATA / "derived/alaska"


def main(run: Path):
    if DST.exists():
        sys.exit(f"refusing: {DST} exists")
    tmp_dir = DST.with_name(f".alaska.{os.getpid()}.tmp")
    tmp_dir.mkdir(parents=True)
    listing = []
    for f in sorted(SRC.glob("ZE.*..DPZ.*.mseed")):
        st = obspy.read(str(f))
        st.merge(method=0, fill_value=None)
        tr = st[0]
        sr = float(tr.stats.sampling_rate)
        data = np.ma.filled(tr.data.astype(np.float32), np.nan) if np.ma.isMaskedArray(tr.data) else tr.data.astype(np.float32)
        node = f.name.split(".")[1]
        start = f.name.split(".DPZ.")[1].removesuffix(".mseed")
        out = tmp_dir / f"{node}_{start}.npz"
        np.savez_compressed(out, data=data, sr=sr, t0=float(tr.stats.starttime.timestamp), node=node,
                            n_traces=len(obspy.read(str(f), headonly=True)))
        listing.append(dict(src=f.name, dst=out.name, sr=sr, t0=tr.stats.starttime.isoformat(), n=int(len(data)),
                            nan=int(np.isnan(data).sum())))
    os.replace(tmp_dir, DST)
    json.dump(dict(obspy=obspy.__version__, files=listing), open(run / "alaska_to_npz.json", "w"), indent=1)
    print(f"{len(listing)} files -> {DST} (obspy {obspy.__version__})")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
