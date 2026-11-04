"""runs: long dopplertrack jobs on their own AWS box, and the dev box.

    tools/aws/runs launch <topic> [--case ID] [--input PATH] [--cache KIND] [--jobs N] [--size 16xlarge]
                          [--on-demand] [--shards N] [--repo CHECKOUT] [--max-hours H] [--wait] -- <command>
    tools/aws/runs launch --resume JOB      (the same run folder, continued on a fresh box)
    tools/aws/runs status [JOB]      tools/aws/runs wait JOB      tools/aws/runs pull JOB      tools/aws/runs fleet
    tools/aws/runs log JOB           tools/aws/runs cancel JOB    tools/aws/runs interrupt JOB
    tools/aws/runs seed-tools        tools/aws/runs seed [--dry-run] [--run FOLDER ...]
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
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
STACK = "DopplertrackFleet"
REGION = "us-west-2"     # the bucket's and the dev box's
# where a job box may run, tried in this order (app.py deploys a compute stack in each)
JOB_REGIONS = ("us-west-2", "us-west-1", "us-east-2", "us-east-1", "eu-central-1")
NOT_OFFERED = {"us-west-1": {"c8gd"}}     # families a region lacks, so the fleet doesn't ask for them
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


def session(region: str = REGION):
    import boto3
    return boto3.Session(profile_name=profile(), region_name=region)


_OUTPUTS: dict[str, dict | None] = {}


def outputs(region: str = REGION) -> dict:
    if _OUTPUTS.get(region) is None:
        cf = session(region).client("cloudformation")
        stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
        _OUTPUTS[region] = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    return _OUTPUTS[region]


def deployed(region: str) -> bool:
    """Whether the region has its compute stack (a region listed here may not be deployed yet)."""
    try:
        return bool(outputs(region).get("TemplateArm64"))
    except Exception:       # noqa: BLE001 - no stack, or the region not reachable: skip it
        return False


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
        traces = c.get("flight_data", {}).get("traces")          # one file, or one per UTC day
        paths = [c.get("audio", {}).get("path"), c.get("spectrogram"),
                 *([traces] if isinstance(traces, str) else traces or [])]
        paths += [d["path"] for d in c.get("derived", [])]
        for p in paths:
            if p and p not in out:
                out.append(p)
    return out


def listed_inputs(doc: dict) -> tuple[list[str], list[str], list[str]]:
    """(cases, data-root paths, cache kinds) from a job's own listing: tools/data/shards.py --inputs
    ({cases, inputs, cache_kinds, cpa_tables}) or `bench inputs` ({data, repo, cache} entries). CPA tables
    and repo files need nothing: the box rebuilds the one and has the other."""
    cases = list(doc.get("cases", []))
    paths = list(doc.get("inputs", [])) + [e["path"] for e in doc.get("data", [])]
    kinds = list(doc.get("cache_kinds", []))
    kinds += [e["path"].split("/", 1)[0] for e in doc.get("cache", []) if "/" in e["path"]]
    return cases, list(dict.fromkeys(paths)), [k for k in dict.fromkeys(kinds) if k in CACHE_KINDS]


def fleet_request(out: dict, job: str, size: str, on_demand: bool, families=FAMILIES, region: str = REGION) -> dict:
    """The create_fleet arguments: one instance, any listed family of `size` in any of the subnets."""
    subnets = out["Subnets"].split(",")
    configs = []
    for arch, fams in families.items():
        fams = [f for f in fams if f not in NOT_OFFERED.get(region, ())]
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


def launch_all(a) -> list[str]:
    """One job, or with --shards n, n jobs <topic>-s<k>of<n>, each on its own box with DOPPLERTRACK_SHARD=k
    and DOPPLERTRACK_SHARDS=n set."""
    if a.shards <= 1:
        return [launch(a)]
    a.only_shard = getattr(a, "only_shard", None)
    pending = []        # every shard claimed and shipped first, then placed together
    for k in (a.only_shard or range(1, a.shards + 1)):
        b = argparse.Namespace(**vars(a))
        b.topic, b.shard, b.defer = f"{a.topic}-s{k}of{a.shards}", [k, a.shards], True
        pending.append((k, launch(b), b))
    s3, bucket = session().client("s3"), outputs()["Bucket"]
    deadline = time.time() + 60 * (getattr(a, "wait_for_capacity", 0) or 0)
    jobs = []
    while True:         # one round: each waiting shard tries every region once; no shard holds back another
        still = []
        for k, job, b in pending:
            if place(b, job, s3, bucket, 0, final=False):
                jobs.append(job)
            else:
                still.append((k, job, b))
        pending = still
        if not pending or time.time() >= deadline:
            break
        print(f"{len(pending)} of {a.shards} shards waiting for capacity: {[k for k, _, _ in pending]}; "
              "next round in 60 s", flush=True)
        time.sleep(60)
    for k, job, b in pending:
        place(b, job, s3, bucket, 0, final=True)
    if pending:
        failed = [k for k, _, _ in pending]
        sys.exit(f"{len(failed)} of {a.shards} shards not launched: {failed}; relaunch them with "
                 f"`--shards {a.shards} --only-shard K` once capacity frees")
    return jobs


def is_run_path(p: str) -> bool:
    return p.strip("/") == "runs" or p.strip("/").startswith("runs/")


def check_run_input(p: str) -> str:
    """A run-folder input names one folder (or a file in one), never runs/ itself."""
    parts = p.strip("/").split("/")
    if parts[0] != "runs" or len(parts) < 2 or not parts[1]:
        sys.exit(f"--input-run {p}: give one run folder, runs/<yyyy-mm-dd>-<topic>[/...], not the whole of runs/")
    return "/".join(parts)


def seed_run_inputs(s3, bucket: str, inputs: list[str]) -> None:
    """Inputs under runs/ (small reference files from earlier runs) go up from here when the bucket lacks
    them or they changed; data/ inputs come from the seed."""
    for rel in inputs:
        if rel.startswith("runs/"):
            src = DATA_ROOT / rel
            if not src.exists():
                sys.exit(f"--input {rel}: not in {DATA_ROOT}")
            if src.is_dir():
                aws_cli("s3", "sync", "--only-show-errors", str(src), f"s3://{bucket}/data/{rel}")
            else:
                aws_cli("s3", "cp", "--only-show-errors", str(src), f"s3://{bucket}/data/{rel}")


def launch(a) -> str:
    out = outputs()
    s3 = session().client("s3")
    bucket = out["Bucket"]
    prior = None
    if a.resume:     # the same run folder, continued on a fresh box: the command, inputs and caches as before
        prior = json.loads(s3.get_object(Bucket=bucket, Key=f"jobs/{a.resume}/spec.json")["Body"].read())
        a.topic = a.topic or prior["topic"]
        a.command = a.command or [prior["command"]]
        a.input, a.case = a.input or prior["inputs"], []
        a.input_run = (getattr(a, "input_run", None) or []) + [i for i in a.input if is_run_path(i)]
        a.input = [i for i in a.input if not is_run_path(i)]
        a.cache = a.cache or prior["caches"]
        a.jobs = a.jobs or prior.get("jobs")
        a.shard = prior.get("shard")
    if not a.topic or not TOPIC.fullmatch(a.topic):
        sys.exit("topic: lowercase letters, digits and hyphens")
    command = " ".join(a.command).strip()
    if not command:
        sys.exit("give the command after --")
    for k in a.cache:
        if k not in CACHE_KINDS:
            sys.exit(f"--cache takes {', '.join(CACHE_KINDS)}")
    if getattr(a, "inputs_from", None):     # the job lists its own inputs; run that listing in its checkout
        repo = Path(a.repo).resolve() if a.repo else REPO
        listing = subprocess.run(a.inputs_from, shell=True, cwd=repo, capture_output=True, text=True, check=True)
        cases, paths, kinds = listed_inputs(json.loads(listing.stdout))
        a.case, a.input, a.cache = a.case + cases, a.input + paths, a.cache + kinds
        print(f"inputs from the job: {len(cases)} cases, {len(paths)} paths, caches {kinds}")
    explicit_runs = [p for p in a.input if is_run_path(p)]
    if explicit_runs:     # run folders are outputs: one goes up only when named with --input-run
        sys.exit(f"--input {explicit_runs[0]}: run folders are outputs; name the one a job reads with --input-run")
    a.input = a.input + [check_run_input(p) for p in getattr(a, "input_run", None) or []]
    inputs = case_inputs(a.case) + [p for p in a.input if p not in case_inputs(a.case)]
    inputs = list(dict.fromkeys(inputs))
    for p in inputs:
        if is_run_path(p):
            check_run_input(p)
    seed_run_inputs(s3, bucket, inputs)
    caches = list(dict.fromkeys(a.cache or (["terrarium"] if a.case else [])))
    with tempfile.TemporaryDirectory() as tmp:
        code = code_bundle(Path(tmp) / "code", repo=Path(a.repo).resolve() if getattr(a, "repo", None) else REPO)
        ids = candidate_ids(f"{prior['run']}-resume", datetime.date.min) if prior else \
            candidate_ids(a.topic, datetime.date.today())
        for job in ids:
            if prior:
                job = job.split("-", 3)[-1]      # candidate_ids put a date in front; a resume keeps the run's
            if (DATA_ROOT / "runs" / job).exists():
                continue
            spec = {"job": job, "run": prior["run"] if prior else job, "topic": a.topic,
                    "resume_of": a.resume, "shard": getattr(a, "shard", None), "command": command, "inputs": inputs,
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
    a._code = code
    if getattr(a, "defer", False):       # launch_all places shards together
        return job
    if not place(a, job, s3, bucket, 60 * (getattr(a, "wait_for_capacity", 0) or 0), final=True):
        sys.exit(f"no capacity for {job}")
    return job


def try_regions(a, job: str) -> tuple[list[str], str | None, list[str]]:
    """One fleet request per allowed region and market, nearest first: (instance ids, region, errors)."""
    # spot in each region in turn; then on demand in each only with --fallback-on-demand, so a job never eats
    # the on-demand quota that deciding runs (--on-demand) count on
    markets = [True] if a.on_demand else [False, True] if a.fallback_on_demand else [False]
    errs = []
    for od in markets:
        for region in (r for r in (a.region or JOB_REGIONS) if deployed(r)):
            ids, err = start_box(session(region).client("ec2"), outputs(region), job, a.size, od)
            if ids:
                return ids, region, errs
            errs.append(f"{region} {'on-demand' if od else 'spot'}: {err}")
    return [], None, errs


def place(a, job: str, s3, bucket: str, wait_s: float, final: bool) -> bool:
    """Starts the job's box, retrying every 60 s while every region is full, for up to wait_s. With final,
    a job still without a box is marked failed; else it stays submitted, waiting for capacity."""
    deadline = time.time() + wait_s
    while True:
        ids, region, errs = try_regions(a, job)
        if ids or time.time() >= deadline:
            break
        put_status(s3, bucket, job, {"job": job, "state": "submitted", "stage": "waiting for capacity",
                                     "error": " | ".join(errs), "updated": now()})
        print(f"{job}: every region full ({' | '.join(errs)}); retrying in 60 s", flush=True)
        time.sleep(60)
    if not ids:
        if final:
            put_status(s3, bucket, job, {"job": job, "state": "failed", "stage": "launch",
                                         "error": " | ".join(errs), "updated": now()})
        else:
            put_status(s3, bucket, job, {"job": job, "state": "submitted", "stage": "waiting for capacity",
                                         "error": " | ".join(errs), "updated": now()})
        return False
    if errs:
        print(f"{job}: " + "; ".join(e.split(':')[0] + ' full' for e in errs), flush=True)
    ec2 = session(region).client("ec2")
    ec2.get_waiter("instance_exists").wait(InstanceIds=ids)     # describe lags create_fleet by a moment
    desc = ec2.describe_instances(InstanceIds=ids)["Reservations"][0]["Instances"][0]
    market = desc.get("InstanceLifecycle", "on-demand")
    price = hourly_price(desc["InstanceType"], desc["Placement"]["AvailabilityZone"], market, region)
    s3.put_object(Bucket=bucket, Key=f"jobs/{job}/launch.json", Body=json.dumps(
        {"instance_id": ids[0], "instance_type": desc["InstanceType"], "market": market, "region": region,
         "availability_zone": desc["Placement"]["AvailabilityZone"], "usd_per_hour": price,
         "ebs_usd_per_hour": JOB_EBS_USD_PER_HOUR, "launched": now()}, indent=1).encode())
    code = a._code
    print(f"{job}: {ids[0]} {desc['InstanceType']} {desc['Placement']['AvailabilityZone']} {market} "
          f"${price:.3f}/h, commit {code['git_commit'][:7]}{' (dirty)' if code['git_dirty'] else ''}", flush=True)
    return True


# the job box's 200 GB gp3 root with 6,000 IOPS and 500 MB/s, us-west-2: (200 x 0.08 + 3000 x 0.005 + 375 x 0.04) / 730 h
JOB_EBS_USD_PER_HOUR = 0.063


def start_box(ec2, out: dict, job: str, size: str, on_demand: bool) -> tuple[list[str], str]:
    resp = ec2.create_fleet(**fleet_request(out, job, size, on_demand, region=ec2.meta.region_name))
    ids = [i for inst in resp.get("Instances", []) for i in inst.get("InstanceIds", [])]
    codes = sorted({e.get("ErrorCode") for e in resp.get("Errors", [])})     # one per code, not per type and AZ
    return ids, ", ".join(c for c in codes if c)


def hourly_price(itype: str, az: str, market: str, region: str = REGION) -> float:
    """The box's price now: the spot price in its AZ, or the on-demand list price."""
    sess = session(region)
    if market == "spot":
        h = sess.client("ec2").describe_spot_price_history(
            InstanceTypes=[itype], AvailabilityZone=az, ProductDescriptions=["Linux/UNIX"], MaxResults=1)
        return float(h["SpotPriceHistory"][0]["SpotPrice"])
    pricing = sess.client("pricing", region_name="us-east-1")
    f = [{"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in (
        ("instanceType", itype), ("regionCode", region), ("operatingSystem", "Linux"), ("tenancy", "Shared"),
        ("preInstalledSw", "NA"), ("capacitystatus", "Used"))]
    item = json.loads(pricing.get_products(ServiceCode="AmazonEC2", Filters=f)["PriceList"][0])
    od = next(iter(item["terms"]["OnDemand"].values()))
    return float(next(iter(od["priceDimensions"].values()))["pricePerUnit"]["USD"])


