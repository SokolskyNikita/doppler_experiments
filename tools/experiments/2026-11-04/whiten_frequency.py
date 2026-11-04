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

usage: whiten_frequency.py RUN build|time|frequency"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from bench import cases as BC, runner as BR, tier1 as BT                # noqa: E402
from dopplertrack import audio                                           # noqa: E402

VARIANT_ROOT = "derived/whiten_frequency"
SEED = ["oyster-bay", "eagle-cam-clip-18000s", "oyster-bay-hp150-aac32k", "oyster-bay-moved-north150", "oyster-bay-moved-wsw150"]


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


def build():
    for path, src in spectrogram_sources().items():
        out = BC.resolve(variant(path))
        if out.exists():
            print("have", out); continue
        out.parent.mkdir(parents=True, exist_ok=True)
        x, sr = audio.load_audio(src.replace("{data}", str(BC.data_root())))
        sp = audio.compute_spectrogram(x, sr, whiten="frequency")
        sp.save(out)
        print("built", out, sp.S.shape, flush=True)


def point_at_variants():
    real = BC.resolve
    paths = set(spectrogram_sources())

    def resolve(path):
        return real(variant(path)) if path in paths else real(path)
    for m in (BC, BR, BT):
        m.resolve = resolve


if __name__ == "__main__":
    run = Path(sys.argv[1]); arm = sys.argv[2]
    os.environ.setdefault("DOPPLERTRACK_JOBS", "2")
    if arm == "build":
        build(); sys.exit(0)
    if arm == "frequency":
        point_at_variants()
    t2 = run / f"{arm}-t2"; t2.mkdir(parents=True, exist_ok=True)
    BR.run_bench(SEED, tier="t2", run_dir=t2, profile="saved-fit", parallel=1)
    t1 = run / f"{arm}-t1"; t1.mkdir(parents=True, exist_ok=True)
    print(BT.run_tier1(("development",), run_dir=t1, workers=2))
