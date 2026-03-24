# Enterprise Omni-Agent AI Platform - Setup Guide

Complete step-by-step guide to run the platform locally with full agent integration.

---

## 📋 Prerequisites

### Required Software
- **Node.js** (v18 or higher) - [Download](https://nodejs.org/)
- **Python** (v3.9 or higher) - [Download](https://www.python.org/)
- **MongoDB** (v5.0 or higher) - See installation options below

### Verify Installations
```powershell
node --version
npm --version
python --version
```

---

## 🗄️ Step 1: MongoDB Setup

Choose **ONE** of the following options:

### Option A: Docker (Recommended)
```powershell
# Start MongoDB container
docker run -d -p 27017:27017 --name omni-mongodb mongo:latest

# Verify it's running
docker ps | findstr mongo
```

### Option B: Windows Installation
1. Download MongoDB Community Server from [mongodb.com](https://www.mongodb.com/try/download/community)
2. Install and start the MongoDB service
3. Verify: `mongo --version`

### Option C: MongoDB Atlas (Cloud)
1. Create free cluster at [mongodb.com/atlas](https://www.mongodb.com/cloud/atlas)
2. Get connection string
3. Update `backend/.env`:
   ```
   MONGODB_URL=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/
   ```

---

## 🔧 Step 2: Backend Setup

```powershell
# Navigate to backend directory
cd d:\Downloads\enterprise-omni-agent-ai-platform\backend

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify .env configuration
# backend/.env should contain:
#   MONGODB_URL=mongodb://localhost:27017
#   MONGODB_DB_NAME=omni_platform

# Start the backend server
python -m uvicorn app:app --reload --port 5000
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:5000
INFO:     Application startup complete.
```

**Leave this terminal running** and open a new one for the next step.

---

## 🎨 Step 3: Frontend Setup

```powershell
# Navigate to project root (new terminal)
cd d:\Downloads\enterprise-omni-agent-ai-platform

# Install dependencies
npm install

# Start the development server
npm run dev
```

**Expected Output:**
```
VITE v6.4.1  ready in 791 ms
➜  Local:   http://localhost:3000/
```

**Leave this terminal running** and open a new one for the agent.

---

## 🤖 Step 4: Agent Installation & Configuration

### 4.1 Configure Agent

Edit `agent/config.yaml`:
```yaml
api_base_url: "http://localhost:5000"
tenant_id: "platform-admin"       # Use your tenant ID
agent_token: ""                   # Optional
interval_seconds: 30
```

### 4.2 Install Agent Dependencies

```powershell
# Navigate to agent directory (new terminal)
cd d:\Downloads\enterprise-omni-agent-ai-platform\agent

# Install dependencies
pip install -r requirements.txt
```

### 4.3 Start the Agent

```powershell
# Run the agent
python agent.py
```

**Expected Output:**
```
2025-12-05 14:00:00 - __main__ - INFO - Starting Omni Agent v2.0 with 30s interval
2025-12-05 14:00:00 - __main__ - INFO - Hostname: YOUR-COMPUTER-NAME
2025-12-05 14:00:00 - __main__ - INFO - Available capabilities: 10
2025-12-05 14:00:00 - __main__ - INFO - Heartbeat -> 200
```

---

## 🌐 Step 5: Access the Platform

1. **Open Browser:** Navigate to `http://localhost:3000`
2. **Login:** Use default credentials:
   - Email: `super@omni.ai`
   - Password: `password123`
3. **Verify Agent:** Navigate to **Observability → Agents** to see your local agent

---

## 🎯 Key Features

### ✅ Implemented Features

#### 1. **Real Vulnerability Scanning**
- Agent uses `pip list --outdated` to detect vulnerable packages
- Real-time CVE detection and reporting
- **Location:** `agent/capabilities/real_scan.py`

#### 2. **2030 Vision Dashboards**
- **Sustainability Dashboard** - Carbon footprint tracking
- **Zero Trust & Quantum Security** - Post-quantum cryptography readiness
- **Unified Future Ops** - AI-driven operations

#### 3. **Webhook Management**
- Create and manage webhooks for event notifications
- **Access:** Administration → Webhooks

#### 4. **Duplicate Prevention**
- Tenant names (company names) are unique
- User emails are unique
- Validation at both application and database level

#### 5. **Multi-Capability Agent**
The agent supports 10 capabilities:
- ✅ **Metrics Collection** - CPU, Memory, Disk
- ✅ **Log Collection** - System logs
- ✅ **File Integrity Monitoring (FIM)** - Critical file changes
- ✅ **Vulnerability Scanning** - Real CVE detection
- ✅ **Compliance Enforcement** - Policy checks
- ✅ **Runtime Security** - Process monitoring
- ✅ **Predictive Health** - Anomaly detection
- ✅ **UEBA** - User behavior analytics
- ✅ **SBOM Analysis** - Software bill of materials
- ✅ **eBPF Tracing** - Kernel-level monitoring

---

## 🔐 Step 6: Create New Tenant/User

### Via UI (Signup)
1. Click **"Create an account"** on login page
2. Fill in:
   - Company Name (must be unique)
   - Your Name
   - Email (must be unique)
   - Password (8+ chars, uppercase, lowercase)
3. Click **Sign Up**

### Via API
```powershell
curl -X POST http://localhost:5000/api/auth/signup `
  -H "Content-Type: application/json" `
  -d '{
    "companyName": "Acme Corp",
    "name": "John Doe",
    "email": "john@acme.com",
    "password": "SecurePass123!"
  }'
```

---

## 🛠️ Agent Installation on Remote Machines

### Windows
```powershell
# 1. Copy agent directory to remote machine
# 2. Edit config.yaml
api_base_url: "http://<BACKEND_IP>:5000"
tenant_id: "<YOUR_TENANT_ID>"

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run agent
python agent.py

# 5. (Optional) Run as Windows Service
# Use NSSM or Task Scheduler to run on startup
```

### Linux
```bash
# 1. Copy agent directory
# 2. Edit config.yaml
# 3. Install dependencies
pip3 install -r requirements.txt

# 4. Run agent
python3 agent.py

# 5. (Optional) Create systemd service
sudo nano /etc/systemd/system/omni-agent.service
```

Example systemd service:
```ini
[Unit]
Description=Omni Agent
After=network.target

[Service]
Type=simple
User=omni
WorkingDirectory=/opt/omni-agent
ExecStart=/usr/bin/python3 /opt/omni-agent/agent.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 📊 Finding Your Tenant ID

### Method 1: Via UI
1. Login as Super Admin
2. Navigate to **Administration → Tenant Management**
3. Click **View Tenant**
4. Copy the Tenant ID

### Method 2: Via MongoDB
```javascript
// Connect to MongoDB
mongo

// Switch to database
use omni_platform

// Find your tenant
db.tenants.find({ "name": "Your Company Name" })
```

### Method 3: Via Python Script
```python
# get_tenant_id.py
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['omni_platform']

# Find tenant by email
user = db.users.find_one({"email": "your@email.com"})
if user:
    print(f"Tenant ID: {user['tenantId']}")
```

---

## 🐛 Troubleshooting

### Backend Connection Lost
**Symptom:** Frontend shows "Backend connection lost"

**Solutions:**
1. Verify backend is running: `http://localhost:5000/health`
2. Check MongoDB is running: `mongosh` or `docker ps | findstr mongo`
3. Check `backend/.env` for correct MongoDB URL

### Agent Not Appearing
**Symptom:** No agents in dashboard

**Solutions:**
1. Verify agent is running and sending heartbeats
2. Check `agent/config.yaml` has correct `tenant_id`
3. Ensure backend and MongoDB are running
4. Check agent logs for errors

### Port Already in Use
**Symptom:** `Address already in use`

**Solutions:**
```powershell
# Find process using port 3000 (frontend)
netstat -ano | findstr :3000

# Find process using port 5000 (backend)
netstat -ano | findstr :5000

# Kill process by PID
taskkill /PID <PID> /F
```

### MongoDB Connection Failed
**Symptom:** Backend fails to start

**Solutions:**
1. Verify MongoDB is running: `mongosh` or `docker ps`
2. Check firewall isn't blocking port 27017
3. If using Docker, ensure container is running: `docker start omni-mongodb`

---

## 🚀 Production Deployment Checklist

- [ ] Change default passwords
- [ ] Set strong `agent_token` in production
- [ ] Use MongoDB replica set for high availability
- [ ] Configure HTTPS/TLS for backend API
- [ ] Set up reverse proxy (nginx) for frontend
- [ ] Configure firewall rules
- [ ] Enable MongoDB authentication
- [ ] Set up log rotation
- [ ] Configure backup strategy
- [ ] Update `MONGODB_URL` in `.env` to production database
- [ ] Set appropriate CORS origins in `backend/app.py`

---

## 📚 Additional Resources

### API Documentation
- **Health Check:** `GET http://localhost:5000/health`
- **Agents:** `GET http://localhost:5000/api/agents`
- **Vulnerabilities:** `GET http://localhost:5000/api/vulnerabilities`
- **Full API:** See `backend/app.py` for all endpoints

### Architecture
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│   MongoDB   │
│  React/Vite │     │   FastAPI   │     │   Database  │
│  Port 3000  │     │  Port 5000  │     │ Port 27017  │
└─────────────┘     └─────────────┘     └─────────────┘
                            ▲
                            │
                    ┌───────┴────────┐
                    │  Omni Agents   │
                    │  (Heartbeats)  │
                    └────────────────┘
```

---

## 📞 Support

For issues or questions:
1. Check logs in terminal windows
2. Review MongoDB logs: `docker logs omni-mongodb`
3. Examine agent logs for errors
4. Verify all services are running on correct ports

---

**Last Updated:** December 2025  
**Platform Version:** 2030.0  
**Agent Version:** 2.0.0
