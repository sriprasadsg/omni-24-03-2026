#!/bin/bash

#################################################################################
# Enterprise Omni Platform - Ubuntu 24.04 Deployment Script
# 
# This script automates the deployment of the entire platform including:
# - Backend (FastAPI + MongoDB)
# - Frontend (React + Vite)
# - Agent (Python)
# - Nginx Reverse Proxy
#
# Usage: sudo ./deploy-ubuntu.sh
#################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() { echo -e "${CYAN}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error() { echo -e "${RED}✗ ${1}${NC}"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

# Configuration
PROJECT_DIR="$ACTUAL_HOME/enterprise-omni-platform"
SYSTEM_IP=$(hostname -I | awk '{print $1}')
BACKEND_PORT=5000
FRONTEND_PORT=3000
MONGODB_PORT=27017
DOMAIN_NAME="localhost" # Change this for production

echo "═══════════════════════════════════════════════════════════"
echo "    Enterprise Omni Platform - Ubuntu 24.04 Deployment"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Step 1: Update system
print_info "Step 1/11: Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
print_success "System updated"

# Function to extract version numbers for comparison
get_version_number() {
    echo "$1" | awk -F. '{ printf("%d%03d%03d\n", $1,$2,$3); }'
}

# Step 2: Install system dependencies (including Phase 1-10 additions)
print_info "Step 2/11: Installing system dependencies..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    build-essential \
    software-properties-common \
    gnupg \
    ufw \
    nginx \
    supervisor \
    python3-dev \
    libssl-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libpcap-dev \
    nmap \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    poppler-utils \
    wkhtmltopdf
print_success "System dependencies installed"

# Install Semgrep (Phase 5 - SAST scanning)
print_info "Installing Semgrep for SAST scanning..."
pip3 install semgrep --quiet || print_warning "Semgrep install failed (optional, non-critical)"
print_success "Semgrep setup complete"

# Step 3: Install Python 3 (ensure >= 3.10)
print_info "Step 3/11: Checking Python 3 version..."
if command -v python3 &> /dev/null; then
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    print_info "Found Python $PY_VER"
    if [ "$(get_version_number $PY_VER)" -lt "$(get_version_number 3.10)" ]; then
        print_info "Python version is older than 3.10. Upgrading..."
        apt-get install -y -qq python3 python3-venv python3-pip
    else
        print_success "Suitable Python 3 version already installed."
        # Ensure venv and pip are at least present
        apt-get install -y -qq python3-venv python3-pip
    fi
else
    print_info "Installing Python 3..."
    apt-get install -y -qq python3 python3-venv python3-pip
fi

# Step 4: Install Node.js (ensure >= 18.x)
print_info "Step 4/11: Checking Node.js version..."
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
# Step 5: Install MongoDB (ensure >= 6.0)
print_info "Step 5/11: Checking MongoDB version..."
if command -v mongod &> /dev/null; then
    MONGO_VER=$(mongod --version | grep 'db version' | awk '{print $3}' | cut -d 'v' -f 2)
    print_info "Found MongoDB $MONGO_VER"
    if [ "$(get_version_number $MONGO_VER)" -lt "$(get_version_number 6.0.0)" ]; then
        print_info "MongoDB version is older than 6.0. Upgrading to 7.0..."
        curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
        echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
        apt-get update -qq
        apt-get install -y -qq mongodb-org
        systemctl restart mongod
    else
        print_success "Suitable MongoDB version already installed."
    fi
else
    print_info "Installing MongoDB 7.0..."
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
    echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    apt-get update -qq
    apt-get install -y -qq mongodb-org
    
    # Start and enable MongoDB
    systemctl start mongod
    systemctl enable mongod
fi
print_success "MongoDB setup complete"

# Step 6: Clone/Setup project
print_info "Step 6/11: Setting up project directory..."
if [ ! -d "$PROJECT_DIR" ]; then
    # Auto-detect source
    if [ -d "backend" ] && [ -f "package.json" ]; then
        SOURCE_DIR=$(pwd)
        print_info "Detected project source in current directory: $SOURCE_DIR"
    else
        read -p "Source directory path: " SOURCE_DIR
    fi
    
    if [ -d "$SOURCE_DIR" ]; then
        cp -r "$SOURCE_DIR" "$PROJECT_DIR"
        chown -R $ACTUAL_USER:$ACTUAL_USER "$PROJECT_DIR"
    else
        print_error "Source directory not found!"
        exit 1
    fi
else
    print_success "Project directory exists: $PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# Step 7: Setup Backend
print_info "Step 7/11: Setting up backend..."

print_info "Clearing existing MongoDB data..."
mongosh --quiet omni_platform --eval "db.dropDatabase()" || true
print_success "Old database cleared"

