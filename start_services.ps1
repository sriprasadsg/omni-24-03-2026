#Requires -Version 5.1
<#
.SYNOPSIS
    Quick-start script for development. Starts backend and frontend.
    For full production use, prefer start-all-services.ps1.
#>

$ROOT        = $PSScriptRoot
$BACKEND_DIR = Join-Path $ROOT "backend"
$BACKEND_PY  = Join-Path $BACKEND_DIR "venv\Scripts\python.exe"

$BACKEND_PORT  = 5000
$FRONTEND_PORT = 3000

# Kill existing processes on those ports
Get-NetTCPConnection -LocalPort $BACKEND_PORT,$FRONTEND_PORT -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "Starting Backend..."
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", @"
`$env:MONGODB_URL          = 'mongodb://127.0.0.1:27017'
`$env:DATABASE_NAME        = 'omni_agent_platform'
`$env:CORS_ORIGINS         = 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173'
`$env:SUPER_ADMIN_PASSWORD = 'Admin@2030'
`$env:PLATFORM_URL         = 'http://127.0.0.1:$BACKEND_PORT'
`$env:TICKET_ATTACHMENT_DIR= "`$env:TEMP\ticket_attachments"
Set-Location '$BACKEND_DIR'
& '$BACKEND_PY' -m uvicorn app:socket_app --host 0.0.0.0 --port $BACKEND_PORT --log-level info
"@ -WorkingDirectory $BACKEND_DIR -WindowStyle Normal

Write-Host "Starting Frontend..."
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", @"
`$env:VITE_PROXY_TARGET = 'http://127.0.0.1:$BACKEND_PORT'
Set-Location '$ROOT'
npm run dev -- --port $FRONTEND_PORT
"@ -WorkingDirectory $ROOT -WindowStyle Normal

Write-Host "Waiting for Backend (:$BACKEND_PORT)..."
$retries = 0
while ($retries -lt 30) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $BACKEND_PORT)
        $tcp.Close()
        Write-Host "Backend is UP." -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 3
        $retries++
    }
}
if ($retries -ge 30) { Write-Error "Backend failed to start in 90s"; exit 1 }

Write-Host "Waiting for Frontend (:$FRONTEND_PORT)..."
$retries = 0
while ($retries -lt 20) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $FRONTEND_PORT)
        $tcp.Close()
        Write-Host "Frontend is UP." -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 3
        $retries++
    }
}
if ($retries -ge 20) { Write-Warning "Frontend not responding — check the terminal window." }

Write-Host ""
Write-Host "  Frontend:  http://localhost:$FRONTEND_PORT" -ForegroundColor Cyan
Write-Host "  Backend:   http://127.0.0.1:$BACKEND_PORT" -ForegroundColor Cyan
Write-Host "  API Docs:  http://127.0.0.1:$BACKEND_PORT/docs" -ForegroundColor Cyan
Write-Host "  Login:     super@omni.ai / Admin@2030" -ForegroundColor Yellow
