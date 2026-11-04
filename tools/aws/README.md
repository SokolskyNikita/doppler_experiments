# The AWS fleet

Long dopplertrack jobs run on a box of their own in us-west-2 instead of on the shared Mac: one spot
instance per job, started in about 30 s, terminated when the job ends. A persistent dev box runs
`tools/check.sh` and interactive work. Why this design and what it was measured against:
[docs/experiments/2026-11-04-aws-fleet.md](../../docs/experiments/2026-11-04-aws-fleet.md).

## Handoff (2026-11-04, 23:30 UTC)

For a fresh operator, Codex or a new session, taking the fleet over:

1. **Credentials:** the AWS profile `dopplertrack` (IAM user dopplertrack-admin, region us-west-2); never the root
   profile. Every command below reads it from `$AWS_PROFILE`, defaulting to that name.
2. **What is running:** `tools/aws/runs fleet` lists every box with its job and price; `tools/aws/runs status`
   lists every job with its state and cost; `tools/aws/runs fleet --util` shows each box's CPU and memory use.
   At handoff: 10 boxes, $2.32/h (SDE-A's synth-suite shards in us-west-1, three detector-roc-s2 shards
   in us-west-2 that started at 20:03 UTC and are worth a look if they are still running, Seattle pilot-12, the
   dev box). Spot boxes terminate themselves when their job ends, after `--max-hours` (12) at the latest.
3. **Finished jobs:** `runs pull JOB` copies the run folder into `$DOPPLERTRACK_DATA/runs/` (a private job's into
   `private/runs/`) and merges new cache entries; sharded jobs are pulled one by one and merged by the job's own
   `--merge` step. A job stuck in a state: `runs cancel JOB`; an interrupted one: `runs launch --resume JOB`.
4. **The dev box** (`runs dev status`; it was running at handoff): it stops itself after 30 minutes with no
   `runs dev run`, command, shell or load (a timer on the box, `box/devbox-idle.sh`, which replaced a CloudWatch
   alarm that stopped it under running checks). Stop it at once with `runs dev stop`. Full checks run there:
   `runs dev run -- tools/check.sh` (about 80 s); no doppler_track compute runs on the Mac.
5. **Before any new or changed job:** the same launch command with `--check`, then `--rehearse` long enough to
   reach the job's first full stage (section below).
6. **Private data:** refused by default. Only the exact files and case ids in
   `$DOPPLERTRACK_DATA/private/fleet-allow.txt` pass, each added after the owner approved that file by name; at
   handoff it clears the Seattle pilot (seattle-home-20261104-ha-pilot-2: 10 files). The home location never goes
   into git, docs or records.

**Costs to watch.** `runs status` shows each job's cost and `runs fleet` the hourly total. 2026-11-04 cost about
$25 in all, with a peak of about $36/h. Fixed costs: the dev box at $0.32/h while running plus about $39/month
for its disk; S3 about $2/month; spot c8g.16xlarge about $0.92–1.05/h, 4xlarge about $0.21–0.28/h. Cost Explorer
lags by a day.

**Open quota cases.** The vCPU increases (spot to 1,024, on-demand to 512) are support cases, CASE_OPENED, in
us-west-2, us-west-1 and us-east-2. AWS raised all six limits from 256 to 320 while the cases stay open, a
partial grant. us-east-1 and eu-central-1 are at the default 256 + 256 with no request filed: the owner asked to
be consulted before any more filings. Check with
`aws service-quotas list-requested-service-quota-change-history --service-code ec2 --region <r>`.

**Needs attention in the next day.**
- The dev box's idle timer is new: confirm it stopped the box once idle (`runs dev status` should read stopped
  an hour after the last use), and that no check was cut off by it.
- The partial quota grant: answer any AWS follow-up in the Support console, where the cases are.
- Two 0-byte files, `data/derived/traces/day1.launch.log` and `full-24h.launch.log`, are the recorder's empty launch
  logs, in the bucket since the first seed; they reveal only their names and wait for the owner's decision to
  remove them.
