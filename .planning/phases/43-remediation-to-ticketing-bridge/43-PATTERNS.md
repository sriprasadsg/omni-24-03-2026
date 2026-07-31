# Phase 43: Remediation-to-Ticketing Bridge - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 7 (2 new, 5 modified)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/ticketing_bridge.py` (NEW) | service (adapter + orchestration + scheduler) | request-response + event-driven + batch | `backend/ticketing_service.py` (adapter/connectors) + `backend/tickets_escalation_service.py` (scheduler shape) | role-match (composite — no single exact analog for this specific hybrid) |
| `backend/tests/test_ticketing_bridge.py` (NEW) | test | unit/integration | `backend/tests/test_remediation_workflow.py` (`_mock_db()` factory), `backend/tests/test_tickets.py` (mock-cursor pattern) | exact |
| `backend/compliance_remediation_service.py` (MODIFIED — auto-create hook in `create_task`) | service | CRUD | itself (`update_task`'s existing `dispatch_rescan` conditional-call shape, lines 96-118) | exact (self-analog — clone the existing conditional side-effect pattern already in this file) |
| `backend/compliance_remediation_endpoints.py` (MODIFIED — new `POST /tasks/{task_id}/create-ticket` route) | route/controller | request-response | itself — `suggest_remediation` (lines 128-171, same file, same router, same `$set` persist-back shape) | exact |
| `backend/app_startup.py` (MODIFIED — new scheduler registration block) | config/bootstrap | event-driven | `tickets_escalation_service` registration block (lines 602-608, same file) | exact |
| `components/RemediationTaskModal.tsx` (MODIFIED — Create Ticket button, provider picker, ticket display) | component | request-response | itself — `handleSuggest`/`handleSave` (lines 68-115) for the async-action+toast shape; `AddCloudAccountModal.tsx` (lines 112-125) for the provider radio-tile picker | exact (self) / role-match (picker) |
| `services/apiService.ts` (MODIFIED — `createTicketForRemediationTask()`, `getTicketingConfig()`) | service (API client) | request-response | itself — `updateRemediationTask`/`suggestRemediation` (lines 4514-4531, same file) | exact |

## Pattern Assignments

### `backend/ticketing_bridge.py` (NEW module — service, request-response + event-driven + batch)

**Analogs:** `backend/ticketing_service.py` (connectors to call, unmodified) + `backend/tickets_escalation_service.py` (scheduler loop shape)

**Imports pattern** — clone `tickets_escalation_service.py` lines 1-10:
```python
"""Background service: ... """
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)
```
Do NOT `from database import get_database` at module scope for the scheduler path — the whole point of Pattern 4 (below) is that this module's scheduler functions receive `db` as a raw parameter, never call `get_database()` themselves.

**Connectors to call, unmodified (`ticketing_service.py` signatures — do not duplicate their bodies):**
- `async def get_ticketing_config(tenant_id: str) -> Optional[dict]` — line 34
- `async def create_jira_ticket(alert: dict, config: dict) -> dict` — line 71 (returns `{"success": True, "ticket_key": ..., "url": ...}` on success, calls `_store_ticket` internally)
- `async def create_servicenow_incident(alert: dict, config: dict) -> dict` — line 208 (returns `{"success": True, "ticket_number": ..., "url": ...}`)
- `JIRA_PRIORITY_MAP` / `SNOW_URGENCY_MAP` (lines 16-29) — `severity` keys `critical|high|medium|low` already match `compliance_remediation_tasks.priority` vocabulary; no re-mapping needed
- `_store_ticket(alert_id, provider, ticket_ref, url)` — line 367, called internally by the two `create_*` functions above; do not call directly, do not duplicate

**Adapter core pattern** (new logic, no direct prior art — write fresh, following the alert-shape contract read directly off `create_jira_ticket`'s `.get()` calls, lines 82-92, and `create_servicenow_incident`'s, lines 216-224):
```python
async def _task_to_alert_shape(db, task: dict) -> dict:
    hostname = "Unknown"
    asset_id = task.get("asset_id")
    if asset_id:
        try:
            asset = await db.assets.find_one({"id": asset_id})
            hostname = (asset or {}).get("hostname", "Unknown")
        except Exception:
            pass  # best-effort; hostname stays "Unknown", never raises
    return {
        "alert_id": task["id"],
        "type": "compliance_remediation",
        "severity": task.get("priority", "medium"),
        "hostname": hostname,
        "process": {},
        "mitre_technique": "N/A",
        "description": (
            f"Compliance control {task.get('control_id', 'N/A')} failed "
            f"(framework: {task.get('framework_id', 'N/A')}).\n\n"
            f"{task.get('description', '')}"
        ),
        "timestamp": task.get("created_at", ""),
    }
```

**Orchestration entry point (manual + auto-create call this):**
```python
async def create_ticket_for_remediation_task(
    db, task: dict, tenant_id: str, provider_override: Optional[str] = None,
) -> Optional[dict]:
    if task.get("ticket_ref"):
        return None  # dedup guard — RESEARCH.md Open Question 2, resolved: hide button, no-op here too
    config = await get_ticketing_config(tenant_id)
    if not config:
        return None  # no-op, matches D-04 "best-effort" — no exception
    provider = provider_override or config.get("provider")
    alert = await _task_to_alert_shape(db, task)
    if provider == "jira":
        result = await create_jira_ticket(alert, config)
        ref, url = result.get("ticket_key"), result.get("url")
    elif provider == "servicenow":
        result = await create_servicenow_incident(alert, config)
        ref, url = result.get("ticket_number"), result.get("url")
    else:
        return None
    if result.get("success") and ref:
        await db.compliance_remediation_tasks.update_one(
            {"id": task["id"], "tenantId": tenant_id},
            {"$set": {"ticket_provider": provider, "ticket_ref": ref, "ticket_url": url}},
        )
        return {"ticket_provider": provider, "ticket_ref": ref, "ticket_url": url}
    return None  # non-fatal — caller decides toast/log (D-04)
```

**Scheduler loop pattern** — clone `tickets_escalation_service.py` lines 34-99 structurally (query shape, `try/except Exception: logger.error(...)` wrapping the whole pass, `while True: await pass_fn(db); await asyncio.sleep(N)`):
```python
async def run_close_loop_pass(db) -> None:
    try:
        query = {"status": {"$in": ["open", "in_progress"]}, "ticket_ref": {"$ne": None}}
        cursor = db.compliance_remediation_tasks.find(query, {"_id": 0})
        async for task in cursor:
            tenant_id = task.get("tenantId", "")
            config = await get_ticketing_config(tenant_id)
            if not config:
                continue
            provider = task.get("ticket_provider")
            if provider == "jira":
                result = await get_jira_issue_status(task["ticket_ref"], config)
            elif provider == "servicenow":
                result = await get_servicenow_incident_status(task["ticket_ref"], config)
            else:
                continue
            if result.get("closed"):
                import compliance_remediation_service as svc
                updated = await svc.update_task(
                    db, task["id"], {"status": "resolved"},
                    {"tenantId": tenant_id}, created_by="system:ticket-close-loop",
                )
                if updated:
                    try:
                        from websocket_manager import broadcast_remediation_update
                        await broadcast_remediation_update(tenant_id, {
                            "task_id": task["id"], "status": "resolved",
                            "control_id": updated.get("control_id"),
                        })
                    except Exception:
                        pass
    except Exception as exc:
        logger.error("Close-loop pass failed: %s", exc)


async def start_close_loop_scheduler(db) -> None:
    logger.info("Ticketing close-loop scheduler started (interval=1200s)")
    while True:
        await run_close_loop_pass(db)
        await asyncio.sleep(1200)
```

**New-logic status checks (no prior art anywhere in codebase — Jira `statusCategory.key == "done"`, ServiceNow display-value label comparison per Pitfall in RESEARCH.md):**
```python
async def get_jira_issue_status(ticket_key: str, config: dict) -> dict:
    import httpx, base64
    jira_url = config.get("jira_url", "").rstrip("/")
    auth = base64.b64encode(f"{config['jira_email']}:{config['jira_api_token']}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{jira_url}/rest/api/3/issue/{ticket_key}?fields=status", headers=headers)
            data = resp.json()
            category = data.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
            return {"success": True, "closed": category == "done"}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}

_SNOW_CLOSED_LABELS = {"closed", "resolved"}

async def get_servicenow_incident_status(sys_id: str, config: dict) -> dict:
    import httpx
    instance = config.get("snow_instance", "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://{instance}.service-now.com/api/now/table/incident/{sys_id}"
                f"?sysparm_fields=state&sysparm_display_value=true",
                auth=(config.get("snow_username"), config.get("snow_password")),
                headers={"Accept": "application/json"},
            )
            data = resp.json().get("result", {})
            state_label = str(data.get("state", "")).strip().lower()
            return {"success": True, "closed": state_label in _SNOW_CLOSED_LABELS}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}
```

**Error handling pattern:** every external call wrapped `try/except Exception` returning a `{"success": False, "error": ...}` dict rather than raising — clone `create_jira_ticket`'s exact shape (`ticketing_service.py` lines 118-120: `except Exception as e: logger.error(...); return {"success": False, "error": str(e)}`).

---

### `backend/tests/test_ticketing_bridge.py` (NEW — test)

**Analogs:** `backend/tests/test_remediation_workflow.py` (`_mock_db()` factory), `backend/tests/test_tickets.py` (mock-cursor pattern for `.find()`)

Clone `_mock_db()`'s `MagicMock` collections + `AsyncMock` methods shape and extend it with mocked `db.ticketing_configs` / `db.ticketing_log` / `db.compliance_remediation_tasks` collections. Test IDs to hit per RESEARCH.md's requirements table: `adapter`, `create_ticket`, `no_config`, `dedup`, `autocreate_nonfatal` (in `test_remediation_workflow.py`), `endpoint`, `status_check`, `close_loop_dispatch`, `close_loop_skip`, `raw_db_registration`.

---

### `backend/compliance_remediation_service.py` (MODIFIED — `create_task`, lines 30-94)

**Analog:** itself — `update_task`'s existing conditional dispatch shape (lines 96-118)

**Core pattern to clone** (the file already demonstrates "insert/update, then conditionally fire a non-blocking side effect" — reuse this exact shape for the auto-create hook):
```python
# update_task's existing shape (lines 115-118) — this IS the pattern to replicate:
if task and updates.get("status") == "resolved":
    dispatch_result = await dispatch_rescan(db, task, created_by)
    task["dispatch"] = dispatch_result
```
Apply identically inside `create_task`, after the task dict is built/inserted, gated on `data.get("priority") in ("high", "critical")`:
```python
if task.get("priority") in ("high", "critical"):
    try:
        import ticketing_bridge
        await ticketing_bridge.create_ticket_for_remediation_task(
            db, task, task.get("tenantId", ""),
        )
    except Exception as exc:
        logger.warning("Auto-create ticket failed (non-fatal): %s", exc)  # D-04
```
Note: `create_task`'s current signature/body (read in full, lines 30-94) does not yet show the final `db.compliance_remediation_tasks.insert_one(...)` / return — confirm exact insertion point during planning by re-reading lines 50-94, but the conditional-side-effect *shape* above is confirmed correct against `update_task`'s proven precedent in the same file.

---

### `backend/compliance_remediation_endpoints.py` (MODIFIED — new `POST /tasks/{task_id}/create-ticket`)

**Analog:** itself — `suggest_remediation` (lines 128-171, same file/router)

**Imports:** already present at top of file (lines 15-26) — `APIRouter`, `Depends`, `HTTPException`, `BaseModel`, `Field`, `Literal`, `get_current_user`, `get_database`, `compliance_remediation_service as svc`. Add `import ticketing_bridge` alongside `import compliance_remediation_service as svc` (line 26).

**Auth/tenant-scope pattern** (lines 34-40, `_tenant_filter`) — reuse unchanged:
```python
def _tenant_filter(user) -> dict:
    role = getattr(user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tenant = getattr(user, "tenant_id", "") or ""
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return {"tenantId": tenant}
```

**Request model pattern** — clone `TaskUpdate`'s `Literal`-typed field style (line 60-65) for the new request body (V5 input validation per RESEARCH.md):
```python
class CreateTicketRequest(BaseModel):
    provider: Literal["jira", "servicenow"]
```

**Route pattern** — clone `suggest_remediation`'s full shape (lines 128-171: fetch task via `svc.get_task`, 404 if `None`, call new logic, persist-back via raw `db.compliance_remediation_tasks.update_one({"id": task_id, **tf}, {"$set": {...}})` wrapped in its own `try/except` that only logs — lines 162-169):
```python
@router.post("/tasks/{task_id}/create-ticket")
async def create_ticket(
    task_id: str,
    body: CreateTicketRequest,
    current_user: dict = Depends(get_current_user),
):
    """REM-01: Manually create a Jira/ServiceNow ticket for a remediation task."""
    tf = _tenant_filter(current_user)
    db = get_database()
    task = await svc.get_task(db, task_id, tf)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    tenant_id = tf.get("tenantId") or task.get("tenantId", "")
    result = await ticketing_bridge.create_ticket_for_remediation_task(
        db, task, tenant_id, provider_override=body.provider,
    )
    if not result:
        raise HTTPException(status_code=502, detail="Ticket creation failed")
    return result
```
Route added to this file directly (already registered router, `router_registry.py:169`) — do NOT create a new endpoint module (Pitfall 3/7 in RESEARCH.md).

**Ticket fields NEVER added to `TaskUpdate`** (line 60-65) — `ticket_provider`/`ticket_ref`/`ticket_url` are written only via the raw `$set` above, mirroring the `ai_suggestion` persist-back (lines 162-169), never through the client-writable PATCH model.

---

### `components/RemediationTaskModal.tsx` (MODIFIED)

**Analog (async-action + toast):** itself, `handleSuggest`/`handleSave` (lines 68-115)

**Imports pattern** (lines 1-5) — extend, don't replace:
```typescript
import React, { useState, useEffect } from 'react';
import { SaveIcon, SparklesIcon, TicketIcon, ExternalLinkIcon } from 'lucide-react';
import { RemediationTask } from '../types';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
```

**Async-action + loading-state + toast pattern** — clone `handleSuggest` (lines 68-82) exactly, swapping `api.suggestRemediation` for the new `api.createTicketForRemediationTask`:
```typescript
const [creatingTicket, setCreatingTicket] = useState(false);

const handleCreateTicket = async (provider: 'jira' | 'servicenow') => {
    if (!task?.id) return;
    setCreatingTicket(true);
    try {
        await api.createTicketForRemediationTask(task.id, provider);
        showToast('Ticket created.', 'success');
        onRefresh();
    } catch (e) {
        console.error('Ticket creation failed:', e);
        showToast('Failed to create ticket — please try again.', 'error');
    } finally {
        setCreatingTicket(false);
    }
};
```

**Button/spinner pattern** — clone the `Save Task` button's disabled/spinner shape (lines 260-269) verbatim, indigo fill per UI-SPEC's accent color:
```typescript
<button
    onClick={() => handleCreateTicket(resolvedProvider)}
    disabled={creatingTicket}
    className="... bg-indigo-600 hover:bg-indigo-700 ..."
>
    {creatingTicket ? (
        <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
    ) : (
        <TicketIcon size={14} />
    )}
    {creatingTicket ? 'Creating...' : 'Create Ticket'}
</button>
```

**Provider picker analog:** `components/AddCloudAccountModal.tsx` lines 112-125 (radio-tile-as-label pattern). UI-SPEC mandates `p-2` not `p-2.5` (off-scale exception) for the new tiles:
```typescript
// AddCloudAccountModal.tsx:112-125 — the pattern to structurally clone (with p-2 not p-2.5):
<div>
  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Cloud Provider</label>
  <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
    {ALL_PROVIDERS.map(p => (
      <label key={p} className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer text-sm transition-colors ${
        provider === p ? `${PROVIDER_META[p].color} bg-gray-50 dark:bg-gray-700 font-semibold` : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
      }`}>
        <input type="radio" name="provider" value={p} checked={provider === p}
          onChange={() => { setProvider(p); setAccountId(''); }} className="sr-only" />
        <span className="text-gray-800 dark:text-gray-100 text-xs leading-tight">{PROVIDER_META[p].label}</span>
      </label>
    ))}
  </div>
