# Phase 81: Autonomy Gate, Stop Switch & Activity Ledger - Pattern Map

**Mapped:** 2026-10-25
**Files analyzed:** 36 (new and modified)
**Analogs found:** 30 / 36 (all analog paths verified git-tracked; line numbers are from the working tree and may shift by a few lines where files carry unrelated uncommitted hunks)

D-21..D-25 in 81-CONTEXT.md override 81-RESEARCH.md where they differ (unticked tenant = Off and nothing recorded; Analyst, not Auditor; Platform tenant stored Off; platform-wide Stop/Resume buttons ship).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/autonomous_ops/__init__.py` | config | n/a | `backend/rbac_defaults.py` (constant frozensets) | role-match |
| `backend/autonomous_ops/messages.py` | utility | transform | none (see No Analog) | none |
| `backend/autonomous_ops/settings.py` | service | CRUD + cache, fail closed | `backend/tenant_features.py::enabled_features` (raw handle, explicit id, errors propagate) | role-match |
| `backend/autonomous_ops/registry.py` | config | transform | `backend/remediation_playbook_service.py` `ACTION_MAP` | role-match |
| `backend/autonomous_ops/protected.py` | utility | transform | none in repo; stdlib `ipaddress` + `psutil` (RESEARCH Q6) | none |
| `backend/autonomous_ops/ledger.py` | service | CRUD (CAS) + audit mirror | `backend/audit_ledger.py` (`event`, never raises) + `backend/distributed_lock.py` (`find_one_and_update` CAS) | role-match |
| `backend/autonomous_ops/gate.py` | service | request-response (ordered decision) | `backend/autonomous_remediation_service.py` `remediate()`/`approve_remediation()` | role-match |
| `backend/autonomous_ops/delivery.py` | middleware | request-response (poll hook) | `backend/agent_capabilities.py::hold_back` (199-216) | exact |
| `backend/autonomous_ops/reconciler.py` | service | batch (loop under lock) | `backend/scheduler.py` lock idiom (105-111) | role-match |
| `backend/autonomous_ops/notify.py` | utility | event-driven | `backend/pending_agents.py::post_to_recipients` (289) | exact |
| `backend/autonomous_ops/scope.py` | utility | transform | `backend/scheduler.py` `set_tenant_id` + `reset_tenant_id` in `finally` | role-match |
| `backend/distributed_lock.py` (modify: `renew_lock`, `lock_with_renewal`) | utility | CRUD | itself (acquire/release) | exact |
| `backend/autonomous_ops_endpoints.py` (router + platform_router) | controller | request-response | `backend/remediation_control_endpoints.py` + `backend/platform_endpoints.py` | role-match |
| `backend/catalogue_mounts_autonomous_ops.py` | config | n/a | `backend/catalogue_mounts_settings_ops.py` (`WEBHOOKS_GUARD`, `MOUNTS`) | exact |
| `backend/migrations/024_autonomous_ops.py` | migration | batch | `backend/migrations/023_hadr_platform_only.py`, `022_security_compliance_screens_explicit.py` | role-match |
| `backend/router_registry.py` (modify) | config | n/a | existing `_load(app, ...)` lines near 410 | exact |
| `shared/catalogue-access.json`, `shared/tenant-feature-switches.json` (modify) | config | n/a | neighbouring `automation` group entries (`view:automation`/`manage:automation`) | exact |
| `backend/rbac_defaults.py` (modify) | config | n/a | itself (`PLATFORM_ONLY_PERMISSIONS` 169-175, `ADMIN_TIER_PERMISSIONS` 181-187, `ROLE_DEFAULTS`) | exact |
| `backend/agent_capabilities.py` (modify `_INSTRUCTIONS`) | config | n/a | itself (lines ~73-77) | exact |
| `backend/agent_tasks_endpoints.py`, `backend/deployment_result_endpoints.py`, `backend/agent_instruction_endpoints.py` (modify) | controller | request-response | the `hold_back` call sites | exact |
| `backend/autonomous_remediation_service.py` (modify: route via gate, delete legacy) | service | request-response | itself | exact |
| `backend/app_background_tasks.py`, `backend/app_startup.py` (modify) | config | event-driven | `_safe_bg_task` registrations (~462-478) | exact |
| `backend/backend_safety.py`, `backend/response_orchestrator.py` (modify) | service | transform | themselves | exact |
| `backend/correlation_engine_threat.py`, `correlation_engine_response.py`, `playbook_engine_actions.py` (D-21 fence) | service | event-driven | themselves; gate call mirrors `remediate()` | role-match |
| `backend/remediation_control_endpoints.py` (modify permission) | controller | request-response | itself (`_require_ops_permission`) | exact |
| `backend/authentication_endpoints.py`, `backend/tenant_endpoints.py` (call `ensure_tenant`) | controller | CRUD | their `tenants.insert_one` sites | exact |
| `backend/tests/test_autonomous_ops_*.py`, `tests/autonomy_support.py` | test | CRUD / request-response | `backend/tests/test_audit_ledger.py`, `tests/_mongo_test_db.py::mongo_db` | role-match |
| `backend/tests/test_autonomous_ops_copy.py`, `src/__tests__/autonomousOpsCopy.test.ts`, `shared/autonomous-ops-banned-terms.json` | test/config | transform | `src/__tests__/catalogueAccess.test.ts` (`read()` helper), manifest drift tests | role-match |
| `components/AutonomousOpsActivity.tsx` | component | request-response (paged list) | `components/AgentsDashboard.tsx` + `components/NoAccessPanel.tsx` (conventions) | role-match |
| `components/AutonomousOpsStopBanner.tsx` | component | polling | shell bar in `App.tsx` ("Backend connection lost") | role-match |
| `services/autonomousOpsApi.ts` | service | request-response | `services/roleApi.ts` | exact |
| `types.ts`, `components/sidebarPresentation.tsx`, `App.tsx` (modify) | config | n/a | existing `AppView`/`Permission` unions, `SIDEBAR_PRESENTATION`, lazy `case` | exact |
| `agent-install/omni-agent-rs/tests/integration.rs` + todo move | test | n/a | already fixed by `c5a2e57ee`; re-run only | n/a |

## Pattern Assignments

### `backend/autonomous_ops/delivery.py` (middleware, poll hook)

**Analog:** `backend/agent_capabilities.py::hold_back` (lines 199-216)

**Core pattern** (early return with no DB call when nothing to do; refuse by marking terminal status, never deliver):
```python
async def hold_back(db, tenant_id, instructions):
    if not instructions:
        return instructions
    ...
    await db.agent_instructions.update_one(
        {"_id": instr["_id"]},
        {"$set": {"status": REFUSED, "error": f"capability_not_enabled: {cap}",
                  "refused_at": datetime.now(timezone.utc).isoformat()}})
    return [instr for instr, _ in deliver]
