# Agent-Backend IP Connectivity Setup Guide

## Overview
This guide explains how to configure agents to connect to the backend server using its IP address instead of localhost, enabling remote agent deployment and monitoring.

## Backend Server IP Address
**IP Address:** `192.168.0.105`  
**Port:** `5000`  
**Full URL:** `http://192.168.0.105:5000`

## Configuration Steps

### 1. Update Agent Configuration
Edit the `agent/config.yaml` file on each agent machine:

```yaml
api_base_url: http://192.168.0.105:5000
```

**Location:** `agent/config.yaml`

### 2. Firewall Configuration

#### Windows Server (Backend)
Allow inbound connections on port 5000:

```powershell
# Add firewall rule for FastAPI backend
New-NetFirewallRule -DisplayName "Enterprise Omni Platform - Backend API" `
  -Direction Inbound `
  -LocalPort 5000 `
  -Protocol TCP `
  -Action Allow
```

#### Linux Server (Backend)
If using `ufw`:
```bash
sudo ufw allow 5000/tcp
sudo ufw reload
```

If using `firewalld`:
```bash
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

### 3. Backend Server Configuration
Ensure the backend is listening on all network interfaces (already configured in `app.py`):

```python
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",  # Listen on all interfaces
        port=5000,
        reload=True
    )
```

## Verification Steps

### 1. Test Backend Accessibility
From the agent machine, test connectivity to the backend:

```powershell
# Windows
Test-NetConnection -ComputerName 192.168.0.105 -Port 5000

# Or use curl
curl http://192.168.0.105:5000/health
```

Expected response:
```json
{"status": "healthy"}
```

### 2. Agent Connection Test
Start the agent and check logs for successful connection:

```powershell
cd agent
python main.py
```

Look for log messages indicating successful WebSocket connection and API communication.

### 3. Platform Verification
1. Log in to the platform at `http://localhost:3000`
2. Navigate to **Assets** view
3. Verify that the agent appears in the asset list
4. Check compliance data is being received

## Network Requirements

### Port Accessibility
- **Port 5000 (TCP):** HTTP API endpoints
- **Port 5000 (WebSocket):** Agent real-time communication

### Network Configuration
- Agents and backend must be on the same network or have routing configured
- No NAT/proxy restrictions between agents and backend
- Backend server firewall must allow inbound connections

## Troubleshooting

### Connection Refused
**Issue:** Agent cannot connect to backend  
**Solution:**
1. Verify backend is running: `curl http://192.168.0.105:5000/health`
2. Check firewall rules on backend server
3. Confirm IP address is correct: `ipconfig` (Windows) or `ip addr` (Linux)

### Authentication Failures
**Issue:** Agent connects but authentication fails  
**Solution:**
1. Verify `agent_token` in `config.yaml` is valid
2. Check token hasn't expired
3. Confirm `tenant_id` matches the backend database

### WebSocket Connection Issues
**Issue:** Agent connects to HTTP API but WebSocket fails  
**Solution:**
1. Ensure backend supports WebSocket upgrade on port 5000
2. Check for proxy/firewall blocking WebSocket connections
3. Verify `websocket_client.py` constructs correct WebSocket URL

## Multi-Agent Deployment

When deploying multiple agents:

1. **Same Configuration:** All agents use the same `api_base_url`
2. **Unique Tokens:** Each agent should have a unique `agent_token`
3. **Network Access:** All agents need network access to `192.168.0.105:5000`
4. **Monitoring:** Use the platform dashboard to monitor all connected agents

## Security Considerations

> [!WARNING]
> When exposing the backend on a network IP:
> - Ensure the network is trusted (internal corporate network)
> - Consider using HTTPS in production (requires SSL certificate)
> - Implement rate limiting for API endpoints
> - Monitor for unauthorized access attempts

## Production Deployment

For production environments:

1. **Use HTTPS:** Configure SSL/TLS certificates
2. **Domain Name:** Use a proper domain instead of IP address
3. **Load Balancing:** Consider load balancer for multiple backend instances
4. **VPN/Tunnel:** Use VPN for agents outside the corporate network

## Support

If you encounter issues:
1. Check backend logs: `backend/logs/`
2. Check agent logs on the agent machine
3. Verify network connectivity with `ping` and `Test-NetConnection`
4. Review this guide's troubleshooting section