- The three detector-roc-s2 shards (above), if still running long past their siblings.

**How to launch.** `tools/aws/runs launch TOPIC --shards N [--size 8xlarge] [--on-demand] [--repo CHECKOUT]
--inputs-from '<the job's --inputs or bench inputs command>' -- <command>`: one box per shard, each with
`DOPPLERTRACK_SHARD_SPEC=k/N`; spot in us-west-2, then us-west-1, then us-east-2, waiting up to
`--queue-minutes` (90) while all are full; on-demand only with `--on-demand` (a deciding run) or
`--fallback-on-demand`. A shard that still found nothing is listed at the end: relaunch it with
`--shards N --only-shard K`. `runs fleet` shows every box running now, its price, and failed launches.

```
tools/aws/runs launch <topic> [--case ID] [--input PATH] [--cache KIND] [--jobs N] [--size 16xlarge]
                              [--on-demand] [--repo CHECKOUT] [--wait] -- <command>
tools/aws/runs status [JOB] | wait JOB | pull JOB | log JOB | cancel JOB | interrupt JOB
tools/aws/runs dev start | stop | status | shell | sync | run -- <command>
tools/aws/runs seed | seed-tools | fetch-sources
```

## Before a real launch: check, then rehearse

Add one flag to the launch command you are about to run:

- **`--check`** (seconds; writes nothing): resolves every input as the launch would, applies the private-data
  guard, checks each input is in the bucket (or here, for run folders and owner-allowed files), checks the
  caches and the code bundle, and prints the plan: boxes, size, market, code, and how many start now in each
  region and how many would queue. It runs no code.
- **`--rehearse [--rehearse-minutes 3]`** (a few minutes; no fleet box): ships the job as a launch would and runs
  it on the dev box through its own supervisor, in a private mount namespace with a fresh folder at `/scratch`,
  so it sees a fleet box's layout (`/scratch/data`, `/scratch/dopplertrack`, `private/runs/` for a private job),
  environment and network. At the cut-off the command is stopped; the verdict is `rehearsal-ok` (still running,
  or finished) or `rehearsal-failed`, with the log's tail. Nothing comes back and the dev box stays up. With
  `--shards N` it rehearses one shard (`--rehearse-shard K`, default 1); with `--resume JOB` it replays that job's
  code, inputs and command. Set the minutes to cover the job's first full stage: a bug is only caught once the
  job reaches it (the Seattle pilot-2 path bug showed in 10 s, pilot-3's missing folder after 300 s). The dev box
  has 8 cores and 16 GB, so it is slower than a fleet box and can't rehearse a job that needs more memory.

What neither catches: anything after the cut-off, and what needs a fleet box's cores or memory.

## A job, end to end

`runs launch` (from the checkout whose branch should run, or with `--repo`):
1. claims the job id `<yyyy-mm-dd>-<topic>[-n]`, free here and in the bucket, which is also its run folder's
   name;
2. ships the branch to `jobs/<id>/code/` in the bucket: a git bundle of HEAD, the uncommitted diff and the
   untracked files. On the box, `git rev-parse HEAD` and `git status` say what they said here, so bench's
   and new_run.py's provenance is the Mac's. Nothing is pushed to GitHub;
3. starts an instant EC2 Fleet of one instance, spot unless `--on-demand`, price-capacity-optimized over
   c8g, c8gd, c7g (arm64) and c7a (amd64) of `--size` across a region's AZs, trying us-west-2, then
   us-west-1, then us-east-2 (`--region` pins one). A single type in a single AZ is often out of capacity
   (c8gd.16xlarge was, twice, on 2026-11-04). With no spot capacity anywhere it fails, unless
   `--fallback-on-demand`: on-demand quota is kept for the deciding runs that ask for it;
4. with `--shards n`, does this n times, one box per shard, each with `DOPPLERTRACK_SHARD_SPEC=k/n`
   (which tools/data/shards.py reads as its `--shard` default); `--inputs-from '<command>'` takes the
   inputs from a job's own listing (shards.py's `--inputs`, or `bench inputs`).

