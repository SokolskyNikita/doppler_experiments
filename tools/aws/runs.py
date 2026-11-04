"""runs: long dopplertrack jobs on their own AWS box, and the dev box.

    tools/aws/runs launch <topic> [--case ID] [--input PATH] [--cache KIND] [--jobs N] [--size 16xlarge]
                          [--on-demand] [--max-hours H] [--wait] -- <command>
    tools/aws/runs status [JOB]      tools/aws/runs wait JOB      tools/aws/runs pull JOB
    tools/aws/runs log JOB           tools/aws/runs cancel JOB    tools/aws/runs interrupt JOB
    tools/aws/runs seed-tools        tools/aws/runs seed [--dry-run]
    tools/aws/runs fetch-sources [--dry-run]
    tools/aws/runs dev start|stop|status|shell|sync|run -- <command>

`launch` claims the job id <yyyy-mm-dd>-<topic>[-n] (free here and in the bucket), puts the branch (a git
bundle of HEAD, the uncommitted diff, the untracked files) and the job spec under jobs/<id>/ in the
bucket, and starts an instant EC2 Fleet: spot by default, price-capacity-optimized over c8g, c8gd, c7g and
c7a of the given size across the four AZs. The box's supervisor (box/supervisor.py) runs the command with
$RUN set to runs/<id>/ and puts the run folders, the cache entries the job added and jobs/<id>/status.json
back. `pull` copies the run folders into $DOPPLERTRACK_DATA/runs and the new cache entries into
$DOPPLERTRACK_CACHE. Nothing is pushed to GitHub.

Credentials come from the AWS profile in $AWS_PROFILE, else `dopplertrack`."""
from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
STACK = "DopplertrackFleet"
REGION = "us-west-2"
FAMILIES = {"arm64": ("c8g", "c8gd", "c7g"), "amd64": ("c7a",)}
TERMINAL = ("done", "failed", "interrupted", "timeout", "cancelled")
# the caches a job box can use; cpa/ rebuilds on the box in under a minute and revisions/ is per machine
CACHE_KINDS = ("detections", "window_fits", "terrarium")
DATA_ROOT = Path(os.environ.get("DOPPLERTRACK_DATA", Path.home() / "data" / "dopplertrack"))
CACHE_ROOT = Path(os.environ.get("DOPPLERTRACK_CACHE", Path.home() / ".cache" / "dopplertrack"))
# what `seed` uploads from this machine: the files with no public source a box could fetch them from (YouTube
# blocks cloud addresses, xeno-canto needs the API key), derived/ and the small aux/ and models/, plus the
# caches above; also A2O (its originals need a login) and the 1,203 small seismic windows. The rest of raw/
# comes from its sources (`runs fetch-sources`). Never reference/ (the papers)
# or runs/, which come back per job.
SEED_DATA = ("derived", "raw/audio/youtube", "raw/audio/xenocanto", "raw/aux", "raw/models", "raw/audio/a2o",
             "raw/seismic")
TOOLS = "tools.json"


def profile() -> str:
    return os.environ.get("AWS_PROFILE", "dopplertrack")


def session():
    import boto3
    return boto3.Session(profile_name=profile(), region_name=REGION)


def outputs() -> dict:
    cf = session().client("cloudformation")
    stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def aws_cli(*args: str) -> None:
    subprocess.run(["aws", "--profile", profile(), "--region", REGION, *args], check=True)


def git(*args: str, binary: bool = False, repo: Path = REPO):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout
    return out if binary else out.decode().strip()


# ---- job ids, specs and code ---------------------------------------------------------------------------

TOPIC = re.compile(r"[a-z0-9][a-z0-9-]*")


def candidate_ids(topic: str, day: datetime.date):
    """<date>-<topic>, then -2, -3, ...: new_run.py's names."""
    base = f"{day:%Y-%m-%d}-{topic}"
    yield base
    for n in range(2, 1000):
        yield f"{base}-{n}"


