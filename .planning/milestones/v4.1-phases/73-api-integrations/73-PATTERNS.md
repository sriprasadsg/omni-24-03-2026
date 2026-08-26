# Phase 73: API & Integrations - Pattern Map

**Mapped:** 2026-08-18
**Files analyzed:** 15 (11 auth-gate swap files + 4 event/ticketing wiring files, plus 3 frontend touch points)
**Analogs found:** 15 / 15 — this phase is pure wiring; every "new" file is actually an edit to an existing file, so each file IS its own analog for surrounding conventions. Cross-file analogs are used for the *new* code being inserted (scope-narrowing check, background sweep, webhook call sites, ticket adapter).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/itam_asset_endpoints.py` (`_require_itam_admin`, canonical def) | middleware/guard | request-response | `backend/rbac_service.py` `RBACService.has_permission`/`_scopes_allow` | role-match (scope-check logic to graft in) |
| `backend/itam_catalog_endpoints.py` (`_require_itam_admin`, duplicate def) | middleware/guard | request-response | `backend/itam_asset_endpoints.py`'s canonical def (same file, sibling edit) | exact |
| `backend/itam_lifecycle_endpoints.py`, `itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py`, `itam_finance_endpoints.py`, `itam_reporting_endpoints.py`, `itam_data_endpoints.py`, `itam_kpi_endpoints.py`, `itam_label_endpoints.py` | route/controller | request-response | `backend/itam_asset_endpoints.py` (import-site pattern, unchanged — these files already `from itam_asset_endpoints import _require_itam_admin`) | exact |
| `backend/api_key_auth.py` (`AVAILABLE_SCOPES` dict extension) | config | CRUD (key-scope lookup) | same file, existing dict (lines 44-53) | exact |
| `backend/itam_lifecycle_endpoints.py` (`checkout_asset`/`checkin_asset` — new `trigger_webhook` call sites) | controller | event-driven | `backend/notification_manager.py` (`asyncio.create_task(trigger_webhook(...))` fire-and-forget precedent) | role-match |
| `backend/itam_consumable_service.py` (`checkout_consumable` — new `trigger_webhook` call site) | service | event-driven | `backend/itam_reporting_prebuilt.py`'s `_build_low_stock_consumables_rows` (threshold logic to reuse) + `notification_manager.py` (fire-and-forget pattern) | role-match |
| `backend/itam_asset_request_endpoints.py` or service (`approve_asset_request`/`reject_asset_request` — new `trigger_webhook` call sites) | controller | event-driven | `backend/itam_lifecycle_endpoints.py`'s checkout/checkin call sites (same phase, same pattern) | exact (sibling, once written) |
| `backend/itam_finance_service.py` (`run_warranty_alert_pass` — new bracketed `trigger_webhook` calls) | service/background-job | event-driven, batch | same file, existing delivery paths inside the function (in-app notification + rule-routed notification) | exact |
| **NEW** `backend/itam_finance_service.py::run_audit_overdue_alert_pass` (or sibling module) | service/background-job | batch, event-driven | `backend/itam_finance_service.py::run_warranty_alert_pass` (structural clone) + `backend/tickets_escalation_service.py::run_escalation_pass` (SLA-style periodic sweep) | exact (structural clone target) |
| `backend/ticketing_bridge.py` (new `_itam_event_to_alert_shape` adapter + automatic-trigger call sites) | service/adapter | transform, event-driven | same file, existing `_task_to_alert_shape` (lines 31-54) | exact |
| **NEW** manual "Create Ticket" endpoint (thin, calls D-09 adapter) | route/controller | request-response | `backend/ticketing_bridge.py::create_ticket_for_remediation_task` (lines 60+) | exact |
| `backend/app_startup.py` (register new audit-overdue scheduler) | config/bootstrap | event-driven | same file, existing `asyncio.create_task(start_warranty_alert_scheduler(...))`-style registration | exact |
| `components/WebhookManagement.tsx` (`availableEvents` array extension) | component | CRUD (static data) | same file, existing array (line 14) | exact |
| `components/itam/LifecyclePanel.tsx` (new "Create Ticket" row action + ticket-ref display) | component | request-response | same file, existing `Label` dropdown-menu pattern (`labelMenuAssetId` state, lines 38-73, 214-227) | exact |
| `components/itam/RequestsPanel.tsx` (new "Create Ticket" row action + ticket-ref display) | component | request-response | same file, existing `handleApprove`/`actioningId` disabled-during-action pattern (lines 19, 52, 123-131) + `LifecyclePanel.tsx`'s Label-menu pattern (cross-file, for the dropdown shape) | exact |
| `types.ts` (`ticket_ref` on `Asset`/`ItamAssetRequest`) | model/type | CRUD | `types.ts:1939` — `RemediationTask.ticket_ref` (already exists, same field name/shape) | exact |

## Pattern Assignments

### `backend/itam_asset_endpoints.py` — `_require_itam_admin` (auth guard, request-response)

**Analog:** `backend/rbac_service.py` (`_scopes_allow` / `has_permission` enforcement order)

**Current implementation** (line 36):
```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="User does not have permission to manage ITAM assets.")
    return current_user
