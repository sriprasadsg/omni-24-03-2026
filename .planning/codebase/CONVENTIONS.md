# Coding Conventions

**Analysis Date:** 2026-06-17

## Naming Patterns

**Files:**
- Python: `snake_case` (e.g., `authentication_service.py`, `rate_limiter.py`, `websocket_manager.py`)
- TypeScript/React: `camelCase` or `PascalCase` (e.g., `apiService.ts`, `LlmSettings.tsx`, `MitreAttackHeatmap.tsx`)
- Components: `PascalCase` with `.tsx` extension (e.g., `AgentList.tsx`, `ConfirmationModal.tsx`)
- Tests: `test_*.py` or `*.test.ts` pattern (e.g., `test_compliance.py`, `test_ai_remediation.py`)

**Functions:**
- Python: `snake_case` (e.g., `create_access_token()`, `verify_token()`, `get_attack_paths()`)
- Python async: prefix with `async` keyword (e.g., `async def get_provider_for_tenant()`)
- TypeScript: `camelCase` (e.g., `fetchSboms()`, `uploadSbom()`, `jwtSecondsUntilExpiry()`)
- React components: `PascalCase` (e.g., `LlmSettings`, `MitreAttackHeatmap`)

**Variables:**
- Python: `snake_case` (e.g., `_revoked_jti_cache`, `_REFRESH_BACKOFF_MS`, `configured_provider`)
- Module-level constants: `SCREAMING_SNAKE_CASE` (e.g., `MAX_CONNECTIONS_PER_TENANT`, `ACCESS_TOKEN_EXPIRE_MINUTES`)
- TypeScript: `camelCase` for variables, `SCREAMING_SNAKE_CASE` for constants (e.g., `POLL_INTERVAL_MS`, `API_BASE`)
- Private variables (Python): prefix with `_` (e.g., `_revocation_cache_last_sync`, `_storage_uri`)

**Types:**
- TypeScript: `PascalCase` (e.g., `LlmSettingsType`, `AgentStatus`, `Filter`)
- Python type hints: inline annotations (e.g., `Dict[str, Any]`, `Optional[AIProvider]`, `List[Dict[str, Any]]`)
- React interfaces: `PascalCase` with `Props` suffix (e.g., `AgentListProps`, `LlmSettingsProps`)

## Code Style

**Formatting:**
- TypeScript/React: ESLint with typescript-eslint (see `eslint.config.js`)
- Currently permissive: many rules disabled (`@typescript-eslint/no-explicit-any`, `no-unused-vars`)
- No Prettier config enforced; relies on ESLint
- Max line length: no strict limit observed

**Linting:**
- ESLint rule: `'@typescript-eslint/no-explicit-any': 'off'` — `any` types are allowed
- ESLint rule: `'@typescript-eslint/no-unused-vars': 'off'` — unused variables permitted
- ESLint rule: `'react-hooks/exhaustive-deps': 'off'` — hook dependencies not validated

**Python:**
- Bandit security scanning enabled (see `pyproject.toml`)
- Security focus: parameter validation, environment variable security checks
- Docstring pattern: inline comments and print statements used for logging

## Import Organization

**Python Order:**
1. Standard library (`import os`, `from typing import`)
2. Third-party (`from fastapi import`, `from motor.motor_asyncio import`)
3. Local modules (`from authentication_service import`, `from database import`)

**TypeScript Order:**
1. External packages (`import React`, `import { io }`)
2. Internal services (`from '../services/apiService'`)
3. Internal types (`from '../types'`)
4. Internal components/contexts (`from '../contexts/UserContext'`)

**Path Aliases:**
- Frontend uses relative imports (e.g., `from '../services/apiService'`)
- Backend uses direct module imports (e.g., `from database import get_database`)

**Barrel Files:**
- Not observed in primary code; each file imports directly from source

## Error Handling

**Python Patterns:**
- Use `HTTPException` from FastAPI for API errors
- Pattern: `raise HTTPException(status_code=400, detail="message")` (`authentication_service.py`, `approval_endpoints.py`)
- Async verification: JWT validation raises `HTTPException(status_code=401, ...)` for auth failures
- Database errors: wrapped in try-except with logging (see `agent_heartbeat_endpoints.py`: `except Exception as e: logger.error("ERROR updating asset: %s", e)`)
- Tenant isolation: "Fail-Closed" pattern — missing tenant context raises error with emergency fallback (`database.py`, `TenantIsolatedCollection`)

**TypeScript Patterns:**
- Use `Error` class or throw strings (e.g., `throw new Error("Failed to fetch components")`)
- Pattern: `if (!res.ok) throw new Error(...)` after API calls (`apiService.ts`, `threatIntelService.ts`)
- Catch-all: empty catch blocks or silent fallbacks (e.g., `catch { return [] }`)
- Error logging: `console.error()` for exceptions (e.g., `console.error('[fetchSboms] Request failed:', err)`)

**Security-Specific Error Handling:**
- Database: Security alerts logged at error level for missing tenant context (`database.py`: `logging.error("[SECURITY ALERT] DB Access without tenant context...")`)
- Tokens: JWT decode failures raise 401 Unauthorized; revoked tokens checked against in-memory cache
- Rate limiting: uses SlowAPI with real socket IP, never X-Forwarded-For (see `rate_limiter.py`: `_real_ip()`)

## Logging

**Framework:**
- Python: `logging` module (stdlib)
- TypeScript: `console.error()`, `console.warn()`, `console.log()`

**Patterns:**
- Python: Each module defines `logger = logging.getLogger(__name__)` at top-level
- Log levels: `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`, `logger.exception()`
- Security alerts: logged as `logger.error("[SECURITY ALERT] message")`
- Startup warnings: `logger.warning("[StartupConfig] ...")` with emoji indicators (`app_startup.py`)
- Components: logged with event context (e.g., `logger.info("[AI] Using Omni-Local...")`, `logger.info("[RateLimiter] Redis configured")`)