cd "$PROJECT_DIR/backend"

# Create/Update required directories
mkdir -p logs backups uploads data_lake_storage
chown -R $ACTUAL_USER:$ACTUAL_USER logs backups uploads data_lake_storage

# Virtual Env
rm -rf venv
sudo -u $ACTUAL_USER python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
if [ -f "requirements.txt" ]; then
    sed -i 's/^chromadb.*/chromadb>=0.5.0/g' requirements.txt
    # Core existing deps
    grep -q "^celery" requirements.txt || echo "celery" >> requirements.txt
    grep -q "^chromadb" requirements.txt || echo "chromadb>=0.5.0" >> requirements.txt
    grep -q "^pydantic-settings" requirements.txt || echo "pydantic-settings" >> requirements.txt
    grep -q "^PyYAML" requirements.txt || echo "PyYAML>=6.0.1" >> requirements.txt
    # Phase 1: Real LLM
    grep -q "^google-generativeai" requirements.txt || echo "google-generativeai" >> requirements.txt
    grep -q "^openai" requirements.txt || echo "openai" >> requirements.txt
    # Phase 3: Stripe Payment
    grep -q "^stripe" requirements.txt || echo "stripe" >> requirements.txt
    # Phase 4: MFA & SSO
    grep -q "^pyotp" requirements.txt || echo "pyotp" >> requirements.txt
    grep -q "^qrcode" requirements.txt || echo "qrcode[pil]" >> requirements.txt
    grep -q "^authlib" requirements.txt || echo "authlib" >> requirements.txt
    grep -q "^httpx" requirements.txt || echo "httpx" >> requirements.txt
    # Phase 5: SAST scanning
    grep -q "^bandit" requirements.txt || echo "bandit" >> requirements.txt
    # Phase 7: PDF Report/Invoice
    grep -q "^reportlab" requirements.txt || echo "reportlab" >> requirements.txt
    # Phase 8: Voice Bot
    grep -q "^gTTS" requirements.txt || echo "gTTS" >> requirements.txt
    grep -q "^google-cloud-speech" requirements.txt || echo "google-cloud-speech" >> requirements.txt
    grep -q "^google-cloud-texttospeech" requirements.txt || echo "google-cloud-texttospeech" >> requirements.txt
    # Phase 9: Real Agent Metrics
    grep -q "^psutil" requirements.txt || echo "psutil" >> requirements.txt
    pip install -r requirements.txt
    print_success "Backend dependencies installed (Phases 1-10)"
fi

# .env Configuration (Phases 1-10)
if [ ! -f ".env" ]; then
    cat > .env <<EOF
# === Core ===
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=omni_platform
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_REFRESH_SECRET_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=http://\$(hostname -I | awk '{print \$1}'):3000,http://\$(hostname -I | awk '{print \$1}'):80,http://\$(hostname -I | awk '{print \$1}'),http://localhost:3000,http://127.0.0.1:3000

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
GOOGLE_REDIRECT_URI=http://localhost:5000/api/sso/google/callback
MFA_ISSUER=OmniAgentPlatform

# === Phase 8: Voice Bot (Google Cloud) ===
GOOGLE_CLOUD_PROJECT=
GOOGLE_APPLICATION_CREDENTIALS=

# === Phase 10: Ticketing (Zoho/Custom) ===
# Configured via UI — no static creds needed here
EOF
    chown $ACTUAL_USER:$ACTUAL_USER .env
    print_success "Backend .env file created (Phases 1-10)"
fi

# Database Setup & Enterprise Unlock
print_info "Setting up database & unlocking features..."

# Clear data
print_info "Clearing existing MongoDB data..."
mongosh --quiet omni_platform --eval "db.dropDatabase()"
print_success "Old database cleared"

# Create working users (Super Admin & Admin)
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
print_info "Seeding governance data..."
python3 seed_governance.py
print_success "Governance data seeded"

# Seed compliance pricing packages
print_info "Seeding Compliance Pricing Packages..."
python3 seed_compliance_pricing.py
print_success "Compliance Pricing Packages seeded"

# Unlock Features
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

# Step 8: Setup Frontend — write .env.local so Vite + Socket.IO uses production IP
print_info "Step 8/11: Setting up frontend..."
cd "$PROJECT_DIR"

# Write .env.local before build — sets Socket.IO server URL for production
cat > .env.local <<EOF
VITE_API_BASE_URL=http://$SYSTEM_IP:5000
EOF
chown $ACTUAL_USER:$ACTUAL_USER .env.local
print_success "Frontend .env.local written with VITE_API_BASE_URL=http://$SYSTEM_IP:5000"

