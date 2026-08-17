# Phase 73: API & Integrations - Research

**Researched:** 2026-08-18
**Domain:** Backend wiring — API-key auth, webhook dispatch, Jira/ServiceNow ticketing, all reusing existing infrastructure
**Confidence:** HIGH (all findings verified against the actual codebase, not training knowledge)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Extend the existing internal ITAM routers to also accept API-key auth — swap `_require_itam_admin`'s `Depends(get_current_user)` → `Depends(get_current_user_or_api_key)` across `itam_*_endpoints.py`. Do NOT build a separate external `/api/v1/itam/*` surface. Reversible.
- **D-02:** All `_require_itam_admin`-gated ITAM routers get API-key access (asset, lifecycle, license, consumable, component, finance, reports) — not a curated subset. Matches ITAM-API-01's unqualified "perform ITAM operations" wording.
- **D-03:** No `/v1/` version prefix — API keys unlock the same `/api/itam/*` paths the frontend already calls. No versioning precedent exists elsewhere in this codebase. **(Research correction: see Pitfall 5 — this claim is factually wrong; a `/v1/` precedent does exist. Does not change the decision's outcome, only its stated rationale.)**
- **D-04:** Reuse `api_key_auth.py`'s existing per-key rate limiter as-is (`_check_rate_limit`) — no ITAM-specific rate-limit tier.
- **D-05:** Four event categories fire webhooks via the existing `WebhookService.trigger_webhook(event_type, payload)`:
  - `asset.checked_out` / `asset.checked_in` (Phase 57 lifecycle actions)
  - `asset.warranty_expiring` / `license.expiring_soon` (mirrors Phase 71/59's existing alert-window computation)
  - `asset.request_approved` / `asset.request_denied` (Phase 71's approval workflow)
  - `consumable.low_stock` / `asset.audit_overdue` (Phase 72's pre-built-report triggers, now also pushed as events)
- **D-06:** Payload is a flat asset/license/consumable record (or a before/after diff for check-out/in) plus event metadata — matches the existing shape `webhook_service.py._send_single_webhook` already sends for other event types. No bespoke per-event-type schema.
- **D-07:** `trigger_webhook()` calls are added inline, directly inside the relevant `itam_*_service.py` mutation functions — no new event-dispatch abstraction layer. **(Research correction: see Pitfall 4 — checkout/checkin mutation logic actually lives in `itam_lifecycle_endpoints.py`, not a service file. "Inline at the mutation point" is still correct; "in a `_service.py` file" is not universally true.)**
- **D-08:** `asset.warranty_expiring` / `license.expiring_soon` are NOT mutation-triggered — the `trigger_webhook()` call is added at Phase 71's existing periodic warranty/depreciation alert job (ITAM-PRO-05), not a new scheduled job.
- **D-09:** Generalize `ticketing_bridge.py` with a new ITAM-event-to-alert-shape adapter, alongside the existing `_task_to_alert_shape`. Reuse `create_jira_ticket`/`create_servicenow_incident`/`run_close_loop_pass` as-is. Reversible.
- **D-10:** Two automatic ticket triggers: `asset.audit_overdue` and a high-value asset request stuck pending approval too long (mirrors Phase 44's SLA/escalation pattern). PLUS an additive manual "Create Ticket" button — both exist together.
- **D-11:** Ticket creation reuses the existing tenant-level Jira/ServiceNow connection config — no new ITAM-specific integration settings UI.
- **D-12 (deferred):** CMDB-style asset data sync into Jira/ServiceNow on a schedule or on change — not built this phase.
- **D-13:** No dedicated API docs page or OpenAPI export this phase — FastAPI's auto `/docs` covers it once API-key auth is added.
- **D-14:** The webhook event_type catalog is documented by populating `components/WebhookManagement.tsx`'s `availableEvents` checkbox array with the new ITAM event types.

### Claude's Discretion

- Exact request/response field naming for any new endpoints beyond what already exists on the internal routers.
- Exact wording/placement of the manual "Create Ticket" button (likely alongside Phase 63's Label action).
- Whether the ITAM-event alert-shape adapter (D-09) lives in `ticketing_bridge.py` itself or a new sibling module.

### Deferred Ideas (OUT OF SCOPE)

- CMDB-style asset data sync into Jira (as issues) or ServiceNow (as CIs), on a schedule or on change (D-12).
- A dedicated ITAM API documentation page / OpenAPI export beyond FastAPI's auto `/docs` (D-13).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-API-01 | Full REST API coverage for ITAM (via API-key auth on existing routers) | Enumerated the exact 13-file gate surface (Std Stack §Auth Gate Enumeration), found the scope-narrowing gap that must be closed for API-key access to be meaningfully scoped (Pitfall 1), confirmed `TokenData` return-shape compatibility (Pitfall 2) |
| ITAM-API-02 | Webhook system for ITAM events | Confirmed `trigger_webhook()` signature/payload shape, found the exact 8 mutation/job insertion points, found the background-job tenant-context pitfall for the 2 non-mutation-triggered events (Pitfall 3), found `asset.audit_overdue` has no existing periodic mechanism at all (Pitfall 6) |
| ITAM-API-03 | Jira/ServiceNow integration for ITAM events | Confirmed `ticketing_bridge.py`'s adapter shape and correct source module (`ticketing_service.py`, not `integration_service_ticketing.py` — Pitfall 7), confirmed Phase 44's SLA/escalation pattern file:function, confirmed `asset.audit_overdue`'s automatic-ticket trigger has the same missing-scheduler gap as its webhook counterpart |

</phase_requirements>

## Summary

This phase is genuinely almost pure wiring: `api_key_auth.py`, `webhook_service.py`, and `ticketing_bridge.py` are all real, working, already-tested modules. No new third-party dependency is needed anywhere in this phase — confirmed by inspecting every file that needs to change; all new code uses stdlib/already-imported modules (`httpx`, `hmac`, `asyncio`, `contextvars`).

That said, deep verification surfaced four findings serious enough to change how the plan must be written, not just confirm CONTEXT.md's decisions:

1. **A real, currently-latent security gap becomes exploitable the moment D-01 ships.** `_require_itam_admin` calls `rbac_utils.verify_permission()`, which never reads `TokenData.scopes`. The scope-narrowing logic CONTEXT.md's canonical refs allude to (`api_key_auth.py`'s docstring: "scopes narrowed... rbac_service.has_permission()/require_role() intersect these") lives in a *different* function (`rbac_service.has_permission()`) that `_require_itam_admin` does not call. Today this is harmless because `_require_itam_admin` only accepts session auth. The instant D-01 swaps it to `get_current_user_or_api_key`, a `read:assets`-scoped API key will pass a `manage:assets` check, because nothing ever narrows by scope. This must be fixed as part of D-01, not treated as a pre-existing bug out of scope.

2. **`_require_itam_admin` is duplicated, not single-sourced.** `itam_catalog_endpoints.py` defines its own local copy (byte-for-byte equivalent logic) rather than importing from `itam_asset_endpoints.py`. A plan that greps for `from itam_asset_endpoints import _require_itam_admin` and patches only those importers will silently miss the catalog router.

3. **Two of the four Phase-59/71/72 "reuse a background job" claims are only half true.** The warranty/expiry job (`itam_finance_service.run_warranty_alert_pass`) genuinely exists and is genuinely running in production — confirmed at its `app_startup.py` registration. But `asset.audit_overdue` has **no periodic job to piggyback on at all** — the existing overdue-audit report route is explicitly documented as "deliberately not a background sweep... top recorded milestone risk" (a prior phase's own words). D-05/D-08 group `asset.audit_overdue` with the warranty-style events, but there is nothing to attach it to; the plan must add a new periodic mechanism for it (both for the webhook AND for D-10's automatic ticket trigger).

4. **CONTEXT.md's canonical_refs has two factual misattributions** that will misdirect a planner who trusts them literally: checkout/checkin mutation logic lives in `itam_lifecycle_endpoints.py` (not `itam_lifecycle_service.py`, which is actually about audit-trail history), and the reusable Jira/ServiceNow client functions live in `ticketing_service.py` (not `integration_service_ticketing.py`, which is an unrelated SaaS-ticketing mixin class inside `integration_service.py`).

**Primary recommendation:** Follow D-01 through D-14 as scoped, but (a) fix the scope-narrowing gap in `_require_itam_admin` as a first-class task inside D-01/D-02, not an afterthought, (b) patch both `_require_itam_admin` definitions (asset + catalog), (c) build one small new periodic sweep for `asset.audit_overdue` (webhook + ticket both depend on it) using the exact raw-db/no-ambient-context pattern already established by `run_warranty_alert_pass`/`run_close_loop_pass`/`run_escalation_pass`, and (d) use `asyncio.create_task()` fire-and-forget for every inline `trigger_webhook()` call site (matching `notification_manager.py`'s existing precedent) rather than a blocking `await`, since `trigger_webhook` dispatches webhooks sequentially with a 10s timeout each.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| API-key authentication for ITAM operations | API / Backend | — | `_require_itam_admin` dependency swap; pure backend auth-layer change, no client/UI involvement |
| Webhook event dispatch on ITAM mutations | API / Backend | Database / Storage | Inline calls at mutation points (request-scoped) + one new periodic sweep (background); `webhooks`/`webhook_deliveries` collections already exist |
| Webhook subscription management UI | Browser / Client | API / Backend | `WebhookManagement.tsx` already built; this phase only extends its static `availableEvents` array — no new UI component |
| Jira/ServiceNow ticket creation for ITAM events | API / Backend | — | New alert-shape adapter + automatic-trigger call sites; reuses existing `ticketing_service.py` HTTP clients unchanged |
| Automatic ticket triggers (overdue audit, stuck approval) | API / Backend | Database / Storage | New periodic sweep(s), raw-db pattern, no request context |
| Manual "Create Ticket" button | Browser / Client | API / Backend | New button wired to a new thin endpoint calling the D-09 adapter directly |

## Standard Stack

### Core

No new libraries. Every module this phase touches already imports everything it needs:

| Module | Already Imports | Reused For |
|--------|-----------------|------------|
| `api_key_auth.py` | `fastapi`, stdlib (`hashlib`, `secrets`, `time`) | API-key auth (unchanged this phase — only its consumers change) |
| `webhook_service.py` | `httpx`, stdlib (`hmac`, `hashlib`, `ipaddress`) | `trigger_webhook()` (unchanged this phase — only its callers change) |
| `ticketing_bridge.py` / `ticketing_service.py` | `httpx`, `base64` | Jira/ServiceNow HTTP clients (unchanged this phase — only a new adapter + call sites are added) |

### Package Legitimacy Audit

Not applicable — **zero new third-party packages** are needed for this phase. Confirmed by reading every file in the reuse surface (`api_key_auth.py`, `webhook_service.py`, `ticketing_bridge.py`, `ticketing_service.py`, `itam_lifecycle_endpoints.py`, `itam_license_service.py`, `itam_consumable_service.py`, `itam_finance_service.py`, `itam_asset_request_service.py`) — all imports are stdlib, `fastapi`, `pymongo`/`motor`, or already-existing project modules. If a planner finds themselves reaching for a new package anywhere in this phase, treat that as a signal the plan has drifted from the intended pure-reuse scope — stop and re-check against this research.

## Auth Gate Enumeration (ITAM-API-01 / D-01 / D-02)

### The canonical `_require_itam_admin`

Defined in `backend/itam_asset_endpoints.py` line 36:

```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="User does not have permission to manage ITAM assets.")
    return current_user
```

**Imported (not re-implemented) by 10 other endpoint files:**

| File | Import site | `_require_itam_admin` usages |
|------|-------------|-------------------------------|
| `itam_lifecycle_endpoints.py` | `from itam_asset_endpoints import _require_itam_admin` | 5 (checkout, checkin, list_assignment_history, mark_asset_audited, overdue_audit_report) |
| `itam_license_endpoints.py` | same | 7 |
| `itam_consumable_endpoints.py` | same | 7 |
| `itam_component_endpoints.py` | same | 5 |
| `itam_finance_endpoints.py` | same | 3 |
| `itam_reporting_endpoints.py` | same | ~9 (all report/custom-report routes) |
| `itam_data_endpoints.py` | same | 2 (bulk import/export) |
| `itam_kpi_endpoints.py` | same | 1 |
| `itam_label_endpoints.py` | same | 3 |
| `api_key_endpoints.py` | same | 2 (`admin_list_api_keys`, one more admin route) |
| `ldap_endpoints.py` | same | 6 (LDAP config/sync/group-mapping routes) |

**`itam_asset_endpoints.py` itself:** 2 usages (create_manual_asset, purchase update — via `itam_asset_endpoints.py` router).

### `[VERIFIED: codebase]` A SECOND, independent duplicate definition exists

`backend/itam_catalog_endpoints.py` line 69 defines its own local `_require_itam_admin` — same logic, same `"manage:assets"` permission string, but **not imported from `itam_asset_endpoints.py`**:

```python
async def _require_itam_admin(current_user: TokenData = Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="Not enough permissions to manage ITAM catalog entities")
    return current_user
```

Used 6 times in `itam_catalog_endpoints.py` (suppliers/models CRUD, custom-fields CRUD). **A plan that only patches the imported occurrences will miss this file entirely** — it must be patched as its own, second edit site.

### D-02's named list vs. the actual gate surface — a scope decision the planner must make explicit

D-02 names 7 categories: "asset, lifecycle, license, consumable, component, finance, reports." That maps cleanly to 7 files. But **6 more files use the identical `_require_itam_admin` gate and are not named**: `itam_catalog_endpoints.py`, `itam_kpi_endpoints.py`, `itam_data_endpoints.py`, `itam_label_endpoints.py`, `ldap_endpoints.py`, `api_key_endpoints.py`.

Recommendation for the plan: swap **all 13 files** that use `_require_itam_admin` (both the imported and the catalog duplicate) — D-02's own rationale ("unqualified 'perform ITAM operations' wording") supports treating catalog/kpi/data/label as in-scope (they are unambiguously ITAM operations). **Flag `ldap_endpoints.py` and `api_key_endpoints.py` as requiring an explicit human decision** before swapping:
- `ldap_endpoints.py` gates LDAP directory sync config — not really "ITAM data," and letting an API key trigger an LDAP sync or rewrite group-role mappings is a materially different risk than letting it read/write assets.
- `api_key_endpoints.py`'s `admin_list_api_keys`/admin route gates *API key management itself* — swapping this means an API key could be used to list or create other API keys (self-service key proliferation / privilege-escalation surface). This is the one file in the list where the swap could plausibly be a deliberate scope-out rather than an oversight.

### `_require_asset_requester` / `_require_asset_approver` / `_require_asset_viewer` — separate gate, NOT part of D-02

`itam_asset_request_endpoints.py` defines its own 3 gates (`request:assets` / `manage:procurement` permissions), never `_require_itam_admin`. Not named in D-02, and D-02's list doesn't cover asset-requests. These stay on `get_current_user` only unless the plan explicitly decides to widen scope — recommend leaving as-is (D-02 does not name "asset-requests" as a category).

### `_require_procurement_admin` — also separate, NOT part of D-02

`itam_procurement_endpoints.py` defines its own `_require_procurement_admin` (`manage:procurement` permission). Also not `_require_itam_admin`, also not named in D-02. Same recommendation: leave as-is unless explicitly widened.

## Common Pitfalls

### Pitfall 1 (CRITICAL): API-key scope narrowing does not actually apply to `_require_itam_admin`

**What goes wrong:** After D-01 ships, an API key created with only the `read:assets` scope can still perform `manage:assets`-gated write operations (create/delete assets, checkout/checkin, license seat assignment, etc.) as long as the key's *owning user* has a role that grants `manage:assets` (e.g., any admin). The scoped-key model becomes security theater.

**Why it happens:** `_require_itam_admin` calls `rbac_utils.verify_permission(user, "manage:assets")`. That function's implementation (`backend/rbac_utils.py`) only ever reads `user.role` — it does not read `user.scopes` or `user.auth_source` at all. The actual scope-narrowing logic lives in a completely different function, `rbac_service.RBACService.has_permission()` (`backend/rbac_service.py` line 197), whose docstring explicitly documents the two-step enforcement order (role check, then `_scopes_allow()` scope check) that `api_key_auth.py`'s own docstring assumes is universal — it is not; it only applies to endpoints that use `Depends(rbac_service.has_permission(...))`, and no ITAM router does.

**How to avoid:** Add an explicit scope-narrowing check inside `_require_itam_admin` (both copies — asset + catalog), calling `rbac_service.rbac_service._scopes_allow(current_user, "manage:assets")` after the existing `verify_permission` call, mirroring `has_permission()`'s enforcement order exactly:

```python
from rbac_service import rbac_service as _rbac_service  # add import

async def _require_itam_admin(current_user: TokenData = Depends(get_current_user_or_api_key)):
    if not await verify_permission(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="User does not have permission to manage ITAM assets.")
    if not _rbac_service._scopes_allow(current_user, "manage:assets"):
        raise HTTPException(status_code=403, detail="API key scope does not permit: manage:assets")
    return current_user
```

**A second, dependent gap:** even with the fix above, `api_key_auth.AVAILABLE_SCOPES` (the predefined scope list offered when creating a key, and validated against on creation — `api_key_endpoints.py` lines 37/85) does **not contain `manage:assets`, `manage:procurement`, or `request:assets`** — the exact permission strings ITAM routers actually check. It only offers `read:assets`, `write:assets`, `read:licenses`, `write:licenses`, `manage:users`, `view:itam`, `manage:itam`, `admin:itam`. `_scopes_allow()` does an exact-string match (`required_permission in scopes`), so none of the currently-offered scopes actually satisfy a `manage:assets` check even after the fix above is applied — a key-holder would have no way to create a key that can pass ITAM write operations at all. **The plan must add `manage:assets` (and, if D-02's broadened swap includes catalog/finance/etc., the matching permission strings those routers check) to `AVAILABLE_SCOPES`.**

**Warning signs:** A test that creates an API key with a narrow scope and confirms it succeeds where it should be *rejected* is the correct regression test to add — the naive "does the key work at all" test will pass even with the bug present.

### Pitfall 2: `TokenData` shape is compatible — confirmed, not a risk

**What was checked:** whether downstream code that consumes `current_user` after `_require_itam_admin` assumes a session-only shape.

**Finding:** `auth_types.TokenData` (dataclass) already has `scopes: Optional[List[str]] = None` and `auth_source: str = "session"` as fields with safe defaults (added for Phase 64's ITAM-USR-05 API-key work). `get_current_user_or_api_key()` populates both correctly. Every ITAM endpoint handler reads only `current_user.tenant_id` / `current_user.username` / `current_user.role` — all present on both session and API-key `TokenData` instances. **No downstream break expected.** `[VERIFIED: codebase]`

### Pitfall 3 (CRITICAL): background jobs have no ambient tenant context — inline `trigger_webhook()` calls at mutation points are safe, calls from a scheduler loop are not, by default

**What goes wrong:** `WebhookService.trigger_webhook()` calls `database.get_database()` internally, which wraps the raw Motor db in `TenantIsolatedDatabase`. Every query that wrapper makes injects `tenantId` from the **ambient `contextvars` context** (`tenant_context.get_tenant_id()`) — it does not take a tenant_id parameter. If `trigger_webhook()` is called from code that never ran inside a request (no `set_tenant_id()` call anywhere on the call stack), `get_tenant_id()` returns `None`, and `TenantIsolatedCollection._inject_tenant_id` falls back to a deliberately-unmatchable dummy filter (`"NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"`) — the webhook lookup silently returns zero results for every tenant. The webhook never fires, with no error anywhere.

**Why it happens:** This is a proven, previously-documented bug class in this codebase (see `ticketing_bridge.py`'s own module docstring, and STATE.md's session notes on `compliance_remediation_sla_service.py`) — every `asyncio.create_task(...)`-launched scheduler loop (warranty alerts, close-loop ticket polling, ticket escalation) is deliberately written to receive a **raw, unwrapped** `mongodb.db` handle as a parameter and manually thread `tenantId` through every query/filter by hand, specifically because there is no request to hang tenant context off of.

**Where this actually matters for this phase:**
- **Safe, no action needed:** the 6 events tied to request-scoped mutation points (`asset.checked_out`, `asset.checked_in`, `asset.request_approved`, `asset.request_denied`, and the mutation-triggered part of `consumable.low_stock`) — these fire from inside FastAPI endpoint handlers where `_require_itam_admin`'s `Depends()` chain has already called `set_tenant_id()`. Calling `trigger_webhook()` (or wrapping it in `asyncio.create_task()`) at these points inherits ambient tenant context correctly — `contextvars.copy_context()` (which `asyncio.create_task` uses internally) snapshots the ContextVar's current value at task-creation time, so a later `reset_tenant_id()` on the original request context does not retroactively affect an already-created task.
- **Unsafe unless explicitly fixed:** `asset.warranty_expiring` / `license.expiring_soon` (D-08 — fired from `itam_finance_service.run_warranty_alert_pass`, a raw-db background loop) and the new sweep this phase must add for `asset.audit_overdue` (see Pitfall 6). Both run with **no ambient tenant context whatsoever**.

**How to avoid:** inside the per-asset loop of `run_warranty_alert_pass` (and the new overdue-audit sweep), explicitly bracket the `trigger_webhook()` call with `set_tenant_id()`/`reset_tenant_id()` from `tenant_context.py`, using the `tenant_id` already extracted from each document in the loop:

```python
from tenant_context import set_tenant_id, reset_tenant_id
from webhook_service import WebhookService

_webhook_service = WebhookService()

# inside the existing `async for asset in cursor:` loop, tenant_id already resolved:
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

This exactly mirrors the existing pattern already used for the two independent delivery paths in the same function (in-app notification via raw db passthrough, rule-routed notification via `_RawDbForNotificationRules` adapter) — just applied to `trigger_webhook` instead.

**Warning signs:** a webhook subscription that never delivers for warranty/expiry/audit-overdue events, but works fine for checkout/checkin/request events, with zero errors in logs — this is the signature of the ambient-context-missing failure mode (fails silently, not loudly).

### Pitfall 4: CONTEXT.md's `itam_lifecycle_service.py` reference is a misattribution

**What goes wrong:** A plan written against CONTEXT.md's literal wording ("`itam_lifecycle_service.py`'s check-out/check-in functions") will look in the wrong file.

**Finding `[VERIFIED: codebase]`:** `backend/itam_lifecycle_service.py` contains only audit-trail history helpers (`write_history`, `list_history`, `_apply_known_delta`, `_revert_on_history_failure`) — no checkout/checkin logic at all. The actual checkout/checkin mutation functions are `checkout_asset` (line 94) and `checkin_asset` (line 211) in **`backend/itam_lifecycle_endpoints.py`** — they are endpoint handlers, not service-layer functions, and both already have the exact pre/post state needed for D-06's before/after-diff payload:
- `pre_image` = the document `find_one_and_update(..., return_document=ReturnDocument.BEFORE)` returns.
- `updated` = `_apply_known_delta(pre_image, set_doc, unset_doc)` — the reconstructed after-state, already computed a few lines later without a second DB read.

**Correct insertion point** (checkout, mirror for checkin): immediately after `invalidate_cache("assets:*")` and before the `await log_itam_action(...)` call (or after it — no ordering dependency), fire-and-forget:

```python
asyncio.create_task(webhook_service.trigger_webhook("asset.checked_out", {
    "assetId": asset_id,
    "before": {k: pre_image.get(k) for k in ("lifecycleStatus", "assignedToType", "assignedToId")},
    "after": {k: updated.get(k) for k in ("lifecycleStatus", "assignedToType", "assignedToId", "checkedOutAt", "checkedOutBy")},
    "asset": updated,
}))
```

**How to avoid:** the plan's file list for D-07's lifecycle events must name `itam_lifecycle_endpoints.py`, not `itam_lifecycle_service.py`.

### Pitfall 5: D-03's "no versioning precedent exists" is factually incorrect (does not change the decision)

**Finding `[VERIFIED: codebase]`:** `itam_asset_request_endpoints.py`'s router is already mounted at `/api/v1/itam/asset-requests` — a `/v1/` prefix genuinely exists elsewhere in this same ITAM surface (Phase 71). D-03's actual decision (the swapped `_require_itam_admin`-gated routers keep their current unprefixed `/api/itam/*`/`/api/assets/*` paths, no new prefix added) is still the right call — it would be inconsistent and disruptive to retrofit a version prefix onto already-shipped, frontend-consumed paths. Flag this only so the plan's own rationale doesn't repeat the false "no precedent anywhere" claim, and so nobody is surprised later when they notice the asset-request router's prefix.

### Pitfall 6 (CRITICAL): `asset.audit_overdue` has no periodic mechanism to hang either the webhook or the automatic ticket trigger off of

**What goes wrong:** D-05 groups `asset.audit_overdue` with `consumable.low_stock` as "Phase 72's pre-built-report triggers, now also pushed as events," implying a symmetric wiring story with the warranty/expiry events. It is not symmetric. `consumable.low_stock` genuinely has a mutation trigger (`ConsumableService.checkout_consumable`'s quantity decrement — see below). `asset.audit_overdue` does not: audit-overdue status is purely a function of elapsed time (`now - lastAuditedAt > AUDIT_INTERVAL_DAYS`, 365 days, `itam_lifecycle_endpoints.py` line 35) with no corresponding mutation — nothing writes to the asset when it silently crosses the overdue threshold.

**Confirmed prior deliberate decision:** the existing `GET /reports/overdue-audit` route (`itam_lifecycle_endpoints.py` line 509) has an explicit comment: *"computed at request time... deliberately not a background sweep (D-03; top recorded milestone risk)."* This phase's D-05/D-10 (webhook + automatic ticket trigger for the same condition) both require exactly the periodic sweep that decision avoided.

**How to avoid:** build one small new periodic sweep (new function, e.g. `itam_finance_service.run_audit_overdue_alert_pass(db)` or a new sibling module, following the identical raw-db/manual-tenantId/marker-field pattern as `run_warranty_alert_pass`) that:
1. Runs on a sensible cadence (daily is plenty — this is a 365-day threshold, not an hourly one; reuse the existing hourly `_WARRANTY_SWEEP_INTERVAL_SECONDS` cadence if simplicity is preferred over precision).
2. Reuses `_overdue_query`/`_overdue_row` from `itam_lifecycle_endpoints.py` (already imported by `itam_reporting_prebuilt.py` for the exact same purpose — safe to import a third time) so the sweep's "overdue" definition can never drift from the report's.
3. Uses an `auditOverdueAlertSentAt`-style marker field (mirroring `warrantyAlertSentAt`) to avoid re-firing every pass for the same asset.
4. Fires both `trigger_webhook("asset.audit_overdue", ...)` (with explicit `set_tenant_id`/`reset_tenant_id` bracketing per Pitfall 3) AND, per D-10, the new ticketing-bridge automatic trigger, from the same pass.
5. Is registered in `app_startup.py` next to the other 4 existing `asyncio.create_task(start_*_scheduler(_mdb.db))` calls.

This is new scope beyond a literal reading of D-05/D-08's wording, but it is required for D-05 and D-10 to actually be deliverable — flag this explicitly to the user/planner as a necessary addition, not a silent scope expansion.

### Pitfall 7: CONTEXT.md's `integration_service_ticketing.py` reference is a misattribution

**Finding `[VERIFIED: codebase]`:** `backend/integration_service_ticketing.py` defines `IntegrationServiceTicketingMixin` — a class with its own `create_ticket`/`_create_jira_ticket`/`_create_servicenow_ticket`/`_create_zoho_ticket` methods, mixed into `integration_service.py`'s `IntegrationService` class. This is a **different, unrelated code path** (general SaaS/vendor ticketing) from the one `ticketing_bridge.py` actually uses.

`ticketing_bridge.py` imports `get_ticketing_config`, `create_jira_ticket`, `create_servicenow_incident` from **`backend/ticketing_service.py`** — this is the correct, actually-reused module for D-09. Do not touch `integration_service_ticketing.py`; it is out of scope entirely.

### Pitfall 8: `trigger_webhook()` dispatches sequentially with a 10s-per-webhook timeout — don't `await` it inline in a request handler

**What goes wrong:** `WebhookService.trigger_webhook()` iterates all matching webhooks in a plain `for` loop (`async with httpx.AsyncClient() as client: for hook in webhooks: await self._send_single_webhook(...)`), each with a 10-second timeout. If a tenant has configured 3 webhook subscribers to `asset.checked_out` and one target is slow/unresponsive, a directly-`await`ed call inside `checkout_asset` would make the check-out HTTP response hang for up to ~30 seconds.

**How to avoid:** use `asyncio.create_task(webhook_service.trigger_webhook(...))` at every inline call site (matching the existing precedent in `notification_manager.py`) rather than a blocking `await`. This is still "inline... no new event-dispatch abstraction layer" per D-07 — it's one line at the mutation point, just non-blocking. Confirmed safe re: tenant context per Pitfall 3's contextvars explanation for request-scoped call sites.

### Pitfall 9: webhook subscription CRUD is only partially wired to API-key auth already — adjacent, not blocking

**Finding:** `webhook_endpoints.py`'s `GET`/`POST`/`GET .../deliveries` routes use `Depends(get_current_user_or_api_key)` already (pre-existing, confirms CONTEXT.md's claim). But `PUT /{webhook_id}` (`update_webhook`) and `POST /{webhook_id}/test` (`test_webhook`) still use plain `Depends(get_current_user)` — an inconsistency, not something D-01/D-02 need to fix (those decisions scope only the `itam_*_endpoints.py` routers), but worth a one-line note/flag in the plan in case the reviewer expects full consistency across all API-key-reachable surfaces touched this phase.

## Code Examples

### D-05/D-07: `consumable.low_stock` — a genuine mutation-triggered event

`ConsumableService.checkout_consumable` (`itam_consumable_service.py` line 88) does an atomic `$inc: {availableQuantity: -quantity}` via `find_one_and_update(..., return_document=ReturnDocument.AFTER)`. The returned document already has the post-decrement `availableQuantity` — the natural insertion point is right after the `if not consumable:` failure-branch, before `return Consumable(**consumable)`:

```python
# after the existing not-found/insufficient-quantity guard, before `return Consumable(**consumable)`:
threshold = consumable.get("reorderThreshold") or DEFAULT_LOW_STOCK_QUANTITY  # itam_reporting_prebuilt.DEFAULT_LOW_STOCK_QUANTITY = 5
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

Reuses the exact threshold-fallback logic `_build_low_stock_consumables_rows` (`itam_reporting_prebuilt.py` line 331) already implements, so the webhook's notion of "low" never disagrees with the report's.

### D-08: bracketing a background-sweep webhook call with explicit tenant context

See Pitfall 3's code example above — this is the one non-obvious code pattern in the whole phase and the plan-checker should specifically verify it's present wherever `trigger_webhook` is called from `run_warranty_alert_pass` or the new audit-overdue sweep.

### D-09: adapter shape to clone

```python
# ticketing_bridge.py's existing adapter — the shape the new ITAM adapter must match:
async def _task_to_alert_shape(db, task: dict) -> dict:
    return {
        "alert_id": task["id"],
        "type": "compliance_remediation",
        "severity": task.get("priority", "medium"),
        "hostname": hostname,       # best-effort asset lookup
        "process": {},
        "mitre_technique": "N/A",
        "description": "...",
        "timestamp": task.get("created_at", ""),
    }
# create_jira_ticket(alert, config) / create_servicenow_incident(alert, config) both consume
# exactly this shape — only "type"/"severity"/"hostname"/"description" carry real per-domain
# meaning; the rest are structural fields both connectors expect present.
```

A new `_itam_event_to_alert_shape(db, event_type: str, payload: dict) -> dict` in `ticketing_bridge.py` (or a sibling module per Claude's Discretion) should produce this same shape, with `"type"` set to something like `"itam_audit_overdue"` / `"itam_request_stuck"`, and `"alert_id"` set to a synthetic-but-stable id (e.g. `f"itam-audit-{asset_id}"`) so `create_ticket_for_remediation_task`'s dedup-by-`ticket_ref` pattern can be mirrored (or a new dedup marker field added to the asset/request doc, matching `warrantyAlertSentAt`'s pattern).

### D-10: Phase 44 SLA/escalation pattern to mirror for "stuck pending approval"

`[VERIFIED: codebase]` File: `backend/tickets_escalation_service.py`, function `run_escalation_pass(db)` (line 34) + `start_escalation_scheduler(db)` (line 94), using `_compute_sla` from `backend/tickets_helpers.py`. Pattern: raw-db background loop, `db.tickets.find({"status": {"$in": [...]}, "escalated": False})`, per-document SLA computation, conditional update. For ITAM's "high-value asset request stuck pending too long," the equivalent sweep queries `db.asset_requests` (note: this collection uses `tenant_id`, snake_case — confirmed in `itam_asset_request_service.py`, unlike most ITAM collections which use `tenantId` camelCase) for `status: "pending"` with `request_date` older than a threshold, filtered to "high-value" per whatever field D-10's plan defines (e.g. `estimatedCost` above a configurable/fixed threshold), and calls the D-09 ticket adapter instead of bumping priority.

## Runtime State Inventory

Not applicable — this is a pure additive/wiring phase (new event-type strings, new call sites, new scope-check code, one new periodic sweep). No renames, no schema migrations, no existing data reinterpretation.

- **Stored data:** No existing documents need migration. New marker fields (`auditOverdueAlertSentAt` or similar) are additive and absent-by-default, matching `warrantyAlertSentAt`'s existing pattern.
- **Live service config:** No n8n/Datadog/Tailscale-style external config involved.
- **OS-registered state:** None.
- **Secrets/env vars:** None new — `jira_url`/`jira_api_token`/`snow_instance`/etc. are reused unchanged per D-11.
- **Build artifacts:** None.

## Environment Availability

Not applicable — no new external dependency, service, or CLI tool. All work is Python (existing FastAPI backend, already-running MongoDB, already-existing tenant Jira/ServiceNow config) plus a small React/TSX array edit.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (backend), existing `backend/tests/` convention |
| Config file | none dedicated — project-wide pytest config already in place |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_api_integrations.py -q` (new file, see Wave 0 Gaps) |
| Full suite command | `backend/venv/bin/python -m pytest backend/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-API-01 | Session auth still works on `_require_itam_admin`-gated routes (regression) | unit | `pytest backend/tests/test_itam_api_integrations.py -k session_auth -x` | ❌ Wave 0 |
| ITAM-API-01 | A `manage:assets`-scoped API key can perform a gated operation | unit | `pytest backend/tests/test_itam_api_integrations.py -k scoped_key_allowed -x` | ❌ Wave 0 |
| ITAM-API-01 | A `read:assets`-only (narrow-scope) API key is REJECTED on a `manage:assets` operation (Pitfall 1 regression) | unit | `pytest backend/tests/test_itam_api_integrations.py -k scope_narrowing_enforced -x` | ❌ Wave 0 |
| ITAM-API-01 | Rate limiter still triggers 429 on a key over its per-minute cap when hit via an ITAM route | unit | `pytest backend/tests/test_itam_api_integrations.py -k rate_limit -x` | ❌ Wave 0 |
| ITAM-API-02 | `checkout_asset`/`checkin_asset` fire `asset.checked_out`/`asset.checked_in` with correct before/after payload | unit | `pytest backend/tests/test_itam_webhook_events.py -k lifecycle -x` | ❌ Wave 0 |
| ITAM-API-02 | `checkout_consumable` fires `consumable.low_stock` only when the post-decrement quantity crosses threshold | unit | `pytest backend/tests/test_itam_webhook_events.py -k low_stock -x` | ❌ Wave 0 |
| ITAM-API-02 | `approve_asset_request`/`reject_asset_request` fire the matching request event | unit | `pytest backend/tests/test_itam_webhook_events.py -k asset_request -x` | ❌ Wave 0 |
| ITAM-API-02 | Warranty/audit-overdue background sweeps set tenant context correctly before dispatching (Pitfall 3 regression — assert `trigger_webhook` is called with the ambient context matching the asset's actual `tenantId`, across 2+ tenants in the fixture) | unit | `pytest backend/tests/test_itam_webhook_events.py -k tenant_context_background -x` | ❌ Wave 0 |
| ITAM-API-03 | New ITAM alert-shape adapter produces the exact shape `create_jira_ticket`/`create_servicenow_incident` expect | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k alert_shape -x` | ❌ Wave 0 |
| ITAM-API-03 | Audit-overdue and stuck-approval automatic triggers create exactly one ticket per condition (dedup guard works) | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k automatic_trigger -x` | ❌ Wave 0 |
| ITAM-API-03 | Manual "Create Ticket" button's endpoint works ad-hoc regardless of automatic-trigger state | unit | `pytest backend/tests/test_itam_ticketing_bridge.py -k manual_create -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted `-k` run for the file(s) touched.
- **Per wave merge:** `pytest backend/tests/test_itam_api_integrations.py backend/tests/test_itam_webhook_events.py backend/tests/test_itam_ticketing_bridge.py -q`.
- **Phase gate:** full `backend/` suite green before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `backend/tests/test_itam_api_integrations.py` — covers ITAM-API-01 (auth swap + scope-narrowing fix + rate limit)
- [ ] `backend/tests/test_itam_webhook_events.py` — covers ITAM-API-02 (all 8 event triggers + tenant-context regression for the 2 background-sweep events)
- [ ] `backend/tests/test_itam_ticketing_bridge.py` — covers ITAM-API-03 (adapter shape + 2 automatic triggers + manual button)
- [ ] Framework install: none — pytest already installed and used project-wide.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | `get_current_user_or_api_key` (existing, unchanged this phase) |
| V3 Session Management | no | API keys are not sessions; no new session state introduced |
| V4 Access Control | **yes — this is the phase's central risk** | `_require_itam_admin` + Pitfall 1's scope-narrowing fix; must ensure narrow-scope keys cannot perform broader operations than granted |
| V5 Input Validation | yes | Webhook `event_type` strings should be validated against a fixed enum/constant list (mirroring `notification_service.VALID_EVENTS`'s existing pattern per Phase 59's own module docstring reference) rather than free-form strings, to prevent typo'd event types silently never matching any subscription |
| V6 Cryptography | yes (pre-existing, unchanged) | Webhook payload HMAC-SHA256 signing (`webhook_service._send_single_webhook`) already implemented; ticket API tokens (`jira_api_token`, ServiceNow basic-auth) reused unchanged |
| V13 API and Web Service | yes | SSRF guard on webhook target URLs (`_is_safe_webhook_url`, blocks private/loopback/link-local/metadata ranges) already implemented and unchanged this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| API-key scope bypass (Pitfall 1) | Elevation of Privilege | Explicit `_scopes_allow()` check added to `_require_itam_admin`, plus `AVAILABLE_SCOPES` extended with the real permission strings |
| Cross-tenant webhook delivery (background sweep, Pitfall 3) | Information Disclosure / Elevation | Explicit `set_tenant_id`/`reset_tenant_id` bracketing around every background-sweep `trigger_webhook()` call, mirroring `run_warranty_alert_pass`'s existing per-document tenant extraction |
| SSRF via webhook target URL | Tampering / Information Disclosure | Already mitigated (`_is_safe_webhook_url`) — no new work, just don't regress it |
| API key used to escalate via `api_key_endpoints.py`/`ldap_endpoints.py` swap (D-02 scope question) | Elevation of Privilege | Flagged in Auth Gate Enumeration — recommend excluding these 2 files from the automatic swap pending explicit confirmation |
| Jira/ServiceNow credential reuse across ITAM + compliance-remediation tickets (D-11) | — (accepted, not a new risk) | Same tenant-level config already used for remediation tickets; no new credential storage introduced |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A daily cadence is sufficient for the new `asset.audit_overdue` sweep (365-day threshold) | Pitfall 6 | If wrong, overdue assets could be alerted/ticketed up to ~24h later than an hourly cadence would catch — low impact given the 365-day granularity, but the plan should make the cadence an explicit, named constant rather than silently reusing the hourly warranty cadence |
| A2 | "High-value" for D-10's stuck-approval trigger maps to an existing `estimatedCost`-style field on `AssetRequestCreate`/`AssetRequest` | Code Examples / D-10 | Not directly verified against `itam_models.py`'s `AssetRequestCreate` field list this session — the plan should confirm the exact field name before writing the threshold query |
| A3 | `manage:assets` is the correct single scope string to add to `AVAILABLE_SCOPES` for D-02's core 7-file swap, with `manage:procurement`/`request:assets` added only if the broader 13-file swap is adopted | Pitfall 1 | If the plan swaps more routers than it adds matching scopes for, scoped keys will be unable to ever pass those routers' checks (a usability gap, not a security gap — fails closed) |

## Open Questions

1. **Should `ldap_endpoints.py` and `api_key_endpoints.py` be included in the D-02 auth swap?**
   - What we know: both use the identical `_require_itam_admin` gate; D-02's literal named list (asset/lifecycle/license/consumable/component/finance/reports) doesn't include them.
   - What's unclear: whether their omission from D-02's list was deliberate or just an incomplete enumeration at CONTEXT.md-authoring time.
   - Recommendation: default to swapping `itam_catalog_endpoints.py`/`itam_kpi_endpoints.py`/`itam_data_endpoints.py`/`itam_label_endpoints.py` (unambiguously ITAM data, matches D-02's stated rationale) but leave `ldap_endpoints.py` and `api_key_endpoints.py` on session-auth-only unless the user confirms otherwise — surface this as an explicit checkpoint in the plan.

2. **What cadence and threshold field should the new `asset.audit_overdue`/stuck-approval sweep(s) use?**
   - What we know: the existing warranty sweep runs hourly; audit-overdue's own threshold is 365 days (far coarser); Phase 44's ticket-escalation sweep runs every 5 minutes (much finer, appropriate for its own SLA windows, not necessarily appropriate here).
   - What's unclear: no existing precedent dictates the right cadence for a 365-day-threshold condition.
   - Recommendation: daily is more than adequate; make it a named constant (not a magic number) so it's trivially tunable later.

3. **Does D-10's "high-value asset request" threshold need to be tenant-configurable, or is a fixed constant acceptable for this phase?**
   - What we know: D-11 explicitly rules out new settings UI for ticketing config; nothing in CONTEXT.md addresses whether the high-value dollar threshold itself needs to be configurable.
   - What's unclear: whether a fixed constant (mirroring `DEFAULT_LOW_STOCK_QUANTITY`'s fixed-fallback pattern) is acceptable, or whether this needs to read an existing tenant setting.
   - Recommendation: default to a fixed constant for this phase (matches the phase's overall "wiring, not new config surfaces" spirit) — confirm with the user only if this feels under-specified during planning.

## Sources

### Primary (HIGH confidence — direct codebase inspection this session)

- `backend/api_key_auth.py` — full read, `get_current_user_or_api_key`/`APIKeyService`/`AVAILABLE_SCOPES`
- `backend/rbac_utils.py` — `verify_permission` implementation (confirmed no scope check)
- `backend/rbac_service.py` — `RBACService.has_permission`/`_scopes_allow`/`require_role` (confirmed scope-narrowing logic lives here, not in `verify_permission`)
- `backend/auth_types.py` — `TokenData` dataclass shape
- `backend/webhook_service.py` — full read, `trigger_webhook`/`_send_single_webhook`/SSRF guard
- `backend/webhook_endpoints.py` — full read, subscription CRUD + auth-dependency-per-route audit
- `components/WebhookManagement.tsx` — `availableEvents` array (8 existing entries, confirmed shape)
- `backend/ticketing_bridge.py` — full read, `_task_to_alert_shape`/`create_ticket_for_remediation_task`/`run_close_loop_pass`
- `backend/ticketing_service.py`, `backend/integration_service_ticketing.py` — function listings, confirmed CONTEXT.md's module-name misattribution
- `backend/itam_asset_endpoints.py`, `itam_catalog_endpoints.py`, `itam_lifecycle_endpoints.py`, `itam_license_endpoints.py`, `itam_license_service.py`, `itam_consumable_endpoints.py`, `itam_consumable_service.py`, `itam_component_endpoints.py`, `itam_finance_endpoints.py`, `itam_finance_service.py`, `itam_reporting_endpoints.py`, `itam_reporting_prebuilt.py`, `itam_data_endpoints.py`, `itam_kpi_endpoints.py`, `itam_label_endpoints.py`, `itam_lifecycle_service.py`, `itam_asset_request_endpoints.py`, `itam_asset_request_service.py`, `itam_procurement_endpoints.py`, `itam_customization_endpoints.py`, `itam_scheduled_tasks.py`, `ldap_endpoints.py` — grepped/read for auth-gate enumeration and mutation-point identification
- `backend/database.py` — `TenantIsolatedCollection`/`TenantIsolatedDatabase`/`get_database` — confirmed ambient-tenant-context mechanism
- `backend/tenant_context.py` — full read, `set_tenant_id`/`reset_tenant_id`/`get_tenant_id` (contextvars-based)
- `backend/app_startup.py` — confirmed exact scheduler registration lines for all 4 existing background jobs
- `backend/tickets_escalation_service.py` — full read, Phase 44's SLA/escalation pattern (`run_escalation_pass`/`start_escalation_scheduler`)
- `backend/notification_manager.py` — confirmed `asyncio.create_task(trigger_webhook(...))` fire-and-forget precedent
- `.planning/phases/71-procurement-asset-workflow/71-01/02/03-SUMMARY.md` — confirmed ITAM-PRO-04/05 actually completed (REQUIREMENTS.md's traceability table is stale)
- `.planning/phases/44-remediation-sla-escalation/` — confirmed directory exists, matches CONTEXT.md's reference

### Secondary (MEDIUM confidence)

- None — every claim in this document was checked directly against the codebase; no WebSearch/Context7 lookups were needed since this phase involves zero new external libraries or APIs.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, fully verified by reading every touched file
- Architecture: HIGH — every mutation point, auth gate, and background-job pattern was read directly, not inferred
- Pitfalls: HIGH — Pitfall 1 (scope-narrowing gap) and Pitfall 6 (missing audit-overdue scheduler) are both traced to their exact root cause in the actual function bodies, not speculation

**Research date:** 2026-08-18
**Valid until:** No expiry concern — this is pure internal-codebase research with no external API/library version dependency. Re-verify only if the underlying files (`api_key_auth.py`, `webhook_service.py`, `ticketing_bridge.py`, `rbac_service.py`) change before this phase is planned/executed.
