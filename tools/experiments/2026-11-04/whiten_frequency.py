"""The across-frequency background as a whitening option (compute_spectrogram(whiten="frequency")), judged on the
benchmark runner against today's whitening. The criterion was fixed before running:
- Tier 2, saved-fit profile, the five seed cases: on every positive case (oyster-bay, eagle-cam-clip-18000s,
  oyster-bay-hp150-aac32k) the true pair's rank is no worse and its margin no smaller than today's. The moved-box
  negatives are reported.
- Tier 1, the development spans: the detector's matched counted windows at min_score 0 are no fewer, and the
  background spans' false alarms per countable hour, at each arm's own threshold (the lowest score among its
  matched detections), are no more. Fewer would be the gain.
One retune at most (bg_hz), counted.

Each case's and span's spectrogram is rebuilt with whiten="frequency" from the audio its recipe names, with the
recipe's defaults otherwise, into $DOPPLERTRACK_DATA/derived/whiten_frequency/<the same path>. The frequency arm
runs the runner with bench's path resolver pointed at those files; the time arm is today's files, same code.

Units (resumable and splittable; tools/experiments/2026-11-04/units.py): one per variant spectrogram (build), one
per (arm, Tier 2 case), one per (arm, Tier 1). A unit whose output exists is skipped. Workers: DOPPLERTRACK_JOBS.

usage: whiten_frequency.py RUN build [SPECTROGRAM ...]
       whiten_frequency.py RUN t2 time|frequency [CASE ...]
       whiten_frequency.py RUN t1 time|frequency
       whiten_frequency.py RUN merge"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import units as U                                                       # noqa: E402

from bench import cases as BC, runner as BR, tier1 as BT                # noqa: E402
from dopplertrack import audio                                           # noqa: E402

VARIANT_ROOT = "derived/whiten_frequency"
SEED = ["oyster-bay", "eagle-cam-clip-18000s", "oyster-bay-hp150-aac32k", "oyster-bay-moved-north150", "oyster-bay-moved-wsw150"]
POSITIVE = ["oyster-bay", "eagle-cam-clip-18000s", "oyster-bay-hp150-aac32k"]


def spectrogram_sources() -> dict[str, str]:
    """Every spectrogram path the seed cases and the development spans use -> the audio its recipe reads."""
    out = {}
    for cid in SEED:
        c = BC.latest_case(cid)
        d = next(x for x in c["derived"] if x["path"] == c["spectrogram"])
        out[c["spectrogram"]] = d["recipe"][0][2]
    for s in BT.load_tier1()["spans"]:
        if s["set"] != "development" or not s["spectrogram"].get("sha256"):
            continue
        p = s["spectrogram"]["path"]
        d = next((x for x in s.get("derived", []) if x["path"] == p), None)
        if d:
            out[p] = d["recipe"][0][2]
        elif p == "derived/swfl/rec.npz":                                 # the full stream, built before recipes existed
            out[p] = "{data}/raw/audio/youtube/swfl_2024-12-28.webm"
    return out


def variant(path: str) -> str:
    return f"{VARIANT_ROOT}/{path.removeprefix('derived/')}"


def build(chosen):
    src = spectrogram_sources()
    for path in U.select(list(src), chosen):
        out = BC.resolve(variant(path))
        if out.exists():
            print("have", out); continue
        out.parent.mkdir(parents=True, exist_ok=True)
        x, sr = audio.load_audio(src[path].replace("{data}", str(BC.data_root())))
        sp = audio.compute_spectrogram(x, sr, whiten="frequency")
        sp.save(out)                                                     # atomic
        print("built", out, sp.S.shape, flush=True)


def point_at_variants():
    real = BC.resolve
    paths = set(spectrogram_sources())

    def resolve(path):
        return real(variant(path)) if path in paths else real(path)
    for m in (BC, BR, BT):
        m.resolve = resolve


def t2(run, arm, chosen):
    if arm == "frequency":
        point_at_variants()
    root = run / f"{arm}-t2"; root.mkdir(parents=True, exist_ok=True)
    code, execute = BR._executor(None, "saved-fit", print)
    info = root / "run.json"
    if not info.exists():
        info.write_text(json.dumps(dict(arm=arm, profile="saved-fit", code=code), indent=1))
    for cid in U.select(SEED, chosen):
        if (root / cid / "entry.json").exists():
            print("have", cid); continue
        BR.run_one(cid, root, execute, code)                             # writes <case>/entry.json last, atomically


def t1(run, arm):
    if arm == "frequency":
        point_at_variants()
    root = run / f"{arm}-t1"
    if (root / "results.json").exists():
        print("have", root); return
    if root.exists() and any(root.iterdir()):                            # a stopped Tier 1 restarts into a fresh folder
        root.rename(root.with_name(root.name + "_stopped"))
    root.mkdir(parents=True)
    print(BT.run_tier1(("development",), run_dir=root, workers=U.jobs()))


def _t1_numbers(results: dict) -> dict:
    """Matched counted windows at min_score 0 over the labelled spans; the arm's threshold (the lowest score among
    its matched detections, i.e. the largest threshold keeping every match); background extras per countable hour
    at that threshold."""
    labelled = [s for s in results["spans"] if s.get("detection_curve") and s["detection_curve"][0].get("matched") is not None]
    scores = sorted({row["min_score"] for s in labelled for row in s["detection_curve"]})

    def matched_at(th):
        tot = 0
        for s in labelled:
            rows = [r for r in s["detection_curve"] if r["min_score"] <= th]
            tot += rows[-1]["matched"] if rows else s["detection_curve"][0]["matched"]
        return tot
    m0 = matched_at(0.0)
    threshold = max([th for th in scores if matched_at(th) == m0] or [0.0])
    bg = results["pooled"]["background"]["curve"]
    rows = [r for r in bg if r["min_score"] <= threshold]
    return dict(matched=m0, threshold=threshold, background_extra_per_hour=(rows[-1] if rows else bg[0])["extra_per_hour"])


def span_results(root: Path) -> dict | None:
    """Tier 1's comparison of the development spans alone (compare_span and pooled_curve, as run_tier1 does), from
    their blind records. Both arms are judged this way: the frequency arm's known-point step raised before its
    comparison ("detect found nothing inside the saved window"), so it has no results.json, and the spans are the
    whole of the Tier 1 criterion."""
    spans = [s for s in BT.load_tier1()["spans"] if s["set"] == "development" and s["spectrogram"].get("sha256")]
    if not all((root / "spans" / s["id"] / BT.SPAN_FILE).exists() for s in spans):
        return None
    entries = []
    for s in spans:
        labels = json.loads(BC.resolve(s["labels"]).read_text())
        ref = (lambda s=s, labels=labels: BT.reference_context(s, labels)) if s.get("reference_case") else None
        entries.append({**BT.compare_span(root / "spans" / s["id"], lambda labels=labels: labels, ref), "family": s["family"]})
    units = {e["span"]: e.pop("_pool") for e in entries if "_pool" in e}
    bg = [e["span"] for e in entries if e["family"] in BT.BACKGROUND_FAMILIES and e["span"] in units]
    return dict(spans=entries, pooled={"background": {"spans": bg, "curve": BT.pooled_curve([units[m] for m in bg])}})


def merge(run):
    out, lines = {}, []
    for arm in ("time", "frequency"):
        entries = {cid: json.loads((run / f"{arm}-t2" / cid / "entry.json").read_text())
                   for cid in SEED if (run / f"{arm}-t2" / cid / "entry.json").exists()}
        r1 = span_results(run / f"{arm}-t1")
        out[arm] = dict(t2={cid: {k: e.get(k) for k in ("true_pair_rank", "margin_pct", "top_error_m", "refined_error_m", "status")}
                            for cid, e in entries.items()},
                        t1=_t1_numbers(r1) if r1 else None)
    for cid in SEED:
        lines.append(f"{cid:28s} time {out['time']['t2'].get(cid)}  |  frequency {out['frequency']['t2'].get(cid)}")
    verdict = []
    for cid in POSITIVE:
        a, b = out["time"]["t2"].get(cid), out["frequency"]["t2"].get(cid)
        if not (a and b):
            verdict.append(f"{cid}: missing"); continue
        ra, rb = a["true_pair_rank"], b["true_pair_rank"]
        rank_ok = isinstance(rb, int) and (not isinstance(ra, int) or rb <= ra)
        margin_ok = (b["margin_pct"] if isinstance(b["margin_pct"], (int, float)) else -1e9) >= \
                    (a["margin_pct"] if isinstance(a["margin_pct"], (int, float)) else -1e9)
        verdict.append(f"{cid}: rank {'OK' if rank_ok else 'worse'}, margin {'OK' if margin_ok else 'smaller'}")
    t1a, t1b = out["time"]["t1"], out["frequency"]["t1"]
    if t1a and t1b:
        verdict.append(f"Tier 1 matched {t1a['matched']} -> {t1b['matched']}: {'OK' if t1b['matched'] >= t1a['matched'] else 'fewer'}")
        verdict.append(f"Tier 1 background extras per hour at each arm's threshold {t1a['background_extra_per_hour']:.2f} -> "
                       f"{t1b['background_extra_per_hour']:.2f}: {'OK' if t1b['background_extra_per_hour'] <= t1a['background_extra_per_hour'] else 'more'}")
    lines += ["== criterion"] + verdict
    txt = "\n".join(lines); print(txt)
    U.write(run / "summary.json", dict(arms=out, verdict=verdict))
    (run / "summary.txt").write_text(txt + "\n")


if __name__ == "__main__":
    run, step, rest = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    if step == "build":
        build(rest)
    elif step == "t2":
        t2(run, rest[0], rest[1:])
    elif step == "t1":
        t1(run, rest[0])
    elif step == "merge":
        merge(run)
    else:
        sys.exit(__doc__)
