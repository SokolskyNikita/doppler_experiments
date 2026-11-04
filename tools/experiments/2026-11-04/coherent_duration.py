"""Coherent alignment duration for weak flyovers (docs/proposals/2026-11-04-coherent-duration.md).

Methods, on the same 18 s of audio and the same search per candidate (clock +-10 s in 0.25 s steps, a constant pitch
over the pass's third-octave band, no drift):
  C1, C3, C9  the audio resampled to emission time for the candidate (warp.py), split into 9, 3 or 1 blocks, each
              block's power spectrum on one fine grid, powers added across blocks: the best pitch's sum over the
              background's median in the band +-20 Hz
  T           today's kind of score: the 2.048 s, 0.25 s-hop spectrogram's power along the candidate's modelled
              Doppler curve, each frame over the background's median in the band +-20 Hz, averaged over the frames,
              best pitch
Everything is linear in the audio, so each (candidate, clock) is warped and transformed once for the background and
once for the clip, and every level g follows as a + g^2 b + 2 g c. The medians are the background's (the tone fills
a handful of bins), the same for every method and for calibration.

Stages (each a run of tools/data/shards.py units):
  plan     local: the background spans' 40 s segments (alternately calibration and evaluation) and each pass's seeded
           calibration and evaluation segments -> coherent_duration_plan.json beside this file
  prep     each span's band power per segment, for the four bands; merged into RUN/bands.json
  gates    gate 1 (exact synthetic tone along the true track) and gate 2 (the real clip), on the 8 verification
           passes, true flight and clock supplied: calibration and evaluation units
  test     the 19 test passes, blind: candidates are the true flight, the real prop traffic within 12 km and +-30 min
           (set A) and the other 26 passes' tracks (set B), each with the same freedom

usage, from the repo root:
  coherent_duration.py plan
  coherent_duration.py [RUN] --stage prep|gates|test [--bands PREP_RUN] [--shard K/N] [--resume DIR ...] [--merge]
                       [--inputs]"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "data"))
import nnumber                                                     # noqa: E402
import shards                                                      # noqa: E402

DATA = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
PLAN = Path(__file__).with_name("coherent_duration_plan.json")
AUDIT = "runs/2026-11-04-livermore-audit"
COHERENCE = "runs/2026-11-04-real-tone-coherence/results.csv"
SR = 2000
SEG_S = 40.0                    # background segment; the clip's heard CPA sits at its middle
WIN_S = 18.0
A0 = SEG_S / 2
CLOCKS = np.arange(-10.0, 10.0 + 1e-9, 0.25)
LEVELS = np.arange(12, -19, -1)  # added clip band power against the background, dB
BLOCKS = {"C1": 9, "C3": 3, "C9": 1}
METHODS = ["C1", "C3", "C9", "T"]
NFFT = 4 * int(WIN_S * SR)      # one fine pitch grid for every block length
MEDIAN_HZ = 20.0
T_NPERSEG, T_HOP = 4096, 500    # 2.048 s and 0.25 s at 2 kHz
T_F0_STEP = 0.25
RANGE_M, WINDOW_TRAFFIC_S = 12000.0, 1800.0
N_CAL, N_EVAL = 200, 10
SEED = 20261104
VERIFY = ["N373DF_R06", "N4004R_R19", "N60RS_R11", "N61NG_R37", "N662EZ_R48", "N784MB_R04", "N795MM_R13", "N913TC_R15"]
JET = "N958JX_R50"
BANDS = [200, 250, 315, 400]
SPANS = {   # Tier 1's development background spans: id -> data-root path of the audio
    "xc990819": "raw/audio/xenocanto/XC990819_2025-04-20_0510.mp3",
    "xc990820": "raw/audio/xenocanto/XC990820_2025-04-20_0510.mp3",
    "xc986433": "raw/audio/xenocanto/XC986433_2025-04-07_0545.mp3",
    **{f"aerosonicdb-env-{k}": f"derived/background/aerosonicdb_env_{k}.wav" for k in range(1, 7)}}


def c_15():
    from dopplertrack.doppler import speed_of_sound
    return speed_of_sound(15.0)


# ---- passes and candidates ----------------------------------------------------------------------------

def passes() -> dict:
    """The 27 props of the coherence diagnostic, with the audit's timing and site."""
    coh = {r["id"]: r for r in csv.DictReader(open(DATA / COHERENCE)) if r["template"] == "adsb"}
    audit = {r["id"]: r for r in csv.DictReader(open(DATA / AUDIT / "passes.csv"))}
    sites = {s["name"]: s for s in json.load(open(DATA / AUDIT / "sites.json"))["sites"]}
    out = {}
    for pid, r in coh.items():
        if pid == JET:
            continue
        a = audit[pid]
        out[pid] = {"id": pid, "day": a["day"], "category": a["category"], "site": sites[a["site"]],
                    "start": float(a["start"]), "heard": float(a["heard_cpa_utc_15C"]), "emit": float(a["emit_cpa_utc"]),
                    "freq": float(r["frequency_Hz"]), "band": int(r["third_octave_Hz"])}
    return out


