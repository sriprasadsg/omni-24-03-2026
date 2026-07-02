#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs (or uninstalls) the OmniAgent Rust Windows service.

.DESCRIPTION
    Copies the agent binary to C:\Program Files\OmniAgent\, writes config.yaml,
    creates the "OmniAgentRust" service under the LocalSystem (SYSTEM) account so
    every PowerShell evidence command runs with full administrator privileges.

.PARAMETER ApiUrl
    Backend API base URL.  Example: https://my-platform.example.com

.PARAMETER RegistrationKey
    Tenant registration key shown in the platform Settings page.

.PARAMETER Uninstall
    Stop and remove the service and installation directory.

.EXAMPLE
    .\install-service.ps1 -ApiUrl https://platform.example.com -RegistrationKey reg_abc123

.EXAMPLE
    .\install-service.ps1 -Uninstall
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ApiUrl          = "http://localhost:5000",
    [string]$RegistrationKey = "",
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ServiceName = "OmniAgentRust"
$DisplayName = "Enterprise OmniAgent (Rust)"
$Description = "Enterprise security compliance agent - collects evidence, runs CISSP/PCI/ISO checks."
$InstallDir  = "$env:ProgramFiles\OmniAgent"
$ExeName     = "omni-agent.exe"
$ExeDst      = Join-Path $InstallDir $ExeName
$ConfigDst   = Join-Path $InstallDir "config.yaml"
$LogDir      = Join-Path $InstallDir "logs"

function Write-Step([string]$msg) { Write-Host "  > $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "  + $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }

# --- Uninstall -----------------------------------------------------------

if ($Uninstall) {
    Write-Host "`n[OmniAgent] Uninstalling service..." -ForegroundColor Magenta

    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Step "Stopping service..."
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Write-Step "Removing service..."
        & sc.exe delete $ServiceName | Out-Null
        Write-Ok "Service removed."
    } else {
        Write-Warn "Service '$ServiceName' not found - skipping."
    }

    if (Test-Path $InstallDir) {
        Write-Step "Removing install directory $InstallDir ..."
        Remove-Item -Recurse -Force $InstallDir
        Write-Ok "Directory removed."
    }

    Write-Host "`n[OmniAgent] Uninstall complete.`n" -ForegroundColor Green
    exit 0
}

# --- Install -------------------------------------------------------------

Write-Host "`n[OmniAgent] Installing Windows service..." -ForegroundColor Magenta

# 1. Locate the EXE next to this script (or in target\release\)
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ExeSrc     = $null
$candidates = @(
    (Join-Path $ScriptDir $ExeName),
    (Join-Path $ScriptDir "target\release\$ExeName"),
    (Join-Path $ScriptDir "target\x86_64-pc-windows-msvc\release\$ExeName")
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $ExeSrc = $c; break }
}

if (-not $ExeSrc) {
    Write-Host "`nERROR: Cannot find $ExeName." -ForegroundColor Red
    Write-Host "  Looked in:" -ForegroundColor Red
    $candidates | ForEach-Object { Write-Host "    $_" }
    Write-Host "`n  Build first:  cargo build --release" -ForegroundColor Yellow
    Write-Host "  Then re-run this script.`n" -ForegroundColor Yellow
    exit 1
}

# 2. Stop and remove existing service (clean upgrade)
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Step "Stopping existing service for upgrade..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 1
    Write-Ok "Old service removed."
}

# 3. Create install directory
Write-Step "Creating $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir     | Out-Null

# 4. Copy binary
Write-Step "Copying $ExeName ..."
Copy-Item -Path $ExeSrc -Destination $ExeDst -Force
Write-Ok "Binary installed: $ExeDst"

# 5. Write config.yaml (next to EXE - matches config.rs path logic)
if (-not (Test-Path $ConfigDst) -or $RegistrationKey) {
    Write-Step "Writing config.yaml ..."
    Set-Content -Path $ConfigDst -Encoding UTF8 -Value @"
api_base_url: $ApiUrl
registration_key: $RegistrationKey
interval_seconds: 60
evidence_collection: true
evidence_interval_hours: 24
"@
    Write-Ok "Config written: $ConfigDst"
} else {
    Write-Warn "config.yaml already exists - skipping (use -RegistrationKey to overwrite)."
}

