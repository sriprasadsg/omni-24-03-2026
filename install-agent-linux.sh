#!/bin/bash

#################################################################################
# Enterprise Omni Platform - Agent Installation Script for Linux
#
# This script installs and configures the agent on Linux systems
#
# Usage: sudo ./install-agent-linux.sh --backend-url URL --token TOKEN --tenant-id ID
#################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info() { echo -e "${CYAN}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error() { echo -e "${RED}✗ ${1}${NC}"; }

# Default values
INSTALL_PATH="/opt/omni-agent"
AS_SERVICE=false
BACKEND_URL=""
AGENT_TOKEN=""
TENANT_ID=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-url)
            BACKEND_URL="$2"
            shift 2
            ;;
        --token)
            AGENT_TOKEN="$2"
            shift 2
            ;;
        --tenant-id)
            TENANT_ID="$2"
            shift 2
            ;;
        --install-path)
            INSTALL_PATH="$2"
            shift 2
            ;;
        --as-service)
            AS_SERVICE=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [ -z "$BACKEND_URL" ] || [ -z "$AGENT_TOKEN" ] || [ -z "$TENANT_ID" ]; then
    print_error "Missing required parameters"
    echo "Usage: sudo $0 --backend-url URL --token TOKEN --tenant-id ID [--install-path PATH] [--as-service]"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════"
echo "    Enterprise Omni Platform - Linux Agent Installer"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Step 1: Check prerequisites
print_info "Step 1/6: Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found!"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_success "Python $PYTHON_VERSION detected"

# Check pip
if ! command -v pip3 &> /dev/null; then
    print_warning "pip3 not found, installing..."
    apt-get install -y python3-pip || yum install -y python3-pip
fi

# Test backend connectivity
print_info "Testing connectivity to $BACKEND_URL..."
if curl -s -f "$BACKEND_URL/health" > /dev/null 2>&1; then
    print_success "Backend is reachable"
else
    print_warning "Could not reach backend"
fi

# Step 2: Create installation directory
print_info "Step 2/6: Creating installation directory..."
mkdir -p "$INSTALL_PATH"
cd "$INSTALL_PATH"
print_success "Created directory: $INSTALL_PATH"

# Step 3: Copy agent files
print_info "Step 3/6: Copying agent files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SOURCE="$SCRIPT_DIR/agent"

if [ -d "$AGENT_SOURCE" ]; then
    cp -r "$AGENT_SOURCE"/* "$INSTALL_PATH/"
    print_success "Agent files copied"
else
    print_error "Agent source directory not found: $AGENT_SOURCE"
    exit 1
fi

# Step 4: Configure agent
print_info "Step 4/6: Configuring agent..."
cat > "$INSTALL_PATH/config.yaml" <<EOF
agent_token: $AGENT_TOKEN
agentic_mode_enabled: true
api_base_url: $BACKEND_URL
tenant_id: $TENANT_ID
EOF
print_success "Configuration written"

# Step 5: Install dependencies
print_info "Step 5/6: Installing Python dependencies..."
if [ -f "$INSTALL_PATH/requirements.txt" ]; then
    pip3 install -q -r "$INSTALL_PATH/requirements.txt"
    print_success "Dependencies installed"
fi

# Step 6: Setup service or script
print_info "Step 6/6: Configuring startup..."

if [ "$AS_SERVICE" = true ]; then
    # Create systemd service
    cat > /etc/systemd/system/omni-agent.service <<EOF
[Unit]
Description=Enterprise Omni Platform Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_PATH
ExecStart=/usr/bin/python3 $INSTALL_PATH/agent.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_PATH/logs/agent.log
StandardError=append:$INSTALL_PATH/logs/agent-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Create logs directory
    mkdir -p "$INSTALL_PATH/logs"
    
    systemctl daemon-reload
    systemctl enable omni-agent
    systemctl start omni-agent
    
    print_success "Agent installed as systemd service"
    
    sleep 2
    if systemctl is-active omni-agent > /dev/null; then
        print_success "Agent service is running"
    else
        print_warning "Agent service status: $(systemctl is-active omni-agent)"
    fi
else
    # Create startup script
    cat > "$INSTALL_PATH/start-agent.sh" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 agent.py
EOF
    chmod +x "$INSTALL_PATH/start-agent.sh"
    print_success "Startup script created: $INSTALL_PATH/start-agent.sh"
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "                Installation Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
print_success "Agent Location: $INSTALL_PATH"
print_success "Configuration: $INSTALL_PATH/config.yaml"
print_success "Backend URL: $BACKEND_URL"
print_success "Tenant ID: $TENANT_ID"
echo ""

if [ "$AS_SERVICE" = true ]; then
    print_info "Agent is running as a systemd service"
    print_info "Control commands:"
    echo "  • Start:   sudo systemctl start omni-agent"
    echo "  • Stop:    sudo systemctl stop omni-agent"
    echo "  • Status:  sudo systemctl status omni-agent"
    echo "  • Logs:    sudo journalctl -u omni-agent -f"
else
    print_info "To start the agent manually:"
    echo "  $INSTALL_PATH/start-agent.sh"
fi

echo ""
print_success "Installation completed successfully!"