def code_bundle(dest: Path, repo: Path = REPO) -> dict:
    """The branch as the box rebuilds it: code.bundle (HEAD with its history), dirty.patch (the uncommitted
    diff against HEAD) and untracked.tar (files git doesn't track or ignore). Returns the commit and flag."""
    dest.mkdir(parents=True, exist_ok=True)
    commit = git("rev-parse", "HEAD", repo=repo)
    subprocess.run(["git", "-C", str(repo), "bundle", "create", "-q", str(dest / "code.bundle"), "HEAD"], check=True)
    (dest / "dirty.patch").write_bytes(git("diff", "HEAD", "--binary", binary=True, repo=repo))
    listing = git("ls-files", "--others", "--exclude-standard", "-z", binary=True, repo=repo).decode()
    untracked = [p for p in listing.split("\0") if p]
    with tarfile.open(dest / "untracked.tar", "w") as t:
        for rel in untracked:
            t.add(repo / rel, arcname=rel)
    return {"git_commit": commit, "git_dirty": bool(git("status", "--porcelain", repo=repo)),
            "untracked": len(untracked)}


def case_inputs(case_ids: list[str]) -> list[str]:
    """The data-root paths a benchmark case reads: its audio, spectrogram, traces and derived files."""
    cases = {c["id"]: c for c in json.loads((REPO / "bench" / "cases.json").read_text())["cases"]}
    out: list[str] = []
    for cid in case_ids:
        if cid not in cases:
            sys.exit(f"no case {cid!r} in bench/cases.json")
        c = cases[cid]
        paths = [c.get("audio", {}).get("path"), c.get("spectrogram"), c.get("flight_data", {}).get("traces")]
        paths += [d["path"] for d in c.get("derived", [])]
        for p in paths:
            if p and p not in out:
                out.append(p)
    return out


def fleet_request(out: dict, job: str, size: str, on_demand: bool, families=FAMILIES) -> dict:
    """The create_fleet arguments: one instance, any listed family of `size` in any of the subnets."""
    subnets = out["Subnets"].split(",")
    configs = []
    for arch, fams in families.items():
        overrides = [{"InstanceType": f"{fam}.{size}", "SubnetId": s} for fam in fams for s in subnets]
        if overrides:
            configs.append({"LaunchTemplateSpecification": {"LaunchTemplateId": out[f"Template{arch.capitalize()}"],
                                                            "Version": "$Latest"}, "Overrides": overrides})
    market = "on-demand" if on_demand else "spot"
    return {"Type": "instant", "LaunchTemplateConfigs": configs,
            "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": market},
            "SpotOptions": {"AllocationStrategy": "price-capacity-optimized"},
            "OnDemandOptions": {"AllocationStrategy": "lowest-price"},
            "TagSpecifications": [{"ResourceType": "instance", "Tags": [
                {"Key": "project", "Value": "dopplertrack"}, {"Key": "dopplertrack-job", "Value": job},
                {"Key": "Name", "Value": f"dopplertrack-job {job}"}]}]}


