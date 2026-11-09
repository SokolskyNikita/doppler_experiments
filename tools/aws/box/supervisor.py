"""Runs one job on its box, then powers the box off (its launch template makes that a termination).

The user data starts this with the bucket and the job id; everything else is in
s3://<bucket>/jobs/<job>/spec.json, which `runs launch` wrote. In order:
1. the code: a git bundle of the engineer's HEAD, their uncommitted diff and untracked files, so
   `git rev-parse HEAD` and `git status` on the box say what they said on the Mac; then `uv sync --frozen`;
2. the inputs (paths under the data root) and caches (kinds under the cache root), from s3 with s5cmd,
   with every cache delta earlier jobs sent back;
3. a run folder, runs/<job>/, whose run.json is new_run.py's plus the box: instance type, AZ, spot or
   on-demand;
4. the command, under bash in the checkout, with $RUN, $DOPPLERTRACK_DATA and $DOPPLERTRACK_CACHE set,
   output to $RUN/command.log. Every 5 s the instance metadata is checked for a spot interruption notice;
   the run folders are uploaded every few minutes while it runs;
5. when it ends, is interrupted or times out: every run folder the job made, a tarball of the cache
   entries it added (s3 cache-deltas/<job>.tar), and jobs/<job>/status.json.

Standard library only: the box has Ubuntu's python3 plus the s5cmd, uv and ffmpeg binaries."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

SCRATCH = Path("/scratch")
# the Mac's interpreter: uv's own CPython build, not Ubuntu's python3, so a box and the Mac run the same Python
PYTHON_ENV = {"UV_PYTHON": "3.12.15", "UV_PYTHON_PREFERENCE": "only-managed"}
IMDS = "http://169.254.169.254/latest"
NOTICE_POLL_S = 5
HEARTBEAT_S = 60
TERM_GRACE_S = 20
# joblib's per-function code file and the per-entry lock files belong to each box, not to the cache's contents
CACHE_SKIP = ("func_code.py",)
CACHE_SKIP_DIRS = ("locks",)


class Metadata:
    """IMDSv2, with the session token renewed before it expires."""

    def __init__(self, base: str = IMDS):
        self.base, self.token, self.expires = base, "", 0.0

    def _token(self) -> str:
        if time.time() > self.expires:
            req = urllib.request.Request(f"{self.base}/api/token", method="PUT",
                                         headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"})
            with urllib.request.urlopen(req, timeout=5) as r:
                self.token = r.read().decode()
            self.expires = time.time() + 21000
        return self.token

    def get(self, path: str) -> str | None:
        """The value at meta-data/<path>, or None where there is none (404)."""
        req = urllib.request.Request(f"{self.base}/meta-data/{path}",
                                     headers={"X-aws-ec2-metadata-token": self._token()})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise


def host_info(md: Metadata) -> dict:
    """Where the job ran, for run.json."""
    lifecycle = md.get("instance-life-cycle")
    return {"provider": "aws", "instance_id": md.get("instance-id"), "instance_type": md.get("instance-type"),
            "availability_zone": md.get("placement/availability-zone"), "region": md.get("placement/region"),
            "market": "spot" if lifecycle == "spot" else "on-demand", "ami": md.get("ami-id"),
            "cpus": os.cpu_count()}


def interruption(md: Metadata) -> dict | None:
    """The spot interruption notice, if EC2 has sent one (meta-data/spot/instance-action exists from then on)."""
    try:
        body = md.get("spot/instance-action")
    except (OSError, urllib.error.URLError):
        return None
    return json.loads(body) if body else None


def s5(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["s5cmd", "--log", "error", *args], check=check, text=True,
                          capture_output=capture)


def s3_exists(url: str) -> bool:
    return s5("ls", url, check=False, capture=True).returncode == 0


def put_json(url: str, obj: dict) -> None:
    subprocess.run(["s5cmd", "--log", "error", "pipe", url], input=json.dumps(obj, indent=1) + "\n",
                   text=True, check=True)


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def prepare_code(prefix: str, spec: dict, repo: Path, work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    s5("cp", f"{prefix}/code/*", f"{work}/")
    rebuild_tree(work, spec, repo)


def rebuild_tree(work: Path, spec: dict, repo: Path) -> None:
    """The engineer's tree at repo: the bundle's commit, with their diff and untracked files on top."""
    subprocess.run(["git", "clone", "-q", "--no-checkout", str(work / "code.bundle"), str(repo)], check=True)
    git(repo, "checkout", "-q", "--detach", spec["git_commit"])
    patch = work / "dirty.patch"
    if patch.exists() and patch.stat().st_size:
        subprocess.run(["git", "-C", str(repo), "apply", "--binary", str(patch)], check=True)
    untracked = work / "untracked.tar"
    if untracked.exists() and untracked.stat().st_size:
        with tarfile.open(untracked) as t:
            t.extractall(repo, filter="data")
    commit, dirty = git(repo, "rev-parse", "HEAD"), bool(git(repo, "status", "--porcelain"))
    if commit != spec["git_commit"] or dirty != spec["git_dirty"]:
        raise RuntimeError(f"rebuilt tree is {commit} dirty={dirty}, the Mac had {spec['git_commit']} "
                           f"dirty={spec['git_dirty']}")


def uv_sync(repo: Path) -> None:
    subprocess.run(["uv", "sync", "--frozen", "-q"], cwd=repo, check=True,
                   env={**os.environ, **PYTHON_ENV, "UV_CACHE_DIR": str(SCRATCH / "uv-cache")})


def input_kind(rel: str, listing: str) -> str:
    """"file" or "folder" for data-root path rel, from `s5cmd ls s3://<bucket>/data/<rel>`'s output (an object as
    "<date> <time> <size> <its full key>", a common prefix as "DIR <last part>/"; checked against s5cmd 2.3.0). A
    path that is both an object and a folder is read as the file. Raises FileNotFoundError when it is neither."""
    rel = rel.strip("/")
    name = rel.rsplit("/", 1)[-1]
    lines = [line.split() for line in listing.splitlines() if line.strip()]
    if any(len(f) >= 4 and f[0] != "DIR" and f[-1] in (f"data/{rel}", rel, name) for f in lines):
        return "file"
    if any(f[:1] == ["DIR"] and f[-1] == f"{name}/" for f in lines):
        return "folder"
    raise FileNotFoundError(f"input {rel} is neither a file nor a folder in the bucket's data/: seed it from the Mac "
                            "(runs seed, or --input-run for a run folder) and relaunch")


def pull_inputs(bucket: str, inputs: list[str], data: Path) -> None:
    """Each input is a file or a folder under the data root; folders come over whole."""
    for rel in inputs:
        rel = rel.strip("/")
        dest = data / rel
        # without --log error: s5cmd prints a listing at its info level, so s5() would get nothing back
        listing = subprocess.run(["s5cmd", "ls", f"s3://{bucket}/data/{rel}"], capture_output=True, text=True).stdout
        if input_kind(rel, listing) == "file":
            dest.parent.mkdir(parents=True, exist_ok=True)
            s5("cp", f"s3://{bucket}/data/{rel}", str(dest))
        else:
            dest.mkdir(parents=True, exist_ok=True)
            s5("cp", f"s3://{bucket}/data/{rel}/*", f"{dest}/")


def pull_caches(bucket: str, kinds: list[str], cache: Path, work: Path) -> int:
    """The seeded cache kinds, then every delta earlier jobs sent back (entries already present are kept).
    Returns the number of deltas applied."""
    for kind in kinds:
        (cache / kind).mkdir(parents=True, exist_ok=True)
        if s3_exists(f"s3://{bucket}/cache/{kind}/*"):
            s5("cp", f"s3://{bucket}/cache/{kind}/*", f"{cache / kind}/")
    deltas = work / "deltas"
    deltas.mkdir(parents=True, exist_ok=True)
    if not s3_exists(f"s3://{bucket}/cache-deltas/*"):
        return 0
    s5("cp", f"s3://{bucket}/cache-deltas/*", f"{deltas}/")
    applied = 0
    for tar in sorted(deltas.glob("*.tar")):
        with tarfile.open(tar) as t:
            members = [m for m in t.getmembers()
                       if m.name.split("/", 1)[0] in kinds and not (cache / m.name).exists()]
            t.extractall(cache, members=members, filter="data")
        applied += 1
    return applied


# public files a tool fetches into the cache root on first use from a host the boxes can't reach: each comes from
# the bucket's copy instead (dopplertrack.data.aircraft_types.AircraftTypes reads opensky-network.org's Doc 8643 table)
CACHE_ROOT_FILES = {"doc8643AircraftTypes.csv": "data/raw/aux/opensky/doc8643AircraftTypes.csv"}


def seed_cache_root(bucket: str, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name, key in CACHE_ROOT_FILES.items():
        if not (cache / name).exists():
            s5("cp", f"s3://{bucket}/{key}", str(cache / name), check=False)


def cache_files(cache: Path) -> set[str]:
    """Every cache file that belongs to an entry, relative to the cache root."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(cache):
        dirnames[:] = [d for d in dirnames if d not in CACHE_SKIP_DIRS]
        for f in filenames:
            if f not in CACHE_SKIP and not f.endswith(".tmp"):
                out.add(os.path.relpath(os.path.join(dirpath, f), cache))
    return out