```

**Required change** (D-01 + Pitfall 1 fix, apply to BOTH this file's def AND `itam_catalog_endpoints.py`'s duplicate def):
```python
from rbac_service import rbac_service as _rbac_service  # add import

async def _require_itam_admin(current_user: TokenData = Depends(get_current_user_or_api_key)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="User does not have permission to manage ITAM assets.")
    if not _rbac_service._scopes_allow(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="API key scope does not permit: manage:assets")
    return current_user
```

`get_current_user_or_api_key` import source: `backend/api_key_auth.py` (already exists, used verbatim by `webhook_endpoints.py`'s GET/POST routes — no changes needed to this function itself).

**11 files getting this `Depends()` swap** (import-site only, no logic change needed beyond the source function above): `itam_asset_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_license_endpoints.py`, `itam_consumable_endpoints.py`, `itam_component_endpoints.py`, `itam_finance_endpoints.py`, `itam_reporting_endpoints.py`, `itam_data_endpoints.py`, `itam_kpi_endpoints.py`, `itam_label_endpoints.py`, `itam_catalog_endpoints.py` (its own separate duplicate def, not an import — must be edited independently).

**Excluded (leave on `Depends(get_current_user)`):** `ldap_endpoints.py`, `api_key_endpoints.py`.

---

### `backend/api_key_auth.py` — `AVAILABLE_SCOPES` (config, CRUD)

**Analog:** same file, existing dict (lines 44-53)

**Current:**
```python
AVAILABLE_SCOPES: Dict[str, str] = {
    "read:assets": "Read ITAM assets",
    "write:assets": "Create and update ITAM assets",
    "read:licenses": "Read software licenses",
    "write:licenses": "Create and update software licenses",
    "manage:users": "Manage users",
    "view:itam": "View ITAM console data",
    "manage:itam": "Manage ITAM console data",
    "admin:itam": "Full ITAM administrative access",
}
```

**Required addition** (Pitfall 1's second gap — `manage:assets` is checked by `_require_itam_admin` but never offered as an issuable scope):
```python
    "manage:assets": "Create, update and manage ITAM assets (checkout/checkin, lifecycle, license/consumable/component/finance operations)",
```
Add matching strings only if D-02's broader swap requires them (`manage:procurement`, `request:assets` are NOT needed — those gates are explicitly out of scope per RESEARCH.md).

---

### `backend/itam_lifecycle_endpoints.py` — `checkout_asset`/`checkin_asset` (controller, event-driven)

**Analog:** `backend/notification_manager.py` (fire-and-forget `asyncio.create_task` precedent) — grep that file for the exact existing call shape before writing the new one, to match style precisely.

**Core pattern — insertion point** (checkout_asset, after `invalidate_cache("assets:*")` at line 196, before `log_itam_action` at line 198; already have `pre_image` and `updated` in scope from lines 149-164):
```python
import asyncio
from webhook_service import WebhookService

_webhook_service = WebhookService()

