# Enterprise Omni Platform - Complete Deployment Package

## 🎯 Overview

The Enterprise Omni Platform now includes complete deployment solutions for:
- ✅ **Docker Compose** - Containerized deployment
- ✅ **Ubuntu 24.04** - Native Linux deployment  
- ✅ **Windows** - Native Windows deployment
- ✅ **Agents** - Windows & Linux monitoring agents

---

## 📦 What's New

### Recently Added (January 2026)

1. **Compliance Evidence Integration**
   - React UI now displays captured compliance evidence
   - Markdown viewer with expand/collapse functionality
   - Copy to clipboard and download features

2. **Complete Ubuntu Deployment**
   - Automated installation script (`deploy-ubuntu.sh`)
   - Systemd service configuration
   - Comprehensive deployment guide

3. **Docker Deployment**  
   - Full `docker-compose.yml` configuration
   - Multi-service orchestration
   - Production-ready with Nginx profile

4. **Agent Installation Scripts**
   - Windows PowerShell installer (`install-agent.ps1`)
   - Linux Bash installer (`install-agent-linux.sh`)
   - Automated configuration and service setup

5. **Bug Fixes**
   - Fixed duplicate agent keys React warning
   - Improved agent deduplication logic

---

## 🚀 Quick Start

### Option 1: Docker Compose (Fastest)

```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Add your JWT secrets and API keys

# 2. Start everything
docker-compose up -d

# 3. Initialize database
docker-compose exec backend python seed_compliance.py

# 4. Access platform
# Frontend: http://localhost:3000
# Backend:  http://localhost:5000
```

### Option 2: Ubuntu 24.04 (Production)

```bash
#1. Copy to server
scp -r enterprise-omni-agent-ai-platform ubuntu@server:~/

# 2. SSH and deploy
ssh ubuntu@server
cd ~/enterprise-omni-agent-ai-platform
chmod +x deploy-ubuntu.sh
sudo ./deploy-ubuntu.sh

# 3. Start services
sudo systemctl start omni-backend omni-frontend
sudo systemctl enable omni-backend omni-frontend
```

### Option 3: Windows (Development)

```powershell
# 1. Install prerequisites
# - Python 3.11+
# - Node.js 20+
# - MongoDB 7.0

# 2. Start all services
.\start-all-services.bat
```

---

## 📂 File Structure

```
enterprise-omni-agent-ai-platform/
├── backend/                      # FastAPI backend
│   ├── app.py                   # Main application
│   ├── Dockerfile               # Backend Docker image
│   ├── requirements.txt         # Python dependencies
│   └── .env                     # Environment config
├── agent/                        # Monitoring agent
│   ├── agent.py                 # Agent application
│   ├── Dockerfile               # Agent Docker image
│   ├── config.yaml              # Agent configuration
│   └── requirements.txt         # Agent dependencies
├── components/                   # React components
│   ├── EvidenceMarkdownViewer.tsx  # NEW: Evidence viewer
│   └── AssetComplianceList.tsx     # Updated for evidence
│
├── DEPLOYMENT SCRIPTS
├── deploy-ubuntu.sh             # Ubuntu automated installer
├── install-agent.ps1            # Windows agent installer
├── install-agent-linux.sh       # Linux agent installer
├── docker-compose.yml           # Docker orchestration
│
├── DEPLOYMENT GUIDES
├── DEPLOYMENT_OPTIONS.md        # Deployment comparison
├── DOCKER_DEPLOYMENT_GUIDE.md   # Docker instructions
├── UBUNTU_DEPLOYMENT_GUIDE.md   # Ubuntu instructions
├── UBUNTU_QUICK_REFERENCE.md    # Ubuntu quick commands
├── AGENT_INSTALLATION_README.md # Agent setup guide
├── AGENT_IP_CONNECTIVITY_GUIDE.md # Network configuration
│
├── CONFIGURATION
├── .env.example                 # Environment template
└── Dockerfile.frontend          # Frontend Docker image
```

---

## 📖 Documentation Index

### Deployment Guides

| Guide | Purpose | Audience |
|-------|---------|----------|
| [DEPLOYMENT_OPTIONS.md](./DEPLOYMENT_OPTIONS.md) | Compare all deployment methods | Everyone |
| [DOCKER_DEPLOYMENT_GUIDE.md](./DOCKER_DEPLOYMENT_GUIDE.md) | Docker Compose setup | DevOps, Developers |
| [UBUNTU_DEPLOYMENT_GUIDE.md](./UBUNTU_DEPLOYMENT_GUIDE.md) | Ubuntu 24.04 native deployment | System Administrators |
| [UBUNTU_QUICK_REFERENCE.md](./UBUNTU_QUICK_REFERENCE.md) | Quick Ubuntu commands | System Administrators |

### Agent Documentation

| Guide | Purpose | Audience |
|-------|---------|----------|
| [AGENT_INSTALLATION_README.md](./AGENT_INSTALLATION_README.md) | Windows agent installation | Windows Administrators |
| [install-agent.ps1](./install-agent.ps1) | Windows installer script | Windows Administrators |
| [install-agent-linux.sh](./install-agent-linux.sh) | Linux installer script | Linux Administrators |
| [AGENT_IP_CONNECTIVITY_GUIDE.md](./AGENT_IP_CONNECTIVITY_GUIDE.md) | NetworkConfiguration | Network Engineers |

### Feature Documentation

| Guide | Purpose | Audience |
|-------|---------|----------|
| [AGENT_COMPLIANCE_DASHBOARD_README.md](./AGENT_COMPLIANCE_DASHBOARD_README.md) | Compliance dashboard usage | Compliance Officers |

