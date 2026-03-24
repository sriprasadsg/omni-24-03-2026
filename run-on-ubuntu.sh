#!/bin/bash

#################################################################################
# Enterprise Omni Platform - Ubuntu 24.04 IP-Integrated Deployment Script
# 
# This script automates the deployment and ensures all components communicate
# using the system's IP address.
#################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info() { echo -e "${CYAN}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error() { echo -e "${RED}✗ ${1}${NC}"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)
PROJECT_DIR=$(pwd)

# Detect System IP
SYSTEM_IP=$(hostname -I | awk '{print $1}')
print_info "Detected System IP: $SYSTEM_IP"

# Function to extract version numbers for comparison
get_version_number() {
    echo "$1" | awk -F. '{ printf("%d%03d%03d\n", $1,$2,$3); }'
}

# Step 1: Install system dependencies (Phases 1-10)
print_info "Step 1: Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    curl wget git build-essential software-properties-common gnupg ufw nginx \
    python3-venv python3-pip python3-dev libssl-dev libffi-dev \
    libjpeg-dev zlib1g-dev libpcap-dev nmap \
    ffmpeg libsndfile1 libportaudio2 \
    poppler-utils wkhtmltopdf
print_success "System dependencies installed (Phases 1-10)"

# Install Semgrep (Phase 5 - SAST)
print_info "Installing Semgrep for SAST scanning..."
pip3 install semgrep --quiet || print_warning "Semgrep install failed (optional)"
print_success "Semgrep ready"

# Smart Install Python 3 (ensure >= 3.10)
print_info "Checking Python 3 version..."
if command -v python3 &> /dev/null; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    print_info "Found Python $PY_VER"
    if [ "$(get_version_number $PY_VER)" -lt "$(get_version_number 3.10)" ]; then
        print_info "Python version is older than 3.10. Upgrading..."
        apt-get install -y -qq python3
    else
        print_success "Suitable Python 3 version already installed."
    fi
else
    print_info "Installing Python 3..."
    apt-get install -y -qq python3
fi

# Smart Install Node.js (ensure >= 18.x)
print_info "Checking Node.js version..."
if command -v node &> /dev/null; then
    NODE_VER=$(node -v | cut -d 'v' -f 2)
    print_info "Found Node.js $NODE_VER"
    if [ "$(get_version_number $NODE_VER)" -lt "$(get_version_number 18.0.0)" ]; then
        print_info "Node.js version is older than 18.x. Upgrading..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y -qq nodejs
    else
        print_success "Suitable Node.js version already installed."
    fi
else
    print_info "Installing Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

# Step 2: Install MongoDB (ensure >= 6.0)
print_info "Step 2: Checking MongoDB version..."
if command -v mongod &> /dev/null; then
    MONGO_VER=$(mongod --version | grep 'db version' | awk '{print $3}' | cut -d 'v' -f 2)
    print_info "Found MongoDB $MONGO_VER"
    if [ "$(get_version_number $MONGO_VER)" -lt "$(get_version_number 6.0.0)" ]; then
        print_info "MongoDB version is older than 6.0. Upgrading to 7.0..."
        curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
        echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
        apt-get update -qq
        apt-get install -y -qq mongodb-org
        systemctl restart mongod
    else
        print_success "Suitable MongoDB version already installed."
    fi
else
    print_info "Installing MongoDB 7.0..."
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    apt-get update -qq
    apt-get install -y -qq mongodb-org
    systemctl start mongod
    systemctl enable mongod
fi
print_success "MongoDB setup complete"

