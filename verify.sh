#!/usr/bin/env bash
# ==============================================================================
# Oracle Cloud ARM64 AI Server: Smoke-Test & Verification Suite
# ==============================================================================
set -u

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}====================================================================${NC}"
echo -e "${CYAN}        ORACLE CLOUD ARM64 ALWAYS-FREE AI SERVER VERIFICATION       ${NC}"
echo -e "${CYAN}====================================================================${NC}\n"

# 1. Hardware & System Specs
echo -e "${YELLOW}>>> [1/6] Checking Hardware Allocations (Goal: 4 OCPUs, 24GB RAM, 200GB NVMe)${NC}"
CPU_CORES=$(nproc)
TOTAL_RAM=$(free -h | awk '/^Mem:/ {print $2}')
DISK_SIZE=$(df -h / | awk 'NR==2 {print $2}')
DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')

echo "  - CPU Cores Available: $CPU_CORES"
echo "  - Total RAM:          $TOTAL_RAM"
echo "  - Root Disk Size:     $DISK_SIZE (Free: $DISK_AVAIL)"

if [ "$CPU_CORES" -ge 4 ]; then
    echo -e "  [${GREEN}OK${NC}] CPU core allocation verified."
else
    echo -e "  [${YELLOW}WARN${NC}] Detected $CPU_CORES cores (Expected: 4)."
fi

# 2. Tailscale Status
echo -e "\n${YELLOW}>>> [2/6] Checking Tailscale Mesh Network${NC}"
if command -v tailscale >/dev/null 2>&1; then
    TS_STATUS=$(sudo tailscale status 2>&1 || true)
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "Not assigned")
    echo "  - Tailscale IP: $TS_IP"
    if [ "$TS_IP" != "Not assigned" ] && [ -n "$TS_IP" ]; then
        echo -e "  [${GREEN}OK${NC}] Tailscale interface active."
    else
        echo -e "  [${RED}FAIL${NC}] Tailscale not authenticated. Run 'sudo tailscale up'."
    fi
else
    TS_IP="<TAILSCALE_NOT_INSTALLED>"
    echo -e "  [${RED}FAIL${NC}] Tailscale binary not found."
fi

# 3. Docker Service & Fleet
echo -e "\n${YELLOW}>>> [3/6] Checking Docker Container Fleet${NC}"
REQUIRED_CONTAINERS=("open-webui" "code-server" "chromium-cloud" "uptime-kuma" "portainer")

if command -v docker >/dev/null 2>&1; then
    for c in "${REQUIRED_CONTAINERS[@]}"; do
        STATUS=$(docker inspect --format '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
        if [ "$STATUS" == "running" ]; then
            echo -e "  - Container $c: [${GREEN}RUNNING${NC}]"
        else
            echo -e "  - Container $c: [${RED}$STATUS${NC}]"
        fi
    done
else
    echo -e "  [${RED}FAIL${NC}] Docker not installed."
fi

# 4. Native ARM Ollama
echo -e "\n${YELLOW}>>> [4/6] Checking Native ARM64 Ollama Engine (:11434)${NC}"
if curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo -e "  - Ollama Daemon: [${GREEN}REACHABLE${NC}]"
    MODELS=$(curl -s http://127.0.0.1:11434/api/tags | jq -r '.models[].name' 2>/dev/null || echo "None")
    echo "  - Installed Models:"
    for m in $MODELS; do
        echo "      * $m"
    done
else
    echo -e "  - Ollama Daemon: [${RED}UNREACHABLE${NC}] (Ensure ollama service is running)"
fi

# 5. Cloud Chromium CDP & noVNC
echo -e "\n${YELLOW}>>> [5/6] Checking Chromium CDP (:9222)${NC}"
CDP_VER=$(curl -s --connect-timeout 3 http://127.0.0.1:9222/json/version 2>/dev/null | jq -r '.Browser' 2>/dev/null || echo "")
if [ -n "$CDP_VER" ]; then
    echo -e "  - Chrome DevTools Protocol: [${GREEN}ONLINE${NC}] ($CDP_VER)"
else
    echo -e "  - Chrome DevTools Protocol: [${RED}OFFLINE${NC}]"
fi

# 6. Final Access Table
echo -e "\n${CYAN}====================================================================${NC}"
echo -e "${CYAN}                       ACCESS DASHBOARD                             ${NC}"
echo -e "${CYAN}====================================================================${NC}"
echo -e "Tailscale Private IP: ${GREEN}${TS_IP}${NC}"
echo -e "\nAccess your services securely across your Tailscale mesh:"
echo -e "  1. Open-WebUI (AI Chat):       ${CYAN}http://${TS_IP}:8080${NC}"
echo -e "  2. Cloud VS Code:             ${CYAN}http://${TS_IP}:8443${NC}"
echo -e "  3. Chromium noVNC Desktop:    ${CYAN}http://${TS_IP}:5800${NC}"
echo -e "  4. Chromium CDP (Automation): ${CYAN}http://${TS_IP}:9222${NC}"
echo -e "  5. Uptime Kuma (Monitoring):  ${CYAN}http://${TS_IP}:3001${NC}"
echo -e "  6. Portainer (Docker GUI):    ${CYAN}http://${TS_IP}:9000${NC}"
echo -e "  7. Ollama REST API:           ${CYAN}http://${TS_IP}:11434${NC}"
echo -e "${CYAN}====================================================================${NC}\n"
