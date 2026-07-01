# Technology Stack

**Analysis Date:** 2026-06-17

## Languages

**Primary:**
- TypeScript 5.7 - Frontend (React), configuration, type definitions
- Python 3.12-3.13 - Backend API, agent services, integrations
- Rust 2021 edition - Cross-platform agent binary (omni-agent)

**Secondary:**
- YAML - Agent configuration and docker-compose
- SQL - Database queries via SQLAlchemy/Motor

## Runtime

**Environment:**
- Node.js 24+ (frontend dev, build)
- Python 3.12-3.13 (backend, agents)
- Rust 2021 (agent binary compilation)

**Package Manager:**
- npm (Node.js dependencies)
- pip (Python dependencies with setuptools 70.0.0+, wheel 0.43.0+)
- Cargo (Rust dependencies)
- Lockfile: package-lock.json present, requirements.txt pinned versions

## Frameworks

**Core:**
- FastAPI 0.110.0+ - Backend web framework and API endpoints (`backend/app.py`)
- Uvicorn 0.28.0+ - ASGI server (runs on port 5000)
- React 19.2.0 - Frontend UI library
- Vite 8.0.14 - Frontend build tool and dev server (port 3000)

**Testing:**
- Vitest 3.2.4 - Frontend test runner
- Testing Library - React component testing (@testing-library/react 16.3.0)

**Build/Dev:**
- TailwindCSS 3.4.17 - CSS framework
- PostCSS 8.4.35 - CSS processing
- TypeScript ESLint 8.60.0 - Linting

## Key Dependencies

**Critical Infrastructure:**
- Motor 3.3.0+ - Async MongoDB driver (primary database client, `backend/database.py`)
- Redis 5.0.0+ - Caching, rate-limiting, session management, Celery broker (`backend/celery_app.py`)
- Celery 5.3.0+ - Distributed task queue with APScheduler 3.10.4 for cron scheduling

**Web & Real-time:**
- python-socketio 5.11.0+ - Socket.IO server for real-time dashboard updates (`backend/websocket_manager.py`)
- WebSockets 12.0+ - WebSocket protocol support
- Axios 1.13.2 - Frontend HTTP client
- socket.io-client 4.7.2 - Frontend WebSocket client

**AI & LLM Integration:**
- google-genai 0.3.0+ - Google Gemini SDK (proxied through backend, `backend/llm_proxy.py`)
- anthropic 0.28.0+ - Claude SDK for compliance oracle and analysis
- chromadb 0.5.0+ - Vector database for RAG and knowledge base retrieval

**Authentication & Security:**
- PyJWT 2.8.0+ - JWT token creation and verification (`backend/authentication_service.py`)
- bcrypt 4.0.0+ - Password hashing
- cryptography 46.0.0+ - Fernet encryption, TLS helpers (CVE-2026 fixed versions)
- Authlib 1.3.0+ - OAuth2, OIDC, SAML SSO flows
- pyotp 2.9.0 - TOTP/HOTP for MFA (RFC 6238)
- qrcode[pil] 7.4.2 - QR code generation for MFA enrollment
- defusedxml 0.7.1+ - Safe XML parsing (prevents XXE, used for SAML)
- Pillow 12.2.0+ - Image processing for QR/icons (CVE-2026 fixed)

**Data Validation:**
- Pydantic 2.5.0+ with email validation module (`backend/auth_types.py`, `backend/database.py`)
- pydantic-settings 2.2.0+ - Environment configuration

**Payment Gateways:**
- Stripe 9.0.0-11.x - Payment processing (`backend/payment_gateways/stripe_gateway.py`)
- PayPal REST SDK 1.13.1 - PayPal integration (`backend/payment_gateways/paypal_gateway.py`)
- Razorpay 1.4.1 - Indian payment provider (`backend/payment_gateways/razorpay_gateway.py`)
- Square 27.0.0+ - Square payment processing (`backend/payment_gateways/square_gateway.py`)

