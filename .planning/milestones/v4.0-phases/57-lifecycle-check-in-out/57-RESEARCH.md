# Phase 57: Lifecycle & Check-In/Out - Research

**Researched:** 2026-08-04
**Domain:** FastAPI + MongoDB (Motor) backend — asset-lifecycle state transitions, append-only audit trail, on-demand reporting. Backend/API-only (no frontend this phase).
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 (Assignee model):** Check-out target for "a user" is an existing platform User account (`backend/models.py` `User`, the `users` collection) — no new lightweight "Person" (non-login) catalog entity is introduced this phase. Reversibility: reversible — a non-login Person type can be added later as an additive alternate target without touching existing checkout records.

**D-02 (Location field reuse):** Checking an asset out to a location overwrites the asset's existing `locationId` field (`backend/itam_models.py` `ManualAssetCreate.locationId`) rather than introducing a separate `assignedLocationId`. `locationId` means "where the asset currently is," whether that's its catalogued home or a checked-out location. Reversibility: costly — once `locationId` is overwritten going forward, splitting it into a separate "home location" + "current location" later requires backfilling home-location values from the append-only assignment-history entries, since the original value won't be recoverable from the asset document itself after the first checkout.

**D-03 (Overdue-audit threshold):** "Overdue for audit" uses a fixed default interval of 12 months since the last physical-audit date (or since creation, if never audited) — not a per-tenant or per-model configurable setting. Reversibility: reversible — a config value; can be made tenant- or model-configurable later without a migration.

**D-04 (Checkout metadata):** Check-out captures an optional free-text note and an optional expected-return date, in addition to who/where/when. The expected-return date is what enables a future "overdue check-out" report without a later schema change. Reversibility: reversible — both fields are additive and optional.

### Claude's Discretion

Exact shape of the assignment-history collection/schema (separate collection vs. embedded array), the checkout/checkin endpoint routes and request/response contracts, and how the overdue-audit report is computed (query vs. precomputed) are implementation details for research/planning — the decisions above only fix the *user-facing* semantics.