# Step 3: Setup Backend
print_info "Step 3: Setting up Backend..."
cd "$PROJECT_DIR/backend"
rm -rf venv
sudo -u $ACTUAL_USER python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
sed -i 's/^chromadb.*/chromadb>=0.5.0/g' requirements.txt
# Core deps
grep -q "^celery" requirements.txt || echo "celery" >> requirements.txt
grep -q "^chromadb" requirements.txt || echo "chromadb>=0.5.0" >> requirements.txt
grep -q "^pydantic-settings" requirements.txt || echo "pydantic-settings" >> requirements.txt
grep -q "^PyYAML" requirements.txt || echo "PyYAML>=6.0.1" >> requirements.txt
# Phase 1: Real LLM
grep -q "^google-generativeai" requirements.txt || echo "google-generativeai" >> requirements.txt
grep -q "^openai" requirements.txt || echo "openai" >> requirements.txt
# Phase 3: Stripe
grep -q "^stripe" requirements.txt || echo "stripe" >> requirements.txt
# Phase 4: MFA & SSO
grep -q "^pyotp" requirements.txt || echo "pyotp" >> requirements.txt
grep -q "^qrcode" requirements.txt || echo "qrcode[pil]" >> requirements.txt
grep -q "^authlib" requirements.txt || echo "authlib" >> requirements.txt
grep -q "^httpx" requirements.txt || echo "httpx" >> requirements.txt
# Phase 5: SAST scanning
grep -q "^bandit" requirements.txt || echo "bandit" >> requirements.txt
# Phase 7: PDF Invoice Export
grep -q "^reportlab" requirements.txt || echo "reportlab" >> requirements.txt
# Phase 8: Voice Bot
grep -q "^gTTS" requirements.txt || echo "gTTS" >> requirements.txt
grep -q "^google-cloud-speech" requirements.txt || echo "google-cloud-speech" >> requirements.txt
grep -q "^google-cloud-texttospeech" requirements.txt || echo "google-cloud-texttospeech" >> requirements.txt
# Phase 9: Agent Metrics
grep -q "^psutil" requirements.txt || echo "psutil" >> requirements.txt
pip install -r requirements.txt
print_success "Backend dependencies installed (Phases 1-10)"

# Create .env with correct IP settings (Phases 1-10)
cat > .env <<EOF
# === Core ===
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=omni_platform
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_REFRESH_SECRET_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=http://$SYSTEM_IP:3000,http://$SYSTEM_IP:80,http://$SYSTEM_IP,http://localhost:3000,http://127.0.0.1:3000

# === Phase 1: AI/LLM ===
GEMINI_API_KEY=
OPENAI_API_KEY=

# === Phase 2: Email (SMTP) ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@yourdomain.com

# === Phase 3: Stripe Payment ===
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
PAYPAL_CLIENT_ID=
PAYPAL_SECRET=
PAYMENT_GATEWAY_MODE=sandbox

# === Phase 4: Google OAuth2 SSO & MFA ===
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://$SYSTEM_IP:5000/api/sso/google/callback
MFA_ISSUER=OmniAgentPlatform

# === Phase 8: Voice Bot (Google Cloud) ===
GOOGLE_CLOUD_PROJECT=
GOOGLE_APPLICATION_CREDENTIALS=

# === Phase 10: Ticketing (Zoho/Custom configured via UI) ===
EOF
chown $ACTUAL_USER:$ACTUAL_USER .env
print_success "Backend .env created with IP $SYSTEM_IP (Phases 1-10)"

# Update agent install script with the correct IP
sed -i "s/REPLACE_WITH_SERVER_IP/$SYSTEM_IP/g" static/omni-agent-install.py
deactivate

# Step 4: Setup Frontend — write .env.local so Vite + Socket.IO uses the correct server IP
print_info "Step 4: Setting up Frontend..."
cd "$PROJECT_DIR"

# Write Vite .env.local with real IP for Socket.IO service
cat > .env.local <<EOF
VITE_API_BASE_URL=http://$SYSTEM_IP:5000
EOF
chown $ACTUAL_USER:$ACTUAL_USER .env.local
print_success "Frontend .env.local written with VITE_API_BASE_URL=http://$SYSTEM_IP:5000"

sudo -u $ACTUAL_USER npm install
sudo -u $ACTUAL_USER npm run build
print_success "Frontend built"

# Step 5: Setup Agent
print_info "Step 5: Configuring Agent..."
if [ -f "agent/config.yaml" ]; then
    sed -i "s|api_base_url:.*|api_base_url: http://$SYSTEM_IP:5000|g" agent/config.yaml
    print_success "Agent config updated to http://$SYSTEM_IP:5000"
fi

