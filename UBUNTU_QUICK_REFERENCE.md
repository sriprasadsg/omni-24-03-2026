# Ubuntu 24.04 - Quick Deployment Reference

## 🚀 One-Command Deployment

```bash
# Copy to server
scp -r enterprise-omni-agent-ai-platform ubuntu@server:~/

# SSH and deploy
ssh ubuntu@server
cd ~/enterprise-omni-agent-ai-platform
chmod +x deploy-ubuntu.sh
sudo ./deploy-ubuntu.sh
```

## ⚡ Quick Commands

### Start Everything
```bash
sudo systemctl start omni-backend omni-frontend
sudo systemctl enable omni-backend omni-frontend
```

### Check Status
```bash
sudo systemctl status omni-backend
sudo systemctl status omni-frontend
sudo systemctl status mongod
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u omni-backend -f
sudo journalctl -u omni-frontend -f

# Last 50 lines
sudo journalctl -u omni-backend -n 50
```

### Access Platform
```bash
# Get server IP
hostname -I | awk '{print $1}'

# URLs:
# Frontend: http://YOUR_IP:3000
# Backend:  http://YOUR_IP:5000
```

## 🔧 Troubleshooting

### Services Won't Start
```bash
# Check what's using the port
sudo lsof -i :5000  # Backend
sudo lsof -i :3000  # Frontend

# MongoDB issues
sudo systemctl restart mongod
sudo journalctl -u mongod -n 50
```

### Reset Everything
```bash
sudo systemctl stop omni-backend omni-frontend omni-agent
cd ~/enterprise-omni-agent-ai-platform/backend
source venv/bin/activate
python seed_compliance.py
deactivate
sudo systemctl start omni-backend omni-frontend
```

## 🔐 Default Credentials

```
Email: super@omni.ai
Password: password123

OR

Email: admin@acmecorp.com
Password: Admin123!
```

## 📁 Important Paths

```
Project:     ~/enterprise-omni-agent-ai-platform
Backend:     ~/enterprise-omni-agent-ai-platform/backend
Config:      ~/enterprise-omni-agent-ai-platform/backend/.env
MongoDB:     /var/lib/mongodb
Logs:        /var/log/mongodb/mongod.log
Services:    /etc/systemd/system/omni-*.service
```

## 🌐 Firewall

```bash
sudo ufw allow 3000/tcp  # Frontend
sudo ufw allow 5000/tcp  # Backend
sudo ufw allow 22/tcp    # SSH
sudo ufw enable
```

## 📊 Monitoring

```bash
# System resources
htop

# MongoDB
mongosh --eval "db.serverStatus()"

# Check all services
systemctl list-units --state=running | grep omni
```

## 🔄 Update Platform

```bash
sudo systemctl stop omni-backend omni-frontend
cd ~/enterprise-omni-agent-ai-platform
git pull  # or rsync new files
cd backend && source venv/bin/activate && pip install -r requirements.txt && deactivate
cd .. && npm install
sudo systemctl start omni-backend omni-frontend
```

## 🛑 Complete Uninstall

```bash
sudo systemctl stop omni-backend omni-frontend omni-agent mongod
sudo systemctl disable omni-backend omni-frontend omni-agent
sudo rm /etc/systemd/system/omni-*.service
sudo systemctl daemon-reload
sudo apt remove -y mongodb-org
rm -rf ~/enterprise-omni-agent-ai-platform
```
