"""Copies SRC's files into DST, keeping any file DST already has (so a box's own run.json survives); `cp -n` exits 1
on macOS when it skips a file, which stops a `set -e` script.

usage: copy_new.py SRC DST [NAME ...]          (only those top-level names when given)"""
import shutil
import sys
from pathlib import Path


def copy_new(src: Path, dst: Path, names: list[str]) -> int:
    n = 0
    for s in sorted(src.rglob("*")):
        rel = s.relative_to(src)
        if not s.is_file() or (names and rel.parts[0] not in names):
            continue
        d = dst / rel
        if not d.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3 or not Path(sys.argv[1]).is_dir():
        sys.exit(__doc__)
    print(copy_new(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]), "files copied", file=sys.stderr)