def launch(a) -> str:
    if not TOPIC.fullmatch(a.topic):
        sys.exit("topic: lowercase letters, digits and hyphens")
    command = " ".join(a.command).strip()
    if not command:
        sys.exit("give the command after --")
    for k in a.cache:
        if k not in CACHE_KINDS:
            sys.exit(f"--cache takes {', '.join(CACHE_KINDS)}")
    out = outputs()
    s3 = session().client("s3")
    bucket = out["Bucket"]
    inputs = case_inputs(a.case) + [p for p in a.input if p not in case_inputs(a.case)]
    caches = list(dict.fromkeys(a.cache or (["terrarium"] if a.case else [])))
    with tempfile.TemporaryDirectory() as tmp:
        code = code_bundle(Path(tmp) / "code", repo=Path(a.repo).resolve() if getattr(a, "repo", None) else REPO)
        for job in candidate_ids(a.topic, datetime.date.today()):
            if (DATA_ROOT / "runs" / job).exists():
                continue
            spec = {"job": job, "run": job, "topic": a.topic, "command": command, "inputs": inputs,
                    "caches": caches, "jobs": a.jobs, "max_hours": a.max_hours,
                    "checkpoint_minutes": a.checkpoint_minutes, "size": a.size,
                    "market": "on-demand" if a.on_demand else "spot", "submitted": now(),
                    "submitted_from": platform.node(), **code}
            try:     # the claim: a conditional put fails if another launch took this id first
                s3.put_object(Bucket=bucket, Key=f"jobs/{job}/spec.json", IfNoneMatch="*",
                              Body=json.dumps(spec, indent=1).encode())
                break
            except s3.exceptions.ClientError as e:
                if e.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
                    continue
                raise
        for f in sorted((Path(tmp) / "code").iterdir()):
            s3.upload_file(str(f), bucket, f"jobs/{job}/code/{f.name}")
    s3.upload_file(str(HERE / "box" / "supervisor.py"), bucket, f"jobs/{job}/supervisor.py")
    put_status(s3, bucket, job, {"job": job, "state": "submitted", "updated": now()})
    ec2 = session().client("ec2")
    resp = ec2.create_fleet(**fleet_request(out, job, a.size, a.on_demand))
    ids = [i for inst in resp.get("Instances", []) for i in inst.get("InstanceIds", [])]
    if not ids:
        errs = "; ".join(f"{e.get('ErrorCode')}: {e.get('ErrorMessage')}" for e in resp.get("Errors", []))
        put_status(s3, bucket, job, {"job": job, "state": "failed", "stage": "launch", "error": errs,
                                     "updated": now()})
        sys.exit(f"no capacity for {job}: {errs}")
    ec2.get_waiter("instance_exists").wait(InstanceIds=ids)     # describe lags create_fleet by a moment
    desc = ec2.describe_instances(InstanceIds=ids)["Reservations"][0]["Instances"][0]
    print(f"{job}: {ids[0]} {desc['InstanceType']} {desc['Placement']['AvailabilityZone']} "
          f"{desc.get('InstanceLifecycle', 'on-demand')}, commit {code['git_commit'][:7]}"
          f"{' (dirty)' if code['git_dirty'] else ''}")
    return job


# ---- following a job -----------------------------------------------------------------------------------

def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def put_status(s3, bucket: str, job: str, status: dict) -> None:
    s3.put_object(Bucket=bucket, Key=f"jobs/{job}/status.json", Body=json.dumps(status, indent=1).encode())


def get_status(s3, bucket: str, job: str) -> dict:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=f"jobs/{job}/status.json")["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"job": job, "state": "unknown"}


def job_instances(job: str, states=("pending", "running", "stopping", "shutting-down")) -> list[str]:
    ec2 = session().client("ec2")
    r = ec2.describe_instances(Filters=[{"Name": "tag:dopplertrack-job", "Values": [job]},
                                        {"Name": "instance-state-name", "Values": list(states)}])
    return [i["InstanceId"] for res in r["Reservations"] for i in res["Instances"]]


def status(a) -> None:
    bucket = outputs()["Bucket"]
    s3 = session().client("s3")
    if a.job:
        print(json.dumps(get_status(s3, bucket, a.job), indent=1))
        return
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="jobs/", Delimiter="/")
    for page in pages:
        for p in page.get("CommonPrefixes", []):
            job = p["Prefix"].split("/")[1]
            st = get_status(s3, bucket, job)
            print(f"{job:45s} {st.get('state', '?'):12s} {st.get('stage', '') or ''} {st.get('updated', '')}")


def wait(a) -> dict:
    bucket = outputs()["Bucket"]
    s3 = session().client("s3")
    last = None
    while True:
        st = get_status(s3, bucket, a.job)
        line = f"{st.get('state')} {st.get('stage', '')} {st.get('elapsed_s', '')}"
        if line != last:
            print(f"{time.strftime('%H:%M:%S')} {a.job}: {line}", flush=True)
            last = line
        if st.get("state") in TERMINAL:
            return st
        time.sleep(15)