**TypeScript:**
- Prefixed console logs (e.g., `console.log('[WebSocket] ✅ Connected')`, `console.error('[MITRE] Coverage fetch error')`)
- No dedicated logging library observed; direct console output

## Comments

**When to Comment:**
- Complex business logic (e.g., tenant isolation, attack pattern correlation)
- Non-obvious parameter handling or fallbacks
- Security-critical decisions (e.g., rate limiting keying strategy)
- TODO/FIXME markers allowed but discouraged in production code

**JSDoc/TSDoc:**
- Minimal usage observed
- Function docstrings in Python (e.g., `"""Builds real attack paths by correlating assets and open vulnerabilities."""`)
- React: interfaces documented inline (see `MitreAttackHeatmap.tsx`: interface definitions with field descriptions)
- No `@param`, `@returns` pattern enforced

**Docstring Style (Python):**
- Triple-quoted strings (e.g., `"""Instantiate and configure the right provider from a settings dict."""`)
- Placed immediately after function definition
- Describe purpose and high-level behavior, not implementation details

## Function Design

**Size:**
- No strict line limit enforced; observed range 20-200 lines
- Large services decomposed into methods (e.g., `CorrelationEngineCoreMixin` in `correlation_engine_core.py`)

**Parameters:**
- Python: use `Optional[Type]` for nullable parameters; `Dict[str, Any]` for flexible payloads
- TypeScript: optional props marked with `?` (e.g., `onDeleteAgent?: (agent: Agent) => void`)
- Avoid long parameter lists; use objects/interfaces instead (e.g., `LlmSettingsProps` interface)

**Return Values:**
- Python: Async functions return coroutines; use type hints (e.g., `async def get_attack_paths(...) -> List[Dict[str, Any]]`)
- TypeScript: Promise-based for async (e.g., `async () => Promise<ThreatIntelScan[]>`)
- Fallbacks: return empty collections on error (e.g., `except: return []` in TypeScript)

**Async/Await:**
- Python: `async def` / `await` pattern used throughout backend (see `ai_service.py`, `database.py`)
- Motor (MongoDB async driver): all operations are awaitable
- TypeScript: `async/await` for service calls (e.g., `const res = await authFetch(...)`)

## Module Design

**Exports:**
- Python: import specific classes/functions (e.g., `from authentication_service import verify_token`, `from database import TenantIsolatedCollection`)
- TypeScript: named exports (e.g., `export const fetchSboms = async (...)`) and type exports (e.g., `export type { LlmSettings }`)
- React: default export for components (e.g., `export default function MitreAttackHeatmap()`)

**Barrel Files:**
- apiService.ts re-exports types from types.ts (e.g., `export type { User, Role, ... }`)
- No index.ts pattern observed for component directories

**Singletons and Global State:**
- Python: module-level instances (e.g., `logger` in each file, `limiter` and `sio` in rate_limiter.py / websocket_manager.py)
- TypeScript: class instances with private state (e.g., `SocketService.private socket`, `private listeners`)
- React: Context providers for cross-component state (e.g., `UserContext`, `ThemeContext`)

## Async Patterns

**Python Async:**
- Motor AsyncIOMotorClient used for all database operations
- Pattern: `async def endpoint(...): result = await db.collection.find_one(...)` 
- Error handling: try-except wraps async calls; log exceptions, don't re-raise to endpoints

**TypeScript Async:**
- Use `async` arrow functions (e.g., `const fetchSboms = async (): Promise<Sbom[]> => { ... }`)
- Chain promises (e.g., `await Promise.all([authFetch(...), authFetch(...)])`)
- WebSocket: async event handling with error callbacks (`socket.on('event', async (data) => { ... })`)

## Security Patterns

**Authentication:**
- JWT tokens with HS256/HS384/HS512 algorithms
- Tokens include `sub` (username), `role`, `tenant_id`, `jti` (revocation), `exp` (expiry)
- Token refresh: check expiry before sending; refresh silently via `authFetch` if expired

**Authorization:**
- Tenant isolation: `TenantIsolatedCollection` wrapper injects `tenantId` into every query
- Fail-Closed: missing tenant context uses dummy ID `NON_EXISTENT_TENANT_ISOLATION_EMERGENCY`
- Super Admin bypass: `tenant_id == "platform-admin"` skips tenant filtering

**Rate Limiting:**
- Per-IP rate limiting: 200/minute, 2000/hour (global)
- Per-agent rate limiting: 60/minute
- Key function: real socket IP (never X-Forwarded-For header)
- Storage: Redis if available; falls back to in-memory

**CORS & WebSocket:**
- Socket.IO CORS: configurable via `SOCKETIO_CORS_ORIGINS` env var
- Development: `*` (all origins)
- Production: localhost only (`http://localhost:3000`, `http://127.0.0.1:5173`)
- Transports: polling first, then upgrade to WebSocket

## Testing Conventions

**File Naming:**
- Python: `test_*.py` (e.g., `test_compliance.py`, `test_ai_remediation.py`)
- TypeScript: `.test.ts` or `.spec.ts` (not observed in primary code)

**Test Structure (Python):**
- Use `unittest.mock.MagicMock` for mocking (see `test_ai_remediation.py`)
- Pytest patterns: plain functions prefixed `test_` 
- Setup: mock objects initialized in test function, not class-based setup

**Assertions:**
- Python: standard `assert` statements, not pytest `assert` idiom
- TypeScript: not yet implemented; vitest configured but no test files in src/

---

*Convention analysis: 2026-06-17*
