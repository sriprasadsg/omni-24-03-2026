<#
.SYNOPSIS
    Installs the Enterprise Omni Agent as a Windows Service.

.DESCRIPTION
    Copies the agent executable and config to C:\Program Files\OmniAgent\,
    registers it as an auto-start Windows Service with failure recovery,
    adds a Windows Defender exclusion, and optionally creates a firewall rule.

.NOTES
    Must be run as Administrator.
    Tested on Windows 10 21H2+, Windows 11, Windows Server 2019/2022.

.EXAMPLE
    # Install with default settings (Ollama on localhost:11434)
    .\install_agent.ps1

    # Install with VirusTotal key and custom Ollama model
    .\install_agent.ps1 -VirusTotalKey "your-vt-key" -OllamaModel "mistral:7b"

    # Install pointing to Ollama on another machine
    .\install_agent.ps1 -OllamaUrl "http://192.168.1.50:11434" -OllamaModel "llama3.1:8b"

    # Install using Gemini instead of Ollama (requires GEMINI_API_KEY env var on the server)
    .\install_agent.ps1 -LlmProvider "gemini"

    # Full example with all options
    .\install_agent.ps1 -Silent -InstallDir "D:\Security\OmniAgent" `
        -VirusTotalKey "vt-key" -OllamaUrl "http://127.0.0.1:11434" -OllamaModel "llama3.2:3b"
#>

param(
    [string] $InstallDir        = "C:\Program Files\OmniAgent",
    [string] $ServiceName       = "OmniAgent",
    [string] $LogDir            = "C:\ProgramData\OmniAgent\logs",
    [string] $VirusTotalKey     = "",                       # Optional — can also be pushed from the dashboard
    [string] $OllamaUrl         = "http://127.0.0.1:11434", # Local Ollama endpoint (default)
    [string] $OllamaModel       = "llama3.2:3b",            # Default Ollama model
    [string] $LlmProvider       = "ollama",                 # ollama | gemini | anthropic
    [switch] $Silent,
    [switch] $SkipDefenderExclusion,
    [switch] $SkipFirewallRule
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Colour helpers ────────────────────────────────────────────────────────────
function Write-OK   ([string]$msg) { Write-Host "  [OK] $msg"      -ForegroundColor Green  }
function Write-Warn ([string]$msg) { Write-Host "  [!!] $msg"      -ForegroundColor Yellow }
function Write-Fail ([string]$msg) { Write-Host "  [XX] $msg"      -ForegroundColor Red    }
function Write-Step ([string]$msg) { Write-Host "`n==> $msg"       -ForegroundColor Cyan   }

# ── Require Administrator ─────────────────────────────────────────────────────
Write-Step "Checking privileges"
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Fail "This script must be run as Administrator."
    Write-Host "  Right-click PowerShell → 'Run as administrator', then re-run."
    exit 1
}
Write-OK "Running as Administrator"

# ── Locate source files ───────────────────────────────────────────────────────
Write-Step "Locating source files"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# The exe is one level up from installer\ (i.e. in dist\ root)
$SourceExe = Join-Path (Split-Path -Parent $ScriptDir) "omni-agent.exe"
$SourceCfg = Join-Path (Split-Path -Parent $ScriptDir) "config.yaml"

if (-not (Test-Path $SourceExe)) {
    Write-Fail "omni-agent.exe not found at: $SourceExe"
    Write-Host "  Make sure you are running from the unpacked OmniAgent distribution folder."
    exit 1
}
Write-OK "Found: omni-agent.exe  ($([math]::Round((Get-Item $SourceExe).Length / 1MB, 1)) MB)"

if (-not (Test-Path $SourceCfg)) {
    Write-Warn "config.yaml not found — agent will use built-in defaults."
    Write-Host "  Run .\Configure-Agent.ps1 after installation to configure the backend URL."
    $SourceCfg = $null
}

# ── Stop & remove existing service ───────────────────────────────────────────
Write-Step "Checking for existing installation"
$existingSvc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingSvc) {
    Write-Warn "Existing service found — stopping and removing..."
    if ($existingSvc.Status -eq "Running") {
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 3
    }
    & sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    Write-OK "Old service removed"
}

# ── Create directories ────────────────────────────────────────────────────────
Write-Step "Creating directories"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir     | Out-Null
Write-OK "Install dir : $InstallDir"
Write-OK "Log dir     : $LogDir"

# ── Copy files ────────────────────────────────────────────────────────────────
Write-Step "Copying files"
$TargetExe = Join-Path $InstallDir "omni-agent.exe"
$TargetCfg = Join-Path $InstallDir "config.yaml"

Copy-Item -Path $SourceExe -Destination $TargetExe -Force
Write-OK "Copied omni-agent.exe"