def new_cache_entries(before: set[str], after: set[str], kinds: list[str]) -> list[str]:
    """Files added under the job's cache kinds. The CPA tables (cpa/) rebuild in under a minute on a
    box, so only the kinds the job named come back."""
    return sorted(p for p in after - before if p.split(os.sep, 1)[0] in kinds)


def write_delta(cache: Path, files: list[str], out: Path) -> None:
    with tarfile.open(out, "w") as t:
        for rel in files:
            t.add(cache / rel, arcname=rel)


def run_folders(runs: Path) -> set[str]:
    return {p.name for p in runs.iterdir() if p.is_dir()} if runs.exists() else set()


def upload_runs(bucket: str, runs: Path, names: list[str]) -> None:
    for name in names:
        s5("cp", f"{runs / name}/*", f"s3://{bucket}/runs/{name}/")


class Job:
    def __init__(self, bucket: str, job: str, md: Metadata):
        self.bucket, self.job, self.md = bucket, job, md
        self.prefix = f"s3://{bucket}/jobs/{job}"
        self.status: dict = {"job": job, "state": "starting", "started": now()}
        self.timings: dict = {}

    def report(self, **fields) -> None:
        self.status.update(fields, updated=now())
        put_json(f"{self.prefix}/status.json", self.status)

    def stage(self, name: str, fn, *args):
        self.report(state="preparing", stage=name)
        t0 = time.time()
        out = fn(*args)
        self.timings[name] = round(time.time() - t0, 1)
        return out


