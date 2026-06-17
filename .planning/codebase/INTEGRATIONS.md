# External Integrations

**Analysis Date:** 2026-06-17

## APIs & External Services

**AI/LLM Providers:**
- Google Gemini / Google GenAI - LLM inference for agent reasoning
  - SDK/Client: google-genai 0.3.0+
  - Auth: GEMINI_API_KEY (environment variable)
  - Location: `backend/llm_proxy.py`, `backend/ai_service.py`, `backend/agent_logic_service.py`
  - Proxy Route: /api/ai-proxy/chat/completions (governance enforcement, input scanning)

- Anthropic Claude - Compliance oracle and policy analysis
  - SDK/Client: anthropic 0.28.0+
  - Auth: ANTHROPIC_API_KEY (environment variable, optional)
  - Location: `backend/compliance_oracle_service.py`, `backend/cissp_oracle_endpoints.py`

- Ollama (Open LLM) - Local/on-premises LLM fallback
  - Auth: None (HTTP endpoint)
  - Environment: OLLAMA_URL or auto-detected via `backend/local_ip.py`
  - Tenant-specific override: Stored in system_settings collection with key "llm"

**Cloud Security Platforms:**
- Azure Defender for Cloud - Security alert ingestion
  - SDK: azure-mgmt-security (Security Center client)
  - Auth: Client ID/Secret via ClientSecretCredential
  - Env Vars: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID
  - Location: `backend/azure_defender_ingest.py`, `backend/cloud_integrations_endpoints.py`
  - Polling: Via agent job, poll_interval_seconds from agent/config.yaml

- Microsoft Sentinel / Log Analytics - SIEM log query
  - SDK: azure-monitor-query (LogsQueryClient)
  - Auth: Same as Azure Defender (DefaultAzureCredential)
  - Env Vars: AZURE_WORKSPACE_ID
  - Location: `backend/azure_defender_ingest.py`

- Google Cloud Security Command Center (SCC) - GCP security findings
  - SDK: google-cloud-securitycenter
  - Auth: Service account JSON (gcp_scc_ingest.py:_make_scc_client)
  - Env Vars: GCP_SERVICE_ACCOUNT_JSON_PATH or config via agent/config.yaml
  - Location: `backend/gcp_scc_ingest.py`, `backend/cloud_integrations_endpoints.py`
  - Scope: https://www.googleapis.com/auth/cloud-platform

- AWS CloudTrail / CloudWatch - Cloud activity and metrics
  - SDK: boto3 1.34.0+
  - Auth: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
  - Location: `backend/secrets_service.py` (used for vault integration)

**Identity & Access:**
- Okta - OIDC/OAuth2 identity provider
  - SDK: Authlib 1.3.0+ (OIDC support)
  - Env Vars: OKTA_ORG_URL, OKTA_API_TOKEN
  - Location: `backend/soar_engine.py` (user management, group lookup)
  - Polling: poll_interval_seconds from agent/config.yaml (default 60s)

**Ticketing & Remediation (Optional):**
- Jira - Issue tracking and automation (commented in requirements.txt)
  - SDK: atlassian-python-api 3.41.0 (optional)
  - Location: If enabled, used for incident response workflows

- PagerDuty - Incident escalation (commented in requirements.txt)
  - SDK: pdpyras 4.5.1 (optional)

## Data Storage

**Databases:**
- MongoDB 8.0+
  - Connection: Motor async driver (motor 3.3.0+)
  - URI: MONGO_URI env var or mongodb://user:pass@mongo:27017/omniagent
  - Client: `backend/database.py` - TenantIsolatedCollection wrapper
  - Collections: ai_settings, security_events, celery_taskmeta, revoked_tokens, system_settings
  - Fallback: mongomock for testing (mongomock_motor)

- SQLite - Agent-local storage (Rust agent)
  - Client: rusqlite (bundled)
  - Location: Local agent filesystem

**File Storage:**
- Local filesystem only
  - Uploads: `/app/uploads` (mounted volume in Docker)
  - Reports: `/app/static/reports` (mounted volume in Docker)
  - Agent data: `/app/omni_data/` (agent state, local ML models)

