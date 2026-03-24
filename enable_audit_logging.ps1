# Enable Compliance Audit Logging
# =====================================
# This script enables Windows audit policies for compliance with:
# - NIST CSF DE.AE-1 (Anomalies and Events)
# - PCI DSS 10.1 (Audit Logging)
# - ISO 27001 A.12.4.1 (Event Logging)
#
# IMPORTANT: Must be run as Administrator!

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Compliance Audit Logging Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: Administrator privileges required!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run PowerShell as Administrator:" -ForegroundColor Yellow
    Write-Host "1. Right-click PowerShell icon" -ForegroundColor White
    Write-Host "2. Select 'Run as Administrator'" -ForegroundColor White
    Write-Host "3. Re-run this script" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

Write-Host "[1/4] Enabling Logon/Logoff Auditing..." -ForegroundColor Yellow
auditpol /set /category:"Logon/Logoff" /success:enable /failure:enable
if ($LASTEXITCODE -eq 0) {
    Write-Host "  SUCCESS: Logon/Logoff auditing enabled" -ForegroundColor Green
}
else {
    Write-Host "  FAILED: Could not enable Logon/Logoff auditing" -ForegroundColor Red
}

Write-Host ""
Write-Host "[2/4] Enabling Account Logon Auditing..." -ForegroundColor Yellow
auditpol /set /category:"Account Logon" /success:enable /failure:enable
if ($LASTEXITCODE -eq 0) {
    Write-Host "  SUCCESS: Account Logon auditing enabled" -ForegroundColor Green
}
else {
    Write-Host "  FAILED: Could not enable Account Logon auditing" -ForegroundColor Red
}

Write-Host ""
Write-Host "[3/4] Enabling Policy Change Auditing..." -ForegroundColor Yellow
auditpol /set /category:"Policy Change" /success:enable /failure:enable
if ($LASTEXITCODE -eq 0) {
    Write-Host "  SUCCESS: Policy Change auditing enabled" -ForegroundColor Green
}
else {
    Write-Host "  FAILED: Could not enable Policy Change auditing" -ForegroundColor Red
}

Write-Host ""
Write-Host "[4/4] Verifying Configuration..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Current Audit Policy:" -ForegroundColor Cyan
Write-Host "--------------------" -ForegroundColor Cyan
auditpol /get /category:"Logon/Logoff"

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Audit Logging Configuration Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "What happens next:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Agent will detect changes within ~60 minutes" -ForegroundColor White
Write-Host "2. Compliance checks will auto-update to PASS" -ForegroundColor White
Write-Host "3. Dashboard will show improved compliance score" -ForegroundColor White
Write-Host ""
Write-Host "Affected Controls:" -ForegroundColor Cyan
Write-Host "  - NIST CSF DE.AE-1: Anomalies and Events" -ForegroundColor White
Write-Host "  - PCI DSS 10.1: Audit Logging" -ForegroundColor White
Write-Host "  - ISO 27001 A.12.4.1: Event Logging" -ForegroundColor White
Write-Host "  - SOC 2 CC9.2: Vendor Management" -ForegroundColor White
Write-Host ""
