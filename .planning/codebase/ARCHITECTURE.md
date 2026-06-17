# Architecture

**Analysis Date:** 2026-06-17

## System Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React/Vite)                         │
│                       `App.tsx` (Root Container)                       │
│ ┌──────────────────┬──────────────────────┬──────────────────────────┐ │
│ │   Dashboard      │  Dashboards          │  Modals & Controls       │ │
│ │  Components      │  (60+ lazy-loaded)   │  (Auth, RBAC, Config)    │ │
│ │ `Dashboard.tsx`  │ (CXO, Security,      │ `LoginPage.tsx`          │ │
│ │                  │  Compliance, etc.)   │ `AddNewTenantModal.tsx`   │ │
│ │                  │ `components/*.tsx`   │ `SettingsDashboard.tsx`  │ │
│ └──────────────────┴──────────────────────┴──────────────────────────┘ │
│                                  │                                      │
│ ┌────────────────────────────────▼───────────────────────────────────┐ │
│ │        Frontend Service Layer                                      │ │
│ │ ┌─────────────────┬──────────────────┬──────────────────────────┐ │ │
│ │ │ apiService.ts   │ socketService.ts  │ contexts/               │ │ │
│ │ │ (REST API)      │ (WebSocket/       │ UserContext,            │ │ │
│ │ │ authFetch()     │  Real-time)       │ ThemeProvider,          │ │ │
│ │ │ fetchMetrics()  │ connect()         │ FeaturesContext         │ │ │
│ │ │ fetchAgents()   │ emit()            │                         │ │ │
│ │ │ ...70+ endpoints│ on()              │                         │ │ │
│ └─────────────────┴──────────────────┴──────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│                          Shared Types                                  │
│                          `types.ts` (1600+ lines)                      │
│            (User, Agent, Asset, Alert, Compliance, etc.)              │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  HTTP + WebSocket Proxy    │
                    │  (Vite Dev / nginx Prod)   │
                    │  /api → :5000/api          │
                    │  /socket.io → :5000/socket│
                    └─────────────▼──────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────────┐
│                    Backend (FastAPI / Python)                          │
│                          `app.py` (Entry)                              │
│                                                                         │
│ ┌──────────────────────┬─────────────────────┬─────────────────────┐  │
│ │ Middleware Layer     │ Route Handlers      │ WebSocket Server    │  │
│ │ ─────────────────    │ ──────────────      │ ───────────────     │  │
│ │ • Auth (JWT/SSO)     │ • /api/agents       │ • socket.io (SIO)   │  │
│ │ • Rate Limiting      │ • /api/assets       │ • Real-time events  │  │
│ │ • Tenant Isolation   │ • /api/security     │ • agent_status_*    │  │
│ │ • Error Handling     │ • /api/compliance   │ • notifications     │  │
│ │ • Security Headers   │ • /api/patches      │ • security_events   │  │
│ │                      │ • /api/integrations │ • compliance_alerts  │  │
│ │                      │ • 200+ route files  │                      │  │
│ └──────────────────────┴─────────────────────┴─────────────────────┘  │
│                                  │                                     │
│ ┌──────────────────────────────────▼──────────────────────────────┐   │
│ │             Service/Business Logic Layer                        │   │
│ │ ┌──────────┬─────────────┬──────────────┬──────────────────┐    │   │
│ │ │ Auth     │ Compliance  │ Security     │ Observability    │    │   │
│ │ │ ─────    │ ──────────  │ ────────     │ ──────────────   │    │   │
│ │ │ • JWT    │ • Framework │ • EDR        │ • Tracing        │    │   │
│ │ │ • RBAC   │   Controls  │ • Correlation│ • Metrics        │    │   │
│ │ │ • SSO    │ • Evidence  │ • SIEM       │ • APM            │    │   │
│ │ │ • Tenant │   Collect   │ • Playbooks  │ • Logs           │    │   │
│ │ │   Mgmt   │ • Risk Reg  │ • Automation │ • Health Check   │    │   │
│ │ └──────────┴─────────────┴──────────────┴──────────────────┘    │   │
│ │ ┌──────────┬─────────────┬──────────────┬──────────────────┐    │   │
│ │ │ Patch    │ Data        │ AI/ML        │ Integrations     │    │   │
│ │ │ ────────  │ ──────      │ ─────        │ ────────────     │    │   │
│ │ │ • Patch  │ • Data Lake │ • LLM Proxy  │ • Slack          │    │   │
│ │ │   Mgmt   │ • ETL       │ • AI Systems │ • PagerDuty      │    │   │
│ │ │ • SBOM   │ • Warehouse │ • XAI        │ • Jira           │    │   │
│ │ │ • Deploy │ • Govern    │ • Automl     │ • Webhooks       │    │   │
│ │ │ • Jobs   │ • Stream    │ • Training   │ • Custom APIs    │    │   │
│ │ └──────────┴─────────────┴──────────────┴──────────────────┘    │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                  │                                     │
│ ┌──────────────────────────────────▼──────────────────────────────┐   │
│ │             Data Access & Persistence                           │   │
│ │ ┌──────────┬────────────┬──────────────┬──────────────────┐     │   │
│ │ │ Database │ Collections│ Tenant Iso.  │ Cache/Redis      │     │   │
│ │ │ ────────  │ ──────────  │ ────────────  │ ────────────   │     │   │
│ │ │ MongoDB  │ • agents    │ • TenantId   │ • Session       │     │   │
│ │ │ (Motor)  │ • assets    │   Injection  │   Tokens        │     │   │
│ │ │          │ • alerts    │ • Fail-Closed│ • Rate Limits   │     │   │
│ │ │          │ • security  │   Access     │ • Hot Data      │     │   │
│ │ │          │ • compliance│ • Global Ref │                 │     │   │
│ │ │          │ • auth      │   Data       │                 │     │   │
│ │ │          │ • ...50+    │   (Frameworks│                 │     │   │
│ │ │          │             │    Exempt)   │                 │     │   │
│ │ └──────────┴────────────┴──────────────┴──────────────────┘     │   │
│ └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │   External Systems         │
                    │ ─────────────────          │
                    │ • Cloud APIs (AWS/Azure)   │
                    │ • Third-party SIEMs        │
                    │ • Threat Intelligence      │
                    │ • LLM Providers (Gemini)   │
                    │ • VirusTotal, etc.         │
                    └────────────────────────────┘

                            ┌──────────────┐
                            │ Agent (Rust) │
                            │ agent-rust/  │
                            │ ─────────────│
                            │ • Telemetry  │
                            │ • Detection  │
                            │ • Remediation│
                            │ • Webhook ↔  │
                            │   Backend    │
                            └──────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **App Root** | Entry point, auth state, data loading orchestration, permission checks | `App.tsx` |
