"""Create a new run folder under $DOPPLERTRACK_DATA/runs, print its path, and record where it came from.

The folder is runs/<yyyy-mm-dd>-<topic>, or <...>-2, -3, ... if that name is taken. mkdir is atomic, so
two sessions starting the same topic at once still get different folders. run.json in it records the
time, the repo's commit and whether its working tree had uncommitted changes; add the command and
parameters to it, and keep the outputs next to it.

usage: RUN=$(uv run python tools/data/new_run.py <topic>)"""
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", sys.argv[1]):
    sys.exit(__doc__ + "\n\ntopic: lowercase letters, digits and hyphens")
now = datetime.datetime.now().astimezone()
base = ROOT / "runs" / f"{now:%Y-%m-%d}-{sys.argv[1]}"
base.parent.mkdir(parents=True, exist_ok=True)
for n in range(1, 1000):
    run = base if n == 1 else base.with_name(f"{base.name}-{n}")
    try:
        run.mkdir()
        break
    except FileExistsError:
        continue
else:
    sys.exit(f"no free run folder for {base}")
info = {"topic": sys.argv[1], "created": now.isoformat(timespec="seconds"), "cwd": os.getcwd(),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain"))}
(run / "run.json").write_text(json.dumps(info, indent=1) + "\n")
print(run)
