#!/bin/bash
# A rehearsal on the dev box (`runs launch --rehearse`): rehearse.sh <bucket> <job>, as root. The job's own
# supervisor runs in a private mount namespace with a fresh folder bind-mounted at /scratch, so the job sees a
# fleet box's layout (/scratch/data, /scratch/dopplertrack), environment and network, and two rehearsals never
# share a /scratch. The supervisor reports to jobs/<job>/status.json and leaves the box up; the folder is removed.
set -uo pipefail
bucket=$1 job=$2
dir=/home/ubuntu/rehearse/$job
export AWS_REGION=us-west-2 DOPPLERTRACK_KEEP_BOX=1 HOME=/root
mkdir -p "$dir" /scratch
trap 'rm -rf "$dir" "$dir.supervisor.py"' EXIT
s5cmd --log error cp "s3://$bucket/jobs/$job/supervisor.py" "$dir.supervisor.py" || exit 1
unshare --mount --propagation private bash -c 'mount --bind "$0" /scratch && exec python3 "$1" --bucket "$2" --job "$3"' \
  "$dir" "$dir.supervisor.py" "$bucket" "$job"
