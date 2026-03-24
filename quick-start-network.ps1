# Quick Start - Network Accessible
# Simplified version

$IP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" }).IPAddress | Select-Object -First 1

if (-not $IP) {
    Write-Host "ERROR: Could not detect IP!" -ForegroundColor Red
    exit 1
}

# Update agent config
$configPath = "agent\config.yaml"
if (Test-Path $configPath) {
    (Get-Content $configPath) -replace 'localhost', $IP | Set-Content $configPath
}

Write-Host "Starting services at http://$IP:3000" -ForegroundColor Green
Write-Host ""

# Start backend
$backendCmd = "cd '$PWD\backend'; ..\venv\Scripts\activate; python app.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

Start-Sleep -Seconds 2

# Start frontend  
$frontendCmd = "cd '$PWD'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "[OK] Backend starting..." -ForegroundColor Green
Write-Host "[OK] Frontend starting..." -ForegroundColor Green
Write-Host ""
Write-Host "Access at: http://$IP:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Login: super@omni.ai / Admin123!" -ForegroundColor Yellow
