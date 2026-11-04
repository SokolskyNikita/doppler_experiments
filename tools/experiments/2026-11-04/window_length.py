"""Window length (PLAN Phase 2 item 5): fit_event's f0, speed and slant-range errors with the STFT window
at 2.048, 1.024 and 0.512 s, and a two-window composite, on the 29 primary Livermore passes and the
development events with an ADS-B truth. The criterion and every definition were fixed before this ran.

Spectrograms: 4 kHz, Hann window of T seconds zero-padded to 8192 points (0.488 Hz grid for every T; the
resolution stays 1/T), hop 0.25 s, default whitening, 40-1900 Hz. A shorter window's samples are offset
by (8192 - N)/2 so every variant has the same frame centres. Informational: hop T/8 at each T, and the
2.048 s window at a 1 s hop (about the independent-frame count of 0.512 s at 0.25 s, Harris 1978).

Two-window composite, two-stage: (a) fit_event on 2.048 s; (b) the fitted curve's sweep rate |g(t)| per
frame picks the window in {2.048, 1.024, 0.512} closest to 1/sqrt|g| (argmin |ln(T sqrt|g|)|); (c) the
chosen windows' whitened columns form one spectrogram; (d) fit_event again on it, init from (a).
Oracle composite (decides nothing): the same, with g from the reference curve.

Fits: fit_event, both objectives, harmonics 1 on Livermore (window = published span, band = 0.85x-1.15x
the reference's range), the README windows and bands on the development pairs, the labelled window and
lines on the blind-matched events. c at 15 deg C.
Truth: Livermore f0 = the audit's f0_15C, v = the PCHIP trajectory's 3-D speed at the emission CPA,
d = slant_m_15C. Development events: v and d from the CPA table at the true location (ADS-B gives no f0).
Criterion: a variant is kept if, for each objective and each of f0, v and d, its median |relative error|
over the 29 primary passes is at most 1.05x the 2.048 s window's, and the same for v and d on the
development events; the paired sign test is reported.

usage: window_length.py RUN [livermore|dev|all]"""
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import livermore_audit as LA                                            # noqa: E402

from dopplertrack import audio                                           # noqa: E402
from dopplertrack.adsb import load_traces                                # noqa: E402
from dopplertrack.audio import Spectrogram                               # noqa: E402
from dopplertrack.doppler import ideal_curve, speed_of_sound             # noqa: E402
from dopplertrack.geo import lla_to_enu                                  # noqa: E402
from dopplertrack.search import Grid, build_segments, cpa_table          # noqa: E402
from dopplertrack.terrain import Terrain                                 # noqa: E402
from dopplertrack.tracks import fit_event                                # noqa: E402

DATA = LA.DATA
AUDIT = DATA / "runs/2026-11-04-livermore-audit"
SR, NFFT, HOP = 4000, 8192, 0.25
WINDOWS = (8192, 4096, 2048)                    # samples: 2.048, 1.024, 0.512 s
C = speed_of_sound(15.0)
OBJECTIVES = ("contrast", "brightness")
GOOD_RMS = 1.6


def spectrogram(x, nperseg, hop_s=HOP, align=True):
    """Whitened spectrogram with frame centres at (8192/2 + k hop)/sr whatever nperseg is."""
    off = (NFFT - nperseg) // 2 if align else 0
    sp = audio.compute_spectrogram(x[off:], SR, nperseg=nperseg, hop_s=hop_s, fmin=40, fmax=1900, nfft=NFFT)
    return Spectrogram(sp.t + off / SR, sp.f, sp.S, sp.valid)


def composite(sps, g, t):
    """Per frame, the column of the window closest to 1/sqrt|g|; sps share t (cropped to the shortest)."""
    K = min(len(s.t) for s in sps)
    T = np.array([n / SR for n in WINDOWS])
    gg = np.abs(np.interp(sps[0].t[:K], t, g, left=0.0, right=0.0))
    pick = np.argmin(np.abs(np.log(T[None, :] * np.sqrt(np.maximum(gg, 1e-9))[:, None])), axis=1)
    S = np.stack([s.S[:, :K] for s in sps])                              # (W, F, K)
    return Spectrogram(sps[0].t[:K], sps[0].f, S[pick, :, np.arange(K)].T.astype(np.float32)), np.bincount(pick, minlength=3)


