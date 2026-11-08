# Phase 85: First-Line Service Desk - Pattern Map

**Mapped:** 2026-11-08
**Files analyzed:** 40 (new and modified)
**Analogs found:** 38 / 40 (2 have no in-repo analog: Ollama client, PowerShell polling timer)
**Scope searched:** `backend/autonomous_ops/`, `backend/*_endpoints.py`, `backend/catalogue_mounts_*.py`, `backend/migrations/`, `backend/tests/`, `components/`, `services/`, `src/__tests__/`, `agent-install/omni-agent-rs/scripts/`
All analog paths below were checked with `git ls-files` (tracked). None is a gitignored mirror.

## File Classification

### Backend (new package `backend/service_desk/`, outside `autonomous_ops/` because of the LLM-import ban)

| New / Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/service_desk/__init__.py` | config (constants) | n/a | `backend/autonomous_ops/__init__.py` | exact |
| `backend/service_desk/worker.py` | service (background loop) | event-driven, batch | `backend/autonomous_ops/sweep.py` | exact |
| `backend/service_desk/intake.py` | service | event-driven (enqueue) | `backend/autonomous_ops/sweep.py` (`tick` per-tenant scoping) | role-match |
| `backend/service_desk/lifecycle.py` | service | CRUD (compare-and-set on ticket) | `backend/tickets_service.py` `add_comment` | role-match |
| `backend/service_desk/handoff.py` | service | CRUD | `backend/tickets_endpoints.py` create_ticket auto_assign (171-178) | role-match |
| `backend/service_desk/settings.py` | service (settings + control rows) | CRUD | `backend/autonomous_ops/response_settings.py` | exact |
| `backend/service_desk/rules.py`, `sanitize.py`, `checks.py`, `retrieval.py`, `workdays.py`, `messages.py`, `gaps.py`, `starters.py` | utility (pure) | transform | `backend/autonomous_ops/response_messages.py` (copy constants), `backend/autonomous_ops/protected.py` (pure rule modules) | role-match |
| `backend/service_desk/model.py` | service (HTTP client) | request-response | none in-repo for loopback Ollama; `backend/ai_providers.py` `OllamaProvider` is the anti-pattern (D-15) | no analog |
| `backend/service_desk_endpoints.py` (portal) | route | request-response | `backend/tickets_endpoints.py` (comments route 252-290) | role-match |
| `backend/service_desk_tray_endpoints.py` (agent-key) | route | request-response | `backend/agent_tasks_endpoints.py` `create_ticket_from_agent` (423-458) | exact |
| `backend/autonomous_ops_service_desk_endpoints.py` | route | CRUD | `backend/autonomous_ops_response_endpoints.py` | exact |
| `backend/catalogue_mounts_autonomous_ops.py` (modify `MOUNTS`) | config | n/a | itself, line 36-39 | exact |
| `backend/migrations/032_service_desk.py` | migration (indexes only) | batch | `backend/migrations/031_patch_rollouts.py` | exact |
| `backend/autonomous_ops/registry.py` (add 2 rows) | config | n/a | `registry.py:52` `install_patches` | exact |
| `backend/autonomous_ops/gate.py` (`_step_protected_targets`, `_step_blast_radius`) | service | request-response | itself, `_STEPS` at 323-325 | exact |
| `backend/autonomous_ops/ledger.py` (`_AUTO_ROWS` kind param, `record_desk_event`) | model/store | CRUD | itself, lines 254-290 | exact |
| `backend/autonomous_ops/decision_row.py`, `reconciler.py`, `approvals.py`, `views.py`, `messages.py` (small hooks) | service | CRUD | themselves (Phase 84 `patch_rollout` precedent) | exact |
| `backend/tickets_service.py` `add_comment` (visibility, extra, comment_id, notify) | service | CRUD | itself, 346-375 | exact |
| `backend/tickets_endpoints.py` (`AddCommentRequest.visibility`, create hooks) | route | request-response | itself | exact |
| `backend/agent_tasks_endpoints.py` (`raise-ticket` and `/ticket` stamp `raised_via`) | route | request-response | itself, 341-458 | exact |
| `backend/ticket_notifications.py` (staff-only no preview) | service | event-driven | itself, 134-145 | exact |
| `backend/notification_endpoints.py` (recipient filter) | route | request-response | itself, `get_notifications` 66-83 | exact |
| `backend/knowledge_endpoints.py` (helpdesk flag, PATCH doc, starters, gaps) | route | CRUD | itself, ingest 171-203, list/delete 274-304 | exact |
| `backend/app_startup.py` (start desk worker + return loop) | config | event-driven | itself, 512-532 | exact |

### Tests

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `backend/tests/test_service_desk_*.py` (rules, retrieval, checks, injection, lifecycle) | test | `backend/tests/test_autonomous_ops_response_endpoints.py` (real mongod fixture) | role-match |
| `backend/tests/test_service_desk_structural.py` | test (AST scan) | `backend/tests/test_autonomous_ops_structural.py` | exact |
| `backend/tests/test_autonomous_ops_registry.py`, `test_autonomous_ops_copy.py`, `test_catalogue_slice_autonomous_ops.py` (extend) | test | themselves | exact |
| `backend/tests/fixtures/service_desk/*.jsonl|json` | fixture | none (new) | no analog |

### Frontend and tray

| File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `services/serviceDeskApi.ts` | service (API client) | request-response | `services/autonomousOpsApi.ts` (414-440) | exact |
| `components/serviceDesk/*.tsx` (draft panel, requester panel, gap list, settings rows, article view) | component | request-response | `components/AutonomousOpsResponseSettings.tsx`, `AutonomousOpsResponseSettingsDialogs.tsx` | role-match |
| `components/ArticleEditDialog.tsx` | component (dialog) | CRUD | `components/AutonomousOpsResponseSettingsDialogs.tsx` | role-match |
| `components/KnowledgeBaseDashboard.tsx` (modify: toggle, gaps, starters) | component | CRUD | itself (233 lines, `authFetch` pattern) | exact |
| `components/InternalTicketsDashboard.tsx` (modify: mount points only; file is 1525 lines) | component | CRUD | itself; keep new code in `components/serviceDesk/` | exact |
| `components/AutonomousOpsActivity.tsx` (modify: mount settings rows) | component | request-response | itself, `AutonomousOpsResponseSettings` mount | exact |
| `src/__tests__/ServiceDesk*.test.tsx` | test | `src/__tests__/AutonomousOpsActivity.test.tsx` | role-match |
| `agent-install/omni-agent-rs/scripts/tray_icon.ps1` (section 8: My tickets) | component (WinForms) | request-response, polling | itself: `Show-TicketDialog` 157-203, `Show-Status` 280-291 | exact (timer: no analog) |

## Pattern Assignments

### `backend/service_desk/worker.py` (service, event-driven loop)

**Analog:** `backend/autonomous_ops/sweep.py`

**Conventions to copy** (lines 22-44): module docstring stating who decides; one runner at a time through `distributed_lock.lock_with_renewal`; raw Mongo handle with explicit `tenantId`; tenant ContextVar only inside `scope.tenant_scope`.
```python
LOCK_NAME = "autonomous_ops_sweep"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
_DEFAULT_INTERVAL_SEC = 60
from .scope import raw
...
if settings.stop_active(await settings.platform_stop(db)):
    return counts
except Exception as exc:
    logger.error("autonomous_ops: sweep could not read the platform stop, doing nothing: %s", exc)
    return counts            # fail closed
```
Use lock name `"service_desk_worker"`, `ttl_seconds=120, renew_every=30`. Millisecond-truncated `_now()` (sweep.py 47-50) for BSON dates. Import from `autonomous_ops` (`PLATFORM_TENANT_ID`, `scope.raw`, `scope.tenant_scope`); nothing under `autonomous_ops/` may import the desk.

**Startup wiring** (`backend/app_startup.py` 521-526):
```python
from autonomous_ops.sweep import sweep_loop as _autonomous_ops_sweep_loop
asyncio.create_task(_safe_bg_task(_autonomous_ops_sweep_loop(), "autonomous_ops_sweep"),
                    name="autonomous_ops_sweep")
```
Add two blocks in the same shape: desk worker loop and hourly return-job loop.

---

### `backend/autonomous_ops/registry.py` (add `ticket_answer`, `ticket_withdraw`)

**Analog:** `registry.py:48-52`
```python
ActionSpec("restart_service", "auto"),
# PTCH-06 / OQ1: ... Any other dispatcher is refused unregistered_action, at decide time
# (gate._step_class) and again at delivery (dispatch_check.bind).
ActionSpec("install_patches", "auto", undo="rollback_patches", dispatchers=("patch_rollout",)),
```
New rows: `ActionSpec("ticket_answer", "auto", undo="ticket_withdraw", target_kind="none", dispatchers=("service_desk",))` and `ActionSpec("ticket_withdraw", "undo_only", target_kind="none", dispatchers=("service_desk",))`. Update the registry test that pins the locked split.

### `backend/autonomous_ops/gate.py` and `ledger.py` (gate extensions)

**Gate steps** (`gate.py:323-325`): `_STEPS = (_step_platform_stop, _step_eligibility, _step_tenant_stop, _step_level, _step_class, _step_protected_targets, agent_support.gate_step, _step_blast_radius, _step_dedupe, _step_shadow)`. Only `_step_protected_targets` (ticket-ownership for `dispatcher == "service_desk"`) and `_step_blast_radius` (desk pool) change. Refusals use `ctx.refuse("<step>", "<reason in REASON_CODES>", record=False)`; dedupe shows the style at gate.py 300-306.

**Rate pool** (`ledger.py:254-290`): `_AUTO_ROWS = {"autoDispatched": True, "kind": {"$ne": "control"}, "state": {"$ne": "shadow"}}` feeds `count_auto_since` and `recent_finished_auto`. Add a `kind` parameter. Default callers must exclude `kind: "servicedesk"` (security behaviour unchanged); the desk passes its own kind with 20/hour. D-30 and D-25 make this load-bearing; pin with tests that three undone desk rows do not trip the Phase 81 breaker.

**Dispatcher-restricted precedent to mirror in reconciler**: `reconciler.py:131` `if row.get("dispatcher") == _ROLLOUT_DISPATCHER:` -> skip desk rows the same way.

---

### `backend/service_desk/settings.py` and `backend/autonomous_ops_service_desk_endpoints.py` (settings route)

**Analogs:** `backend/autonomous_ops/response_settings.py` and `backend/autonomous_ops_response_endpoints.py`

**Imports / router** (endpoints 25-43):
```python
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, StrictBool, StrictInt, StringConstraints
from autonomous_ops import PLATFORM_TENANT_ID, messages, response_settings, views
from autonomous_ops.scope import raw
from autonomous_ops_endpoints import (_decision_error, _require_control, _require_interactive_session,
                                      _require_manage, _tenant_for, _unavailable)
from database import get_database
router = APIRouter(prefix="/api/autonomous-ops", tags=["Autonomous Ops"])
```
**Guards + tenant resolution** (endpoints 83-90, 93-110): `user=Depends(_require_manage), _session=Depends(_require_interactive_session)`; `_tenant()` refuses `PLATFORM_TENANT_ID` with 409; wrap in `try/except HTTPException: raise / except Exception as exc: raise _unavailable(exc)`.
**Write pattern** (endpoints 111-125): `caller = await views.build_caller(user)`, `response_settings.save(db, tenant, changes, actor=await views.actor_for(db, caller), ...)`, 422 via `refuse(exc)`. Every changed value writes one control row (`ledger.record_control`) and one audit event naming the person; an unchanged save records nothing. Put tenant words validation (max 50, 2-40 chars, casefold, dedupe) in `settings.py` as the `validate_changes` equivalent.
**Mount:** add `("autonomous_ops_service_desk_endpoints", "router"): AUTONOMOUS_OPS_GUARD,` to `MOUNTS` in `backend/catalogue_mounts_autonomous_ops.py` (line 38-39). Undo needs no new route: register an undo handler for `"service_desk"` with `approvals` and reuse `POST /api/autonomous-ops/actions/{action_id}/undo`.
**Test analog:** `backend/tests/test_autonomous_ops_response_endpoints.py` (docstring "Value / fails_when / no_claim" style; fixtures `from tests._autonomous_ops_http import PLATFORM, _case, _env, _probe, api`, `from tests._mongo_test_db import mongo_db`, `from tests.autonomy_support import seed_tenant`; helpers `_controls`, `_audit_actions`, `_stored`).

---

### `backend/service_desk_tray_endpoints.py` (agent-key routes)

**Analog:** `backend/agent_tasks_endpoints.py` `create_ticket_from_agent` (423-458)
```python
@router.post("/{agent_id}/ticket")
async def create_ticket_from_agent(agent_id: str, body: RaiseTicketRequest,
                                   _tenant: Dict[str, Any] = Depends(verify_agent_key)):
    agent_capabilities.assert_allowed(_tenant, "ticket_reporter")
    db = get_database()
    tenant_id = _tenant.get("id", "")
    agent = await db.agents.find_one({"$or": [{"id": agent_id}, {"hostname": agent_id}], "tenantId": tenant_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
```
Copy `Depends(verify_agent_key)` + `assert_allowed(_tenant, "ticket_reporter")` + explicit `tenantId` on every query. No catalogue guard (agent routes never carry one). Rate limit like `report_network_scan_results`: `@limiter.limit("30/minute")` with `request: Request, response: Response` params (agent_tasks_endpoints ~473). New creation route `POST /api/agents/{id}/tray/tickets` stamps `raised_via="tray"` by route identity. In the legacy `/ticket` route set `raised_via` to `tray` only when tags contain `tray` and `user-raised`, not `agent-raised`, and `endpoint_info.username` is non-empty; the route currently appends `"agent-raised"` to tags itself (line 446), so check the body tags BEFORE that append. Tray routes return an explicit projection, never the raw ticket.

### `backend/service_desk_endpoints.py` (portal routes)

**Analog:** `backend/tickets_endpoints.py` comments route (252-290): `Depends(rbac_service.has_permission("view:dashboard"))`, plus `ticket.reporter == current_user.username` for confirm/help. Router prefix `/api/tickets/{ticket_id}/service-desk` (already an owned catalogue prefix; run parity tests).

### `backend/tickets_service.py` `add_comment` (modify)

**Analog:** itself, 346-375
```python
comment = {"id": str(uuid.uuid4()), "author": author, "text": text, "created_at": _now(), "edited": False}
history = self._history_entry(author, "commented", {"preview": text[:80]})
result = await db[self.COL].update_one(query, {"$push": {"comments": comment, "history": history},
                                                "$set": {"updated_at": _now()}})
```
Add kwargs `visibility="staff"`, `extra=None`, `comment_id=None` (idempotent: filter `comments.id: {"$ne": comment_id}`), `notify=True`. A missing `visibility` reads as staff (no backfill). The tail of this function schedules `notify_comment_added` which previews `text[:100]` to the reporter (`ticket_notifications.py:134-145`): skip it for staff-only comments.

### `backend/notification_endpoints.py` (recipient filter)

**Analog:** itself, 66-83. Existing filter pattern:
```python
query: Dict[str, Any] = {"tenantId": tenant_id}
if "*" not in perms and "manage:agents" not in perms:
    query["metadata.audience"] = {"$ne": "tenant_admins"}
```
Add `query["$or"] = [{"metadata.recipient": {"$exists": False}}, {"metadata.recipient": current_user.username}]` (combine with any existing `$or` via `$and`). Send desk notices with `get_notification_service(db).send_alert(..., channels=[])`; never `autonomous_ops.notify.notify` (pages on-call, D-22).

### `backend/knowledge_endpoints.py` (modify)

**Analog:** itself. Ingest (171-203): `Depends(rbac_service.has_permission("manage:ai_risks"))`, tenant from `getattr(current_user, "tenant_id", None)` else 403, doc id `kb-{uuid.uuid4().hex[:12]}`, doc shape `{id, content, title, source, tags, tenantId, createdBy, createdAt}`. Add `helpdesk: bool`, `starterKey`, `updatedAt`; new `PATCH /docs/{doc_id}` and starter/gap routes use the same dependency and tenant check as `delete_doc` (291). Starter copy: `update_one({"tenantId": t, "starterKey": key}, {"$setOnInsert": {...}}, upsert=True)`. Gap route also checks `view:dashboard` (D-27). Cap content size (ingest has none).

### `backend/migrations/032_service_desk.py`

**Analog:** `backend/migrations/031_patch_rollouts.py` (whole file, 1-30): `DESCRIPTION = ...`, `logger`, `async def up(db: AsyncIOMotorDatabase)` calling a store `ensure_indexes(db)` (see `autonomous_ops/rollout/store.py`), idempotent `create_index`, docstring "Indexes only, nothing is backfilled". Indexes: `service_desk_jobs` unique `(tenantId, ticketId)` and `(state, createdAt)` plus 90-day TTL on `finishedAt`; `service_desk_gaps` TTL; `knowledge_docs` unique partial `(tenantId, starterKey)`; open-dedupe index for desk rows.

---

### `backend/tests/test_service_desk_structural.py`

**Analog:** `backend/tests/test_autonomous_ops_structural.py` (80-125): reuse `_backend_sources()` (git ls-files walk) and the `BANNED_LLM_MODULES` tuple. Desk variant: no import of those modules inside `service_desk/` (the desk's own client uses `httpx`, allowed only in `service_desk/model.py`), no write to `agent_instructions`/`instructions`/`response_tasks`.

### Copy / ACTV-08 scan

Add new desk files and `service_desk/messages.py` to `EXPECTED_FILES` in `backend/tests/test_autonomous_ops_copy.py` and `src/__tests__/autonomousOpsCopy.test.ts`, plus `shared/autonomous-ops-banned-terms.json` if it lists files (Autonomous Ops naming; never "ASI", "Autopilot", "fully autonomous").

---

### `services/serviceDeskApi.ts`

**Analog:** `services/autonomousOpsApi.ts`
```ts
import { API_BASE, authFetch } from './apiService';
export function fetchResponseSettings(tenantId?: string | null): Promise<ResponseSettings> {
    return getJson(withTenant(`${API_BASE}/autonomous-ops/response-settings`, tenantId));
}
export async function saveResponseSettings(changes, tenantId?) {
    const url = withTenant(`${API_BASE}/autonomous-ops/response-settings`, tenantId);
    const res = await authFetch(url, { method: 'PUT', body: JSON.stringify(changes) });
    if (!res.ok) throw await failure(res);
    return res.json();
}
```
Reuse (export if needed) `getJson`, `withTenant`, `failure`, the `AutonomousOpsApiError` shape. JSDoc each function with its route and permission. Settings-panel types extend `ResponseSettings`-style interfaces with a `readable` flag.

### `components/serviceDesk/*` and settings rows

**Analog:** `components/AutonomousOpsResponseSettings.tsx` (1-50, 150-200)
```tsx
import { fetchResponseSettings, saveResponseSettings } from '../services/autonomousOpsApi';
import { showToast } from '../utils/toast';
import { SECONDARY_BUTTON } from './AutonomousOpsHealthCards';
import { HEALTH_SKELETON, HealthNotice } from './AutonomousOpsHealthChips';
import { ACCENT_BUTTON, TurnOffRuleDialog, plain, plural } from './AutonomousOpsResponseSettingsDialogs';
const uid = useId();          // aria ids: `${uid}-body`
const alive = useRef(true);   // guard setState after unmount
const load = useCallback(async () => { ... if (!alive.current) return; setLoadFailed(true) ... }, [tenantId]);
useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [load]);
// staged draft resets from server data: useEffect(() => { if (data) setDraft(draftFrom(data)); }, [data]);
```
Exports reusable styling constants `HELPER`, `FIELD` (lines 21-23). Copy the staged-form-with-one-Save pattern, `inFlight` ref against double submit, `LOAD_ERROR` copy style. Dialogs: `AutonomousOpsResponseSettingsDialogs.tsx` (`TurnOffRuleDialog`) for confirm dialogs and `ArticleEditDialog.tsx`. Mount the new rows beside `<AutonomousOpsResponseSettings>` in `components/AutonomousOpsActivity.tsx` (imports at lines 1-15, manage-gated). Test shape: `src/__tests__/AutonomousOpsActivity.test.tsx`.

### `components/KnowledgeBaseDashboard.tsx` (modify)

**Analog:** itself. Uses `authFetch('/api/knowledge/docs')` directly and local `useState` forms (lines 1-40). Keep additions small (file is 233 lines, limit 500): add `helpdesk?: boolean` to `KBDoc`, mount `<KnowledgeGaps/>` and the "Add starter IT articles" button from `components/serviceDesk/`. `InternalTicketsDashboard.tsx` is 1525 lines: only add imports and mount points; all new UI lives in `components/serviceDesk/`.

---

### `agent-install/omni-agent-rs/scripts/tray_icon.ps1` (section 8: My tickets)

**Analog:** itself. Window pattern from `Show-TicketDialog` (157-203):
```powershell
function Show-TicketDialog($tpl) {
    Sync-TrayConfig
    $f = New-Object System.Windows.Forms.Form
    $f.StartPosition = 'CenterScreen'; $f.TopMost = $true
    $lblT = New-Object System.Windows.Forms.Label
    $lblT.Text = 'Title'; $lblT.Location = '12,12'; $lblT.AutoSize = $true; $f.Controls.Add($lblT)
    $submit.Add_Click({
        Sync-TrayConfig
        if (-not (Test-Enrolled $status)) { return }
        $uri = "$Base/api/agents/$AgentId/ticket"
        try {
            $r = Invoke-RestMethod -Method Post -Uri $uri -Headers $Headers -ContentType 'application/json' -Body $body
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "ticket failed: POST $uri -> $why ($($_.Exception.Message))"
            $status.ForeColor = 'Firebrick'; $status.Text = "Ticket not sent. $why"; $submit.Enabled = $true
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}
```
Copy: `Sync-TrayConfig` first, `Test-Enrolled`, absolute `Location` strings, `.GetNewClosure()` on every handler, `Get-FailureText` + `Write-TrayLog`, `Get-EndpointInfo` (147-155, reports `username = $env:USERNAME`) for the Windows user. Ticket body today sends `tags = @('user-raised','tray')` and the template prefix from `$Templates` (lines ~91-96); add `template` and a `client.features = @('my_tickets')` claim. Menu item pattern (300-321): `ToolStripMenuItem 'My tickets'` with `Add_Click({ Show-MyTickets })` inserted before the separator. Balloon: `$notify.ShowBalloonTip(6000)` as in `Show-Status` (280-291); add `BalloonTipClicked`. Message loop is `[System.Windows.Forms.Application]::Run($ctx)` (324): the polling `System.Windows.Forms.Timer` must be created before it. No in-repo timer analog; follow RESEARCH Pattern 8 (20-60 s for 3 min after raising, then 5 min while an open tray ticket exists, `-TimeoutSec 10`, seen ids in `%LOCALAPPDATA%\OmniAgent\tray-seen.json`). PowerShell 5.1 only; no `Invoke-Expression`. Tests are static (Python reads the `.ps1` for function and route names). The script ships via `include_str!` in `src/tray.rs`, so it reaches users only with an agent release (user step).

## Shared Patterns

### Fail closed
**Source:** `sweep.py` 66-72 and `gate.py` dedupe 300-306. Unreadable stop/settings/ledger -> do nothing or refuse with a `REASON_CODES` value; wrap external reads in try/except that logs and refuses. Apply to every desk stage.

### Tenant scoping in background work
**Source:** `autonomous_ops/scope.py` (`raw(db)`, `tenant_scope(tenant_id)` with try/finally reset) and `sweep._ticked_tenants` (`raw(db).tenants.find({"enabledFeatures": SCREEN_PERMISSION})` minus `PLATFORM_TENANT_ID`). Always explicit `tenantId` filters; only enter `tenant_scope` to call tenant-wrapped `tickets_service`.

### Settings change recording
**Source:** `response_settings.save` plus `ledger.record_control` (see `test_autonomous_ops_response_endpoints.py` `_controls` / `_audit_actions`): one control row and one audit event per real change, none for no-ops.

### Route permission stack
**Source:** `autonomous_ops_response_endpoints.py` (`_require_manage`, `_require_interactive_session`, `_tenant` refusing Platform) for settings; `rbac_service.has_permission("view:dashboard")` for ticket routes; `verify_agent_key` + `assert_allowed(_tenant, "ticket_reporter")` for tray routes (no catalogue guard). Remember the real app adds a permission guard the tests' bare router lacks: test the role matrix via `probe_real_app` as the response-endpoints test does.

### Catalogue drift
New routers must be added to a `MOUNTS` dict (`catalogue_mounts_autonomous_ops.py`); run `test_catalogue_route_parity.py`, `test_catalogue_slice_autonomous_ops.py`, `test_catalogue_slice_billing_identity.py`, `test_catalogue_slice_agents*.py`.

### Staging discipline
The working tree has ~1,800 unrelated dirty files and user WIP; executors stage only their own paths and hunks, never `git add -A`.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/service_desk/model.py` | service | request-response (loopback Ollama) | The only in-repo Ollama client (`ai_providers.OllamaProvider`) is what D-15/DESK-04 forbids (fixed 60 s timeout, ignores `max_tokens`, first-model fallback, `with_own_model` wrap). Use RESEARCH Pattern 5 and `httpx.MockTransport` for tests. |
| PowerShell polling `Timer` in `tray_icon.ps1` | component | polling | The script has no timer today; use RESEARCH Pattern 8. |
| `backend/tests/fixtures/service_desk/*` | fixture | n/a | New eval sets; formats given in RESEARCH Pattern 4/6. |

## Metadata

**Analog search scope:** `backend/autonomous_ops/`, backend endpoints and catalogue mounts, migrations, tests, `components/`, `services/`, `src/__tests__/`, tray script
**Files read:** about 14 (targeted line ranges)
**Pattern extraction date:** 2026-11-08