| **Dashboard Components** | Feature-specific views (60+ lazy-loaded dashboards) | `components/*.tsx` |
| **API Service** | REST API calls, token refresh, auth headers, error handling | `services/apiService.ts` |
| **WebSocket Service** | Real-time event subscription, agent status updates | `services/socketService.ts` |
| **FastAPI Backend** | Route handling, business logic orchestration, DB access | `backend/app.py` |
| **Authentication** | JWT/SSO/MFA, token lifecycle, RBAC enforcement | `backend/authentication_service.py` |
| **Router Registry** | Centralised router loading, graceful error handling | `backend/router_registry.py` |
| **Database Layer** | MongoDB access, tenant isolation, data integrity | `backend/database.py` |
| **WebSocket Manager** | Socket.io server, event broadcasting, auth tunnel | `backend/websocket_manager.py` |
| **Agent Interface** | Agent registration, deployment, capability management | `backend/agent_endpoints.py` |

## Pattern Overview

**Overall:** Multi-tenant SaaS platform with three-tier architecture (frontend/backend/data) and distributed agent network.

**Key Characteristics:**
- **Tenant-First Architecture:** All data access enforces tenant isolation at the database layer
- **Lazy-Loaded Frontend:** 60+ dashboard components loaded on-demand for performance
- **Microservices-Inspired:** 200+ route handlers grouped by domain (agents, security, compliance, etc.)
- **Real-Time-Ready:** WebSocket and REST endpoints for live updates (agent status, alerts, events)
- **Permission-Based Access Control:** Feature visibility and CRUD tied to JWT permissions + tenant bundles
- **Multi-Agent Support:** Distributed Rust agents report telemetry, execute commands, perform compliance checks

## Layers

**Presentation (Frontend):**
- Purpose: Render dashboards, forms, modals, execute user commands
- Location: `components/`, `contexts/`, `services/`
- Contains: React components, Hooks, API abstraction, type definitions
- Depends on: REST API, WebSocket, localStorage for tokens
- Used by: End users via browser

