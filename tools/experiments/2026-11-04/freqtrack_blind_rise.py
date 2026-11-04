"""How often freqtrack's rise rule fires on the blind-labelled clear events (bench/labels on dev), which
have no ADS-B reference: tracker B with the rise and hop rules as flags, over each event's window and the band
its labelled lines span (0.85x to 1.15x). Reports, per event, the tracks, the measured points, and the
points each rule flags. Audio is decoded only around each event (from 60 s before to 60 s after).

usage: freqtrack_blind_rise.py RUN LABELS.json..."""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

from dopplertrack import audio, freqtrack as ft

DATA = Path.home() / "data" / "dopplertrack"
SR, N, HOP = 4000, 8192, 0.25


def decode(src, t0, dur):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-t", f"{dur}", "-i", str(src), "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, check=True, capture_output=True).stdout, np.float32).copy()


def eclipse(zip_path, t0, dur, tmp):
    """ESID recording seconds count from 00:00 UTC; the minute files abut, so decode the ones covering
    [t0, t0 + dur) and join them."""
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.lower().endswith(".wav"))
        def sec(n):
            s = Path(n).name[9:15]
            return int(s[:2]) * 3600 + int(s[2:4]) * 60 + int(s[4:])
        pick = [n for n in names if sec(n) + 60 > t0 and sec(n) < t0 + dur]
        first = sec(pick[0])
        parts = []
        for n in pick:
            out = tmp / Path(n).name
            out.write_bytes(z.read(n))
            parts.append(audio.load_audio(out, SR)[0])
            out.unlink()
    return np.concatenate(parts), first


def main(run, labels, tag):
    rows = []
    tmp = run / "tmp_blind"; tmp.mkdir(exist_ok=True)
    for lf in labels:
        d = json.loads(Path(lf).read_text())
        src = DATA / d["recording"]["source"]
        for w in d["windows"]:
            if w["class"] != "clear":
                continue
            a = max(w["start"] - 60, 0)
            if src.suffix == ".zip":
                x, first = eclipse(src, a, w["end"] + 60 - a, tmp); off = first
            else:
                x = decode(src, a, w["end"] + 60 - a); off = a
            sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900)
            st = ft.SampleSTFT(x, SR, N, HOP)
            fl = [f for line in w["lines"] for f in line]
            band = (0.85 * min(fl), 1.15 * max(fl))
            ev = ft.track_window(sp, st, w["start"] - off, w["end"] - off, *band, PARAMS, flag=("rise", "hop"))
            pts = sum(int(tr.measured.sum()) for tr in ev.tracks)
            row = dict(event=w["id"], tracks=len(ev.tracks), points=pts, band=band)
            for rule in ("rise", "hop"):
                row[f"{rule}_flagged"] = sum(len(tr.flags.get(rule, [])) for tr in ev.tracks)
                row[f"tracks_with_{rule}"] = sum(bool(tr.flags.get(rule)) for tr in ev.tracks)
            rows.append(row)
            print(rows[-1], flush=True)
    tmp.rmdir()
    (run / f"freqtrack_blind_rise{tag}.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    # RUN1=1 in the environment: run 1's knobs (theta 9.5, birth 6); otherwise TrackParams()'s defaults
    import os
    run1 = os.environ.get("RUN1") == "1"
    PARAMS = ft.TrackParams(theta_db=9.5, birth=6.0, death=6.0) if run1 else ft.TrackParams()
    main(Path(sys.argv[1]), sys.argv[2:], "_run1" if run1 else "_run2")
