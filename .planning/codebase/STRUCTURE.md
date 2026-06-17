# Codebase Structure

**Analysis Date:** 2026-06-17

## Directory Layout

```
enterprise-omni-agent-ai-platform/
├── App.tsx                           # Root React component, auth, navigation, data loading
├── types.ts                          # Shared type definitions (1600+ lines)
├── vite.config.ts                    # Vite dev server config, proxy rules
├── package.json                      # Frontend dependencies (React 19, Socket.io, Recharts, etc.)
│
├── components/                       # React dashboard components (60+ files)
│   ├── Dashboard.tsx                 # Main dashboard landing page
│   ├── LoginPage.tsx                 # Authentication UI
│   ├── Sidebar.tsx                   # Navigation menu
│   ├── Header.tsx                    # Top bar with search, notifications
│   ├── ErrorBoundary.tsx             # React error catching
│   ├── AgentsDashboard.tsx           # Agent inventory & management
│   ├── SecurityDashboard.tsx         # Security events, cases, correlation
│   ├── ComplianceDashboard.tsx       # Framework tracking, evidence collection
│   ├── CXODashboard.tsx              # Executive summary metrics
│   ├── ReportingDashboard.tsx        # Report generation UI
│   ├── ...                           # ~60 more specialized dashboards
│   ├── ui/                           # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Modal.tsx
│   │   └── ...
│   └── icons/                        # Icon definitions
│
├── services/                         # Frontend API integration
│   ├── apiService.ts                 # REST API calls (70+ endpoints)
│   │                                 # authFetch(), token refresh, error handling
│   └── socketService.ts              # WebSocket subscription & event handling
│
├── contexts/                         # React Context API providers
│   ├── UserContext.tsx               # User, role, permission state
│   ├── ThemeProvider.tsx             # Dark/light mode
│   ├── TimeZoneContext.tsx           # Timezone conversion
│   └── FeaturesContext.tsx           # Feature flag state
│
├── utils/                            # Utility functions
│   ├── toast.ts                      # Toast notifications
│   └── ...
│
├── backend/                          # FastAPI backend (200+ route files)
│   ├── app.py                        # FastAPI entry, lifespan, middleware setup
│   ├── app_startup.py                # Config validation, database seeding, YARA rules
│   ├── database.py                   # MongoDB connection, TenantIsolatedCollection
│   ├── router_registry.py            # Centralized router loading
│   ├── app_middleware.py             # Security headers, rate limiting, auth hooks
│   ├── error_handlers.py             # Custom exception handlers
│   ├── authentication_service.py     # JWT/SSO/MFA auth logic
│   ├── tenant_context.py             # Async-local tenant ID storage
│   ├── websocket_manager.py          # Socket.io server, real-time events
│   │
│   ├── agent_endpoints.py            # Agent registration, heartbeat, command polling
│   ├── asset_endpoints.py            # Asset CRUD, inventory
│   ├── patch_endpoints.py            # Patch management endpoints
│   ├── patch_core_endpoints.py       # Patch deployment service logic
│   ├── security_endpoints.py         # Security case, event management
│   ├── compliance_endpoints.py       # Compliance framework, control evidence
│   ├── compliance_evidence_processor.py # Evidence collection orchestration
│   │
│   ├── agent_heartbeat_endpoints.py  # Agent telemetry ingestion
│   ├── edr_telemetry_endpoints.py    # EDR-specific telemetry
│   ├── threat_intel_endpoints.py     # Threat intelligence enrichment
│   ├── correlation_engine_core.py    # Security event correlation
│   ├── attack_path_endpoints.py      # Attack path analysis
│   ├── mitre_endpoints.py            # MITRE ATT&CK mapping
│   │
│   ├── ai_service.py                 # LLM integration, prompt engineering
│   ├── llm_proxy.py                  # Gemini/Claude proxy, chat endpoints
│   ├── ai_system_endpoints.py        # AI system governance (risk, metrics)
│   ├── ai_auditor_endpoints.py       # AI compliance auditing
│   ├── ai_remediation_service.py     # AI-assisted remediation suggestions
│   │
│   ├── finops_service.py             # Cost tracking, forecasting
│   ├── finops_scheduler.py           # Periodic cost calculations
│   ├── billing_endpoints.py          # Invoice, subscription management
│   ├── payment_endpoints.py          # Stripe integration
│   │
│   ├── rate_limiter.py               # Request throttling
│   ├── logging_config.py             # Centralized logging setup
│   ├── health_service.py             # System health checks
│   ├── scheduler.py                  # Celery/APScheduler for jobs
│   │
│   ├── ai_services/                  # AI/ML subdomain
│   │   ├── training_endpoints.py     # Model training API
│   │   └── ...
│   ├── models/                       # SQLAlchemy/Pydantic schemas
│   │   ├── user.py
│   │   ├── agent.py
│   │   └── ...
│   ├── migrations/                   # Database migration scripts
│   │   ├── runner.py
│   │   └── 001_initial.py
│   ├── frameworks/                   # Compliance frameworks
│   │   ├── soc2_framework.json
│   │   ├── iso27001_framework.json
│   │   └── ...
│   ├── yara_rules/                   # Malware detection rules
│   │   ├── ransomware.yar
│   │   ├── injectors.yar
│   │   └── credential_dumpers.yar
│   ├── data_lake_storage/            # Raw/processed data lake
│   │   ├── raw/
│   │   └── processed/
│   ├── tests/                        # Pytest unit/integration tests
│   ├── logs/                         # Runtime logs directory
│   ├── static/                       # Static files (agent installers, docs)
│   │   ├── win-install.ps1           # Windows agent installer
│   │   ├── linux-install.sh
│   │   ├── .well-known/
│   │   │   └── security.txt          # RFC 9116 security policy
│   │   └── reports/                  # Generated compliance reports
│   └── venv/                         # Python virtual environment (excluded from git)
│
├── agent-rust/                       # Rust agent source
│   ├── Cargo.toml                    # Rust dependencies
│   ├── src/
│   │   ├── main.rs                   # Agent entry point
│   │   ├── agent.rs                  # Agent core logic, polling loop
│   │   ├── http.rs                   # HTTP client for backend calls
│   │   ├── ws.rs                     # WebSocket connection (alternate to polling)
│   │   ├── config.rs                 # Config file parsing
│   │   ├── caps.rs                   # Capability 1: telemetry collection
│   │   ├── caps2.rs                  # Capability 2: vulnerability scanning
│   │   ├── caps3.rs                  # Capability 3: compliance enforcement
│   │   ├── shell.rs                  # Shell command execution
│   │   ├── log.rs                    # Logging infrastructure
│   │   ├── poll.rs                   # Command polling from backend
│   │   ├── yara_scan.rs              # YARA rule detection
│   │   ├── compliance_native.rs      # Native compliance checks
│   │   ├── agentic.rs                # Agentic reasoning for autonomous action
│   │   └── cissp.rs                  # CISSP control compliance checks
│   └── target/                       # Build artifacts
│
├── agent-install/                    # Agent deployment & installation
│   ├── agent/                        # Python agent reference implementation
│   │   ├── installer.py              # MSI/DEB generator
│   │   ├── config_template.yaml
│   │   └── ...
│   └── omni-agent-rs/                # Rust build templates
│
├── agent/                            # Legacy/reference agent implementations
│   ├── agentic_core/                 # Agentic reasoning module
│   ├── autonomous_actions/           # Auto-remediation workflows
│   ├── capabilities/                 # Modular capabilities registry
│   │   ├── yara_rules/               # Shared YARA detection rules
│   │   └── ...
│   ├── goal_system/                  # Goal-driven automation
│   ├── knowledge_base/               # Agent reasoning knowledge
│   ├── swarm/                        # Multi-agent coordination
│   └── venv/                         # Python virtual environment
│
├── .claude/                          # Claude Code workspace config
│   ├── skills/                       # Custom agent skills
│   │   └── SKILL.md                  # Skill definitions
│   ├── commands/                     # CLI command definitions
│   ├── settings.json                 # Global workspace settings
│   └── agents/                       # Configured agents
│
├── .github/workflows/                # CI/CD pipelines
│   ├── test.yml
│   ├── deploy.yml
│   └── security.yml
│
├── kubernetes/                       # Kubernetes manifests
│   ├── deployment.yaml
│   └── service.yaml
│
├── helm/                             # Helm chart for Kubernetes deployment
│   └── omni-platform/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
├── docs/                             # Documentation
│   └── superpowers/                  # Feature documentation
│
├── .planning/                        # GSD codebase map output (this file location)
│   └── codebase/
│       ├── ARCHITECTURE.md
│       └── STRUCTURE.md
│
├── .env                              # Environment variables (git-ignored)
├── .env.example                      # Template env file
├── .gitignore                        # Git exclusions
├── tsconfig.json                     # TypeScript config
├── tailwind.config.js                # Tailwind CSS config
├── pyproject.toml                    # Python project config (ruff, pytest)
├── requirements.txt                  # Python dependencies (FastAPI, Motor, etc.)
└── README.md                         # Project overview
```