**API/Application (Backend):**
- Purpose: Handle HTTP/WebSocket requests, orchestrate business logic, manage state
- Location: `backend/*.py` (200+ route files, services, middleware)
- Contains: FastAPI routers, service classes, integration logic, WebSocket handlers
- Depends on: MongoDB, external APIs (Gemini, Slack, etc.), agents
- Used by: Frontend, agents, webhooks, external systems

**Data Access (MongoDB):**
- Purpose: Persist all application state, enforce tenant isolation
- Location: Collections in MongoDB (agents, assets, alerts, compliance, etc.)
- Contains: User data, audit logs, configuration, agent heartbeats
- Depends on: Motor (async driver), tenant_context middleware
- Used by: Every backend service

## Data Flow

### Primary Request Path

1. **User Action** (`components/Dashboard.tsx` or any page)
   - User clicks "Deploy Patch", opens modal, submits form
   
2. **Frontend API Call** (`services/apiService.ts:authFetch()`)
   - Wrap request with JWT token from sessionStorage
   - Add Content-Type, tenantId headers
   - Call `POST /api/patches/deploy`

3. **Backend Route Handler** (`backend/patch_endpoints.py`)
   - FastAPI `@app.post("/deploy")` receives request
   - `get_current_user()` dependency validates JWT, extracts tenantId
   - Set tenant context via `set_tenant_id(user.tenantId)`

4. **Service Layer** (`backend/patch_core_endpoints.py` or service class)
   - Call business logic (validate inputs, check permissions, build job)
   - Persist to database via isolated collection

5. **Database Write** (`backend/database.py:TenantIsolatedCollection`)
   - `TenantIsolatedCollection._inject_tenant_id()` adds `tenantId` to filter
   - MongoDB `insert_one()` stores job with tenant isolation
   - Audit log recorded automatically

6. **Response** (back through stack)
   - Service returns job ID
   - FastAPI serializes to JSON
   - Frontend receives job status
   - UI updates with success toast

### WebSocket Real-Time Flow

1. **Connection** (`services/socketService.ts:connect()`)
   - Frontend opens socket.io connection via `/socket.io` proxy
   - Auth header includes JWT token and tenantId

2. **Authentication** (`backend/websocket_manager.py`)
   - Socket.io server validates token, tenant context set
   - Client joins tenant-specific room

3. **Backend Event** (any service)
   - Job completes, agent comes online, security event fires
   - Service calls `sio.emit('agent_status_change', {...})` or broadcasts to room

4. **Client Receive** (`App.tsx` useEffect or component listener)
   - `socketService.on('agent_status_change', (data) => {...})`
   - Update React state, re-render UI in real-time

**State Management:**
- **Tokens:** Stored in sessionStorage (volatile, cleared on logout)
- **User Data:** React useState (App.tsx holds currentUser, tenants, roles, permissions)
- **Global UI State:** useState for sidebar, modals, current view
- **Feature Flags:** Fetched at login via `/api/platform-features`, stored in state
- **Data Refresh:** Periodic polling (30s for metrics, 5s for agents when on agents page)

## Key Abstractions

**Agent:**
- Purpose: Software deployed to customer systems to collect telemetry, detect threats, execute remediation
- Examples: `backend/agent_endpoints.py`, `agent-rust/src/agent.rs`
- Pattern: Poll backend for commands, report status/logs via webhook, execute autonomously

**Asset:**
- Purpose: Logical representation of a resource (host, VM, container, K8s node, network device)
- Examples: Windows Server, Linux VM, Docker container
- Pattern: Agent discovers and reports asset metadata (OS, software, vulnerabilities)

**Alert & SecurityEvent:**
- Purpose: Incident signal (from agents, integrations, or correlation engine)
- Examples: "Malware detected", "Failed login x10", "Unauthorized S3 access"
- Pattern: Triggered by detection rules, enriched with threat intel, assigned to SecurityCase

**SecurityCase:**
- Purpose: Investigation container linking related events, enrichment, and remediation steps
- Examples: Active investigation into data exfiltration
- Pattern: Can reference Playbook for automated or manual response steps

**Playbook:**
- Purpose: Reusable SOC workflow triggered by conditions/cases
- Examples: "Contain compromised host", "Notify leadership", "Block IP globally"
- Pattern: Steps are ordered, can branch on conditions, integrate with external systems

**ComplianceFramework & Control:**
- Purpose: Track regulatory requirements (SOC2, ISO27001, CIS Benchmark)
- Examples: "Access control must be multi-factor"
- Pattern: Evidenced by collected artifacts (logs, configs, automation output)

