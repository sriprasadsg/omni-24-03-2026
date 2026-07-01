# Architecture Overview

## System Diagram

```
                              ┌─────────────────────────────────────┐
                              │           User Browser               │
                              │     React 19 + TypeScript            │
                              │  50+ lazy-loaded domain dashboards   │
                              │  Socket.IO client (real-time)        │
                              └──────────────┬──────────────────────┘
                                             │ HTTP/WebSocket
                              ┌──────────────▼──────────────────────┐
                              │         nginx (prod) / Vite (dev)    │
                              │  Port 80/443 (prod) | 3000 (dev)     │
                              │  SPA routing, static asset caching   │
                              └──────────────┬──────────────────────┘
                                             │ /api/* proxy
        ┌────────────────────────────────────▼────────────────────────────────────┐
        │                        FastAPI Backend (Python 3.13)                    │
        │                        Port 5000 | 2 Uvicorn workers                   │
        │                                                                         │
        │  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐   │
        │  │ Router Registry │  │  Auth Middleware  │  │  Rate Limiter       │   │
        │  │ 118 routers     │  │  JWT + RBAC       │  │  200/min default    │   │
        │  │ fault-tolerant  │  │  Tenant isolation │  │  Slowapi            │   │
        │  └────────┬────────┘  └──────────────────┘  └─────────────────────┘   │
        │           │                                                              │
        │  ┌────────▼──────────────────────────────────────────────────────────┐ │
        │  │                     Domain Endpoint Modules (169 files)            │ │
        │  │  Security │ Compliance │ AI Governance │ Agents │ Cloud │ ITSM... │ │
        │  └────────┬──────────────────────────────────────────────────────────┘ │
        │           │                                                              │
        │  ┌────────▼────────────────────────────────┐                           │
        │  │     TenantIsolatedCollection (wrapper)   │                           │
        │  │     Auto-injects tenantId on all queries │                           │
        │  │     Fail-closed: empty tenant → blocked  │                           │
        │  └────────┬────────────────────────────────┘                           │
        └───────────┼─────────────────────────────────────────────────────────── ┘
                    │                             │                    │
         ┌──────────▼──────┐          ┌──────────▼────┐    ┌─────────▼────────┐
         │   MongoDB 8.0   │          │   Redis 8.0   │    │   ChromaDB       │
         │  Primary store  │          │  Rate limits  │    │  Vector DB       │
         │  Tenant-isolated│          │  Session cache│    │  RAG / Agent     │
         │  30+ collections│          │  Auth tokens  │    │  knowledge base  │
         └─────────────────┘          └───────────────┘    └──────────────────┘

                         ┌────────────────────────────────────────────────┐
                         │              Agent Fleet                        │
                         │                                                  │
                         │  ┌──────────────┐  ┌────────────┐              │
                         │  │ Windows .exe │  │ Linux svc  │  K8s daemon  │
                         │  │ PyInstaller  │  │ systemd    │  DaemonSet   │
                         │  └──────┬───────┘  └─────┬──────┘              │
                         │         │                 │                      │
                         │  ┌──────▼─────────────────▼──────────────────┐ │
                         │  │            agent.py (main loop)            │ │
                         │  │                                            │ │
                         │  │  AgenticLLM ◄── Ollama (local LLM)        │ │
                         │  │  ReasoningEngine                          │ │
                         │  │  SafetyGuardrails                         │ │
                         │  │  46 capability modules:                   │ │
                         │  │    EDR, FIM, Patching, YARA,              │ │
                         │  │    K8s monitor, SBOM, Network scan,       │ │
                         │  │    Shadow AI monitor, Remote terminal...  │ │
                         │  │                                            │ │
                         │  │  Offline buffer: SQLite (disconnected)    │ │
                         │  │  SwarmCoordinator (multi-agent)           │ │
                         │  │  GoalManager (goal-driven autonomy)       │ │
                         │  └────────────────────┬───────────────────── ┘ │
                         └───────────────────────┼────────────────────────┘
                                                 │ WebSocket / JWT
                                     ┌───────────▼──────────┐
                                     │   Backend /api/agents │
                                     │   Heartbeat, Tasks,   │
                                     │   Remote control,     │
                                     │   Telemetry           │
                                     └──────────────────────┘

     External Integrations
     ──────────────────────
     AI Providers:  Anthropic Claude │ Google Gemini │ Ollama (local)
     Cloud:         AWS (CloudTrail, Security Hub) │ Azure Defender │ GCP
     SIEM/ITSM:     Splunk │ PagerDuty │ Jira │ ServiceNow
     Notifications: Slack │ Microsoft Teams │ Email (SMTP)
     Security:      VirusTotal │ YARA rules │ NIST NVD │ MITRE ATT&CK
     Payments:      Stripe │ PayPal │ Razorpay
```

