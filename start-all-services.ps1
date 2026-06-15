#Requires -Version 5.1
<#
.SYNOPSIS
    Enterprise Omni-Agent AI Platform - Windows Service Launcher
.DESCRIPTION
    Auto-installs missing dependencies, then starts MongoDB, Backend (FastAPI on :5000),
    Frontend (Vite/React on :3000), and the Agent.
    Run from the project root: .\start-all-services.ps1
#>

Set-StrictMode -Version Latest

# ── Configuration ──────────────────────────────────────────────────────────────
$ROOT           = $PSScriptRoot
$BACKEND_DIR    = Join-Path $ROOT "backend"
$AGENT_DIR      = Join-Path $ROOT "agent"
$BACKEND_PYTHON = Join-Path $BACKEND_DIR "venv\Scripts\python.exe"
$AGENT_PYTHON   = Join-Path $AGENT_DIR   "venv\Scripts\python.exe"

$BACKEND_PORT  = 5000
$FRONTEND_PORT = 3000
$MONGO_PORT    = 27017

$MONGODB_URL   = "mongodb://127.0.0.1:$MONGO_PORT"
$DATABASE_NAME = "omni_agent_platform"
$CORS_ORIGINS  = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"

$API_BASE_URL     = "http://127.0.0.1:$BACKEND_PORT"
$REGISTRATION_KEY = "reg_platformadmin123"
$TENANT_ID        = "platform-admin"

# ── Helpers ────────────────────────────────────────────────────────────────────
function Write-Step { param($n, $msg) Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg)     Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg)     Write-Host "    !!  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg)     Write-Host "    ERR $msg" -ForegroundColor Red }

function Test-Port {
    param([int]$Port)
    $tcp = New-Object System.Net.Sockets.TcpClient
    try { $tcp.Connect("127.0.0.1", $Port); $tcp.Close(); return $true }
    catch { return $false }
}

