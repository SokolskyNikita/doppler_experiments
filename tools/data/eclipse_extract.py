"""Unzip a UTC time range of an Eclipse Soundscapes day zip into its own folder, with CONFIG.TXT.

AudioMoth names each WAV by its start, YYYYMMDD_HHMMSS.WAV in UTC (CONFIG.TXT says the time zone),
so a range is picked by name. The output folder is what `dopplertrack spectrogram` takes. Files
are unzipped into a temporary folder beside the output and renamed into place, so another session
never sees a half-written folder; an existing output is never touched.

usage: eclipse_extract.py ZIP OUT_DIR FROM TO
  FROM, TO: UTC as YYYYMMDD_HHMMSS; files whose names fall in [FROM, TO) are extracted
example: eclipse_extract.py $DOPPLERTRACK_DATA/raw/audio/eclipse/ESID_740/ESID_740_2024_04_07.zip \\
         $DOPPLERTRACK_DATA/derived/eclipse/ESID_740/2024-04-07_04h 20240407_040000 20240407_050000
"""
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

if len(sys.argv) != 5:
    sys.exit(__doc__)
zip_path, out, lo, hi = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
if not all(re.fullmatch(r"\d{8}_\d{6}", s) for s in (lo, hi)):
    sys.exit("FROM and TO must look like YYYYMMDD_HHMMSS")
if out.exists():
    sys.exit(f"{out} exists; pick a new folder")

with zipfile.ZipFile(zip_path) as z:
    names = [n for n in z.namelist() if Path(n).name.upper() == "CONFIG.TXT"
             or (re.fullmatch(r"\d{8}_\d{6}\.wav", Path(n).name, re.IGNORECASE) and lo <= Path(n).name[:15] < hi)]
    wavs = [n for n in names if n.lower().endswith(".wav")]
    if not wavs:
        sys.exit(f"no WAV in {zip_path} between {lo} and {hi}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        for n in names:
            with z.open(n) as src, open(tmp / Path(n).name, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
print(f"{out}: {len(wavs)} WAVs, {Path(sorted(wavs)[0]).name} .. {Path(sorted(wavs)[-1]).name}")
