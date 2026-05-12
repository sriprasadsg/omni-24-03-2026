#!/bin/bash
set -e

# Enterprise Omni Agent - Linux Installation Script
# Usage: ./linux-install.sh -r <RegistrationKey> -b <BackendUrl> [-t <TenantId>] [--as-service]

BACKEND_URL="http://localhost:5000"
REGISTRATION_KEY=""
TENANT_ID="default-tenant"
AGENT_TOKEN=""
INSTALL_DIR="/opt/enterprise-omni-agent"
AS_SERVICE=false

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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registration-key) REGISTRATION_KEY="$2"; shift 2 ;;
        -b|--backend-url)      BACKEND_URL="$2";      shift 2 ;;
        -t|--tenant-id)        TENANT_ID="$2";        shift 2 ;;
        -k|--agent-token)      AGENT_TOKEN="$2";      shift 2 ;;
        --install-dir)         INSTALL_DIR="$2";      shift 2 ;;
        --as-service)          AS_SERVICE=true;       shift   ;;
        *)
            print_error "Unknown option: $1"
            echo "Usage: $0 -r <RegistrationKey> -b <BackendUrl> [-t <TenantId>] [-k <AgentToken>] [--as-service]"
            exit 1
            ;;
    esac
done

echo "═══════════════════════════════════════════════════════════"
echo "    Enterprise Omni Agent — Linux Installer"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Prerequisites ────────────────────────────────────────────────────
print_info "Step 1/6: Checking prerequisites..."

# Python ≥ 3.11
if ! command -v python3 &>/dev/null; then
    print_error "Python 3 not found. Install python3.11 or later."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_NUM=$(python3 -c 'import sys; print(sys.version_info.major * 1000 + sys.version_info.minor)')
if [ "$PY_NUM" -lt 3011 ]; then
    print_error "Python $PY_VER detected — Python 3.11+ required."
    echo "  Ubuntu/Debian: sudo apt install python3.11 python3.11-venv python3.11-dev"
    exit 1
fi
print_success "Python $PY_VER detected"

# Build tools needed for C-extension packages (cryptography, psutil, yara-python)
if command -v apt-get &>/dev/null; then
    apt-get install -y -qq python3-dev build-essential libssl-dev libffi-dev 2>/dev/null || \
        print_warning "Could not install build tools (non-root?). C-extension packages may fail."
elif command -v dnf &>/dev/null; then
    dnf install -y -q python3-devel gcc openssl-devel libffi-devel 2>/dev/null || \
        print_warning "Could not install build tools (non-root?). C-extension packages may fail."
fi

# curl
if ! command -v curl &>/dev/null; then
    print_error "curl is required but not installed."
    exit 1
fi

# Test backend connectivity
print_info "Testing connectivity to $BACKEND_URL..."
if curl -sf "$BACKEND_URL/api/health" >/dev/null 2>&1; then
    print_success "Backend is reachable"
else
    print_warning "Cannot reach backend at $BACKEND_URL — agent will retry at startup"
fi

