# Codebase Concerns

**Analysis Date:** 2026-06-17

## Tech Debt

### 1. File Size Violations (CLAUDE.md Rule: Keep files under 500 lines)

**Files exceeding 500-line limit:**
- `services/apiService.ts`: 4,202 lines - Monolithic API service layer with no separation of concerns
- `App.tsx`: 1,987 lines - Main React component with ~100+ lazy-loaded dashboards mixed into one file
- `agent/agent.py`: 2,186 lines - Massive agent controller with all capability dispatching in one module
- `components/InternalTicketsDashboard.tsx`: 1,511 lines - Single component file with embedded logic
- `types.ts`: 1,654 lines - Type definitions for entire system in one file
- `agent/capabilities/compliance.py`: 1,379 lines - Monolithic compliance capability
- `backend/siem_endpoints.py`: 736 lines
- `backend/connectors_hub_endpoints.py`: 632 lines
- `backend/app_startup.py`: 632 lines
- Multiple other files between 500-700 lines

**Impact:** Hard to maintain, test, and debug. Violates project CLAUDE.md rule. No clear separation of concerns.

**Fix approach:**
- Split `apiService.ts` into feature-specific modules (auth, agents, compliance, etc.)
- Extract lazy-loaded routes from `App.tsx` into a separate route configuration file
- Decompose `agent.py` into capability-specific handler modules
- Split large component files into smaller, reusable sub-components
- Create focused type definition files by domain

---

### 2. Widespread Bare `except Exception` Handlers (975 occurrences)

**Pattern observed:**
```python
except Exception:
    pass  # or minimal logging
except Exception:
    logger.warning("Generic error")
```

**Files with problematic exception handling:**
- `backend/webhook_endpoints.py`: Multiple bare `except Exception` with no logging
- `backend/remediation_service.py`: Silent exception swallowing
- `backend/dr_endpoints.py`: Two silent exception handlers
- `backend/threat_intel_endpoints.py`: Silent failure path
- `backend/siem_endpoints.py`: Multiple silent catches
- `backend/mfa_service.py`: Three bare exception blocks

**Impact:**
- Silent failures make debugging impossible. Production issues are invisible.
- Prevents proper error tracking and alerting.
- Makes user-facing APIs return ambiguous errors.
- Security issues can be hidden in exception paths.

**Fix approach:**
- Replace bare `except Exception` with specific exception types
- Always log with sufficient context (e.g., input data, operation being performed)
- For user-facing endpoints, log the full exception and return a generic HTTP 500, not a silent failure
- Use centralized error handling middleware to catch unhandled exceptions

---

### 3. Global Mutable Singletons (26+ instances)

**Pattern:** Module-level global state updated via `global` keyword

**Critical singletons creating race conditions or shared state issues:**
- `backend/authentication_service.py`: `_revoked_jti_cache` (set) - Thread-unsafe token revocation tracking
- `backend/authentication_service.py`: `_revocation_cache_last_sync` (float) - Last sync time, shared across workers
- `backend/websocket_manager.py`: `connected_clients` dict - Tracks WebSocket connections by tenant
- `backend/websocket_manager.py`: `agent_sessions` dict - Agent SID mapping
- `backend/websocket_manager.py`: `user_sessions` dict - User SID mapping
- `services/apiService.ts`: `SECURITY_CASES` (array) - In-memory cache of security cases
- `services/apiService.ts`: `SECURITY_EVENTS` (array) - In-memory cache of events
- `agent/agent.py`: `_pending_task_feedback` (list) - Buffer of task results
- `backend/circuit_breaker.py`: Global circuit breaker state
- `backend/rate_limiter.py`: In-memory rate limiter (single-instance only per `README`)

