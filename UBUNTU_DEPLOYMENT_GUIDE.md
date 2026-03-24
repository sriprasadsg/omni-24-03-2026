# Enterprise Omni Platform - Ubuntu 24.04 Deployment Guide

Complete guide for deploying the Enterprise Omni Platform on Ubuntu 24.04 LTS.

## 📋 Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Manual Installation](#manual-installation)
- [Service Management](#service-management)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Production Setup](#production-setup)

---

## 🖥️ System Requirements

### Minimum Requirements
- **OS**: Ubuntu 24.04 LTS (64-bit)
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Disk**: 20 GB free space
- **Network**: Internet connection for initial setup

### Recommended for Production
- **CPU**: 4+ cores
- **RAM**: 8+ GB
- **Disk**: 50+ GB SSD
- **Network**: Static IP address

---

## 🚀 Quick Start

### Automated Deployment

```bash
# 1. Copy project to Ubuntu server
scp -r enterprise-omni-agent-ai-platform user@server:/home/user/

# 2. SSH into server
ssh user@server

# 3. Navigate to project
cd ~/enterprise-omni-agent-ai-platform

# 4. Make script executable
chmod +x deploy-ubuntu.sh

# 5. Run deployment script
sudo ./deploy-ubuntu.sh
```

The script will automatically:
- ✅ Install all dependencies (Python, Node.js, MongoDB)
- ✅ Set up virtual environments
- ✅ Install project dependencies
- ✅ Create systemd services
- ✅ Configure firewall
- ✅ Initialize database

### Start Services

```bash
# Start all services
sudo systemctl start omni-backend
sudo systemctl start omni-frontend
sudo systemctl start omni-agent    # Optional

# Enable auto-start on boot
sudo systemctl enable omni-backend omni-frontend

# Check status
sudo systemctl status omni-backend
sudo systemctl status omni-frontend
```

### Access the Platform

```bash
# Get server IP
hostname -I | awk '{print $1}'

# Access URLs:
# Frontend: http://YOUR_SERVER_IP:3000
# Backend:  http://YOUR_SERVER_IP:5000
```

---

## 📦 Manual Installation

### Step 1: System Update

```bash
sudo apt update
sudo apt upgrade -y
```

### Step 2: Install Python 3.11

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
python3 --version
```

### Step 3: Install Node.js 20.x

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
npm --version
```

### Step 4: Install MongoDB 7.0

```bash
# Import MongoDB GPG key
wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | sudo apt-key add -

# Add MongoDB repository
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

# Install MongoDB
sudo apt update
sudo apt install -y mongodb-org

# Start and enable MongoDB
sudo systemctl start mongod
sudo systemctl enable mongod
sudo systemctl status mongod
```

### Step 5: Setup Backend

```bash
cd ~/enterprise-omni-agent-ai-platform/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
nano .env
```

**Backend .env configuration:**
```env
MONGODB_URL=mongodb://localhost:27017/
DATABASE_NAME=omni_platform
JWT_SECRET_KEY=your-secret-key-here
JWT_REFRESH_SECRET_KEY=your-refresh-secret-here
GEMINI_API_KEY=your-gemini-api-key  # Optional
```

**Seed database:**
```bash
python seed_compliance.py
deactivate
```

### Step 6: Setup Frontend

```bash
cd ~/enterprise-omni-agent-ai-platform

# Install dependencies
npm install

# Build for production (optional)
npm run build
```

### Step 7: Create Systemd Services

**Backend Service** (`/etc/systemd/system/omni-backend.service`):
```ini
[Unit]
Description=Enterprise Omni Platform - Backend API
After=network.target mongod.service
Requires=mongod.service

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/enterprise-omni-agent-ai-platform/backend
Environment="PATH=/home/your-username/enterprise-omni-agent-ai-platform/backend/venv/bin"
ExecStart=/home/your-username/enterprise-omni-agent-ai-platform/backend/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Frontend Service** (`/etc/systemd/system/omni-frontend.service`):
```ini
[Unit]
Description=Enterprise Omni Platform - Frontend
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/enterprise-omni-agent-ai-platform
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/npm run dev -- --host 0.0.0.0 --port 3000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start services:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable omni-backend omni-frontend
sudo systemctl start omni-backend omni-frontend
```

### Step 8: Configure Firewall

```bash
sudo ufw enable
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 3000/tcp    # Frontend
sudo ufw allow 5000/tcp    # Backend
sudo ufw status
```

---

## 🔧 Service Management

### Basic Commands

```bash
# Start services
sudo systemctl start omni-backend
sudo systemctl start omni-frontend
sudo systemctl start omni-agent

# Stop services
sudo systemctl stop omni-backend
sudo systemctl stop omni-frontend
sudo systemctl stop omni-agent

# Restart services
sudo systemctl restart omni-backend
sudo systemctl restart omni-frontend

# Check status
sudo systemctl status omni-backend
sudo systemctl status omni-frontend

# View logs
sudo journalctl -u omni-backend -f
sudo journalctl -u omni-frontend -f
sudo journalctl -u omni-agent -f

# Enable auto-start
sudo systemctl enable omni-backend omni-frontend

# Disable auto-start
sudo systemctl disable omni-backend omni-frontend
```

### MongoDB Management

```bash
# Start/stop/restart
sudo systemctl start mongod
sudo systemctl stop mongod
sudo systemctl restart mongod

# Check status
sudo systemctl status mongod

# Access MongoDB shell
mongosh

# Backup database
mongodump --db omni_platform --out /backup/mongodb/

# Restore database
mongorestore --db omni_platform /backup/mongodb/omni_platform/
```

---

## ⚙️ Configuration

### Backend Configuration

**Edit `.env` file:**
```bash
cd ~/enterprise-omni-agent-ai-platform/backend
nano .env
```

**Available environment variables:**
```env
# Database
MONGODB_URL=mongodb://localhost:27017/
DATABASE_NAME=omni_platform

# Security
JWT_SECRET_KEY=your-secret-key
JWT_REFRESH_SECRET_KEY=your-refresh-secret
CORS_ORIGINS=http://localhost:3000,http://your-domain.com

# AI Features (Optional)
GEMINI_API_KEY=your-gemini-api-key

# Logging
LOG_LEVEL=INFO
```

**Restart after changes:**
```bash
sudo systemctl restart omni-backend
```

### Frontend Configuration

**Update API URL** (if backend is on different server):
```bash
cd ~/enterprise-omni-agent-ai-platform
nano services/apiService.ts
```

Change `API_BASE` to your backend URL:
```typescript
export const API_BASE = 'http://YOUR_BACKEND_IP:5000/api';
```

**Rebuild and restart:**
```bash
npm run build
sudo systemctl restart omni-frontend
```

### Agent Configuration

```bash
cd ~/enterprise-omni-agent-ai-platform/agent
nano config.yaml
```

```yaml
agent_token: your-agent-token
agentic_mode_enabled: true
api_base_url: http://localhost:5000  # or remote backend
tenant_id: your-tenant-id
```

---

## 🐛 Troubleshooting

### Backend Won't Start

**Check logs:**
```bash
sudo journalctl -u omni-backend -n 50
```

**Common issues:**

1. **MongoDB not running:**
   ```bash
   sudo systemctl status mongod
   sudo systemctl start mongod
   ```

2. **Port already in use:**
   ```bash
   sudo lsof -i :5000
   # Kill process if needed
   sudo kill -9 <PID>
   ```

3. **Missing dependencies:**
   ```bash
   cd ~/enterprise-omni-agent-ai-platform/backend
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### Frontend Won't Start

**Check logs:**
```bash
sudo journalctl -u omni-frontend -n 50
```

**Common issues:**

1. **Port 3000 in use:**
   ```bash
   sudo lsof -i :3000
   sudo kill -9 <PID>
   ```

2. **Node modules missing:**
   ```bash
   cd ~/enterprise-omni-agent-ai-platform
   npm install
   ```

3. **Build errors:**
   ```bash
   npm run build
   # Check for errors
   ```

### MongoDB Issues

**Check MongoDB status:**
```bash
sudo systemctl status mongod
```

**Check MongoDB logs:**
```bash
sudo tail -f /var/log/mongodb/mongod.log
```

**Test connection:**
```bash
mongosh --eval "db.adminCommand('ping')"
```

### Network/Firewall Issues

**Check firewall status:**
```bash
sudo ufw status verbose
```

**Test port accessibility:**
```bash
# From another machine
curl http://YOUR_SERVER_IP:5000/health
curl http://YOUR_SERVER_IP:3000
```

**Check listening ports:**
```bash
sudo netstat -tulpn | grep LISTEN
```

---

## 🏭 Production Setup

### 1. Use Nginx as Reverse Proxy

**Install Nginx:**
```bash
sudo apt install -y nginx
```

**Configure Nginx** (`/etc/nginx/sites-available/omni-platform`):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
    }
}
```

**Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/omni-platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 2. Enable HTTPS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo systemctl restart nginx
```