def kml_track(path: Path):
    s = path.read_text()
    t = np.array([np.datetime64(w.rstrip("Z")).astype("datetime64[ns]").astype(np.int64) / 1e9
                  for w in re.findall(r"<when\s*>([^<]+)</when>", s)])
    c = np.array([[float(x) for x in v.split()] for v in re.findall(r"<gx:coord\s*>([^<]+)</gx:coord>", s)])
    keep = np.r_[True, np.diff(t) > 0]
    return t[keep], c[keep, 1], c[keep, 0], c[keep, 2]


def site_enu(site: dict):
    from dopplertrack.terrain import Terrain
    return site["lat"], site["lon"], float(Terrain().elevation([site["lat"]], [site["lon"]])[0])


def candidate(name, t, lat, lon, alt, site, c):
    from dopplertrack.geo import lla_to_enu
    lat0, lon0, alt0 = site
    enu = lla_to_enu(lat, lon, alt, lat0, lon0, alt0)
    r = np.linalg.norm(enu, axis=1)
    k = int(np.argmin(r))
    return {"name": name, "t": t, "enu": enu, "emit": float(t[k]), "heard": float(t[k] + r[k] / c), "r_min": float(r[k])}


def pass_dir(p):
    return DATA / "derived/livermore" / p["category"] / p["id"]


def candidates(p, allp, c, with_traffic: bool):
    """[true, set A (traffic)..., set B (other passes' tracks)...] and each one's set label."""
    from dopplertrack.adsb import load_traces
    site = site_enu(p["site"])
    true = candidate(p["id"], *kml_track(next(pass_dir(p).glob("*.kml"))), site, c)
    out, sets = [true], ["true"]
    if not with_traffic:
        return out, sets
    reg = p["id"].split("_")[0]
    own = nnumber.icao(reg)
    for tr in load_traces(DATA / f"derived/traces/{p['day']}/livermore_margin12.npz"):
        if tr.icao == own or len(tr.t) < 4:
            continue
        ok = ~np.asarray(tr.on_ground, bool) & np.isfinite(tr.alt)
        if ok.sum() < 4:
            continue
        cand = candidate(tr.icao, tr.t[ok], tr.lat[ok], tr.lon[ok], tr.alt[ok], site, c)
        if cand["r_min"] <= RANGE_M and abs(cand["heard"] - p["heard"]) <= WINDOW_TRAFFIC_S:
            out.append(cand); sets.append("A")
    for q in allp.values():
        if q["id"] != p["id"]:
            out.append(candidate(q["id"], *kml_track(next(pass_dir(q).glob("*.kml"))), site, c)); sets.append("B")
    return out, sets


# ---- audio ---------------------------------------------------------------------------------------------

