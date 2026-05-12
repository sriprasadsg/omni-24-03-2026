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
print_info "[2/3] Starting Frontend (port 3000)..."
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
    "$AGENT_PYTHON" agent.py
) &
AGENT_PID=$!
print_success "Agent started (PID: $AGENT_PID)"

echo ""
echo "============================================="
print_success "All services running!"
echo "============================================="
echo ""
echo "  Frontend:  http://127.0.0.1:3000"
echo "  Backend:   http://127.0.0.1:5000"
echo "  Health:    http://127.0.0.1:5000/api/health"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Keep alive until any service dies or user presses Ctrl+C
wait -n 2>/dev/null || wait
print_warning "A service exited — stopping remaining services"
cleanup
