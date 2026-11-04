#!/bin/bash
# Installs devbox-idle.sh as a per-minute systemd timer (run as root on the dev box).
set -euo pipefail
install -m 755 "$1" /usr/local/bin/dopplertrack-idle
cat > /etc/systemd/system/dopplertrack-idle.service <<'EOS'
[Unit]
Description=dopplertrack dev box idle stop
[Service]
Type=oneshot
ExecStart=/usr/local/bin/dopplertrack-idle
EOS
cat > /etc/systemd/system/dopplertrack-idle.timer <<'EOS'
[Unit]
Description=dopplertrack dev box idle stop, each minute
[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOS
echo 0 > /var/lib/dopplertrack-idle
systemctl daemon-reload
systemctl enable --now dopplertrack-idle.timer
