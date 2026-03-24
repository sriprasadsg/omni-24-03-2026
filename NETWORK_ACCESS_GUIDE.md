# Network Access Configuration Guide

## Quick Start

Run this command to start all services with network access:

```powershell
.\start-network.ps1
```

Or for quick start:
```powershell
.\quick-start-network.ps1
```

---

## Current Network Configuration

**Your Server IP:** `192.168.90.68`

### Services

| Service | Address | Access |
|---------|---------|--------|
| **Frontend** | `http://192.168.90.68:3000` | Web UI |
| **Backend** | `http://192.168.90.68:5000` | REST API |
| **API Docs** | `http://192.168.90.68:5000/docs` | Swagger UI |

### Service Bindings

All services are configured to accept connections from any IP:

1. **Backend:** Binds to `0.0.0.0:5000`
   - File: `backend/app.py:913`
   - Code: `uvicorn.run(app, host="0.0.0.0", port=5000)`

2. **Frontend:** Binds to `0.0.0.0:3000`
   - File: `vite.config.ts:10`
   - Code: `host: '0.0.0.0'`

3. **Agent Config:** Uses server IP
   - File: `agent/config.yaml:3`
   - Code: `api_base_url: http://192.168.90.68:5000`

---

## Windows Firewall Configuration

### Automatic (Recommended)

Run the startup script as Administrator:
```powershell
# Right-click on PowerShell → Run as Administrator
.\start-network.ps1
```

The script will automatically create firewall rules.

### Manual Configuration

If you need to manually configure the firewall:

```powershell
# Allow Frontend (port 3000)
New-NetFirewallRule -DisplayName "Omni Platform Frontend" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow

# Allow Backend (port 5000)
New-NetFirewallRule -DisplayName "Omni Platform Backend" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

### Verify Firewall Rules

```powershell
Get-NetFirewallRule -DisplayName "*Omni*"
```

---

## Access from Other Devices

### Same Network

Any device on the same Wi-Fi/LAN can access the platform:

1. **From Windows/Mac/Linux:**
   ```
   http://192.168.90.68:3000
   ```

2. **From Mobile:**
   - Open browser
   - Navigate to: `http://192.168.90.68:3000`

3. **From Another Agent Machine:**
   - Update `agent/config.yaml`:
   ```yaml
   api_base_url: http://192.168.90.68:5000
   ```

### Login Credentials

```
Super Admin:  super@omni.ai          / Admin123!
Test Admin:   admin@sriprasad.com    / Admin123!
Tenant Admin: admin@acmecorp.com     / Admin123!
```

---

## Agent Installation on Remote Machines

### Windows Agent

1. **Download agent files to remote machine**

2. **Create `config.yaml`:**
```yaml
agent_token: <your-token-from-signup>
agentic_mode_enabled: true
api_base_url: http://192.168.90.68:5000
tenant_id: <your-tenant-id>
```

3. **Run agent:**
```powershell
python agent.py
```

### Linux Agent

1. **Download agent files**

2. **Create `config.yaml`:**
```yaml
agent_token: <your-token>
agentic_mode_enabled: true
api_base_url: http://192.168.90.68:5000
tenant_id: <your-tenant-id>
```

3. **Run agent:**
```bash
python3 agent.py
```

---

## Troubleshooting

### Cannot Access from Other Devices

**Check Firewall:**
```powershell
# Disable firewall temporarily to test (re-enable after)
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False

# Test access, then re-enable
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
```

**Check if services are listening:**
```powershell
netstat -ano | findstr ":3000"
netstat -ano | findstr ":5000"
```

**Verify IP address:**
```powershell
ipconfig
# Look for "IPv4 Address" (should be 192.168.90.68)
```

### Agent Cannot Connect

**Test backend connectivity from agent machine:**
```powershell
# Test from remote machine
curl http://192.168.90.68:5000/health
```

**Expected response:**
```json
{"status":"ok","service":"backend-fastapi","edition":"2030"}
```

### Wrong IP Address

If your IP changed, update the agent config:

```powershell
# Get current IP
$IP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"}).IPAddress | Select-Object -First 1
Write-Host "Current IP: $IP"

# Update agent config
(Get-Content agent\config.yaml) -replace 'http://[0-9.]+:5000', "http://$IP:5000" | Set-Content agent\config.yaml
```

---

## Network Security Notes

### Current Setup
- ✅ Services accessible on local network (192.168.x.x)
- ❌ NOT accessible from internet (good for security)
- ✅ Firewall protects against external access

### Production Deployment

For internet access, you would need:
1. Port forwarding on your router (3000, 5000)
2. HTTPS/TLS certificates
3. Reverse proxy (nginx/Apache)
4. VPN or SSH tunnel (more secure)

**Recommendation:** Keep on local network for development/testing.

---

## Quick Reference

### Start Everything
```powershell
.\start-network.ps1
```

### Access URLs
```
Frontend: http://192.168.90.68:3000
Backend:  http://192.168.90.68:5000
```

### Stop Everything
Press `Ctrl+C` in each PowerShell window

---

## MongoDB Configuration (Optional)

If MongoDB needs network access:

```powershell
# Edit MongoDB config (typically C:\Program Files\MongoDB\Server\x.x\bin\mongod.cfg)
# Change bindIp from 127.0.0.1 to 0.0.0.0

# Restart MongoDB
net stop MongoDB
net start MongoDB
```

**Note:** MongoDB network access is NOT required for normal operation. The backend, frontend, and agents can all access MongoDB locally on the server.

---

## Status Check

To verify all services are accessible:

```powershell
# From server or any network device
curl http://192.168.90.68:5000/health
curl http://192.168.90.68:3000
```

Both should return successful responses.