## Directory Purposes

**Frontend Root:**
- Purpose: Vite + React app source
- Contains: Components, services, contexts, shared types
- Key files: App.tsx (root), types.ts (all interfaces), package.json (deps)
- Compiled to: `dist/` by `npm run build`

**components/**
- Purpose: React component library (60+ feature dashboards + shared components)
- Contains: Functional components with hooks, forms, charts
- Key files: Dashboard.tsx (landing), LoginPage.tsx (auth), Sidebar.tsx (navigation)
- Pattern: Each dashboard is lazy-loaded via React.lazy() to reduce initial bundle

**services/**
- Purpose: API abstraction layer
- Contains: REST/WebSocket wrapper functions, token management, error handling
- Key files: apiService.ts (70+ fetch methods), socketService.ts (real-time)
- Pattern: All authenticated requests go through authFetch() which auto-injects JWT, handles refresh

**contexts/**
- Purpose: Global state via React Context API
- Contains: User auth, theme, timezone, feature flags
- Key files: UserContext.tsx (user + permissions), ThemeProvider.tsx (light/dark)
- Pattern: Providers wrap <App> in index.tsx or main entry

**backend/app.py:**
- Purpose: FastAPI entry point, lifespan management, error handlers
- Contains: FastAPI instance, middleware chain, static file mounts, health checks
- Pattern: Middleware registered first, then routers included via router_registry.py

**backend/router_registry.py:**
- Purpose: Centralized router loading (fails gracefully if one router breaks)
- Contains: Import statements for all 200+ route modules
- Pattern: _load() helper catches import errors, logs them, continues with next router

**backend/database.py:**
- Purpose: MongoDB connection pool, tenant isolation wrapper
- Contains: TenantIsolatedCollection (auto-injects tenantId filter), TenantIsolatedDatabase
- Pattern: Every collection query auto-adds `{"tenantId": <current_tenant>}` unless exempt (frameworks, roles, etc.)

**backend/authentication_service.py:**
- Purpose: JWT validation, SSO integration, RBAC checks
- Contains: get_current_user() dependency, token validation, permission mapping
- Pattern: Every protected route has `get_current_user()` dependency to enforce auth + tenant context

**backend/agent_endpoints.py:**
- Purpose: Agent registration, heartbeat, command polling
- Contains: POST /agents/register, POST /agents/{id}/heartbeat, GET /agents/{id}/commands
- Pattern: Async polling loop in agent pulls new commands from backend job queue

**backend/patch_endpoints.py & patch_core_endpoints.py:**
- Purpose: Patch inventory, deployment automation
- Contains: Patch CRUD, deployment scheduling, job tracking
- Pattern: Deployment is async job (returns job ID immediately, agent executes later)

**backend/compliance_endpoints.py & compliance_evidence_processor.py:**
- Purpose: Framework tracking, evidence collection, control assessment
- Contains: Control mapping, evidence collection API, compliance report generation
- Pattern: Evidence collected from agents + integrations, AI scores compliance status

**backend/security_endpoints.py:**
- Purpose: Security case management, incident response
- Contains: Case CRUD, playbook execution, alert enrichment
- Pattern: Cases link events + evidence + playbooks, can be manually or automatically created

**agent-rust/src/:**
- Purpose: Compiled Rust agent binary source
- Contains: Polling loop, capability execution, telemetry reporting
- Key files: main.rs (entry), agent.rs (core loop), caps.rs/caps2.rs (capabilities)
- Pattern: Runs as daemon/service, polls backend for commands, reports status via webhook

## Key File Locations

**Entry Points:**
- Frontend: `/home/user/enterprise-omni-agent-ai-platform/App.tsx` (React root)
- Backend API: `/home/user/enterprise-omni-agent-ai-platform/backend/app.py` (FastAPI root)
- Agent: `/home/user/enterprise-omni-agent-ai-platform/agent-rust/src/main.rs` (Rust entry)
- Database: MongoDB (cloud or local) — no file-based SQL; URI in env var MONGO_URI

**Configuration:**
- Frontend: `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`, `package.json`
- Backend: `backend/app.py` (see lifespan), `backend/app_startup.py` (validation), `.env`
- Build: `package.json` scripts (dev, build, test), `Cargo.toml` (Rust)

**Core Logic:**
- Auth: `backend/authentication_service.py` (JWT validation, RBAC)
- Agents: `backend/agent_endpoints.py` (registration), `agent-rust/src/agent.rs` (execution)
- Compliance: `backend/compliance_endpoints.py` (framework), `backend/compliance_evidence_processor.py` (evidence)
- Security: `backend/security_endpoints.py` (cases), `backend/correlation_engine_core.py` (event correlation)
- AI: `backend/ai_service.py` (LLM calls), `backend/llm_proxy.py` (proxy to Gemini)

**Testing:**
- Frontend: Tests (if any) in `src/__tests__/` or `*.test.ts`
- Backend: Tests in `backend/tests/` (pytest-based)
- Run: `npm test` (frontend), `pytest backend/tests/` (backend)

## Naming Conventions

**Files:**
- React components: PascalCase, `.tsx` (e.g., `AgentsDashboard.tsx`, `LoginPage.tsx`)
- Services: camelCase, `.ts` (e.g., `apiService.ts`, `socketService.ts`)
- Python modules: snake_case, `.py` (e.g., `authentication_service.py`, `router_registry.py`)
- Styles: Tailwind classes inline; no separate .css files (except Tailwind config)

**Directories:**
- Feature domains: lowercase plural (e.g., `components/`, `services/`, `agents/`)
- Unused/archived: prefix with underscore or move to separate folder
- Test directories: `tests/` or `__tests__/`

**React Component Structure:**
```typescript
// e.g., components/AgentsDashboard.tsx
const AgentsDashboard: React.FC<Props> = ({ data, onAction }) => {
  const [localState, setLocalState] = useState<T>(...);
  
  return (
    <div>
      {/* JSX */}
    </div>
  );
};
export default AgentsDashboard;
```

**Python Endpoint Structure:**
```python
# e.g., backend/agent_endpoints.py
router = APIRouter(prefix="/api/agents", tags=["Agents"])

