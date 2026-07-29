#!/bin/bash

# Enterprise Omni-Agent Platform — Linux Launcher
# Starts backend, frontend, and agent in the foreground with proper wait logic.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_info()    { echo -e "${CYAN}ℹ ${1}${NC}"; }
print_success() { echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error()   { echo -e "${RED}✗ ${1}${NC}"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Primary LAN IP of this machine — services bind 0.0.0.0, so this is the
# address other machines use to reach them. Override with SERVER_IP=... .
SERVER_IP="${SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
SERVER_IP="${SERVER_IP:-127.0.0.1}"

# ── TLS: ensure a self-signed cert exists so Vite serves the app over HTTPS ────
# Vite (vite.config.ts) auto-enables HTTPS on port 443 when certs/server.{key,crt}
# are present. The cert carries SubjectAltName IP:${SERVER_IP} so browsers on the
# LAN accept it (after a one-time self-signed warning).
CERT_DIR="$PROJECT_ROOT/certs"
if [ ! -f "$CERT_DIR/server.crt" ] || [ ! -f "$CERT_DIR/server.key" ]; then
    print_info "Generating self-signed TLS certificate for ${SERVER_IP}..."
    mkdir -p "$CERT_DIR"
    if openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.crt" -days 825 \
        -subj "/C=US/ST=Local/L=Local/O=OmniAgent/CN=${SERVER_IP}" \
        -addext "subjectAltName=IP:${SERVER_IP},IP:127.0.0.1,DNS:localhost" >/dev/null 2>&1; then
        print_success "TLS cert created at certs/"
    else
        print_warning "openssl unavailable — Vite will fall back to HTTP on :3000"
    fi
fi

# Stop all child processes cleanly on Ctrl+C
cleanup() {
    echo ""
    print_info "Stopping all services..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "============================================="
echo "Enterprise Omni-Agent Platform — Launcher"
echo "============================================="
echo ""

# ── Python resolver ──────────────────────────────────────────────────────────
resolve_python() {
    local venv_dir="$1"
    if [ -d "$venv_dir" ] && [ -x "$venv_dir/bin/python" ]; then
        echo "$venv_dir/bin/python"
    elif command -v python3 &>/dev/null; then
        echo "python3"
    else
        print_error "python3 not found and no venv at $venv_dir"
        exit 1
    fi
}

# ── 1. Backend ────────────────────────────────────────────────────────────────
print_info "[1/3] Starting Backend (port 5000)..."
BACKEND_PYTHON=$(resolve_python "$PROJECT_ROOT/backend/venv")

if [ "$BACKEND_PYTHON" = "python3" ]; then
    print_warning "backend/venv not found — using system python3"
fi

(
    cd "$PROJECT_ROOT/backend"
    export SUPER_ADMIN_PASSWORD="${SUPER_ADMIN_PASSWORD:-Admin@2030}"
    # PLATFORM_URL is used by the agent install-instructions endpoint. Agents talk
    # HTTP directly to the backend (:5000) — they can't verify the self-signed TLS
    # cert — so this stays HTTP even though the browser front door is HTTPS.
    # Override with PLATFORM_URL=... .
    export PLATFORM_URL="${PLATFORM_URL:-http://${SERVER_IP}:5000}"
    # Ticket file upload directory (auto-created by tickets_endpoints on start)
    export TICKET_ATTACHMENT_DIR="${TICKET_ATTACHMENT_DIR:-/tmp/ticket_attachments}"
    # Use socket_app (not app) so Socket.IO real-time events work
    "$BACKEND_PYTHON" -m uvicorn app:socket_app \
        --host 0.0.0.0 --port 5000 --log-level info
) &
BACKEND_PID=$!
print_success "Backend started (PID: $BACKEND_PID)"

# Wait until backend is healthy (up to 60 s)
print_info "Waiting for backend to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
        print_success "Backend is healthy"
        break
    fi
    if [ "$i" -eq 30 ]; then
        print_warning "Backend did not become healthy in 60 s — continuing anyway"
    fi
    sleep 2
done

# ── 2. Frontend ───────────────────────────────────────────────────────────────
# Serves HTTPS on :443 when certs/ exist (see vite.config.ts). Binding :443
# requires root — run this launcher with sudo, or set VITE_PORT for a high port.
print_info "[2/3] Starting Frontend (HTTPS on port 443)..."
(
    cd "$PROJECT_ROOT"
    npm run dev
) &
FRONTEND_PID=$!
print_success "Frontend started (PID: $FRONTEND_PID)"

# ── 3. Agent ──────────────────────────────────────────────────────────────────
print_info "[3/3] Starting Agent..."
AGENT_PYTHON=$(resolve_python "$PROJECT_ROOT/agent/venv")

if [ "$AGENT_PYTHON" = "python3" ]; then
    print_warning "agent/venv not found — using system python3"
fi

(
    cd "$PROJECT_ROOT/agent"
    export MONGODB_URL="${MONGODB_URL:-mongodb://127.0.0.1:27017}"
    export DATABASE_NAME="${DATABASE_NAME:-omni_agent_platform}"
    "$AGENT_PYTHON" agent.py
) &
AGENT_PID=$!
print_success "Agent started (PID: $AGENT_PID)"

echo ""
echo "============================================="
print_success "All services running!"
echo "============================================="
echo ""
echo "  Frontend:  https://${SERVER_IP}"
echo "  API:       https://${SERVER_IP}/api        (proxied to backend over TLS)"
echo "  Health:    https://${SERVER_IP}/api/health"
echo "  Backend:   http://${SERVER_IP}:5000        (direct, HTTP — internal/debug only)"
echo ""
echo "  Note: self-signed cert — accept the one-time browser warning, or trust certs/server.crt."
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Keep alive until any service dies or user presses Ctrl+C
wait -n 2>/dev/null || wait
print_warning "A service exited — stopping remaining services"
cleanup
