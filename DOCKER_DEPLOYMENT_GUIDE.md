# Docker Deployment Guide

## Quick Start with Docker Compose

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+

### Deploy Everything with One Command

```bash
# Development mode
docker-compose up -d

# With agent
docker-compose --profile agent up -d

# Production mode with Nginx
docker-compose --profile production up -d
```

## Installation Steps

### 1. Install Docker (Ubuntu)

```bash
# Update package index
sudo apt-get update

# Install dependencies
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit configuration
nano .env
```

**Required variables in `.env`:**
```env
# JWT Secrets (generate with: openssl rand -hex 32)
JWT_SECRET_KEY=your-secret-key-here
JWT_REFRESH_SECRET_KEY=your-refresh-secret-here

# Gemini API Key (optional, for AI features)
GEMINI_API_KEY=your-gemini-api-key

# Agent Configuration (if using agent profile)
AGENT_TOKEN=your-agent-token
TENANT_ID=your-tenant-id
```

### 3. Build and Start

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. Initialize Database

```bash
# Seed compliance data
docker-compose exec backend python seed_compliance.py

# Verify
docker-compose exec mongodb mongosh omni_platform --eval "db.compliance_frameworks.countDocuments()"
```

### 5. Access Platform

```
Frontend: http://localhost:3000
Backend:  http://localhost:5000
MongoDB:  localhost:27017
```

## Service Management

### Start/Stop Services

```bash
# Start all
docker-compose up -d

# Start specific service
docker-compose up -d backend

# Stop all
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f mongodb

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Execute Commands in Containers

```bash
# Access backend shell
docker-compose exec backend bash

# Access MongoDB shell
docker-compose exec mongodb mongosh omni_platform

# Run Python script in backend
docker-compose exec backend python seed_compliance.py

# Check backend health
docker-compose exec backend curl http://localhost:5000/health
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend
docker-compose restart frontend
```

## Using Profiles

### Agent Profile

Start the monitoring agent:

```bash
docker-compose --profile agent up -d
```

Configure agent in `.env`:
```env
AGENT_TOKEN=your-token
TENANT_ID=your-tenant-id
```

### Production Profile

Start with Nginx reverse proxy:

```bash
docker-compose --profile production up -d
```

This includes:
- Nginx reverse proxy on ports 80/443
- SSL termination (configure in `nginx/ssl/`)
- Production-ready configuration

## Data Persistence

### Volumes

Docker Compose creates persistent volumes:
- `mongodb_data` - Database files
- `mongodb_config` - MongoDB configuration
- `backend_logs` - Backend application logs
- `agent_logs` - Agent logs
- `nginx_logs` - Nginx access/error logs

### Backup Data

```bash
# Backup MongoDB
docker-compose exec mongodb mongodump --out /data/backup
docker cp omni-mongodb:/data/backup ./mongodb-backup-$(date +%Y%m%d)

# Backup volumes
docker run --rm -v omni-platform_mongodb_data:/data -v $(pwd):/backup alpine tar czf /backup/mongodb-data-$(date +%Y%m%d).tar.gz /data
```

### Restore Data

```bash
# Restore MongoDB
docker cp ./mongodb-backup omni-mongodb:/data/restore
docker-compose exec mongodb mongorestore /data/restore

# Restore volume
docker run --rm -v omni-platform_mongodb_data:/data -v $(pwd):/backup alpine tar xzf /backup/mongodb-data.tar.gz -C /
```

## Updating

### Update Images

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose build --no-cache

# Restart services
docker-compose down
docker-compose up -d
```

### Update Dependencies

```bash
# Backend dependencies
docker-compose exec backend pip install -r requirements.txt --upgrade

# Frontend dependencies
docker-compose exec frontend npm update

# Restart services
docker-compose restart
```

## Scaling

### Scale Services

```bash
# Scale backend to 3 instances
docker-compose up -d --scale backend=3

# Scale with load balancer (requires nginx profile)
docker-compose --profile production up -d --scale backend=3
```

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Check specific service  
docker-compose logs backend

# Verify network
docker network ls
docker network inspect omni-platform_omni-network
```

### Database Connection Issues

```bash
# Check MongoDB status
docker-compose exec mongodb mongosh --eval "db.serverStatus()"

# Verify connectivity from backend
docker-compose exec backend python -c "from pymongo import MongoClient; print(MongoClient('mongodb://mongodb:27017/').admin.command('ping'))"

# Check MongoDB logs
docker-compose logs mongodb
```

### Port Conflicts

```bash
# Check what's using the port
sudo lsof -i :3000
sudo lsof -i :5000

# Change ports in docker-compose.yml
# Example: "8080:3000" instead of "3000:3000"
```

### Container Health

```bash
# Check health status
docker-compose ps

# Inspect container
docker inspect omni-backend
docker inspect omni-frontend

# View resource usage
docker stats
```

### Reset Everything

```bash
# Stop and remove everything
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Clean up system
docker system prune -a --volumes
```

## Production Deployment

### Nginx Configuration

Create `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:5000;
    }

    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;
        server_name your-domain.com;

        # Redirect to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        # Backend API
        location /api {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header Host $host;
        }
    }
}
```

### SSL Certificates

```bash
# Create directory
mkdir -p nginx/ssl

# Self-signed (development)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/ssl/key.pem \
    -out nginx/ssl/cert.pem

# Let's Encrypt (production)
# Use certbot in a separate container or on host
```

### Environment Variables

For production, use Docker secrets or external secret management:

```bash
# Using Docker secrets
echo "your-secret-key" | docker secret create jwt_secret -
echo "your-refresh-key" | docker secret create jwt_refresh_secret -
```

Update `docker-compose.yml` to use secrets:

```yaml
services:
  backend:
    secrets:
      - jwt_secret
      - jwt_refresh_secret
    environment:
      - JWT_SECRET_KEY_FILE=/run/secrets/jwt_secret

secrets:
  jwt_secret:
    external: true
  jwt_refresh_secret:
    external: true
```

## Monitoring

### Health Checks

```bash
# Check all services
curl http://localhost:5000/health
curl http://localhost:3000

# Container health
docker-compose ps
```

### Resource Monitoring

```bash
# Real-time stats
docker stats

# Logs
docker-compose logs -f --tail=100
```

### Database Monitoring

```bash
# MongoDB stats
docker-compose exec mongodb mongosh --eval "db.serverStatus()"

# Connection count
docker-compose exec mongodb mongosh --eval "db.serverStatus().connections"
```

## Best Practices

1. **Use `.env` file** - Never commit secrets to git
2. **Regular backups** - Backup MongoDB daily
3. **Update images** - Keep dependencies up to date
4. **Monitor logs** - Set up log aggregation
5. **Health checks** - Configure proper health checks
6. **Resource limits** - Set CPU/memory limits in production
7. **SSL/TLS** - Always use HTTPS in production
8. **Network security** - Use internal networks for services

## Quick Reference

```bash
# Start everything
docker-compose up -d

# View logs
docker-compose logs -f

# Stop everything
docker-compose down

# Backup database
docker-compose exec mongodb mongodump --out /data/backup

# Update and restart
docker-compose build && docker-compose up -d

# Clean everything
docker-compose down -v && docker system prune -a
```