@router.post("/register")
async def register_agent(
    payload: AgentRegisterRequest,
    current_user = Depends(get_current_user),
):
    set_tenant_id(current_user.tenantId)
    # business logic
    return {"success": True, "agent_id": "..."}
```

## Where to Add New Code

**New Feature:**
- **Primary code:** `backend/new_feature_endpoints.py` (FastAPI router + 1-2 service classes)
- **Tests:** `backend/tests/test_new_feature.py` (pytest)
- **Frontend UI:** `components/NewFeatureDashboard.tsx` (lazy-load in App.tsx)
- **API client:** Add to `services/apiService.ts` (fetch function + type)
- **Types:** Add interfaces to `types.ts`

**New Component/Module:**
- **Implementation:** 
  - React: `components/NewComponent.tsx` with hooks and props
  - Python: `backend/new_module_service.py` with classes
- **Exports:** Each module exports default or named exports matching filename
- **Entry:**
  - React: Imported in parent or lazy-loaded in App.tsx
  - Python: Imported in router_registry.py for auto-loading

**New Endpoint Route:**
- Create `backend/my_feature_endpoints.py` with `router = APIRouter(...)`
- Define route function with `get_current_user()` dependency and `set_tenant_id()` call
- Add to `backend/router_registry.py` via `_load(app, "my_feature_endpoints", "router")`
- Frontend calls via `await authFetch('/api/...', {...})`

**Utilities:**
- Shared helpers: `backend/common_utils.py` or `services/utils.ts`
- Constants: Define near usage or in central `constants.ts` / `config.py`

**Tests:**
- Backend: `backend/tests/test_<module>.py` (pytest)
- Frontend: `src/__tests__/<component>.test.tsx` (Vitest)
- Run `pytest backend/tests/` or `npm test`

## Special Directories

**agent/ (legacy Python agent):**
- Purpose: Reference implementation and agentic core modules
- Generated: Not part of main build; used for reference or custom agent builds
- Committed: Yes (part of version control)

**agent-rust/ (compiled Rust agent):**
- Purpose: Production agent binary source
- Build: `cargo build --release` produces `target/release/omni-agent` binary
- Committed: Yes (src/), no (target/ via .gitignore)

**backend/data/ & data_lake_storage/:**
- Purpose: Data lake for raw/processed data ingest
- Generated: Yes (populated at runtime)
- Committed: No (excluded via .gitignore)

**backend/migrations/:**
- Purpose: Database schema migration scripts
- Generated: No (authored by developers)
- Committed: Yes (versioned alongside code)

**.env & .env.example:**
- Purpose: Environment configuration (secrets, API keys, URLs)
- .env: Actual secrets (git-ignored, never committed)
- .env.example: Template showing required keys (committed as reference)

**.planning/codebase/:**
- Purpose: GSD codebase analysis output
- Generated: Yes (by `/gsd-map-codebase` command)
- Committed: Yes (part of documentation)

