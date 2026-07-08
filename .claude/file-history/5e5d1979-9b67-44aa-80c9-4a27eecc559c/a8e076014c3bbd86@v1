<#
.SYNOPSIS
    Uninstalls the Enterprise Omni Agent Windows Service.

.DESCRIPTION
    Stops the service, removes it from the SCM, removes the installation
    directory, removes Windows Defender exclusions, and removes the firewall
    rule. Optionally preserves logs and config.

.EXAMPLE
    .\uninstall_agent.ps1

    # Remove everything including logs and config
    .\uninstall_agent.ps1 -RemoveAll
#>

param(
    [string] $InstallDir  = "C:\Program Files\OmniAgent",
    [string] $ServiceName = "OmniAgent",
    [string] $LogDir      = "C:\ProgramData\OmniAgent\logs",
    [switch] $RemoveAll,  # Also remove logs and config (default: keep them)
    [switch] $Silent
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-OK   ([string]$msg) { Write-Host "  [OK] $msg" -ForegroundColor Green  }
function Write-Warn ([string]$msg) { Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Step ([string]$msg) { Write-Host "`n==> $msg"  -ForegroundColor Cyan   }

# ── Require Administrator ─────────────────────────────────────────────────────
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Must be run as Administrator." -ForegroundColor Red
    exit 1
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "This will uninstall the Enterprise Omni Agent." -ForegroundColor Yellow
    if ($RemoveAll) {
        Write-Host "ALL files including logs and config will be deleted." -ForegroundColor Red
    } else {
        Write-Host "Logs and config will be preserved in $LogDir" -ForegroundColor Yellow
    }
    $confirm = Read-Host "`nContinue? (y/N)"
    if ($confirm -notmatch '^[yY]') {
        Write-Host "Uninstall cancelled."
        exit 0
    }
}

# ── Stop service ──────────────────────────────────────────────────────────────
Write-Step "Stopping service"
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -eq "Running") {
        Stop-Service -Name $ServiceName -Force
        # Wait up to 15s for clean shutdown
        $waited = 0
        while ((Get-Service $ServiceName).Status -ne "Stopped" -and $waited -lt 15) {
            Start-Sleep -Seconds 1
            $waited++
        }
        Write-OK "Service stopped"
    } else {
        Write-OK "Service was already stopped (Status: $($svc.Status))"
    }
} else {
    Write-Warn "Service '$ServiceName' not found — skipping stop."
}

# ── Remove service from SCM ───────────────────────────────────────────────────
Write-Step "Removing service registration"
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    Write-OK "Service '$ServiceName' removed from SCM"
} else {
    Write-Warn "Service not registered — nothing to remove."
}

# ── Remove firewall rule ──────────────────────────────────────────────────────
Write-Step "Removing firewall rule"
try {
    Remove-NetFirewallRule -DisplayName "OmniAgent Outbound" -ErrorAction SilentlyContinue
    Write-OK "Firewall rule removed"
} catch {
    Write-Warn "Could not remove firewall rule: $_"
}

# ── Remove Defender exclusion ─────────────────────────────────────────────────
Write-Step "Removing Windows Defender exclusion"
try {
    Remove-MpPreference -ExclusionPath    $InstallDir    -ErrorAction SilentlyContinue
    Remove-MpPreference -ExclusionProcess "omni-agent.exe" -ErrorAction SilentlyContinue
    Write-OK "Defender exclusion removed"
} catch {
    Write-Warn "Could not remove Defender exclusion: $_"
}

# ── Remove environment variable ───────────────────────────────────────────────
[System.Environment]::SetEnvironmentVariable(
    "OMNI_AGENT_LOG_DIR", $null, [System.EnvironmentVariableTarget]::Machine)

# ── Remove install directory ──────────────────────────────────────────────────
Write-Step "Removing files"
if (Test-Path $InstallDir) {
    if ($RemoveAll) {
        Remove-Item -Recurse -Force $InstallDir
        Write-OK "Removed install dir: $InstallDir"
    } else {
        # Keep config and logs; only remove the executable
        $exePath = Join-Path $InstallDir "omni-agent.exe"
        if (Test-Path $exePath) {
            Remove-Item -Force $exePath
            Write-OK "Removed: omni-agent.exe"
        }
        Write-Warn "Keeping config.yaml and remaining files in $InstallDir"
        Write-Host "  Delete manually if not needed: Remove-Item -Recurse '$InstallDir'"
    }
} else {
    Write-Warn "Install directory not found: $InstallDir"
}

# ── Remove logs (only with -RemoveAll) ───────────────────────────────────────
if ($RemoveAll -and (Test-Path $LogDir)) {
    Remove-Item -Recurse -Force $LogDir
    Write-OK "Removed log directory: $LogDir"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Enterprise Omni Agent uninstalled successfully." -ForegroundColor Green
if (-not $RemoveAll) {
    Write-Host "  Config/logs preserved at: $InstallDir" -ForegroundColor Yellow
    Write-Host "  Run with -RemoveAll to delete everything." -ForegroundColor Yellow
}
Write-Host ""