def free_local(name: str) -> str:
    """name, or name-2, -3, ... if a run folder of that name already exists here (never write into one)."""
    if not (DATA_ROOT / "runs" / name).exists():
        return name
    m = re.fullmatch(r"(.*?)-(\d+)", name)
    base, n = (m.group(1), int(m.group(2)) + 1) if m else (name, 2)
    while (DATA_ROOT / "runs" / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"


def merge_cache_delta(tar_bytes: bytes, root: Path) -> int:
    """Adds the delta's entries to the local cache without touching any existing file. Each entry folder is
    unpacked beside its destination and renamed into place, so a reader never sees half an entry."""
    added = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as t:
        members = t.getmembers()
        entries = sorted({str(Path(m.name).parent) for m in members if m.isfile()})
        for entry in entries:
            dest = root / entry
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
                for m in members:
                    if m.isfile() and str(Path(m.name).parent) == entry:
                        t.extract(m, path=tmp, filter="data")
                staged = Path(tmp) / entry
                try:
                    os.rename(staged, dest)
                    added += 1
                except OSError:
                    pass
    return added


def pull(a) -> None:
    out = outputs()
    bucket = out["Bucket"]
    s3 = session().client("s3")
    st = get_status(s3, bucket, a.job)
    if st.get("state") not in TERMINAL:
        print(f"{a.job} is {st.get('state')}; pulling what has been uploaded so far")
    for name in st.get("run_folders") or [a.job]:
        local = free_local(name)
        if local != name:
            print(f"runs/{name} exists here; pulling into runs/{local}")
        aws_cli("s3", "sync", "--only-show-errors", f"s3://{bucket}/runs/{name}/", str(DATA_ROOT / "runs" / local))
        print(f"runs/{local}")
    if st.get("cache_delta"):
        body = s3.get_object(Bucket=bucket, Key=st["cache_delta"])["Body"].read()
        print(f"cache: {merge_cache_delta(body, CACHE_ROOT)} new entries")


def log(a) -> None:
    bucket = outputs()["Bucket"]
    s3 = session().client("s3")
    try:
        body = s3.get_object(Bucket=bucket, Key=f"runs/{a.job}/command.log")["Body"].read().decode(errors="replace")
        print(body[-20000:])
    except s3.exceptions.NoSuchKey:
        print("no command.log uploaded yet (the box uploads its run folder every few minutes)")
        print(json.dumps(get_status(s3, bucket, a.job), indent=1))


def cancel(a) -> None:
    ids = job_instances(a.job)
    if ids:
        session().client("ec2").terminate_instances(InstanceIds=ids)
    s3 = session().client("s3")
    bucket = outputs()["Bucket"]
    st = get_status(s3, bucket, a.job)
    if st.get("state") not in TERMINAL:
        put_status(s3, bucket, a.job, {**st, "state": "cancelled", "updated": now()})
    print(f"{a.job}: terminated {ids or 'nothing'}")


def interrupt(a) -> None:
    """Sends the job's spot box a real interruption through AWS Fault Injection Service (the supervisor's
    tested path): the 2-minute notice, then termination."""
    ids = job_instances(a.job, states=("running",))
    if not ids:
        sys.exit(f"no running box for {a.job}")
    sess = session()
    account = sess.client("sts").get_caller_identity()["Account"]
    role_arn = outputs()["FisRoleArn"]
    fis = sess.client("fis")
    tmpl = fis.create_experiment_template(
        description=f"dopplertrack: interrupt {a.job}", roleArn=role_arn,
        stopConditions=[{"source": "none"}], tags={"project": "dopplertrack"},
        targets={"box": {"resourceType": "aws:ec2:spot-instance", "selectionMode": "ALL",
                         "resourceArns": [f"arn:aws:ec2:{REGION}:{account}:instance/{i}" for i in ids]}},
        actions={"interrupt": {"actionId": "aws:ec2:send-spot-instance-interruptions", "targets": {"SpotInstances": "box"},
                               "parameters": {"durationBeforeInterruption": "PT2M"}}})["experimentTemplate"]
    exp = fis.start_experiment(experimentTemplateId=tmpl["id"], tags={"project": "dopplertrack"})["experiment"]
    print(f"{a.job}: interruption {exp['id']} sent to {ids} (template {tmpl['id']})")


# ---- the bucket's tools and data -----------------------------------------------------------------------

def seed_tools(a) -> None:
    """Downloads uv and a static ffmpeg for each architecture from the sources in tools.json, checks their
    SHA-256, and puts the binaries under tools/<arch>/ in the bucket, with tools.json beside them."""
    import hashlib
    import urllib.request
    spec = json.loads((HERE / TOOLS).read_text())
    bucket = outputs()["Bucket"]
    s3 = session().client("s3")
    with tempfile.TemporaryDirectory() as tmp:
        for arch, items in spec["arch"].items():
            for item in items:
                path = Path(tmp) / f"{arch}-{item['name']}"
                urllib.request.urlretrieve(item["url"], path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != item["sha256"]:
                    sys.exit(f"{item['url']}: sha256 {digest}, expected {item['sha256']}")
                with tarfile.open(path) as t:
                    for member in item["members"]:
                        m = next(x for x in t.getmembers() if x.name.endswith("/" + member) or x.name == member)
                        data = t.extractfile(m).read()
                        s3.put_object(Bucket=bucket, Key=f"tools/{arch}/{member}", Body=data)
                        print(f"tools/{arch}/{member} from {item['name']} ({len(data) / 1e6:.0f} MB)")
    s3.upload_file(str(HERE / TOOLS), bucket, f"tools/{TOOLS}")


def seed(a) -> None:
    """Uploads SEED_DATA and the caches a job can use. Only new or changed files are sent; nothing in the
    bucket is deleted."""
    bucket = outputs()["Bucket"]
    dry = ["--dryrun"] if a.dry_run else []
    for sub in SEED_DATA:
        aws_cli("s3", "sync", "--only-show-errors", "--exclude", ".DS_Store", *dry, str(DATA_ROOT / sub),
                f"s3://{bucket}/data/{sub}")
        print(f"data/{sub}", flush=True)
    for kind in CACHE_KINDS:
        aws_cli("s3", "sync", "--only-show-errors", "--exclude", "locks/*", "--exclude", "*.lock", *dry,
                str(CACHE_ROOT / kind), f"s3://{bucket}/cache/{kind}")
        print(f"cache/{kind}", flush=True)


def manifest_files() -> list[dict]:
    return json.loads((REPO / "bench" / "manifest.json").read_text())["files"]


def bucket_sizes(s3, bucket: str, prefix: str) -> dict[str, int]:
    out = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        out.update({o["Key"]: o["Size"] for o in page.get("Contents", [])})
    return out


def source_url(f: dict, zenodo: dict) -> str | None:
    """Where a raw file can be downloaded again: adsb.lol's GitHub releases, or its Zenodo record (matched by
    name and size). None if neither applies."""
    name = Path(f["path"]).name
    if f["path"].startswith("raw/adsb/") and "planes-readsb" in name:
        tag = name.split(".tar")[0]
        return f"https://github.com/adsblol/globe_history_{name[1:5]}/releases/download/{tag}/{name}"
    m = re.match(r"https://zenodo\.org/records/(\d+)", f.get("source") or "")
    if m:
        rec = m.group(1)
        if rec not in zenodo:
            import urllib.request
            with urllib.request.urlopen(f"https://zenodo.org/api/records/{rec}", timeout=60) as r:
                zenodo[rec] = {x["key"]: x for x in json.loads(r.read())["files"]}
        hit = zenodo[rec].get(name)
        if hit and hit["size"] == f["bytes"]:
            return hit["links"]["self"]
    return None


def fetch_plan(s3, bucket: str) -> tuple[list[dict], list[dict]]:
    """The raw files not yet in the bucket at their size: those with a public URL, and the rest."""
    have = bucket_sizes(s3, bucket, "data/raw/")
    plan, rest, zenodo = [], [], {}
    for f in manifest_files():
        if not f["path"].startswith("raw/") or have.get(f"data/{f['path']}") == f["bytes"]:
            continue
        if any(f["path"].startswith(p + "/") for p in SEED_DATA):
            continue       # `runs seed` sends these from here
        url = source_url(f, zenodo)
        (plan if url else rest).append({"path": f["path"], "url": url, "bytes": f["bytes"], "sha256": f["sha256"]})
    return plan, rest


def fetch_sources(a) -> None:
    """Plans the download of every public raw file the bucket lacks and launches a box to fetch them."""
    out = outputs()
    bucket = out["Bucket"]
    s3 = session().client("s3")
    plan, rest = fetch_plan(s3, bucket)
    gb = sum(i["bytes"] for i in plan) / 1e9
    print(f"{len(plan)} files ({gb:.1f} GB) to fetch from their sources")
    for r in rest:
        print(f"  no public URL, sent from here: {r['path']} ({r['bytes'] / 1e6:.1f} MB)")
    if a.dry_run:
        return
    for r in rest:       # files written alongside the downloads (record metadata, checksum lists): small
        s3.upload_file(str(DATA_ROOT / r["path"]), bucket, f"data/{r['path']}")
    if not plan:
        return
    key = f"plans/{datetime.datetime.now():%Y%m%d-%H%M%S}-fetch.json"
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps({"files": plan}, indent=1).encode())
    a.topic, a.case, a.input, a.cache, a.jobs = "aws-fetch-sources", [], [], [], None
    a.on_demand, a.max_hours, a.checkpoint_minutes, a.wait = False, 6, 5, False
    a.command = ["python3", "tools/aws/box/fetch_sources.py", f"s3://{bucket}/{key}", bucket]
    launch(a)


# ---- the dev box ---------------------------------------------------------------------------------------

def dev(a) -> None:
    out = outputs()
    iid = out["DevBoxId"]
    ec2 = session().client("ec2")
    if a.action == "start":
        ec2.start_instances(InstanceIds=[iid])
        ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
        print(f"{iid} running")
    elif a.action == "stop":
        ec2.stop_instances(InstanceIds=[iid])
        print(f"{iid} stopping")
    elif a.action == "status":
        i = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
        print(iid, i["State"]["Name"], i["InstanceType"], i["Placement"]["AvailabilityZone"])
    elif a.action in ("shell", "sync", "run"):
        dev_ready(ec2, iid)
    if a.action == "shell":
        os.execvp("aws", ["aws", "--profile", profile(), "--region", REGION, "ssm", "start-session",
                          "--target", iid])
    elif a.action == "sync":
        dev_sync(out)
    elif a.action == "run":
        dev_sync(out)
        dev_run(iid, " ".join(a.command))


DEV_CHECKOUT = "/home/ubuntu/branch"


def dev_ready(ec2, iid: str) -> None:
    """Starts the dev box if the idle alarm stopped it, and waits until Systems Manager can reach it."""
    state = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]
    if state in ("stopped", "stopping"):
        print(f"starting the dev box ({state})", flush=True)
        if state == "stopping":
            ec2.get_waiter("instance_stopped").wait(InstanceIds=[iid])
        ec2.start_instances(InstanceIds=[iid])
        ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    ssm = session().client("ssm")
    for _ in range(60):
        info = ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": [iid]}])
        if [i for i in info["InstanceInformationList"] if i["PingStatus"] == "Online"]:
            return
        time.sleep(5)
    sys.exit("the dev box is running but Systems Manager can't reach it")


