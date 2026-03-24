<#
.SYNOPSIS
    Enterprise Omni Platform - Agent Installation Script for Windows

.DESCRIPTION
    This script installs and configures the Enterprise Omni Platform agent on Windows systems.
    It checks prerequisites, installs dependencies, configures the agent, and optionally
    registers it as a Windows service.

.PARAMETER BackendUrl
    The URL of the backend server (e.g., http://192.168.0.105:5000)

.PARAMETER AgentToken
    The authentication token for the agent

.PARAMETER TenantId
    The tenant ID for the agent

.PARAMETER InstallPath
    Installation directory for the agent (default: C:\Program Files\OmniAgent)

.PARAMETER AsService
    If specified, installs the agent as a Windows service

.EXAMPLE
    .\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" -AgentToken "your-token" -TenantId "tenant-123"

.EXAMPLE
    .\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" -AgentToken "your-token" -TenantId "tenant-123" -AsService
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$BackendUrl,

    [Parameter(Mandatory = $true)]
    [string]$AgentToken,

    [Parameter(Mandatory = $true)]
    [string]$TenantId,

    [Parameter(Mandatory = $false)]
    [string]$InstallPath = "C:\Program Files\OmniAgent",

    [Parameter(Mandatory = $false)]
    [switch]$AsService
)

# Requires administrator privileges
#Requires -RunAsAdministrator

# Script configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Colors for output
function Write-ColorOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [Parameter(Mandatory = $false)]
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Success { param([string]$Message) Write-ColorOutput "✓ $Message" -Color Green }
function Write-Info { param([string]$Message) Write-ColorOutput "ℹ $Message" -Color Cyan }
function Write-Warning { param([string]$Message) Write-ColorOutput "⚠ $Message" -Color Yellow }
function Write-Error { param([string]$Message) Write-ColorOutput "✗ $Message" -Color Red }

# Banner
Clear-Host
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "    Enterprise Omni Platform - Agent Installer" -ForegroundColor White
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Prerequisites
Write-Info "Step 1/6: Checking prerequisites..."

# Check Python installation
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -ge 3 -and $minor -ge 8) {
            Write-Success "Python $($matches[0]) detected"
        }
        else {
            throw "Python 3.8 or higher required. Found: $pythonVersion"
        }
    }
    else {
        throw "Python not found in PATH"
    }
}
catch {
    Write-Error "Python 3.8+ is required but not found!"
    Write-Info "Please install Python from: https://www.python.org/downloads/"
    exit 1
}

# Check pip
try {
    pip --version | Out-Null
    Write-Success "pip detected"
}
catch {
    Write-Error "pip not found!"
    Write-Info "Please ensure pip is installed with Python"
    exit 1
}

# Check network connectivity to backend
Write-Info "Testing connectivity to backend: $BackendUrl"
try {
    $healthUrl = "$BackendUrl/health".TrimEnd('/') + "/health"
    $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Success "Backend is reachable"
    }
    else {
        Write-Warning "Backend returned status: $($response.StatusCode)"
    }
}
catch {
    Write-Warning "Could not reach backend at $BackendUrl"
    Write-Info "Installation will continue, but agent may not connect until backend is available"
}

# Step 2: Create installation directory
Write-Info "Step 2/6: Creating installation directory..."

if (Test-Path $InstallPath) {
    Write-Warning "Installation directory already exists: $InstallPath"
    $overwrite = Read-Host "Overwrite existing installation? (y/n)"
    if ($overwrite -ne 'y') {
        Write-Info "Installation cancelled by user"
        exit 0
    }
    Remove-Item -Path $InstallPath -Recurse -Force
}

New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
Write-Success "Created directory: $InstallPath"

# Step 3: Copy agent files
Write-Info "Step 3/6: Copying agent files..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentSourceDir = Join-Path $scriptDir "agent"

if (-not (Test-Path $agentSourceDir)) {
    Write-Error "Agent source directory not found: $agentSourceDir"
    Write-Info "Please ensure this script is run from the project root directory"
    exit 1
}

# Copy all agent files
Copy-Item -Path "$agentSourceDir\*" -Destination $InstallPath -Recurse -Force
Write-Success "Agent files copied to $InstallPath"

# Step 4: Configure agent
Write-Info "Step 4/6: Configuring agent..."

$configPath = Join-Path $InstallPath "config.yaml"
$configContent = @"
agent_token: $AgentToken
agentic_mode_enabled: true
api_base_url: $BackendUrl
tenant_id: $TenantId
"@

Set-Content -Path $configPath -Value $configContent -Force
Write-Success "Configuration written to $configPath"

# Step 5: Install Python dependencies
Write-Info "Step 5/6: Installing Python dependencies..."

$requirementsPath = Join-Path $InstallPath "requirements.txt"
if (Test-Path $requirementsPath) {
    try {
        & pip install -r $requirementsPath --quiet
        Write-Success "Python dependencies installed"
    }
    catch {
        Write-Error "Failed to install dependencies: $_"
        exit 1
    }
}
else {
    Write-Warning "requirements.txt not found, skipping dependency installation"
}

# Step 6: Configure agent startup
Write-Info "Step 6/6: Configuring agent startup..."