The box (launch template user data, [box/bootstrap.sh](box/bootstrap.sh)) stripes any instance-store NVMe
as /scratch, installs s5cmd (pinned by hash) and uv and ffmpeg from the bucket, and starts the job's
[supervisor](box/supervisor.py), which:
- rebuilds the branch and runs `uv sync --frozen`;
- pulls the inputs (`--case` adds a bench case's audio, spectrogram, traces and derived files; `--input`
  any file or folder under the data root except runs/; `--input-run runs/<folder>` an earlier run's folder,
  uploaded from here first: run folders are outputs, so each one a job reads is named, and runs/ as a whole never
  goes up) and the caches (`--cache`: detections, window_fits, terrarium,
  plus every cache delta earlier jobs sent back). CPA tables are rebuilt on the box (under a minute);
- writes `runs/<id>/run.json`: new_run.py's fields plus the instance type, AZ, spot or on-demand, AMI,
  inputs and preparation times;
- runs the command with bash in the checkout, with `$RUN`, `$DOPPLERTRACK_DATA`, `$DOPPLERTRACK_CACHE`
  and `$DOPPLERTRACK_JOB` set and `DOPPLERTRACK_JOBS` from `--jobs` (default: the box's physical cores),
  output to `$RUN/command.log`;
- every 5 s checks the instance metadata for a spot interruption notice; uploads the run folders every
  `--checkpoint-minutes` (10);
- at the end, or on a notice (2 min before AWS reclaims the box), or after `--max-hours` (12): stops the
  command, uploads every run folder the job made and a tarball of the cache entries it added, writes
  `jobs/<id>/status.json`, and powers off, which terminates the box.

`runs wait` follows the status; `runs pull` copies the run folders into `$DOPPLERTRACK_DATA/runs` (under
a new `-n` name if one exists here: never into an existing run) and adds the new cache entries to
`$DOPPLERTRACK_CACHE` without touching any existing file. An interrupted job continues with `runs launch
--resume JOB`: its partial run folder comes to the fresh box, and it runs the job's own code bundle (copied
from `jobs/JOB/code/`, recorded as `code_source` in run.json), not this checkout's, unless `--repo` says otherwise.

Example, the Oyster Bay saved-fit Tier 2 case (157 s from submit to done on 2026-11-04):

```
tools/aws/runs launch oyster-t2 --case oyster-bay --wait -- .venv/bin/python -m bench run oyster-bay --tier t2 --profile saved-fit --run-dir '"$RUN"'
```

Several invocations on one box: a driver that runs them at once with `DOPPLERTRACK_JOBS` split, like
[aws_sweep.sh](../experiments/2026-11-04/aws_sweep.sh) (6 settings at a time with 10 jobs each).

## Private data

The owner's home recordings (household audio, exact home coordinates, the ADS-B the recorder fetches for a circle
around the home) and everything derived from them stay on the Mac. In runs.py: `PRIVATE_PREFIXES` (`private/`,
`incoming/`, `raw/seattle-home/`), any path with a `private` folder in it, every prefix listed one per line in
`$DOPPLERTRACK_DATA/private/exclude.txt` (read at every upload; a missing file adds nothing), and under `derived/traces/` everything but the date-named day traces
(`YYYY-MM-DD/`, `YYYY-MM-DD.log`), since the recorder writes its sessions there. `runs launch` refuses those paths
from `--input`, `--input-run`, `--inputs-from` and a case's files, and any case marked `private: true` or naming a
`site`; `runs seed` turns them into `--exclude` filters on every sync (day traces kept by `--include`), and
`fetch-sources` skips them. A new private location goes into exclude.txt before data lands there. `runs seed` also prints what it uploads and
excludes, and refuses to run while a recorder session (`2026MMDD-` then ha-pilot, pilot, selftest, speakertest,
subtest, coexist or latency) sits under `derived/traces/`, unless `private/seed-allow.txt` names it: the recorder's
output belongs under `private/`.