```
Copy: `hold_back_autonomous(db, tenant_id, instructions)` returns early when no instruction carries the `autonomy` stamp (keeps MagicMock poll tests green); withhold on any read error (fail closed); mark `cancelled_by_stop`. Use the raw handle and explicit `tenantId`.

**Call sites** (insert directly after the existing call, before the `status: "sent"` update):
- `backend/agent_tasks_endpoints.py:47`: `instructions = await agent_capabilities.hold_back(db, tenant_id, instructions)`
- `backend/deployment_result_endpoints.py:93-97`: `instructions = await agent_capabilities.hold_back(db, caller_tenant_id, instructions)`
- `backend/agent_instruction_endpoints.py`: unmounted third handler; hook or delete (RESEARCH Q4).
- Third queue (D-21): the `response_tasks` poll path gets the same stop hold-back.

---

### `backend/distributed_lock.py` (add `renew_lock`, `lock_with_renewal`)

**Analog:** same file, lines 20-60.

**Imports/idiom:**
```python
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
DEFAULT_LOCK_TTL_SECONDS = 300
async def acquire_lock(db, name, ttl_seconds=DEFAULT_LOCK_TTL_SECONDS) -> Optional[str]:
    await db._db["_distributed_locks"].find_one_and_update(
        {"_id": name, "expiresAt": {"$lt": now}},
        {"$set": {"expiresAt": now + timedelta(seconds=ttl_seconds), "token": token}}, upsert=True)
async def release_lock(db, name, token):
    await db._db["_distributed_locks"].delete_one({"_id": name, "token": token})