def decode(path: Path, start: float, dur: float) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(path), "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).astype(np.float64)
    n = int(round(dur * SR))
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def band_edges(fc):
    return fc * 2 ** (-1 / 6), fc * 2 ** (1 / 6)


def band_power(x, fc):
    from scipy.signal import welch
    f, P = welch(x, SR, nperseg=4096)
    lo, hi = band_edges(fc)
    return float(P[(f >= lo) & (f < hi)].sum() * (f[1] - f[0]))


def clip_audio(p) -> np.ndarray:
    """The pass's 18 s around its heard CPA, placed with that CPA at A0 of a silent segment."""
    h = p["heard"] - p["start"]
    x = decode(pass_dir(p) / "audio.wav", h - WIN_S / 2, WIN_S)
    seg = np.zeros(int(SEG_S * SR))
    i0 = int(round((A0 - WIN_S / 2) * SR))
    seg[i0:i0 + len(x)] = x
    return seg


def synthetic_clip(p, true, c) -> np.ndarray:
    """An exact constant-pitch tone at the pass's frequency along the true track, heard CPA at A0, 18 s long."""
    a = np.arange(int(SEG_S * SR)) / SR
    t = a - A0 + true["heard"]                       # UTC of each audio sample, true clock
    u = t.copy()
    for _ in range(4):                                # reception t = u + r(u)/c
        r = np.linalg.norm(np.stack([np.interp(u, true["t"], true["enu"][:, k]) for k in range(3)], 1), axis=1)
        u = t - r / c
    s = np.cos(2 * np.pi * p["freq"] * (u - true["emit"]))
    s[np.abs(a - A0) > WIN_S / 2] = 0.0
    return s


# ---- the statistics -------------------------------------------------------------------------------------

_S: dict = {}


def _init(state):
    _S.clear(); _S.update(state)


def _spectra(y, n):
    y = np.nan_to_num(y)
    L = len(y) // n
    return np.fft.rfft(y[:L * n].reshape(n, L), NFFT, axis=1)