def job_cost(s3, bucket: str, job: str, st: dict) -> str:
    """The box's cost so far (or in all, once the job has ended), from its launch price and run time."""
    try:
        launch = json.loads(s3.get_object(Bucket=bucket, Key=f"jobs/{job}/launch.json")["Body"].read())
    except s3.exceptions.NoSuchKey:
        return ""
    t0 = datetime.datetime.fromisoformat(launch["launched"])
    t1 = datetime.datetime.fromisoformat(st["finished"]) if st.get("finished") else datetime.datetime.now().astimezone()
    hours = max(0.0, (t1 - t0).total_seconds() / 3600)
    usd = hours * (launch["usd_per_hour"] + launch["ebs_usd_per_hour"])
    return f"${usd:.2f} ({launch['instance_type']} {launch['market']}, {hours * 60:.0f} min)"


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


def job_instances(job: str, states=("pending", "running", "stopping", "shutting-down")) -> dict[str, list[str]]:
    """The job's boxes by region."""
    out = {}
    for region in (r for r in JOB_REGIONS if deployed(r)):
        r = session(region).client("ec2").describe_instances(Filters=[
            {"Name": "tag:dopplertrack-job", "Values": [job]}, {"Name": "instance-state-name", "Values": list(states)}])
        ids = [i["InstanceId"] for res in r["Reservations"] for i in res["Instances"]]
        if ids:
            out[region] = ids
    return out


