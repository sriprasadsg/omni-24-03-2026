#!/bin/bash
set -e

#################################################################################
# Enterprise Omni Platform - Agent Installation Script for Linux
#
# Usage: sudo ./install-agent-linux.sh --backend-url URL --token TOKEN --tenant-id ID
#        [--install-path PATH] [--as-service]
#################################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info()    { echo -e "${CYAN}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error()   { echo -e "${RED}✗ ${1}${NC}"; }

# Defaults
INSTALL_PATH="/opt/omni-agent"
AS_SERVICE=false
BACKEND_URL=""
AGENT_TOKEN=""
TENANT_ID=""
REGISTRATION_KEY=""
VIRUSTOTAL_API_KEY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-url)      BACKEND_URL="$2";        shift 2 ;;
        --token)            AGENT_TOKEN="$2";        shift 2 ;;
        --tenant-id)        TENANT_ID="$2";          shift 2 ;;
        --registration-key) REGISTRATION_KEY="$2";   shift 2 ;;
        --install-path)     INSTALL_PATH="$2";       shift 2 ;;
        --virustotal-key)   VIRUSTOTAL_API_KEY="$2"; shift 2 ;;
        --as-service)       AS_SERVICE=true;         shift   ;;
        *)
            print_error "Unknown option: $1"
            echo "Usage: sudo $0 --backend-url URL [--token TOKEN] [--tenant-id ID]"
            echo "                       [--registration-key KEY] [--virustotal-key KEY]"
            echo "                       [--install-path PATH] [--as-service]"
            exit 1
            ;;
    esac
done

# Validate
if [ -z "$BACKEND_URL" ]; then
    print_error "Missing required --backend-url"
    echo "Usage: sudo $0 --backend-url URL [--token TOKEN | --registration-key KEY] --tenant-id ID"
    exit 1
fi

# Must be root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════"
echo "    Enterprise Omni Platform — Linux Agent Installer"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Step 1: System prerequisites ────────────────────────────────────────────
print_info "Step 1/6: Installing system prerequisites..."

# Detect package manager
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq \
        python3 python3-venv python3-dev python3-pip \
        build-essential libssl-dev libffi-dev \
        curl wget
    print_success "System packages installed (apt)"
elif command -v dnf &>/dev/null; then
    dnf install -y -q \
        python3 python3-venv python3-devel python3-pip \
        gcc gcc-c++ openssl-devel libffi-devel \
        curl wget
    print_success "System packages installed (dnf)"
elif command -v yum &>/dev/null; then
    yum install -y -q \
        python3 python3-venv python3-devel python3-pip \
        gcc gcc-c++ openssl-devel libffi-devel \
        curl wget
    print_success "System packages installed (yum)"
else
    print_warning "Unknown package manager — skipping system package install"
fi

# Check Python version ≥ 3.11
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_NUM=$(python3 -c 'import sys; print(sys.version_info.major * 1000 + sys.version_info.minor)')
if [ "$PY_NUM" -lt 3011 ]; then
    print_error "Python $PY_VER detected — Python 3.11+ required."
    echo "  Ubuntu 22+:  sudo apt install python3.11 python3.11-venv python3.11-dev"
    echo "  Ubuntu 20:   sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.11"
    exit 1
fi
print_success "Python $PY_VER — OK"

# Test backend connectivity
print_info "Testing connectivity to $BACKEND_URL..."
if curl -sf "$BACKEND_URL/api/health" >/dev/null 2>&1; then
    print_success "Backend is reachable"
else
    print_warning "Cannot reach $BACKEND_URL — agent will retry connections at runtime"
fi

