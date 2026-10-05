#!/bin/bash
set -e

echo "==========================================="
echo "  Phonos Turntable Bridge Container Engine "
echo "==========================================="

# 0. Configure Icecast & DarkIce passwords dynamically from environment variables
python3 - <<'EOF'
import os, re

source_pw = os.environ.get("ICECAST_SOURCE_PASSWORD") or os.environ.get("ICECAST_PASSWORD", "hackme")
relay_pw = os.environ.get("ICECAST_RELAY_PASSWORD", source_pw)
admin_user = os.environ.get("ICECAST_ADMIN_USER", "admin")
admin_pw = os.environ.get("ICECAST_ADMIN_PASSWORD", source_pw)

icecast_cfg = "/etc/icecast2/icecast.xml"
if os.path.exists(icecast_cfg):
    with open(icecast_cfg, "r") as f:
        content = f.read()
    content = re.sub(r"<source-password>.*?</source-password>", f"<source-password>{source_pw}</source-password>", content)
    content = re.sub(r"<relay-password>.*?</relay-password>", f"<relay-password>{relay_pw}</relay-password>", content)
    content = re.sub(r"<admin-user>.*?</admin-user>", f"<admin-user>{admin_user}</admin-user>", content)
    content = re.sub(r"<admin-password>.*?</admin-password>", f"<admin-password>{admin_pw}</admin-password>", content)
    with open(icecast_cfg, "w") as f:
        f.write(content)

darkice_cfg = "/etc/darkice.cfg"
if os.path.exists(darkice_cfg):
    with open(darkice_cfg, "r") as f:
        content = f.read()
    content = re.sub(r"^password\s*=.*$", f"password        = {source_pw}", content, flags=re.MULTILINE)
    with open(darkice_cfg, "w") as f:
        f.write(content)
EOF

# 1. Start Icecast2 streaming daemon
su -s /bin/bash icecast2 -c "/usr/bin/icecast2 -c /etc/icecast2/icecast.xml -b"
echo "[+] Icecast2 running on port 8000"

# 2. Start PulseAudio daemon
pulseaudio --start --exit-idle-time=-1 --system=false
pactl load-module module-switch-on-connect || true
pactl load-module module-bluetooth-discover || true
pactl load-module module-bluetooth-policy || true
echo "[+] PulseAudio initialized"

# 3. Start Bluetooth agent and autoconnect daemon if D-Bus socket is available
if [ -S /var/run/dbus/system_bus_socket ]; then
    bt-agent -c NoInputNoOutput &
    /usr/local/bin/bt-turntable-autoconnect.sh &
    echo "[+] Bluetooth subsystem & autoconnect daemon active"
else
    echo "[!] Warning: /var/run/dbus/system_bus_socket not detected. Running without host Bluetooth."
fi

# 4. Start DarkIce audio streamer
darkice -c /etc/darkice.cfg &
echo "[+] DarkIce streamer active"

# 5. Start Phonos API & Web Dashboard as main foreground process
PORT="${PORT:-8080}"
echo "[+] Phonos Status API & UI running on port ${PORT}"
exec python3 /usr/local/bin/phonos-status-api.py