**The owner's allow list.** The default is refuse. `$DOPPLERTRACK_DATA/private/fleet-allow.txt` lists the private
files the owner has approved for the fleet, each by name and one exact path per line, added only after that
approval; a case id there only permits that case's launch, and each of its files still needs its own line. A folder
is never cleared (a listed one is refused, and nothing inside it passes unless listed itself). `runs launch` prints
each allowed file, ships it from the Mac and marks the job private: on the box its run folder is
`private/runs/<job>`, its cache `private/cache/`, and no cache entry comes back to the shared cache; `runs pull`
brings the run folder to `$DOPPLERTRACK_DATA/private/runs/`. `runs seed` prints each allowed file and uploads only
those. The exact home location still never goes into git, docs or records (the site-relative frame).

**What a box can't reach.** opensky-network.org refuses the boxes, so `dopplertrack.adsb.AircraftTypes()`, which
fetches Doc 8643 from there into the cache on first use, would fail on a box; the supervisor copies the bucket's
`data/raw/aux/opensky/doc8643AircraftTypes.csv` into every job's cache first (`CACHE_ROOT_FILES` in supervisor.py,
for any other file like it).

## Sizing

Quota is counted in vCPUs per region and market: 256 spot and 256 on-demand in each region until AWS raises it
(increases requested). A box counts its whole size against that, whatever the job uses: a 16xlarge shard costs 64
vCPUs even when its job runs 16 workers, so only four fit in a region. Size the box to the job's workers
(`--size 4xlarge` for 16, `8xlarge` for 32; a vCPU is a core on Graviton and c7a), and shard wider rather than
deeper: more small boxes start sooner, fit the quota's remainders in every region, and lose less to one
interruption. Keep 16xlarge for a single process that really uses 64 workers.

**Is the box the right size?** `runs fleet --util` lists every running box's CPU over the last 5 and 15 minutes
and the vCPU-hours it has left idle, and marks a box under 60 % after its first 5 minutes; `--history` covers
every job today over its whole run, and `--watch 10` appends a snapshot every 10 minutes to a new run folder. It
reads EC2's own CPUUtilization metric with GetMetricStatistics, which counts against CloudWatch's free 1M API
requests a month: nothing to pay at a few dozen boxes every few minutes. A temporary check
([fleet_util.py](fleet_util.py)).

## The dev box

A c8g.2xlarge on demand (8 cores, 16 GB, 300 GB gp3) with the fork at `~/dopplertrack` and the data and
cache roots at `/srv/dopplertrack/{data,cache}`. An alarm stops it after 30 min with no 5-minute CPU
maximum above 5 %; `runs dev` starts it again when it's needed (about 15 s to running, plus Systems
Manager's registration). `runs dev run -- tools/check.sh` puts this branch at `~/branch` (bundle, diff,
untracked) and runs the command there; `runs dev shell` opens a Systems Manager session. There is no SSH
and no inbound port.

## Cost (us-west-2 prices on 2026-11-04, from the EC2 price and spot-price APIs)

| Box | Spot $/h | On-demand $/h |
|---|---|---|
| c8g.16xlarge (64 cores, 128 GB) | 0.92–1.05 | 2.55 |
| c8gd.16xlarge (plus 2 × 1.9 TB NVMe) | 0.87–0.99 | 3.14 |
| c7g.16xlarge | 0.76–0.97 | 2.32 |
| c7a.16xlarge (amd64) | 1.02–1.40 | 3.28 |
| c8g.4xlarge / c7g.4xlarge (`--size 4xlarge`) | 0.21–0.28 (c7g) | 0.64 / 0.58 |
| dev box c8g.2xlarge | – | 0.32 while running |