def status(a) -> None:
    bucket = outputs()["Bucket"]
    s3 = session().client("s3")
    if a.job:
        st = get_status(s3, bucket, a.job)
        print(json.dumps({**st, "cost": job_cost(s3, bucket, a.job, st)}, indent=1))
        return
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="jobs/", Delimiter="/")
    print(f"{'job':45s} {'state':12s} {'updated':26s} cost")
    for page in pages:
        for p in page.get("CommonPrefixes", []):
            job = p["Prefix"].split("/")[1]
            if job.startswith("dev-"):       # dev-box syncs from before they moved to dev/: not jobs
                continue
            st = get_status(s3, bucket, job)
            print(f"{job:45s} {st.get('state', '?'):12s} {st.get('updated', ''):26s} {job_cost(s3, bucket, job, st)}")


def fleet(a) -> None:
    """Every project box running now, by region, with its job and hourly price; the jobs whose launch failed
    for capacity or quota in the last day; and the hourly total. With --util, how much CPU each box uses."""
    if getattr(a, "util", False):
        sys.path.insert(0, str(HERE))
        import fleet_util
        return fleet_util.main(a)
    total, rows, launches = 0.0, [], {}
    for region in (r for r in JOB_REGIONS if deployed(r)):
        ec2 = session(region).client("ec2")
        r = ec2.describe_instances(Filters=[{"Name": "tag:project", "Values": ["dopplertrack"]},
                                            {"Name": "instance-state-name", "Values": ["pending", "running"]}])
        for res in r["Reservations"]:
            for i in res["Instances"]:
                tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                market = i.get("InstanceLifecycle", "on-demand")
                key = (i["InstanceType"], i["Placement"]["AvailabilityZone"], market)
                if key not in launches:
                    launches[key] = hourly_price(*key, region)
                total += launches[key]
                rows.append((region, i["InstanceType"], market, launches[key], tags.get("dopplertrack-job", tags.get("Name", "")),
                             i["LaunchTime"].strftime("%H:%M")))
    for row in sorted(rows):
        print(f"{row[0]:10s} {row[1]:14s} {row[2]:9s} ${row[3]:.3f}/h  {row[5]}  {row[4]}")
    by = {}
    for row in rows:
        by[(row[0], row[2])] = by.get((row[0], row[2]), 0) + 1
    print("boxes: " + ", ".join(f"{r} {m} {n}" for (r, m), n in sorted(by.items())) + f"; ${total:.2f}/h in all")
    s3 = session().client("s3")
    bucket = outputs()["Bucket"]
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    failed = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="jobs/"):
        for o in page.get("Contents", []):
            if o["Key"].endswith("/status.json") and o["LastModified"] > since:
                st = json.loads(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())
                if st.get("state") == "failed" and st.get("stage") == "launch":
                    failed.append((st.get("updated", ""), st["job"], st.get("error", "")[:160]))
    for f in sorted(failed):
        print(f"launch failed {f[0]} {f[1]}: {f[2]}")


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


