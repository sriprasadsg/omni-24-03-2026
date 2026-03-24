# Enterprise Omni-Agent Platform - Service Launcher
# This script launches all required services in separate terminal windows

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Enterprise Omni-Agent Platform - Launcher"
Write-Host "============================================="
Write-Host ""

$projectRoot = "d:\Downloads\enterprise-omni-agent-ai-platform"

# Check if project directory exists
if (-not (Test-Path $projectRoot)) {
    Write-Host "ERROR: Project directory not found at $projectRoot" -ForegroundColor Red
    Write-Host "Please update the `$projectRoot variable in this script." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Starting services..." -ForegroundColor Green
Write-Host ""

# 1. Launch Backend (uvicorn)
Write-Host "[1/3] Starting Backend (Port 5000)..." -ForegroundColor Yellow
$backendCmd = "cd '$projectRoot\backend'; Write-Host 'Backend Server Starting...' -ForegroundColor Green; & 'venv\Scripts\python.exe' -m uvicorn app:app --reload --port 5000 --host 127.0.0.1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
Write-Host "  ✓ Backend launched in new window" -ForegroundColor Green
Start-Sleep -Seconds 2

# 2. Launch Frontend (npm)
Write-Host "[2/3] Starting Frontend (Port 3000)..." -ForegroundColor Yellow
$frontendCmd = "cd '$projectRoot'; Write-Host 'Frontend Server Starting...' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
Write-Host "  ✓ Frontend launched in new window" -ForegroundColor Green
Start-Sleep -Seconds 2

# 3. Launch Agent
Write-Host "[3/3] Starting Agent..." -ForegroundColor Yellow
$agentCmd = "cd '$projectRoot\agent'; Write-Host 'Agent Starting...' -ForegroundColor Green; & 'venv\Scripts\python.exe' agent.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $agentCmd
Write-Host "  ✓ Agent launched in new window" -ForegroundColor Green
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "All services started!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service URLs:" -ForegroundColor White
Write-Host "  Frontend:  http://127.0.0.1:3000" -ForegroundColor Cyan
Write-Host "  Backend:   http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host "  Health:    http://127.0.0.1:5000/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: Wait 60-90 seconds for:" -ForegroundColor Yellow
Write-Host "  1. Backend to fully initialize" -ForegroundColor White
Write-Host "  2. Frontend to compile and start" -ForegroundColor White
Write-Host "  3. Agent to complete first compliance scan" -ForegroundColor White
Write-Host ""
Write-Host "To test Phase 1 compliance features:" -ForegroundColor Yellow
Write-Host "  1. Wait 90 seconds (timing is important!)" -ForegroundColor White
Write-Host "  2. Open http://127.0.0.1:3000 in your browser" -ForegroundColor White
Write-Host "  3. Navigate to: Agents → EILT0197 → Compliance Tab" -ForegroundColor White
Write-Host "  4. Verify you see 28-36 compliance checks" -ForegroundColor White
Write-Host ""

# Ask if user wants to auto-open browser after waiting
$openBrowser = Read-Host "Open browser automatically after 90 seconds? (Y/N)"

if ($openBrowser -eq "Y" -or $openBrowser -eq "y") {
    Write-Host ""
    Write-Host "Waiting 90 seconds for services to initialize..." -ForegroundColor Yellow
    
    for ($i = 90; $i -gt 0; $i--) {
        Write-Progress -Activity "Waiting for services to start" -Status "$i seconds remaining..." -PercentComplete ((90 - $i) / 90 * 100)
        Start-Sleep -Seconds 1
    }
    
    Write-Progress -Activity "Waiting for services to start" -Completed
    
    Write-Host ""
    Write-Host "Opening browser..." -ForegroundColor Green
    Start-Process "http://127.0.0.1:3000"
    
    Write-Host ""
    Write-Host "Browser opened! You should now be able to test the compliance features." -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "Remember to wait 90 seconds before opening http://127.0.0.1:3000" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "To stop all services:" -ForegroundColor Yellow
Write-Host "  - Close all 3 terminal windows that were opened" -ForegroundColor White
Write-Host "  - OR press Ctrl+C in each window" -ForegroundColor White
Write-Host ""
Write-Host "Press Enter to exit this launcher..." -ForegroundColor Cyan
Read-Host
