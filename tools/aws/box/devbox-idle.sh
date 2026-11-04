#!/bin/bash
# The dev box's idle stop, run each minute by a systemd timer (devbox.sh installs it): after IDLE_MIN minutes in a
# row with no `runs dev run` checkout, no Systems Manager command or session and a load average under 0.5, the box
# powers off, which stops it (its root volume and data stay). It replaces a CloudWatch alarm, which counted the
# near-zero CPU of a stopping and starting box as idle and stopped the box under a check that had just begun.
set -u
IDLE_MIN=30
STATE=/var/lib/dopplertrack-idle
busy() {
  [ -n "$(ls -A /home/ubuntu/runs 2>/dev/null)" ] && return 0                 # a runs dev run checkout
  pgrep -f 'ssm-document-worker|ssm-session-worker' >/dev/null && return 0    # a command or a shell
  awk '{exit !($1 >= 0.5)}' /proc/loadavg
}
if busy; then echo 0 > "$STATE"; exit 0; fi
n=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STATE"
if [ "$n" -ge "$IDLE_MIN" ]; then
  echo 0 > "$STATE"
  logger -t dopplertrack-idle "idle for $IDLE_MIN min: stopping"
  shutdown -h now
fi
