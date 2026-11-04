"""How much of its box each job uses: a temporary check for jobs holding cores they leave idle.

    tools/aws/runs fleet --util              every running box: its 5- and 15-minute CPU, elapsed time, idle vCPU-hours
    tools/aws/runs fleet --util --history    every job today, over its whole run (finished ones too)
    tools/aws/runs fleet --util --watch 10   a snapshot every 10 minutes into a new run folder, for an hour's shape

A box is under-used when its CPU stays below 60 % (over 15 minutes, or over its whole run with --history) after its
first 5 minutes, which bootstrap and input pulls take. Idle vCPU-hours = (1 - utilisation) x vCPUs x hours, the
cores paid for and left unused. Peak memory is the supervisor's own (MemTotal - MemAvailable, sampled every 5 s;
EC2 publishes no memory metric without the CloudWatch agent), from jobs launched after it was added. The numbers
are EC2's own CPUUtilization metric (5-minute points, no agent), read
with GetMetricStatistics, whose calls count against CloudWatch's free 1M API requests a month."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import runs

UNDER = 60.0               # % below which a box that has run past GRACE_MIN is under-used
GRACE_MIN = 5
# whose job a topic is: the first owner one of whose words appears in the job id
OWNERS = (("E", ("aws-",)), ("PM", ("pm-",)),
          ("A", ("hypotheses", "timing-sweep", "comparable-score", "b1b2")),
          ("B", ("locate", "savedfit", "saved-fit", "tier1", "refit", "bench")),
          ("C", ("hmm", "whiten", "warp", "sde-c")), ("D", ("turn-model", "alaska", "model-error")))
_VCPUS: dict[tuple[str, str], int] = {}


def owner(job: str) -> str:
    return next((o for o, words in OWNERS if any(w in job for w in words)), "?")


def vcpus(region: str, itype: str) -> int:
    if (region, itype) not in _VCPUS:
        d = runs.session(region).client("ec2").describe_instance_types(InstanceTypes=[itype])["InstanceTypes"][0]
        _VCPUS[(region, itype)] = d["VCpuInfo"]["DefaultVCpus"]
    return _VCPUS[(region, itype)]


def cpu(region: str, iid: str, start: datetime.datetime, end: datetime.datetime) -> list[tuple[datetime.datetime, float]]:
    """The 5-minute average CPU points of an instance between start and end, oldest first."""
    if end - start < datetime.timedelta(minutes=5):      # nothing past the grace period yet
        return []
    cw = runs.session(region).client("cloudwatch")
    pts = cw.get_metric_statistics(Namespace="AWS/EC2", MetricName="CPUUtilization",
                                   Dimensions=[{"Name": "InstanceId", "Value": iid}], StartTime=start, EndTime=end,
                                   Period=300, Statistics=["Average"])["Datapoints"]
    return sorted((p["Timestamp"], p["Average"]) for p in pts)


def row(job: str, region: str, iid: str, itype: str, t0: datetime.datetime, t1: datetime.datetime,
        history: bool, mem: dict | None = None) -> dict:
    mem = mem or {}
    n = vcpus(region, itype)
    hours = (t1 - t0).total_seconds() / 3600
    pts = cpu(region, iid, t0 + datetime.timedelta(minutes=GRACE_MIN), t1)
    last = [v for _, v in pts]
    u5 = last[-1] if last else None
    u15 = sum(last[-3:]) / len(last[-3:]) if last else None
    whole = sum(last) / len(last) if last else None
    judged = whole if history else u15
    idle = (1 - whole / 100) * n * max(0.0, hours - GRACE_MIN / 60) if whole is not None else None
    return {"owner": owner(job), "job": job, "region": region, "instance": iid, "type": itype, "vcpus": n,
            "mem_peak_gb": mem.get("mem_peak_gb"), "mem_total_gb": mem.get("mem_total_gb"),
            "elapsed_min": round(hours * 60), "cpu_5min": u5, "cpu_15min": u15, "cpu_run": whole,
            "idle_vcpu_h": idle, "under": judged is not None and hours * 60 > GRACE_MIN and judged < UNDER}


def running_rows() -> list[dict]:
    now = datetime.datetime.now(datetime.timezone.utc)
    s3, bucket = runs.session().client("s3"), runs.outputs()["Bucket"]
    out = []
    for region in (r for r in runs.JOB_REGIONS if runs.deployed(r)):
        r = runs.session(region).client("ec2").describe_instances(Filters=[
            {"Name": "tag:project", "Values": ["dopplertrack"]}, {"Name": "instance-state-name", "Values": ["running"]}])
        for res in r["Reservations"]:
            for i in res["Instances"]:
                tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                job = tags.get("dopplertrack-job") or tags.get("Name", "dev box")
                st = runs.get_status(s3, bucket, job) if tags.get("dopplertrack-job") else {}
                out.append(row(job, region, i["InstanceId"], i["InstanceType"], i["LaunchTime"], now, False, st))
    return out


def history_rows(day: datetime.date) -> list[dict]:
    """Every job whose box started on `day` (UTC), over its whole run, from the jobs' own status records."""
    s3 = runs.session().client("s3")
    bucket = runs.outputs()["Bucket"]
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="jobs/", Delimiter="/"):
        for p in page.get("CommonPrefixes", []):
            job = p["Prefix"].split("/")[1]
            st = runs.get_status(s3, bucket, job)
            host = st.get("host") or {}
            if not host.get("instance_id") or not st.get("started"):
                continue
            t0 = datetime.datetime.fromisoformat(st["started"])
            if t0.astimezone(datetime.timezone.utc).date() != day:
                continue
            end = st.get("finished") or (st.get("updated") if st.get("state") in runs.TERMINAL else None)
            t1 = datetime.datetime.fromisoformat(end) if end else now     # a cancelled job ends at its last status
            out.append(row(job, host["region"], host["instance_id"], host["instance_type"], t0, t1, True, st))
    return out