### 3. Setup Automated Backups

**Create backup script** (`/usr/local/bin/backup-omni.sh`):
```bash
#!/bin/bash
BACKUP_DIR="/backup/omni-platform"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup MongoDB
mongodump --db omni_platform --out $BACKUP_DIR/mongodb_$DATE

# Backup files
tar -czf $BACKUP_DIR/files_$DATE.tar.gz \
    /home/user/enterprise-omni-agent-ai-platform/backend/.env \
    /home/user/enterprise-omni-agent-ai-platform/agent/config.yaml

# Keep only last 7 days
find $BACKUP_DIR -type f -mtime +7 -delete

echo "Backup completed: $DATE"
```

**Make executable and schedule:**
```bash
sudo chmod +x /usr/local/bin/backup-omni.sh
sudo crontab -e

# Add daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-omni.sh >> /var/log/omni-backup.log 2>&1
```

### 4. Monitoring

**Install and configure monitoring:**
```bash
# Install htop for system monitoring
sudo apt install -y htop

# Monitor services
watch -n 5 'systemctl status omni-backend omni-frontend'

# Monitor resources
htop
```

### 5. Security Hardening

```bash
# Update firewall to only allow necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Fail2ban for SSH protection
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## 📊 Performance Tuning

### MongoDB Optimization

```bash
# Edit MongoDB config
sudo nano /etc/mongod.conf
```

```yaml
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 2  # Adjust based on RAM
```

### Node.js Performance

**Increase file watch limit:**
```bash
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## 🔄 Updating the Platform

```bash
# Stop services
sudo systemctl stop omni-backend omni-frontend omni-agent

# Backup current installation
cd ~
cp -r enterprise-omni-agent-ai-platform enterprise-omni-agent-ai-platform.backup

# Pull updates (if using git)
cd ~/enterprise-omni-agent-ai-platform
git pull

# Update dependencies
cd backend
source venv/bin/activate
pip install -r requirements.txt --upgrade
deactivate

cd ..
npm install

# Restart services
sudo systemctl start omni-backend omni-frontend omni-agent
```

---

## 📝 Additional Resources

- [MongoDB Documentation](https://docs.mongodb.com/)
- [Node.js Best Practices](https://github.com/goldbergyoni/nodebestpractices)
- [Nginx Configuration](https://nginx.org/en/docs/)
- [Ubuntu Server Guide](https://ubuntu.com/server/docs)

---

## 🆘 Support

For issues or questions:
1. Check service logs: `sudo journalctl -u service-name -f`
2. Review MongoDB logs: `sudo tail -f /var/log/mongodb/mongod.log`
3. Check system resources: `htop`
4. Verify network connectivity: `sudo netstat -tulpn`
5. Review firewall rules: `sudo ufw status verbose`