```
Add `renew_lock` filtered on `{"_id": name, "token": token, "expiresAt": {"$gt": now}}` returning `matched_count == 1` (RESEARCH Q7 snippet). Raw `db._db` is deliberate here.

**Caller idiom to copy for `reconciler.py`:** `backend/scheduler.py` 103-111: `lock_token = await acquire_lock(lock_db, "<name>", ttl_seconds=...)`; `if not lock_token: return`; `set_tenant_id(...)` then `try: ... finally:` reset and `release_lock`. Reset tenant context per iteration in `finally` (the legacy `autonomous_remediation_loop` leaks all but the last token).

---

### `backend/autonomous_ops/ledger.py` (service, CAS + audit mirror)

**Analog:** `backend/audit_ledger.py::event` (line 203) and `backend/autonomous_remediation_service.py::approve_remediation` (611-632, the anti-pattern to replace).

**Audit mirror signature (never raises, spools on failure):**
```python
async def event(action: str, tenant_id: Optional[str], *, actor=None,
                outcome: str = "success", db=None, **fields) -> Dict[str, Any]:
    return await record(build(action, tenant_id, actor=actor, outcome=outcome, **fields), db=db)
```
Await it before dispatch so "intent before dispatch" holds in chain order. It cannot be the write-ahead guard; the intent row insert is (raise, then gate REFUSEs `ledger_unavailable`).

**Anti-pattern to replace** (read-then-unconditional-write, double-click race):
```python
req = await db.remediation_requests.find_one({"id": remediation_id, "tenantId": tenant_id})
if not req or req.get("status") != "pending_approval": return {"status": "not_found", ...}
await db.remediation_requests.update_one({"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "dispatching"}})
```
Replace with `transition()` using `find_one_and_update` with `{"state": {"$in": from_states}}` (RESEARCH Q5 snippet); `None` = lost the race.

---

### `backend/autonomous_ops/gate.py` and `autonomous_remediation_service.py` modifications

**Analog:** `AutonomousRemediationService.remediate()` (~548-609): keep the `remediation_requests` console row and `write_audit` stages; call `gate.decide(db, ActionRequest(...))` first and branch on outcome (RESEARCH Q1 wiring block). Replace both `execute_plan(...)` call sites (`_dispatch_step` ~760, `_check_nscan_resolved` ~864) with `gate.execute` before deleting `run_cycle`, `generate_plan`, `execute_plan`, `verify_remediation`, `_log_decision`, `_create_failure_ticket`, `_is_tenant_enabled`, `RemediationPlan`. Keep `SEVERITY_ORDER` (imported by `response_orchestrator.py:56`), `RemediationFinding`, `_render_step_params`, and the module constant `AUTONOMOUS_REMEDIATION_DRY_RUN` (tests patch it; pass it to the gate as the deployment master). Gate takes `tenant_id` explicitly, never the ContextVar, raw handle with explicit `tenantId`.

Stamp on every written instruction (RESEARCH Q4): `"triggered_by": "autonomous_ops", "autonomy": {"actionId", "tenantId", "kind"}, "tenantId": tenant_id`.

---

### `backend/autonomous_ops/settings.py` (service, fail-closed read)

**Analog:** `backend/tenant_features.py::enabled_features` (215-227):
```python
async def enabled_features(tenant_id, get_db):
    if not tenant_id: return []
    db = get_db()
    raw = getattr(db, "_db", db)
    doc = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0, "enabledFeatures": 1})
```
Copy raw-handle + explicit-id + errors-propagate-so-caller-fails-closed. Eligibility = literal `"view:autonomous_ops" in enabledFeatures` (not `switched_off()`). D-23: unticked = Off (refuse, record nothing); unreadable = Suggest. Platform stop: raw `system_settings` doc (precedent `raw.system_settings.find_one`, `agent_location_history_service.py:67`).

---

### `backend/autonomous_ops/notify.py` (utility, event-driven)

**Analog:** `backend/pending_agents.py::post_to_recipients` (289-295):
```python
async def post_to_recipients(raw, tenant, title, message, severity, metadata) -> None:
    await _post_in_app(raw, PLATFORM_TENANT_ID, title, message, severity, metadata)
    if tenant.get("id") and tenant["id"] != PLATFORM_TENANT_ID:
        await _post_in_app(raw, tenant["id"], title, message, severity, {**metadata, "audience": TENANT_ADMIN_AUDIENCE})