Plus, per job box, its 200 GB gp3 root at 6,000 IOPS and 500 MB/s: about $0.06/h while it exists. The dev
box's 300 GB root costs about $0.05/h whether it runs or not (about $39/month). S3 holds about 80 GB
($0.023/GB-month, about $2/month, plus replaced versions for 30 days). Transfer between S3 and the boxes
is free (same region, S3 gateway endpoint); `runs pull` to the Mac is internet egress at $0.09/GB, small
for run folders. A Fault Injection interruption costs $0.10 per action-minute.

## Stop, resume, tear down

- A job: `runs cancel JOB` terminates its box (its run folder keeps whatever was last uploaded).
- The dev box: `runs dev stop`, or let the alarm stop it; `runs dev start` resumes it with its disk.
- Everything: `cdk destroy` from `tools/aws` deletes the stack (VPC, roles, templates, dev box) and keeps
  the bucket and all its data (RemovalPolicy RETAIN). A later `cdk deploy` finds the bucket name taken:
  import it, or delete it by hand first, deliberately.

## What you do by hand

1. An AWS profile named `dopplertrack` (or set `$AWS_PROFILE`) with region us-west-2. Today it is the IAM
   user dopplertrack-admin with AdministratorAccess; [operator-policy.json](operator-policy.json) is the
   minimum `runs` and `cdk deploy` need, for scoping it down (replace ACCOUNT). Never the root user's keys.
2. `brew install --cask session-manager-plugin` (for `runs dev shell`), `brew install shellcheck` (for
   check.sh), Node and the CDK CLI (`brew install aws-cdk`), and uv.
3. Once: `cdk bootstrap aws://ACCOUNT/us-west-2` (done), `cd tools/aws && cdk deploy`, `runs seed-tools`,
   `runs seed` (the files with no public source: derived/, YouTube and xeno-canto audio, A2O, the seismic
   windows, aux/, models/ and the caches; about 10 GB, 15 min at 10 MB/s), then `runs fetch-sources`, which
   fetches the rest of raw/ (adsb.lol from GitHub, the Zenodo datasets: about 65 GB) on a box, checks each
   file's SHA-256 against bench/manifest.json and puts it in the bucket. Rerun `runs seed` after adding
   derived files here, and `runs fetch-sources` after adding raw downloads to the manifest.

Nothing secret is in the repo, the bucket or the data root: credentials come from the profile, and the
xeno-canto API key never leaves the Mac.

## The bucket and the role

`s3://dopplertrack-<account>-us-west-2`, private (public access blocked, TLS only), versioned (a replaced
object is kept 30 days), kept when the stack is deleted:

| Prefix | What | Who writes |
|---|---|---|
| `data/raw/`, `data/derived/` | the data root, minus reference/ (the papers) and runs/ | `runs seed`, `fetch-sources` jobs, jobs that build derived files |
| `cache/{detections,window_fits,terrarium}/` | the seeded caches | `runs seed` only |
| `cache-deltas/<job>.tar` | the cache entries a job added | that job |
| `tools/{arm64,amd64}/`, `tools/tools.json` | uv 0.13.7 (MIT or Apache-2.0) and ffmpeg n9.0.2 static (BtbN, GPL-3.0-or-later): sources and hashes in [tools.json](tools.json) | `runs seed-tools` only |
| `jobs/<job>/` | spec, code, supervisor, status (expire after 60 days) | `runs launch`, the job |
| `runs/<run>/` | run folders | the job |
| `dev/`, `plans/` | dev-box syncs (7 days), fetch plans | `runs` |

The boxes' role reads the bucket and writes, without delete, only under `jobs/`, `runs/`, `cache-deltas/`,
`data/raw/` and `data/derived/`; it has Systems Manager and nothing else.

## Checks

`tools/aws/check.sh`, before every deploy: shellcheck on the box scripts, pyflakes, assertions on the
synthesized stack ([stack_checks.py](stack_checks.py): bucket private and versioned, the role's prefixes
and no delete, no inbound rule, IMDSv2 with tags, every output `runs` reads exists), and the offline tests
of `runs` and the supervisor (tests/test_aws_runs.py, also part of the repo's pytest). No AWS call.