def same_run(folder: Path) -> bool:
    """A local run folder that an earlier job of the same run made (a resumed job's run comes back into
    it): its run.json names the job that started the run, which is the folder's own name."""
    try:
        return json.loads((folder / "run.json").read_text()).get("job") == folder.name
    except (OSError, ValueError):
        return False


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
    try:
        own = json.loads(s3.get_object(Bucket=bucket, Key=f"jobs/{a.job}/spec.json")["Body"].read())["run"]
    except s3.exceptions.NoSuchKey:
        own = a.job
    for name in st.get("run_folders") or [own]:
        local = name if name == own and same_run(DATA_ROOT / "runs" / name) else free_local(name)
        if local != name:
            print(f"runs/{name} exists here; pulling into runs/{local}")
        aws_cli("s3", "sync", "--only-show-errors", f"s3://{bucket}/runs/{name}/", str(DATA_ROOT / "runs" / local))
        print(f"runs/{local}")
    print(f"cost: {job_cost(s3, bucket, a.job, st)}")
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
    for region, these in ids.items():
        session(region).client("ec2").terminate_instances(InstanceIds=these)
    s3 = session().client("s3")
    bucket = outputs()["Bucket"]
    st = get_status(s3, bucket, a.job)
    if st.get("state") not in TERMINAL:
        put_status(s3, bucket, a.job, {**st, "state": "cancelled", "updated": now()})
    print(f"{a.job}: terminated {ids or 'nothing'}")


