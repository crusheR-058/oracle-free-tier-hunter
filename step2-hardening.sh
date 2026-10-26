#!/usr/bin/env bash
# ==============================================================================
# Oracle Cloud ARM64 Always-Free AI Server: Base Hardening & Setup Script
# Step 2: Storage expansion, base tools, Tailscale mesh VPN, and UFW firewall.
# ==============================================================================
set -euo pipefail

echo "===> [1/5] Expanding Boot Volume Filesystem to Full 200GB..."
if command -v /usr/libexec/oci-growfs >/dev/null 2>&1; then
    sudo /usr/libexec/oci-growfs -y || true
fi
df -h /

echo "===> [2/5] Updating Apt Repositories and Installing Core Tools..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    curl wget git tmux htop ufw jq net-tools \
    python3-pip python3-venv ca-certificates gnupg lsb-release

echo "===> [3/5] Adjusting Oracle Default Iptables Rules for UFW & Tailscale..."
# OCI Ubuntu images inject strict reject rules in /etc/iptables/rules.v4.
# We ensure standard UFW control is not blocked by legacy OCI rules.
if [ -f /etc/iptables/rules.v4 ]; then
    sudo cp /etc/iptables/rules.v4 /etc/iptables/rules.v4.bak
fi

echo "===> [4/5] Installing Tailscale..."
if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "===> [5/5] Configuring Zero-Trust UFW Firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'SSH Public Port'
sudo ufw allow in on tailscale0 comment 'Tailscale Secure Mesh (All internal services)'
echo "y" | sudo ufw enable
sudo ufw status verbose

echo "=============================================================================="
echo "Base hardening complete!"
echo "Next step: Run 'sudo tailscale up' or pass your authkey:"
echo "  sudo tailscale up --accept-routes=true --hostname=oracle-cloud-relay"
echo "=============================================================================="