**Caching & Queue:**
- Redis 8.0+
  - Connection: redis 5.0.0+ client
  - URI: REDIS_URL env var or redis://:password@redis:6379
  - Uses: Rate limiting (slowapi), Celery broker/backend, session cache
  - Fallback: MongoDB (if REDIS_URL not set, uses mongodb://localhost:27017/omni-agent-queue)
  - Location: `backend/celery_app.py`

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based authentication
  - Implementation: `backend/authentication_service.py`
  - Token Format: HS256/HS384/HS512 HMAC
  - Secret Key: JWT_SECRET_KEY env var (required for prod)
  - Expiry: ACCESS_TOKEN_EXPIRE_MINUTES (default 60, max 120 minutes)
  - Refresh Tokens: 7-day expiry
  - JTI (JWT ID) Revocation: Cached in-process, synced from MongoDB revoked_tokens collection every 60s

**MFA Support:**
- TOTP/HOTP: pyotp 2.9.0, QR codes via qrcode[pil]
- Endpoints: `backend/authentication_service.py`

**SSO Support (Optional):**
- OAuth2 / OIDC: Authlib 1.3.0+ (OAuth2PasswordBearer in FastAPI)
- SAML: defusedxml 0.7.1+ (secure XML parsing for SAML assertions)

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry/Rollbar integration currently
- Local logging via Python logging module

**Logs:**
- Approach: Python logging to stdout/file
- Location: `/app/logs` (mounted volume in Docker)
- WebSocket Event Logs: Forwarded via Socket.IO to frontend dashboard
- Backend Health: GET /health endpoint (15s check interval)

**Distributed Tracing:**
- None detected - No OpenTelemetry, Jaeger, or Zipkin integration
- Request context tracking via tenant_id (multi-tenant isolation)

**Metrics & Monitoring:**
- APScheduler 3.10.4 - Cron job scheduling (patch scans, FinOps tasks)
- Location: `backend/celery_app.py` beat_schedule config

## CI/CD & Deployment

**Hosting:**
- Docker Compose (development & single-instance production)
- Kubernetes-ready (multi-container orchestration)
- Frontend: Node 24-alpine or nginx for built assets
- Backend: Python 3.13-slim (multi-stage Docker build)

**CI Pipeline:**
- None detected - No GitHub Actions, GitLab CI, or Jenkins config
- Manual deployment via docker-compose up

**Build Artifact Storage:**
- Docker Images: Frontend (node:24-alpine), Backend (python:3.13-slim)
- Frontend: vite build output to dist/
- Backend: Non-root user omni (security best practice)

## Environment Configuration

**Required env vars (CRITICAL):**
- `MONGO_URI` - MongoDB connection string
- `REDIS_URL` - Redis connection string (fallback to MongoDB if not set)
- `JWT_SECRET_KEY` - JWT signing key (blocks startup in prod if missing)
- `GEMINI_API_KEY` - Google Gemini API key (if using Gemini)

**Cloud Integration env vars:**
- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_SUBSCRIPTION_ID` - Azure Defender
- `AZURE_WORKSPACE_ID` - Sentinel Log Analytics workspace
- `GCP_SERVICE_ACCOUNT_JSON_PATH` - GCP SCC service account
- `OKTA_ORG_URL`, `OKTA_API_TOKEN` - Okta identity

**Payment Gateway env vars:**
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` - Stripe
- `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` - PayPal
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` - Razorpay
- `SQUARE_ACCESS_TOKEN`, `SQUARE_ENVIRONMENT` - Square

**AI/LLM env vars:**
- `GEMINI_API_KEY` - Google Gemini
- `ANTHROPIC_API_KEY` - Claude (optional)
- `OLLAMA_URL` - Local Ollama endpoint

**Other env vars:**
- `VITE_PROXY_TARGET` - Frontend dev server API proxy target (default: http://127.0.0.1:5000)
- `REDIS_PASSWORD` - Redis auth password
- `MONGO_ROOT_USER`, `MONGO_ROOT_PASSWORD` - MongoDB auth (docker-compose)
- `ENVIRONMENT` - Set to prod/staging/dev (controls JWT fallback behavior)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT token lifetime (capped at 120)
- `JWT_ALGORITHM` - JWT signing algorithm (HS256/HS384/HS512 only)
- `VITE_API_BASE_URL` - Frontend API endpoint override
- `VITE_WS_URL` - Frontend WebSocket URL override

**Secrets location:**
- `.env` file at project root (NOT committed)
- Injected via docker-compose `env_file: .env` or individual environment variables in docker-compose.yml
- Vault integration: AWS Secrets Manager via `backend/secrets_service.py` (optional, uses boto3)
- Azure Vault: AZURE_VAULT_URL env var support

## Webhooks & Callbacks

**Incoming Webhooks:**
- Deception Technology tokens - `/api/deception/webhook/trigger/{token_id}`
  - Location: `backend/deception_endpoints.py`
  - Purpose: Track if honeytoken is triggered (unauthorized access detection)

- Payment Gateway webhooks (if enabled):
  - Stripe: stripe.Event webhook signature verification
  - PayPal: IPN (Instant Payment Notification) verification
  - Razorpay: Webhook signature validation
  - Square: Webhook signature validation
  - Location: `backend/payment_gateways/*_gateway.py`

**Outgoing Webhooks:**
- Security event notifications (via WebSocket first, HTTP webhook support TBD)
- Report delivery via email or SFTP (optional)
- Compliance event notifications to tenant notification endpoints (if configured)

## Real-Time Communication

**WebSocket / Socket.IO:**
- Server: python-socketio 5.11.0+
- Port: 5000 (same as FastAPI), separate HMR port 24678 for frontend
- Location: `backend/websocket_manager.py`
- Events:
  - Broadcast: MITRE heatmap updates, network traffic, support events
  - Bidirectional: Agent chat, remote control (reverse shell), incident warroom
  - Auth: JWT token validation on connect (requires valid user session)
- Client (Frontend): socket.io-client 4.7.2 in `services/socketService.ts`

## Agent Communication

**Agent Registration & Heartbeat:**
- Protocol: HTTPS REST API + WebSocket upgrade
- Base URL: api_base_url from agent/config.yaml
- Agent Token: JWT token embedded in config (signed by backend)
- Heartbeat Interval: 5 seconds (default from config)
- Location: `backend/agent_registry_endpoints.py`, `backend/agent_heartbeat_endpoints.py`

**Agent Data Collection:**
- File Integrity Monitoring: watchdog 4.0.0+
- Network Discovery: scapy 2.5.0+ or nmap wrapper
- Process Discovery: psutil 5.9.0+
- System Enumeration: sysinfo 0.32 (Rust)
- Malware Scanning: yara-python 4.3.0+ (optional)

---

*Integration audit: 2026-06-17*