def curve_rate(f0, v, d, t0_emit, t):
    f = ideal_curve(t, f0, v, d, t0_emit, c=C)
    return np.gradient(np.nan_to_num(f, nan=np.nanmean(f)), t)


def fit_all(x, t_start, t_end, f_lo, f_hi, harmonics=1, ref_rate=None, timing=None):
    """Every variant's fits: {variant: {objective: EventFit}}, plus run times and composite picks."""
    out, info = {}, {}
    sps = {n: spectrogram(x, n) for n in WINDOWS}
    for n, sp in sps.items():
        out[f"w{n}"] = {o: fit_event(sp, t_start, t_end, f_lo, f_hi, c=C, harmonics=harmonics, objective=o) for o in OBJECTIVES}
    for n in WINDOWS:                                                    # informational: hop T/8
        sp = spectrogram(x, n, hop_s=n / SR / 8)
        out[f"w{n}_hopT8"] = {o: fit_event(sp, t_start, t_end, f_lo, f_hi, c=C, harmonics=harmonics, objective=o) for o in OBJECTIVES}
    sp = spectrogram(x, 8192, hop_s=1.0)
    out["w8192_hop1"] = {o: fit_event(sp, t_start, t_end, f_lo, f_hi, c=C, harmonics=harmonics, objective=o) for o in OBJECTIVES}
    tt = np.arange(t_start - 40, t_end + 40, 0.05)
    out["two"], out["oracle"] = {}, {}
    for o in OBJECTIVES:
        e = out["w8192"][o]
        comp, picks = composite([sps[n] for n in WINDOWS], curve_rate(e.f0, e.v, e.d, e.t_cpa_emit, tt), tt)
        info[f"picks_two_{o}"] = picks.tolist()
        out["two"][o] = fit_event(comp, t_start, t_end, f_lo, f_hi, c=C, harmonics=harmonics, objective=o,
                                  init=(e.f0, e.v, e.d, e.t_cpa_emit))
        if ref_rate is not None:
            comp, picks = composite([sps[n] for n in WINDOWS], ref_rate(tt), tt)
            info[f"picks_oracle_{o}"] = picks.tolist()
            out["oracle"][o] = fit_event(comp, t_start, t_end, f_lo, f_hi, c=C, harmonics=harmonics, objective=o,
                                         init=(e.f0, e.v, e.d, e.t_cpa_emit))
    if not out["oracle"]:
        del out["oracle"]
    return out, info


def rel(e, truth):
    return {k: abs(getattr(e, k) - truth[k]) / truth[k] for k in truth}


# ---- Livermore -------------------------------------------------------------------------------

def speed_at_cpa(p, site):
    tr = p["track"]
    mid = p["ridge"][:, 0].mean()
    m = np.abs(tr[:, 0] - mid) <= 300
    t, lat, lon, alt = tr[m].T
    enu = lla_to_enu(lat, lon, alt, site["lat"], site["lon"], site["alt_msl"])
    P = PchipInterpolator(t, enu.T, axis=1)
    te = np.arange(t[0], t[-1], 0.05)
    k = int(np.argmin(np.linalg.norm(P(te).T, axis=1)))
    return float(np.linalg.norm(P.derivative()(te[k])))


def livermore(run):
    passes = {p["id"]: p for p in LA.load_passes()}
    rows = {r["id"]: r for r in csv.DictReader(open(AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(AUDIT / "sites.json"))["sites"]}
    out = []
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        site = sites[r["site"]]
        th, g, _, _, _ = LA.heard_curve(p, site, C)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        fref = lambda t: f0 * np.interp(start + np.asarray(t) - shift, th, g, left=np.nan, right=np.nan)
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        fs = fref(np.arange(*span, HOP))
        band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        truth = dict(f0=f0, v=speed_at_cpa(p, site), d=float(r["slant_m_15C"]))

        def ref_rate(t):
            f = fref(t)
            return np.gradient(np.where(np.isfinite(f), f, np.nanmean(f)), t)

        x, _ = audio.load_audio(p["dir"] / "audio.wav", SR)
        t0 = time.perf_counter()
        fits, info = fit_all(x, *span, *band, ref_rate=ref_rate)
        res = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < GOOD_RMS, truth=truth, band=band, span=span,
                   seconds=time.perf_counter() - t0, info=info,
                   err={v: {o: rel(e, truth) for o, e in fo.items()} for v, fo in fits.items()},
                   fits={v: {o: e.to_dict() for o, e in fo.items()} for v, fo in fits.items()})
        out.append(res)
        e = res["err"]
        print(pid, "good" if res["good"] else "flag", " ".join(
            f"{v}:{e[v]['contrast']['d']:.3f}/{e[v]['brightness']['d']:.3f}" for v in ("w8192", "w4096", "w2048", "two")),
            f"{res['seconds']:.1f}s", flush=True)
    (run / "window_livermore.json").write_text(json.dumps(out, indent=1, default=float))
    return out