---

## Key Architectural Decisions

### Multi-Tenancy (Fail-Closed)
`TenantIsolatedCollection` wraps every MongoDB collection. It auto-injects `{tenantId: <current>}` into every `find`, `insert`, `update`, and `delete`. If no tenant context exists in the request, a dummy tenant ID is used — queries return empty rather than leaking data.

### Fault-Tolerant Router Loading
`router_registry.py` loads all 118 API routers via `_load()`. Each router is imported inside a try/except — a broken router logs a warning and is skipped, preventing one bad module from taking down the entire API.

### Agent Offline-First Design
Agents use a SQLite-backed `MessageBuffer` for outbound messages when the backend is unreachable. Messages are encrypted, buffered locally, and flushed on reconnection via the heartbeat channel.

### LLM Self-Tuning
`AgenticLLM` tracks inference success/failure ratios and auto-adjusts temperature (deterministic ↔ creative) persisted to `data/llm_tuning.json` across restarts.

### AI Provider Abstraction
`ai_service.py` presents a single interface for Claude, Gemini, and Ollama. The active provider is selected via the `LLM_PROVIDER` env var. A circuit breaker (`circuit_breaker.py`) wraps all provider calls to prevent cascade failures.

---

## Directory Map

```
enterprise-omni-agent-ai-platform/
├── backend/                   # FastAPI Python backend
│   ├── app.py                 # Application factory, lifespan, middleware registration
│   ├── router_registry.py     # Dynamic router loader (118 routers)
│   ├── database.py            # Motor async client + TenantIsolatedCollection
│   ├── authentication_service.py  # JWT, bcrypt, MFA, OAuth2/OIDC/SAML
│   ├── migrations/            # MongoDB migration runner + versioned migrations
│   ├── ai_services/           # Claude, Gemini, Ollama provider implementations
│   ├── static/                # Reports (PDF/Excel), .well-known/security.txt
│   └── tests/                 # pytest test suite
│
├── components/                # React component library (312 .tsx files)
│   ├── Dashboard.tsx          # Main navigation shell
│   ├── *Dashboard.tsx         # Domain dashboards (50+)
│   └── ui/                    # Shadcn/Radix base components
│
├── contexts/                  # React shared state
│   ├── UserContext.tsx        # Auth user + permissions
│   ├── ThemeProvider.tsx      # Light/dark mode
│   └── FeaturesContext.tsx    # Feature flags
│
├── agent/                     # Distributed agent system
│   ├── agent.py               # Main agent loop (entry point)
│   ├── agentic_core/          # LLM, reasoning, safety, tool registry
│   ├── capabilities/          # 46 monitoring/security/patching modules
│   ├── autonomous_actions/    # Remediation + rollback engine
│   ├── swarm/                 # Multi-agent coordination
│   └── goal_system/           # Goal-driven autonomy
│
├── nginx/                     # Production nginx config
├── kubernetes/                # K8s manifests
├── helm/                      # Helm charts
├── docs/                      # Documentation
└── .github/workflows/         # CI/CD pipelines
```
