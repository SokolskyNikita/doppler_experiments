"""Why did the find choose another line? (docs/experiments/2026-11-04-event-fit.md: method and criterion written before the
run.) One shards.py unit over the two wrong finds, Oyster Bay event 2 and the eagle cam's event 2:
  - the true flight's heard curve (ADS-B, known point, 15 C) with f0 and the clock chosen to maximise the find's own objective
    (brightness for Oyster Bay, detect's sweep-weighted contrast for the eagle cam) on local_whiten of the stored spectrogram;
  - its presence: a track gated +-3 bins around it on the original STFT, the share of frames >= 6 dB above the local noise;
  - the found line's score (the committed fit) and fit_event's own best in the window under the same objective;
  - what the found line is: f0 and heard CPA against the true line's, the frequency ratio, and which flight in the box its
    gated track follows best (f0 and clock +-20 s free, by RMS).
Criterion: the true line present on >= half the frames, and the objective scores the found line higher.

usage: uv run python tools/experiments/2026-11-04/find_test.py [RUN] [--shard K/N] [--resume DIR ...] [--merge] [--inputs]
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "tools/data"))
import shards  # noqa: E402
from bench import cases, runner  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


gt, ov = _load("gated_track"), _load("overlay_truth")
GATE_BINS = 3
EVENTS = {"oyster-bay": dict(k=2, band=(95.0, 195.0), objective="brightness"),
          "eagle-cam-clip-18000s": dict(k=2, band=(60.0, 300.0), objective="contrast")}


def objective_fn(sp, t0w, t1w, f_lo, f_hi, objective):
    from dopplertrack.tracks import curve_contrast, local_whiten, sweep_weights
    pad = 0.3 * (f_hi - f_lo)
    win = local_whiten(sp.crop(t0w - 30, t1w + 30, max(f_lo - pad, sp.f[0]), min(f_hi + pad, sp.f[-1])))
    tt = np.linspace(t0w, t1w, 400)

    def score(f):
        if not np.all(np.isfinite(f)):
            return -np.inf
        if objective == "brightness":
            return float(np.mean(win.sample(tt, f)))
        w = sweep_weights(f / np.nanmedian(f), tt)
        return float(np.sum(w * curve_contrast(win, tt, f)) / np.sum(w))
    return tt, score


def gated_presence(case, t0w, t1w, gate_fn):
    """Share of frames whose peak within +-3 bins of gate_fn(t) on the original STFT is >= 6 dB above the local noise."""
    from dopplertrack.audio import _band, _stft_db
    x = gt.audio(case)
    hop = int(round(gt.HOP_S * gt.SR))
    k0 = int(np.ceil((t0w * gt.SR - gt.NPERSEG / 2) / hop)); k1 = int(np.floor((t1w * gt.SR - gt.NPERSEG / 2) / hop)) + 1
    f, band = _band(gt.SR, gt.NPERSEG, 40.0, 450.0)
    L = _stft_db(x[k0 * hop:(k1 - 1) * hop + gt.NPERSEG], gt.SR, gt.NPERSEG, hop, band)
    t = (gt.NPERSEG / 2 + np.arange(k0, k1) * hop) / gt.SR
    gate = gate_fn(t); df = float(f[1] - f[0])
    snr = []
    for k in range(len(t)):
        if not np.isfinite(gate[k]):
            snr.append(np.nan); continue
        j = int(round((gate[k] - f[0]) / df))
        lo, hi = max(1, j - GATE_BINS), min(len(f) - 2, j + GATE_BINS)
        col = L[:, k]
        idx = np.r_[max(0, j - gt.NOISE_HALF):max(0, j - gt.NOISE_EXCL), min(len(f), j + gt.NOISE_EXCL + 1):min(len(f), j + gt.NOISE_HALF + 1)]
        snr.append(float(col[lo:hi + 1].max() - np.median(col[idx])) if hi > lo and len(idx) else np.nan)
    snr = np.array(snr)
    ok = np.isfinite(snr)
    return dict(frames=int(ok.sum()), share_ge_6db=float(np.mean(snr[ok] >= gt.MARGIN_DB)) if ok.any() else 0.0,
                median_snr_db=float(np.nanmedian(snr)) if ok.any() else None)


def heard_cpa(t_audio, ratio_audio):
    """The heard CPA: where the curve crosses its rest frequency (ratio 1), nearest the window's middle."""
    s = np.sign(ratio_audio - 1.0)
    idx = np.where(np.isfinite(s[:-1]) & np.isfinite(s[1:]) & (s[:-1] != s[1:]))[0]
    if not len(idx):
        return None
    i = idx[np.argmin(np.abs(idx - len(t_audio) / 2))]
    a, b = ratio_audio[i] - 1, ratio_audio[i + 1] - 1
    return float(t_audio[i] + (t_audio[i + 1] - t_audio[i]) * a / (a - b))


