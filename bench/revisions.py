"""Another code revision, exported and installed on its own, for baselines such as upstream a16b700.

`ensure_revision` exports the commit's tree with `git archive` into $DOPPLERTRACK_CACHE/revisions/<short>/src
and installs it with `uv sync --frozen` against that revision's own uv.lock, into a venv beside the source.
`export.json` is written last, so a folder without it is an unfinished export. Before every use the tree
on disk is hashed the way git hashes a tree and compared with the commit's, so an edited or stale export
can't run under the commit's name. The revision's code runs only through its own CLI, in a subprocess."""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .cases import REPO, cache_root


class RevisionError(RuntimeError):
    pass


@dataclass
class Revision:
    commit: str
    tree: str
    root: Path

    @property
    def short(self) -> str:
        return self.commit[:7]

    @property
    def src(self) -> Path:
        return self.root / "src"

    @property
    def python(self) -> Path:
        return self.root / "venv" / "bin" / "python"

    def cli(self, *args) -> list[str]:
        # -I keeps the user's site and the working directory off sys.path. -B writes no bytecode, so running
        # the revision never changes the tree that is verified; unlike -X pycache_prefix, multiprocessing
        # passes -B on to the worker processes detect starts
        return [str(self.python), "-I", "-B", "-m", "dopplertrack.cli", *args]

    def provenance(self) -> dict:
        info = json.loads((self.root / "export.json").read_text())
        return {"package_version": info["package_version"], "git_commit": self.commit, "git_dirty": False,
                "git_tree": self.tree, "uv_lock_sha256": info["uv_lock_sha256"], "python": info["python"],
                "executed": "the revision's own CLI, in its own uv environment, as subprocesses"}


def _git(*args, env=None) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def tree_on_disk(src: Path, against: str | None = None) -> str | tuple[str, list[str]]:
    """The git tree hash of every file under src, ignored or not, computed in a throwaway index. With
    `against` (a tree), also the files that differ from it: added (A), modified (M) or deleted (D)."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        work = ["--work-tree", str(src)]
        _git(*work, "add", "--all", "--force", ".", env=env)
        tree = _git(*work, "write-tree", env=env)
        if against is None:
            return tree
        changed = _git(*work, "diff", "--cached", "--name-status", "--no-renames", against, env=env)
        return tree, [ln.replace("\t", " ") for ln in changed.splitlines()]


@contextlib.contextmanager
def file_lock(path: Path):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def verify(rev: Revision) -> None:
    """Refuse an export whose files are not exactly the commit's tree."""
    if not (rev.root / "export.json").exists():
        raise RevisionError(f"{rev.root} has no export.json: an unfinished export; move it aside and rebuild")
    info = json.loads((rev.root / "export.json").read_text())
    if info.get("commit") != rev.commit:
        raise RevisionError(f"{rev.root} was exported from {info.get('commit')}, not {rev.commit}")
    on_disk, changed = tree_on_disk(rev.src, against=rev.tree)
    if on_disk != rev.tree:
        shown = "; ".join(changed[:10]) + (f"; and {len(changed) - 10} more" if len(changed) > 10 else "")
        raise RevisionError(f"{rev.src} hashes to tree {on_disk}, not {rev.commit}'s tree {rev.tree}: "
                            f"the export was changed after it was made ({shown})")


def ensure_revision(name: str, log=print) -> Revision:
    """Export and install `name` (any commit-ish) once, then verify it on every call."""
    commit = _git("rev-parse", "--verify", f"{name}^{{commit}}")
    rev = Revision(commit, _git("rev-parse", f"{commit}^{{tree}}"), cache_root() / "revisions" / commit[:7])
    with file_lock(rev.root.with_name(f"{rev.short}.lock")):
        if not rev.root.exists():
            log(f"exporting {commit} into {rev.root}")
            tmp = rev.root.with_name(f".{rev.short}.{os.getpid()}.tmp")
            (tmp / "src").mkdir(parents=True)
            archive = subprocess.run(["git", "-C", str(REPO), "archive", commit], capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", str(tmp / "src")], input=archive, check=True)
            if tree_on_disk(tmp / "src") != rev.tree:
                raise RevisionError(f"git archive of {commit} does not reproduce its tree (export attributes?)")
            os.replace(tmp, rev.root)
        if not (rev.root / "export.json").exists():
            # the venv's paths are absolute, so it is built in place; export.json marks it complete
            env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(rev.root / "venv")}
            log(f"installing {rev.short} with uv sync --frozen")
            subprocess.run(["uv", "sync", "--frozen", "--no-dev", "--project", str(rev.src)], env=env, check=True)
            py = subprocess.run([str(rev.python), "-I", "-c", "import sys, importlib.metadata as m; "
                                 "print(sys.version.split()[0], m.version('dopplertrack'))"],
                                capture_output=True, text=True, check=True).stdout.split()
            info = {"commit": commit, "tree": rev.tree, "python": py[0], "package_version": py[1],
                    "uv_lock_sha256": hashlib.sha256((rev.src / "uv.lock").read_bytes()).hexdigest(),
                    "uv": subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip(),
                    "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            tmp = rev.root / ".export.json.tmp"
            tmp.write_text(json.dumps(info, indent=1) + "\n")
            os.replace(tmp, rev.root / "export.json")
    verify(rev)
    return rev