def memory_gb() -> tuple[float, float]:
    """(total, in use) in GB, from /proc/meminfo: MemTotal less MemAvailable."""
    kb = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            kb[k] = int(v.split()[0])
    return kb["MemTotal"] / 1e6, (kb["MemTotal"] - kb["MemAvailable"]) / 1e6


def rehearsal_verdict(state: str) -> str:
    """A rehearsal is ok if the command ran to its cut-off without failing, or finished; failed otherwise."""
    return "rehearsal-ok" if state in ("done", "timeout") else "rehearsal-failed"


def kill_group(proc: subprocess.Popen) -> None:
    """SIGTERM to the command's process group, SIGKILL after TERM_GRACE_S."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(TERM_GRACE_S)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--job", required=True)
    args = ap.parse_args(argv)
    md = Metadata()
    job = Job(args.bucket, args.job, md)
    spec = json.loads(s5("cat", f"{job.prefix}/spec.json", capture=True).stdout)
    data, cache, work = SCRATCH / "data", SCRATCH / "cache", SCRATCH / "work"
    if spec.get("private"):      # a case the owner cleared: its cache stays apart and none of it comes back
        cache = SCRATCH / "data" / "private" / "cache"
    repo = SCRATCH / "dopplertrack"
    # a private job's run folder sits under private/runs/, where a private case's records must be written; it
    # comes back under the same path on the Mac (`runs pull`)
    runs_dir = data / "private" / "runs" if spec.get("private") else data / "runs"
    run = runs_dir / spec["run"]
    host = host_info(md)
    job.report(host=host)
    try:
        job.stage("code", prepare_code, job.prefix, spec, repo, work)
        job.stage("uv_sync", uv_sync, repo)
        job.stage("inputs", pull_inputs, args.bucket, spec.get("inputs", []), data)
        deltas = job.stage("caches", pull_caches, args.bucket, spec.get("caches", []), cache, work)
        seed_cache_root(args.bucket, cache)
    except Exception:
        job.report(state="rehearsal-failed" if spec.get("rehearsal_minutes") else "failed",
                   stage_failed=job.status.get("stage"), error=traceback.format_exc(limit=5))
        s5("cp", "/var/log/dopplertrack-boot.log", f"{job.prefix}/boot.log", check=False)
        return 1

    resumed = None
    if spec.get("resume_of"):    # the run so far: its finished units are skipped by the command, not by us
        run.mkdir(parents=True, exist_ok=True)
        if s3_exists(f"s3://{args.bucket}/runs/{spec['run']}/*"):
            s5("cp", f"s3://{args.bucket}/runs/{spec['run']}/*", f"{run}/")
        try:
            resumed = json.loads((run / "run.json").read_text())
        except (OSError, ValueError):
            resumed = None
    else:
        run.mkdir(parents=True)
    info = {"topic": spec["topic"], "created": now(), "cwd": str(repo), "git_commit": spec["git_commit"],
            "git_dirty": spec["git_dirty"], "job": args.job, "command": spec["command"],
            "jobs": spec.get("jobs"), "inputs": spec.get("inputs", []), "caches": spec.get("caches", []),
            "cache_deltas_applied": deltas, "host": host, "submitted": spec.get("submitted"),
            "submitted_from": spec.get("submitted_from"), "box_prepare_s": job.timings,
            "shard": spec.get("shard"), "code_source": spec.get("code_source")}
    if resumed:      # keep the run's own record and add this box to it
        stint = {k: info[k] for k in ("job", "host", "git_commit", "git_dirty", "code_source", "created", "box_prepare_s")}
        info = {**resumed, "resumed": resumed.get("resumed", []) + [stint]}
        info.pop("finished", None)
    (run / "run.json").write_text(json.dumps(info, indent=1) + "\n")
    runs_before, cache_before = run_folders(runs_dir) - {spec["run"]}, cache_files(cache)

    env = {**os.environ, "DOPPLERTRACK_DATA": str(data), "DOPPLERTRACK_CACHE": str(cache), "RUN": str(run),
           "DOPPLERTRACK_JOB": args.job,
           **({"DOPPLERTRACK_SHARD": str(spec["shard"][0]), "DOPPLERTRACK_SHARDS": str(spec["shard"][1]),
               "DOPPLERTRACK_SHARD_SPEC": f"{spec['shard'][0]}/{spec['shard'][1]}"}
              if spec.get("shard") else {}),
           "UV_CACHE_DIR": str(SCRATCH / "uv-cache"), "PYTHONUNBUFFERED": "1", **PYTHON_ENV}
    env.pop("DOPPLERTRACK_JOBS", None)
    if spec.get("jobs"):
        env["DOPPLERTRACK_JOBS"] = str(spec["jobs"])
    rehearsal = spec.get("rehearsal_minutes")      # `runs launch --rehearse`: the dev box, cut off after this long
    deadline = time.time() + (60 * float(rehearsal) if rehearsal else 3600 * float(spec.get("max_hours", 12)))
    checkpoint_s = float("inf") if rehearsal else 60 * float(spec.get("checkpoint_minutes", 10))
    t_start = time.time()
    with open(run / "command.log", "ab") as log:
        proc = subprocess.Popen(["bash", "-c", spec["command"]], cwd=repo, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        job.report(state="running", stage="command", pid=proc.pid)
        state, notice, last_beat, last_ckpt = "done", None, time.time(), time.time()
        mem_total, mem_peak = memory_gb()
        while proc.poll() is None:
            time.sleep(NOTICE_POLL_S)
            mem_peak = max(mem_peak, memory_gb()[1])
            notice = interruption(md)
            if notice:
                state = "interrupted"
                break
            if time.time() > deadline:
                state = "timeout"
                break
            if time.time() - last_beat > HEARTBEAT_S:
                job.report(state="running", elapsed_s=round(time.time() - t_start), mem_total_gb=round(mem_total, 1),
                           mem_peak_gb=round(mem_peak, 1))
                last_beat = time.time()
            if time.time() - last_ckpt > checkpoint_s:
                upload_runs(args.bucket, runs_dir, sorted(run_folders(runs_dir) - runs_before))
                last_ckpt = time.time()
        if proc.poll() is None:
            job.report(state=state, notice=notice)
            kill_group(proc)
    wall = round(time.time() - t_start, 1)
    code = proc.returncode
    if state == "done" and code != 0:
        state = "failed"
    if rehearsal:
        state = rehearsal_verdict(state)
    try:    # the command may have added to run.json (bench run --run-dir does), so merge into what is there
        info = {**info, **json.loads((run / "run.json").read_text())}
    except (OSError, ValueError):
        pass
    info.update(finished=now(), wall_s=wall, exit_code=code, state=state, notice=notice,
                mem_total_gb=round(mem_total, 1), mem_peak_gb=round(mem_peak, 1))
    (run / "run.json").write_text(json.dumps(info, indent=1) + "\n")

    made = sorted(run_folders(runs_dir) - runs_before)
    if rehearsal:       # nothing comes back from a rehearsal but its verdict and the log's tail
        tail = (run / "command.log").read_bytes()[-20000:].decode(errors="replace")
        job.report(state=state, exit_code=code, wall_s=wall, log_tail=tail, finished=now(),
                   mem_total_gb=round(mem_total, 1), mem_peak_gb=round(mem_peak, 1))
        return 0
    upload_runs(args.bucket, runs_dir, made)
    added = [] if spec.get("private") else new_cache_entries(cache_before, cache_files(cache), spec.get("caches", []))
    delta = None
    if added:
        write_delta(cache, added, work / "delta.tar")
        delta = f"cache-deltas/{args.job}.tar"
        s5("cp", str(work / "delta.tar"), f"s3://{args.bucket}/{delta}")
    job.report(state=state, exit_code=code, wall_s=wall, run_folders=made, cache_delta=delta,
               mem_total_gb=round(mem_total, 1), mem_peak_gb=round(mem_peak, 1),
               cache_files_added=len(added), notice=notice, finished=now())
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        a = sys.argv
        if "--bucket" in a and "--job" in a:
            prefix = f"s3://{a[a.index('--bucket') + 1]}/jobs/{a[a.index('--job') + 1]}"
            try:
                put_json(f"{prefix}/status.json", {"state": "failed", "error": traceback.format_exc(limit=5),
                                                   "updated": now()})
            except Exception:
                pass
    finally:
        if not os.environ.get("DOPPLERTRACK_KEEP_BOX"):
            shutil.which("shutdown") and subprocess.run(["shutdown", "-h", "now"])
    sys.exit(code)