function Stop-Port {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($c in $conns) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-Port {
    param([int]$Port, [string]$Name, [int]$TimeoutSec = 60)
    $elapsed = 0
    while (-not (Test-Port $Port)) {
        if ($elapsed -ge $TimeoutSec) { return $false }
        Write-Host "`r    ... waiting for $Name (:$Port) ${elapsed}s   " -NoNewline
        Start-Sleep 3
        $elapsed += 3
    }
    Write-Host ""
    return $true
}

function Start-WindowedProcess {
    param([string]$Title, [string]$WorkDir, [string]$Command)
    Start-Process powershell.exe `
        -ArgumentList "-NoExit", "-Command", $Command `
        -WorkingDirectory $WorkDir `
        -WindowStyle Normal
}

# ── Banner ─────────────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host "   Enterprise Omni-Agent AI Platform" -ForegroundColor Cyan
Write-Host "   Windows Service Launcher" -ForegroundColor Cyan
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host ""

# ── Prerequisites ──────────────────────────────────────────────────────────────
Write-Step "0" "Checking prerequisites"

# Python
try { $null = & python --version 2>$null; Write-OK "Python found" }
catch { Write-Fail "Python not found. Install from https://python.org (tick Add to PATH)"; exit 1 }

# Node
try { $null = & node --version 2>$null; Write-OK "Node.js found" }
catch { Write-Fail "Node.js not found. Install from https://nodejs.org/"; exit 1 }

# Backend dir
if (-not (Test-Path $BACKEND_DIR)) {
    Write-Fail "Backend directory not found: $BACKEND_DIR"; exit 1
}

# Backend venv — auto-create if missing
if (-not (Test-Path $BACKEND_PYTHON)) {
    Write-Warn "Backend venv missing - creating it (this takes ~60s the first time)..."
    Push-Location $BACKEND_DIR
    & python -m venv venv
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create backend venv"; exit 1 }
    Write-Host "    ... Installing backend dependencies..." -ForegroundColor Gray
    & "$BACKEND_DIR\venv\Scripts\pip.exe" install --upgrade pip --quiet
    & "$BACKEND_DIR\venv\Scripts\pip.exe" install -r "$BACKEND_DIR\requirements.txt" --quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed — check requirements.txt"; exit 1 }
    Pop-Location
    Write-OK "Backend venv ready"
} else {
    Write-OK "Backend venv found"
}

# node_modules — auto-install if missing
if (-not (Test-Path (Join-Path $ROOT "node_modules"))) {
    Write-Warn "node_modules missing - running npm install (this takes ~30s the first time)..."
    Push-Location $ROOT
    & npm install
    if ($LASTEXITCODE -ne 0) { Write-Fail "npm install failed"; exit 1 }
    Pop-Location
    Write-OK "node_modules ready"
} else {
    Write-OK "node_modules found"
}

# Agent venv — auto-create if agent exists but venv is missing
$startAgent = $false
if (Test-Path (Join-Path $AGENT_DIR "agent.py")) {
    if (-not (Test-Path $AGENT_PYTHON)) {
        Write-Warn "Agent venv missing - creating it..."
        Push-Location $AGENT_DIR
        & python -m venv venv
        if ($LASTEXITCODE -eq 0) {
            & "$AGENT_DIR\venv\Scripts\pip.exe" install --upgrade pip --quiet
            $agentReqs = Join-Path $AGENT_DIR "requirements.txt"
            if (Test-Path $agentReqs) {
                & "$AGENT_DIR\venv\Scripts\pip.exe" install -r $agentReqs --quiet
            }
            Write-OK "Agent venv ready"
            $startAgent = $true
        } else {
            Write-Warn "Agent venv creation failed - agent will not be started"
        }
        Pop-Location
    } else {
        Write-OK "Agent venv found"
        $startAgent = $true
    }
} else {
    Write-Warn "Agent directory missing - agent will not be started"
}

Write-OK "All prerequisites satisfied"
Write-Host ""

# ── Clear stale processes ──────────────────────────────────────────────────────
Write-Step "1" "Clearing ports $BACKEND_PORT and $FRONTEND_PORT"
Stop-Port $BACKEND_PORT
Stop-Port $FRONTEND_PORT
Start-Sleep 1
Write-OK "Ports cleared"
Write-Host ""

# ── MongoDB ────────────────────────────────────────────────────────────────────
Write-Step "2" "Checking MongoDB on port $MONGO_PORT"
if (Test-Port $MONGO_PORT) {
    Write-OK "MongoDB already running"
} else {
    Write-Warn "MongoDB not running - attempting to start..."
    $svc = Get-Service -Name "MongoDB" -ErrorAction SilentlyContinue
    if ($svc) {
        Start-Service "MongoDB" -ErrorAction SilentlyContinue
        Start-Sleep 4
    } else {
        $dbPath = "C:\data\db"
        New-Item -ItemType Directory -Path $dbPath -Force | Out-Null
        Start-Process "mongod" -ArgumentList "--dbpath", $dbPath, "--port", $MONGO_PORT -WindowStyle Minimized -ErrorAction SilentlyContinue
        Start-Sleep 5
    }
    if (Test-Port $MONGO_PORT) {
        Write-OK "MongoDB started"
    } else {
        Write-Fail "MongoDB failed to start."
        Write-Fail "Install from https://www.mongodb.com/try/download/community or start it manually."
        exit 1
    }
}
Write-Host ""

# ── Backend ────────────────────────────────────────────────────────────────────
Write-Step "3" "Starting Backend (FastAPI/uvicorn on :$BACKEND_PORT)"

$backendScript = @"
`$env:MONGODB_URL             = '$MONGODB_URL'
`$env:DATABASE_NAME           = '$DATABASE_NAME'
`$env:CORS_ORIGINS            = '$CORS_ORIGINS'
`$env:SUPER_ADMIN_PASSWORD    = 'Admin@2030'
`$env:PLATFORM_URL            = 'http://127.0.0.1:$BACKEND_PORT'
`$env:TICKET_ATTACHMENT_DIR   = "`$env:TEMP\ticket_attachments"
`$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
Set-Location '$BACKEND_DIR'
Write-Host ''
Write-Host '  Omni-Agent Backend' -ForegroundColor Cyan
Write-Host '  http://127.0.0.1:$BACKEND_PORT/health' -ForegroundColor Green
Write-Host ''
& '$BACKEND_PYTHON' -m uvicorn app:socket_app --host 0.0.0.0 --port $BACKEND_PORT --log-level info
"@

Start-WindowedProcess "Omni-Backend :$BACKEND_PORT" $BACKEND_DIR $backendScript

Write-Host "    Waiting for backend to be ready (up to 90s)..." -ForegroundColor Gray
if (Wait-Port $BACKEND_PORT "Backend" 90) {
    Write-OK "Backend is up -> http://127.0.0.1:$BACKEND_PORT"
} else {
    Write-Fail "Backend did not start. Check the backend terminal window."
    exit 1
}
Write-Host ""

# ── Frontend ───────────────────────────────────────────────────────────────────
Write-Step "4" "Starting Frontend (Vite/React on :$FRONTEND_PORT)"

$frontendScript = @"
`$env:VITE_PROXY_TARGET = 'http://127.0.0.1:$BACKEND_PORT'
Set-Location '$ROOT'
Write-Host ''
Write-Host '  Omni-Agent Frontend' -ForegroundColor Cyan
Write-Host '  http://localhost:$FRONTEND_PORT' -ForegroundColor Green
Write-Host ''
npm run dev -- --port $FRONTEND_PORT
"@

Start-WindowedProcess "Omni-Frontend :$FRONTEND_PORT" $ROOT $frontendScript

Write-Host "    Waiting for frontend to compile (up to 60s)..." -ForegroundColor Gray
if (Wait-Port $FRONTEND_PORT "Frontend" 60) {
    Write-OK "Frontend is up -> http://localhost:$FRONTEND_PORT"
} else {
    Write-Warn "Frontend not responding - check the frontend terminal window."
}
Write-Host ""

# ── Agent ──────────────────────────────────────────────────────────────────────
if ($startAgent) {
    Write-Step "5" "Starting Agent"

    $agentScript = @"
`$env:API_BASE_URL     = '$API_BASE_URL'
`$env:REGISTRATION_KEY = '$REGISTRATION_KEY'
`$env:TENANT_ID        = '$TENANT_ID'
`$env:MONGODB_URL      = '$MONGODB_URL'
`$env:DATABASE_NAME    = '$DATABASE_NAME'
Set-Location '$AGENT_DIR'
Write-Host ''
Write-Host '  Omni-Agent Client' -ForegroundColor Cyan
Write-Host '  Connecting to $API_BASE_URL' -ForegroundColor Green
Write-Host ''
& '$AGENT_PYTHON' agent.py --url $API_BASE_URL --key $REGISTRATION_KEY
"@

    Start-WindowedProcess "Omni-Agent" $AGENT_DIR $agentScript
    Write-OK "Agent launched"
    Write-Host ""
}

# ── Summary ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host "   All services started!" -ForegroundColor Green
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Service URLs:" -ForegroundColor White
Write-Host "    Frontend   http://localhost:$FRONTEND_PORT" -ForegroundColor Cyan
Write-Host "    Backend    http://127.0.0.1:$BACKEND_PORT" -ForegroundColor Cyan
Write-Host "    API Docs   http://127.0.0.1:$BACKEND_PORT/docs" -ForegroundColor Cyan
Write-Host "    Health     http://127.0.0.1:$BACKEND_PORT/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Default login:  super@omni.ai  /  Admin@2030" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To stop all services:" -ForegroundColor Yellow
Write-Host "    Stop-Process -Name python,node -Force" -ForegroundColor Gray
Write-Host "  Or just close the terminal windows." -ForegroundColor Gray
Write-Host ""

$open = Read-Host "  Open browser now? (Y/N)"
if ($open -match "^[Yy]") {
    Start-Process "http://localhost:$FRONTEND_PORT"
}