**Impact:**
- **Single-instance deployments only:** If this code is scaled to multiple workers/processes, all mutable state becomes inconsistent. The rate limiter explicitly falls back to in-memory only.
- **Race conditions:** Multiple async operations on the same dict/set can corrupt state.
- **Memory bloat:** Token revocation cache can grow unbounded (current code limits to 5000 JTIs per sync, but no eviction).
- **WebSocket state loss:** If a server restarts, all connected clients lose their sessions (no Redis persistence by default).

**Fix approach:**
- Migrate all mutable state to Redis (already partial support via `REDIS_URL`)
- Make `_revoked_jti_cache` a TTL-based in-memory cache with periodic full sync (already implemented partially)
- Use async-safe data structures or locks for shared state
- Implement proper connection recovery for WebSocket clients
- Validate multi-worker deployments with actual load tests

---

### 4. Agent Instruction Polling Design Bug

**File:** `agent/agent.py` lines 1498-1598 (`check_and_execute_instructions`)

**Pattern observed:**
```python
def check_and_execute_instructions(cfg, capability_mgr):
    agent_id = capability_mgr.agent_id   # Uses registered agent_id
    url = f"{base_url}/api/agents/{agent_id}/instructions"
    # ... polls every N seconds via heartbeat loop
```

**Problem:**
1. **Polling creates scalability ceiling:** Every agent polls every 5 seconds. With 10,000 agents, this creates 120,000 requests/minute to a single endpoint.
2. **Instruction delivery latency:** Instructions are not delivered immediately. Worst-case: 5 seconds before agent sees instruction.
3. **No acknowledgment on failure:** If an agent crashes mid-instruction, the instruction remains marked as pending forever (or times out).
4. **Race condition on instruction state:** Multiple agents polling the same endpoint could execute the same instruction if not properly idempotent.
5. **Missing instruction deduplication:** No check for duplicate instruction execution. A crashed agent that restarts could re-execute old instructions.

**Documented in:** `backend/check_remote_status.py` contains reference to "[BUG CONFIRMED]"

**Impact:**
- **Scalability:** System cannot support 10,000+ agents simultaneously.
- **Reliability:** Instructions may never reach agents if polling window misses the delivery window.
- **Idempotency:** Operations like "Install Patch KB12345" could run twice if agent restarts.

**Fix approach:**
- Replace polling with WebSocket event subscriptions (bidirectional). See `websocket_manager.py` — infrastructure exists.
- Add instruction acknowledgment handshake: agent receives → agent executes → agent sends result → backend removes from queue.
- Implement idempotent instruction execution with deduplication key (instruction_id + checksum).
- Add instruction TTL: if not executed within X minutes, mark as failed and alert admin.

---

## Known Bugs

### 1. Database Fail-Closed Tenant Isolation Creates Orphaned Data

**File:** `backend/database.py` lines 29-39

**Issue:**
```python
# Fail-Closed: If no tenant_id is found and not in platform-admin context, 
# it enforces a non-matching tenantId to prevent accidental data leakage.
effective_tenant_id = tenant_id if tenant_id else "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
```

**Problem:**
- When tenant context is lost (e.g., database call outside async context, missing middleware), records are tagged with `"NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"`.
- This creates unfindable orphaned records that accumulate over time.
- Logs show "SECURITY ALERT: DB Access without tenant context" but code continues to insert data.
- No cleanup process exists to remove these orphaned records.

**Impact:**
- Orphaned data accumulates in MongoDB without operator visibility.
- Debugging why records are missing becomes difficult (they exist but under dummy tenant ID).