---

## 🔐 Default Credentials

```
Super Admin:
  Email: super@omni.ai
  Password: password123

Tenant Admin (ACME Corp):
  Email: admin@acmecorp.com
  Password: Admin123!

Tenant Admin (Exafluence):
  Email: admin@exafluence.com
  Password: Admin123!
```

**⚠️ Change these passwords immediately in production!**

---

## 🌐 Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | React application |
| Backend | 5000 | FastAPI REST API |
| MongoDB | 27017 | Database |
| Nginx | 80/443 | Reverse proxy (production) |

---

## 🛠️ Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.11)
- **Database:** MongoDB 7.0
- **Authentication:** JWT
- **AI:** Google Gemini API (optional)

### Frontend
- **Framework:** React 18 + TypeScript
- **Build Tool:** Vite
- **UI Library:** Custom with Tailwind CSS
- **State Management:** React Context

### Agent
- **Language:** Python 3.11
- **Communication:** WebSocket + REST API
- **OS Support:** Windows, Linux

### Infrastructure
- **Containerization:** Docker + Docker Compose
- **Service Management:** Systemd (Linux), Windows Services
- **Reverse Proxy:** Nginx
- **SSL/TLS:** Let's Encrypt / Self-signed

---

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example`):

```env
# Required
JWT_SECRET_KEY=your-secret-key
JWT_REFRESH_SECRET_KEY=your-refresh-key
MONGODB_URL=mongodb://localhost:27017/

# Optional
GEMINI_API_KEY=your-gemini-api-key
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

### Agent Configuration

`agent/config.yaml`:
```yaml
agent_token: your-agent-token
agentic_mode_enabled: true
api_base_url: http://192.168.0.105:5000
tenant_id: your-tenant-id
```

---

## 🧪 Testing

### Verify Deployment

**Docker:**
```bash
docker-compose ps
docker-compose logs
curl http://localhost:5000/health
```

**Ubuntu:**
```bash
sudo systemctl status omni-backend omni-frontend
curl http://localhost:5000/health
```

**Windows:**
```powershell
Get-Service OmniAgent
Invoke-WebRequest http://localhost:5000/health
```

### Access Platform

1. Open browser: `http://localhost:3000`
2. Login with default credentials
3. Navigate to **Compliance** tab
4. Verify compliance frameworks loaded
5. Check **Agents** tab for connected agents

---

## 📊 Feature Set

### Core Features
- ✅ Multi-tenant administration
- ✅ Role-based access control (RBAC)
- ✅ Compliance framework management (ISO 27001, SOC 2, etc.)
- ✅ Asset management and inventory
- ✅ Patch management
- ✅ Vulnerability scanning
- ✅ Security event monitoring
- ✅ Alert management

### Agent Features
- ✅ Automated compliance evidence capture
- ✅ System health monitoring
- ✅ Real-time status reporting
- ✅ Remote command execution
- ✅ Log collection

### AI Features (Optional - Requires Gemini API Key)
- ✅ AI-powered insights
- ✅ Intelligent threat analysis
- ✅ Automated remediation suggestions
- ✅ Compliance guidance

---

## 🔄 Updates & Maintenance

### Update Platform (Docker)

```bash
docker-compose down
git pull
docker-compose build --no-cache
docker-compose up -d
```

### Update Platform (Ubuntu)

```bash
sudo systemctl stop omni-backend omni-frontend
cd ~/enterprise-omni-agent-ai-platform
git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt && deactivate
cd .. && npm install
sudo systemctl start omni-backend omni-frontend
```

### Backup

**Docker:**
```bash
docker-compose exec mongodb mongodump --out /data/backup
docker cp omni-mongodb:/data/backup ./backup-$(date +%Y%m%d)
```

**Ubuntu:**
```bash
mongodump --db omni_platform --out ~/backup/mongodb-$(date +%Y%m%d)
tar -czf ~/backup/platform-$(date +%Y%m%d).tar.gz ~/enterprise-omni-agent-ai-platform
```

---

## 🐛 Troubleshooting

### Common Issues

**Services won't start:**
- Check logs: `docker-compose logs` or `sudo journalctl -u omni-backend -f`
- Verify ports aren't in use: `sudo lsof -i :5000`
- Check MongoDB is running: `sudo systemctl status mongod`

**Can't connect to backend:**
- Verify firewall rules
- Check backend health: `curl http://localhost:5000/health`
- Review backend logs

**Agent won't connect:**
- Verify `config.yaml` has correct `api_base_url`
- Check firewall allows port 5000
- Ensure agent token is valid

**No compliance frameworks:**
- Run: `docker-compose exec backend python seed_compliance.py`
- Or: `cd backend && source venv/bin/activate && python seed_compliance.py`

---

## 📞 Support & Contributing

### Getting Help
1. Check relevant deployment guide
2. Review troubleshooting sections
3. Search documentation
4. Check logs for errors

### Reporting Issues
Include:
- Deployment method (Docker/Ubuntu/Windows)
- Error logs
- Steps to reproduce
- Platform version

---

## 📄 License

Enterprise Omni Platform - Proprietary Software

---

## 🎉 Recent Improvements

### January 2026
- ✅ Complete Docker Compose deployment
- ✅ Ubuntu 24.04 automated deployment
- ✅ Agent installation scripts (Windows & Linux)
- ✅ Compliance evidence display in React UI
- ✅ Markdown evidence viewer component
- ✅ Fixed duplicate agent keys bug
- ✅ Comprehensive deployment documentation
- ✅ Quick reference guides

---

**Version:** 1.0.0  
**Last Updated:** 2026-01-08  
**Platform Status:** Production Ready ✅
