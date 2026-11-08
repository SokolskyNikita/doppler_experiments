"""The spectrogram of a whole Eclipse Soundscapes day zip, in one step, for a case's recipe.

Unzips every AudioMoth WAV (and CONFIG.TXT) into a temporary folder beside OUT, builds the gap-aware spectrogram with
`dopplertrack spectrogram`'s defaults (0.25 s hop, 40-450 Hz; the holes between files marked invalid), writes OUT and
removes the folder. Nothing of the unzipped audio (about 6 GB a site-day) is left behind. Refuses to overwrite OUT.

usage: eclipse_spectrogram.py ZIP OUT
"""
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from dopplertrack.components.stft import spectrogram_from_audiomoth

if len(sys.argv) != 3:
    sys.exit(__doc__)
zip_path, out = Path(sys.argv[1]), Path(sys.argv[2])
if out.exists():
    sys.exit(f"{out} exists")
out.parent.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp(prefix=f".{out.stem}.audio.", dir=out.parent))
try:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if Path(n).name.upper() == "CONFIG.TXT"
                 or re.fullmatch(r"\d{8}_\d{6}\.wav", Path(n).name, re.IGNORECASE)]
        if not any(n.lower().endswith(".wav") for n in names):
            sys.exit(f"no WAV in {zip_path}")
        for n in names:
            with z.open(n) as src, open(tmp / Path(n).name, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    sp = spectrogram_from_audiomoth(tmp, hop_s=0.25, fmin=40, fmax=450)
    sp.save(out)
    print(f"{zip_path.name} -> {out}: {len(sp.t)} frames, {len(sp.f)} bins, "
          f"{0 if sp.valid is None else int((~sp.valid).sum())} invalid frames")
finally:
    shutil.rmtree(tmp)