def interrupt(a) -> None:
    """Sends the job's spot box a real interruption through AWS Fault Injection Service (the supervisor's
    tested path): the 2-minute notice, then termination."""
    boxes = job_instances(a.job, states=("running",))
    if not boxes:
        sys.exit(f"no running box for {a.job}")
    region, ids = next(iter(boxes.items()))
    sess = session(region)
    account = sess.client("sts").get_caller_identity()["Account"]
    role_arn = outputs(region)["FisRoleArn"]
    fis = sess.client("fis")
    tmpl = fis.create_experiment_template(
        description=f"dopplertrack: interrupt {a.job}", roleArn=role_arn,
        stopConditions=[{"source": "none"}], tags={"project": "dopplertrack"},
        targets={"box": {"resourceType": "aws:ec2:spot-instance", "selectionMode": "ALL",
                         "resourceArns": [f"arn:aws:ec2:{region}:{account}:instance/{i}" for i in ids]}},
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
    if a.run:        # only these run folders, for jobs that read them (--input runs/<folder>)
        for name in a.run:
            name = name.removeprefix("runs/").strip("/")
            aws_cli("s3", "sync", "--only-show-errors", *dry, str(DATA_ROOT / "runs" / name),
                    f"s3://{bucket}/data/runs/{name}")
            print(f"data/runs/{name}", flush=True)
        return
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
    a.on_demand, a.fallback_on_demand, a.max_hours, a.checkpoint_minutes, a.wait = False, False, 6, 5, False
    a.resume, a.repo, a.shards, a.shard, a.region, a.wait_for_capacity = None, None, 1, None, None, 90
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
        # each run gets its own checkout, removed when its command ends: callers never see each other's branch
        name = f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        dest = f"{DEV_RUNS}/{name}"
        dev_sync(out, dest, name)
        t0 = time.time()
        try:
            dev_run(iid, f"{' '.join(a.command)}; rc=$?; cd / && rm -rf {dest}; exit $rc", cwd=dest)
        finally:
            print(f"dev box: {time.time() - t0:.0f} s in {dest}", file=sys.stderr)


DEV_CHECKOUT = "/home/ubuntu/branch"     # `runs dev sync`'s, for interactive work
DEV_RUNS = "/home/ubuntu/runs"           # one checkout per `runs dev run`


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


def dev_sync(out: dict, dest: str = DEV_CHECKOUT, name: str | None = None) -> str:
    """Puts this branch on the dev box at dest (~/branch by default): the same bundle, diff and untracked files
    as a job."""
    bucket = out["Bucket"]
    s3 = session().client("s3")
    key = f"dev/{name or datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmp:
        code = code_bundle(Path(tmp))
        for f in sorted(Path(tmp).iterdir()):
            s3.upload_file(str(f), bucket, f"{key}/code/{f.name}")
    s3.upload_file(str(HERE / "box" / "devsync.sh"), bucket, f"{key}/devsync.sh")
    # the script travels as a file: Run Command and the login shell would each re-quote an inline one
    sh = f"/tmp/devsync-{key.split('/')[-1]}.sh"
    script = (f"s5cmd --log error cp 's3://{bucket}/{key}/devsync.sh' {sh} && "
              f"bash {sh} s3://{bucket}/{key}/code {code['git_commit']} {dest}")
    dev_run(out["DevBoxId"], script, cwd=None, quiet=True)
    print(f"dev box {dest} at {code['git_commit'][:7]}{' (dirty)' if code['git_dirty'] else ''}", file=sys.stderr)
    return code["git_commit"]


def dev_run(iid: str, command: str, cwd: str | None = DEV_CHECKOUT, quiet: bool = False) -> None:
    """Runs a shell command on the dev box as ubuntu (login shell, so the data and cache roots are set)
    through Systems Manager, and prints its output."""
    ssm = session().client("ssm")
    inner = f"cd {cwd} && {command}" if cwd else command
    inner = f"export UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed; {inner}"   # as the job boxes do
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
    la.add_argument("topic", nargs="?", help="the run folder's topic, as for new_run.py")
    la.add_argument("--resume", metavar="JOB", help="continue JOB's run folder on a fresh box (after an "
                    "interruption): its partial folder is brought in first; command, inputs and caches as before")
    la.add_argument("--only-shard", type=int, action="append", metavar="K", help="with --shards, launch only "
                    "shard K (repeatable), e.g. the ones that found no capacity")
    la.add_argument("--shards", type=int, default=1, help="launch n boxes, each with DOPPLERTRACK_SHARD=k "
                    "(1..n) and DOPPLERTRACK_SHARDS=n, as jobs <topic>-s<k>of<n>")
    la.add_argument("--case", action="append", default=[], help="a bench case whose inputs the box needs")
    la.add_argument("--input", action="append", default=[], help="a file or folder under the data root, not runs/")
    la.add_argument("--input-run", action="append", default=[], metavar="runs/FOLDER", help="a run folder the job "
                    "reads (or a file in one), uploaded from here first; never runs/ itself")
    la.add_argument("--cache", action="append", default=[], help=f"a cache kind to bring: {', '.join(CACHE_KINDS)}")
    la.add_argument("--inputs-from", metavar="COMMAND", help="a command (run here, in the checkout) that prints "
                    "the job's inputs as JSON: `tools/data/shards.py`'s --inputs or `bench inputs`")
    la.add_argument("--jobs", type=int, help="DOPPLERTRACK_JOBS on the box (default: its physical cores)")
    la.add_argument("--size", default="16xlarge", help="instance size of every family (default: 16xlarge)")
    la.add_argument("--on-demand", action="store_true", help="on-demand instead of spot, for deciding runs")
    la.add_argument("--region", action="append", choices=JOB_REGIONS, help="only this region (repeatable; "
                    f"default: {', '.join(JOB_REGIONS)}, in that order)")
    la.add_argument("--queue-minutes", "--wait-for-capacity", dest="wait_for_capacity", type=float, default=90,
                    metavar="MIN", help="when every region is full (MaxSpotInstanceCountExceeded, VcpuLimitExceeded, "
                    "no capacity), keep the job submitted and retry every 60 s, cycling the regions, for this long "
                    "(default: 90; 0: fail at once)")
    la.add_argument("--fallback-on-demand", action="store_true", help="if no region has spot capacity, start "
                    "an on-demand box rather than fail (off by default: it uses the on-demand quota)")
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
    fl = sub.add_parser("fleet", help="every box running now, by region, with its price, and failed launches")
    fl.add_argument("--util", action="store_true", help="each box's CPU use and idle vCPU-hours (fleet_util.py)")
    fl.add_argument("--history", action="store_true", help="with --util: every job today, over its whole run")
    fl.add_argument("--watch", type=float, metavar="MIN", help="with --util: a snapshot every MIN minutes into a run folder")
    sub.add_parser("seed-tools", help="put uv and ffmpeg for each architecture in the bucket")
    fs = sub.add_parser("fetch-sources", help="fetch the public raw files the bucket lacks on a box")
    fs.add_argument("--size", default="large", help="instance size (default: large, 2 vCPU: the job only waits on "
                    "the network, at 0 %% CPU on a 4xlarge)")
    fs.add_argument("--dry-run", action="store_true", help="only print the plan")
    sd = sub.add_parser("seed", help="upload what has no public source, and the caches")
    sd.add_argument("--dry-run", action="store_true")
    sd.add_argument("--run", action="append", default=[], metavar="FOLDER", help="only this run folder")
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
        jobs = launch_all(a)
        if a.wait:
            states = []
            for job in jobs:
                a.job = job
                states.append(wait(a).get("state"))
                pull(a)
            sys.exit(0 if all(st == "done" for st in states) else 1)
    else:
        {"status": status, "fleet": fleet, "wait": wait, "pull": pull, "log": log, "cancel": cancel, "interrupt": interrupt,
         "seed-tools": seed_tools, "seed": seed, "fetch-sources": fetch_sources,
         "dev": dev}[a.cmd](a)


if __name__ == "__main__":
    main()
