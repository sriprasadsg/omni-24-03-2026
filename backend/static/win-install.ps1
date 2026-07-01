#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Downloads and installs the OmniAgent Rust Windows service with PowerShell
    evidence collection.

.PARAMETER ApiUrl
    Backend API base URL.  Example: http://192.168.1.100:5000

.PARAMETER RegistrationKey
    Tenant registration key shown in Settings / Agents page.

.PARAMETER BackendUrl
    Alias for -ApiUrl (backwards-compatible).

.PARAMETER SkipFirstRun
    Skip the immediate evidence collection run after install.

.PARAMETER Uninstall
    Stop and remove the service, scheduled task, and installation directory.

.EXAMPLE
    .\win-install.ps1 -ApiUrl http://192.168.1.100:5000 -RegistrationKey reg_abc123

.EXAMPLE
    .\win-install.ps1 -Uninstall
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ApiUrl          = "",
    [string]$BackendUrl      = "",
    [string]$RegistrationKey = "",
    [switch]$SkipFirstRun,
    [switch]$Uninstall
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ApiUrl -and $BackendUrl) { $ApiUrl = $BackendUrl }
if (-not $ApiUrl) { $ApiUrl = "http://localhost:5000" }
$ApiUrl = $ApiUrl.TrimEnd("/")

$ServiceName    = "OmniAgentRust"
$DisplayName    = "Enterprise OmniAgent (Rust)"
$Description    = "Enterprise security compliance agent — collects evidence, runs CIS/PCI/ISO checks."
$InstallDir     = "$env:ProgramFiles\OmniAgent"
$ExeName        = "omni-agent.exe"
$ExeDst         = Join-Path $InstallDir $ExeName
$ConfigDst      = Join-Path $InstallDir "config.yaml"
$EvidenceScript = Join-Path $InstallDir "Collect-Evidence.ps1"
$LogDir         = Join-Path $InstallDir "logs"
$TaskName       = "OmniAgentEvidenceCollection"

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
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Ok "Scheduled task removed."
    if (Test-Path $InstallDir) {
        Write-Step "Removing $InstallDir ..."
        Remove-Item -Recurse -Force $InstallDir
        Write-Ok "Directory removed."
    }
    Write-Host "`n[OmniAgent] Uninstall complete.`n" -ForegroundColor Green
    exit 0
}

# --- Install -------------------------------------------------------------

Write-Host "`n[OmniAgent] Installing Windows service..." -ForegroundColor Magenta
Write-Host "  ApiUrl : $ApiUrl"
if ($RegistrationKey) {
    Write-Host "  RegKey : $($RegistrationKey.Substring(0, [Math]::Min(8, $RegistrationKey.Length)))..."
} else {
    Write-Host "  RegKey : (none)"
}

# 1. Download binary
Write-Step "Downloading agent binary..."
$TmpExe      = Join-Path $env:TEMP $ExeName
$DownloadUrl = "$ApiUrl/api/agent-updates/download/omni-agent.exe"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TmpExe -UseBasicParsing -ErrorAction Stop
    Write-Ok "Downloaded: $TmpExe"
} catch {
    Write-Host "`nERROR: Failed to download from $DownloadUrl`n  $_" -ForegroundColor Red
    Write-Host "  Ensure the platform server is reachable and try again." -ForegroundColor Yellow
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

# 3. Create install directory and copy binary
Write-Step "Installing to $InstallDir ..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir     | Out-Null
Copy-Item -Path $TmpExe -Destination $ExeDst -Force
Remove-Item $TmpExe -ErrorAction SilentlyContinue
Write-Ok "Binary installed: $ExeDst"

# 4. Write config.yaml
Write-Step "Writing config.yaml..."
Set-Content -Path $ConfigDst -Encoding UTF8 -Value @"
api_base_url: $ApiUrl
registration_key: $RegistrationKey
interval_seconds: 60
evidence_collection: true
evidence_interval_hours: 24
"@
Write-Ok "Config written: $ConfigDst"

# 5. Download Collect-Evidence.ps1 from platform
Write-Step "Downloading Collect-Evidence.ps1..."
try {
    Invoke-WebRequest -Uri "$ApiUrl/api/agent/collect-evidence-script" `
        -OutFile $EvidenceScript -UseBasicParsing -ErrorAction Stop
    Write-Ok "Collect-Evidence.ps1 installed: $EvidenceScript"
} catch {
    Write-Warn "Could not download Collect-Evidence.ps1: $_"
    Write-Warn "Evidence collection will be unavailable until script is present."
}

# 6. Create service as LocalSystem (SYSTEM) - full admin, no PATH issues
Write-Step "Creating service '$ServiceName' (LocalSystem)..."
& sc.exe create $ServiceName `
    binPath= "`"$ExeDst`"" `
    start= auto `
    obj= LocalSystem `
    DisplayName= $DisplayName | Out-Null
& sc.exe description $ServiceName $Description | Out-Null
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
Write-Ok "Service created."

Write-Step "Setting delayed auto-start..."
& sc.exe config $ServiceName start= delayed-auto | Out-Null
Write-Ok "Delayed auto-start configured."

# 7. Register daily scheduled task
Write-Step "Registering scheduled task '$TaskName'..."
$action    = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$EvidenceScript`""
$trigger   = New-ScheduledTaskTrigger -Daily -At "06:00"
$settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Write-Ok "Scheduled task registered (daily at 06:00, runs as SYSTEM)."

# 8. Start service
Write-Step "Starting service..."
Start-Service -Name $ServiceName
$svc = Get-Service -Name $ServiceName
Write-Ok "Service status: $($svc.Status)"

# 9. First evidence run (unless skipped)
if (-not $SkipFirstRun -and (Test-Path $EvidenceScript)) {
    Write-Step "Running initial evidence collection..."
    & powershell.exe -NonInteractive -ExecutionPolicy Bypass -File $EvidenceScript
    Write-Ok "Initial evidence collection complete."
}

Write-Host "`n[OmniAgent] Installation complete." -ForegroundColor Green
Write-Host "  Service  : $ServiceName"
Write-Host "  Account  : LocalSystem (SYSTEM - full administrator privileges)"
Write-Host "  Binary   : $ExeDst"
Write-Host "  Config   : $ConfigDst"
Write-Host "  Logs     : $LogDir\omni-agent.log"
Write-Host "  Evidence : $EvidenceScript"
Write-Host "  Task     : $TaskName (daily 06:00 SYSTEM)"
Write-Host ""
Write-Host "  To verify      : Get-Service $ServiceName"
Write-Host "  To collect now : powershell -File `"$EvidenceScript`""
Write-Host "  To tail log    : Get-Content '$LogDir\omni-agent.log' -Tail 50 -Wait"
Write-Host "  To uninstall   : .\win-install.ps1 -Uninstall"