if ($SourceCfg) {
    # Don't overwrite an existing user-edited config on upgrade
    if (-not (Test-Path $TargetCfg)) {
        Copy-Item -Path $SourceCfg -Destination $TargetCfg -Force
        Write-OK "Copied config.yaml"
    } else {
        Write-Warn "config.yaml already exists — keeping existing config (not overwriting)."
    }
}

# ── Set NTFS permissions ──────────────────────────────────────────────────────
# Restrict config.yaml so only SYSTEM and Administrators can read it
if (Test-Path $TargetCfg) {
    $acl = Get-Acl $TargetCfg
    $acl.SetAccessRuleProtection($true, $false)   # disable inheritance
    $sysRule   = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "SYSTEM", "FullControl", "Allow")
    $adminRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "Administrators", "FullControl", "Allow")
    $acl.AddAccessRule($sysRule)
    $acl.AddAccessRule($adminRule)
    Set-Acl -Path $TargetCfg -AclObject $acl
    Write-OK "Secured config.yaml (SYSTEM + Administrators only)"
}

# ── Register Windows Service ──────────────────────────────────────────────────
Write-Step "Registering Windows Service"

$binPath = "`"$TargetExe`""

& sc.exe create $ServiceName `
    "binPath=$binPath" `
    start=   auto `
    obj=     LocalSystem `
    DisplayName= "Enterprise Omni Agent" | Out-Null

& sc.exe description $ServiceName `
    "AI-Powered Enterprise Security and Management Agent" | Out-Null

# Failure recovery: restart after 60s, up to 3 times; reset counter after 24h
& sc.exe failure $ServiceName `
    reset=  86400 `
    actions= restart/60000/restart/60000/restart/60000 | Out-Null

Write-OK "Service registered: $ServiceName"
Write-OK "Start type: Automatic"
Write-OK "Recovery: auto-restart (3x, 60s delay)"

# ── Delayed auto-start (recommended for services with network deps) ───────────
& sc.exe config $ServiceName start= delayed-auto | Out-Null
Write-OK "Start type upgraded to: Automatic (Delayed Start)"

# ── Windows Defender exclusion ────────────────────────────────────────────────
if (-not $SkipDefenderExclusion) {
    Write-Step "Adding Windows Defender exclusion"
    try {
        Add-MpPreference -ExclusionPath $InstallDir -ErrorAction Stop
        Add-MpPreference -ExclusionProcess "omni-agent.exe" -ErrorAction Stop
        Write-OK "Defender exclusion added for $InstallDir"
    } catch {
        Write-Warn "Could not add Defender exclusion: $_"
        Write-Warn "Add manually: Add-MpPreference -ExclusionPath '$InstallDir'"
    }
}

# ── Firewall rule (outbound HTTPS to backend) ─────────────────────────────────
if (-not $SkipFirewallRule) {
    Write-Step "Adding outbound firewall rule"
    try {
        $fwRuleName = "OmniAgent Outbound"
        Remove-NetFirewallRule -DisplayName $fwRuleName -ErrorAction SilentlyContinue
        New-NetFirewallRule `
            -DisplayName   $fwRuleName `
            -Direction     Outbound `
            -Action        Allow `
            -Program       $TargetExe `
            -Protocol      TCP `
            -RemotePort    443,5000,8080 `
            -Profile       Any `
            -Enabled       True | Out-Null
        Write-OK "Firewall rule: '$fwRuleName' (TCP 443/5000/8080 outbound)"
    } catch {
        Write-Warn "Could not create firewall rule: $_"
    }
}

# ── Start the service ─────────────────────────────────────────────────────────
Write-Step "Starting service"

# Check config before starting
if (-not (Test-Path $TargetCfg)) {
    Write-Warn "No config.yaml found — service will start but cannot connect to backend."
    Write-Host "  Run: .\Configure-Agent.ps1 to configure, then: Start-Service $ServiceName"
} else {
    try {
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 3
        $svc = Get-Service -Name $ServiceName
        if ($svc.Status -eq "Running") {
            Write-OK "Service started successfully (Status: $($svc.Status))"
        } else {
            Write-Warn "Service status: $($svc.Status) — check Event Log for details."
        }
    } catch {
        Write-Warn "Could not start service automatically: $_"
        Write-Host "  Start manually: Start-Service $ServiceName"
        Write-Host "  Check logs    : Get-EventLog -LogName Application -Source $ServiceName -Newest 20"
    }
}

# ── Evidence Collection Setup ──────────────────────────────────────────────────
Write-Step "Setting up PowerShell evidence collection"

