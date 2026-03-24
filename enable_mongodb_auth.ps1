# MongoDB --auth Enabler Script
# Run this script AS ADMINISTRATOR

$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "MongoDB Authentication Enforcement" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please:" -ForegroundColor Yellow
    Write-Host "1. Right-click PowerShell" -ForegroundColor White
    Write-Host "2. Select 'Run as Administrator'" -ForegroundColor White
    Write-Host "3. Run this script again" -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Running as Administrator" -ForegroundColor Green
Write-Host ""

# Configuration
$configFile = "C:\Program Files\MongoDB\Server\8.0\bin\mongod.cfg"
$backupFile = "$configFile.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# Step 1: Check config file
Write-Host "Step 1: Checking MongoDB configuration..." -ForegroundColor Yellow

if (-not (Test-Path $configFile)) {
    Write-Host "ERROR: Config not found at $configFile" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Found: $configFile" -ForegroundColor Green
Write-Host ""

# Step 2: Show current config
Write-Host "Current configuration:" -ForegroundColor Cyan
Get-Content $configFile
Write-Host ""

# Step 3: Create backup
Write-Host "Step 2: Creating backup..." -ForegroundColor Yellow
Copy-Item $configFile $backupFile -Force
Write-Host "Backup created: $backupFile" -ForegroundColor Green
Write-Host ""

# Step 4: Add security section
Write-Host "Step 3: Adding authentication..." -ForegroundColor Yellow
$content = Get-Content $configFile -Raw

if ($content -match "security:") {
    Write-Host "Security section already exists" -ForegroundColor Yellow
}
else {
    $securitySection = "`r`n# Security Configuration`r`nsecurity:`r`n  authorization: enabled`r`n"
    Add-Content -Path $configFile -Value $securitySection -Encoding UTF8
    Write-Host "Added security.authorization: enabled" -ForegroundColor Green
}
Write-Host ""

# Step 5: Show updated config
Write-Host "Updated configuration:" -ForegroundColor Cyan
Get-Content $configFile
Write-Host ""

# Step 6: Restart MongoDB
Write-Host "Step 4: Restarting MongoDB..." -ForegroundColor Yellow
try {
    Write-Host "Stopping MongoDB..." -ForegroundColor Gray
    Stop-Service -Name MongoDB -Force
    Start-Sleep -Seconds 2
    
    Write-Host "Starting MongoDB..." -ForegroundColor Gray
    Start-Service -Name MongoDB
    Start-Sleep -Seconds 3
    
    $service = Get-Service -Name MongoDB
    if ($service.Status -eq "Running") {
        Write-Host "MongoDB restarted successfully" -ForegroundColor Green
    }
    else {
        Write-Host "ERROR: MongoDB not running" -ForegroundColor Red
        Copy-Item $backupFile $configFile -Force
        Start-Service -Name MongoDB
        Read-Host "Press Enter to exit"
        exit 1
    }
}
catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Copy-Item $backupFile $configFile -Force
    Start-Service -Name MongoDB
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Step 7: Test authentication
Write-Host "Step 5: Testing authentication..." -ForegroundColor Yellow

# Test without auth (should fail)
Write-Host "Test 1: Connection without credentials..." -ForegroundColor Gray
$testCmd = 'mongosh --quiet --eval "db.adminCommand({ping: 1})" 2>&1'
$result = Invoke-Expression $testCmd

if ($result -like "*not authorized*" -or $result -like "*Authentication failed*") {
    Write-Host "PASS: Authentication required" -ForegroundColor Green
}
else {
    Write-Host "WARNING: May not require auth yet" -ForegroundColor Yellow
}
Write-Host ""

# Test with auth (should work)
Write-Host "Test 2: Connection WITH credentials..." -ForegroundColor Gray
$connectionString = 'mongodb://omni_app:SecureApp%232025!MongoDB@localhost:27017/omni_platform?authSource=omni_platform'
$authTestCmd = "mongosh `"$connectionString`" --quiet --eval `"db.agents.countDocuments()`" 2>&1"
$authResult = Invoke-Expression $authTestCmd

if ($authResult -match '^\d+$') {
    Write-Host "PASS: Authenticated connection works" -ForegroundColor Green
    Write-Host "Found $authResult agents" -ForegroundColor Gray
}
else {
    Write-Host "WARNING: Auth connection issue" -ForegroundColor Yellow
    Write-Host "Result: $authResult" -ForegroundColor Gray
}
Write-Host ""

# Test application
Write-Host "Step 6: Testing application..." -ForegroundColor Yellow
try {
    $health = Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing -TimeoutSec 5
    if ($health.StatusCode -eq 200) {
        Write-Host "PASS: Application healthy" -ForegroundColor Green
    }
}
catch {
    Write-Host "WARNING: Application health check failed" -ForegroundColor Yellow
    Write-Host "Error: $_" -ForegroundColor Gray
}
Write-Host ""

# Summary
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "MongoDB Authentication ENABLED" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Config: $configFile" -ForegroundColor White
Write-Host "Backup: $backupFile" -ForegroundColor White
Write-Host "MongoDB: $((Get-Service MongoDB).Status)" -ForegroundColor White
Write-Host ""
Write-Host "To rollback:" -ForegroundColor Yellow
Write-Host "  Copy-Item '$backupFile' '$configFile' -Force" -ForegroundColor Gray
Write-Host "  Restart-Service MongoDB" -ForegroundColor Gray
Write-Host ""
Read-Host "Press Enter to exit"
