"""runs: long dopplertrack jobs on their own AWS box, and the dev box.

    tools/aws/runs launch <topic> [--case ID] [--input PATH] [--cache KIND] [--jobs N] [--size 16xlarge]
                          [--on-demand] [--max-hours H] [--wait] -- <command>
    tools/aws/runs status [JOB]      tools/aws/runs wait JOB      tools/aws/runs pull JOB
    tools/aws/runs log JOB           tools/aws/runs cancel JOB    tools/aws/runs interrupt JOB
    tools/aws/runs seed-tools        tools/aws/runs seed [--dry-run]
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
# what `seed` uploads: raw/ and derived/ (not reference/, the papers; not runs/, which come back per job)
# and the caches above (PM decision, 2026-11-04)
SEED_DATA = ("raw", "derived")
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
        code = code_bundle(Path(tmp) / "code")
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
    iam = sess.client("iam")
    role_name = "dopplertrack-fis"
    try:
        role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                                                         "Principal": {"Service": "fis.amazonaws.com"}}]}
        role_arn = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust),
                                   Tags=[{"Key": "project", "Value": "dopplertrack"}])["Role"]["Arn"]
        iam.put_role_policy(RoleName=role_name, PolicyName="spot-interrupt", PolicyDocument=json.dumps({
            "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "ec2:SendSpotInstanceInterruptions",
                                                    "Resource": "*", "Condition": {"StringEquals": {
                                                        "aws:ResourceTag/project": "dopplertrack"}}},
                                                   {"Effect": "Allow", "Action": "ec2:DescribeInstances", "Resource": "*"}]}))
        time.sleep(10)    # IAM is eventually consistent
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
    """Uploads the data root (raw/ without the papers, derived/) and the caches a job can use. Only new or
    changed files are sent; nothing in the bucket is deleted."""
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
    elif a.action == "shell":
        os.execvp("aws", ["aws", "--profile", profile(), "--region", REGION, "ssm", "start-session",
                          "--target", iid])
    elif a.action == "sync":
        dev_sync(out)
    elif a.action == "run":
        dev_sync(out)
        dev_run(iid, " ".join(a.command))


DEV_CHECKOUT = "/home/ubuntu/branch"


def dev_sync(out: dict) -> str:
    """Puts this branch on the dev box at ~/branch: the same bundle, diff and untracked files as a job."""
    bucket = out["Bucket"]
    s3 = session().client("s3")
    key = f"jobs/dev-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    with tempfile.TemporaryDirectory() as tmp:
        code = code_bundle(Path(tmp))
        for f in sorted(Path(tmp).iterdir()):
            s3.upload_file(str(f), bucket, f"{key}/code/{f.name}")
    script = f"""set -e
export HOME=/home/ubuntu
cd /home/ubuntu && rm -rf {DEV_CHECKOUT}.new && mkdir -p /tmp/devsync && rm -rf /tmp/devsync/*
s5cmd --log error cp 's3://{bucket}/{key}/code/*' /tmp/devsync/
git clone -q --no-checkout /tmp/devsync/code.bundle {DEV_CHECKOUT}.new
git -C {DEV_CHECKOUT}.new checkout -q --detach {code['git_commit']}
[ -s /tmp/devsync/dirty.patch ] && git -C {DEV_CHECKOUT}.new apply --binary /tmp/devsync/dirty.patch
[ -s /tmp/devsync/untracked.tar ] && tar xf /tmp/devsync/untracked.tar -C {DEV_CHECKOUT}.new
rm -rf {DEV_CHECKOUT} && mv {DEV_CHECKOUT}.new {DEV_CHECKOUT}
cd {DEV_CHECKOUT} && uv sync --frozen -q && git log -1 --oneline"""
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
    la.add_argument("--wait", action="store_true", help="wait for it, then pull")
    la.add_argument("command", nargs=argparse.REMAINDER, help="-- then the command, run with bash in the checkout")
    for name, help_ in (("status", "list jobs, or one job's status"), ("wait", "wait until a job ends"),
                        ("pull", "copy a job's run folders and cache entries here"), ("log", "a job's command.log"),
                        ("cancel", "terminate a job's box"), ("interrupt", "send a job's spot box a real interruption")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("job", nargs="?" if name == "status" else None)
    sub.add_parser("seed-tools", help="put uv and ffmpeg for each architecture in the bucket")
    sd = sub.add_parser("seed", help="upload the data root and caches (long the first time)")
    sd.add_argument("--dry-run", action="store_true")
    dv = sub.add_parser("dev", help="the persistent dev box")
    dv.add_argument("action", choices=("start", "stop", "status", "shell", "sync", "run"))
    dv.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if getattr(a, "command", None) and a.command[:1] == ["--"]:
        a.command = a.command[1:]
    if a.cmd == "launch":
        job = launch(a)
        if a.wait:
            a.job = job
            st = wait(a)
            pull(a)
            sys.exit(0 if st.get("state") == "done" else 1)
    else:
        {"status": status, "wait": wait, "pull": pull, "log": log, "cancel": cancel, "interrupt": interrupt,
         "seed-tools": seed_tools, "seed": seed, "dev": dev}[a.cmd](a)


if __name__ == "__main__":
    main()
