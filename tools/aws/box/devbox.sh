#!/bin/bash
# User data of the persistent dev box (first boot only): the same tools as a job box, a clone of the fork
# with its environment, and the data and cache roots on the root volume, which survives stops.
# `runs dev sync` later brings an engineer's branch over; `runs dev run -- tools/check.sh` runs it there.
set -uo pipefail
exec > >(tee -a /var/log/dopplertrack-boot.log > /dev/console) 2>&1
BUCKET=@@BUCKET@@
IMDS=http://169.254.169.254/latest
TOKEN=$(curl -sfX PUT "$IMDS/api/token" -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600')
export AWS_REGION=$(curl -sf -H "X-aws-ec2-metadata-token: $TOKEN" "$IMDS/meta-data/placement/region")
export HOME=/root DEBIAN_FRONTEND=noninteractive
S5=s5cmd_2.3.0_Linux-arm64.tar.gz
curl -sfL -o "/tmp/$S5" "https://github.com/peak/s5cmd/releases/download/v2.3.0/$S5"
echo "1439f0d00ecedcd2a2f1f2c6749bbb0152b2257bf5086f29646ec8ae38798e24  /tmp/$S5" | sha256sum -c --quiet || exit 1
tar xzf "/tmp/$S5" -C /usr/local/bin s5cmd
# on the first deploy the box boots before `runs seed-tools` has filled tools/, so wait for it
for i in $(seq 1 120); do
  s5cmd --log error cp "s3://$BUCKET/tools/arm64/*" /usr/local/bin/ && break
  sleep 30
done
chmod +x /usr/local/bin/uv /usr/local/bin/ffmpeg /usr/local/bin/ffprobe || exit 1
mkdir -p /srv/dopplertrack/data /srv/dopplertrack/cache && chown -R ubuntu:ubuntu /srv/dopplertrack
cat > /etc/profile.d/dopplertrack.sh <<EOS
export DOPPLERTRACK_DATA=/srv/dopplertrack/data
export DOPPLERTRACK_CACHE=/srv/dopplertrack/cache
export DOPPLERTRACK_BUCKET=$BUCKET
export AWS_REGION=$AWS_REGION
EOS
sudo -iu ubuntu bash -c 'git clone -q https://github.com/SokolskyNikita/dopplertrack.git ~/dopplertrack && cd ~/dopplertrack && git checkout -q dev && uv sync --frozen -q'
echo "dopplertrack dev box ready"