def _cand_stats(k):
    """Per method: per clock offset, the (a, b, c) power terms at the best pitch are level dependent, so return for
    each clock the arrays needed to form every level's statistic: max over pitch of (a + g^2 b + 2 g c) / median."""
    from dopplertrack.warp import warp
    st = _S
    cand, c = st["cands"][k], st["c"]
    bg, clip, lo, hi = st["bg"], st["clip"], st["lo"], st["hi"]
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    sel = (f >= lo - MEDIAN_HZ) & (f <= hi + MEDIAN_HZ)
    inb = (f[sel] >= lo) & (f[sel] <= hi)
    g = st["g"]                                       # (levels,) amplitude gains, [0] for calibration
    out = {m: np.full((len(st["clocks"]), len(g)), np.nan) for m in METHODS}
    # T: one STFT of the segment, shared by every candidate and clock
    Sb, Sc, tf, ff, medT = st["T"]
    f0s = np.arange(lo, hi, T_F0_STEP)
    for ci, d in enumerate(st["clocks"]):
        amt = A0 + d - cand["heard"]                  # audio minus UTC under this clock
        u0, u1 = cand["emit"] - WIN_S / 2, cand["emit"] + WIN_S / 2
        try:
            wb = warp(bg, SR, amt, cand["t"], cand["enu"], np.zeros(3), c, u0, u1, max_rate=1.6, prefiltered=True)
            if np.mean(np.isfinite(wb.y)) < 0.9:
                continue
            wc = warp(clip, SR, amt, cand["t"], cand["enu"], np.zeros(3), c, u0, u1, max_rate=1.6, prefiltered=True) \
                if clip is not None else None
        except ValueError:
            continue
        for m, n in BLOCKS.items():
            A = _spectra(wb.y, n)[:, sel]
            a = (np.abs(A) ** 2).sum(0)
            med = np.median(a)
            if wc is None:
                out[m][ci] = (a[inb] / med).max()
                continue
            B = _spectra(wc.y, n)[:, sel]
            b = (np.abs(B) ** 2).sum(0); cc = (A * np.conj(B)).real.sum(0)
            P = a[None, inb] + g[:, None] ** 2 * b[None, inb] + 2 * g[:, None] * cc[None, inb]
            out[m][ci] = P.max(1) / med
        # T: the modelled Doppler curve at each frame's reception time
        fr = (tf >= A0 + d - WIN_S / 2) & (tf <= A0 + d + WIN_S / 2)
        t_utc = tf[fr] - amt
        u = t_utc.copy()
        for _ in range(3):
            p3 = np.stack([np.interp(u, cand["t"], cand["enu"][:, k]) for k in range(3)], 1)
            u = t_utc - np.linalg.norm(p3, axis=1) / c
        if u.min() < cand["t"][0] or u.max() > cand["t"][-1]:
            continue
        p3 = np.stack([np.interp(u, cand["t"], cand["enu"][:, k]) for k in range(3)], 1)
        v3 = np.stack([np.interp(u, cand["t"], np.gradient(cand["enu"][:, k], cand["t"])) for k in range(3)], 1)
        rdot = (p3 * v3).sum(1) / np.linalg.norm(p3, axis=1)
        ratio = 1.0 / (1.0 + rdot / c)                                   # received / emitted
        idx = np.clip(np.rint(f0s[:, None] * ratio[None, :] / (ff[1] - ff[0])).astype(int), 0, len(ff) - 1)
        rows = np.flatnonzero(fr)
        Pb = (np.abs(Sb[rows]) ** 2)[np.arange(len(rows))[None, :], idx] / medT[rows][None, :]
        if Sc is None:
            out["T"][ci] = Pb.mean(1).max()
            continue
        Xb, Xc = Sb[rows][np.arange(len(rows))[None, :], idx], Sc[rows][np.arange(len(rows))[None, :], idx]
        Pc = (np.abs(Xc) ** 2) / medT[rows][None, :]
        Pbc = (Xb * np.conj(Xc)).real / medT[rows][None, :]
        P = Pb.mean(1)[None, :] + g[:, None] ** 2 * Pc.mean(1)[None, :] + 2 * g[:, None] * Pbc.mean(1)[None, :]
        out["T"][ci] = P.max(1)
    return {m: np.nanmax(v, axis=0) if np.isfinite(v).any() else np.full(len(g), np.nan) for m, v in out.items()}


def stats_for(bg, clip, g, cands, clocks, lo, hi, c, jobs):
    """(method, level, candidate) maxima over clock and pitch."""
    from scipy.signal import stft
    from dopplertrack.parallel import ordered_map
    from dopplertrack.warp import lowpass
    bgf = lowpass(bg, SR, SR / (2 * 1.6))
    clf = lowpass(clip, SR, SR / (2 * 1.6)) if clip is not None else None
    ff, tf, Sb = stft(bg, SR, window="hann", nperseg=T_NPERSEG, noverlap=T_NPERSEG - T_HOP, boundary=None, padded=False)
    Sc = stft(clip, SR, window="hann", nperseg=T_NPERSEG, noverlap=T_NPERSEG - T_HOP, boundary=None, padded=False)[2] \
        if clip is not None else None
    tf = tf.copy()
    bandm = (ff >= lo - MEDIAN_HZ) & (ff <= hi + MEDIAN_HZ)
    medT = np.median(np.abs(Sb[bandm]) ** 2, axis=0)
    state = {"cands": cands, "c": c, "bg": bgf, "clip": clf, "lo": lo, "hi": hi, "g": g, "clocks": clocks,
             "T": (Sb.T, None if Sc is None else Sc.T, tf, ff, medT)}
    res = list(ordered_map(_cand_stats, range(len(cands)), jobs, _init, (state,)))
    return np.stack([np.stack([r[m] for r in res], axis=1) for m in METHODS])      # (method, level, candidate)


