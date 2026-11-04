"""Does a private case's recording carry each nearby pass as broadband energy, where the tonal check hears two?

usage: broadband_site.py CASE SESSION_DIR KNOWN_POINT_DIR OUT_DIR [--max-ground-m 6000] [--null 200]
                         [--fmax HZ --spectrogram PATH]

The known-point check (known_point_site.py) scores each propeller pass by the brightness along its modelled
harmonic curve, on the whitened spectrogram. A person indoors hears the passes as a roar, which a harmonic-line
score need not see, and whitening removes part of a slow broadband rise. So here, for every airborne segment (any
type, jets included) whose closest approach to the site is within --max-ground-m of ground range during the
recording: the band power in 40 Hz to --fmax (450 by default) and in 40-100, 100-200 and 200-450 Hz (with 450-900
and 900-fmax for a wider band), on the UNWHITENED spectrogram (the session's FLACs, framed exactly as
session_spectrogram.py frames them at that fmax), over +-15 s of the predicted heard CPA, against the same 30 s power at
every centre 30-150 s from it on either side: z = (centre - median) / (1.4826 MAD), and the rise in dB. A pass is
marked when its 40-fmax z >= 3. With a wider band, --spectrogram names the case's whitened spectrogram built at the
same fmax (session_spectrogram.py --fmax), for the frame check and the pictures, and --known-point the known-point
run at that band. The traffic is dense (about one aircraft within 6 km every
80 s), so the same z at --null random times gives the share of times that are marked without any pass chosen; and
each pass carries how many other aircraft have a heard CPA within 30 s and 150 s of its own.

The ear's reference is the owner's: piston and unknown-type passes audible to about 3.5 km of ground range, turboprops
to about 2 km, each for 8-12 s; nothing beyond. Each propeller row says whether the ear would have heard it.

Pictures, for the two passes the tonal check heard and the four nearest the ear heard and it did not: the unwhitened
spectrogram over +-60 s and the window the tonal scorer sees, with the predicted curve at the tonal sweep's best tone
and shift overlaid (its 2nd and 3rd harmonics dashed). The per-pass table and the pictures go to OUT_DIR only, which
must be under $DOPPLERTRACK_DATA/private/: with public ADS-B they would place the site. The summary carries counts.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data"))
from bench import private as priv  # noqa: E402
from bench.cases import data_root, latest_case, resolve  # noqa: E402
from bench.runner import trace_paths  # noqa: E402
from dopplertrack.adsb import AircraftTypes, join_days  # noqa: E402
from dopplertrack.audio import Spectrogram, _band, _placed_blocks, _stft_db  # noqa: E402
from dopplertrack.doppler import speed_of_sound  # noqa: E402
from dopplertrack.score import modelled_curve  # noqa: E402
from dopplertrack.search import build_segments  # noqa: E402
from known_point_site import F0_SCALES, F_REF, SHIFTS, window  # noqa: E402
from session_spectrogram import recipe, session_files  # noqa: E402
HALF_S, NEAR_S, FAR_S = 15.0, 30.0, 150.0
Z_MARK = 3.0
EDGES = [0, 1000, 2000, 3500]


def bands(fmax: float) -> dict:
    """The marking band first (40 Hz to fmax), then the sub-bands that fit under fmax."""
    out = {f"40-{fmax:g}": (40.0, fmax)}
    for lo, hi in ((40.0, 100.0), (100.0, 200.0), (200.0, 450.0), (450.0, 900.0), (900.0, fmax)):
        if hi <= fmax and lo < hi and (lo, hi) != (40.0, fmax):
            out[f"{lo:g}-{hi:g}"] = (lo, hi)
    return out



def _json_default(o):
    """numpy scalars and arrays from the band sums, which json cannot encode by itself."""
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

def raw_spectrogram(session: Path, fmax: float = 450.0):
    """The session's spectrogram in dB, not whitened, on session_spectrogram.py's timeline and frames at fmax."""
    files, _ = session_files(session)
    r = recipe(fmax)
    SR, NPERSEG, HOP_S = r["sr"], r["nperseg"], r["hop_s"]
    x, gap = [], []
    for b, is_audio in _placed_blocks(files, SR, 0.01, 1 << 22):
        x.append(np.asarray(b, np.float32) if is_audio else np.zeros(len(b), np.float32))
        gap.append(np.full(len(b), not is_audio))
    x, g = np.concatenate(x), np.concatenate(gap)
    hop = int(round(HOP_S * SR))
    f, band = _band(SR, NPERSEG, r["fmin"], r["fmax"])
    K = (len(x) - NPERSEG) // hop + 1
    parts = [_stft_db(x[k0 * hop:(min(k0 + 16384, K) - 1) * hop + NPERSEG], SR, NPERSEG, hop, band)
             for k0 in range(0, K, 16384)]
    cg = np.concatenate([[0], np.cumsum(g)])
    s0 = np.arange(K) * hop
    return (NPERSEG / 2 + np.arange(K) * hop) / SR, f, np.concatenate(parts, axis=1), cg[s0 + NPERSEG] - cg[s0] == 0


def band_power(f, L, valid, BANDS):
    """Each band's linear mean power per frame; NaN on an invalid frame."""
    P = 10 ** (L.astype(np.float64) / 10)
    out = {}
    for name, (lo, hi) in BANDS.items():
        p = P[(f >= lo) & (f <= hi)].mean(axis=0)
        p[~valid] = np.nan
        out[name] = p
    return out


