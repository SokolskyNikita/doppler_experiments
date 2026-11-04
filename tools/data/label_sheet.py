"""Contact sheets for labelling acoustic events (PLAN 5.3), and a check of the label files.

  label_sheet.py sheet SOURCE OUT_DIR --span T0 T1 [--band 40 450] [--strip 120] [--sheet 600]
      Whitened spectrogram of [T0, T1] recording seconds, one PNG per --sheet seconds in strips of --strip
      seconds, with no flight data: the blind layer-1 view. SOURCE is one of
        a spectrogram .npz (dopplertrack spectrogram output);
        an audio file (decoded from T0 with ffmpeg);
        ZIP:GLOB, a zip of AudioMoth files named YYYYMMDD_HHMMSS.wav (Eclipse Soundscapes), with --t0-utc
        giving the UTC of recording second 0. Files are placed by their names; gaps between them stay grey.
      Writes sheet.json beside the images: the source, its SHA-256, the span and the drawing parameters.
  label_sheet.py overlay SOURCE LABELS TRACES OUT_DIR --site LAT LON ELEV --t0-utc ISO [same options]
      Layer 2, after the blind pass: the same sheets with every ADS-B pass within --range m drawn as the curve
      heard at the site, scaled to the f0 of the labelled line nearest it in time (dashed, and at 100 Hz if
      none is within 60 s), and its heard-CPA time marked with the aircraft and slant range.
  label_sheet.py check LABELS...
      Validates label files against the format below.

The spectrogram is the package's default: a 2.048 s Hann window (8192 samples at 4 kHz) every 0.25 s,
in dB, less each bin's median over the sheet and then each frame's median over frequency, shown from 0 to
--vmax dB.

Label files live in bench/labels/<recording>-<t0>-<t1>.json:
  {"format": 1,
   "recording": {"id", "source" (path under $DOPPLERTRACK_DATA), "sha256", "t0_utc" or null, "case" or null},
   "span": [t0, t1],                    recording seconds that were labelled
   "sheets": "runs/<folder>",          where the contact sheets are
   "windows": [{"id", "class", "start", "end", "lines": [[f_start, f_end], ...], "harmonics",
                "labeller", "blind", "date", "notes"}],
   "associations": [{"window", "flight": {"icao", "registration", "heard_cpa_utc", "slant_m"} or "unmatched",
                     "labeller", "blind", "date", "notes"}]}
Layer 1 classes: clear, uncertain, overlapping, masked, absent. The windows cover the whole span, so a
stretch with no event is an "absent" window, not a gap. A line is the frequency where a visible tone enters
and leaves the window; "harmonics" is how many such lines belong to the event.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy.signal as ss

from dopplertrack.audio import Spectrogram

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
SR, NFFT, HOP = 4000, 8192, 1000
CLASSES = ("clear", "uncertain", "overlapping", "masked", "absent")


def utc(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def decode(cmd_input: list[str]) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", *cmd_input, "-ac", "1", "-ar", str(SR), "-f", "f32le",
                          "-acodec", "pcm_f32le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def db_frames(x: np.ndarray, t_first: float, band) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """dB STFT of x, whose first sample is at recording time t_first: (frame times, freqs, dB)."""
    if len(x) < NFFT:
        return np.empty(0), np.empty(0), np.empty((0, 0))
    f, _, Z = ss.stft(x, SR, nperseg=NFFT, noverlap=NFFT - HOP, window="hann", boundary=None, padded=False)
    keep = (f >= band[0]) & (f <= band[1])
    t = t_first + (NFFT / 2 + np.arange(Z.shape[1]) * HOP) / SR
    return t, f[keep], 10 * np.log10(np.abs(Z[keep]) ** 2 + 1e-20)


def load(source: str, span, band, t0_utc: str | None) -> tuple[Spectrogram, dict]:
    """Spectrogram of span on a regular 0.25 s grid (NaN where there is no audio), and provenance."""
    grid = np.arange(span[0] + NFFT / 2 / SR, span[1] - NFFT / 2 / SR + 1e-9, HOP / SR)
    if ":" in source and source.split(":")[0].endswith(".zip"):
        zpath, pattern = source.split(":", 1)
        if t0_utc is None:
            sys.exit("a zip source needs --t0-utc")
        z = zipfile.ZipFile(zpath)
        rows, freqs = [], None
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            name = Path(info.filename).name
            m = re.match(r"(\d{8}_\d{6})\.wav$", name, re.I)
            if not m or not fnmatch.fnmatch(name, pattern):
                continue
            start = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc).timestamp() - utc(t0_utc)
            if start > span[1] or start + info.file_size / 2 / 8000 < span[0]:    # >= 8 kHz 16-bit mono
                continue
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "f32le",
                                  "-acodec", "pcm_f32le", "-"], input=z.read(info), check=True, capture_output=True).stdout
            x = np.frombuffer(raw, np.float32)
            if start + len(x) / SR < span[0]:
                continue
            t, freqs, L = db_frames(x, start, band)
            rows.append((t, L))
        S = np.full((len(freqs), len(grid)), np.nan, np.float32)
        for t, L in rows:
            idx = np.round((t - grid[0]) / (HOP / SR)).astype(int)
            ok = (idx >= 0) & (idx < len(grid))
            S[:, idx[ok]] = L[:, ok]
        prov = dict(source=zpath, member_glob=pattern, sha256=sha256(Path(zpath)), t0_utc=t0_utc)
        f = freqs
    elif source.endswith(".npz"):
        sp = Spectrogram.load(source).crop(span[0], span[1], band[0], band[1])
        return sp, dict(source=source, sha256=sha256(Path(source)), t0_utc=t0_utc,
                        note="whitened by `dopplertrack spectrogram`, then by the sheet median")
    else:
        x = decode(["-ss", f"{span[0]}", "-t", f"{span[1] - span[0]}", "-i", source])
        t, f, L = db_frames(x, span[0], band)
        S = L.astype(np.float32)
        grid = t
        prov = dict(source=source, sha256=sha256(Path(source)), t0_utc=t0_utc)
    return Spectrogram(grid, f, S), prov


def whiten(S: np.ndarray, frames: bool = True) -> np.ndarray:
    """Less each bin's median over the sheet (stationary tones), then each frame's median over frequency
    (broadband bursts: wind, rain, traffic), so that a moving tone stands out."""
    S = S - np.nanmedian(S, axis=1, keepdims=True)
    return S - np.nanmedian(S, axis=0, keepdims=True) if frames else S


def draw(sp: Spectrogram, out_dir: Path, span, strip, sheet, vmax, smooth=2.0, fpool=3, overlay=None, tag="blind"):
    """For display only: a running mean over `smooth` s along time (tones are continuous, noise isn't) and
    a maximum over `fpool` bins along frequency (a one-bin line survives the downscaling)."""
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    out_dir.mkdir(parents=True, exist_ok=True)
    S = whiten(sp.S)
    gap = np.isnan(S)
    S = np.nan_to_num(S)
    if smooth > 0:
        S = uniform_filter1d(S, max(1, int(round(smooth / sp.dt))), axis=1)
    if fpool > 1:
        S = maximum_filter1d(S, fpool, axis=0)
    S[gap] = np.nan
    paths = []
    for s0 in np.arange(span[0], span[1], sheet):
        s1 = min(s0 + sheet, span[1])
        n = int(np.ceil((s1 - s0) / strip))
        fig, axes = plt.subplots(n, 1, figsize=(16, 3.6 * n), squeeze=False)
        for k, ax in enumerate(axes[:, 0]):
            a, b = s0 + k * strip, min(s0 + (k + 1) * strip, s1)
            m = (sp.t >= a) & (sp.t <= b)
            cmap = plt.get_cmap("magma").copy(); cmap.set_bad("0.6")
            ax.imshow(np.ma.masked_invalid(S[:, m]), origin="lower", aspect="auto", cmap=cmap, vmin=0, vmax=vmax,
                      extent=[sp.t[m][0] if m.any() else a, sp.t[m][-1] if m.any() else b, sp.f[0], sp.f[-1]],
                      interpolation="nearest")
            ax.set_xlim(a, a + strip); ax.set_ylim(sp.f[0], sp.f[-1])
            ax.set_xticks(np.arange(a, a + strip + 1e-9, 10)); ax.set_xticks(np.arange(a, a + strip, 2), minor=True)
            ax.set_yticks(np.arange(50, sp.f[-1], 50)); ax.grid(axis="y", color="w", alpha=0.15, lw=0.5)
            ax.tick_params(labelsize=7); ax.set_ylabel("Hz", fontsize=7)
            if overlay:
                overlay(ax, a, a + strip)
        axes[0, 0].set_title(f"{tag}: recording seconds {s0:.0f}-{s1:.0f}", fontsize=9)
        fig.tight_layout()
        p = out_dir / f"{tag}_{s0:06.0f}-{s1:06.0f}.png"
        fig.savefig(p, dpi=90)
        plt.close(fig)
        paths.append(p.name)
    return paths


def passes(traces_path, site, t0_utc, span, max_range):
    """(heard t in recording s, ratio curve, heard-CPA time, slant, icao, registration) of every pass within
    max_range of the site that is heard during the span."""
    from dopplertrack.adsb import load_traces
    from dopplertrack.doppler import speed_of_sound
    from dopplertrack.score import modelled_curve
    from dopplertrack.search import build_segments
    c = speed_of_sound()
    traces = load_traces(traces_path)
    t0 = utc(t0_utc)
    segs = build_segments(traces, site[0], site[1], clip_enu=(-max_range, max_range, -max_range, max_range))
    obs = np.array([0.0, 0.0, site[2]])
    out = []
    for s in segs:
        r = np.linalg.norm(s.enu - obs, axis=1)
        k = int(np.argmin(r))
        th = s.t[k] + r[k] / c - t0
        if r[k] > max_range or not (span[0] - 60 <= th <= span[1] + 60):
            continue
        to, ratio = modelled_curve(s, obs, c)
        tr = traces[s.trace_idx]
        out.append((to - t0, ratio, th, float(r[k]), s.icao, getattr(tr, "reg", None) or ""))
    return out


def make_overlay(labels, flights):
    lines = []      # (t_mid, f0) of every labelled line
    for w in labels["windows"]:
        for f_a, f_b in w.get("lines", []):
            if f_a and f_b:
                lines.append((0.5 * (w["start"] + w["end"]), 2 * f_a * f_b / (f_a + f_b)))

    def overlay(ax, a, b):
        for t, ratio, th, d, icao, reg in flights:
            if not (a - 60 <= th <= b + 60):
                continue
            near = [f0 for tm, f0 in lines if abs(tm - th) <= 60]
            for f0 in (near or [100.0]):
                ax.plot(t, f0 * ratio, "c--" if near else "c:", lw=0.8)
            if a <= th <= b:
                ax.axvline(th, color="c", lw=0.6, alpha=0.7)
                ax.text(th, ax.get_ylim()[1], f" {reg or icao} {d / 1000:.1f} km", color="c", fontsize=6, va="top")
        for w in labels["windows"]:
            if w["class"] != "absent" and w["end"] >= a and w["start"] <= b:
                ax.axvspan(max(w["start"], a), min(w["end"], b), color="lime", alpha=0.08)
                ax.text(max(w["start"], a), ax.get_ylim()[0], f" {w['id']}", color="lime", fontsize=6, va="bottom")
    return overlay


def check(path: Path) -> list[str]:
    errs = []
    d = json.load(open(path))
    if d.get("format") != 1:
        errs.append("format must be 1")
    for k in ("id", "source", "sha256"):
        if not d.get("recording", {}).get(k):
            errs.append(f"recording.{k} missing")
    t0, t1 = d["span"]
    ws = sorted(d.get("windows", []), key=lambda w: w["start"])
    ids = [w["id"] for w in ws]
    if len(set(ids)) != len(ids):
        errs.append("window ids repeat")
    for w in ws:
        if w["class"] not in CLASSES:
            errs.append(f"{w['id']}: class {w['class']!r}")
        if not (t0 <= w["start"] < w["end"] <= t1):
            errs.append(f"{w['id']}: [{w['start']}, {w['end']}] outside the span or empty")
        for k in ("labeller", "blind", "date"):
            if k not in w:
                errs.append(f"{w['id']}: {k} missing")
        if w["class"] in ("clear", "uncertain", "overlapping") and w.get("harmonics", 0) < 1:
            errs.append(f"{w['id']}: an event needs at least one harmonic")
    covered = t0
    for w in ws:
        if w["start"] > covered + 1e-6:
            errs.append(f"[{covered}, {w['start']}] is not covered by any window")
        covered = max(covered, w["end"])
    if covered < t1 - 1e-6:
        errs.append(f"[{covered}, {t1}] is not covered by any window")
    for a in d.get("associations", []):
        if a["window"] not in ids:
            errs.append(f"association to unknown window {a['window']}")
        if a["flight"] != "unmatched" and not a["flight"].get("icao"):
            errs.append(f"association of {a['window']}: flight needs an icao or 'unmatched'")
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sheet", "overlay"):
        p = sub.add_parser(name)
        p.add_argument("source")
        if name == "overlay":
            p.add_argument("labels"); p.add_argument("traces")
            p.add_argument("--site", nargs=3, type=float, required=True, metavar=("LAT", "LON", "ELEV"))
            p.add_argument("--range", type=float, default=12000.0)
        p.add_argument("out_dir")
        p.add_argument("--span", nargs=2, type=float, required=True)
        p.add_argument("--band", nargs=2, type=float, default=(40.0, 450.0))
        p.add_argument("--strip", type=float, default=120.0); p.add_argument("--sheet", type=float, default=600.0)
        p.add_argument("--vmax", type=float, default=6.0)
        p.add_argument("--smooth", type=float, default=2.0, help="running mean along time for display, s")
        p.add_argument("--fpool", type=int, default=3, help="maximum over this many bins along frequency, for display")
        p.add_argument("--t0-utc", required=name == "overlay")
    c = sub.add_parser("check"); c.add_argument("labels", nargs="+")
    a = ap.parse_args()
    if a.cmd == "check":
        bad = 0
        for p in a.labels:
            errs = check(Path(p))
            print(f"{p}: {'ok' if not errs else '; '.join(errs)}")
            bad += bool(errs)
        sys.exit(1 if bad else 0)
    sp, prov = load(a.source, a.span, a.band, a.t0_utc)
    out = Path(a.out_dir)
    if a.cmd == "sheet":
        pngs = draw(sp, out, a.span, a.strip, a.sheet, a.vmax, a.smooth, a.fpool)
    else:
        labels = json.load(open(a.labels))
        flights = passes(a.traces, a.site, a.t0_utc, a.span, a.range)
        pngs = draw(sp, out, a.span, a.strip, a.sheet, a.vmax, a.smooth, a.fpool, make_overlay(labels, flights), tag="overlay")
        json.dump([dict(heard_cpa_s=th, slant_m=d, icao=icao, registration=reg) for _, _, th, d, icao, reg in
                   sorted(flights, key=lambda x: x[2])], open(out / "passes.json", "w"), indent=1)
    meta = dict(cmd=a.cmd, span=a.span, band=a.band, strip=a.strip, sheet=a.sheet, vmax=a.vmax, smooth=a.smooth, fpool=a.fpool,
                stft=dict(sr=SR, nperseg=NFFT, hop=HOP, window="hann"), images=pngs, **prov)
    json.dump(meta, open(out / f"{a.cmd}.json", "w"), indent=1)
    print("\n".join(str(out / p) for p in pngs))


if __name__ == "__main__":
    main()