**Fix approach:**
- Change fail-closed strategy: raise exception if tenant_id is missing in production (don't insert).
- Create periodic cleanup job to remove records with dummy tenant IDs.
- Add metrics/alerts for orphaned data creation.

---

### 2. JWT Token Revocation Cache May Never Sync

**File:** `backend/authentication_service.py` lines 135-149

**Issue:**
```python
global _revocation_cache_last_sync
now = _time.monotonic()
if now - _revocation_cache_last_sync > 60:  # refresh every 60 s
    _revocation_cache_last_sync = now
    async for doc in db._db.revoked_tokens.find({}, {"jti": 1, "_id": 0}).limit(5000):
```

**Problem:**
1. **No initialization:** `_revocation_cache_last_sync` is never initialized (starts at 0.0), so first call always syncs.
2. **Unbounded cache:** If more than 5000 tokens are revoked, older revocations are never loaded into in-process cache.
3. **No eviction:** Revoked tokens are never removed from `_revoked_jti_cache` — it only grows.
4. **Race condition:** Multiple async workers calling `verify_token_async` simultaneously could all trigger syncs at the same time, causing thundering herd.

**Impact:**
- After logout, users can still make requests with revoked tokens (until next 60-second sync).
- Memory usage of token revocation cache grows unbounded.
- With >5000 revoked tokens, older revocations are lost.

**Fix approach:**
- Initialize `_revocation_cache_last_sync` to current time at module load.
- Implement TTL-based eviction: remove revoked tokens from in-process cache after their JWT expiry time + grace period.
- Add a lock to prevent thundering herd on sync.
- Paginate the revocation list properly (currently only queries first 5000).

---

### 3. Rate Limiter Fails to Distributed Setups Without Redis

**File:** `backend/rate_limiter.py` lines 30-46

**Issue:**
```python
def _make_storage_uri() -> str | None:
    # Falls back to in-memory if REDIS_URL is unset or unreachable
    if not _REDIS_URL:
        logger.info("[RateLimiter] Redis not configured (REDIS_URL unset); using in-memory")
        return None  # Falls back to in-memory (single-instance only)
```

**Problem:**
- If Redis is unavailable at startup, rate limiting silently falls back to in-memory.
- With multiple app instances, each instance has its own rate limiter — 3 instances = 3x the allowed rate.
- No warning after startup if this fallback happened (only logged at init time).
- An attacker can exceed rate limits by load-balancing across multiple instances.

**Impact:**
- Rate limiting is ineffective in horizontally-scaled deployments without Redis.
- DDoS attacks bypass rate limits by hitting multiple instances.

**Fix approach:**
- Make Redis required in production (`ENVIRONMENT=production`).
- Raise startup error if Redis is unavailable in production, don't silently degrade.
- Add periodic Redis connectivity checks and alerting.

---

## Security Considerations

### 1. AI Service Fallback Chain Accepts Any Provider Configuration

**File:** `backend/ai_service.py` lines 92-194

**Issue:**
```python
# Tries: OmniLocal → Env LLM_PROVIDER → DB settings → Ollama → Gemini → MockProvider
if not env_provider:
    if os.getenv("ANTHROPIC_API_KEY"):
        # Try Anthropic
    if os.getenv("GEMINI_API_KEY"):
        # Try Gemini

# Final fallback if nothing works
self.provider = MockProvider()  # Always succeeds
```

**Problem:**
1. **No validation of API keys:** If `ANTHROPIC_API_KEY` env var is set but contains garbage, the provider silently fails and cascades.
2. **Verbose fallback chain:** An attacker who can inspect logs can see which providers are tried.
3. **Silent MockProvider fallback:** If all external LLM providers fail, the system uses a rule-based MockProvider that returns empty responses.
4. **Prompt injection risk:** No input validation before sending to LLM. User queries go directly to LLM without guardrails applied.

**Impact:**
- Prompt injection attacks can be executed via user input fields.
- LLM configuration errors are silently masked.
- Malicious actors can determine LLM provider chain from logs.

**Fix approach:**
- Validate API keys at startup (make a test call).
- Fail startup if no working LLM provider is available (don't fall back to MockProvider silently).
- Apply input validation + guardrails before *every* LLM call (currently done via `guardrail_service`, but not enforced at call sites).
- Remove verbose provider chain logging; replace with single "Using provider: X" message.

---

### 2. WebSocket Authentication Performed in Connect Handler with Async/Sync Mismatch

**File:** `backend/websocket_manager.py` lines 144-150

**Issue:**
```python
try:
    from database import get_database
    db = get_database()
    import asyncio
    agent_doc = asyncio.get_event_loop().run_until_complete(
        db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 1})
    ) if not asyncio.get_event_loop().is_running() else None
except Exception:
    agent_doc = None
```

**Problem:**
1. **Async/sync confusion:** Uses `run_until_complete()` to run async code in a sync context, but then checks `is_running()` (which will be True inside async handler).
2. **Silent authentication failure:** If any exception occurs, `agent_doc = None`, allowing the connection to proceed unchecked.
3. **No agent verification:** Agent ID is trusted but never verified to exist; silently proceeds if DB fails.
4. **Race condition:** Agent could be deleted between check and use.

**Impact:**
- WebSocket connection succeeds even if agent doesn't exist or is unauthorized.
- Silent database failures mask authentication problems.

**Fix approach:**
- Refactor connect handler to be fully async (python-socketio supports it).
- Verify agent exists and belongs to claimed tenant before allowing connection.
- Raise `ConnectionRefusedError` on auth failure instead of silently proceeding.
- Add logging for all auth failures (currently silent except for early token/tenant checks).

---

### 3. Agent Configuration Broadcast Over HTTP Without Validation

**File:** `agent/agent.py` lines 250-284 (Registration flow)

**Issue:**
- Agent receives `agent_token` and `agent_id` from HTTP response, stores in plaintext in `config.yaml`.
- No signature verification on registration response.
- Registration response contains sensitive auth token transmitted via HTTP (if not HTTPS).

**Problem:**
1. **No response validation:** Response could be intercepted/modified by MITM attack.
2. **Plaintext credential storage:** Token stored in `config.yaml` on disk. If agent machine is compromised, attacker gets token.
3. **No HTTPS enforcement:** Code doesn't verify HTTPS is used for registration.

**Impact:**
- Agent tokens can be stolen via MITM attack during registration.
- Compromised agent machines leak auth tokens via config file.

**Fix approach:**
- Verify registration response via HMAC signature (sign response with a pre-shared registration key).
- Encrypt sensitive credentials before storing in `config.yaml` (infrastructure exists: `security_mgr.encrypt_data()`).
- Enforce HTTPS for API base URL validation (reject `http://` in production).
- Store agent token in encrypted local keystore, not plaintext YAML.

---

## Performance Bottlenecks

### 1. Large Component Lazy-Loading Creates Initial Render Stalls

**File:** `App.tsx` lines 28-150

**Issue:**
- App.tsx dynamically imports 90+ lazy-loaded components
- Each lazy import is a separate bundle chunk: `CXODashboard`, `ReportingDashboard`, `AgentsDashboard`, etc.
- Router dynamically mounts components based on `currentTab`
- No prefetching strategy

**Impact:**
- First navigation to any heavy dashboard (e.g., `EDRDashboard`, `SecurityDashboard`) causes 2-3 second lag while chunk loads.
- Network waterfalls: component loads → requests data → renders.

**Fix approach:**
- Prefetch high-priority dashboards (based on user role/recent usage).
- Use route-based code splitting with React Router v6 lazy/Suspense.
- Add skeleton loaders while chunks are loading.

---

### 2. Unbounded In-Memory Caches Cause Memory Leaks

**Files:**
- `services/apiService.ts`: `SECURITY_CASES`, `SECURITY_EVENTS` arrays grow indefinitely
- `backend/websocket_manager.py`: `connected_clients` dict grows with every connection
- `backend/authentication_service.py`: `_revoked_jti_cache` grows with every logout

**Impact:**
- Frontend service: after 24 hours of operation, apiService memory usage grows unbounded.
- WebSocket manager: with 10,000 concurrent connections, dict consumes significant memory.
- Token cache: after 1 million logins/logouts, token cache contains 1 million+ entries (if no eviction).

**Fix approach:**
- Implement LRU cache with max size for all in-memory caches.
- Add TTL-based eviction (remove entries older than token expiry + grace period).
- Monitor cache sizes and alert if they exceed thresholds.

---

### 3. Polling-Based Instruction Delivery Creates Scalability Cliff

**File:** `agent/agent.py` lines 1495-1598

**Issue:**
- Every agent polls `/api/agents/{agent_id}/instructions` every 5 seconds.
- Each poll fetches all pending instructions (no pagination/filtering).
- No batching: 10,000 agents = 120,000 HTTP requests/minute to backend.

**Impact:**
- With 1,000 agents: ~200 requests/sec to instruction endpoint.
- With 10,000 agents: ~2,000 requests/sec (hits typical API limits).
- Instruction latency: average 2.5 seconds (0-5 second polling window).
- Cold start on agent registration: agent immediately starts polling, but no instructions exist (wasted requests).

**Fix approach:**
- Replace polling with WebSocket subscription (bidirectional).
- Batch multi-agent instructions into single query (e.g., `/api/instructions/batch?agent_ids=...`).
- Add exponential backoff when no instructions are available.
- Implement server-sent events (SSE) or gRPC streaming as alternative if WebSocket not viable.

---

## Fragile Areas

### 1. Agentic Core Optional Imports With Silent Degradation

**File:** `agent/agent.py` lines 34-73

**Issue:**
```python
def _try_import(module_path: str, class_name: str):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name), None
    except Exception as _e:
        return None, str(_e)

AgenticLLM, _e = _try_import("agentic_core.llm_engine", "AgenticLLM")
if _e: _degraded.append(f"llm_engine ({_e})")
# ... 7 more optional imports
```

**Problem:**
- If any agentic module is missing, agent starts in "degraded mode" with AI capabilities disabled.
- No exception on degraded mode — silently continues.
- Admin may not know that autonomous remediation is disabled.
- Capabilities list is checked at runtime, so mis-installed packages aren't caught until agent starts executing.

**Impact:**
- Autonomous response actions don't execute (silently).
- Security incidents go unresponded because remediation is disabled.
- No alerting that agentic core is unavailable.

**Fix approach:**
- In production, require all agentic modules to be present. Fail startup with clear error if missing.
- In development, allow degraded mode but log at ERROR level (not WARNING).
- Add health check endpoint that reports which capabilities are available.

---

### 2. Tenant Context Lost in Non-Async Database Calls

**File:** `backend/database.py` lines 22-39

**Issue:**
```python
def _inject_tenant_id(self, filter_query: Dict[str, Any]) -> Dict[str, Any]:
    tenant_id = get_tenant_id()  # Looks up contextvars
    if not tenant_id:
        logging.error(f"[SECURITY ALERT] DB Access without tenant context")
        effective_tenant_id = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
```

**Problem:**
- Any non-async database call outside of FastAPI request context loses tenant context.
- Scheduled jobs, background tasks, and event handlers may not have tenant context set.
- Error logging created but data is still inserted under dummy tenant.
- No way for developer to know a function needs to set tenant context.

**Impact:**
- Data access is silently broken for background jobs.
- Orphaned records accumulate.
- Difficult to debug cross-tenant data leaks.

**Fix approach:**
- Make tenant_id a required parameter instead of relying on context (explicit is better than implicit).
- Create a decorator `@require_tenant_context` that raises if tenant_id is missing.
- For background jobs, explicitly set tenant_id before calling database methods.
- Add type hints to collection methods to show tenant_id is required.

---

### 3. MongoDB Connection Pool Not Configured for Scaling

**File:** `backend/database.py` lines 170-198

**Issue:**
```python
client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=3000)
```

**Problem:**
- No `maxPoolSize` configured (defaults to 50 connections per server).
- With 100+ concurrent API workers, connection pool exhaustion occurs.
- No connection retry logic beyond initial 3 attempts.
- Timeout is 3 seconds (may be too short for high-load scenarios).

**Impact:**
- Under load, database operations fail with "connection pool exhausted" errors.
- No graceful degradation; clients get 500 errors instead of queued requests.

**Fix approach:**
- Set `maxPoolSize=min(cpu_count * 4, 200)` based on deployment scale.
- Set `minPoolSize=10` to maintain baseline connections.
- Add `maxIdleTimeMS=300000` to reclaim unused connections.
- Implement connection pool monitoring and alerting.

---

## Test Coverage Gaps

### 1. No Tests for Multi-Tenant Data Isolation

**Files affected:**
- `backend/database.py` (TenantIsolatedCollection)
- All API endpoints that use the database

**What's missing:**
- Test that accessing tenant A's data while authenticated as tenant B fails.
- Test that database queries automatically inject tenant_id filter.
- Test orphaned data (records with dummy tenant ID) scenario.
- Test cross-tenant query attacks (e.g., intentionally omitting tenant filter in aggregation pipeline).

**Risk:** Cross-tenant data leaks could occur silently.

**Priority:** HIGH

---

### 2. No Tests for Agent Instruction Polling Edge Cases

**Files affected:**
- `agent/agent.py` (check_and_execute_instructions)

**What's missing:**
- Test duplicate instruction execution (agent restarts mid-execution).
- Test instruction timeout (instruction in queue for >5 min, agent never sees it).
- Test race condition (multiple agents polling same endpoint simultaneously).
- Test instruction acknowledgment failure (agent executes but result POST fails).

**Risk:** Instructions silently fail or execute multiple times.

**Priority:** HIGH

---

### 3. No Load/Scalability Tests

**What's missing:**
- Test system with 1,000+ concurrent agents polling simultaneously.
- Test WebSocket connection scaling (10,000+ concurrent connections).
- Test database query performance under load (1 million records per collection).
- Test memory usage over 24-hour operation (detect leaks).

**Risk:** System works in testing but fails in production.

**Priority:** MEDIUM

---

## Scaling Limits

### 1. Agent Instruction Polling Hits Scalability Ceiling at ~5,000 Agents

**Current:**
- Each agent polls every 5 seconds.
- With N agents: N / 5 requests/sec to instruction endpoint.

**Limit:**
- Typical API can handle ~500 requests/sec.
- At 5,000 agents: 1,000 req/sec → Exceeds capacity.
- Current system supports: ~2,500 agents max (500 req/sec limit).

**Migration path:**
- Switch to WebSocket-based push (each agent = 1 persistent connection, not 1 request per 5 seconds).
- WebSocket overhead: ~100KB per connection. 10,000 agents = ~1GB RAM (acceptable).

---

### 2. Single MongoDB Instance Becomes Bottleneck

**Current:**
- All tenants' data in single `omni_platform` database.
- No sharding configured.

**Limit:**
- MongoDB can handle ~10,000 concurrent connections.
- Each API worker takes 1-3 connections; with 100 workers = 100-300 connections (OK).
- Query latency degrades with >1TB of data or >100K queries/sec.

**Migration path:**
- Implement multi-database sharding by tenant (tenant A → db_tenant_a, tenant B → db_tenant_b).
- Add read replicas for reporting queries.

---

### 3. In-Memory Rate Limiter Doesn't Scale Horizontally

**Current:**
- Rate limiter uses in-memory storage if Redis is unavailable.
- Each instance has independent rate limits.

**Limit:**
- 3 API instances × 200 req/min per instance = 600 req/min effective limit.
- But advertised limit is 200 req/min (misleading to clients).

**Migration path:**
- Make Redis required for production deployments.
- Implement Redis-based rate limiting with proper key expiration.

---

## Dependencies at Risk

### 1. Deprecated `python-socketio` 5.x

**File:** `backend/websocket_manager.py` (uses `socketio.AsyncServer`)

**Issue:**
- `python-socketio` 5.x is in maintenance mode; 6.x is current.
- Version 5.x has known limitations in async context handling (see WebSocket bug #2 above).

**Impact:**
- Security patches will eventually stop.
- Async bugs in 5.x are not being fixed.

**Migration path:**
- Update to `python-socketio` 6.x (requires testing for breaking changes).
- Or switch to native FastAPI WebSockets (no third-party dependency).

---

### 2. JWT Library Without RS256 Support

**File:** `backend/authentication_service.py` lines 32-38

**Issue:**
- Only HMAC algorithms supported (HS256/384/512).
- Limits to symmetric keys shared across all services.

**Problem:**
- HMAC keys are secrets; if exposed, attacker can forge tokens.
- RS256 (RSA) allows public verification without exposing private key.
- Microservices architecture requires asymmetric cryptography.

**Impact:**
- Limited deployment topologies.
- Higher key rotation complexity.

**Migration path:**
- Add RS256 support to authentication_service.py.
- Migrate to asymmetric key pair for token signing.

---

## Missing Critical Features

### 1. No Instruction Idempotency

**Problem:**
- If agent crashes during instruction execution (e.g., "Install Patch KB12345"), instruction remains pending.
- When agent restarts, it polls and re-executes the same instruction.
- Result: Patch installed twice, or conflicting states.

**Blocks:**
- Safe autonomous remediation at scale.
- Any destructive operations (delete, uninstall, etc.).

**Recommendation:**
- Add idempotency keys to all instructions.
- Track instruction execution by checksum + instruction_id.
- Implement idempotent handlers for all capabilities (check if action already done before executing).

---

### 2. No Distributed Tracing Across Agents

**Problem:**
- Trace requests from UI → Backend → Agent, but each system has independent tracing.
- Impossible to correlate logs across the stack.

**Blocks:**
- Debugging complex failures (UI says "success" but agent says "error").
- Performance profiling end-to-end.

**Recommendation:**
- Add OpenTelemetry instrumentation to backend, frontend, and agents.
- Propagate trace IDs in all HTTP/WebSocket requests.
- Correlate logs by trace ID in centralized logging.

---

### 3. No Agent Health Monitoring Dashboard

**Problem:**
- Agent `heartbeat_endpoints.py` exists but no UI to see which agents are unhealthy.
- Admins must manually check agent status.

**Blocks:**
- Rapid response to agent failures.
- Capacity planning (knowing how many agents are active).

**Recommendation:**
- Add `/api/agents/health/summary` endpoint showing:
  - Total agents online/offline
  - Agents with capabilities disabled (degraded mode)
  - Agents with old agent versions
  - Agents with high error rates
- Add AgentHealthDashboard component to show this data.

---

## Security Hotspots Summary

| Hotspot | Severity | File | Quick Mitigation |
|---------|----------|------|------------------|
| Bare `except Exception` handlers | HIGH | Multiple | Add logging; catch specific exceptions |
| Global mutable state in single-instance only | HIGH | `authentication_service.py`, `websocket_manager.py` | Document as single-instance; migrate to Redis |
| Agent polling bug (scalability) | MEDIUM | `agent/agent.py` | Switch to WebSocket push |
| JWT revocation cache unbounded | MEDIUM | `authentication_service.py` | Add TTL-based eviction |
| Agent config stored in plaintext | MEDIUM | `agent/agent.py` | Encrypt token in config file |
| No input validation before LLM calls | MEDIUM | `ai_service.py` | Apply guardrails at all call sites |
| Rate limiter falls back silently | MEDIUM | `rate_limiter.py` | Make Redis required in production |
| WebSocket auth with async/sync mismatch | LOW | `websocket_manager.py` | Refactor connect handler to async |

---

*Concerns audit: 2026-06-17*