## Entry Points

**Web App:**
- Location: `App.tsx` (line 410+)
- Triggers: Browser loads `http://localhost:3000/`
- Responsibilities: Auth check, data preload, navigation, permission-based view filtering

**Backend Health:**
- Location: `backend/app.py:health()` (line 93)
- Triggers: GET `/health` (polling)
- Responsibilities: Return service status, database connectivity, edition info

**Agent Registration:**
- Location: `backend/agent_endpoints.py:register_agent()` (approx. line 150+)
- Triggers: New agent binary runs, calls POST `/api/agents/register`
- Responsibilities: Validate agent, create tenant-isolated agent record, return API key

**WebSocket Connection:**
- Location: `backend/websocket_manager.py` (socket.io auth handler)
- Triggers: Frontend loads, calls `socketService.connect(tenantId)`
- Responsibilities: Authenticate, set up real-time event routing

## Architectural Constraints

- **Threading:** Python asyncio (event loop) for backend; frontend is single-threaded event loop
- **Global State:** 
  - `backend/tenant_context.py` uses context-local storage (one tenantId per async task)
  - Frontend React state (App.tsx) holds all user session, permissions, data
  - No global singletons; all state passed via dependency injection or React context
- **Circular Imports:** Frontend lazy-loads dashboard components to avoid circular dep chains
- **Data Isolation:** MongoDB collections wrapped by `TenantIsolatedCollection`; fail-closed (rejects unauth queries)
- **Token Lifecycle:** Frontend refreshes JWT proactively 5 minutes before expiry; refresh token stored encrypted in session

## Anti-Patterns

### Uncontrolled Permission Checks

**What happens:** Multiple dashboards manually check `currentUser.permissions.includes('view:security')` instead of using centralized permission map.

**Why it's wrong:** Permission definitions are scattered across 60 components, easy to miss permission gate, security regression on refactor.

**Do this instead:** Use centralized `viewPermissionMap` in `App.tsx` (lines 209-382) and `hasPermission(perm)` helper; gating is enforced at component render level or in route handler.

### Unvalidated Tenant ID Assumptions

**What happens:** Route handler writes data to MongoDB without explicitly calling `set_tenant_id()` first, assuming it's already set.

**Why it's wrong:** Tenant context may be stale or unset; data could be written to wrong tenant or with missing tenantId.

**Do this instead:** Every authenticated endpoint must have `get_current_user()` dependency AND call `set_tenant_id(user.tenantId)` explicitly. Database layer (`TenantIsolatedCollection`) then auto-injects tenant filter.

### Synchronous Agent Command Blocking

**What happens:** Frontend calls `POST /api/agents/{id}/execute-command`, waits for immediate response.

**Why it's wrong:** Agent may be offline or slow; blocks frontend, poor UX, timeout.

**Do this instead:** Async job pattern: POST creates AgentUpgradeJob record, returns job ID immediately, frontend polls `/api/jobs/{id}` or listens to WebSocket for completion event.

### Missing Audit Trail

**What happens:** Sensitive operation (delete compliance evidence, approve AI model) executes without audit log.

**Why it's wrong:** No forensics trail; regulatory audit fails; insider threat undetected.

**Do this instead:** Every state-changing endpoint must insert audit log entry (`AuditLog` collection) with user, timestamp, resource ID, and change summary.

## Error Handling

**Strategy:** Fail-closed with specific error codes. Frontend surfaces user-friendly messages; backend logs detailed stack traces.

**Patterns:**
- **HTTP Errors:** 400 (validation), 401 (auth), 403 (permission), 404 (not found), 500 (internal), 503 (service unavailable)
- **Auth Failure:** Return 401, trigger frontend session logout via `_expireSession()` in apiService
- **Tenant Isolation Breach:** Log security alert, return 403, block further access in that session
- **External API Failure:** Catch, log, return graceful fallback (cached data, empty list) to avoid cascading failures

## Cross-Cutting Concerns

**Logging:** 
- Python: `logging` module configured via `backend/logging_config.py`, outputs to stdout (container-friendly)
- Frontend: `console.log()` disabled in production via `App.tsx` lines 4-7

**Validation:**
- Frontend: React form validation (React Hook Form or manual), UI feedback
- Backend: Pydantic models auto-validate request bodies; custom validators in service layer

**Authentication:**
- Frontend: JWT stored in sessionStorage, proactively refreshed, auto-logout on expiry
- Backend: JWTBearer dependency in every protected route, tenant context set from JWT claims

