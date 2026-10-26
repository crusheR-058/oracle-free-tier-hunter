#!/usr/bin/env bash
# ==============================================================================
# VIAF Arma Reforger Dedicated Server Setup & Hardening Script
# Target: Ubuntu Server 22.04 / 24.04 LTS (x86_64 Native)
# Workload: 8-Player Enfusion Dedicated Server
# ==============================================================================

set -euo pipefail

SERVER_USER="reforger"
SERVER_HOME="/home/${SERVER_USER}"
SERVER_DIR="${SERVER_HOME}/server"
STEAMCMD_DIR="${SERVER_HOME}/steamcmd"
PROFILE_DIR="${SERVER_HOME}/profile"
CONFIG_FILE="${SERVER_DIR}/ArmaReforgerServer.json"
APP_ID="1874900" # Arma Reforger Dedicated Server

echo "=== [1/7] System Update & Dependency Installation ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    curl \
    tar \
    gzip \
    ca-certificates \
    lib32gcc-s1 \
    lib32stdc++6 \
    ufw \
    jq \
    logrotate

echo "=== [2/7] Creating Dedicated Service Account ==="
if ! id -u "${SERVER_USER}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "${SERVER_USER}"
    echo "Created user ${SERVER_USER}."
else
    echo "User ${SERVER_USER} already exists."
fi

mkdir -p "${SERVER_DIR}" "${STEAMCMD_DIR}" "${PROFILE_DIR}"
chown -R "${SERVER_USER}:${SERVER_USER}" "${SERVER_HOME}"

echo "=== [3/7] Installing SteamCMD & Arma Reforger Server ==="
sudo -u "${SERVER_USER}" bash << 'EOF'
set -euo pipefail
cd /home/reforger/steamcmd
if [ ! -f "steamcmd.sh" ]; then
    curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -
fi

echo "Downloading / Validating Arma Reforger Dedicated Server (App ID 1874900)..."
./steamcmd.sh +force_install_dir /home/reforger/server +login anonymous +app_update 1874900 validate +quit
EOF

echo "=== [4/7] Generating Server Configuration (8 Players) ==="
cat << 'EOF' > "${CONFIG_FILE}"
{
  "bindAddress": "0.0.0.0",
  "bindPort": 2001,
  "publicAddress": "",
  "publicPort": 2001,
  "a2s": {
    "address": "0.0.0.0",
    "port": 17777
  },
  "rcon": {
    "address": "127.0.0.1",
    "port": 19999,
    "password": "",
    "permission": "admin"
  },
  "game": {
    "name": "VIAF Arma Reforger Dedicated Server [8 Players]",
    "password": "",
    "scenarioId": "{ECC61978EDCC2D5A}Missions/23_Campaign.conf",
    "playerLimit": 8,
    "autoJoinable": true,
    "visible": true,
    "supportedPlatforms": [
      "PLATFORM_PC",
      "PLATFORM_XBL",
      "PLATFORM_PSN"
    ],
    "gameProperties": {
      "serverMaxViewDistance": 2500,
      "serverMinGrassDistance": 50,
      "networkViewDistance": 1500,
      "disableThirdPerson": false,
      "fastValidation": true,
      "battlEye": true,
      "VONDisableUI": false,
      "VONDisableDirectSpeechUI": false
    }
  },
  "operating": {
    "lobbyPlayerLimit": 8,
    "playerSaveTime": 120,
    "aiLimit": -1,
    "slotReservationTimeout": 60
  }
}
EOF
chown "${SERVER_USER}:${SERVER_USER}" "${CONFIG_FILE}"
chmod 640 "${CONFIG_FILE}"

echo "=== [5/7] Configuring Host Firewall (UFW) ==="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH Administration'
ufw allow 2001/udp comment 'Arma Reforger Game Port'
ufw allow 17777/udp comment 'Arma Reforger Steam A2S Query'
ufw allow 19999/udp comment 'Arma Reforger RCON'
ufw --force enable

echo "=== [6/7] Installing Systemd Service ==="
cat << 'EOF' > /etc/systemd/system/reforger-server.service
[Unit]
Description=Arma Reforger Dedicated Server (8 Players)
After=network.target

[Service]
Type=simple
User=reforger
Group=reforger
WorkingDirectory=/home/reforger/server
ExecStart=/home/reforger/server/ArmaReforgerServer -config /home/reforger/server/ArmaReforgerServer.json -profile /home/reforger/profile -maxFPS 60
Restart=on-failure
RestartSec=10
LimitNOFILE=65536
Nice=-5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable reforger-server.service

echo "=== [7/7] Installing Maintenance Scripts ==="
# Backup script
cat << 'EOF' > "${SERVER_HOME}/backup.sh"
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="/home/reforger/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "${BACKUP_DIR}"
tar -czf "${BACKUP_DIR}/reforger_profile_${TIMESTAMP}.tar.gz" -C /home/reforger profile
# Retain last 7 backups
ls -dt "${BACKUP_DIR}"/* | tail -n +8 | xargs -r rm -f
echo "Backup completed: reforger_profile_${TIMESTAMP}.tar.gz"
EOF
chmod +x "${SERVER_HOME}/backup.sh"
chown "${SERVER_USER}:${SERVER_USER}" "${SERVER_HOME}/backup.sh"

# Update script
cat << 'EOF' > "${SERVER_HOME}/update.sh"
#!/usr/bin/env bash
set -euo pipefail
echo "Stopping reforger server..."
sudo systemctl stop reforger-server
/home/reforger/backup.sh
echo "Updating game server via SteamCMD..."
/home/reforger/steamcmd/steamcmd.sh +force_install_dir /home/reforger/server +login anonymous +app_update 1874900 validate +quit
echo "Starting reforger server..."
sudo systemctl start reforger-server
echo "Update complete."
EOF
chmod +x "${SERVER_HOME}/update.sh"
chown "${SERVER_USER}:${SERVER_USER}" "${SERVER_HOME}/update.sh"

echo "=============================================================================="
echo " Arma Reforger Dedicated Server Setup Complete!"
echo " Start server with: sudo systemctl start reforger-server"
echo " View logs with:    sudo journalctl -u reforger-server -f"
echo "=============================================================================="