# ... inside checkout_asset, after invalidate_cache("assets:*"):
asyncio.create_task(_webhook_service.trigger_webhook("asset.checked_out", {
    "assetId": asset_id,
    "before": {k: pre_image.get(k) for k in ("lifecycleStatus", "assignedToType", "assignedToId")},
    "after": {k: updated.get(k) for k in ("lifecycleStatus", "assignedToType", "assignedToId", "checkedOutAt", "checkedOutBy")},
    "asset": updated,
}))
```
Mirror identically for `checkin_asset` (event_type `"asset.checked_in"`) at its own `invalidate_cache("assets:*")` call (line 307).

**No tenant-context bracketing needed here** — this fires inside a request handler where `_require_itam_admin`'s `Depends()` chain already called `set_tenant_id()`; `asyncio.create_task` snapshots the ambient contextvars context at creation time (Pitfall 3).

**Error handling pattern:** none needed at the call site itself — `trigger_webhook` is fire-and-forget; a failure inside it should not propagate to the check-out/check-in response. Do not `await` it directly (Pitfall 8 — sequential per-webhook 10s timeout would stall the response).

---

### `backend/itam_consumable_service.py` — `checkout_consumable` (service, event-driven)

**Analog:** `backend/itam_reporting_prebuilt.py::_build_low_stock_consumables_rows` (line 331, threshold-fallback logic) + the same fire-and-forget pattern above.

**Core pattern** (after the not-found/insufficient-quantity guard, before `return Consumable(**consumable)`):
```python
threshold = consumable.get("reorderThreshold") or DEFAULT_LOW_STOCK_QUANTITY  # from itam_reporting_prebuilt
if consumable["availableQuantity"] <= threshold:
    import asyncio
    from webhook_service import WebhookService
    asyncio.create_task(WebhookService().trigger_webhook("consumable.low_stock", {
        "consumableId": str(consumable["_id"]),
        "name": consumable.get("name"),
        "availableQuantity": consumable["availableQuantity"],
        "reorderThreshold": threshold,
    }))
```
Import `DEFAULT_LOW_STOCK_QUANTITY` from `itam_reporting_prebuilt.py` — do not redefine the constant, so the webhook's notion of "low" can never drift from the report's.

---

### `backend/itam_finance_service.py::run_warranty_alert_pass` (background job, batch + event-driven)

**Analog:** same function's own two existing delivery paths (in-app + rule-routed notification), lines ~266-330. Read the full function before editing to place the new call correctly inside the per-asset loop, alongside the existing tenant-id extraction.

**Core pattern — the ONE non-obvious pattern in this phase** (tenant-context bracketing, Pitfall 3):
```python
from tenant_context import set_tenant_id, reset_tenant_id
from webhook_service import WebhookService

_webhook_service = WebhookService()

# inside the existing `async for asset in cursor:` loop, tenant_id already resolved from the doc:
token = set_tenant_id(tenant_id)
try:
    await _webhook_service.trigger_webhook("asset.warranty_expiring", {
        "assetId": asset["id"], "assetTag": asset.get("assetTag"),
        "warrantyStatus": status_result["warrantyStatus"],
        "warrantyExpiresAt": status_result["warrantyExpiresAt"],
    })
except Exception as exc:
    logger.warning("Webhook dispatch failed for asset %s: %s", asset.get("id"), exc)
finally:
    reset_tenant_id(token)
```
Mirror for `license.expiring_soon` wherever the equivalent license-expiry sweep lives (confirm exact function name during planning — RESEARCH.md references it as "Phase 59's existing alert-window computation").

**Error handling pattern:** each webhook dispatch wrapped in its own try/except inside the per-document loop — a single asset's dispatch failure must never abort the sweep for remaining assets (matches the function's existing two delivery paths, each independently non-fatal).

---

### NEW `run_audit_overdue_alert_pass` (background job, batch + event-driven) — no existing analog, structural clone required

**Analog:** `backend/itam_finance_service.py::run_warranty_alert_pass` (full structural clone — docstring pattern, per-doc tenant extraction, marker-field guard, non-fatal delivery try/except) + `backend/tickets_escalation_service.py::run_escalation_pass` (line 34, for the periodic-sweep-plus-ticket-trigger combination) + `backend/tickets_escalation_service.py::start_escalation_scheduler` (line 94, for the scheduler-loop wrapper) + `backend/app_startup.py` (registration site — find the existing 4 `asyncio.create_task(start_*_scheduler(_mdb.db))` calls and add a 5th).

**Required behavior (RESEARCH.md Pitfall 6 — this is NEW scope, no existing function to edit):**
1. Reuse `_overdue_query`/`_overdue_row` from `itam_lifecycle_endpoints.py` (already imported a second time by `itam_reporting_prebuilt.py` for the identical purpose) so "overdue" can never drift from the `GET /reports/overdue-audit` route's own definition.
2. Daily cadence, named constant (not the hourly `_WARRANTY_SWEEP_INTERVAL_SECONDS`).
3. `auditOverdueAlertSentAt` marker field, mirroring `warrantyAlertSentAt`'s exact pattern (write unconditionally once the delivery step is reached, regardless of success — same reasoning as `run_warranty_alert_pass`'s docstring, lines ~260-300).
4. Fires BOTH `trigger_webhook("asset.audit_overdue", ...)` (tenant-bracketed per the pattern above) AND the new ticketing-bridge automatic trigger (D-10) from the same pass, per-document.

---

### `backend/ticketing_bridge.py` — new `_itam_event_to_alert_shape` adapter (service/adapter, transform)

**Analog:** same file, existing `_task_to_alert_shape` (lines 31-54)

**Exact shape to clone:**
```python
async def _task_to_alert_shape(db, task: dict) -> dict:
    """Adapt a compliance_remediation_tasks doc into the alert-shaped dict
    ticketing_service.py's connectors expect."""
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