(This research document's Standard Stack / Architecture Patterns sections resolve these discretion points: separate `assignment_history` collection, action-endpoint routes under `/api/assets/{asset_id}/...`, query-time overdue computation.)

### Deferred Ideas (OUT OF SCOPE)

- Non-login "Person" checkout targets (e.g. contractors without platform accounts) — deferred; platform Users only for v1 (D-01). Revisit if real usage shows a gap.
- Per-tenant or per-model configurable audit interval — deferred; fixed 12-month default for v1 (D-03).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ITAM-LIFE-02 | User can check out a deployable-status asset to a user or a location; checkout is rejected for assets not in a deployable-typed status | Pattern 1 (atomic guarded transition), Code Examples (CheckoutRequest + target-existence validation), Pitfall 2 (TOCTOU race) |
| ITAM-LIFE-03 | User can check in an asset, returning it to stock/available and clearing its current assignment | Pattern 1 (same atomic-transition shape, reverse direction), Architecture Diagram |
| ITAM-LIFE-04 | Every check-out/check-in is recorded in an append-only assignment history visible per asset (who, where, when) | Pattern 2 (append-only audit module), Pitfall 3 (no update/delete), Security Domain (audit-log tampering mitigation) |
| ITAM-LIFE-05 | User can mark an asset as physically audited on a given date and pull a report of assets overdue for audit | Pattern 3 (query-time overdue report), Standard Stack Alternatives Considered (rejected background-sweep approach) |

</phase_requirements>

## Summary

Phase 57 is additive backend work on top of Phase 56's already-shipped `itam_models.py` / `itam_asset_endpoints.py` / `itam_catalog_endpoints.py`. There is no framework-selection risk here — every primitive needed (tenant isolation, RBAC gate, atomic guarded state transition, append-only audit collection, `$or`/range report queries) already has at least one working precedent in this codebase. The job is disciplined reuse, not invention.

Three in-repo analogs cover the entire phase: `compliance_status_endpoints.py`'s `find_one_and_update`-based atomic status transition (the pattern for gating checkout on `lifecycleStatus == deployable` and eliminating the TOCTOU window), `remediation_audit_service.py`'s two-function (`write_audit`/`list_audit`) append-only collection module (the pattern for `assignment_history`), and `itam_catalog_endpoints.py` / `itam_asset_endpoints.py` themselves (the RBAC gate, tenant-isolated collection access, and router registration/priority conventions to extend rather than fork).

**Primary recommendation:** Add a new `assignment_history` collection (separate collection, not an embedded array — matches the codebase's existing `remediation_audit`/`evidence_audit_log` precedent and avoids the 16MB-document/write-amplification risk of appending to the asset document itself), a new `backend/itam_lifecycle_endpoints.py` router registered in `router_registry.py` immediately after `itam_asset_endpoints.py`, and sub-resource routes (`POST /api/assets/{asset_id}/checkout`, `/checkin`, `/audit`, `GET /api/assets/{asset_id}/history`, `GET /api/assets/overdue-audit`) that never collide with `asset_endpoints.py`'s single-segment `GET /{asset_id}` route regardless of registration order.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Checkout/checkin state transition (lifecycleStatus + assignment fields on `assets`) | API / Backend | Database / Storage | Business rule (deployable-gated) belongs in the endpoint handler; the atomic guard is expressed as a Mongo filter, not application-level check-then-write |
| Append-only assignment history | Database / Storage | API / Backend | Collection is the source of truth; API only ever inserts/reads, mirroring `remediation_audit_service.py`'s insert-only contract |
| Overdue-audit report | API / Backend | Database / Storage | Computed at query time from an indexed date field — no new background scheduler, no materialized/precomputed collection needed for a v1 admin report |
| RBAC gate (`manage:assets`) | API / Backend | — | Existing `_require_itam_admin` dependency in `itam_asset_endpoints.py`; reused verbatim, not reimplemented |
| Location/assignee reference validation | API / Backend | Database / Storage | Existence checks against `db.locations`/`db.users` happen in the endpoint handler before the atomic write, same shape as `itam_asset_endpoints.create_manual_asset`'s `manufacturerId`/`modelId` checks |

## Package Legitimacy Audit

**Not applicable this phase.** No new third-party packages are introduced — the phase is pure FastAPI/Pydantic/Motor code reusing the stack already installed for Phase 56. `Standard Stack` below lists only already-installed, in-repo-verified libraries.

## Standard Stack

### Core (already installed — verified via grep of Phase 56 code, not a new install)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (existing pin, see `backend/requirements.txt`) | Router/endpoint definitions | Already used by every ITAM/backend module; no alternative considered |
| Pydantic v2 | (existing pin) | Request/response contracts (`itam_models.py` already uses `ConfigDict(extra="forbid")` v2 syntax) | Matches `itam_models.py` exactly — new lifecycle models must use the same v2 idiom |
| Motor (`motor.motor_asyncio`) | (existing pin) | Async MongoDB driver, via `TenantIsolatedDatabase`/`TenantIsolatedCollection` | Sole DB access path in this codebase; never call `pymongo` sync driver directly |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-asyncio` (already installed) | existing | `@pytest.mark.asyncio` test decoration | `test_itam_foundation.py` already uses this — new `test_itam_lifecycle.py` should match, not introduce `asyncio.run()` wrapper pattern used elsewhere in the repo (that pattern predates pytest-asyncio being installed for this module) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate `assignment_history` collection | Embedded array on the asset document | Rejected — `[CITED: MongoDB schema-design guidance]` embedded audit arrays risk the 16MB document cap and degrade write performance as history grows; the codebase's own two existing audit-trail precedents (`remediation_audit`, `evidence_audit_log`) both use separate collections, not embedded arrays |
| Query-time overdue computation | Precomputed/materialized "overdue" flag updated by a background sweep | Rejected for v1 — no other requirement in this phase needs a background scheduler, and introducing one repeats the exact tenant-isolation background-scheduler bug class flagged as the milestone's top risk (STATE.md 2026-08-04 session note: sweeps must use raw `db._db` + explicit `set_tenant_id`, easy to get wrong). A single indexed date-range query at report-request time is simpler and correct by construction. |

**Installation:** None — no new packages.

**Version verification:** Not applicable — no new packages recommended.

## Architecture Patterns

### System Architecture Diagram

```
Client (admin, manage:assets)
      │
      ├─ POST /api/assets/{asset_id}/checkout {targetType, targetId, note?, expectedReturnDate?}
      │       │
      │       ▼
      │   _require_itam_admin (RBAC gate, reused)
      │       │
      │       ▼
      │   resolve asset by id + tenant (db.assets.find_one)
      │       │
      │       ▼
      │   validate target exists (db.users.find_one for user target,
      │   or db[locations].find_one for location target)
      │       │
      │       ▼
      │   ATOMIC guarded transition:
      │   db.assets.find_one_and_update(
      │     {id, lifecycleStatus: "deployable"},           <- guard clause
      │     {$set: {lifecycleStatus: "deployed",
      │              assignedToUserId | locationId,
      │              checkedOutAt, checkedOutBy}})
      │       │
      │       ├─ prior_doc is None → 409 (not deployable / already checked out)
      │       ▼
      │   insert assignment_history doc (action="checkout", who, where, when,
      │   note, expectedReturnDate) — INSERT ONLY, never update/delete
      │       │
      │       ▼
      │   200 response (asset + history entry)
      │
      ├─ POST /api/assets/{asset_id}/checkin
      │       │  same shape: atomic find_one_and_update clears assignment fields
      │       │  and sets lifecycleStatus back to "deployable"; insert history
      │       │  doc with action="checkin"
      │       ▼
      │
      ├─ POST /api/assets/{asset_id}/audit {auditedAt?}
      │       │  sets lastAuditedAt on the asset (does NOT touch lifecycleStatus
      │       │  or assignment — a physical audit is orthogonal to checkout state)
      │       ▼
      │
      ├─ GET /api/assets/{asset_id}/history
      │       │  reads assignment_history filtered by assetId + tenantId, sorted
      │       │  by ts desc — mirrors remediation_audit_service.list_audit
      │       ▼
      │
      └─ GET /api/assets/overdue-audit
              │  query-time computation: assets where
              │  (lastAuditedAt < now - 12mo) OR
              │  (lastAuditedAt absent AND createdAt < now - 12mo)
              ▼
          returns list of overdue assets (id, name, assetTag, lastAuditedAt|null, daysOverdue)
```

### Recommended Project Structure
```
backend/
├── itam_models.py                 # extend: CheckoutRequest, CheckinRequest, AuditMarkRequest,
│                                   #   AssignmentHistoryEntry — same file Phase 56 already owns
├── itam_lifecycle_endpoints.py    # NEW — checkout/checkin/audit-mark/history/overdue-report routes
├── itam_lifecycle_service.py      # NEW (optional, only if handler logic exceeds ~150 lines per
│                                   #   endpoint file — CLAUDE.md 500-line cap) — houses the atomic
│                                   #   transition + assignment_history insert/list helpers, mirroring
│                                   #   remediation_audit_service.py's DB-only, no-FastAPI-import shape
├── router_registry.py             # MODIFY — register itam_lifecycle_endpoints router
├── database.py                    # MODIFY — add assignment_history + lastAuditedAt-related indexes
│                                   #   in connect_to_mongo() (compound tenantId+assetId, tenantId+ts)
└── tests/
    └── test_itam_lifecycle.py     # NEW — mirrors test_itam_foundation.py's MockTenantIsolatedDatabase
                                    #   fixture pattern exactly
```

### Pattern 1: Atomic guarded state transition (checkout gate)
**What:** Use `find_one_and_update` with the guard condition (`lifecycleStatus: "deployable"`) baked into the filter, not a separate `find_one` read followed by a conditional `update_one`.
**When to use:** Any lifecycle transition where two concurrent requests could both pass a naive "read status, then write" check (checkout, checkin, and — later phases — license seat assignment).
**Example:**
```python
# Source: backend/compliance_status_endpoints.py:76-88 (in-repo precedent, adapted)
prior_doc = await db.assets.find_one_and_update(
    {"id": asset_id, "lifecycleStatus": "deployable"},
    {
        "$set": {
            "lifecycleStatus": "deployed",
            "assignedToType": target_type,          # "user" | "location"
            "assignedToId": target_id,
            "locationId": location_id_if_applicable,  # D-02: overwrites existing locationId
            "checkedOutAt": now.isoformat(),
            "checkedOutBy": actor_user_id,
            "updatedAt": now.isoformat(),
        },
    },
    return_document=ReturnDocument.BEFORE,  # or AFTER — pick one, document the choice
)
if prior_doc is None:
    # Either the asset doesn't exist, or it wasn't in a deployable status —
    # disambiguate with a preceding find_one({"id": asset_id}) only for the 404 case.
    ...
```
**Note:** `TenantIsolatedCollection.find_one_and_update` (`backend/database.py:89-90`) already injects `tenantId` into the filter automatically — do not add it manually or the guard becomes `{"id", "lifecycleStatus", "tenantId", "tenantId"}` duplication (harmless but redundant).

### Pattern 2: Append-only audit-trail module (assignment history)
**What:** A tiny DB-only module exposing exactly two functions — `write_history` (insert) and `list_history` (read) — with no update/delete function defined anywhere, making tampering require an out-of-band DB operation, not an API call.
**When to use:** ITAM-LIFE-04's append-only requirement.
**Example:**
```python
# Source: backend/remediation_audit_service.py (in-repo precedent, adapted 1:1)
async def write_history(db, tenant_id: str, record: Dict[str, Any]) -> str:
    """Inserts one immutable assignment-history record. No update/delete function
    exists in this module — a record, once written, cannot be altered via this API."""
    doc = dict(record)
    doc.setdefault("tenantId", tenant_id)
    doc.setdefault("ts", datetime.now(timezone.utc).isoformat())
    result = await db.assignment_history.insert_one(doc)
    return str(result.inserted_id)

async def list_history(db, tenant_id: str, asset_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    query = {"tenantId": tenant_id, "assetId": asset_id}
    cursor = db.assignment_history.find(query, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)
```

### Pattern 3: Query-time overdue report (no scheduler)
**What:** A single indexed range query against `lastAuditedAt` (falling back to `createdAt` when absent), computed on request, not via a background sweep.
**When to use:** ITAM-LIFE-05's overdue-audit report, given D-03's fixed 12-month interval.
**Example:**
```python
cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
cursor = db.assets.find({
    "$or": [
        {"lastAuditedAt": {"$lt": cutoff}},
        {"lastAuditedAt": {"$exists": False}, "createdAt": {"$lt": cutoff}},
    ],
}, {"_id": 0, "id": 1, "name": 1, "assetTag": 1, "lastAuditedAt": 1, "createdAt": 1})
```
Requires a compound index `(tenantId, lastAuditedAt)` — add alongside the other Phase 57 indexes in `database.py::connect_to_mongo()`, following the existing pattern (e.g. `tickets.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])`).

### Anti-Patterns to Avoid
- **Embedding assignment history as an array field on the asset document:** Rejected per Standard Stack above — use a separate collection.
- **Read-then-write status check:** `if asset["lifecycleStatus"] == "deployable": update(...)` — introduces a TOCTOU race between two concurrent checkout requests. Always fold the guard into the `find_one_and_update` filter (Pattern 1).
- **Writing to `assets.status`:** That key is exclusively agent-liveness (Phase 56 decision, restated in CONTEXT.md D-02 discussion and `itam_asset_endpoints.py`'s own comment). Checkout/checkin/audit-mark must only ever touch `lifecycleStatus` and the new assignment/audit fields, never `status`.
- **A generic `PATCH /api/assets/{asset_id}` for lifecycle transitions:** Phase 56 shipped no update endpoint at all for manual assets (`itam_asset_endpoints.py` has only `POST`); a bare PATCH that accepts arbitrary field changes would let a caller set `lifecycleStatus` without going through the deployable-gate business rule or writing a history entry. Use dedicated action endpoints (`/checkout`, `/checkin`, `/audit`) instead — same shape as `remediation_control_endpoints.py`'s `/approve`/`/deny` action-endpoint convention, not a bare PATCH.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tenant isolation on the new `assignment_history` collection | Manual `tenantId` filter/injection logic | `TenantIsolatedDatabase`/`TenantIsolatedCollection` (`backend/database.py`) — collection is NOT in the exemption allowlist, so it is auto-wrapped | Every other per-tenant collection in this codebase goes through this wrapper; a hand-rolled equivalent risks a cross-tenant leak the wrapper already prevents by construction |
| RBAC gate for checkout/checkin/audit-mark | A new permission or new dependency function | `_require_itam_admin` — copy the dependency function (or import it) from `itam_asset_endpoints.py`, gated on the existing `manage:assets` permission | CONTEXT.md explicitly locks this: "reuse rather than defining a new RBAC gate" |
| Atomic status-transition race prevention | Application-level locking, retries, or optimistic-concurrency version field | `find_one_and_update` with the guard clause in the filter (Pattern 1) | Native Mongo document-level atomicity already solves this; no new dependency, no new failure mode |
| Overdue-interval math (12 months) | A cron/celery-style scheduled job | A single query-time date comparison (Pattern 3) | D-03 locks a fixed, non-configurable interval — no state to precompute, no staleness window to manage |

**Key insight:** Every "hard part" of this phase (tenant isolation, RBAC, atomic transitions, append-only audit) is already solved elsewhere in this codebase. The risk in this phase is architectural drift (forking a new pattern where an existing one applies), not missing library support.

## Common Pitfalls

### Pitfall 1: Colliding with the agent-liveness `status` field
**What goes wrong:** A lifecycle-transition endpoint accidentally sets or reads `assets.status` instead of `assets.lifecycleStatus`.
**Why it happens:** Both fields sit on the same `assets` document and have overlapping English meanings ("status"); `asset_endpoints.py` (the legacy agent-facing router) already writes `status` for connectivity/heartbeat purposes.
**How to avoid:** Every write in this phase's endpoints must literally use the string `lifecycleStatus`, never `status`. Grep the diff for `"status"` (not `lifecycleStatus`) before considering a task done — `itam_asset_endpoints.py`'s own header comment already documents this trap for manual-asset creation; the same discipline applies here.
**Warning signs:** A test that checks `assets.status` changed after checkout — that's testing the wrong field.

### Pitfall 2: TOCTOU race on the deployable-gate check
**What goes wrong:** Two near-simultaneous checkout requests for the same asset both read `lifecycleStatus == "deployable"` before either write lands, and both succeed — the asset ends up "checked out" to two different targets, with only the second write's assignment fields surviving (silent data loss, not even a visible error).
**Why it happens:** A naive `if (await db.assets.find_one(...))["lifecycleStatus"] == "deployable": await db.assets.update_one(...)` implementation.
**How to avoid:** Pattern 1 — bake `lifecycleStatus: "deployable"` into the `find_one_and_update` filter itself; a `None` return means the guard failed (either not found or not deployable).
**Warning signs:** No test exercises two concurrent checkout calls against the same asset (56-01's `test_itam_foundation.py` has a precedent for this: `asyncio.gather`-based concurrency test against the counter — the same shape should be written for checkout).

### Pitfall 3: Assignment history that can be edited or deleted via the API
**What goes wrong:** Adding a `PATCH`/`DELETE` route on `assignment_history` "for corrections," defeating ITAM-LIFE-04's append-only requirement and the audit-trail's forensic value.
**Why it happens:** Reviewers/support staff will eventually ask for a way to fix a typo'd note.
**How to avoid:** Follow `remediation_audit_service.py`'s module contract exactly — only `write_history`/`list_history` exist; a correction is a *new* history entry (e.g., `action="correction"` referencing the original entry's id), never an update to the original row.
**Warning signs:** A route or service function with `update`/`delete`/`edit` in its name touching `assignment_history`.

### Pitfall 4: Router registration order assumption
**What goes wrong:** Assuming the inline comment in `itam_asset_endpoints.py` ("registered *after* asset_endpoints") reflects the actual `router_registry.py` order, and building new sub-resource routes that implicitly depend on that assumption.
**Why it happens:** The comment is stale — `[VERIFIED: backend/router_registry.py:82-84]` the actual registration order is `itam_catalog_endpoints` → `itam_asset_endpoints` → `asset_endpoints` (ITAM routers load FIRST, opposite of what the comment claims).
**How to avoid:** In practice this doesn't matter for Phase 57 because every new route this phase adds is multi-segment (`/{asset_id}/checkout`, `/{asset_id}/history`, `/overdue-audit`) and Starlette matches by exact path template, not prefix — none of these collide with `asset_endpoints.py`'s single-segment `GET /{asset_id}` regardless of order. Still, register the new `itam_lifecycle_endpoints` router immediately adjacent to `itam_asset_endpoints` in `router_registry.py` (not scattered elsewhere) and do not add a new bare `GET /{asset_id}` or `PATCH /{asset_id}` route to the ITAM side — that WOULD collide, and win or lose based on this exact (currently ITAM-first) order.
**Warning signs:** A new route with zero path segments beyond `{asset_id}` in the ITAM lifecycle router.

## Code Examples

### Checkout request/response contracts (extend itam_models.py)
```python
# New in itam_models.py, following the existing ManualAssetCreate style (extra="forbid")
class CheckoutRequest(BaseModel):
    targetType: Literal["user", "location"]
    targetId: str  # userId (must exist in db.users) or locationId (must exist in db.locations)
    note: Optional[str] = None                      # D-04
    expectedReturnDate: Optional[str] = None         # D-04, ISO date string

    model_config = ConfigDict(extra="forbid")


class CheckinRequest(BaseModel):
    note: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class AuditMarkRequest(BaseModel):
    auditedAt: Optional[str] = None  # defaults to now if omitted

    model_config = ConfigDict(extra="forbid")
```

### Target-existence validation (mirrors itam_asset_endpoints.create_manual_asset's manufacturerId/modelId checks)
```python
# Source pattern: backend/itam_asset_endpoints.py:83-96 (adapted)
if payload.targetType == "user":
    target = await db.users.find_one({"id": payload.targetId})
    if not target:
        raise HTTPException(status_code=400, detail=f"targetId '{payload.targetId}' (user) not found.")
else:  # "location"
    target = await db.locations.find_one({"id": payload.targetId})
    if not target:
        raise HTTPException(status_code=400, detail=f"targetId '{payload.targetId}' (location) not found.")
```
Note: `db.users` is NOT in `TenantIsolatedDatabase`'s exemption allowlist (`backend/database.py:123-134` lists `compliance_frameworks`, `tenants`, `roles`, etc. — `users` is absent), so `db.users.find_one({"id": ...})` is automatically tenant-scoped — a cross-tenant user id will correctly resolve to "not found," closing an IDOR vector without extra code.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A — this is new functionality on an established codebase pattern set | Reuse the Phase 56 tenant-isolation/RBAC/atomic-transition conventions | Phase 56, 2026-08-04 (same session) | No new pattern class introduced this phase; the codebase's own conventions ARE the state of the art here |

**Deprecated/outdated:** None applicable.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Assignment target for "location" checkout resolves against `db.locations` (the collection name `CATALOG_KINDS["locations"]` maps to) rather than a differently-named collection | Code Examples | Low — `itam_catalog_endpoints.py:32` confirms `CATALOG_KINDS = {"locations": "locations", ...}` via direct grep, so this is actually `[VERIFIED: backend/itam_catalog_endpoints.py:32]`, not assumed. Listed here only because the exact field name used server-side for the reference check should be double-checked against the live collection at implementation time. |
| A2 | A separate `itam_lifecycle_service.py` module is needed only if handler logic exceeds the 500-line CLAUDE.md cap when placed directly in `itam_lifecycle_endpoints.py` | Recommended Project Structure | Low — if the planner keeps `itam_lifecycle_endpoints.py` under 500 lines, this file need not exist this phase; not a hard requirement, an anticipatory recommendation |
| A3 | Snipe-IT's checkout/checkin status semantics (deployable-gated checkout, any-status checkin) generalize as reasonable prior art for this phase's already-locked semantics | Common Pitfalls / Architecture Patterns | Low — D-02/ITAM-LIFE-02/03 requirement text already locks this exact behavior independent of Snipe-IT; the WebSearch citation is corroborating context, not a load-bearing decision source |

**If this table is empty:** N/A — see above; all three assumptions are low-risk corroboration, not load-bearing unverified claims. The core architectural claims in this document (RBAC gate, tenant-isolation wrapper behavior, router registration order, field names) are all `[VERIFIED]` by direct grep/Read of the current codebase, not assumed.

## Open Questions

1. **Exact field names for assignment on the `assets` document** (e.g., `assignedToUserId` + `assignedToLocationId` as two optional fields vs. one polymorphic `assignedToType`/`assignedToId` pair)
   - What we know: D-02 locks that `locationId` is overwritten directly for location checkouts. It does NOT specify the field name(s) for a *user* checkout target — that's genuinely new (no existing field to reuse, unlike `locationId`).
   - What's unclear: Whether to add one polymorphic pair (`assignedToType`, `assignedToId`) or two separate optional fields (`assignedToUserId`, and reuse `locationId` for the location case per D-02).
   - Recommendation: Use `locationId` (reused, per D-02) for location checkouts, and a new `assignedToUserId` field for user checkouts (never populate both simultaneously) — this keeps `locationId`'s existing single meaning ("where the asset currently is") intact and adds exactly one new field, minimizing schema surface. The planner should treat this as a concrete task-level decision, not defer it further — CONTEXT.md's discretion note covers this.

2. **Response shape for `GET /api/assets/{asset_id}/history`**
   - What we know: `remediation_audit_service.list_audit` returns a flat, unpaginated (limit-capped) list.
   - What's unclear: Whether ITAM-LIFE-04's "visible per asset" success criterion needs pagination given assignment history is expected to be low-volume per asset (unlike remediation events).
   - Recommendation: Mirror `list_audit`'s `limit`-only (no cursor pagination) shape for v1 — consistent with the existing precedent and sufficient given per-asset history volume is naturally bounded (checkouts happen at human timescales, not machine timescales).

## Environment Availability

Not applicable — this phase has no new external tool/service/runtime dependencies. MongoDB (already required by the whole backend) and the existing Python/FastAPI/Motor stack are the only dependencies, all already verified present by every prior phase in this milestone (Phase 56 tests pass against the same stack).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`@pytest.mark.asyncio`), `httpx.AsyncClient`/`ASGITransport` for endpoint-level tests |
| Config file | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section found; pytest-asyncio auto-mode presumed active given `test_itam_foundation.py` uses bare `@pytest.mark.asyncio` without an explicit `asyncio_mode` setting |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_itam_lifecycle.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q` (per MEMORY.md: use `backend/venv/bin/python`, NOT system Python — deps installed there; baseline as of 2026-07-22 was 1343 pass / 3 pre-existing unrelated fails) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ITAM-LIFE-02 | Checkout succeeds when `lifecycleStatus == deployable`; rejected (409) otherwise | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkout -x` | ❌ Wave 0 |
| ITAM-LIFE-02 | Checkout to a nonexistent user/location returns 400 | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkout_target -x` | ❌ Wave 0 |
| ITAM-LIFE-02 | Concurrent checkout requests on the same asset — only one succeeds (race test) | unit | `pytest backend/tests/test_itam_lifecycle.py -k concurrent -x` | ❌ Wave 0 |
| ITAM-LIFE-03 | Checkin returns `lifecycleStatus` to `deployable` and clears assignment fields | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkin -x` | ❌ Wave 0 |
| ITAM-LIFE-04 | Every checkout/checkin writes exactly one `assignment_history` entry, no update/delete function exists on the history module | unit | `pytest backend/tests/test_itam_lifecycle.py -k history -x` | ❌ Wave 0 |
| ITAM-LIFE-04 | History is tenant-isolated (cross-tenant read returns empty, not another tenant's rows) | unit | `pytest backend/tests/test_itam_lifecycle.py -k history_tenant_isolation -x` | ❌ Wave 0 |
| ITAM-LIFE-05 | Marking an asset audited sets `lastAuditedAt`; overdue report excludes it until 12 months later | unit | `pytest backend/tests/test_itam_lifecycle.py -k audit_mark -x` | ❌ Wave 0 |
| ITAM-LIFE-05 | Overdue report includes never-audited assets whose `createdAt` is >12 months old | unit | `pytest backend/tests/test_itam_lifecycle.py -k overdue -x` | ❌ Wave 0 |
| ITAM-LIFE-02/03 | Endpoints reject callers without `manage:assets` permission (403) | unit | `pytest backend/tests/test_itam_lifecycle.py -k rbac -x` | ❌ Wave 0 |
| (cross-cutting) | Neither checkout nor checkin ever writes the `status` key (agent-liveness field) | unit | `pytest backend/tests/test_itam_lifecycle.py -k does_not_write_status -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_itam_lifecycle.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_itam_lifecycle.py` — new file, covers all rows above; reuse `MockTenantIsolatedDatabase`/`MockTenantIsolatedCollection`/`_make_col` fixtures from `backend/tests/test_itam_foundation.py` (or promote them to `backend/tests/conftest.py` if a second file needs them — check whether `conftest.py` already has an equivalent before duplicating)
- [ ] Framework install: none — pytest/pytest-asyncio already installed and exercised by `test_itam_foundation.py`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | `Depends(get_current_user)` — unchanged, reused from `authentication_service` |
| V3 Session Management | no | No new session surface introduced |
| V4 Access Control | yes | `_require_itam_admin` (`manage:assets` permission) gates every new endpoint — copy/import from `itam_asset_endpoints.py`, do not redefine a weaker check |
| V5 Input Validation | yes | Pydantic v2 models with `extra="forbid"` (matches `itam_models.py` convention) for `CheckoutRequest`/`CheckinRequest`/`AuditMarkRequest`; explicit existence validation of `targetId` against `db.users`/`db.locations` before the atomic write |
| V6 Cryptography | no | No new crypto surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Authorization bypass — a caller without `manage:assets` hits checkout/checkin/audit-mark directly | Elevation of Privilege | Reuse `_require_itam_admin` as a FastAPI `Depends` on every new route, verified via a dedicated 403 test per route (see Validation Architecture `rbac` row) |
| IDOR on `targetId` (assigning to another tenant's user, or reading another tenant's asset history) | Information Disclosure / Tampering | `TenantIsolatedCollection` auto-injects `tenantId` into every `find_one`/`find` call on `db.users`, `db.locations`, `db.assets`, and the new `db.assignment_history` — a cross-tenant id resolves to "not found," not another tenant's record. `[VERIFIED: backend/database.py:117-136]` `users`/`locations`/`assignment_history` are all absent from the exemption allowlist, so this protection is automatic, not something the endpoint code must implement itself. |
| Audit-log tampering — a compromised admin session or a bug lets someone edit/delete an assignment-history entry to hide a checkout | Repudiation / Tampering | Enforced structurally: the `assignment_history` service module (Pattern 2) exposes only `write_history`/`list_history` — no code path in this phase can update or delete a row. Matches `.planning/codebase/ARCHITECTURE.md` §Anti-Patterns "Missing Audit Trail" control. |
| TOCTOU race on the deployable-gate check — two concurrent checkouts both pass a naively-implemented guard | Tampering (data integrity) | Pattern 1 — atomic `find_one_and_update` with the guard baked into the filter; covered by a dedicated concurrency test (mirrors 56-01's `asyncio.gather` counter test) |
| Overdue-report query as an unauthenticated/under-scoped read of asset location data | Information Disclosure | Same `_require_itam_admin` gate as all other endpoints — the report is not a public or lower-privilege surface; it exposes asset location/assignment data, same sensitivity class as the asset list itself |

## Sources

### Primary (HIGH confidence — verified via Read/grep of the actual codebase this session)
- `backend/remediation_audit_service.py` — append-only audit module pattern (2 functions, no update/delete)
- `backend/itam_asset_endpoints.py` — `_require_itam_admin`, `next_asset_tag`, manual-asset creation flow, router registration comment (found stale, see Pitfall 4)
- `backend/itam_models.py` — `LifecycleStatus`, `DEFAULT_LIFECYCLE_STATUS`, `ManualAssetCreate`, `ASSET_SOURCE_*` discriminators
- `backend/itam_catalog_endpoints.py` — `CATALOG_KINDS`/`CATALOG_REFERENCE_FIELDS` (confirms `locations` → `locationId`)
- `backend/database.py` — `TenantIsolatedDatabase`/`TenantIsolatedCollection`, exemption allowlist (confirms `users`/`locations` are NOT exempt, i.e. ARE auto-isolated), index-creation conventions
- `backend/router_registry.py` — actual registration order (`itam_catalog_endpoints` → `itam_asset_endpoints` → `asset_endpoints`), contradicting the stale inline comment
- `backend/compliance_status_endpoints.py` — atomic `find_one_and_update` guarded-transition pattern with TOCTOU rationale in its own comments
- `backend/remediation_control_endpoints.py` — action-endpoint convention (`/approve`, `/deny`) as the analog for `/checkout`, `/checkin`
- `backend/tests/test_itam_foundation.py` — `MockTenantIsolatedDatabase`/`MockTenantIsolatedCollection` test-fixture pattern, `@pytest.mark.asyncio` usage
- `.planning/codebase/ARCHITECTURE.md` §Anti-Patterns "Missing Audit Trail"
- `.planning/phases/56-catalog-foundation/56-01-SUMMARY.md`, `56-02-SUMMARY.md` — dependency graph (`affects: phase_57_checkout`), decisions log
- `.planning/phases/57-lifecycle-check-in-out/57-CONTEXT.md` — locked decisions D-01 through D-04
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — requirement text, milestone risk notes (background-scheduler tenant-isolation bug class)
- `backend/models.py` — `User` model shape (`id`, `email`, `role`, `tenantId`)
- `backend/rbac_utils.py`, `backend/rbac_service.py` — confirms `manage:assets` permission already provisioned to relevant roles

### Secondary (MEDIUM confidence — WebSearch, corroborating already-locked decisions)
- MongoDB schema-design guidance on separate-collection vs. embedded-array audit trails (general best-practice corroboration for the Standard Stack recommendation)
- Snipe-IT checkout/checkin deployable-status behavior (corroborates, does not drive, the already-locked ITAM-LIFE-02/03 semantics)

### Tertiary (LOW confidence)
None used as load-bearing claims this phase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; every primitive verified present and in-use in the current tree
- Architecture: HIGH — three concrete in-repo analogs (audit module, atomic transition, action-endpoint router) cover 100% of the phase's structural needs
- Pitfalls: HIGH — all four pitfalls are grounded in direct code reads this session (stale comment, field-name collision risk, TOCTOU precedent, append-only contract), not speculative

**Research date:** 2026-08-04
**Valid until:** Stable — 60 days (no fast-moving external dependency; only invalidated by a Phase 56 code change to the files listed under Primary Sources)