```
Single `notify()` seam; Phase 82 swaps it.

---

### `backend/autonomous_ops_endpoints.py` (controller, request-response)

**Analog 1 (tenant router, permission dependency shape):** `backend/remediation_control_endpoints.py` 1-25:
```python
router = APIRouter(prefix="/api/remediation", tags=["Remediation Control"])
async def _require_ops_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:active_response"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user
```
Keep calling `verify_permission` from that module (tests patch `remediation_control_endpoints.verify_permission`); change string to `control:autonomous_ops` (D-24c) and delegate to `gate.approve/deny`.

**Analog 2 (platform-only dependency):** `backend/rbac_utils.py:46-54` `has_platform_permission(user, permission)`. Platform router prefix `/api/platform/autonomous-ops` (already in `unownedPrefixes`, same prefix as `platform_endpoints.py` `router = APIRouter(prefix="/api", ...)` `/platform/features`); each route `Depends(_require_platform_autonomy_control)` checking `control:platform_autonomous_ops`.

**Interactive-session guard (D-10)**, named `_require_*` so `tests/_route_walk.py` `PERM_DEP` (`_require_`) counts it (RESEARCH code example):
```python
async def _require_interactive_session(user: TokenData = Depends(get_current_user_or_api_key)) -> TokenData:
    if getattr(user, "auth_source", "session") == "api_key":
        raise HTTPException(403, "An interactive sign-in is required for this action")
    return user
```
Apply to approve, deny, undo, clear-stop, level, never-touch, restore; NOT to press-stop. Platform-scope stop responses return `by = "Platform administrator"` to tenant viewers (D-25), decided server-side. Cross-tenant reads: explicit `tenantId` param honoured only when `can_read_all_tenants(user)` (precedent `audit_endpoints.py:31`, `tenant_endpoints.py:49`).

---

### `backend/catalogue_mounts_autonomous_ops.py` (config)

**Analog:** `backend/catalogue_mounts_settings_ops.py` (`WEBHOOKS_GUARD` ~line 78; in the cat output near 489-546) and billing slice header (guard + `MOUNTS`). API-key-capable guard:
```python
from api_key_auth import get_current_user_or_api_key
from catalogue_guards import catalogue_guard
AUTONOMOUS_OPS_GUARD = catalogue_guard("autonomousOps",
    read=("view:autonomous_ops",), write=("manage:autonomous_ops", "control:autonomous_ops"),
    auth=get_current_user_or_api_key)
MOUNTS = {("autonomous_ops_endpoints", "router"): AUTONOMOUS_OPS_GUARD}
```
`catalogue_guard` signature at `catalogue_guards.py:117-125` (`auth=get_current_user`, `platform_read=()`). `catalogue_mounts._collect` globs `catalogue_mounts_*.py`; guard read/write must equal the manifest's resolved lists. Do NOT use `platform_read=("view:tenants",)` (Billing also holds it; A8).

---

### `backend/migrations/024_autonomous_ops.py` (migration, batch)

**Analog:** `backend/migrations/023_hadr_platform_only.py`:
```python
from motor.motor_asyncio import AsyncIOMotorDatabase
DESCRIPTION = "Remove the HA/DR screen switch from every tenant"
async def up(db: AsyncIOMotorDatabase) -> None:
    await db.tenants.update_many(...)
```
`up(db)` receives the raw Motor database, version from filename, must be idempotent. Body per RESEARCH skeleton with D-24b: `platform-admin` -> `off`/`off`, every other tenant -> `undoable_auto`, `shadow: True`, `$setOnInsert` upsert, then `create_index` calls (unique `tenantId`, partial unique `(tenantId, dedupeKey)`, etc.). Next free number is 024 (022 exists as sibling).

---

### `backend/rbac_defaults.py` (modify)

**Analog:** same file, lines 169-187:
```python
PLATFORM_ONLY_PERMISSIONS: FrozenSet[str] = frozenset({"manage:pending_agents", ..., "view:tenants"})
ADMIN_TIER_PERMISSIONS: FrozenSet[str] = frozenset({"manage:users","manage:rbac","manage:settings",
    "manage:api_keys","control:remote_access"}) | PLATFORM_ONLY_PERMISSIONS
```
Add `control:platform_autonomous_ops` to `PLATFORM_ONLY_PERMISSIONS` (becomes admin-tier automatically) and literal `control:autonomous_ops` to `ADMIN_TIER_PERMISSIONS` (D-07). Role table (D-06/D-24a): `manage:` tenant_admin; `control:` tenant_admin, security_analyst, incident_responder; `view:` those plus `analyst` and `platform_support`. Goldens that must change in the same commit: `test_rbac_defaults.py` (GOLDEN + `GOLDEN_SIZES`), `test_custom_role_mfa.py`, `test_admin_mfa_required.py:60`, `test_platform_roles.py`. Count bumps 203/189 to 204/190 in `test_catalogue_manifest.py:147,161`, `test_closure_delivery.py:214`, `test_role_visibility.py:87`, `src/__tests__/catalogueAccess.test.ts:49`.

---

### `backend/agent_capabilities.py` (modify)

Add `restart_service`, `quarantine_file`, `unquarantine_file`, `restore_host` -> `remediation_executor` and `reboot_host` -> `patch_installer` to `_INSTRUCTIONS` (existing mapping at ~73-77 already holds `isolate_host`, `kill_process`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`, `rotate_key`, `rotate_key_rollback`). Keep `"autonomous_remediation": "autonomous_response"` (human `/rotate-key` writes it; `skill_handlers.py:177-192`).

