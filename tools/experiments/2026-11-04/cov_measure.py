"""PLAN item 2's provisional bound: the frame covariance of ridge()'s frequency error, measured on passes synthesised
from the propagation delay alone (window_roc.synth: the three geometries, amplitudes 0.06, 0.03 and 0.015, seeds 0-2)
through the package's STFT (compute_spectrogram's defaults, 2.048 s Hann at 0.25 s) and tracks.ridge, against
Harris's predictions (crb.py's HANN_C: c(r) for the complex coefficients, c(r)^2 for an estimate from magnitudes).

Per frame, e = ridge frequency - the true heard frequency, over the frames with the tone in the ridge's band. The
correlation is measured on e less its 5 s running median (the slow part is bias, not noise, as crb.py's ridge model
treats it), with |e| beyond 5 MADs (bridges onto another line) dropped. N_eff = 1 + 2 sum_r rho(r), r = 1..8 hops,
is what the bound depends on: Harris gives 3.94 for c^2 (crb.py's N_EFF) and the c value printed beside it.

Criterion, fixed before the run: the measured correlation matches one of the two predictions within 20 % in N_eff,
and the slant-range bound it implies on the 29 primary Livermore passes (crb.py's package bound with sigma 0.45 % of
f0 and the measured rho in place of Harris's) has a median between 63 and 74 m; otherwise the record says which
numbers replace them.

Units: RUN/cov/<geometry>_<amp>/seed_<s>.json; `runs launch --shards 9` takes one geometry x amplitude per box
(units.shard). `bound` reads every unit and needs the Livermore inputs (crb.py's).

Follow-up (`bound2`; criterion fixed before it ran): rho with no detrend, against the exact synthetic curve (the 5 s
detrended rho kept beside it), and sigma at each Livermore pass's own SNR. SNR is the median whitened dB on the curve
over the pass's frames: on the synthetic passes along the true curve, on each primary Livermore pass along its
trajectory reference (the audit's). A pass's sigma (% of f0) is interpolated in SNR from the synthetic passes' (SNR,
sigma) pairs. Criterion: N_eff over lags 1-4 (1 + 2 sum_{r=1..4} rho) matches c (5.32) or c^2 (3.93) within 20 %, and
the median implied bound lands within 15 % of 63 or 74 m; otherwise the record names the number that replaces them,
and "provisional" comes off with it.

usage: cov_measure.py RUN measure [CELL ...]
       cov_measure.py RUN bound
       cov_measure.py RUN bound2"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import units as U                                                       # noqa: E402
import window_roc as WR                                                  # noqa: E402

from dopplertrack import audio                                           # noqa: E402
from dopplertrack.tracks import local_whiten, ridge                     # noqa: E402

HOP, SLOW_S, LAGS = 0.25, 5.0, 8
CELLS = [f"{g}_{a:g}" for g in WR.GEOMETRIES for a in WR.AMPS]


def _crb():
    spec = importlib.util.spec_from_file_location("crb", HERE / "crb.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def measure(run: Path, chosen: list[str]):
    for cell in U.shard(U.select(CELLS, chosen)):
        geom, amp = cell.rsplit("_", 1)
        for seed in WR.SEEDS:
            out = U.path(run / "cov" / cell, f"seed_{seed}")
            if out.exists():
                continue
            x, fref, _, (f0, v, d) = WR.synth(geom, float(amp), seed)
            sp = audio.compute_spectrogram(x, WR.SR)
            tt = sp.t[(sp.t > 5) & (sp.t < WR.DUR - 5)]
            fs = fref(tt)
            band = (0.85 * np.nanmin(fs), 1.15 * np.nanmax(fs))
            w = local_whiten(sp.crop(sp.t[0], sp.t[-1], *band))
            r = ridge(w)
            e = r - fref(w.t)
            U.write(out, dict(cell=cell, seed=seed, f0=f0, t=w.t.tolist(), e=np.where(np.isfinite(e), e, np.nan).tolist(),
                              df=float(sp.df)))
            print(cell, seed, float(np.nanstd(e)), flush=True)


def raw_errors(u):
    """e against the exact curve, no detrend; frames beyond 5 MADs (bridges) dropped."""
    e = np.asarray(u["e"], float)
    e = e[np.isfinite(e)]
    mad = 1.4826 * np.median(np.abs(e - np.median(e)))
    return e[np.abs(e - np.median(e)) <= 5 * mad] if mad > 0 else e


def snr_on_curve(sp, fref, t0, t1):
    w = local_whiten(sp)
    t = w.t[(w.t >= t0) & (w.t <= t1) & w.valid]
    v = w.sample(t, fref(t))
    return float(np.nanmedian(v))


def fast_errors(u):
    e = np.asarray(u["e"], float)
    ok = np.isfinite(e)
    e = e[ok]
    k = max(3, int(round(SLOW_S / HOP)) | 1)
    f = e - ss.medfilt(e, k)
    mad = 1.4826 * np.median(np.abs(f - np.median(f)))
    return f[np.abs(f) <= 5 * mad] if mad > 0 else f


def autocorr(series: list[np.ndarray]) -> np.ndarray:
    """Pooled autocorrelation at lags 0..LAGS hops over several series (each demeaned)."""
    num = np.zeros(LAGS + 1); den = 0.0
    for f in series:
        f = f - f.mean()
        den += float(np.dot(f, f))
        for r in range(LAGS + 1):
            num[r] += float(np.dot(f[:len(f) - r], f[r:]))
    return num / den


def bound(run: Path):
    crb = _crb()
    units = U.read_all(run / "cov", "*/seed_*.json")
    by_cell: dict = {}
    for u in units:
        by_cell.setdefault(u["cell"], []).append(u)
    c, c2 = crb.HANN_C, crb.HANN_C ** 2
    n_c, n_c2 = float(1 + 2 * c[1:].sum()), float(1 + 2 * c2[1:].sum())
    table = {}
    for cell, us in sorted(by_cell.items()):
        fs = [fast_errors(u) for u in us]
        rho = autocorr(fs)
        n_eff = float(1 + 2 * rho[1:].sum())
        sig = float(np.std(np.concatenate(fs)))
        table[cell] = dict(rho=rho.tolist(), n_eff=n_eff, sigma_hz=sig, sigma_pct=100 * sig / us[0]["f0"],
                           frames=int(sum(len(f) for f in fs)),
                           match_c2=abs(n_eff / n_c2 - 1) <= 0.2, match_c=abs(n_eff / n_c - 1) <= 0.2)
    pooled = autocorr([fast_errors(u) for u in units])
    n_pooled = float(1 + 2 * pooled[1:].sum())
    # the implied bound on the 29 primary Livermore passes: crb.py's package bound, sigma 0.45 % of f0, measured rho
    import csv
    import scipy.linalg as sl
    use = pooled
    if np.linalg.eigvalsh(sl.toeplitz(np.r_[pooled, np.zeros(200)]))[0] < 0:   # keep the covariance positive definite
        use = pooled * (1 - np.arange(LAGS + 1) / (LAGS + 1))
    rows_a = {r["id"]: r for r in csv.DictReader(open(crb.me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(crb.me.AUDIT / "sites.json"))["sites"]}
    flagged = {k for k, r in rows_a.items() if 100 * float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) >= 1.6}
    Rb = {"measured": [], "c2": [], "c": []}
    for p in crb.me.audit.load_passes():
        if p["id"] in flagged:
            continue
        a = rows_a[p["id"]]; site = sites[a["site"]]
        t = p["ridge"][:, 0] - float(a["shift_15C"])
        te, pos = crb.me.trajectory(p, site)
        ref = crb.me.reference(te, pos, crb.C)
        par = np.array([float(a["f0_15C"]), ref["v"], ref["R"], ref["tau"]])
        tg = np.arange(t[0], t[-1], HOP)
        sig = crb.RIDGE_SIGMA_PCT / 100 * par[0]
        for name, rho in (("measured", use), ("c2", c2), ("c", c)):
            Rb[name].append(float(crb.bound(tg, par, sig, np.asarray(rho))[2]))
    med = {k: float(np.median(v)) for k, v in Rb.items()}
    verdict = dict(n_eff_pooled=n_pooled, n_eff_c2=n_c2, n_eff_c=n_c,
                   match=("c2" if abs(n_pooled / n_c2 - 1) <= 0.2 else "c" if abs(n_pooled / n_c - 1) <= 0.2 else None),
                   bound_median_m=med, bound_in_63_74=63 <= med["measured"] <= 74, passes=len(Rb["measured"]),
                   bartlett_tapered=use is not pooled)
    U.write(run / "cov_bound.json", dict(cells=table, pooled_rho=pooled.tolist(), verdict=verdict,
                                         harris_c=c.tolist(), harris_c2=c2.tolist()))
    for cell, t in table.items():
        print(f"{cell:14s} sigma {t['sigma_hz']:.3f} Hz ({t['sigma_pct']:.3f} %)  N_eff {t['n_eff']:.2f}  frames {t['frames']}  "
              f"rho {np.round(t['rho'][1:5], 3).tolist()}")
    print("pooled rho", np.round(pooled, 3).tolist())
    print("Harris c ", np.round(c, 3).tolist()); print("Harris c2", np.round(c2, 3).tolist())
    print(verdict)
    return verdict


def n_eff4(rho):
    return float(1 + 2 * np.sum(np.asarray(rho)[1:5]))


def bound2(run: Path):
    import csv
    import scipy.linalg as sl
    crb = _crb()
    import hmm_livermore as HL
    import livermore_audit as LA
    from dopplertrack.doppler import speed_of_sound
    units = U.read_all(run / "cov", "*/seed_*.json")
    raw = autocorr([raw_errors(u) for u in units]); det = autocorr([fast_errors(u) for u in units])
    c, c2 = crb.HANN_C, crb.HANN_C ** 2
    n_raw, n_det, n_c, n_c2 = n_eff4(raw), n_eff4(det), n_eff4(c), n_eff4(c2)
    pairs = []                                                            # (SNR dB, sigma % of f0) per synthetic pass
    for u in units:
        geom, amp = u["cell"].rsplit("_", 1)
        x, fref, _, (f0, v, d) = WR.synth(geom, float(amp), u["seed"])
        sp = audio.compute_spectrogram(x, WR.SR)
        pairs.append((snr_on_curve(sp, fref, 5.0, WR.DUR - 5.0), 100 * float(np.std(raw_errors(u))) / f0))
    pairs.sort()
    snr_s, sig_s = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    use = raw
    if np.linalg.eigvalsh(sl.toeplitz(np.r_[raw, np.zeros(200)]))[0] < 0:
        use = raw * (1 - np.arange(LAGS + 1) / (LAGS + 1))
    HL._liv_init()
    rows_a = {r["id"]: r for r in csv.DictReader(open(crb.me.AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(crb.me.AUDIT / "sites.json"))["sites"]}
    flagged = {k for k, r in rows_a.items() if 100 * float(r["fit_rms_hz_15C"]) / float(r["f0_15C"]) >= 1.6}
    per, Rb = [], {"snr_sigma_raw_rho": [], "c2_045": [], "c_045": [], "raw_rho_045": []}
    for p in crb.me.audit.load_passes():
        if p["id"] in flagged:
            continue
        a = rows_a[p["id"]]; site = sites[a["site"]]
        q = HL._LIV["passes"][p["id"]]
        th, g, _, _, _ = LA.heard_curve(q, HL._LIV["sites"][a["site"]], speed_of_sound(15.0))
        shift, f0, start = float(a["shift_15C"]), float(a["f0_15C"]), float(a["start"])
        fref = lambda tt: f0 * np.interp(start + np.asarray(tt) - shift, th, g, left=np.nan, right=np.nan)
        x, _ = audio.load_audio(q["dir"] / "audio.wav", WR.SR)
        sp = audio.compute_spectrogram(x, WR.SR, fmax=1900.0)
        span = (q["ridge"][0, 0] - start, q["ridge"][-1, 0] - start)
        snr = snr_on_curve(sp, fref, *span)
        sig_pct = float(np.interp(snr, snr_s, sig_s))
        t = p["ridge"][:, 0] - float(a["shift_15C"])
        te, pos = crb.me.trajectory(p, site)
        ref = crb.me.reference(te, pos, crb.C)
        par = np.array([f0, ref["v"], ref["R"], ref["tau"]])
        tg = np.arange(t[0], t[-1], HOP)
        s045 = crb.RIDGE_SIGMA_PCT / 100 * f0
        Rb["snr_sigma_raw_rho"].append(float(crb.bound(tg, par, sig_pct / 100 * f0, use)[2]))
        Rb["raw_rho_045"].append(float(crb.bound(tg, par, s045, use)[2]))
        Rb["c2_045"].append(float(crb.bound(tg, par, s045, c2)[2]))
        Rb["c_045"].append(float(crb.bound(tg, par, s045, c)[2]))
        per.append(dict(id=p["id"], snr_db=snr, sigma_pct=sig_pct, R=float(par[2]), bound_m=Rb["snr_sigma_raw_rho"][-1]))
        print(p["id"], f"SNR {snr:.2f} dB  sigma {sig_pct:.3f} %  R {par[2]:.0f} m  bound {Rb['snr_sigma_raw_rho'][-1]:.1f} m", flush=True)
    med = {k: float(np.median(v)) for k, v in Rb.items()}
    m = med["snr_sigma_raw_rho"]
    verdict = dict(n_eff4_raw=n_raw, n_eff4_detrended=n_det, n_eff4_c2=n_c2, n_eff4_c=n_c,
                   rho_match=("c2" if abs(n_raw / n_c2 - 1) <= 0.2 else "c" if abs(n_raw / n_c - 1) <= 0.2 else None),
                   bound_median_m=med, bound_match=("63" if abs(m / 63 - 1) <= 0.15 else "74" if abs(m / 74 - 1) <= 0.15 else None),
                   sigma_pct_median=float(np.median([r["sigma_pct"] for r in per])), passes=len(per),
                   bartlett_tapered=use is not raw)
    U.write(run / "cov_bound2.json", dict(rho_raw=raw.tolist(), rho_detrended=det.tolist(), harris_c=c.tolist(),
                                          harris_c2=c2.tolist(), synthetic_snr_sigma=pairs, passes=per, verdict=verdict))
    print("rho raw      ", np.round(raw, 3).tolist()); print("rho detrended", np.round(det, 3).tolist())
    print("Harris c     ", np.round(c, 3).tolist()); print("Harris c2    ", np.round(c2, 3).tolist())
    print("synthetic (SNR dB, sigma %):", [(round(a, 2), round(b, 3)) for a, b in pairs])
    print(verdict)
    return verdict


if __name__ == "__main__":
    run, step = Path(sys.argv[1]), sys.argv[2]
    if step == "measure":
        measure(run, sys.argv[3:])
    elif step == "bound":
        bound(run)
    elif step == "bound2":
        bound2(run)
    else:
        sys.exit(__doc__)
