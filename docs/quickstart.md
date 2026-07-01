# Quickstart — Local Development

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker | 24+ | https://docs.docker.com/get-docker/ |
| Docker Compose | v2 | included with Docker Desktop |
| Node.js | 24+ | https://nodejs.org/ |
| Python | 3.13+ | https://python.org/ |
| Git | any | https://git-scm.com/ |

---

## 1. Clone and configure

```bash
git clone <repo-url>
cd enterprise-omni-agent-ai-platform
```

### Generate secrets

```bash
# JWT signing key (required)
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(64))"

# MongoDB root password (required)
python -c "import secrets; print('MONGO_ROOT_PASSWORD=' + secrets.token_urlsafe(32))"

# Redis password (required)
python -c "import secrets; print('REDIS_PASSWORD=' + secrets.token_urlsafe(32))"

# Email encryption key (required if using SMTP features)
python -c "from cryptography.fernet import Fernet; print('EMAIL_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Super admin password (set something strong)
echo "SUPER_ADMIN_PASSWORD=<your-password>"
```

### Create .env file

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and fill in the values generated above
```

Minimum required values in `backend/.env`:
```env
JWT_SECRET_KEY=<generated>
MONGO_ROOT_PASSWORD=<generated>
REDIS_PASSWORD=<generated>
SUPER_ADMIN_PASSWORD=<your-password>
EMAIL_ENCRYPTION_KEY=<generated>   # optional if not using SMTP
```

---

## 2. Start services

```bash
# Start MongoDB, Redis, Backend (FastAPI), and Frontend (Vite dev server)
docker compose up

# Or run detached:
docker compose up -d
```

Wait for the health checks to pass (about 30 seconds):
```
omniagent-mongo    | Ready
omniagent-backend  | Application startup complete
omniagent-frontend | vite dev server running
```

---

## 3. Access the platform

| Service | URL | Notes |
|---------|-----|-------|
| **Frontend** | http://localhost:3000 | Main UI |
| **Backend API** | http://localhost:5000 | FastAPI |
| **API Docs** | http://localhost:5000/docs | Swagger UI |
| **MongoDB** | localhost:27017 | Dev only (localhost-bound) |
| **Redis** | localhost:6379 | Dev only |

### First login

The platform seeds a super admin on first startup:
- **Email:** `super@omni.ai`
- **Password:** the value of `SUPER_ADMIN_PASSWORD` in your `.env`

---

## 4. Seed demo data (optional)

```bash
docker compose --profile seed up seeder
```

This populates the database with demo agents, assets, vulnerabilities, and compliance data.

---

## 5. Development workflow

### Backend (hot reload)
```bash
cd backend
pip install -r requirements.txt
uvicorn app:socket_app --reload --port 5000
```

### Frontend (Vite HMR)
```bash
npm install
npm run dev   # http://localhost:3000
```

### Run tests
```bash
# Backend
cd backend
pytest tests/ --tb=short -q --cov=. --cov-report=term-missing

# Frontend
npm test
```

### Lint
```bash
# Python
cd backend && ruff check .

# TypeScript
npx eslint . --max-warnings 0
npx tsc --noEmit
```

---

## 6. Production deployment

```bash
# Build and start production stack (nginx serving built frontend)
docker compose --profile production up -d
```

See [DEPLOYMENT_README.md](../DEPLOYMENT_README.md) for Kubernetes/Helm deployment.

---

## Troubleshooting

**Backend fails to start:**
- Check `backend/.env` has all required variables
- Run `docker compose logs backend` for error details
- In production: ensure `SUPER_ADMIN_PASSWORD` does not start with `changeme_`

**MongoDB connection refused:**
- Ensure `MONGO_ROOT_PASSWORD` matches in both `.env` and `docker-compose.yml`
- Check `docker compose ps` — mongo health check must be passing

**Frontend can't reach backend:**
- Verify `VITE_API_BASE_URL=http://localhost:5000` in `.env`
- Check backend health: `curl http://localhost:5000/health`