---

### `backend/app_startup.py` and `app_background_tasks.py` (modify)

**Analog:** `app_startup.py:369` `_safe_bg_task(coro, name)` and registrations such as line 462:
```python
asyncio.create_task(_safe_bg_task(_start_xdr_correlation_scanner(), "xdr_correlation"), name="xdr_correlation")
```
Replace the legacy loop registration at 642-643 with `_safe_bg_task(reconciler_loop(), "autonomous_ops_reconciler")`. Delete `autonomous_remediation_loop` (app_background_tasks 10-40). `monitor_agent_status` fix (GATE-12 per D-24d): select Online-and-stale ids first, update by id, notify those; pin cadence with frozen-clock test. Both files carry unrelated uncommitted hunks: stage by path with hunk review only.

---

### `backend/correlation_engine_threat.py` / `correlation_engine_response.py` / `playbook_engine_actions.py` (D-21)

Targets: `_ai_select_playbook` (threat:48), `_fallback_select_playbook` (threat:102), `executed_by="xdr-auto"` (response:55), `_action_block_ip` (actions:108; also `_action_isolate_endpoint`, `_action_quarantine_file`, `rollback_ransomware`). Pattern: executors for `xdr-auto`/`ai-selector`/`fallback-selector` build an `ActionRequest` and call `gate.decide`; execute only on allow-auto, otherwise record the decision. Manual runs unchanged. `_action_block_ip` raises `ValueError("block_ip requires 'ip' and 'agent_id'")` for missing params: reuse that validation style before building the request. Remove `AUTO_APPROVE_CONFIDENCE_THRESHOLD` branch in `backend_safety.py::evaluate_action` (keep the keyword param, ignored; `playbook_engine_authority` importer `playbook_engine_safety.py:9`).

---

### `backend/response_orchestrator.py::is_duplicate_task` (modify, lines ~231-262)

Add `"tenantId": tenant_id` to both queries and return `True` when `tenant_id` is empty (fail closed). Real-Mongo two-tenant test.

---

### `services/autonomousOpsApi.ts` (service)

**Analog:** `services/roleApi.ts`:
```ts
import { API_BASE, authFetch } from './apiService';
export async function fetchRoleVisibility(roleId: string, tenantId?: string | null) {
    const res = await authFetch(withTenant(`${API_BASE}/roles/${encodeURIComponent(roleId)}/visibility`, tenantId));
    if (!res.ok) throw await failure(res, 'Could not load role visibility');
    return res.json();
}
export class RoleApiError extends Error { status: number; ... }
```
Copy: own module (not `apiService.ts`, 6334 lines), `withTenant`, `failure(res, fallback)`, typed error class carrying `status` (needed for UI 409 and 403 branches).

---

### `components/AutonomousOpsActivity.tsx`, `AutonomousOpsStopBanner.tsx`

**Analogs:** `components/NoAccessPanel.tsx` (imports `InfoIcon, ShieldLockIcon` from `./icons`, `SkeletonDashboard` from `./ui/skeleton`; props typed with `AppView, Permission` from `../types`) and `components/AgentsDashboard.tsx` for the Spatial Glass screen conventions. Follow 81-UI-SPEC.md for every primitive (`Modal size="md" showClose={false} closeOnBackdrop={false}`, `useUser().hasPermission`, `showToast`, `.card`). Banner mounts in `App.tsx` shell column above `<Header>`, only when `hasPermission('view:autonomous_ops')`. Do not collide with existing `AutonomousOpsLog.tsx` (Agents screen). One shared poller feeds banner and screen.

**Wiring (modify):** `types.ts` `AppView` + `Permission` unions (parsed by `catalogueAccess.test.ts` `unionMembers`), `components/sidebarPresentation.tsx` `SIDEBAR_PRESENTATION.autonomousOps` (pick a glyph different from the autopilot entry), `App.tsx` lazy `case 'autonomousOps'` (uncommitted unrelated hunks present: stage by hunk).

