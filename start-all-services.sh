#!/bin/bash

# Enterprise Omni-Agent Platform - Linux Launcher

echo "============================================="
echo "Enterprise Omni-Agent Platform - Launcher"
echo "============================================="
echo ""

PROJECT_ROOT=$(pwd)

# Function to kill child processes on exit
cleanup() {
    echo ""
    echo "Stopping all services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

echo "Starting services..."
echo ""

# 1. Start Backend
echo "[1/3] Starting Backend (Port 5000)..."
if [ -d "backend/venv" ]; then
    PYTHON_CMD="backend/venv/bin/python"
else
    PYTHON_CMD="python3"
    echo "Warning: backend/venv not found, using system python3"
fi

cd backend
$PROJECT_ROOT/$PYTHON_CMD -m uvicorn app:app --reload --port 5000 --host 127.0.0.1 &
BACKEND_PID=$!
cd ..
echo "  ✓ Backend started (PID: $BACKEND_PID)"
sleep 2

# 2. Start Frontend
echo "[2/3] Starting Frontend (Port 3000)..."
npm run dev &
FRONTEND_PID=$!
echo "  ✓ Frontend started (PID: $FRONTEND_PID)"
sleep 2

# 3. Start Agent
echo "[3/3] Starting Agent..."
if [ -d "agent/venv" ]; then
    AGENT_PYTHON_CMD="agent/venv/bin/python"
else
    AGENT_PYTHON_CMD="python3"
    echo "Warning: agent/venv not found, using system python3"
fi

cd agent
$PROJECT_ROOT/$AGENT_PYTHON_CMD agent.py &
AGENT_PID=$!
cd ..
echo "  ✓ Agent started (PID: $AGENT_PID)"
sleep 1

echo ""
echo "============================================="
echo "All services started!"
echo "============================================="
echo ""
echo "Service URLs:"
echo "  Frontend:  http://127.0.0.1:3000"
echo "  Backend:   http://127.0.0.1:5000"
echo "  Health:    http://127.0.0.1:5000/health"
echo ""
echo "Ready to use! Open http://127.0.0.1:3000 in your browser."
echo ""
echo "Press Ctrl+C to stop all services."

# Keep script running to maintain background processes
wait