**New adapter to write** (`_itam_event_to_alert_shape(db, event_type: str, payload: dict) -> dict`), same required-field shape, `type` set to `"itam_audit_overdue"` / `"itam_request_stuck"`, `alert_id` synthetic-but-stable (e.g. `f"itam-audit-{asset_id}"`) so `create_jira_ticket`/`create_servicenow_incident` (imported from `ticketing_service.py`, NOT `integration_service_ticketing.py` — Pitfall 7) work unmodified.

**Imports pattern** (module header, lines 1-24):
```python
import asyncio
import logging
from typing import Any, Dict, Optional

from ticketing_service import (
    get_ticketing_config,
    create_jira_ticket,
    create_servicenow_incident,
)

logger = logging.getLogger(__name__)
```

**Docstring convention to match** — this module's docstring explicitly documents the raw-db/no-ambient-context reasoning; the new adapter's docstring should state the same reasoning if it's used from the new background sweep.

---

### NEW manual "Create Ticket" endpoint (controller, request-response)

**Analog:** `backend/ticketing_bridge.py::create_ticket_for_remediation_task` (line 60+) — read the full function body before writing; it already handles provider dispatch (`jira`/`servicenow`) and dedup.

**Core pattern:** thin FastAPI route, `Depends(_require_itam_admin)` (same guard, post-D-01/D-02 fix) or a lighter-weight requester/approver-appropriate guard, calling the new adapter directly, then `create_jira_ticket`/`create_servicenow_incident` per the selected provider (`'jira' | 'servicenow'` strict enum per `73-UI-SPEC.md`'s Component Notes — never free text).

---

## Shared Patterns

### API-key / session dual auth
**Source:** `backend/api_key_auth.py::get_current_user_or_api_key` (lines 256-286)
**Apply to:** All 11 `_require_itam_admin`-gated files' `Depends()` swap (D-01/D-02).
```python
async def get_current_user_or_api_key(
    api_key: Optional[str] = Security(_api_key_header),
    token: Optional[str] = Depends(_oauth2_optional)
) -> TokenData:
    if api_key:
        token_data = await api_key_service.authenticate(api_key)
        if token_data is not None:
            set_tenant_id(token_data.tenant_id or "platform-admin")
            return token_data
        # ... legacy tenant-key fallback ...
    elif token:
        return await verify_token_async(token)
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
```
Unchanged this phase — only its consumers (the 11 `_require_itam_admin` defs) change.

### Fire-and-forget webhook dispatch
**Source:** `backend/notification_manager.py` (existing `asyncio.create_task(...)` precedent — grep for exact line before writing)
**Apply to:** All 6 request-scoped mutation call sites (checkout, checkin, request-approved, request-denied, consumable low-stock) — never `await trigger_webhook(...)` directly inline (Pitfall 8).

### Tenant-context bracketing for background sweeps
**Source:** `backend/tenant_context.py::set_tenant_id`/`reset_tenant_id` (contextvars-based) — pattern already established in `itam_finance_service.py::run_warranty_alert_pass`'s two existing delivery paths.
**Apply to:** Both background-sweep-triggered webhook events (`asset.warranty_expiring`/`license.expiring_soon`) AND the new `asset.audit_overdue` sweep — every `trigger_webhook()` call from a scheduler loop must be individually bracketed per-document, never batch-bracketed (Pitfall 3).

### Raw-db scheduler-loop structure
**Source:** `backend/tickets_escalation_service.py::run_escalation_pass` (line 34) + `start_escalation_scheduler` (line 94); structurally identical to `itam_finance_service.py::run_warranty_alert_pass`.
**Apply to:** The new `run_audit_overdue_alert_pass` — receives raw `db` as a parameter (never resolves it via `get_database()`/`database.mongodb` itself), manual `tenantId` extraction per document, one outer `try/except Exception` that logs and never re-raises around the `async for` cursor loop, registered in `app_startup.py` alongside the other 4 existing `asyncio.create_task(start_*_scheduler(_mdb.db))` calls.

### Alert-shape adapter → provider dispatch
**Source:** `backend/ticketing_bridge.py::_task_to_alert_shape` → `create_ticket_for_remediation_task`'s existing `jira`/`servicenow` dispatch branch.
**Apply to:** New `_itam_event_to_alert_shape` + the two automatic triggers (`asset.audit_overdue`, stuck-approval) + the manual "Create Ticket" endpoint — all three converge on the same adapter-then-dispatch shape, only the caller and the alert_id/dedup-marker differ.

### Frontend: cloned dropdown-menu state shape
**Source:** `components/itam/LifecyclePanel.tsx` — `labelMenuAssetId` state (line 38) + outside-click-close `ref` pattern (lines 65-73) + rendered menu (lines 214-227).
**Apply to:** Both `LifecyclePanel.tsx`'s new "Create Ticket" dropdown (sibling state `ticketMenuAssetId`) and `RequestsPanel.tsx`'s new "Create Ticket" dropdown (sibling state `ticketMenuRequestId`) — reuse the exact state-management shape, not a new dropdown/menu component or library.

### Frontend: disabled-during-action row buttons
**Source:** `components/itam/RequestsPanel.tsx` — `actioningId` state (line 19) + `handleApprove` (line 52) + disabled-prop usage (lines 123-131).
**Apply to:** The new "Create Ticket" action's `Creating…` + disabled-while-in-flight state in both `LifecyclePanel.tsx` and `RequestsPanel.tsx`.

### Frontend: static event-catalog array extension
**Source:** `components/WebhookManagement.tsx` — `availableEvents: WebhookEvent[]` array (line 14), rendered unmodified by existing checkbox-list markup (`font-mono text-sm`, lines ~340).
**Apply to:** D-14 — append the 8 new event-type strings verbatim: `asset.checked_out`, `asset.checked_in`, `asset.warranty_expiring`, `license.expiring_soon`, `asset.request_approved`, `asset.request_denied`, `consumable.low_stock`, `asset.audit_overdue`. Pure data change, zero markup change.

### Frontend: existing `ticket_ref` type precedent
**Source:** `types.ts:1939` — `RemediationTask.ticket_ref` (already exists, same shape needed).
**Apply to:** New optional `ticket_ref` field on `Asset` and `ItamAssetRequest` types — additive, matching backend's `warrantyAlertSentAt`-style additive-marker convention.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `run_audit_overdue_alert_pass` (new function) | service/background-job | batch, event-driven | No existing periodic sweep for the audit-overdue condition exists (RESEARCH.md Pitfall 6, confirmed prior deliberate decision to keep it request-time-only) — built as a structural clone of `run_warranty_alert_pass` + `run_escalation_pass`, not a direct analog edit. |

## Metadata

**Analog search scope:** `backend/` (itam_*_endpoints.py, itam_*_service.py, api_key_auth.py, webhook_service.py, webhook_endpoints.py, ticketing_bridge.py, ticketing_service.py, rbac_service.py, rbac_utils.py, tenant_context.py, tickets_escalation_service.py, notification_manager.py, itam_finance_service.py, itam_reporting_prebuilt.py, app_startup.py), `components/` (WebhookManagement.tsx, itam/LifecyclePanel.tsx, itam/RequestsPanel.tsx), `types.ts`
**Files scanned:** ~30 (backend) + 4 (frontend), largely already deep-read by RESEARCH.md — this pass verified line numbers and extracted exact excerpts against the live codebase rather than re-deriving findings
**Pattern extraction date:** 2026-08-18