if ($AsService) {
    # Install as Windows Service using NSSM (Non-Sucking Service Manager)
    Write-Info "Installing agent as Windows service..."
    
    $serviceName = "OmniAgent"
    $pythonPath = (Get-Command python).Source
    $agentScript = Join-Path $InstallPath "agent.py"
    
    # Check if NSSM is available
    try {
        $nssmPath = (Get-Command nssm -ErrorAction Stop).Source
    }
    catch {
        Write-Warning "NSSM (Non-Sucking Service Manager) not found"
        Write-Info "Downloading NSSM..."
        
        $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
        $nssmZip = Join-Path $env:TEMP "nssm.zip"
        $nssmDir = Join-Path $env:TEMP "nssm"
        
        try {
            Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
            Expand-Archive -Path $nssmZip -DestinationPath $nssmDir -Force
            
            # Copy appropriate architecture
            if ([Environment]::Is64BitOperatingSystem) {
                $nssmExe = Join-Path $nssmDir "nssm-2.24\win64\nssm.exe"
            }
            else {
                $nssmExe = Join-Path $nssmDir "nssm-2.24\win32\nssm.exe"
            }
            
            Copy-Item -Path $nssmExe -Destination $InstallPath -Force
            $nssmPath = Join-Path $InstallPath "nssm.exe"
            Write-Success "NSSM downloaded"
        }
        catch {
            Write-Error "Failed to download NSSM: $_"
            Write-Info "You can manually install the service or run the agent directly"
            $AsService = $false
        }
    }
    
    if ($AsService) {
        # Remove existing service if it exists
        $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-Warning "Service $serviceName already exists, removing..."
            & $nssmPath stop $serviceName
            & $nssmPath remove $serviceName confirm
        }
        
        # Install new service
        & $nssmPath install $serviceName $pythonPath $agentScript
        & $nssmPath set $serviceName AppDirectory $InstallPath
        & $nssmPath set $serviceName DisplayName "Enterprise Omni Platform Agent"
        & $nssmPath set $serviceName Description "Security and compliance monitoring agent for Enterprise Omni Platform"
        & $nssmPath set $serviceName Start SERVICE_AUTO_START
        
        # Configure service recovery
        & $nssmPath set $serviceName AppStdout (Join-Path $InstallPath "logs\agent.log")
        & $nssmPath set $serviceName AppStderr (Join-Path $InstallPath "logs\agent-error.log")
        
        Write-Success "Service installed: $serviceName"
        
        # Start the service
        Write-Info "Starting agent service..."
        Start-Service -Name $serviceName
        Start-Sleep -Seconds 2
        
        $serviceStatus = Get-Service -Name $serviceName
        if ($serviceStatus.Status -eq 'Running') {
            Write-Success "Agent service is running"
        }
        else {
            Write-Warning "Agent service status: $($serviceStatus.Status)"
        }
    }
}
else {
    # Create startup batch file
    $startScriptPath = Join-Path $InstallPath "start-agent.bat"
    $startScriptContent = @"
@echo off
cd /d "%~dp0"
python agent.py
pause
"@
    Set-Content -Path $startScriptPath -Value $startScriptContent -Force
    Write-Success "Startup script created: $startScriptPath"
    
    # Create scheduled task for auto-start
    $createTask = Read-Host "Create scheduled task to auto-start agent on system boot? (y/n)"
    if ($createTask -eq 'y') {
        $taskName = "OmniAgent"
        
        # Remove existing task if it exists
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($existingTask) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
        
        $action = New-ScheduledTaskAction -Execute "python" -Argument "agent.py" -WorkingDirectory $InstallPath
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Enterprise Omni Platform Agent" | Out-Null
        Write-Success "Scheduled task created: $taskName"
    }
}

# Create logs directory
$logsDir = Join-Path $InstallPath "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

# Final summary
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "                Installation Complete!" -ForegroundColor White
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Success "Agent Location: $InstallPath"
Write-Success "Configuration: $configPath"
Write-Success "Backend URL: $BackendUrl"
Write-Success "Tenant ID: $TenantId"
Write-Host ""

if ($AsService) {
    Write-Info "Agent is running as a Windows service: OmniAgent"
    Write-Info "Control the service with:"
    Write-Host "  • Start:   " -NoNewline; Write-Host "Start-Service OmniAgent" -ForegroundColor Yellow
    Write-Host "  • Stop:    " -NoNewline; Write-Host "Stop-Service OmniAgent" -ForegroundColor Yellow
    Write-Host "  • Status:  " -NoNewline; Write-Host "Get-Service OmniAgent" -ForegroundColor Yellow
    Write-Host "  • Logs:    " -NoNewline; Write-Host "$logsDir" -ForegroundColor Yellow
}
else {
    Write-Info "To start the agent manually, run:"
    Write-Host "  $startScriptPath" -ForegroundColor Yellow
    Write-Host ""
    Write-Info "Or from PowerShell:"
    Write-Host "  cd '$InstallPath'" -ForegroundColor Yellow
    Write-Host "  python agent.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Info "Monitor agent status in the platform at: $BackendUrl"
Write-Host ""
Write-Success "Installation completed successfully!"
Write-Host ""