def report(rows: list[dict], history: bool) -> str:
    def pct(x):
        return f"{x:4.0f}%" if x is not None else "   –"
    lines = [f"{'owner':5s} {'job':48s} {'type':14s} {'vCPU':>4s} {'min':>4s} "
             + ("  run " if history else "  5m   15m ") + " idle vCPU-h  peak mem"]
    for r in sorted(rows, key=lambda r: (r["owner"], -(r["idle_vcpu_h"] or 0))):
        cols = pct(r["cpu_run"]) if history else f"{pct(r['cpu_5min'])} {pct(r['cpu_15min'])}"
        idle = f"{r['idle_vcpu_h']:6.1f}" if r["idle_vcpu_h"] is not None else "     –"
        mem = f"{r['mem_peak_gb']:5.1f}/{r['mem_total_gb']:.0f} GB" if r.get("mem_peak_gb") is not None else "       –"
        lines.append(f"{r['owner']:5s} {r['job'][:48]:48s} {r['type']:14s} {r['vcpus']:4d} {r['elapsed_min']:4d} "
                     f"{cols} {idle}  {mem}{'  UNDER-USED' if r['under'] else ''}")
    lines.append("")
    for o in sorted({r["owner"] for r in rows}):
        mine = [r for r in rows if r["owner"] == o]
        under = [r for r in mine if r["under"]]
        idle = sum(r["idle_vcpu_h"] or 0 for r in mine)
        held = sum(r["vcpus"] * r["elapsed_min"] / 60 for r in mine)
        worst = ", ".join(f"{r['job'].removeprefix('2026-11-04-')} ({r['type']}, "
                          f"{(r['cpu_run'] if history else r['cpu_15min']) or 0:.0f}%)" for r in
                          sorted(under, key=lambda r: -(r["idle_vcpu_h"] or 0))[:4])
        lines.append(f"{o}: {len(mine)} boxes, {len(under)} under-used; {idle:.0f} of {held:.0f} vCPU-hours idle"
                     + (f"; worst: {worst}" if worst else ""))
    return "\n".join(lines)


def main(a) -> None:
    if a.watch:
        run = Path(subprocess.run([sys.executable, str(runs.REPO / "tools" / "data" / "new_run.py"), "aws-fleet-util"],
                                  capture_output=True, text=True, check=True).stdout.strip())
        print(f"snapshots every {a.watch} min into {run}", flush=True)
        while True:
            rows = running_rows()
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            with open(run / "snapshots.jsonl", "a") as f:
                f.write(json.dumps({"at": stamp, "rows": rows}, default=str) + "\n")
            with open(run / "report.txt", "a") as f:
                f.write(f"=== {stamp}\n{report(rows, False)}\n\n")
            time.sleep(60 * a.watch)
    rows = history_rows(datetime.datetime.now(datetime.timezone.utc).date()) if a.history else running_rows()
    print(report(rows, a.history))