</div>
```
Adapt for the two-option `jira`/`servicenow` set, `p-2` padding, indigo selected-state border/bg per UI-SPEC Color section (`border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20`), and a `Choose a provider` label (UI-SPEC copy contract) only rendered when both providers are configured (D-02) — mirrors `task?.id` gating already used at line 164/165 for the Suggest-steps button.

**Ticket-display badge color analog:** `components/RemediationDashboard.tsx:192` — clone the `STATUS_COLORS` pill class string verbatim (`px-2 py-0.5 text-xs font-semibold rounded-full`), swapping only the color pair: Jira `bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400`, ServiceNow `bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400` (colors already established in `TicketingIntegration.tsx`'s provider selector — same association, no new palette).

**Three-state render gate** (per UI-SPEC "Component Notes for Executor"): `task?.ticket_ref` truthy → display-only block; `!task?.id` or no provider configured → hide section entirely (clone `disabled={!task?.id || suggesting}` gating pattern at line 164, extended to full conditional render rather than just `disabled`); otherwise → button (+ picker if both configured).

---

### `services/apiService.ts` (MODIFIED)

**Analog:** itself — `updateRemediationTask`/`suggestRemediation` (lines 4514-4531)

**Pattern to clone** (throw on non-2xx, return parsed JSON):
```typescript
export const createTicketForRemediationTask = async (
    taskId: string,
    provider: 'jira' | 'servicenow',
): Promise<{ ticket_provider: string; ticket_ref: string; ticket_url: string }> => {
    const res = await authFetch(`${API_BASE}/compliance-remediation/tasks/${taskId}/create-ticket`, {
        method: 'POST',
        body: JSON.stringify({ provider }),
    });
    if (!res.ok) throw new Error(`Failed to create ticket: HTTP ${res.status}`);
    return res.json();
};
```
For `getTicketingConfig()` — search for the existing `GET /api/ticketing/config` wrapper (likely already present near `ticketing`-prefixed functions in this file, given `TicketingIntegration.tsx` already consumes it); if absent, clone `getRemediationTasks`'s try/catch-returns-safe-default shape (lines 4501-4511) rather than the throwing shape, since this is a background-derived read (`hasJira`/`hasServiceNow` booleans), not a user-triggered action needing a toast.

---

### `backend/app_startup.py` (MODIFIED — new scheduler registration block)

**Analog:** `tickets_escalation_service` registration block, same file, lines 602-608

**Exact pattern to clone** (5th instance of this shape in the file — tickets, syslog, AWS/Okta/Azure/GCP polling×4, reports precede it):
```python
try:
    from ticketing_bridge import start_close_loop_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_close_loop_scheduler(_mdb.db))
    logger.info("[Ticketing] Remediation close-loop scheduler started")