def window_means(p, dt):
    """The 30 s mean of p centred on every frame (NaN frames skipped; NaN where fewer than half are valid)."""
    w = int(round(2 * HALF_S / dt)) | 1
    ok = np.isfinite(p)
    s = np.convolve(np.where(ok, p, 0.0), np.ones(w), "same")
    n = np.convolve(ok.astype(float), np.ones(w), "same")
    return np.where(n >= w / 2, s / np.maximum(n, 1), np.nan)


def z_at(t, m, tc):
    """z and rise (dB) of the 30 s mean at tc against the 30 s means 30-150 s away on either side."""
    k = int(np.argmin(np.abs(t - tc)))
    d = np.abs(t - tc)
    bg = m[(d >= NEAR_S) & (d <= FAR_S)]
    bg = 10 * np.log10(bg[np.isfinite(bg) & (bg > 0)])
    if not np.isfinite(m[k]) or len(bg) < 50:
        return None, None
    c = 10 * np.log10(m[k])
    med = float(np.median(bg))
    mad = float(np.median(np.abs(bg - med)) * 1.4826)
    return (round((c - med) / mad, 2) if mad > 0 else None), round(c - med, 2)


def ear_audible(engine, ground_m):
    if engine == "jet":
        return None
    return ground_m <= (2000.0 if engine == "turboprop" else 3500.0)