# 5a. Restrict config.yaml (contains the plaintext registration_key) so only SYSTEM
# and Administrators can read it — default Program Files ACLs otherwise grant
# Users/Authenticated Users read access (WR-04).
if (Test-Path $ConfigDst) {
    $cfgAcl = Get-Acl $ConfigDst
    $cfgAcl.SetAccessRuleProtection($true, $false)
    $cfgSysRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "NT AUTHORITY\SYSTEM", "FullControl", "Allow")
    $cfgAdmRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "BUILTIN\Administrators", "FullControl", "Allow")
    $cfgAcl.AddAccessRule($cfgSysRule)
    $cfgAcl.AddAccessRule($cfgAdmRule)
    Set-Acl -Path $ConfigDst -AclObject $cfgAcl
    Write-Ok "Secured config.yaml (SYSTEM + Administrators only)."
}

# 5b. Download Collect-Evidence.ps1 from platform
$EvidenceScript = Join-Path $InstallDir "Collect-Evidence.ps1"
Write-Step "Downloading Collect-Evidence.ps1..."
try {
    Invoke-WebRequest -Uri "$ApiUrl/api/agent/collect-evidence-script" `
        -OutFile $EvidenceScript -UseBasicParsing -ErrorAction Stop
    Write-Ok "Evidence collector installed: $EvidenceScript"
} catch {
    Write-Warn "Could not download Collect-Evidence.ps1: $_"
}

# 5c. Register daily scheduled task for evidence collection
Write-Step "Registering scheduled task..."
if (Test-Path $EvidenceScript) {
    $action    = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$EvidenceScript`""
    $trigger   = New-ScheduledTaskTrigger -Daily -At "06:00"
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName "OmniAgentEvidenceCollection" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Ok "Scheduled task registered (daily 06:00, SYSTEM)."
}

# 6. Create service - LocalSystem = SYSTEM account (full admin, no PATH stripping issues)
Write-Step "Creating Windows service '$ServiceName' ..."
& sc.exe create $ServiceName `
    binPath= "`"$ExeDst`"" `
    start= auto `
    obj= LocalSystem `
    DisplayName= $DisplayName | Out-Null

& sc.exe description $ServiceName $Description | Out-Null

# Configure failure recovery: restart after 5 s, 3 consecutive failures
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null

Write-Ok "Service created (LocalSystem, auto-start)."

# 7. Set service to delayed auto-start so network is available on boot
Write-Step "Setting delayed auto-start..."
& sc.exe config $ServiceName start= delayed-auto | Out-Null
Write-Ok "Delayed auto-start configured."

# 8. Grant service binary ACL: SYSTEM full control, Administrators read/execute
Write-Step "Setting ACL on binary..."
$acl = Get-Acl $ExeDst
$acl.SetAccessRuleProtection($true, $false)
$sysRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "NT AUTHORITY\SYSTEM", "FullControl", "Allow")
$admRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators", "ReadAndExecute", "Allow")
$acl.AddAccessRule($sysRule)
$acl.AddAccessRule($admRule)
Set-Acl -Path $ExeDst -AclObject $acl
Write-Ok "ACL set (SYSTEM=FullControl, Administrators=ReadAndExecute)."

# 9. Start the service
Write-Step "Starting service..."
Start-Service -Name $ServiceName
$svc = Get-Service -Name $ServiceName
Write-Ok "Service status: $($svc.Status)"

# --- Summary -------------------------------------------------------------

Write-Host "`n[OmniAgent] Installation complete." -ForegroundColor Green
Write-Host ""
Write-Host "  Service  : $ServiceName"
Write-Host "  Account  : LocalSystem (SYSTEM - full administrator privileges)"
Write-Host "  Binary   : $ExeDst"
Write-Host "  Config   : $ConfigDst"
Write-Host "  Logs     : $LogDir\omni-agent.log"
Write-Host "  Evidence : $EvidenceScript"
Write-Host "  Task     : OmniAgentEvidenceCollection (daily 06:00 SYSTEM)"
Write-Host ""
Write-Host "  To verify      : Get-Service $ServiceName"
Write-Host "  To collect now : powershell -File `"$EvidenceScript`""
Write-Host "  To view log    : Get-Content '$LogDir\omni-agent.log' -Tail 50 -Wait"
Write-Host "  To uninstall   : .\install-service.ps1 -Uninstall"
Write-Host ""