# ---- development events -----------------------------------------------------------------------

def decode(src, t0, dur):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-t", f"{dur}", "-i", str(src), "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, check=True, capture_output=True).stdout, np.float32).copy()


def cpa_truth(traces_path, lat, lon, icao, t_heard_rec, t0_unix):
    traces = load_traces(traces_path)
    grid = Grid.points([lat], [lon], Terrain().elevation(np.array([lat]), np.array([lon])))
    segs = build_segments(traces, grid.lat0, grid.lon0, clip_enu=(-12000, 12000, -12000, 12000))
    cpa = cpa_table(grid, segs, max_range_m=12000, c=C)
    cpa["icao"] = [segs[s].icao for s in cpa.seg]
    x = cpa[cpa.icao == icao]
    r = x.iloc[int(np.argmin(np.abs(x.t_heard.to_numpy() - t0_unix - t_heard_rec)))]
    return dict(v=float(r.v), d=float(r.d), t_heard_rec=float(r.t_heard - t0_unix))


def unix(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


DEV = [   # (name, source, (t_start, t_end), (f_lo, f_hi), harmonics, traces, truth point, icao, heard s (approx), clock)
    ("oyster ev1 (README)", "raw/audio/youtube/oyster_bay.webm", (2090, 2200), (95, 200), 2, "derived/oyster_bay/traces_ny.npz",
     (40.876466, -73.524951), "a1dfeb", 2155.6, "2026-09-08T20:17:30.34Z"),
    ("oyster ev2 (README)", "raw/audio/youtube/oyster_bay.webm", (3020, 3130), (95, 195), 1, "derived/oyster_bay/traces_ny.npz",
     (40.876466, -73.524951), "ace391", 3068.4, "2026-09-08T20:17:30.34Z"),
    ("eagle ev1 (README)", "raw/audio/youtube/swfl_2024-12-28.webm", (20117.024, 20357.024), (60, 300), 1, "derived/swfl/traces_swfl.npz",
     (26.702359, -81.847766), "a2baea", 20247.5, "2024-12-28T14:21:08.49Z"),
    ("eagle ev2 (README)", "raw/audio/youtube/swfl_2024-12-28.webm", (20457.024, 20697.024), (60, 300), 1, "derived/swfl/traces_swfl.npz",
     (26.702359, -81.847766), "a336e4", 20585.3, "2024-12-28T14:21:08.49Z"),
    ("ob-e03 (blind, clear)", "raw/audio/youtube/oyster_bay.webm", (105, 200), (0.85 * 65, 1.15 * 130), 1, "derived/oyster_bay/traces_ny.npz",
     (40.876466, -73.524951), "a40d8f", 130.5, "2026-09-08T20:17:30.34Z"),
    ("sw-e01 (blind, overlapping)", "raw/audio/youtube/swfl_2024-12-28.webm", (3600, 3775), (0.85 * 105, 1.15 * 165), 1, "derived/swfl/traces_swfl.npz",
     (26.702359, -81.847766), "a625e2", 3701.4, "2024-12-28T14:21:08.49Z"),
]


def dev(run):
    out = []
    for name, src, (a, b), (lo, hi), harm, trp, (lat, lon), icao, heard, clock in DEV:
        truth = cpa_truth(DATA / trp, lat, lon, icao, heard, unix(clock))
        pad = 400.0
        a0 = max(a - pad, 0.0)
        x = decode(DATA / src, a0, b - a0 + pad)
        # the segment's sample 0 is recording second a0: shift the window instead of the spectrogram
        fits, info = fit_all(x, a - a0, b - a0, lo, hi, harmonics=harm)
        res = dict(event=name, truth=truth, info=info,
                   err={v: {o: {k: abs(getattr(e, k) - truth[k]) / truth[k] for k in ("v", "d")} for o, e in fo.items()}
                        for v, fo in fits.items()},
                   fits={v: {o: e.to_dict() for o, e in fo.items()} for v, fo in fits.items()})
        out.append(res)
        print(name, truth, {v: {o: {k: round(x, 3) for k, x in d.items()} for o, d in res["err"][v].items()}
                            for v in ("w8192", "w4096", "w2048", "two")}, flush=True)
    (run / "window_dev.json").write_text(json.dumps(out, indent=1, default=float))
    return out


# ---- summary -----------------------------------------------------------------------------------

VARIANTS = ("w8192", "w4096", "w2048", "two", "oracle", "w8192_hopT8", "w4096_hopT8", "w2048_hopT8", "w8192_hop1")


def summarise(run, liv, devs):
    lines, verdict = [], {}
    good = [r for r in liv if r["good"]] if liv else []
    for title, rows, params in (("Livermore primary (29)", good, ("f0", "v", "d")),
                                ("Livermore flagged (11)", [r for r in (liv or []) if not r["good"]], ("f0", "v", "d")),
                                ("development events", devs or [], ("v", "d"))):
        if not rows:
            continue
        lines.append(f"== {title}, n={len(rows)}: median |relative error| (variant: contrast / brightness)")
        for v in VARIANTS:
            if v not in rows[0]["err"]:
                continue
            cells = []
            for o in OBJECTIVES:
                med = {k: float(np.median([r["err"][v][o][k] for r in rows])) for k in params}
                base = {k: float(np.median([r["err"]["w8192"][o][k] for r in rows])) for k in params}
                wins = {k: sum(r["err"][v][o][k] < r["err"]["w8192"][o][k] for r in rows) for k in params}
                sign = {k: binomtest(wins[k], len(rows)).pvalue for k in params} if v != "w8192" else {}
                ok = all(med[k] <= 1.05 * base[k] for k in params)
                if v in ("w4096", "w2048", "two"):
                    verdict.setdefault(v, []).append((title, o, ok))
                cells.append(f"{o}: " + " ".join(f"{k} {med[k]:.4f}" + (f" ({wins[k]}/{len(rows)} better, p {sign[k]:.2f})" if sign else "")
                                                  for k in params) + (f" -> {'OK' if ok else 'worse'}" if v != "w8192" else ""))
            lines.append(f"{v:12s} " + " | ".join(cells))
    lines.append("== criterion (a variant is kept if OK for both objectives on Livermore primary and on the development events)")
    for v, items in verdict.items():
        crit = [ok for title, o, ok in items if not title.startswith("Livermore flagged")]
        lines.append(f"{v}: {'KEPT' if crit and all(crit) else 'not kept'}  {items}")
    if liv:
        pk = np.sum([r["info"]["picks_two_contrast"] for r in good], axis=0)
        po = np.sum([r["info"]["picks_oracle_contrast"] for r in good], axis=0)
        lines.append(f"composite frames by window (2.048/1.024/0.512 s), contrast, primary: two-stage {pk.tolist()}, oracle {po.tolist()}")
        lines.append(f"runtime per pass, all variants: median {np.median([r['seconds'] for r in liv]):.1f} s")
    txt = "\n".join(lines)
    print(txt)
    (run / "window_summary.txt").write_text(txt + "\n")


if __name__ == "__main__":
    run = Path(sys.argv[1]); what = sys.argv[2] if len(sys.argv) > 2 else "all"
    liv = livermore(run) if what in ("livermore", "all") else (json.loads((run / "window_livermore.json").read_text())
                                                              if (run / "window_livermore.json").exists() else None)
    devs = dev(run) if what in ("dev", "all") else (json.loads((run / "window_dev.json").read_text())
                                                    if (run / "window_dev.json").exists() else None)
    summarise(run, liv, devs)