# ---- plan, prep and the units ---------------------------------------------------------------------------

def plan():
    rng = np.random.default_rng(SEED)
    segs = []
    for sid, rel in SPANS.items():
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(DATA / rel)], capture_output=True, text=True, check=True).stdout)
        for k in range(int(dur // SEG_S)):
            segs.append({"span": sid, "path": rel, "start": k * SEG_S, "role": "cal" if k % 2 == 0 else "eval"})
    allp = passes()
    cal = [i for i, s in enumerate(segs) if s["role"] == "cal"]
    ev = [i for i, s in enumerate(segs) if s["role"] == "eval"]
    sel = {pid: {"cal": sorted(int(x) for x in rng.choice(cal, min(N_CAL, len(cal)), replace=False)),
                 "eval": sorted(int(x) for x in rng.choice(ev, N_EVAL, replace=False))} for pid in sorted(allp)}
    out = {"seed": SEED, "segment_s": SEG_S, "segments": segs, "passes": sorted(allp), "verify": VERIFY,
           "test": sorted(set(allp) - set(VERIFY)), "selection": sel}
    PLAN.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(segs)} segments ({len(cal)} cal, {len(ev)} eval), {len(allp)} passes -> {PLAN}")


def units_for(stage, pl):
    if stage == "prep":
        return [f"prep--{s}" for s in SPANS]
    names = pl["verify"] if stage == "gates" else pl["test"]
    modes = ["synthetic", "assisted"] if stage == "gates" else ["blind"]
    out = []
    for m in modes:
        for pid in names:
            out += [f"{m}--{pid}--cal--{i}" for i in range(0, N_CAL, 20)]           # 20 segments per unit
            out += [f"{m}--{pid}--eval--{j}" for j in range(N_EVAL)]
    return out


def run_unit(uid, pl, bands, d: Path, jobs):
    allp, c = passes(), c_15()
    if uid.startswith("prep--"):
        sid = uid.split("--")[1]
        rows = [(i, s) for i, s in enumerate(pl["segments"]) if s["span"] == sid]
        res = {str(i): {str(fc): band_power(decode(DATA / s["path"], s["start"], SEG_S), fc) for fc in BANDS} for i, s in rows}
        (d / "bands.json").write_text(json.dumps(res) + "\n")
        return {"segments": len(rows)}
    mode, pid, kind, j = uid.split("--")
    p = allp[pid]
    cands, sets = candidates(p, allp, c, with_traffic=(mode == "blind"))
    clocks = CLOCKS if mode == "blind" else np.array([0.0])
    lo, hi = band_edges(p["band"])
    ref = np.median([v[str(p["band"])] for v in bands.values()])           # the fixed background band power
    idx = pl["selection"][pid]["cal" if kind == "cal" else "eval"]
    idx = idx[int(j):int(j) + 20] if kind == "cal" else [idx[int(j)]]
    if mode == "synthetic":
        clip = synthetic_clip(p, cands[0], c)
    else:
        clip = clip_audio(p)
    pc = band_power(clip[int((A0 - WIN_S / 2) * SR):int((A0 + WIN_S / 2) * SR)], p["band"])
    stats = []
    for i in idx:
        s = pl["segments"][i]
        bg = decode(DATA / s["path"], s["start"], SEG_S)
        bg *= np.sqrt(ref / max(bands[str(i)][str(p["band"])], 1e-30))
        if kind == "cal":
            stats.append(stats_for(bg, None, np.array([0.0]), cands, clocks, lo, hi, c, jobs)[:, 0, :])
        else:
            g = np.sqrt(10 ** (LEVELS / 10) * ref / pc)
            stats.append(stats_for(bg, clip, g, cands, clocks, lo, hi, c, jobs))
    np.savez(d / "stats.npz", stats=np.stack(stats), segments=np.array(idx), sets=np.array(sets),
             names=np.array([x["name"] for x in cands]), levels=LEVELS, methods=np.array(METHODS))
    return {"segments": len(idx), "candidates": len(cands), "set_A": sets.count("A"), "set_B": sets.count("B")}


def inputs(stage, pl, bands_run):
    allp = passes()
    paths = {AUDIT + "/passes.csv", AUDIT + "/sites.json", COHERENCE, "raw/aux/opensky/doc8643AircraftTypes.csv"}
    if stage == "prep":
        paths |= set(SPANS.values())
    else:
        paths |= set(SPANS.values()) | {str(next(pass_dir(p).glob("*.kml")).relative_to(DATA)) for p in allp.values()}
        paths |= {str((pass_dir(p) / "audio.wav").relative_to(DATA)) for p in allp.values()}
        paths |= {f"derived/traces/{p['day']}/livermore_margin12.npz" for p in allp.values()}
        if bands_run:
            paths.add(str(Path(bands_run).resolve().relative_to(DATA.resolve()) / "bands.json"))
    return sorted(paths)


def merge_prep(run, folders):
    bands = {}
    for d in folders.values():
        bands.update(json.loads((d / "bands.json").read_text()))
    (run / "bands.json").write_text(json.dumps(bands) + "\n")
    print(f"bands for {len(bands)} segments -> {run / 'bands.json'}")


def main():
    if sys.argv[1:2] == ["plan"]:
        plan(); return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    shards.add_args(ap)
    ap.add_argument("--stage", required=True, choices=["prep", "gates", "test"])
    ap.add_argument("--bands", type=Path, help="the merged prep run (its bands.json)")
    a = ap.parse_args()
    pl = json.loads(PLAN.read_text())
    if a.inputs:
        shards.print_inputs([], inputs(a.stage, pl, a.bands), [], ("terrarium",) if a.stage != "prep" else ())
        return
    bands = json.loads((a.bands / "bands.json").read_text()) if a.bands else None
    if a.stage != "prep" and bands is None:
        sys.exit("--bands PREP_RUN is required after prep")
    params = {"stage": a.stage, "plan_sha": __import__("hashlib").sha256(PLAN.read_bytes()).hexdigest(),
              "levels": LEVELS.tolist(), "clocks": [float(CLOCKS[0]), float(CLOCKS[-1]), 0.25], "blocks": BLOCKS}
    run = shards.open_run(a.run, f"coherent-duration-{a.stage}", {"script": "tools/experiments/2026-11-04/coherent_duration.py",
                          "params": params, "invocation": {"shard": "%d/%d" % a.shard, "resume": [str(r) for r in a.resume],
                                                           "merge": a.merge, "bands": str(a.bands)}})
    cached = Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack")) / "doc8643AircraftTypes.csv"
    if not cached.exists() and (DATA / "raw/aux/opensky/doc8643AircraftTypes.csv").exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes((DATA / "raw/aux/opensky/doc8643AircraftTypes.csv").read_bytes())
    units = shards.Units(run, units_for(a.stage, pl), params, a.shard, a.resume)
    if not a.merge:
        from dopplertrack.parallel import default_jobs
        jobs = default_jobs()
        for uid in units.todo():
            t0 = time.time()
            d = units.dir(uid); d.mkdir(parents=True, exist_ok=True)
            try:
                summary = run_unit(uid, pl, bands, d, jobs)
                units.finish(uid, {**summary, "seconds": round(time.time() - t0)})
                print(f"{uid}: {time.time() - t0:.0f} s", flush=True)
            except Exception as e:
                print(f"{uid}: failed: {e!r}", flush=True)
    try:
        folders = units.all()
    except SystemExit as e:
        if a.merge:
            raise
        print(f"this shard is done; not merging yet: {e}", flush=True)
        return
    if a.stage == "prep":
        merge_prep(run, folders)
    else:
        print(f"all {len(folders)} units finished; judge with coherent_duration_judge.py", flush=True)


if __name__ == "__main__":         # ordered_map's spawn workers re-import this file
    main()
