<#
.SYNOPSIS
    Interactive first-run configuration wizard for the Enterprise Omni Agent.

.DESCRIPTION
    Guides the operator through:
      1. Setting the backend API URL and agent token
      2. Optionally generating a new agent registration via the API
      3. Writing config.yaml to the install directory
      4. Optionally (re)starting the agent service

.EXAMPLE
    # Interactive wizard
    .\Configure-Agent.ps1

    # Non-interactive (CI/automated deployment)
    .\Configure-Agent.ps1 -ApiUrl "https://omni.corp.example.com:5000" `
                           -AgentToken "eyJ..." `
                           -TenantKey "tenant-key-123" `
                           -Silent
#>

param(
    [string] $InstallDir  = "C:\Program Files\OmniAgent",
    [string] $ServiceName = "OmniAgent",
    [string] $ApiUrl      = "",
    [string] $AgentToken  = "",
    [string] $TenantKey   = "",
    [string] $AgentName   = "",
    [switch] $Silent,
    [switch] $Register     # Auto-register agent with backend after configuring
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

function Write-Header ([string]$msg) {
    Write-Host ""
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ("  " + "-" * ($msg.Length)) -ForegroundColor DarkCyan
}

function Prompt-Input ([string]$label, [string]$default = "", [switch]$Secret) {
    $prompt = if ($default) { "$label [$default]" } else { $label }
    if ($Secret) {
        $secure = Read-Host -Prompt "  $prompt" -AsSecureString
        $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    }
    $value = Read-Host -Prompt "  $prompt"
    if ($value) { return $value }
    return $default
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      Enterprise Omni Agent — Configuration Wizard        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# ── Load existing config if present ──────────────────────────────────────────
$ConfigPath = Join-Path $InstallDir "config.yaml"
$existingConfig = @{}
if (Test-Path $ConfigPath) {
    Write-Host ""
    Write-Host "  Existing config found at $ConfigPath" -ForegroundColor Yellow
    # Parse key: value pairs from YAML (simple, no full parser needed)
    Get-Content $ConfigPath | ForEach-Object {
        if ($_ -match '^(\w[\w_]+):\s*(.+)$') {
            $existingConfig[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

# ── Gather settings ───────────────────────────────────────────────────────────
if (-not $Silent) {
    Write-Header "Backend Connection"

    if (-not $ApiUrl) {
        $defaultUrl = if ($existingConfig.ContainsKey("api_base_url")) { $existingConfig["api_base_url"] } else { "http://localhost:5000" }
        $ApiUrl = Prompt-Input "Backend API URL" $defaultUrl
    }

    if (-not $TenantKey) {
        $defaultKey = if ($existingConfig.ContainsKey("tenant_key")) { $existingConfig["tenant_key"] } else { "" }
        $TenantKey = Prompt-Input "Tenant Key (from Admin Portal → Settings → Agents)" $defaultKey
    }

    Write-Header "Agent Identity"

    if (-not $AgentName) {
        $hostname = $env:COMPUTERNAME
        $defaultName = if ($existingConfig.ContainsKey("agent_name")) { $existingConfig["agent_name"] } else { "agent-$hostname" }
        $AgentName = Prompt-Input "Agent Name" $defaultName
    }

    if (-not $AgentToken) {
        $defaultToken = if ($existingConfig.ContainsKey("agent_token")) { "*****(existing)*****" } else { "" }
        $inputToken = Prompt-Input "Agent JWT Token (leave blank to auto-register)" $defaultToken
        if ($inputToken -and $inputToken -ne "*****(existing)*****") {
            $AgentToken = $inputToken
        } elseif ($inputToken -eq "*****(existing)*****") {
            $AgentToken = $existingConfig["agent_token"]
        }
    }

    # Auto-register if no token provided
    if (-not $AgentToken -and $TenantKey) {
        Write-Host ""
        Write-Host "  No agent token provided. Attempting auto-registration..." -ForegroundColor Yellow
        $Register = $true
    }
} else {
    # Silent mode: validate required params
    if (-not $ApiUrl) {
        Write-Host "ERROR: -ApiUrl is required in silent mode." -ForegroundColor Red
        exit 1
    }
    if (-not $TenantKey -and -not $AgentToken) {
        Write-Host "ERROR: Either -TenantKey or -AgentToken is required in silent mode." -ForegroundColor Red
        exit 1
    }
    if (-not $AgentName) { $AgentName = "agent-$env:COMPUTERNAME" }
}

# ── Auto-register with backend ────────────────────────────────────────────────
if ($Register -and $TenantKey -and -not $AgentToken) {
    Write-Header "Registering Agent with Backend"

    $hostname   = $env:COMPUTERNAME
    $os_version = (Get-WmiObject Win32_OperatingSystem).Caption

    $body = @{
        name       = $AgentName
        hostname   = $hostname
        os         = "Windows"
        os_version = $os_version
        version    = "2.0.1"
        capabilities = @(
            "metrics", "process_monitor", "fim", "network_discovery",
            "vulnerability_scanner", "runtime_security", "compliance",
            "persistence_detection", "shadow_ai", "software_management",
            "predictive_health", "autonomous_response", "sbom",
            "edr_realtime", "yara_scanner", "ueba", "patch_installer",
            "vss_manager", "log_shipper", "remote_access"
        )
    } | ConvertTo-Json -Depth 3

    $headers = @{
        "X-Tenant-Key"  = $TenantKey
        "Content-Type"  = "application/json"
    }

    try {
        $response = Invoke-RestMethod `
            -Uri     "$ApiUrl/api/agents/register" `
            -Method  POST `
            -Headers $headers `
            -Body    $body `
            -TimeoutSec 15

        if ($response.token -or $response.agent_token) {
            $AgentToken = if ($response.token) { $response.token } else { $response.agent_token }
            $AgentId    = if ($response.id)    { $response.id }    else { $response.agent_id }
            Write-Host "  [OK] Registered! Agent ID: $AgentId" -ForegroundColor Green
        } elseif ($response.agent_id) {
            # Already registered — fetch existing token or use ID as token
            Write-Host "  [!!] Agent may already be registered." -ForegroundColor Yellow
            Write-Host "       Retrieve the agent token from the Admin Portal." -ForegroundColor Yellow
        } else {
            Write-Host "  [!!] Registration succeeded but no token returned." -ForegroundColor Yellow
            Write-Host "       Response: $($response | ConvertTo-Json)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  [!!] Registration failed: $_" -ForegroundColor Yellow
        Write-Host "       The agent config will be written without a token." -ForegroundColor Yellow
        Write-Host "       Update agent_token in $ConfigPath manually." -ForegroundColor Yellow
    }
}

