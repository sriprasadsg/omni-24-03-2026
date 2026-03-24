# Agent Installation Guide

## Quick Start

The `install-agent.ps1` PowerShell script automates the installation and configuration of the Enterprise Omni Platform agent on Windows systems.

## Prerequisites

- **Windows 10/11** or **Windows Server 2016+**
- **Python 3.8 or higher** ([Download](https://www.python.org/downloads/))
- **Administrator privileges**
- Network access to the backend server

## Installation Methods

### Method 1: Basic Installation (Recommended for Testing)

```powershell
# Run PowerShell as Administrator
.\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" `
                    -AgentToken "your-agent-token-here" `
                    -TenantId "your-tenant-id"
```

This installs the agent to `C:\Program Files\OmniAgent` and creates a startup script.

### Method 2: Install as Windows Service (Recommended for Production)

```powershell
# Run PowerShell as Administrator
.\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" `
                    -AgentToken "your-agent-token-here" `
                    -TenantId "your-tenant-id" `
                    -AsService
```

This installs the agent as a Windows service that starts automatically on system boot.

### Method 3: Custom Installation Path

```powershell
.\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" `
                    -AgentToken "your-agent-token-here" `
                    -TenantId "your-tenant-id" `
                    -InstallPath "D:\CustomPath\OmniAgent"
```

## Parameters

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `BackendUrl` | Yes | Backend server URL (e.g., `http://192.168.0.105:5000`) | N/A |
| `AgentToken` | Yes | Authentication token from platform | N/A |
| `TenantId` | Yes | Tenant ID from platform | N/A |
| `InstallPath` | No | Installation directory | `C:\Program Files\OmniAgent` |
| `AsService` | No | Install as Windows service | `false` |

## Getting Your Credentials

### 1. Obtain Agent Token

**Via Platform UI:**
1. Log in to the platform at `http://192.168.0.105:3000`
2. Navigate to **Agents** → **Register New Agent**
3. Copy the generated token

**Via API:**
```powershell
# Login to get access token
$loginResponse = Invoke-RestMethod -Method POST `
    -Uri "http://192.168.0.105:5000/api/auth/login" `
    -Body (@{email="admin@acmecorp.com"; password="Admin123!"} | ConvertTo-Json) `
    -ContentType "application/json"

$token = $loginResponse.access_token

# Generate agent token
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod -Method POST `
    -Uri "http://192.168.0.105:5000/api/agents/generate-token" `
    -Headers $headers
```

### 2. Find Your Tenant ID

Check your user profile in the platform or use:

```powershell
# After login
$currentUser = Invoke-RestMethod -Method GET `
    -Uri "http://192.168.0.105:5000/api/auth/me" `
    -Headers @{ Authorization = "Bearer $token" }

$tenantId = $currentUser.tenantId
```

## Post-Installation

### Verify Agent is Running

**If installed as service:**
```powershell
Get-Service OmniAgent
```

**If installed manually:**
```powershell
cd "C:\Program Files\OmniAgent"
.\start-agent.bat
```

### Check Agent Logs

```powershell
# Service logs
Get-Content "C:\Program Files\OmniAgent\logs\agent.log" -Tail 50

# Real-time monitoring
Get-Content "C:\Program Files\OmniAgent\logs\agent.log" -Wait
```

### Verify in Platform

1. Log in to the platform
2. Navigate to **Agents** view
3. Your agent should appear with status **Online**

## Managing the Agent Service

### Start/Stop/Restart

```powershell
# Start
Start-Service OmniAgent

# Stop
Stop-Service OmniAgent

# Restart
Restart-Service OmniAgent

# Check status
Get-Service OmniAgent | Select-Object Name, Status, StartType
```

### View Service Details

```powershell
Get-WmiObject Win32_Service | Where-Object {$_.Name -eq "OmniAgent"} | 
    Select-Object Name, State, StartMode, PathName
```

### Uninstall Service

```powershell
# Stop the service
Stop-Service OmniAgent

# Remove using NSSM
cd "C:\Program Files\OmniAgent"
.\nssm.exe remove OmniAgent confirm

# Or use sc.exe
sc.exe delete OmniAgent
```

## Troubleshooting

### Agent Won't Start

**Check Python:**
```powershell
python --version
# Should show: Python 3.8.x or higher
```

**Check dependencies:**
```powershell
cd "C:\Program Files\OmniAgent"
pip install -r requirements.txt
```

**Test manual start:**
```powershell
cd "C:\Program Files\OmniAgent"
python agent.py
# Watch for errors in output
```

### Can't Connect to Backend

**Test connectivity:**
```powershell
Test-NetConnection -ComputerName 192.168.0.105 -Port 5000
curl http://192.168.0.105:5000/health
```

**Check firewall:**
```powershell
# Add firewall rule if needed
New-NetFirewallRule -DisplayName "Omni Agent Outbound" `
    -Direction Outbound `
    -LocalPort Any `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress 192.168.0.105
```

**Verify config:**
```powershell
Get-Content "C:\Program Files\OmniAgent\config.yaml"
```

### Authentication Errors

**Regenerate token:**
1. Go to platform → **Agents** → **Settings**
2. Click **Generate New Token**
3. Update `config.yaml`:
   ```powershell
   notepad "C:\Program Files\OmniAgent\config.yaml"
   # Update agent_token line
   # Save and restart agent
   Restart-Service OmniAgent
   ```

### Permission Errors

**Run as Administrator:**
- Right-click PowerShell → "Run as Administrator"

**Check service account:**
```powershell
# Service should run as SYSTEM account
Get-WmiObject Win32_Service | Where-Object {$_.Name -eq "OmniAgent"} | 
    Select-Object StartName
```

## Updating the Agent

### Update via Script

```powershell
# Re-run installation (will prompt to overwrite)
.\install-agent.ps1 -BackendUrl "http://192.168.0.105:5000" `
                    -AgentToken "your-token" `
                    -TenantId "your-tenant-id" `
                    -AsService
```

### Manual Update

```powershell
# Stop agent
Stop-Service OmniAgent

# Backup current installation
Copy-Item "C:\Program Files\OmniAgent" "C:\Backup\OmniAgent_$(Get-Date -Format 'yyyyMMdd')" -Recurse

# Copy new agent files
Copy-Item ".\agent\*" "C:\Program Files\OmniAgent" -Recurse -Force

# Reinstall dependencies
cd "C:\Program Files\OmniAgent"
pip install -r requirements.txt --upgrade

# Start agent
Start-Service OmniAgent
```

## Uninstallation

### Complete Removal

```powershell
# Stop and remove service
Stop-Service OmniAgent -ErrorAction SilentlyContinue
.\nssm.exe remove OmniAgent confirm

# Remove scheduled task (if created)
Unregister-ScheduledTask -TaskName "OmniAgent" -Confirm:$false -ErrorAction SilentlyContinue

# Delete installation directory
Remove-Item "C:\Program Files\OmniAgent" -Recurse -Force

# Remove firewall rules (optional)
Remove-NetFirewallRule -DisplayName "Omni Agent*" -ErrorAction SilentlyContinue
```

## Advanced Configuration

### Configure Custom Checks

Edit compliance checks in:
```
C:\Program Files\OmniAgent\capabilities\compliance.py
```

Restart agent after changes:
```powershell
Restart-Service OmniAgent
```

### Adjust Logging Level

Edit `agent.py` and modify:
```python
logging.basicConfig(level=logging.DEBUG)  # Change to DEBUG, INFO, WARNING, ERROR
```

### Run Multiple Agents

Install to different directories:
```powershell
.\install-agent.ps1 -InstallPath "C:\OmniAgent1" -BackendUrl "..." -AgentToken "..." -TenantId "..."
.\install-agent.ps1 -InstallPath "C:\OmniAgent2" -BackendUrl "..." -AgentToken "..." -TenantId "..."
```

## Support

For issues or questions:
1. Check logs: `C:\Program Files\OmniAgent\logs\agent.log`
2. Review platform documentation
3. Contact your platform administrator
4. Refer to [AGENT_IP_CONNECTIVITY_GUIDE.md](./AGENT_IP_CONNECTIVITY_GUIDE.md) for network troubleshooting

## Security Best Practices

1. **Protect agent token**: Store securely, rotate regularly
2. **Use service account**: Run as dedicated low-privilege service account in production
3. **Enable TLS**: Use HTTPS for backend communication in production
4. **Audit logs**: Regularly review agent logs for anomalies
5. **Update frequently**: Keep agent software up to date
6. **Network segmentation**: Use firewall rules to restrict agent network access
