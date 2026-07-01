# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security
- Removed hardcoded credentials (`sriprasad_credentials.txt`, `WORKING_CREDENTIALS.txt`, `token.txt`, `key.txt`) from repository tracking
- Removed `email_encryption.key` from git tracking; key now loaded from `EMAIL_ENCRYPTION_KEY` env var
- Fixed SSRF vulnerabilities in `integrations_v2.py` (Slack, MSTeams, Jira webhook test endpoints) — all URLs now validated against private IP ranges before HTTP requests
- Fixed SSRF via DNS bypass in `pentest_integration_service.py` — hostname now resolved and all returned IPs checked
- Added SSRF guard to `webhook_endpoints.py` `create_webhook` — private/internal URLs rejected at creation time
- Replaced plaintext password seeds with `hash_password(os.getenv("SUPER_ADMIN_PASSWORD"))` across all seeders and scripts
- Removed `SECRET_KEY` from public import in `authentication_endpoints.py`
- Capped `ACCESS_TOKEN_EXPIRE_MINUTES` at 120 minutes regardless of env var value
- Added `DOMPurify.sanitize()` to `EvidenceMarkdownViewer.tsx` and `CSPMRemediationModal.tsx` to prevent XSS via AI-generated content
- Added global rate limiting defaults (`200/minute`, `2000/hour`) to all 118 API routers
- Expanded Content-Security-Policy headers: added `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`
- Added `X-XSS-Protection: 1; mode=block` header

### Added
- **Security automation**: gitleaks pre-commit hook (`.pre-commit-config.yaml`, `.gitleaks.toml`) to block future credential commits
- **CI — Bandit**: Python SAST scan added to backend CI job (medium+ severity gate)
- **CI — Safety**: Python dependency vulnerability check (advisory, `continue-on-error: true`)
- **CI — npm audit**: Frontend high-severity dependency gate added
- **CI — Permissions**: Explicit `permissions: contents:read, checks:write` added to workflow
- **Dependabot**: Automated dependency updates for pip, npm, Docker, and GitHub Actions (`.github/dependabot.yml`)
- **Production Dockerfile**: Multi-stage `Dockerfile.frontend.prod` — Node 24 builder → nginx 1.27 runtime, non-root user, SPA routing
- **nginx config**: `nginx/nginx.prod.conf` with gzip, security headers, API/WebSocket proxy, 1-year asset cache, SPA fallback
- **docker-compose profiles**: `--profile production` uses nginx frontend; default profile uses Vite dev server
- **Global error handlers**: `backend/error_handlers.py` — consistent `{error, request_id}` JSON shape for all exceptions
- **Circuit breaker**: `backend/circuit_breaker.py` — CLOSED/OPEN/HALF_OPEN state machine for AI provider and webhook calls
- **Structured logging**: `backend/logging_config.py` — JSON formatter with request ID correlation
- **Request ID middleware**: Every request gets `X-Request-ID` header for log correlation
- **DB migration system**: `backend/migrations/runner.py` — tracks applied migrations in `_migrations` collection; `001_initial_indexes.py` adds core collection indexes
- **Startup secret validation**: `_check_placeholder_secrets()` in `app_startup.py` refuses to start in production with placeholder credentials
- **security.txt**: RFC 9116 security disclosure policy at `/.well-known/security.txt`
- **CONTRIBUTING.md**: Branch naming, commit conventions, PR checklist, test requirements
- **CHANGELOG.md**: This file

### Changed
- `backend/.env.example`: `ACCESS_TOKEN_EXPIRE_MINUTES` changed from `480` to `60`; added `MONGO_ROOT_PASSWORD`, `REDIS_PASSWORD`, `EMAIL_ENCRYPTION_KEY` placeholders
- `docker-compose.yml`: MongoDB bound to `127.0.0.1:27017`, Redis bound to `127.0.0.1:6379` with password auth, backend volume changed to read-only (`:ro`) with named volumes for writable dirs
- `backend/Dockerfile`: Changed from pre-release `python:3.14-slim` to stable `python:3.13-slim`
- `Dockerfile.frontend`: `NODE_ENV` changed from `development` to `production`
- `.github/workflows/ci.yml`: Removed hardcoded `ci-test-secret-key-not-for-production` JWT fallback; JWT secret now required as GitHub Actions secret
- `.editorconfig`: Added consistent formatting rules for Python (4-space), TypeScript (2-space), Markdown

### Fixed
- MongoDB exposed on all interfaces with no auth (now `127.0.0.1` only, requires `MONGO_ROOT_PASSWORD`)
- Redis exposed on all interfaces with no auth (now `127.0.0.1` only, requires `REDIS_PASSWORD`)

---

## [2030.0.0] — Initial Release

- Enterprise-grade autonomous observability and AI governance platform
- Multi-tenant FastAPI backend with 118 API routers
- React 19 frontend with 50+ domain dashboards
- Distributed agent system with 46 capability modules
- XDR/SIEM, CSPM, AI governance, compliance, incident response, FinOps domains
- Kubernetes + Helm deployment support