except Exception as _e:
    logger.warning("[Ticketing] Close-loop scheduler failed to start: %s", _e)
```
Insert this block directly after the existing `tickets_escalation_service` block (after line 608) — same file, same function body, same `try/except Exception: logger.warning(...)` non-fatal-boot pattern used by every other scheduler registration in this function.

**Critical constraint (Pitfall 1):** must pass raw `_mdb.db`, never `get_database()` — see Shared Patterns below.

## Shared Patterns

### Non-fatal external-call error handling (D-04)
**Source:** `backend/ticketing_service.py:118-120` (`create_jira_ticket`'s `except Exception as e: logger.error(...); return {"success": False, "error": str(e)}`), replicated at `backend/tickets_escalation_service.py:90-91` (`except Exception as exc: logger.error("Escalation pass failed: %s", exc)`), and `compliance_remediation_endpoints.py:162-169` (`ai_suggestion` persist-back `try/except: logger.warning`)
**Apply to:** every new function in `ticketing_bridge.py`, the `create_task` auto-create hook, the new `create-ticket` endpoint — never let a ticketing failure raise past the caller; log and return a falsy/error result instead.

### Raw-db background scheduler (Pitfall 1)
**Source:** `backend/database.py:110-134` (`TenantIsolatedDatabase` exemption allowlist — confirmed `compliance_remediation_tasks` is ABSENT, so it IS wrapped and WILL silently fail-closed under `get_database()`'s contextvar-based tenant resolution when called from a bare `asyncio.create_task`); `backend/app_startup.py:602-606` (the proven raw-`_mdb.db` registration pattern)
**Apply to:** `start_close_loop_scheduler`/`run_close_loop_pass` in `ticketing_bridge.py` and their registration in `app_startup.py` — must receive `db` as a passed-in raw parameter, never call `get_database()` internally. This is the single highest-risk regression this phase must guard against (RESEARCH.md flags a dedicated regression test: `-k raw_db_registration`).

### Server-controlled `$set`-only field persistence (never client-writable)
**Source:** `compliance_remediation_endpoints.py:162-169` (`ai_suggestion` persist-back — same shape: external call succeeds, then a raw `db.<collection>.update_one({"id": ..., **tf}, {"$set": {...}})` outside any public Pydantic PATCH model)
**Apply to:** `ticket_provider`/`ticket_ref`/`ticket_url` — written only from `ticketing_bridge.create_ticket_for_remediation_task`'s internal `$set`, never added to `TaskUpdate` (`compliance_remediation_endpoints.py:60-65`).

### Async-action + spinner + toast (frontend)
**Source:** `components/RemediationTaskModal.tsx:68-115` (`handleSuggest`/`handleSave`), button markup at lines 163-177 and 260-269
**Apply to:** the new `handleCreateTicket` and its button — identical boolean-flag-guards-a-button-and-spinner shape, identical `showToast(..., 'error')` on catch, terse em-dash-plus-retry-instruction copy.

## No Analog Found

None — every file in scope has at least a role-match or exact analog. The two genuinely new pieces of logic (`_task_to_alert_shape`, `get_jira_issue_status`/`get_servicenow_incident_status`) have no in-repo prior art (per RESEARCH.md, confirmed by direct read of every ticketing-adjacent file) but are fully specified in Code Examples above, sourced from official Jira/ServiceNow API docs rather than a codebase analog.

## Metadata

**Analog search scope:** `backend/*.py` (ticketing_service.py, tickets_escalation_service.py, compliance_remediation_service.py, compliance_remediation_endpoints.py, app_startup.py, database.py, tests/), `components/*.tsx` (RemediationTaskModal.tsx, AddCloudAccountModal.tsx, RemediationDashboard.tsx, TicketingIntegration.tsx), `services/apiService.ts`
**Files scanned:** 12 (all read in full or via targeted line-range reads; no re-reads of overlapping ranges)
**Pattern extraction date:** 2026-07-21