$ApiUrl         = [System.Environment]::GetEnvironmentVariable("OMNI_API_URL", "Machine")
$EvidenceScript = Join-Path $InstallDir "Collect-Evidence.ps1"
# Copy from distribution folder if present, else download
$DistEvidence = Join-Path (Split-Path -Parent $ScriptDir) "Collect-Evidence.ps1"
if (Test-Path $DistEvidence) {
    Copy-Item $DistEvidence $EvidenceScript -Force
    Write-OK "Collect-Evidence.ps1 copied from distribution."
} elseif ($ApiUrl) {
    try {
        Invoke-WebRequest -Uri "$ApiUrl/api/agent/collect-evidence-script" -OutFile $EvidenceScript -UseBasicParsing -ErrorAction Stop
        Write-OK "Collect-Evidence.ps1 downloaded from platform."
    } catch { Write-Warn "Could not obtain Collect-Evidence.ps1: $_" }
}

if (Test-Path $EvidenceScript) {
    $action    = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$EvidenceScript`""
    $trigger   = New-ScheduledTaskTrigger -Daily -At "06:00"
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    Register-ScheduledTask -TaskName "OmniAgentEvidenceCollection" -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    Write-OK "Evidence collection scheduled (daily 06:00 SYSTEM)."
}

# ── Environment variables ─────────────────────────────────────────────────────
Write-Step "Setting environment variables"

[System.Environment]::SetEnvironmentVariable(
    "OMNI_AGENT_LOG_DIR", $LogDir, [System.EnvironmentVariableTarget]::Machine)

# LLM / Ollama configuration
[System.Environment]::SetEnvironmentVariable(
    "LLM_PROVIDER", $LlmProvider, [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable(
    "OLLAMA_URL", $OllamaUrl, [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable(
    "OLLAMA_MODEL", $OllamaModel, [System.EnvironmentVariableTarget]::Machine)
[System.Environment]::SetEnvironmentVariable(
    "LLM_MODEL", $OllamaModel, [System.EnvironmentVariableTarget]::Machine)
Write-OK "LLM_PROVIDER=$LlmProvider"
Write-OK "OLLAMA_URL=$OllamaUrl"
Write-OK "OLLAMA_MODEL=$OllamaModel"

# Check if Ollama is reachable
Write-Step "Checking Ollama connectivity"
try {
    $ollamaResp = Invoke-WebRequest -Uri "$OllamaUrl/api/tags" -TimeoutSec 5 -ErrorAction Stop
    $models = ($ollamaResp.Content | ConvertFrom-Json).models.name -join ", "
    Write-OK "Ollama is running at $OllamaUrl"
    if ($models) { Write-OK "Available models: $models" } else { Write-Warn "No models pulled yet. Run: ollama pull $OllamaModel" }
    if ($models -notmatch [regex]::Escape($OllamaModel)) {
        Write-Warn "Model '$OllamaModel' not found locally."
        Write-Host "  Pull it:  ollama pull $OllamaModel"
    }
} catch {
    Write-Warn "Ollama not reachable at $OllamaUrl — AI features will use rule-based fallback."
    Write-Host "  Install:  winget install Ollama.Ollama"
    Write-Host "  Start:    ollama serve"
    Write-Host "  Pull:     ollama pull $OllamaModel"
}

# VirusTotal API key
if ($VirusTotalKey -ne "") {
    [System.Environment]::SetEnvironmentVariable(
        "VIRUSTOTAL_API_KEY", $VirusTotalKey, [System.EnvironmentVariableTarget]::Machine)
    Write-OK "VIRUSTOTAL_API_KEY set as system environment variable"
} else {
    Write-Warn "No -VirusTotalKey provided — VirusTotal key can be pushed from the dashboard."
    Write-Host "  To set now:  [System.Environment]::SetEnvironmentVariable('VIRUSTOTAL_API_KEY', 'your-key', 'Machine')"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         Enterprise Omni Agent — Installation Complete     ║" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║  Install dir : $($InstallDir.PadRight(42)) ║" -ForegroundColor White
Write-Host "║  Service     : $($ServiceName.PadRight(42)) ║" -ForegroundColor White
Write-Host "║  Logs        : $($LogDir.PadRight(42)) ║" -ForegroundColor White
Write-Host "║  LLM         : $($LlmProvider.PadRight(42)) ║" -ForegroundColor White
Write-Host "║  Ollama URL  : $($OllamaUrl.PadRight(42)) ║" -ForegroundColor White
Write-Host "║  Ollama model: $($OllamaModel.PadRight(42)) ║" -ForegroundColor White
Write-Host "╠══════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║  Useful commands:                                         ║" -ForegroundColor Yellow
Write-Host "║    Get-Service OmniAgent                                  ║" -ForegroundColor Yellow
Write-Host "║    Stop-Service OmniAgent                                 ║" -ForegroundColor Yellow
Write-Host "║    Start-Service OmniAgent                                ║" -ForegroundColor Yellow
Write-Host "║    .\installer\uninstall_agent.ps1   (to remove)         ║" -ForegroundColor Yellow
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
