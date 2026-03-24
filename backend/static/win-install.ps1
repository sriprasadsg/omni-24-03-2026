[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl = "http://192.168.0.105:5000",
    
    [string]$TenantId = "default-tenant",
    
    [string]$RegistrationKey = "",

    [string]$AgentToken = ""
)

$ErrorActionPreference = "Stop"

Write-Host "Installing Enterprise Omni Agent..." -ForegroundColor Cyan

# 0. Resolve Registration Key to Tenant ID
if ($RegistrationKey) {
    Write-Host "Resolving Registration Key: $RegistrationKey"
    try {
        $Body = @{ registrationKey = $RegistrationKey } | ConvertTo-Json
        $Resp = Invoke-RestMethod -Uri "$BackendUrl/api/tenants/lookup-key" -Method Post -Body $Body -ContentType "application/json"
        
        if ($Resp.success) {
            $TenantId = $Resp.tenantId
            Write-Host "✅ Key Verified! Tenant: $($Resp.name) ($TenantId)" -ForegroundColor Green
        }
        else {
            Write-Error "Invalid Registration Key."
        }
    }
    catch {
        Write-Error "Failed to resolve Registration Key: $_"
    }
}
else {
    Write-Warning "No Registration Key provided. Using default/manual Tenant ID: $TenantId"
}

# 1. Create Directory
$InstallDir = "C:\EnterpriseOmniAgent"
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}

# 2. Fetch Latest Version Info
Write-Host "Fetching latest agent version from $BackendUrl..."
try {
    $VersionInfo = Invoke-RestMethod -Uri "$BackendUrl/api/agent-updates/latest?platform=windows" -Method Get
    if ($VersionInfo.url) {
        $DownloadUrl = $VersionInfo.url
        Write-Host "Found version $($VersionInfo.version). Downloading from $DownloadUrl..."
    }
    else {
        # Fallback if no version found (e.g. dev mode)
        Write-Warning "No agent version found updates API. Trying direct download..."
        $DownloadUrl = "$BackendUrl/api/agent-updates/download/omni-agent.exe"
    }
}
catch {
    Write-Warning "Could not fetch version info: $_"
    $DownloadUrl = "$BackendUrl/api/agent-updates/download/omni-agent.exe"
}

# 3. Download Binary
$AgentExe = "$InstallDir\omni-agent.exe"
try {
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $AgentExe -ErrorAction Stop
    Write-Host "Downloaded agent binary to $AgentExe"
}
catch {
    Write-Error "Failed to download agent binary from $DownloadUrl : $_"
    exit 1
}


# 4. Create Config
$ConfigContent = @"
api_base_url: "$BackendUrl"
tenant_id: "$TenantId"
agent_token: "$AgentToken"
interval_seconds: 30
swarm:
  enabled: true
autonomous_actions:
  enabled: true
"@
Set-Content -Path "$InstallDir\config.yaml" -Value $ConfigContent
Write-Host "Created config file at $InstallDir\config.yaml"

# 5. Register Service (using nssm or sc)
# We assume sc.exe is available.
$ServiceName = "OmniAgent"
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Stopping existing service..."
    Stop-Service $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 1 # Give time for service to be deleted
}

Write-Host "Registering Service..."
# Note: sc create binPath must be quoted properly
$BinPath = "`"$AgentExe`""
try {
    sc.exe create $ServiceName binPath= $BinPath start= auto DisplayName= "Enterprise Omni Agent" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "sc create failed with exit code $LASTEXITCODE" }
    
    sc.exe description $ServiceName "AI-Powered Enterprise Security Agent" | Out-Null
    Write-Host "Service '$ServiceName' registered successfully."
}
catch {
    if ("$_" -match "1072") {
        Write-Warning "The Windows Service is marked for deletion (Error 1072)."
        Write-Warning "A system reboot is required to fully clean up the old service."
        Write-Warning "Proceeding with standalone mode so you can use the agent immediately."
    }
    else {
        Write-Warning "Failed to register service (likely due to permissions): $_"
    }
    
    Write-Warning "Attempting to start agent as a standalone background process instead..."
    
    # Fallback: Start as background job
    Start-Process -FilePath $AgentExe -WindowStyle Hidden
    Write-Host "Agent started as a standalone process (Process ID will not be tracked by Service Manager)." -ForegroundColor Yellow
    Write-Host "Note: It will stop if you reboot or close the session." -ForegroundColor Yellow
    
    # Skip Start-Service below and exit successfully
    exit 0
}


# 6. Start Service
try {
    Start-Service $ServiceName
    Write-Host "Agent installed and started successfully!" -ForegroundColor Green
}
catch {
    Write-Warning "Failed to start service: $_"
    Write-Warning "Falling back to standalone process..."
    
    # Fallback: Start as background job
    Start-Process -FilePath $AgentExe -WindowStyle Hidden
    Write-Host "Agent started as a standalone process (Process ID will not be tracked by Service Manager)." -ForegroundColor Yellow
    Write-Host "Note: It will stop if you reboot or close the session." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n✅ Omni-Agent AI has been installed and REGISTERED successfully!"
Write-Host "   Check the 'Agents' dashboard to see your new agent."
