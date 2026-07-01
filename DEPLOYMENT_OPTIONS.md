# Deployment Options Summary

Enterprise Omni Platform supports multiple deployment methods. Choose based on your environment and requirements.

## 📦 Available Deployment Methods

### 1. **Docker Compose** (Recommended for Development)

**Best for:** Development, testing, quick demos

**Pros:**
- ✅ Fastest setup (single command)
- ✅ Isolated environment
- ✅ Easy to reset/rebuild
- ✅ Works on any OS (Windows, macOS, Linux)
- ✅ Automatic service dependencies

**Cons:**
- ❌ Requires Docker installed
- ❌ Slightly higher resource usage

**Quick Start:**
```bash
docker-compose up -d
```

📖 **Guide:** [DOCKER_DEPLOYMENT_GUIDE.md](./DOCKER_DEPLOYMENT_GUIDE.md)

---

### 2. **Ubuntu 24.04 Native** (Recommended for Production)

**Best for:** Production deployments, maximum performance

**Pros:**
- ✅ Native performance
- ✅ Direct system integration
- ✅ Systemd service management
- ✅ Lower resource overhead
- ✅ Easier debugging

**Cons:**
- ❌ Longer initial setup
- ❌ Ubuntu-specific
- ❌ Manual dependency management

**Quick Start:**
```bash
chmod +x deploy-ubuntu.sh
sudo ./deploy-ubuntu.sh
```

📖 **Guide:** [UBUNTU_DEPLOYMENT_GUIDE.md](./UBUNTU_DEPLOYMENT_GUIDE.md)

---

### 3. **Windows Server** (Native)

**Best for:** Windows environments, development on Windows

**Pros:**
- ✅ Native Windows integration
- ✅ Windows service support
- ✅ PowerShell automation

**Cons:**
- ❌ Manual setup required
- ❌ More complex dependency management

**Quick Start:**
```powershell
# Install Python, Node.js, MongoDB manually
# Then run:
.\start-all-services.bat
```

---

## 🎯 Deployment Decision Matrix

| Scenario | Recommended Method | Reason |
|----------|-------------------|--------|
| **Development** | Docker Compose | Fast setup, easy reset |
| **Testing/Staging** | Docker Compose or Ubuntu | Flexible, production-like |
| **Production (Linux)** | Ubuntu Native | Best performance, reliability |
| **Production (Windows)** | Windows Native or Docker | OS compatibility |
| **Quick Demo** | Docker Compose | Fastest deployment |
| **Multi-tenant Production** | Ubuntu + Nginx | Scalability, security |

---

## 📊 Comparison Table

| Feature | Docker Compose | Ubuntu Native | Windows Native |
|---------|---------------|---------------|----------------|
| **Setup Time** | 5 minutes | 10-15 minutes | 15-20 minutes |
| **Prerequisites** | Docker only | Multiple packages | Multiple packages |
| **Performance** | Good | Excellent | Good |
| **Isolation** | Excellent | Good | Good |
| **Service Management** | Docker CLI | Systemd | Windows Services |
| **Updates** | Rebuild images | Package managers | Manual updates |
| **Backup** | Volume backups | File/DB backups | File/DB backups |
| **Scaling** | Easy (docker-compose scale) | Manual | Manual |
| **SSL/HTTPS** | Nginx in container | Nginx + Certbot | IIS or manual |

---

## 🚀 Quick Commands Reference

### Docker Compose

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f

# Update
docker-compose build && docker-compose up -d
```

### Ubuntu Native

```bash
# Start services
sudo systemctl start omni-backend omni-frontend

# Stop services
sudo systemctl stop omni-backend omni-frontend

# View logs
sudo journalctl -u omni-backend -f

# Update
cd ~/enterprise-omni-agent-ai-platform && git pull
```

### Windows Native

```powershell
# Start services
.\start-all-services.bat

# Stop services
# Press Ctrl+C in each terminal

# View logs
Get-Content .\backend\logs\app.log -Tail 50 -Wait
```

---

## 🔧 Component Installation Guides

### Agent Installation

Choose based on OS:

- **Windows:** [install-agent.ps1](./install-agent.ps1) + [AGENT_INSTALLATION_README.md](./AGENT_INSTALLATION_README.md)
- **Linux:** [install-agent-linux.sh](./install-agent-linux.sh)
- **Docker:** Included in `docker-compose.yml` (use `--profile agent`)

### Database Setup

- **MongoDB Installation:** Included in all deployment scripts
- **Data Seeding:** Automatic in Docker, manual in native deployments

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                Load Balancer (Optional)          │
│                 Nginx / HAProxy                  │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐      ┌────────▼───────┐
│   Frontend     │      │   Backend API  │
│   React/Vite   │      │    FastAPI     │
│   Port 3000    │      │   Port 5000    │
└────────────────┘      └────────┬───────┘
                                 │
                        ┌────────▼────────┐
                        │   MongoDB 7.0   │
                        │  Port 27017     │
                        └─────────────────┘
                                 │
                    ┌────────────┴───────────┐
                    │                        │
            ┌───────▼────────┐     ┌────────▼────────┐
            │  Agent (Local) │     │ Agent (Remote)  │
            │   Monitoring   │     │   Monitoring    │
            └────────────────┘     └─────────────────┘
```

---

## 📝 Post-Deployment Checklist

### All Deployments

- [ ] Verify all services are running
- [ ] Test frontend access (default: http://localhost:3000)
- [ ] Test backend API (default: http://localhost:5000/health)
- [ ] Login with default credentials
- [ ] Change default passwords
- [ ] Configure environment variables (.env)
- [ ] Seed compliance frameworks
- [ ] Test agent connectivity (if using agents)

### Production Only

- [ ] Configure SSL/TLS certificates
- [ ] Set up Nginx reverse proxy
- [ ] Configure firewall rules
- [ ] Set up automated backups
- [ ] Configure monitoring/alerting
- [ ] Update DNS records
- [ ] Test disaster recovery procedure
- [ ] Document deployment specifics
- [ ] Set up log aggregation
- [ ] Configure security hardening

---

## 🆘 Getting Help

1. **Check logs** first (service-specific)
2. **Review** relevant deployment guide
3. **Search** troubleshooting sections
4. **Test** connectivity and prerequisites
5. **Verify** configuration files

---

## 📚 Complete Documentation Index

### Deployment Guides
- [DOCKER_DEPLOYMENT_GUIDE.md](./DOCKER_DEPLOYMENT_GUIDE.md) - Docker Compose deployment
- [UBUNTU_DEPLOYMENT_GUIDE.md](./UBUNTU_DEPLOYMENT_GUIDE.md) - Ubuntu 24.04 native
- [UBUNTU_QUICK_REFERENCE.md](./UBUNTU_QUICK_REFERENCE.md) - Quick commands

### Agent Installation
- [AGENT_INSTALLATION_README.md](./AGENT_INSTALLATION_README.md) - Windows agent
- [install-agent.ps1](./install-agent.ps1) - Windows installer script
- [install-agent-linux.sh](./install-agent-linux.sh) - Linux installer script

### Configuration
- [AGENT_IP_CONNECTIVITY_GUIDE.md](./AGENT_IP_CONNECTIVITY_GUIDE.md) - Network setup
- [.env.example](./.env.example) - Environment configuration template

### Feature Documentation
- [AGENT_COMPLIANCE_DASHBOARD_README.md](./AGENT_COMPLIANCE_DASHBOARD_README.md) - Compliance dashboard

---

**Last Updated:** 2026-01-08  
**Platform Version:** 1.0.0
