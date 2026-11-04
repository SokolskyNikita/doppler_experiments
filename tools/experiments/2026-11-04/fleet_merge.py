"""Collects SDE-C's fleet jobs (fleet_launch.sh) into one new run folder and runs every merge step, then writes the
two settings side by side.

The pulled job folders ($DOPPLERTRACK_DATA/runs/<job>/, from `runs pull`) are copied in without replacing a file
already there, so units that two jobs both finished come from the first; their own run.json and logs stay in their
folders. Then: whiten_frequency's merge (summary.txt), hmm_livermore's merge under each whitening at the pair its
box picked (hmm/<whiten>_tc.._tb../hmm_summary.txt), and side_by_side.txt.

usage: fleet_merge.py JOB ...          (prints the new run folder)"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import units as U                                                       # noqa: E402
from livermore_audit import DATA                                         # noqa: E402

KEEP = ("time-t2", "frequency-t2", "time-t1", "frequency-t1", "hmm", "hmm_knobs", "dev_references.json")


def collect(out: Path, jobs: list[str]) -> None:
    for job in jobs:
        src = DATA / "runs" / job
        if not src.is_dir():
            sys.exit(f"{src} missing: runs pull {job} first")
        for name in KEEP:
            s = src / name
            if s.is_dir():
                shutil.copytree(s, out / name, dirs_exist_ok=True, copy_function=_copy_new)
            elif s.is_file():
                _copy_new(s, out / name)


def _copy_new(s, d):
    d = Path(d)
    if not d.exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    return d


def py(*args) -> str:
    r = subprocess.run(["uv", "run", "--frozen", "python", *map(str, args)], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr, file=sys.stderr)
        sys.exit(f"failed: {args}")
    return r.stdout


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(subprocess.run(["uv", "run", "--frozen", "python", "tools/data/new_run.py", "sde-c-fleet-merge"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip())
    info = json.loads((out / "run.json").read_text())
    info.update(command=" ".join(sys.argv), sources=sys.argv[1:])
    (out / "run.json").write_text(json.dumps(info, indent=1))
    collect(out, sys.argv[1:])
    lines = []
    if any((out / f"{a}-t{t}").exists() for a in ("time", "frequency") for t in (1, 2)):
        lines += ["#### whitening across frequency (task 1)", py(HERE / "whiten_frequency.py", out, "merge")]
    for w in ("time", "frequency"):
        chosen = out / "hmm_knobs" / w / "chosen.json"
        if not chosen.exists():
            lines.append(f"#### tracker, {w} whitening: no chosen.json"); continue
        c = json.loads(chosen.read_text())
        tc, tb = c["chosen"]
        lines.append(f"#### tracker, {w} whitening: theta_cont {tc:g}, theta_birth {tb:g} (pairs {c['pairs']})")
        lines.append(py(HERE / "hmm_livermore.py", out, "merge", w, tc, tb))
    txt = "\n".join(lines)
    (out / "side_by_side.txt").write_text(txt + "\n")
    U.write(out / "merged_from.json", dict(jobs=sys.argv[1:]))
    print(txt)
    print(out)