def dev_sync(out: dict) -> str:
    """Puts this branch on the dev box at ~/branch: the same bundle, diff and untracked files as a job."""
    bucket = out["Bucket"]
    s3 = session().client("s3")
    key = f"dev/{datetime.datetime.now():%Y%m%d-%H%M%S}"
    with tempfile.TemporaryDirectory() as tmp:
        code = code_bundle(Path(tmp))
        for f in sorted(Path(tmp).iterdir()):
            s3.upload_file(str(f), bucket, f"{key}/code/{f.name}")
    s3.upload_file(str(HERE / "box" / "devsync.sh"), bucket, f"{key}/devsync.sh")
    # the script travels as a file: Run Command and the login shell would each re-quote an inline one
    script = (f"s5cmd --log error cp 's3://{bucket}/{key}/devsync.sh' /tmp/devsync.sh && "
              f"bash /tmp/devsync.sh s3://{bucket}/{key}/code {code['git_commit']} {DEV_CHECKOUT}")
    dev_run(out["DevBoxId"], script, cwd=None, quiet=True)
    print(f"dev box ~/branch at {code['git_commit'][:7]}{' (dirty)' if code['git_dirty'] else ''}")
    return code["git_commit"]


def dev_run(iid: str, command: str, cwd: str | None = DEV_CHECKOUT, quiet: bool = False) -> None:
    """Runs a shell command on the dev box as ubuntu (login shell, so the data and cache roots are set)
    through Systems Manager, and prints its output."""
    ssm = session().client("ssm")
    inner = f"cd {cwd} && {command}" if cwd else command
    wrapped = f"sudo -iu ubuntu bash -lc {shlex_quote(inner)}"
    cmd = ssm.send_command(InstanceIds=[iid], DocumentName="AWS-RunShellScript",
                           Parameters={"commands": [wrapped], "executionTimeout": ["7200"]},
                           TimeoutSeconds=60)["Command"]["CommandId"]
    while True:
        time.sleep(3)
        try:
            r = ssm.get_command_invocation(CommandId=cmd, InstanceId=iid)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if r["Status"] not in ("Pending", "InProgress", "Delayed"):
            break
    if not quiet or r["Status"] != "Success":
        print(r.get("StandardOutputContent", ""), end="")
        print(r.get("StandardErrorContent", ""), end="", file=sys.stderr)
    if r["Status"] != "Success":
        sys.exit(f"dev box command {r['Status']} (exit {r.get('ResponseCode')})")


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="runs", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    la = sub.add_parser("launch", help="run a command on its own box")
    la.add_argument("topic", help="the run folder's topic, as for new_run.py")
    la.add_argument("--case", action="append", default=[], help="a bench case whose inputs the box needs")
    la.add_argument("--input", action="append", default=[], help="a file or folder under the data root")
    la.add_argument("--cache", action="append", default=[], help=f"a cache kind to bring: {', '.join(CACHE_KINDS)}")
    la.add_argument("--jobs", type=int, help="DOPPLERTRACK_JOBS on the box (default: its physical cores)")
    la.add_argument("--size", default="16xlarge", help="instance size of every family (default: 16xlarge)")
    la.add_argument("--on-demand", action="store_true", help="on-demand instead of spot, for deciding runs")
    la.add_argument("--max-hours", type=float, default=12, help="stop the command after this long (default: 12)")
    la.add_argument("--checkpoint-minutes", type=float, default=10, help="upload the run folders this often")
    la.add_argument("--repo", help="ship this checkout instead of the one runs is in (e.g. a worktree at another commit)")
    la.add_argument("--wait", action="store_true", help="wait for it, then pull")
    la.epilog = "then -- and the command, run with bash in the checkout"
    la.set_defaults(command=[])
    for name, help_ in (("status", "list jobs, or one job's status"), ("wait", "wait until a job ends"),
                        ("pull", "copy a job's run folders and cache entries here"), ("log", "a job's command.log"),
                        ("cancel", "terminate a job's box"), ("interrupt", "send a job's spot box a real interruption")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("job", nargs="?" if name == "status" else None)
    sub.add_parser("seed-tools", help="put uv and ffmpeg for each architecture in the bucket")
    fs = sub.add_parser("fetch-sources", help="fetch the public raw files the bucket lacks on a box")
    fs.add_argument("--size", default="4xlarge", help="instance size (default: 4xlarge; the job is network-bound)")
    fs.add_argument("--dry-run", action="store_true", help="only print the plan")
    sd = sub.add_parser("seed", help="upload what has no public source, and the caches")
    sd.add_argument("--dry-run", action="store_true")
    dv = sub.add_parser("dev", help="the persistent dev box")
    dv.add_argument("action", choices=("start", "stop", "status", "shell", "sync", "run"))
    dv.set_defaults(command=[])
    argv = sys.argv[1:] if argv is None else list(argv)
    command = []
    if "--" in argv:     # everything after the first -- is the command, options and all
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    if hasattr(a, "command"):
        a.command = command
    if a.cmd == "launch":
        job = launch(a)
        if a.wait:
            a.job = job
            st = wait(a)
            pull(a)
            sys.exit(0 if st.get("state") == "done" else 1)
    else:
        {"status": status, "wait": wait, "pull": pull, "log": log, "cancel": cancel, "interrupt": interrupt,
         "seed-tools": seed_tools, "seed": seed, "fetch-sources": fetch_sources,
         "dev": dev}[a.cmd](a)


if __name__ == "__main__":
    main()