def one(cid):
    from dopplertrack.adsb import join_days
    from dopplertrack.audio import Spectrogram
    from dopplertrack.doppler import ideal_curve, speed_of_sound
    from dopplertrack.score import modelled_curve
    from dopplertrack.search import build_segments
    from dopplertrack.terrain import Terrain
    from dopplertrack.tracks import fit_event
    spec = EVENTS[cid]
    blind, full = cases.blind_case(cid), cases.latest_case(cid)
    ev = runner.saved_fit_dicts(blind)[spec["k"] - 1]
    icao = cases.case_labels(cid, full["version"])["true_pair"][spec["k"] - 1]
    sp = Spectrogram.load(runner.resolve(blind["spectrogram"]))
    t0w, t1w = ev["t_start"], ev["t_end"]
    f_lo, f_hi = spec["band"]
    c = speed_of_sound(15.0)
    tt, score = objective_fn(sp, t0w, t1w, f_lo, f_hi, spec["objective"])
    found_curve = lambda t: ideal_curve(t, ev["f0"], ev["v"], ev["d"], ev["t_cpa_emit"], c=c)  # noqa: E731
    s_found = score(found_curve(tt))
    best_window = fit_event(sp, t0w, t1w, f_lo, f_hi, c=c, objective=spec["objective"])
    t_curve, ratio, _ = ov.true_curve(full, icao)
    clock0 = ov.audio_zero(full)
    best = (-np.inf, None, None)
    for dlt in np.arange(-30.0, 30.01, 0.5):
        r = np.interp(tt + clock0 + dlt, t_curve, ratio, left=np.nan, right=np.nan)
        if not np.all(np.isfinite(r)):
            continue
        for f0 in np.arange(f_lo, f_hi + 0.01, 0.25):
            sc = score(f0 * r)
            if sc > best[0]:
                best = (sc, float(f0), float(dlt))
    s_true, f0_true, d_true = best
    true_fn = lambda t: f0_true * np.interp(t + clock0 + d_true, t_curve, ratio, left=np.nan, right=np.nan)  # noqa: E731
    presence = gated_presence(blind, t0w, t1w, true_fn) if f0_true else None
    ta = np.linspace(t0w - 60, t1w + 60, 2401)
    cpa_true = heard_cpa(ta, np.interp(ta + clock0 + d_true, t_curve, ratio, left=np.nan, right=np.nan)) if f0_true else None
    # which flight in the box the found line's gated track follows best
    (tr, _), _ = gt.tracks(blind, GATE_BINS)[spec["k"] - 1]
    tt_tr, g, _ = tr.usable()
    ref = cases.case_labels(cid, full["version"])["reference"]
    lat, lon = float(ref["lat"]), float(ref["lon"])
    elev = float(Terrain().elevation(np.array([lat]), np.array([lon]))[0]) if full["search"]["dem"] else 0.0
    traces, _ = join_days(runner.trace_paths(full))
    segs = build_segments(traces, lat, lon)
    obs = np.array([0.0, 0.0, elev])
    lo_u, hi_u = clock0 + t0w - 120, clock0 + t1w + 120
    by_icao = {}
    for s in segs:
        rng = np.linalg.norm(s.enu - obs, axis=1)
        k = int(np.argmin(rng))
        if rng[k] <= 15000 and lo_u <= s.t[k] + rng[k] / c <= hi_u:
            to, rr = modelled_curve(s, obs, c)
            by_icao.setdefault(s.icao, []).append((to, rr, float(rng[k])))
    matches = []
    for ic, parts in by_icao.items():
        to = np.concatenate([p[0] for p in parts]); rr = np.concatenate([p[1] for p in parts]); o = np.argsort(to)
        best_m = None
        for dlt in np.arange(-20.0, 20.01, 0.5):
            r = np.interp(tt_tr + clock0 + dlt, to[o], rr[o], left=np.nan, right=np.nan)
            ok = np.isfinite(r)
            if ok.sum() < 0.8 * len(tt_tr):
                continue
            f0 = float(np.dot(g[ok], r[ok]) / np.dot(r[ok], r[ok])); rms = float(np.sqrt(np.mean((g[ok] - f0 * r[ok]) ** 2)))
            if best_m is None or rms < best_m[0]:
                best_m = (rms, f0, float(dlt))
        if best_m:
            matches.append(dict(icao=ic, rms_hz=best_m[0], f0=best_m[1], clock_s=best_m[2], min_range_m=min(p[2] for p in parts),
                                is_true=ic == icao))
    matches.sort(key=lambda m: m["rms_hz"])
    return dict(case=cid, event=spec["k"], true_icao=icao, objective=spec["objective"], window=[t0w, t1w], band=[f_lo, f_hi],
                found=dict(f0=ev["f0"], v=ev["v"], d=ev["d"], t_cpa=ev["t_cpa"], score=s_found),
                window_best=dict(f0=best_window.f0, v=best_window.v, d=best_window.d, t_cpa=best_window.t_cpa, score=best_window.score),
                true_line=dict(f0=f0_true, clock_offset_s=d_true, score=s_true, t_cpa=cpa_true, presence=presence),
                found_over_true_f0=ev["f0"] / f0_true if f0_true else None,
                found_track_best_flights=matches[:6], n_flights_considered=len(matches),
                criterion=dict(true_present_half=bool(presence and presence["share_ge_6db"] >= 0.5), found_scores_higher=bool(s_found > s_true)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    a = ap.parse_args()
    if a.inputs:
        from bench import inputs as bench_inputs
        doc = bench_inputs.run_inputs(list(EVENTS), "saved-fit")
        extra = [cases.latest_case(c)["audio"]["path"] for c in EVENTS]
        shards.print_inputs(doc["cases"], list(dict.fromkeys(doc["inputs"] + extra)), [], tuple(doc["cache_kinds"]))
        return
    params = dict(events=EVENTS, f0_step=0.25, clock=[-30, 30, 0.5], gate_bins=3, margin_db=6.0, flights_within_m=15000)
    run = shards.open_run(a.run, "find-test", {"script": "tools/experiments/2026-11-04/find_test.py", "params": params})
    units = shards.Units(run, ["find"], params, a.shard, a.resume)
    if not a.merge and units.todo():
        d = units.dir("find"); d.mkdir(parents=True, exist_ok=True)
        rows = [one(cid) for cid in EVENTS]
        (d / "result.json").write_text(json.dumps(rows, indent=1, default=float) + "\n")
        units.finish("find", {r["case"]: r["criterion"] for r in rows})
    rows = json.loads((units.all()["find"] / "result.json").read_text())
    (run / "find_test.json").write_text(json.dumps(rows, indent=1, default=float) + "\n")
    print(json.dumps(rows, indent=1, default=float))


if __name__ == "__main__":
    main()
