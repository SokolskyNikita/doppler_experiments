"""Provenance audit of the Livermore corpus (Pathak 2026, Zenodo 23424278): where the microphone was, and
whether the published frequency tracks and the WAVs line up in time with the ADS-B tracks.

1. Microphone. The results table gives each pass's L, the horizontal distance from the recorder to the
   ADS-B ground track at closest approach, and H, the track's height above the recorder there. The recorder
   is the point whose distance to every track (the KML polyline within 180 s of the ridge) matches L, by
   robust least squares; passes more than 150 m off are fitted again as a second site. Its height is the
   median of track altitude minus H. 1-sigma from the Jacobian scaled by the residuals, and the
   leave-one-out spread.
2. ADS-B clock against the ridge clock. At the reconstructed microphone, the curve heard from the
   trajectory (PCHIP through the KML points, emission-time kinematics, c at --temp) is shifted in time and
   scaled in f0 to fit the published ridge by least squares. The shift is the ridge clock minus the ADS-B
   clock. Also the steepest-fall times of both curves and the trajectory's heard-CPA time.
3. WAV start. The WAVs carry no time. The start that lays the UTC ridge on the recording's own whitened
   spectrogram (best of every 10 ms) is the first sample's time on the ridge clock; aligning the first and
   last halves of the ridge separately bounds any stretch.

Run from the repo root:
    uv run python tools/experiments/2026-11-04/livermore_audit.py "$RUN"
with RUN from tools/data/new_run.py and the zips unpacked in $DOPPLERTRACK_DATA/derived/livermore/.
"""
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy.optimize as so
import scipy.signal as ss
from scipy.interpolate import PchipInterpolator

from dopplertrack.audio import load_audio
from dopplertrack.doppler import curve_from_trajectory, speed_of_sound
from dopplertrack.geo import enu_to_lla, lla_to_enu
from dopplertrack.terrain import Terrain

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
RAW = DATA / "raw/audio/livermore/zenodo-23424278"
CORPUS = DATA / "derived/livermore"
NEAR = (37.68, -121.77)          # a starting point in Livermore; the fit does not depend on it
ELSEWHERE = 150.0                # m: a pass this far off its L was recorded at another site
TEMPS = (15.0, 25.0)             # deg C: the package default and a May afternoon in Livermore