---

### Tests

**Real-Mongo fixture:** `backend/tests/_mongo_test_db.py` lines 15-28 `mongo_db` fixture (throwaway `omni_test_*` DB, skips if unreachable); use for CAS race (`asyncio.gather` of two approves, exactly one dispatch), lock renewal, two-tenant isolation, unique partial index. Header style of `tests/test_audit_ledger.py` (Value/protects/fails_when/no_claim docstring, `sys.path.insert(0, ...)`, httpx ASGI) is the project convention.
**Shared fake fixture:** new `tests/autonomy_support.py` used by `test_autonomous_remediation_loop.py`, `test_remediation_guards.py`, `test_ueba_remediation_trigger.py` (they patch `autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN` and use MagicMock dbs).
**Copy lint (ACTV-08):** `src/__tests__/catalogueAccess.test.ts` pattern:
```ts
const ROOT = resolve(__dirname, '../..');
const read = (rel: string) => readFileSync(resolve(ROOT, rel), 'utf-8');
```
Both pytest and vitest read `shared/autonomous-ops-banned-terms.json`; explicit file list; include negative controls; never scan `.planning/**`.
**Structural writer test (GATE-03):** AST/grep over backend modules writing `agent_instructions`/`instructions` against a committed grandfather list of 27 modules; separate LLM-import ban over `autonomous_ops/*.py`.

## Shared Patterns

### Raw handle plus explicit tenantId
**Source:** `backend/distributed_lock.py` (`db._db[...]`), `backend/tenant_features.py::enabled_features` (`getattr(db, "_db", db)`).
**Apply to:** every file in `backend/autonomous_ops/`. Never the ambient ContextVar: under `platform-admin` the wrapper injects no filter and stamps no `tenantId`. Use `scope.tenant_scope()` (set, reset in `finally`) only when calling tenant-wrapped helpers.

### Fail closed
**Source:** `agent_capabilities.hold_back` / `allowed_for`; `enabled_features` propagates errors.
**Apply to:** gate, settings, delivery. Unknown action, unreadable setting (Suggest), unreadable stop (stopped), ledger insert failure (REFUSE `ledger_unavailable`).

### Catalogue registration and drift tests
**Source:** `catalogue_guards.py:117`, `catalogue_mounts_*.py` `MOUNTS`, `shared/catalogue-access.json`.
**Apply to:** the router, manifest entry (`view: autonomousOps`, group `automation`), switches (`view:autonomous_ops`, `manage:autonomous_ops` with parent), `router_registry` `_load` lines. Run `test_catalogue_manifest`, `test_catalogue_route_parity`, `test_route_auth_baseline`, `test_audit_parity`, `test_tenant_feature_switches`.

### Commit hygiene
Unrelated uncommitted hunks exist in `app_background_tasks.py`, `app_startup.py`, `agent_capabilities.py`, `deployment_result_endpoints.py`, `App.tsx`, `omni-agent-rs/src/capabilities/mod.rs`. Stage by path, review hunks, never `git add -A`.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/autonomous_ops/messages.py` | utility | transform | No central user-visible string module exists; design per RESEARCH Q8 (every label here so ACTV-08 scans one file) |
| `backend/autonomous_ops/protected.py` | utility | transform | No never-touch matcher exists; use stdlib `ipaddress` and `psutil.net_if_addrs()` per RESEARCH Q6 |
| `shared/autonomous-ops-banned-terms.json` | config | transform | New shared rule file; follow other `shared/*.json` conventions |
| `backend/autonomous_ops/registry.py` (undo pairing, class table) | config | transform | `ACTION_MAP` (remediation_playbook_service.py:21-31) covers only name mapping; the class/undo table is new (RESEARCH Q1 table) |
| App-wide stop banner polling hook | component | polling | No existing visibility-aware poller shared across shell and screen |
| Rust folded todo | test | n/a | Already green (21/21); re-run with `PATH=$HOME/.cargo/bin:$PATH` and move `.planning/todos/pending/2026-08-17-fix-stale-capability-count-assertions-in-integration-rs.md` to `.planning/todos/completed/` |

## Metadata

**Analog search scope:** `backend/` (gate-adjacent services, migrations, catalogue slices, lock, audit, capabilities, tests), `services/`, `components/`, `src/__tests__/`
**Files scanned:** about 30 read or grepped this session; the rest taken from 81-RESEARCH.md `[VERIFIED]` tags
**Pattern extraction date:** 2026-10-25