# ── Write config.yaml ─────────────────────────────────────────────────────────
Write-Header "Writing Configuration"

# Ensure install dir exists
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$agentId = if ($existingConfig.ContainsKey("agent_id")) {
    $existingConfig["agent_id"]
} else {
    "agent-" + [System.Guid]::NewGuid().ToString("N").Substring(0, 8)
}

$configContent = @"
# Enterprise Omni Agent Configuration
# Generated by Configure-Agent.ps1 on $(Get-Date -Format 'yyyy-MM-dd HH:mm')
# Edit this file and restart the service to apply changes.

agent_id: $agentId
agent_name: $AgentName
agent_token: $AgentToken
api_base_url: $ApiUrl
tenant_key: $TenantKey

# Heartbeat interval in seconds (default: 30)
heartbeat_interval: 30

# Evidence Collection
evidence_collection: true
evidence_interval_hours: 24
evidence_submit_url: $ApiUrl/api/powershell-evidence/submit

# Capabilities to enable (remove a line to disable that capability)
enabled_capabilities:
  - metrics
  - process_monitor
  - fim
  - network_discovery
  - vulnerability_scanner
  - runtime_security
  - compliance
  - persistence_detection
  - shadow_ai
  - software_management
  - predictive_health
  - autonomous_response
  - sbom
  - edr_realtime
  - yara_scanner
  - ueba
  - patch_installer
  - vss_manager
  - log_shipper
  - remote_access

# File Integrity Monitoring paths
fim_paths:
  - C:\Windows\System32
  - C:\Program Files
  - C:\Users

# Goals
goals:
  - name: reduce_attack_surface
    description: Reduce overall attack surface score by 40%
    priority: 2
    target: 40.0
    unit: "% reduction"
  - name: patch_critical_cves
    description: Achieve 100% patching of CVSS 9.0+ vulnerabilities
    priority: 1
    target: 100.0
    unit: "% patched"
  - name: compliance_coverage
    description: Achieve 90% passing controls across all compliance frameworks
    priority: 2
    target: 90.0
    unit: "% controls passing"
"@

$configContent | Out-File -FilePath $ConfigPath -Encoding utf8 -Force

# Lock down permissions
$acl = Get-Acl $ConfigPath
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @("SYSTEM", "Administrators")) {
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity, "FullControl", "Allow")
    $acl.AddAccessRule($rule)
}
Set-Acl -Path $ConfigPath -AclObject $acl

Write-Host "  [OK] Config written to: $ConfigPath" -ForegroundColor Green

# ── Restart service ───────────────────────────────────────────────────────────
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    $restart = if ($Silent) { "y" } else { Read-Host "`n  Restart service now? (Y/n)" }
    if ($restart -notmatch '^[nN]') {
        Stop-Service  -Name $ServiceName -Force  -ErrorAction SilentlyContinue
        Start-Sleep   -Seconds 2
        Start-Service -Name $ServiceName
        Start-Sleep   -Seconds 3
        $status = (Get-Service $ServiceName).Status
        Write-Host "  [OK] Service restarted — Status: $status" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "  Service not installed yet. Run install_agent.ps1 to install." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Configuration complete." -ForegroundColor Green
Write-Host ""