# ── Step 2: Resolve registration key ────────────────────────────────────────
print_info "Step 2/6: Resolving tenant..."
if [ -n "$REGISTRATION_KEY" ] && [ -z "$TENANT_ID" ]; then
    RESPONSE=$(curl -sf -X POST "${BACKEND_URL}/api/tenants/lookup-key" \
        -H "Content-Type: application/json" \
        -d "{\"registrationKey\": \"${REGISTRATION_KEY}\"}" 2>/dev/null || echo "")
    if echo "$RESPONSE" | grep -q '"success":true'; then
        TENANT_ID=$(echo "$RESPONSE" | grep -o '"tenantId":"[^"]*"' | cut -d'"' -f4)
        TENANT_NAME=$(echo "$RESPONSE" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
        print_success "Registration key verified — Tenant: $TENANT_NAME ($TENANT_ID)"
    else
        print_warning "Could not verify registration key"
    fi
fi

if [ -z "$TENANT_ID" ]; then
    TENANT_ID="platform-admin"
    print_warning "No tenant-id resolved — defaulting to: $TENANT_ID"
fi

# ── Step 3: Copy agent files ─────────────────────────────────────────────────
print_info "Step 3/6: Installing agent files..."
mkdir -p "$INSTALL_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SOURCE="$SCRIPT_DIR/agent"

if [ -d "$AGENT_SOURCE" ]; then
    cp -r "$AGENT_SOURCE"/. "$INSTALL_PATH/"
    print_success "Agent files copied from $AGENT_SOURCE"
else
    print_error "Agent source directory not found: $AGENT_SOURCE"
    exit 1
fi

# ── Step 4: Write config.yaml ─────────────────────────────────────────────────
print_info "Step 4/6: Writing configuration..."
cat > "$INSTALL_PATH/config.yaml" <<EOF
api_base_url: "$BACKEND_URL"
tenant_id: "$TENANT_ID"
registration_key: "${REGISTRATION_KEY}"
agent_token: "${AGENT_TOKEN}"
interval_seconds: 5
agentic_mode_enabled: true
swarm:
  enabled: true
autonomous_actions:
  enabled: true
enabled_capabilities:
  - metrics_collection
  - log_collection
  - fim
  - real_time_fim
  - vulnerability_scanning
  - compliance_enforcement
  - compliance_evidence_collector
  - runtime_security
  - predictive_health
  - ueba
  - sbom_analysis
  - ebpf_tracing
  - system_patching
  - software_management
  - remote_access
  - network_discovery
  - agent_update
  - patch_installer
  - process_injection_simulation
  - persistence_detection
  - remediation_executor
  - shadow_ai
  - pii_scanner
  - cloud_metadata
  - web_monitor
  - vss_manager
  - autonomous_response
  - edr_realtime
  - process_monitor
  - log_shipper
  - vendor_risk
  - backup_verifier
  - deception_monitor
  - threat_intel
EOF
print_success "config.yaml written"

# ── Step 5: Create venv and install dependencies ─────────────────────────────
print_info "Step 5/6: Installing Python dependencies..."
python3 -m venv "$INSTALL_PATH/venv"
"$INSTALL_PATH/venv/bin/pip" install --upgrade pip setuptools wheel --quiet

if [ -f "$INSTALL_PATH/requirements.txt" ]; then
    "$INSTALL_PATH/venv/bin/pip" install -r "$INSTALL_PATH/requirements.txt" --quiet
    print_success "Dependencies installed from requirements.txt"
else
    "$INSTALL_PATH/venv/bin/pip" install --quiet \
        requests PyYAML "psutil>=7.0.0" py-cpuinfo "cryptography>=41.0.0" httpx \
        "watchdog>=4.0.0" "websockets>=12.0" "websocket-client>=1.7.0" \
        "python-socketio[client]>=5.10.0"
    print_success "Core dependencies installed (fallback)"
fi

# ── Step 6: Startup ──────────────────────────────────────────────────────────
print_info "Step 6/6: Configuring startup..."
mkdir -p "$INSTALL_PATH/logs"

if [ "$AS_SERVICE" = true ]; then
    cat > /etc/systemd/system/omni-agent.service <<EOF
[Unit]
Description=Enterprise Omni Platform Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_PATH
Environment="PATH=$INSTALL_PATH/venv/bin:/usr/bin:/bin"
Environment="PYTHONPATH=$INSTALL_PATH"
Environment="VIRUSTOTAL_API_KEY=${VIRUSTOTAL_API_KEY:-}"
ExecStart=$INSTALL_PATH/venv/bin/python agent.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_PATH/logs/agent.log
StandardError=append:$INSTALL_PATH/logs/agent-error.log

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable omni-agent
    systemctl start omni-agent

    sleep 2
    if systemctl is-active --quiet omni-agent; then
        print_success "Agent service started"
    else
        print_warning "Check status: sudo journalctl -u omni-agent -f"
    fi
else
    cat > "$INSTALL_PATH/start-agent.sh" <<'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
VENV="$(dirname "$0")/venv"
if [ -d "$VENV" ]; then
    "$VENV/bin/python" agent.py
else
    python3 agent.py
fi
STARTEOF
    chmod +x "$INSTALL_PATH/start-agent.sh"
    print_success "Start script: $INSTALL_PATH/start-agent.sh"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "                Installation Complete!"
echo "═══════════════════════════════════════════════════════════"
print_success "Agent:     $INSTALL_PATH"
print_success "Config:    $INSTALL_PATH/config.yaml"
print_success "Backend:   $BACKEND_URL"
print_success "Tenant:    $TENANT_ID"
echo ""
if [ "$AS_SERVICE" = true ]; then
    echo "  Start:   sudo systemctl start omni-agent"
    echo "  Stop:    sudo systemctl stop omni-agent"
    echo "  Status:  sudo systemctl status omni-agent"
    echo "  Logs:    sudo journalctl -u omni-agent -f"
else
    echo "  Run:     $INSTALL_PATH/start-agent.sh"
fi