def picture(path, t, f, L, sp, seg_curve, t_cpa, best, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t_obs, ratio, start = seg_curve
    shift, scale = best
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    m = (t >= t_cpa - 60) & (t <= t_cpa + 60)
    axes[0].pcolormesh(t[m] - t_cpa, f, L[:, m], shading="auto", cmap="magma",
                       vmin=np.percentile(L[:, m], 5), vmax=np.percentile(L[:, m], 99.5))
    axes[0].set_title("unwhitened dB")
    ew = window(sp, t_cpa, float(sp.f[-1]))
    w = ew.sp
    axes[1].pcolormesh(w.t - t_cpa, w.f, w.S, shading="auto", cmap="magma", vmin=0, vmax=np.percentile(w.S, 99.5))
    axes[1].set_title("what the tonal scorer sees (whitened, local median removed)")
    tt = t_obs - start + shift - t_cpa
    keep = np.abs(tt) <= 60
    for ax in axes:
        for h, ls in ((1, "-"), (2, "--"), (3, "--")):
            ax.plot(tt[keep], h * F_REF * scale * ratio[keep], ls, color="cyan", lw=0.8, alpha=0.8)
        ax.axvline(0, color="white", lw=0.6, alpha=0.6)
        ax.set_xlabel("s from the predicted heard CPA")
        ax.set_ylim(40, float(f[-1]))
    axes[0].set_ylabel("Hz")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case"); ap.add_argument("session", type=Path); ap.add_argument("known_point", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--max-ground-m", type=float, default=6000.0); ap.add_argument("--null", type=int, default=200)
    ap.add_argument("--fmax", type=float, default=450.0, help="the band's upper edge, Hz (default 450)")
    ap.add_argument("--spectrogram", help="the case's whitened spectrogram at --fmax (default the case's own)")
    a = ap.parse_args()
    if not a.out.resolve().is_relative_to((data_root() / "private").resolve()):
        sys.exit(f"{a.out} is not under {data_root() / 'private'}: the per-pass table would place the site")
    case = priv.resolve_case(latest_case(a.case))
    site = priv.load_site(case["site"])
    sp = Spectrogram.load(resolve(a.spectrogram or case["spectrogram"]))
    BANDS = bands(a.fmax)
    MARK = next(iter(BANDS))
    t, f, L, valid = raw_spectrogram(a.session, a.fmax)
    if len(t) != len(sp.t) or not np.allclose(t, sp.t) or len(f) != len(sp.f):
        sys.exit("the unwhitened frames don't match the case's spectrogram")
    start = datetime.datetime.fromisoformat(case["start_time"]["utc"].replace("Z", "+00:00")).timestamp()
    t0, t1 = start + float(t[0]), start + float(t[-1])
    dt = float(t[1] - t[0])
    means = {k: window_means(p, dt) for k, p in band_power(f, L, valid, BANDS).items()}
    types = AircraftTypes()
    traces = join_days(trace_paths(case))[0]
    segs = build_segments(traces, site["lat"], site["lon"])
    obs = np.array([0.0, 0.0, site["elev_m"]])
    c = speed_of_sound()
    passes = []
    for seg in segs:
        ground = np.hypot(seg.enu[:, 0], seg.enu[:, 1])
        k = int(np.argmin(ground))
        if ground[k] > a.max_ground_m or not (t0 <= seg.t[k] <= t1):
            continue
        t_obs, ratio = modelled_curve(seg, obs, c)
        t_cpa = float(np.interp(seg.t[k], seg.t, t_obs)) - start
        if not (t[0] + 60.0 <= t_cpa <= t[-1] - 60.0):        # the known point's margin; a background may be one-sided
            continue
        typ = traces[seg.trace_idx].typ
        e = types.engine(typ)
        engine = ("jet" if not types.is_prop(typ) else "piston" if e and "Piston" in e
                  else "turboprop" if e and "Turbo" in e else "unknown")
        passes.append((seg, t_obs, ratio, t_cpa, float(ground[k]), engine))
    cpas = np.array([p[3] for p in passes])
    known = {(r["icao"], r["cpa_audio_s"]): r for r in json.loads((a.known_point / "known_point_passes.json").read_text())}
    rows = []
    for seg, t_obs, ratio, t_cpa, ground, engine in passes:
        row = {"icao": seg.icao, "engine": engine, "cpa_audio_s": round(t_cpa, 1), "ground_m": round(ground, 0),
               "others_30s": int((np.abs(cpas - t_cpa) <= 30).sum() - 1),
               "others_150s": int((np.abs(cpas - t_cpa) <= 150).sum() - 1),
               "ear_audible": ear_audible(engine, ground)}
        for name, m in means.items():
            row[f"z_{name}"], row[f"rise_db_{name}"] = z_at(t, m, t_cpa)
        z = row[f"z_{MARK}"]
        row["marked"] = bool(z is not None and z >= Z_MARK)
        kp = known.get((seg.icao, round(t_cpa, 1)))
        row["tonal_heard"] = None if kp is None else kp["heard"]
        row["tonal_z"] = None if kp is None else kp["z"]
        rows.append(row)
    rng = np.random.default_rng(20261104)
    null = [z_at(t, means[MARK], tc)[0] for tc in rng.uniform(t[0] + FAR_S, t[-1] - FAR_S, a.null)]
    null = [z for z in null if z is not None]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "broadband_passes.json").write_text(json.dumps(rows, indent=1, default=_json_default) + "\n")    # private: never in git
    # pictures: the tonal check's heard passes, and the four nearest unheard passes the ear heard
    props = [(r, p) for r, p in zip(rows, passes) if r["engine"] != "jet"]
    pick = [x for x in props if x[0]["tonal_heard"]]
    pick += sorted((x for x in props if x[0]["ear_audible"] and x[0]["tonal_heard"] is False),
                   key=lambda x: x[0]["ground_m"])[:4]
    for i, (r, (seg, t_obs, ratio, t_cpa, ground, engine)) in enumerate(pick):
        sc = window(sp, t_cpa, a.fmax).sweep_scores(t_obs - start, ratio, SHIFTS, F0_SCALES)
        si, fi = np.unravel_index(int(np.argmax(sc)), sc.shape)
        picture(a.out / f"pass-{i + 1}.png", t, f, L, sp, (t_obs, ratio, start), t_cpa,
                (float(SHIFTS[si]), float(F0_SCALES[fi])),
                f"pass {i + 1}: {engine}, {ground / 1000:.1f} km ground; tonal {'heard' if r['tonal_heard'] else 'not heard'}"
                f" (z {r['tonal_z']}), broadband z {r[f'z_{MARK}']}; best tone {F_REF * F0_SCALES[fi]:.0f} Hz")
        r["picture"] = f"pass-{i + 1}.png"
    (a.out / "broadband_passes.json").write_text(json.dumps(rows, indent=1, default=_json_default) + "\n")

    def tally(rs):
        zs = [r[f"z_{MARK}"] for r in rs if r[f"z_{MARK}"] is not None]
        return {"passes": len(rs), "marked": sum(r["marked"] for r in rs),
                "tonal_heard": sum(bool(r["tonal_heard"]) for r in rs),
                "median_z": round(float(np.median(zs)), 2) if zs else None,
                "marked_by_band": {b: sum((r[f"z_{b}"] or 0) >= Z_MARK for r in rs) for b in BANDS},
                "median_rise_db": round(float(np.median([r[f"rise_db_{MARK}"] for r in rs
                                                         if r[f"rise_db_{MARK}"] is not None] or [np.nan])), 2)}
    edges = EDGES + [a.max_ground_m]
    summary = {"case": a.case, "z_mark": Z_MARK, "mark_band_hz": MARK, "bands_hz": list(BANDS), "fmax_hz": a.fmax,
               "recipe": recipe(a.fmax),
               "null": {"times": len(null), "marked_share": round(float(np.mean(np.array(null) >= Z_MARK)), 3),
                        "median_z": round(float(np.median(null)), 2)},
               "by_class": {}, "ear": {}}
    for cls in ("piston", "unknown", "turboprop", "jet"):
        rs = [r for r in rows if r["engine"] == cls]
        summary["by_class"][cls] = [{"from": lo, "to": hi, **tally([r for r in rs if lo <= r["ground_m"] < hi])}
                                    for lo, hi in zip(edges[:-1], edges[1:])]
    for k, v in (("ear_audible", True), ("ear_inaudible", False)):
        summary["ear"][k] = tally([r for r in rows if r["ear_audible"] is v])
    summary["pictures"] = len(pick)
    (a.out / "broadband_summary.json").write_text(json.dumps(summary, indent=1, default=_json_default) + "\n")
    print(json.dumps(summary, default=_json_default))


if __name__ == "__main__":
    main()
