# Enterprise Omni Agent AI Platform - Network Startup Script
# This script starts all services with network accessibility

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "   Enterprise Omni Agent AI Platform" -ForegroundColor Cyan
Write-Host "   Network-Accessible Startup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Get the actual IP address (excluding loopback)
$IP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" }).IPAddress | Select-Object -First 1

if (-not $IP) {
    Write-Host "ERROR: Could not detect network IP address!" -ForegroundColor Red
    exit 1
}

Write-Host "Detected IP Address: $IP" -ForegroundColor Green
Write-Host ""

# Display access URLs
Write-Host "Services will be accessible at:" -ForegroundColor Yellow
Write-Host "  Frontend:  http://$IP:3000" -ForegroundColor White
Write-Host "  Backend:   http://$IP:5000" -ForegroundColor White
Write-Host "  API Docs:  http://$IP:5000/docs" -ForegroundColor White
Write-Host ""

# Check if MongoDB is running
Write-Host "Checking MongoDB..." -ForegroundColor Yellow
$mongoProcess = Get-Process mongod -ErrorAction SilentlyContinue
if (-not $mongoProcess) {
    Write-Host "WARNING: MongoDB is not running!" -ForegroundColor Red
    Write-Host "Please start MongoDB first:" -ForegroundColor Yellow
    Write-Host '  net start MongoDB' -ForegroundColor White
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') {
        exit 1
    }
}
else {
    Write-Host "[OK] MongoDB is running" -ForegroundColor Green
}

Write-Host ""

# Update agent config with current IP
Write-Host "Updating agent configuration..." -ForegroundColor Yellow
$configPath = "agent\config.yaml"
if (Test-Path $configPath) {
    (Get-Content $configPath) -replace 'localhost', $IP | Set-Content $configPath
    Write-Host "[OK] Agent config updated to use $IP" -ForegroundColor Green
}
else {
    Write-Host "WARNING: agent\config.yaml not found" -ForegroundColor Yellow
}

Write-Host ""

# Configure Windows Firewall
Write-Host "Configuring Windows Firewall..." -ForegroundColor Yellow
try {
    # Frontend port 3000
    $rule3000 = Get-NetFirewallRule -DisplayName "Omni Platform Frontend" -ErrorAction SilentlyContinue
    if (-not $rule3000) {
        New-NetFirewallRule -DisplayName "Omni Platform Frontend" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow | Out-Null
        Write-Host "[OK] Firewall rule created for port 3000" -ForegroundColor Green
    }
    else {
        Write-Host "[OK] Firewall rule for port 3000 already exists" -ForegroundColor Green
    }
    
    # Backend port 5000
    $rule5000 = Get-NetFirewallRule -DisplayName "Omni Platform Backend" -ErrorAction SilentlyContinue
    if (-not $rule5000) {
        New-NetFirewallRule -DisplayName "Omni Platform Backend" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow | Out-Null
        Write-Host "[OK] Firewall rule created for port 5000" -ForegroundColor Green
    }
    else {
        Write-Host "[OK] Firewall rule for port 5000 already exists" -ForegroundColor Green
    }
}
catch {
    Write-Host "WARNING: Could not configure firewall (requires admin)" -ForegroundColor Yellow
    Write-Host "Run this script as Administrator to auto-configure firewall" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Starting Services..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Start backend in a new window
Write-Host "Starting Backend Server..." -ForegroundColor Yellow
$backendScript = @"
    cd '$PWD'
    Write-Host '================================================' -ForegroundColor Green
    Write-Host 'Backend Server' -ForegroundColor Green
    Write-Host 'Access at: http://$IP:5000' -ForegroundColor Green
    Write-Host '================================================' -ForegroundColor Green
    Write-Host ''
    cd backend
    ..\venv\Scripts\activate
    python app.py
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

Write-Host "[OK] Backend starting in new window..." -ForegroundColor Green
Start-Sleep -Seconds 3

# Start frontend in a new window
Write-Host "Starting Frontend Server..." -ForegroundColor Yellow
$frontendScript = @"
    cd '$PWD'
    Write-Host '================================================' -ForegroundColor Blue
    Write-Host 'Frontend Server' -ForegroundColor Blue
    Write-Host 'Access at: http://$IP:3000' -ForegroundColor Blue
    Write-Host '================================================' -ForegroundColor Blue
    Write-Host ''
    npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Write-Host "[OK] Frontend starting in new window..." -ForegroundColor Green

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Services Started!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access the platform from any device:" -ForegroundColor Yellow
Write-Host "  http://$IP:3000" -ForegroundColor White -NoNewline
Write-Host " (Frontend)" -ForegroundColor Gray
Write-Host "  http://$IP:5000" -ForegroundColor White -NoNewline
Write-Host " (Backend API)" -ForegroundColor Gray
Write-Host ""
Write-Host "Login Credentials:" -ForegroundColor Yellow
Write-Host "  Super Admin: super@omni.ai / Admin123!" -ForegroundColor White
Write-Host "  Test Admin:  admin@sriprasad.com / Admin123!" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to exit" -ForegroundColor Gray
Write-Host ""

# Keep the main window open
Write-Host "Monitoring services... (Press Ctrl+C to stop)" -ForegroundColor Yellow
while ($true) {
    Start-Sleep -Seconds 30
    Write-Host "$(Get-Date -Format 'HH:mm:ss') - Services running at http://$IP:3000" -ForegroundColor Gray
}