if [ -f "package.json" ]; then
    sudo -u $ACTUAL_USER rm -f .env.local.bak
    sudo -u $ACTUAL_USER npm install
    # Build for production
    sudo -u $ACTUAL_USER npm run build
    print_success "Frontend dependencies installed and built"
fi

# Step 8.5: Setup Agent Configuration
print_info "Step 8.5/11: Setting up default agent configuration..."
cd "$PROJECT_DIR/agent"
if [ ! -f "config.yaml" ]; then
    cat > config.yaml <<EOF
tenant_id: platform-admin
registration_key: reg_platformadmin123
api_base_url: http://localhost:5000
log_level: INFO
capabilities:
  metrics: true
  zero_trust: true
  predictive_health: true
  process_monitoring: true
  log_collection: true
  persistence_detection: true
  ueba: true
EOF
    chown $ACTUAL_USER:$ACTUAL_USER config.yaml
    print_success "Agent config.yaml generated"
fi
cd "$PROJECT_DIR"

# Step 9: Nginx Configuration
print_info "Step 9/11: Configuring Nginx Reverse Proxy..."
cat > /etc/nginx/sites-available/omni-platform <<EOF
server {
    listen 80;
    server_name $DOMAIN_NAME;

    # Frontend (Serve Static Files + SPA Fallback)
    location / {
        proxy_pass http://localhost:$FRONTEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }

    # Backend API — ALL /api/* routes including agent download, ticketing, billing
    location /api {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        client_max_body_size 50M;
    }

    # Static files (install scripts, agent downloads)
    location /static {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # Socket.IO WebSocket support
    location /socket.io {
        proxy_pass http://localhost:$BACKEND_PORT;
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

# Step 10: Create Systemd Services
print_info "Step 10/11: Creating systemd services..."

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

# Frontend Service 
# We serve the dist folder using 'serve' or standard npm preview
cat > /etc/systemd/system/omni-frontend.service <<EOF
[Unit]
Description=Enterprise Omni Platform - Frontend
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port $FRONTEND_PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Agent Service
cat > /etc/systemd/system/omni-agent.service <<EOF
[Unit]
Description=Enterprise Omni Platform - Agent
After=network.target omni-backend.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/agent
Environment="PATH=/usr/bin/python3"
ExecStart=/usr/bin/python3 agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Celery Worker Service
cat > /etc/systemd/system/omni-worker.service <<EOF
[Unit]
Description=Enterprise Omni Platform - Celery Worker
After=network.target mongod.service omni-backend.service
Requires=mongod.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$PROJECT_DIR/backend
Environment="PATH=$PROJECT_DIR/backend/venv/bin"
ExecStart=$PROJECT_DIR/backend/venv/bin/celery -A celery_app worker --loglevel=info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
print_success "Systemd services created"

# Step 11: Configure Firewall
print_info "Step 11/11: Configuring firewall..."
ufw allow 'Nginx Full'
ufw allow OpenSSH
ufw --force enable
print_success "Firewall configured"

# Finalize
print_info "Starting services..."
systemctl enable omni-backend omni-frontend omni-agent omni-worker
systemctl start omni-backend omni-frontend omni-agent omni-worker --no-block

# Step 12: Verification
print_info "Step 12/12: Running Automated Verification..."

# Wait for backend to be ready
print_info "Waiting for services to stabilize (15s)..."
sleep 15

# Run verification scripts from backend directory
cd "$PROJECT_DIR/backend"
source venv/bin/activate

# Run master API verification against the running backend
print_info "Running Master API Verification (Phases 1-10)..."
cd "$PROJECT_DIR"
if python3 master_api_verify.py; then
    print_success "Master API Verification PASSED (all modules OK)"
else
    print_warning "Some API endpoints returned non-200 (check logs above)"
fi

cd "$PROJECT_DIR/backend"
source venv/bin/activate
deactivate
cd "$PROJECT_DIR"

echo ""
print_info "==========================================================="
print_info "              Service Status Summary"
print_info "==========================================================="
for service in mongod nginx omni-backend omni-frontend omni-agent omni-worker; do
    if systemctl is-active --quiet $service; then
        echo -e "  [\e[32mACTIVE\e[0m] $service is running"
    else
        echo -e "  [\e[31mFAILED\e[0m] $service is not running"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "              Deployment Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
print_success "Access the platform at: http://$(hostname -I | awk '{print $1}')"
echo ""
print_warning "Next Steps:"
echo "1. Edit .env: $PROJECT_DIR/backend/.env"
echo "2. Add your GEMINI_API_KEY"
echo "3. Restart backend: sudo systemctl restart omni-backend"
echo ""