# ── Step 2: Resolve Registration Key ────────────────────────────────────────
print_info "Step 2/6: Resolving registration key..."
if [ -n "$REGISTRATION_KEY" ]; then
    RESPONSE=$(curl -sf -X POST "${BACKEND_URL}/api/tenants/lookup-key" \
        -H "Content-Type: application/json" \
        -d "{\"registrationKey\": \"${REGISTRATION_KEY}\"}" 2>/dev/null || echo "")
    if echo "$RESPONSE" | grep -q '"success":true'; then
        TENANT_ID=$(echo "$RESPONSE" | grep -o '"tenantId":"[^"]*"' | cut -d'"' -f4)
        TENANT_NAME=$(echo "$RESPONSE" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
        print_success "Key verified — Tenant: $TENANT_NAME ($TENANT_ID)"
    else
        print_warning "Could not verify registration key — using tenant-id: $TENANT_ID"
    fi
else
    print_warning "No registration key provided — using tenant-id: $TENANT_ID"
fi

# ── Step 3: Create install directory & copy files ────────────────────────────
print_info "Step 3/6: Setting up installation directory..."
mkdir -p "$INSTALL_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SOURCE="$SCRIPT_DIR/agent"

if [ -d "$AGENT_SOURCE" ]; then
    cp -r "$AGENT_SOURCE"/. "$INSTALL_DIR/"
    print_success "Agent files copied to $INSTALL_DIR"
else
    # Try to download agent from backend
    print_info "Downloading agent from $BACKEND_URL..."
    if curl -sf -L -o "$INSTALL_DIR/agent.py" "${BACKEND_URL}/api/agent-updates/download/agent.py"; then
        print_success "Downloaded agent.py"
    else
        print_error "Agent source not found locally and download failed."
        exit 1
    fi
    # Download capabilities
    if curl -sf -L -o "$INSTALL_DIR/capabilities.tar.gz" "${BACKEND_URL}/api/agent-updates/download/capabilities.tar.gz"; then
        tar -xzf "$INSTALL_DIR/capabilities.tar.gz" -C "$INSTALL_DIR"
        rm "$INSTALL_DIR/capabilities.tar.gz"
        print_success "Capabilities extracted"
    else
        print_warning "Capabilities download failed — agent may run in limited mode"
    fi
fi

# ── Step 4: Write config.yaml ────────────────────────────────────────────────
print_info "Step 4/6: Writing configuration..."
cat > "$INSTALL_DIR/config.yaml" <<EOF
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
EOF
print_success "config.yaml written"

# ── Step 5: Create venv and install dependencies ─────────────────────────────
print_info "Step 5/6: Installing Python dependencies..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip setuptools wheel --quiet

if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
    print_success "Dependencies installed from requirements.txt"
else
    # Fallback: install known-required packages
    "$INSTALL_DIR/venv/bin/pip" install --quiet \
        requests PyYAML psutil py-cpuinfo cryptography httpx \
        watchdog "websockets>=12.0" "websocket-client>=1.7.0" \
        "python-socketio[client]>=5.10.0"
    print_success "Core dependencies installed (requirements.txt not found)"
fi

# ── Step 6: Startup ──────────────────────────────────────────────────────────
print_info "Step 6/6: Configuring startup..."
mkdir -p "$INSTALL_DIR/logs"

if [ "$AS_SERVICE" = true ]; then
    cat > /etc/systemd/system/omni-agent.service <<EOF
[Unit]
Description=Enterprise Omni Platform Agent
After=network.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/bin:/bin"
Environment="PYTHONPATH=$INSTALL_DIR"
ExecStart=$INSTALL_DIR/venv/bin/python agent.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/agent.log
StandardError=append:$INSTALL_DIR/logs/agent-error.log

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable omni-agent
    systemctl start omni-agent

    sleep 2
    if systemctl is-active --quiet omni-agent; then
        print_success "Agent service is running"
    else
        print_warning "Service did not start cleanly — check: journalctl -u omni-agent -f"
    fi
else
    cat > "$INSTALL_DIR/start-agent.sh" <<'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
VENV="$(dirname "$0")/venv"
if [ -d "$VENV" ]; then
    "$VENV/bin/python" agent.py
else
    python3 agent.py
fi
STARTEOF
    chmod +x "$INSTALL_DIR/start-agent.sh"
    print_success "Start script created: $INSTALL_DIR/start-agent.sh"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "                Installation Complete!"
echo "═══════════════════════════════════════════════════════════"
print_success "Agent:      $INSTALL_DIR"
print_success "Config:     $INSTALL_DIR/config.yaml"
print_success "Backend:    $BACKEND_URL"
print_success "Tenant:     $TENANT_ID"
echo ""
if [ "$AS_SERVICE" = true ]; then
    echo "  Start:   sudo systemctl start omni-agent"
    echo "  Stop:    sudo systemctl stop omni-agent"
    echo "  Status:  sudo systemctl status omni-agent"
    echo "  Logs:    sudo journalctl -u omni-agent -f"
else
    echo "  Run:     $INSTALL_DIR/start-agent.sh"
fi