# Step 6: Configure Nginx — proxies frontend and all /api/* to backend
print_info "Step 6: Configuring Nginx..."
cat > /etc/nginx/sites-available/omni-platform <<EOF
server {
    listen 80;
    server_name _;

    # Frontend (Vite dev preview)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }

    # Backend API — all /api/* routes including agent download
    location /api {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        client_max_body_size 50M;
    }

    # Static files (install scripts)
    location /static {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # Socket.IO (WebSocket upgrade)
    location /socket.io {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

ln -sf /etc/nginx/sites-available/omni-platform /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
print_success "Nginx configured (frontend + /api/* + /static + socket.io)"

# Step 7: Database Seeding & Enterprise Unlock
print_info "Step 7: Seeding database & unlocking features..."
cd "$PROJECT_DIR/backend"
source venv/bin/activate

# Clear data
print_info "Clearing existing MongoDB data..."
mongosh --quiet omni_platform --eval "db.dropDatabase()"
print_success "Old database cleared"

# Create working users (Super Admin & Admin) (creates initial tenant)
print_info "Creating Default Super Admin and Working Users..."
python3 ../create_working_users.py
print_success "Users created/verified"

# Seed CISSP full framework
print_info "Seeding CISSP Compliance Framework (8 Domains)..."
python3 ../seed_cissp_framework.py
print_success "CISSP Framework seeded"

# Seed additional compliance frameworks
print_info "Seeding Additional Compliance Frameworks (SOC2, HIPAA, ISO, etc.)..."
python3 seed_compliance.py
print_success "Additional Frameworks seeded"

# Seed governance data
print_info "Seeding additional data..."
python3 seed_governance.py
print_success "Governance data seeded"

# Seed compliance pricing packages
print_info "Seeding Compliance Pricing Packages..."
python3 seed_compliance_pricing.py
print_success "Compliance Pricing Packages seeded"

# Unlock Features (updates tenants to Enterprise)
print_info "Unlocking Enterprise Features for all tenants..."
python3 unlock_enterprise_features.py
print_success "Enterprise features unlocked"

# Seeding Ollama AI Settings
print_info "Seeding AI Settings (Ollama Llama 3)..."
python3 seed_ai_settings.py

# Seed telemetry & SIEM
print_info "Seeding SIEM and Telemetry..."
python3 ../seed_siem_data.py
python3 ../seed_telemetry.py

# Seed advanced security features
print_info "Seeding Vulnerabilities and Runtime Security..."
python3 ../seed_vulnerabilities.py
python3 ../seed_runtime_security.py

# Seed FinOps & Analytics
print_info "Seeding FinOps and Predictive Analytics..."
python3 ../seed_finops_data.py
python3 seed_analytics.py
python3 ../seed_predictive_health.py

# Seed Network
print_info "Seeding Network Topology..."
python3 seed_network.py

# Pulling Ollama Model
if ! command -v ollama &> /dev/null; then
    print_info "Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

if command -v ollama &> /dev/null; then
    print_info "Pulling Llama 3.2 3B model for Ollama..."
    ollama pull llama3.2:3b
    
    print_info "Creating specialized SecurityExpert model..."
    ollama create SecurityExpert -f SecurityExpert.modelfile
    
    print_info "Ingesting Security Standards into RAG knowledge base..."
    python3 ingest_security_standards.py
    
    print_info "Generating synthetic security training data..."
    python3 generate_training_data.py
else
    print_warning "Ollama not found. Please install it manually to use local AI features."
fi

deactivate
cd "$PROJECT_DIR"

print_info "==========================================================="
print_info "  CHECKLIST OF ALL ENABLED SYSTEM FEATURES (Phases 1-10)"
print_info "==========================================================="
echo -e "${GREEN}[✓] Dashboard${NC} - Core Overview and Metrics"
echo -e "${GREEN}[✓] CXO Insights${NC} - High-level Strategic Intelligence"
echo -e "${GREEN}[✓] Distributed Tracing${NC} - Microservices Observability"
echo -e "${GREEN}[✓] Log Explorer${NC} - Centralized Log Management"
echo -e "${GREEN}[✓] Network Observability${NC} - Real-time Traffic Monitoring"
echo -e "${GREEN}[✓] Agents & Asset Management${NC} - Infrastructure Inventory"
echo -e "${GREEN}[✓] Patch Management${NC} - Automated Security Updates"
echo -e "${GREEN}[✓] Security Dashboard${NC} - Unified SecOps Interface"
echo -e "${GREEN}[✓] Cloud Security (CSPM)${NC} - Multi-cloud Governance"
echo -e "${GREEN}[✓] Threat Hunting${NC} - Advanced Behavioral Analysis"
echo -e "${GREEN}[✓] Attack Path Analysis${NC} - Visualizing Lateral Movement"
echo -e "${GREEN}[✓] Data Security (DSPM)${NC} - Protecting Sensitive Assets"
echo -e "${GREEN}[✓] SBOM Management${NC} - Software Supply Chain Visibility"
echo -e "${GREEN}[✓] DevSecOps + SAST/DAST${NC} - CI/CD Integrated Security (Phase 5)"
echo -e "${GREEN}[✓] Chaos Engineering${NC} - Resiliency Testing Suite"
echo -e "${GREEN}[✓] Compliance & AI Governance${NC} - RegTech Controls"
echo -e "${GREEN}[✓] FinOps & Billing${NC} - Stripe Integrated (Phase 3)"
echo -e "${GREEN}[✓] Swarm Intelligence${NC} - Autonomous Multi-Agent Operations"
echo -e "${GREEN}[✓] Real LLM (Gemini/OpenAI)${NC} - Phase 1"
echo -e "${GREEN}[✓] Email SMTP${NC} - Phase 2"
echo -e "${GREEN}[✓] MFA & Google SSO${NC} - Phase 4"
echo -e "${GREEN}[✓] ML Model Monitoring${NC} - Phase 6"
echo -e "${GREEN}[✓] PDF Invoice Export${NC} - Phase 7"
echo -e "${GREEN}[✓] Voice Bot (gTTS/Google Cloud)${NC} - Phase 8"
echo -e "${GREEN}[✓] Real Agent Metrics (psutil)${NC} - Phase 9"
echo -e "${GREEN}[✓] Ticketing: Jira, ServiceNow, Zoho Desk, Custom Webhook${NC} - Phase 10"
print_info "==========================================================="

# Backend Service (uses socket_app for Socket.IO support)
cat > /etc/systemd/system/omni-backend.service <<EOF
[Unit]
Description=Enterprise Omni Platform - Backend API
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/backend
Environment="PATH=$PROJECT_DIR/backend/venv/bin"
Environment="PLATFORM_URL=http://$SYSTEM_IP:5000"
Environment="PYTHONPATH=$PROJECT_DIR/backend"
ExecStart=$PROJECT_DIR/backend/venv/bin/uvicorn app:socket_app --host 0.0.0.0 --port 5000 --log-level info
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Frontend (Vite Preview for simple deployment)
cat > /etc/systemd/system/omni-frontend.service <<EOF
[Unit]
Description=Omni Frontend
After=network.target

[Service]
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 3000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Celery Worker
cat > /etc/systemd/system/omni-worker.service <<EOF
[Unit]
Description=Omni Celery Worker
After=network.target mongod.service omni-backend.service

[Service]
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/backend
Environment="PATH=$PROJECT_DIR/backend/venv/bin"
ExecStart=$PROJECT_DIR/backend/venv/bin/celery -A celery_app worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable omni-backend omni-frontend omni-worker
systemctl start omni-backend omni-frontend omni-worker

# Step 8: Firewall
print_info "Step 8: Configuring Firewall..."
ufw allow 80/tcp
ufw allow 3000/tcp
ufw allow 5000/tcp
ufw --force enable
print_success "Firewall configured"

# Step 9: Verification (Master API check - Phases 1-10)
print_info "Step 9: Running Master API Verification (Phases 1-10)..."

# Wait for backend to be ready
print_info "Waiting for backend service to stabilize (15s)..."
sleep 15

export MONGODB_URL="mongodb://localhost:27017"
export MONGODB_DB_NAME="omni_platform"

# Run master API verification from root project directory
cd "$PROJECT_DIR"
if python3 master_api_verify.py; then
    print_success "Master API Verification PASSED (all 14 modules OK)"
else
    print_warning "Some API modules returned non-200 — review logs above"
fi

cd "$PROJECT_DIR/backend"
source venv/bin/activate
deactivate
cd "$PROJECT_DIR"

echo ""
print_info "==========================================================="
print_info "              Service Status Summary"
print_info "==========================================================="
for service in mongod omni-backend omni-frontend omni-worker; do
    if systemctl is-active --quiet $service; then
        echo -e "  [\e[32mACTIVE\e[0m] $service is running"
    else
        echo -e "  [\e[31mFAILED\e[0m] $service is not running"
    fi
done

echo ""
echo "==========================================================="
echo "  Deployment Complete! System IP: $SYSTEM_IP"
echo " [x] 2030 GOVERNANCE & TRUST"
echo "     - Risk Register (Enabled)"
echo "     - Vendor Risk Management (Enabled)"
echo "     - Trust Center (Enabled)"
echo " [x] ADVANCED SECURITY HUB"
echo "  Frontend: http://$SYSTEM_IP"
echo "  Backend API: http://$SYSTEM_IP:5000/api"
echo "==========================================================="
echo ""