def utc(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_passes():
    rows = {r["case"]: r for r in csv.DictReader(open(RAW / "final_results_40_cases.csv"))}
    passes = []
    for d in sorted(CORPUS.glob("*/*/")):
        r = rows[d.name]
        kml = next(d.glob("*.kml")).read_text()
        when = [utc(w) for w in re.findall(r"<when\s*>([^<]+)</when>", kml)]
        coord = [tuple(map(float, c.split())) for c in re.findall(r"<gx:coord\s*>([^<]+)</gx:coord>", kml)]
        assert len(when) == len(coord), d
        tr = np.array([(t, lat, lon, alt) for t, (lon, lat, alt) in zip(when, coord) if alt > 0])
        _, keep = np.unique(tr[:, 0], return_index=True)   # repeated stamps: keep the first
        ridge = np.array([(utc(a), float(b)) for a, b in csv.reader(list(open(d / "frequency_vs_time_used.csv"))[1:])])
        tr = tr[np.sort(keep)]
        mid = ridge[:, 0].mean()
        near = tr[np.abs(tr[:, 0] - mid) <= 180]
        en = lla_to_enu(near[:, 1], near[:, 2], near[:, 3], *NEAR, 0.0)[:, :2]
        passes.append(dict(id=d.name, dir=d, cat=r["category"], row=r, L=float(r["L_ADSB_m"]),
                           H=float(r["H_ADSB_above_recorder_m"]), track=tr, ridge=ridge, near=(near[:, 0], near[:, 3], en),
                           day=r["received_start_utc"][:10]))
    return passes


def horiz_cpa(p, lat0, lon0):
    """Horizontal closest approach of the track polyline (within 180 s of the ridge) to (lat0, lon0):
    distance, altitude there, and the time there. Distances are taken in the tangent plane at NEAR, whose
    distortion over 15 km is a few millimetres."""
    t, alt, en = p["near"]
    e0, n0, _ = lla_to_enu(lat0, lon0, 0.0, *NEAR, 0.0)
    a = en[:-1] - (e0, n0); ab = en[1:] - en[:-1]
    u = np.clip(-(a * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
    d = np.hypot(*(a + u[:, None] * ab).T)
    i = int(np.argmin(d))
    return float(d[i]), float(alt[i] + u[i] * (alt[i + 1] - alt[i])), float(t[i] + u[i] * (t[i + 1] - t[i]))


def trilaterate(passes, x0=None):
    """The point whose horizontal distance to every track matches its L (soft-L1, 50 m scale), from a
    grid of starts, or from x0 (east, north of NEAR) when given."""
    def at(x):
        lat, lon, _ = enu_to_lla(x[0], x[1], 0.0, *NEAR, 0.0)
        return float(lat), float(lon)

    def res(x):
        return np.array([horiz_cpa(p, *at(x))[0] - p["L"] for p in passes])

    if x0 is None:
        grid = [(e, n) for e in range(-15000, 15001, 500) for n in range(-15000, 15001, 500)]
        cost = [np.sum(np.sqrt(1 + (res(g) / 50) ** 2) - 1) for g in grid]
        starts = [grid[k] for k in np.argsort(cost)[:10]]   # each pass alone allows a line either side of its track
    else:
        starts = [x0]
    best = None
    for x in starts:
        fit = so.least_squares(res, x, loss="soft_l1", f_scale=50.0, x_scale=100.0)
        if best is None or fit.cost < best.cost:
            best = fit
    r = res(best.x)
    J = best.jac
    dof = max(len(r) - 2, 1)
    cov = np.linalg.inv(J.T @ J) * float(np.sum(r ** 2) / dof)
    return *at(best.x), r, np.sqrt(np.diag(cov)), best.x


def place(passes):
    """Main site from the passes that agree within ELSEWHERE, refitted until the set holds; then a second
    site from the rest when at least three agree."""
    sites, left = [], list(passes)
    for name in ("main", "second"):
        if len(left) < 3:
            break
        members = left
        for _ in range(10):
            lat, lon, r, sd, x = trilaterate(members)
            d = np.array([horiz_cpa(p, lat, lon)[0] - p["L"] for p in left])
            new = [p for p, x in zip(left, d) if abs(x) <= ELSEWHERE]
            if len(new) < 3 or {p["id"] for p in new} == {p["id"] for p in members}:
                break
            members = new
        lat, lon, r, sd, x = trilaterate(members)
        loo = []
        for i in range(len(members)):
            la, lo, _, _, _ = trilaterate(members[:i] + members[i + 1:], x0=x)
            e, n, _ = lla_to_enu(la, lo, 0.0, lat, lon, 0.0)
            loo.append((float(e), float(n)))
        alts = [horiz_cpa(p, lat, lon)[1] - p["H"] for p in members]
        sites.append(dict(name=name, lat=lat, lon=lon, alt_msl=float(np.median(alts)),
                          alt_spread=float(np.percentile(alts, 75) - np.percentile(alts, 25)),
                          sd_e=float(sd[0]), sd_n=float(sd[1]), loo=np.array(loo),
                          rms=float(np.sqrt(np.mean(r ** 2))), members=[p["id"] for p in members],
                          resid={p["id"]: float(x) for p, x in zip(members, r)}))
        left = [p for p in left if p["id"] not in sites[-1]["members"]]
    return sites, [p["id"] for p in left]


def heard_curve(p, site, c, dt=0.05, interp="pchip"):
    """Ratio curve heard at the site from the trajectory through the KML points (PCHIP or linear):
    (t_heard, ratio, r, t_emit, largest KML gap within 30 s of the emission CPA)."""
    tr = p["track"]
    mid = p["ridge"][:, 0].mean()
    m = np.abs(tr[:, 0] - mid) <= 300
    t, lat, lon, alt = tr[m].T
    enu = lla_to_enu(lat, lon, alt, site["lat"], site["lon"], site["alt_msl"])
    te = np.arange(t[0], t[-1], dt)
    if interp == "pchip":
        pos = PchipInterpolator(t, enu.T, axis=1)(te).T
    else:
        pos = np.stack([np.interp(te, t, enu[:, j]) for j in range(3)], axis=1)
    th, g, r = curve_from_trajectory(te, pos, np.zeros(3), c=c, max_gap_s=1e9)
    ok = np.isfinite(g)
    te_cpa = te[np.nanargmin(r)]
    near = t[np.abs(t - te_cpa) <= 30]
    gap = float(np.diff(np.r_[t[t < te_cpa - 30][-1:], near, t[t > te_cpa + 30][:1]]).max())
    return th[ok], g[ok], r[ok], te[ok], gap


def steepest(t, f, lo, hi, smooth=4.0):
    """Time in [lo, hi] the curve falls fastest: a 7-point median (the ridge has outliers), then the
    local-quadratic slope over `smooth` s on a 0.1 s grid."""
    m = (t >= lo) & (t <= hi)
    t, f = t[m], ss.medfilt(f[m], 7)
    tg = np.arange(t[0], t[-1], 0.1)
    fg = np.interp(tg, t, f)
    w = int(round(smooth / 0.1)) | 1
    if len(fg) <= 3 * w:
        return np.nan
    slope = ss.savgol_filter(fg, w, 2, deriv=1, delta=0.1)
    k = slice(w, len(tg) - w)
    return float(tg[k][np.argmin(slope[k])])


def clock_shift(ridge, th, g, span=20.0, step=0.01):
    """Shift s (ridge clock minus ADS-B clock) and f0 minimising sum (f - f0 g(t - s))^2."""
    t, f = ridge.T
    best = (np.inf, np.nan, np.nan)
    for s in np.arange(-span, span + step / 2, step):
        x = np.interp(t - s, th, g, left=np.nan, right=np.nan)
        ok = np.isfinite(x)
        if ok.mean() < 0.95:
            continue
        f0 = float(np.dot(x[ok], f[ok]) / np.dot(x[ok], x[ok]))
        sse = float(np.mean((f[ok] - f0 * x[ok]) ** 2))
        if sse < best[0]:
            best = (sse, s, f0)
    return best[1], best[2], float(np.sqrt(best[0]))


def align_wav(p, sr=4000, nfft=2048, hop=80):
    """First sample's time on the ridge clock: the start maximising whitened power along the ridge."""
    x, sr = load_audio(p["dir"] / "audio.wav", sr)
    dur = len(x) / sr
    f, t, Z = ss.stft(x, sr, nperseg=nfft, noverlap=nfft - hop, boundary=None, padded=False)
    P = 10 * np.log10(np.abs(Z) ** 2 + 1e-20)
    P -= np.median(P, axis=1, keepdims=True)
    P = np.maximum.reduce([np.roll(P, k, axis=0) for k in (-2, -1, 0, 1, 2)])   # +-2 bins
    rt, rf = p["ridge"].T
    bins = np.clip(np.round(rf / (sr / nfft)).astype(int), 0, len(f) - 1)

    def score(s, sel=slice(None)):
        fr = np.round((rt[sel] - s - t[0]) / (hop / sr)).astype(int)
        ok = (fr >= 0) & (fr < len(t))
        return P[bins[sel][ok], fr[ok]].mean() if ok.mean() > 0.99 else -np.inf

    starts = np.arange(rt[-1] - dur, rt[0] + 1e-9, 0.01)
    sc = np.array([score(s) for s in starts])
    i = int(np.argmax(sc))
    others = sc[np.isfinite(sc) & (np.abs(starts - starts[i]) > 1)]
    contrast = float((sc[i] - others.mean()) / others.std()) if len(others) > 10 else np.nan
    h = len(rt) // 2
    near = starts[np.abs(starts - starts[i]) <= 2]
    first = near[np.argmax([score(s, slice(0, h)) for s in near])]
    last = near[np.argmax([score(s, slice(h, None)) for s in near])]
    return dict(start=float(starts[i]), dur=dur, pad_before=float(rt[0] - starts[i]),
                pad_after=float(starts[i] + dur - rt[-1]), contrast=contrast,
                halves=float(last - first))


def main(run: Path):
    passes = load_passes()
    sites, unplaced = place(passes)
    site_of = {pid: s for s in sites for pid in s["members"]}
    ground = Terrain().elevation(np.array([s["lat"] for s in sites]), np.array([s["lon"] for s in sites]))
    rows = []
    for p in passes:
        s = site_of.get(p["id"])
        if s is None:
            continue
        d, alt, t_hcpa = horiz_cpa(p, s["lat"], s["lon"])
        out = dict(id=p["id"], day=p["day"], category=p["cat"], site=s["name"], L=p["L"], L_resid=d - p["L"],
                   H=p["H"], flags=p["row"]["flags"], paper_timing_difference_s=float(p["row"]["timing_difference_s"]))
        for temp in TEMPS:
            c = speed_of_sound(temp)
            th, g, r, te, gap = heard_curve(p, s, c)
            shift, f0, rms = clock_shift(p["ridge"], th, g)
            k = int(np.argmin(r))
            tag = f"_{temp:.0f}C"
            out.update({f"shift{tag}": shift, f"f0{tag}": f0, f"fit_rms_hz{tag}": rms,
                        f"heard_cpa_utc{tag}": float(th[k]), f"slant_m{tag}": float(r[k])})
            if temp == TEMPS[0]:
                lo, hi = p["ridge"][0, 0] - shift, p["ridge"][-1, 0] - shift
                st_model = steepest(th, g, lo, hi)
                st_ridge = steepest(*p["ridge"].T, lo + shift, hi + shift)
                thl, gl, _, _, _ = heard_curve(p, s, c, interp="linear")
                out["shift_linear_15C"], _, out["fit_rms_hz_linear_15C"] = clock_shift(p["ridge"], thl, gl)
                out.update(steep_model_utc=st_model, steep_ridge_utc=st_ridge, steep_diff=st_ridge - st_model,
                           steep_model_minus_heard_cpa=st_model - float(th[k]),
                           steep_model_minus_emit_cpa=st_model - float(te[k]),
                           steep_ridge_minus_heard_cpa=st_ridge - float(th[k]), max_kml_gap_s=gap,
                           emit_cpa_utc=float(te[k]))
                plot_pass(run, p, th, g, shift, f0)
        out.update(align_wav(p))
        out["ridge_first_utc"] = float(p["ridge"][0, 0])
        rows.append(out)
        print(f"{p['id']:12s} {s['name']:6s} L_res {out['L_resid']:6.1f}  shift {out['shift_15C']:6.2f} s  "
              f"steep {out['steep_diff']:6.2f} s  wav pad {out['pad_before']:5.2f}/{out['pad_after']:5.2f} s  "
              f"contrast {out['contrast']:5.1f}", flush=True)

    with open(run / "passes.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    site_out = []
    for s, z in zip(sites, ground):
        loo = s.pop("loo")
        site_out.append({**s, "ground_terrarium_m": float(z), "loo_max_m": float(np.hypot(*loo.T).max()),
                         "loo_sd_e": float(loo[:, 0].std()), "loo_sd_n": float(loo[:, 1].std())})
    json.dump(dict(sites=site_out, unplaced=unplaced, temps=TEMPS), open(run / "sites.json", "w"), indent=1)
    summarise(run, rows)


def summarise(run, rows, good_rms_pct=1.6):
    """Robust statistics of the clock shift over the passes whose trajectory curve fits the ridge to
    good_rms_pct of f0, overall and per day; the WAV pads over all passes."""
    def stats(x):
        x = np.asarray(x, float)
        med = float(np.median(x))
        return dict(n=len(x), median=med, robust_sd=float(1.4826 * np.median(np.abs(x - med))),
                    q25=float(np.percentile(x, 25)), q75=float(np.percentile(x, 75)))
    good = [r for r in rows if 100 * r["fit_rms_hz_15C"] / r["f0_15C"] < good_rms_pct]
    days = sorted({r["day"] for r in good})
    out = dict(good_rms_pct=good_rms_pct, good=[r["id"] for r in good],
               shift_15C=stats([r["shift_15C"] for r in good]),
               shift_25C=stats([r["shift_25C"] for r in good]),
               shift_linear_minus_pchip=stats([r["shift_linear_15C"] - r["shift_15C"] for r in good]),
               shift_by_day={d: stats([r["shift_15C"] for r in good if r["day"] == d]) for d in days},
               steep_ridge_minus_model=stats([r["steep_diff"] for r in good]),
               steep_model_minus_emit_cpa=stats([r["steep_model_minus_emit_cpa"] for r in good]),
               corr_shift_kml_gap=float(np.corrcoef([r["shift_15C"] for r in good], [r["max_kml_gap_s"] for r in good])[0, 1]),
               corr_shift_paper_timing=float(np.corrcoef([r["shift_15C"] for r in good],
                                                         [r["paper_timing_difference_s"] for r in good])[0, 1]),
               kml_gap_s=stats([r["max_kml_gap_s"] for r in rows]),
               pad_before=stats([r["pad_before"] for r in rows]), pad_after=stats([r["pad_after"] for r in rows]))
    json.dump(out, open(run / "summary.json", "w"), indent=1)


def plot_pass(run, p, th, g, shift, f0):
    fig, ax = plt.subplots(figsize=(7, 3.5))
    t0 = p["ridge"][0, 0]
    ax.plot(p["ridge"][:, 0] - t0, p["ridge"][:, 1], ".", ms=2, label="published ridge")
    m = (th + shift >= t0 - 5) & (th + shift <= p["ridge"][-1, 0] + 5)
    ax.plot(th[m] + shift - t0, f0 * g[m], "-", lw=1, label=f"trajectory, shifted {shift:+.2f} s")
    ax.set(xlabel="s after first ridge point", ylabel="Hz", title=p["id"])
    ax.legend(fontsize=7)
    fig.tight_layout()
    (run / "passes").mkdir(exist_ok=True)
    fig.savefig(run / "passes" / f"{p['id']}.png", dpi=90)
    plt.close(fig)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
