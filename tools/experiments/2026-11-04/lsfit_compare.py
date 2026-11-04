"""PLAN Phase 2 item 4: the least-squares track fit against today's brightness and contrast fits.
The criterion and every definition are in docs/experiments/2026-11-04-least-squares-fit.md, written first.

livermore: every pass, the four methods, errors in f0, speed and slant range against the trajectory-derived
           reference (the Livermore audit's passes.csv and the KML trajectory at its emission CPA).
dev:       Oyster Bay's README events and the eagle cam's detect ranks 5 and 13, the four methods, the
           heard-CPA, emission-CPA and steepest-fall gap errors against the trajectories' true gaps.

usage: lsfit_compare.py RUN livermore|dev"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import livermore_audit as LA                                            # noqa: E402

from dopplertrack import audio, tracks                                  # noqa: E402
from dopplertrack.audio import Spectrogram                              # noqa: E402
from dopplertrack.doppler import curve_from_trajectory, speed_of_sound  # noqa: E402
from dopplertrack.geo import lla_to_enu                                 # noqa: E402

REPO = Path(__file__).resolve().parents[3]
AUDIT = LA.DATA / "runs/2026-11-04-livermore-audit"
SR, N, HOP = 4000, 8192, 0.25
GOOD_RMS = 1.6
METHODS = ("brightness", "contrast", "ls", "ls_weighted")
# true gaps between the two events, from the trajectories (timing-conventions record)
TRUE_GAPS = {"oyster-bay": {"heard": 922.96, "emission": 930.17, "steepest": 928.18},
             "eagle-cam": {"heard": 331.61, "emission": 321.47, "steepest": 338.30}}


def fit_all(sp, t0, t1, f_lo, f_hi, c, harmonics=1):
    """The four methods on one window: {method: (EventFit, TrackFit diagnostics or None, seconds)}."""
    out = {}
    for obj in ("brightness", "contrast"):
        a = time.perf_counter()
        out[obj] = (tracks.fit_event(sp, t0, t1, f_lo, f_hi, c=c, harmonics=harmonics, objective=obj), None,
                    time.perf_counter() - a)
    a = time.perf_counter()
    tr = tracks.ridge_track(sp, t0, t1, f_lo, f_hi)
    for name, weighted in (("ls", False), ("ls_weighted", True)):
        b = time.perf_counter()
        fit = tracks.fit_track(tr, c=c, weighted=weighted)
        out[name] = (fit.event(), fit, time.perf_counter() - b + (b - a if name == "ls" else 0.0))
    return out, tr


def ols_outlier_share(tr, fit):
    t, g, _ = tr.usable()
    z, _ = tracks._z(t, fit.t_cpa_emit, fit.s)
    r = g - fit.alpha - fit.beta * z
    mad = 1.4826 * np.median(np.abs(r - np.median(r)))
    return float(np.mean(np.abs(r - np.median(r)) > 4 * mad)) if mad > 0 else 0.0


def reference_speed(p, site, c):
    """3D speed of the PCHIP-interpolated KML trajectory at its emission CPA, as heard_curve interpolates."""
    tr = p["track"]
    mid = p["ridge"][:, 0].mean()
    m = np.abs(tr[:, 0] - mid) <= 300
    t, lat, lon, alt = tr[m].T
    enu = lla_to_enu(lat, lon, alt, site["lat"], site["lon"], site["alt_msl"])
    pchip = PchipInterpolator(t, enu.T, axis=1)
    te = np.arange(t[0], t[-1], 0.05)
    _, _, r = curve_from_trajectory(te, pchip(te).T, np.zeros(3), c=c, max_gap_s=1e9)
    tc = te[np.nanargmin(r)]
    return float(np.linalg.norm(pchip.derivative()(tc))), float(np.nanmin(r))


def livermore(run: Path):
    passes = {p["id"]: p for p in LA.load_passes()}
    rows = {r["id"]: r for r in csv.DictReader(open(AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(AUDIT / "sites.json"))["sites"]}
    c = speed_of_sound(15.0)
    out = []
    for pid in sorted(rows):
        r, p = rows[pid], passes[pid]
        th, g, _, _, _ = LA.heard_curve(p, sites[r["site"]], c)
        shift, f0, start = float(r["shift_15C"]), float(r["f0_15C"]), float(r["start"])
        fs = f0 * np.interp(start + np.arange(p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start, HOP) - shift,
                            th, g, left=np.nan, right=np.nan)
        span = (p["ridge"][0, 0] - start, p["ridge"][-1, 0] - start)
        band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
        v_ref, d_kml = reference_speed(p, sites[r["site"]], c)
        x, _ = audio.load_audio(p["dir"] / "audio.wav", SR)
        sp = audio.compute_spectrogram(x, SR, nperseg=N, hop_s=HOP, fmin=40, fmax=1900)
        fits, tr = fit_all(sp, *span, *band, c)
        row = dict(id=pid, good=float(r["fit_rms_hz_15C"]) / f0 * 100 < GOOD_RMS, f0_ref=f0, v_ref=v_ref,
                   d_ref=float(r["slant_m_15C"]), d_kml_min=d_kml, span=span, band=band, n_track=len(tr.t))
        for name, (ev, diag, secs) in fits.items():
            row[name] = dict(f0=ev.f0, v=ev.v, d=ev.d, t_cpa_emit=ev.t_cpa_emit, seconds=secs,
                             err_f0=abs(ev.f0 - f0) / f0, err_v=abs(ev.v - v_ref) / v_ref,
                             err_d=abs(ev.d - row["d_ref"]) / row["d_ref"])
            if diag is not None:
                row[name].update(identified=diag.identified, z_span=diag.z_span, cond=diag.cond, rms_hz=diag.rms_hz,
                                 n_optima=diag.n_optima, at_bound=diag.at_bound, corr_v_d=diag.corr_v_d,
                                 converged=diag.converged)
        row["ls"]["outlier_share"] = ols_outlier_share(tr, fits["ls"][1])
        out.append(row)
        print(pid, "good" if row["good"] else "flagged",
              " ".join(f"{m}: f0 {row[m]['err_f0']:.4f} v {row[m]['err_v']:.3f} d {row[m]['err_d']:.3f}" for m in METHODS),
              flush=True)
    (run / "livermore.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    summary = {}
    for group, keep in (("primary_29", lambda r: r["good"]), ("flagged_11", lambda r: not r["good"]), ("all_40", lambda r: True)):
        sel = [r for r in out if keep(r)]
        summary[group] = {m: {q: float(np.median([r[m][f"err_{q}"] for r in sel])) for q in ("f0", "v", "d")} | {"n": len(sel)}
                          for m in METHODS}
        for m in ("ls", "ls_weighted"):
            summary[group][m]["not_identified"] = sum(not r[m]["identified"] for r in sel)
            summary[group][m]["median_corr_v_d"] = float(np.median([r[m]["corr_v_d"] for r in sel]))
        summary[group]["ls"]["outlier_share_median"] = float(np.median([r["ls"]["outlier_share"] for r in sel]))
        summary[group]["ls"]["outlier_share_pooled_over_2pct"] = sum(r["ls"]["outlier_share"] > 0.02 for r in sel)
    p = summary["primary_29"]
    best = {q: min(p["brightness"][q], p["contrast"][q]) for q in ("f0", "v", "d")}
    summary["criterion_1"] = {m: {q: p[m][q] <= best[q] for q in best} for m in ("ls", "ls_weighted")}
    (run / "livermore_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


def dev(run: Path):
    c = speed_of_sound()
    swfl = json.loads((REPO / "docs/results/swfl_detected.json").read_text())
    cases = {
        "oyster-bay": (LA.DATA / "derived/oyster_bay/rec.npz",
                       [(2090, 2200, 95, 200, 2), (3020, 3130, 95, 195, 1)]),
        "eagle-cam": (LA.DATA / "derived/swfl/rec.npz",
                      [(e["t_start"], e["t_end"], 0.85 * e["f_post"], 1.15 * e["f_pre"], 1) for e in (swfl[4], swfl[12])]),
    }
    out = {}
    for case, (path, events) in cases.items():
        sp = Spectrogram.load(path)
        fits = [fit_all(sp, t0, t1, lo, hi, c, harmonics=h)[0] for t0, t1, lo, hi, h in events]
        res = {}
        for m in METHODS:
            e1, e2 = fits[0][m][0], fits[1][m][0]
            res[m] = dict(ev1=e1.to_dict(), ev2=e2.to_dict(),
                          heard_gap_error=(e2.t_cpa - e1.t_cpa) - TRUE_GAPS[case]["heard"],
                          emission_gap_error=(e2.t_cpa_emit - e1.t_cpa_emit) - TRUE_GAPS[case]["emission"],
                          emission_vs_steepest_gap_error=(e2.t_cpa_emit - e1.t_cpa_emit) - TRUE_GAPS[case]["steepest"])
            for k, (_, diag, _) in enumerate((fits[0][m], fits[1][m]), 1):
                if diag is not None:
                    res[m][f"ev{k}_diag"] = {kk: getattr(diag, kk) for kk in ("identified", "z_span", "cond", "rms_hz", "n_optima",
                                                                              "at_bound", "corr_v_d", "converged", "n")}
        res["criterion_2"] = {m: abs(res[m]["heard_gap_error"]) <= abs(res["contrast"]["heard_gap_error"]) for m in ("ls", "ls_weighted")}
        out[case] = res
        print(case, {m: round(res[m]["heard_gap_error"], 2) for m in METHODS}, flush=True)
    (run / "dev.json").write_text(json.dumps(out, indent=1, default=float) + "\n")


if __name__ == "__main__":
    {"livermore": livermore, "dev": dev}[sys.argv[2]](Path(sys.argv[1]))