**Cloud & Infrastructure:**
- boto3 1.34.0+ - AWS SDK (S3, CloudWatch, CloudTrail) (`backend/secrets_service.py`)
- azure-mgmt-resource 23.0.1 - Azure Resource Manager
- azure-mgmt-network 25.0.0 - Azure networking APIs
- azure-mgmt-compute 30.0.0 - Azure compute operations
- google-cloud-compute 1.15.0 - GCP Compute Engine
- google-cloud-storage 2.14.0 - GCP Cloud Storage
- google-cloud-securitycenter 1.23.0 - GCP Security Command Center ingest (`backend/gcp_scc_ingest.py`)
- azure-monitor-query 1.2.0 - Microsoft Sentinel log queries (`backend/azure_defender_ingest.py`)

**Data Analysis & ML:**
- scikit-learn 1.3.0+ - Machine learning (UEBA, anomaly detection)
- pandas 2.1.0+ - Data manipulation and analysis
- numpy 1.24.0+ - Numerical operations
- joblib 1.3.0+ - Model persistence

**Network & Security Analysis:**
- python-nmap 0.7.1 - Network scanning wrapper
- psutil 5.9.0+ - System metrics (CPU, RAM, Disk, Network)
- pefile 2023.2.7 - PE header parsing (binary analysis)
- yara-python 4.3.0+ - Malware detection rules (optional, C extension)
- scapy 2.5.0+ - Network packet manipulation (optional)
- Mss 9.0.0+ - Screen capture (agent remote access)
- pystray 0.19.0 - System tray icon (agent UI)

**Reports & Documents:**
- ReportLab 4.0.0 - PDF generation for invoices
- openpyxl 3.1.0 - Excel report generation
- Jinja2 3.1.0 - HTML templating

**Rate Limiting & Observability:**
- slowapi 0.1.9 - FastAPI rate limiter (`backend/rate_limiter.py`)
- python-socketio logging - Event tracking via Socket.IO

**HTTP & Async Clients:**
- requests 2.28.0+ - Synchronous HTTP (LLM calls, webhooks)
- httpx 0.27.0+ - Async HTTP client
- aiohttp 3.9.0+ - Async HTTP sessions

**Rust Agent Dependencies:**
- tokio 1.x - Async runtime with full feature set
- reqwest 0.12+ - HTTP client
- serde/serde_json - Serialization (JSON)
- serde_yaml - YAML parsing
- sysinfo 0.32 - System information
- rusqlite 0.32 - SQLite database (bundled)
- tokio-tungstenite 0.23 - WebSocket client for agent comms
- sha2 0.10 - SHA-256 hashing
- chrono 0.4 - Date/time handling
- log/simplelog - Logging
- winreg 0.52 - Windows registry access (Windows only)
- windows-service 0.7 - Windows service integration (Windows only)

## Configuration

**Environment:**
- `.env` file - Environment variables (MongoDB URI, Redis URL, API keys)
- `agent/config.yaml` - Agent goals, integration settings, registration key
- `vite.config.ts` - Frontend dev server proxy config (proxies /api, /socket.io, /health to backend)
- `tsconfig.json` - TypeScript compiler options
- Vite HMR on port 24678 (separate from API proxy on 3000 to avoid Socket.IO conflicts)

**Build:**
- `vite.config.ts` - Defines proxy routes, chunk size warnings, test environment
- `tsconfig.json` - ES2022 target, React JSX preset, path alias @ for root
- Docker multi-stage Dockerfile (`backend/Dockerfile`) - Python 3.13 slim, non-root user omni

## Platform Requirements

**Development:**
- Node.js 24.x
- Python 3.12+ with build tools (gcc, libffi-dev, libssl-dev for native packages)
- Cargo/Rust 2021 edition (for agent binary compilation)
- MongoDB 8.0+ (local or containerized)
- Redis 8.0+ (local or containerized)

**Production:**
- Python 3.13-slim in Docker
- MongoDB 8.0+ (connection via MONGO_URI env var)
- Redis 8.0+ (connection via REDIS_URL env var)
- Deployment: Docker Compose or Kubernetes
- Frontend: Node 24-alpine or nginx (for built assets)

**Deployment Architecture:**
- Frontend: Vite dev server (dev) or nginx-served static build (prod)
- Backend: Uvicorn with 2 workers on port 5000
- Database: MongoDB (motor async driver, fallback mongomock)
- Cache/Queue: Redis (preferred) or MongoDB (fallback for Celery broker/backend)
- Monitoring: Health checks on /health endpoint (15s interval)

---

*Stack analysis: 2026-06-17*
