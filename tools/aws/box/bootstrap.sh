#!/bin/bash
# User data of every job box (both launch templates). It mounts scratch space, installs s5cmd (pinned by hash)
# and the tools kept in the bucket, then hands over to the job's supervisor, which `runs launch` put beside the
# job spec. The job id comes from the instance's dopplertrack-job tag. The CDK stack fills in the bucket.
set -uo pipefail
exec > >(tee -a /var/log/dopplertrack-boot.log > /dev/console) 2>&1
BUCKET=@@BUCKET@@
shutdown -h +30     # a boot that hangs before the supervisor starts still ends; the supervisor cancels this

IMDS=http://169.254.169.254/latest
TOKEN=$(curl -sfX PUT "$IMDS/api/token" -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600')
md() { curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" "$IMDS/meta-data/$1"; }
export AWS_REGION=$(md placement/region) HOME=/root DEBIAN_FRONTEND=noninteractive
JOB=$(md tags/instance/dopplertrack-job) || { echo "no dopplertrack-job tag"; shutdown -h now; exit 1; }
echo "dopplertrack job $JOB on $(md instance-type) in $(md placement/availability-zone)"

fail() {
  echo "bootstrap failed: $*"
  if [ -x /usr/local/bin/s5cmd ]; then
    printf '{"state": "failed", "stage": "bootstrap", "error": "%s"}\n' "$*" | s5cmd pipe "s3://$BUCKET/jobs/$JOB/status.json"
    s5cmd cp /var/log/dopplertrack-boot.log "s3://$BUCKET/jobs/$JOB/boot.log"
  fi
  shutdown -h now
  exit 1
}

# Scratch: the instance-store NVMe drives (c8gd), striped, if there are any; else the root volume.
mkdir -p /scratch
DEVS=$(lsblk -dpno NAME,MODEL | awk '/Instance Storage/ {print $1}')
DEV=""
if [ -n "$DEVS" ]; then
  if [ "$(echo $DEVS | wc -w)" -gt 1 ]; then
    mdadm --create /dev/md0 --level=0 --raid-devices=$(echo $DEVS | wc -w) $DEVS --run && DEV=/dev/md0
  else
    DEV=$DEVS
  fi
  mkfs.xfs -q -f "$DEV" && mount -o noatime "$DEV" /scratch || echo "instance store not mounted; using the root volume"
fi

case $(dpkg --print-architecture) in
  arm64) ARCH=arm64; S5=s5cmd_2.3.0_Linux-arm64.tar.gz; S5SUM=1439f0d00ecedcd2a2f1f2c6749bbb0152b2257bf5086f29646ec8ae38798e24 ;;
  amd64) ARCH=amd64; S5=s5cmd_2.3.0_Linux-64bit.tar.gz; S5SUM=de0fdbfa3aceae55e069ba81a0fc17b2026567637603734a387b2fca06c299b4 ;;
  *) fail "unsupported architecture" ;;
esac
curl -sfL -o "/tmp/$S5" "https://github.com/peak/s5cmd/releases/download/v2.3.0/$S5" || fail "s5cmd download"
echo "$S5SUM  /tmp/$S5" | sha256sum -c --quiet || fail "s5cmd checksum"
tar xzf "/tmp/$S5" -C /usr/local/bin s5cmd || fail "s5cmd unpack"
s5cmd --log error cp "s3://$BUCKET/tools/$ARCH/*" /usr/local/bin/ || fail "tools from the bucket"
chmod +x /usr/local/bin/uv /usr/local/bin/ffmpeg /usr/local/bin/ffprobe
mkdir -p /opt/dopplertrack
s5cmd --log error cp "s3://$BUCKET/jobs/$JOB/supervisor.py" /opt/dopplertrack/supervisor.py || fail "supervisor"

shutdown -c
exec python3 /opt/dopplertrack/supervisor.py --bucket "$BUCKET" --job "$JOB"
