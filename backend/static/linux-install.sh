#!/bin/bash
set -e

# Enterprise Omni Agent - Linux Installation Script
# Usage: ./linux-install.sh -r <RegistrationKey> -b <BackendUrl>

BACKEND_URL="http://localhost:5000"
REGISTRATION_KEY=""
TENANT_ID="default-tenant"
AGENT_TOKEN=""
INSTALL_DIR="/opt/enterprise-omni-agent"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registration-key)
            REGISTRATION_KEY="$2"
            shift 2
            ;;
        -b|--backend-url)
            BACKEND_URL="$2"
            shift 2
            ;;
        -t|--tenant-id)
            TENANT_ID="$2"
            shift 2
            ;;
        -k|--agent-token)
            AGENT_TOKEN="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 -r <RegistrationKey> -b <BackendUrl> [-t <TenantId>] [-k <AgentToken>]"
            exit 1
            ;;
    esac
done

echo "========================================="
echo "Enterprise Omni Agent - Linux Installer"
echo "========================================="

# Resolve Registration Key to Tenant ID
if [ -n "$REGISTRATION_KEY" ]; then
    echo "Resolving Registration Key: $REGISTRATION_KEY"
    RESPONSE=$(curl -s -X POST "${BACKEND_URL}/api/tenants/lookup-key" \
        -H "Content-Type: application/json" \
        -d "{\"registrationKey\": \"${REGISTRATION_KEY}\"}")
    
    if echo "$RESPONSE" | grep -q '"success":true'; then
        TENANT_ID=$(echo "$RESPONSE" | grep -o '"tenantId":"[^"]*"' | cut -d'"' -f4)
        TENANT_NAME=$(echo "$RESPONSE" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
        echo "✅ Key Verified! Tenant: $TENANT_NAME ($TENANT_ID)"
    else
        echo "❌ Invalid Registration Key!"
        exit 1
    fi
else
    echo "⚠️  No Registration Key provided. Using default Tenant ID: $TENANT_ID"
fi

# Create install directory
echo "Creating installation directory: $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"

# Download agent (Python version for cross-platform compatibility)
echo "Downloading agent from $BACKEND_URL..."
DOWNLOAD_URL="${BACKEND_URL}/api/agent-updates/download/agent.py"

if sudo curl -f -L -o "$INSTALL_DIR/agent.py" "$DOWNLOAD_URL"; then
    echo "✅ Downloaded agent to $INSTALL_DIR/agent.py"
else
    echo "❌ Failed to download agent from $DOWNLOAD_URL"
    exit 1
fi

# Download capabilities directory
echo "Downloading capabilities..."
if sudo curl -f -L -o "$INSTALL_DIR/capabilities.tar.gz" "${BACKEND_URL}/api/agent-updates/download/capabilities.tar.gz"; then
    sudo tar -xzf "$INSTALL_DIR/capabilities.tar.gz" -C "$INSTALL_DIR"
    sudo rm "$INSTALL_DIR/capabilities.tar.gz"
    echo "✅ Capabilities extracted"
else
    echo "⚠️  Capabilities download failed. Agent may not work correctly."
fi

# Create config.yaml
echo "Creating configuration file..."
sudo tee "$INSTALL_DIR/config.yaml" > /dev/null <<EOF
api_base_url: "$BACKEND_URL"
tenant_id: "$TENANT_ID"
agent_token: "$AGENT_TOKEN"
interval_seconds: 10
metrics_collection: true
max_cpu_percent: 20

# Agentic AI Configuration
agentic_mode_enabled: true
swarm:
  enabled: true
autonomous_actions:
  enabled: true
EOF
echo "✅ Configuration file created"

# Install Python dependencies
echo "Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    sudo pip3 install pyyaml requests psutil
    echo "✅ Dependencies installed"
else
    echo "⚠️  pip3 not found. Please install dependencies manually:"
    echo "   sudo pip3 install pyyaml requests psutil"
fi

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/omni-agent.service > /dev/null <<EOF
[Unit]
Description=Enterprise Omni Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable omni-agent.service

# Start service
echo "Starting Omni Agent service..."
if sudo systemctl start omni-agent.service; then
    echo "✅ Agent service started successfully!"
else
    echo "⚠️  Failed to start service. Check logs with: sudo journalctl -u omni-agent -f"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ Installation Complete!"
echo "========================================="
echo "Service Status:"
sudo systemctl status omni-agent.service --no-pager
echo ""
echo "Useful commands:"
echo "  View logs:    sudo journalctl -u omni-agent -f"
echo "  Stop agent:   sudo systemctl stop omni-agent"
echo "  Start agent:  sudo systemctl start omni-agent"
echo "  Restart:      sudo systemctl restart omni-agent"
echo "========================================="
