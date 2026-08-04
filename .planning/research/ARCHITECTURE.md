# Architecture Research: ITAM Lifecycle Integration

**Domain:** IT Asset Management (Snipe-IT-parity) extension onto an existing multi-tenant security/compliance CMDB
**Researched:** 2026-08-04
**Confidence:** HIGH (based on direct inspection of this codebase's actual code, not generic ITAM literature — every claim below is traceable to a file/line read during this research pass)

## Scope note

This is a subsequent-milestone integration study, not greenfield architecture research. The standard architecture (FastAPI + Motor/MongoDB + `TenantIsolatedCollection` + `router_registry.py` + React/TS skeleton) already exists and is not re-litigated. Everything below answers one question: **how does the v4.0 ITAM lifecycle — catalog, checkout/assignment, licenses/consumables, procurement/finance — attach to the existing `assets` model and platform skeleton**, and specifically how a hand-catalogued "manual" asset coexists with an agent-auto-discovered one.

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Frontend (React/TS) — components/itam/*  (new, mirrors components/nativeSecurity/*)│
├──────────────────────────────────────────────────────────────────────────────┤
│ AssetCatalogTab │ CheckoutTab │ LicensesTab │ ConsumablesTab │ FinanceTab      │
│  (mfr/model/     │ (assign/    │ (seats)     │ (qty ledger)   │ (warranty/    │
│   category/       │  return)    │             │                │  depreciation)│
│   location/       │             │             │                │               │
│   supplier)        │             │             │                │               │
└────────┬──────────┴──────┬──────┴──────┬──────┴───────┬────────┴──────┬───────┘
         │                 │             │              │               │
         ▼                 ▼             ▼              ▼               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Backend routers (FastAPI) — registered via router_registry.py               │
├──────────────────────────────────────────────────────────────────────────────┤
│ itam_catalog_endpoints │ asset_endpoints (EXTENDED, not forked) │             │
│ itam_checkout_endpoints │ itam_license_endpoints │ itam_consumable_endpoints  │
│ itam_finance_service (warranty/depreciation) │ itam_label_endpoints (QR)      │
└────────┬──────────┴──────┬──────┴──────┬──────┴───────┬────────┴──────┬───────┘
         │                 │             │              │               │
         ▼                 ▼             ▼              ▼               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  MongoDB (Motor) — every collection accessed ONLY via TenantIsolatedCollection│
│  except the warranty-expiry scheduler, which uses db._db + set_tenant_id     │
├──────────────────────────────────────────────────────────────────────────────┤
│ assets (EXTENDED)        │ manufacturers │ asset_models │ asset_categories    │
│ suppliers │ locations    │ asset_checkouts (append-only ledger)              │
│ licenses │ license_seats │ consumables │ consumable_checkouts (append-only)  │
│ notifications (reused — warranty-expiry alerts via notification_service)     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `assets` collection (extended) | Single source of truth for every physical/virtual thing — agent-discovered AND manually catalogued | Add ITAM fields as additive, all-optional top-level keys; discriminator `assetSource: "agent" \| "manual"` |
| Catalog collections (`manufacturers`, `asset_models`, `asset_categories`, `suppliers`, `locations`) | Normalized reference data assets point to by ID | Small top-level collections, tenant-isolated, simple CRUD routers, no cross-references between each other except `asset_models.manufacturerId`/`categoryId` |
| `asset_checkouts` | Immutable audit trail of every check-out/check-in event | Append-only inserts via raw `db._db`, mirrors `evidence_audit_log` pattern in `evidence_coc.py` |
| `assets.currentAssignment` (embedded) | Fast "who has this asset right now" lookup without joining the ledger | Denormalized sub-document updated on each checkout/check-in, source of truth is still the ledger |
| `licenses` / `license_seats` | Software license inventory + per-seat assignment | `licenses` = catalog record (name, total seats, cost, expiry); `license_seats` = one doc per seat, `assignedTo` nullable |
| `consumables` / `consumable_checkouts` | Quantity-tracked accessories/components (not individually serialized) | `consumables.qtyRemaining` decremented on checkout row insert |
| Warranty/depreciation | Financial lifecycle fields on the asset itself | Additive fields on `assets` (`purchase`, `warranty`, `depreciation` sub-documents); book value computed at read time, not stored mutable |
| `itam_label_endpoints` | QR/barcode asset-tag generation, offline | Reuses `qrcode[pil]` (already a backend dependency, used today for MFA enrollment) |
| Warranty-expiry scheduler | Cross-tenant background sweep flagging assets nearing warranty expiry | New coroutine in `app_background_tasks.py`, follows the `autonomous_remediation_loop`/`monitor_agent_status` pattern exactly: `db._db.tenants.find()` → `set_tenant_id(tid)` per tenant → query → `reset_tenant_id` |

## Recommended Project Structure

```
backend/
├── asset_endpoints.py              # EXTENDED — add POST/PATCH for manual assets;
│                                    #   existing GET/DELETE/link/bulk-update untouched
├── itam_catalog_endpoints.py       # NEW — manufacturers, asset_models, categories,
│                                    #   suppliers, locations (one router, 5 sets of
│                                    #   CRUD routes — these are structurally identical)
├── itam_catalog_service.py         # NEW — shared CRUD helper for the 5 catalog kinds
│                                    #   (avoids 5x copy-pasted create/list/delete)
├── itam_checkout_endpoints.py      # NEW — POST /api/assets/{id}/checkout,
│                                    #   POST /api/assets/{id}/checkin, GET history
├── itam_license_endpoints.py       # NEW — licenses + license_seats CRUD + assign/reclaim
├── itam_consumable_endpoints.py    # NEW — consumables CRUD + checkout ledger
├── itam_finance_service.py         # NEW — depreciation calculation (pure function,
│                                    #   no persistence of computed book value)
├── itam_label_endpoints.py         # NEW — QR/barcode generation for asset tags
├── itam_models.py                  # NEW — Pydantic models for ITAM-specific payloads
│                                    #   (deliberately separate from models.py::Asset —
│                                    #   see "Extend, Don't Fork" pattern below)
├── app_background_tasks.py         # EXTENDED — add warranty_expiry_loop()
└── router_registry.py              # EXTENDED — 6 new _load() calls, optional bucket

components/
└── itam/                           # NEW — mirrors components/nativeSecurity/*
    ├── AssetCatalogTab.tsx         # manufacturers/models/categories/suppliers/locations
    ├── CheckoutTab.tsx             # assign/return UI, current-assignment view
    ├── LicensesTab.tsx             # seats table, assign/reclaim
    ├── ConsumablesTab.tsx          # qty ledger, checkout modal
    ├── FinanceTab.tsx              # warranty countdown, depreciation/book-value display
    └── AssetLabelPrintout.tsx      # QR/barcode render + print view

components/
└── ITAMDashboard.tsx               # NEW top-level page — lazy-loaded in App.tsx,
                                     #   composes the itam/* tabs, same shape as
                                     #   NativeSecurityConsole.tsx
```

### Structure Rationale

- **`itam_*_endpoints.py` as separate files, not folded into `asset_endpoints.py`:** `asset_endpoints.py` is 500 lines already (the codebase's own 500-line guideline). ITAM adds roughly 5 new functional surfaces (catalog, checkout, license, consumable, finance/label) — each gets its own router file and its own `_load()` line in `router_registry.py`, consistent with how `compliance_remediation_endpoints`, `compliance_remediation_sla_endpoints`, and `compliance_evidence_lifecycle_endpoints` were split out from a single "compliance" surface rather than crammed into one file.
- **`itam_models.py` separate from `models.py::Asset`:** `models.py::Asset` (lines 70-96) declares `hostname`, `osName`, `osVersion`, `kernel`, `ipAddress`, `macAddress`, `cpuModel`, `ram`, `serialNumber`, `lastScanned`, `patchStatus` as **required, non-Optional** fields. That model is correct for the agent-telemetry shape and must not be loosened (it would silently make hardware inventory optional for every consumer that already relies on it). ITAM request/response models need a leaner shape where only `name`/`assetTag`/`categoryId` are required and everything else (purchase info, warranty, checkout state, custom fields) is optional. Keep them as sibling models, not a subclass — a manual asset document in Mongo simply won't populate the agent-only fields, and `itam_models.py` validates only the fields it owns.
- **`components/itam/` mirrors `components/nativeSecurity/`:** that is the most recent precedent in this codebase for "console with tabs behind a `manage:*` gate" (Phase 54, `NativeSecurityConsole.tsx` + `components/nativeSecurity/{AuditTab,FindingsTab,PlaybooksTab,RemediationQueueTab}.tsx`). Reuse the same shape rather than inventing a new one.

## Architectural Patterns

### Pattern 1: Extend the `assets` collection via a discriminator, never fork it

**What:** Every asset — agent-discovered or hand-catalogued — lives in the single `assets` collection. Add a top-level `assetSource: "agent" | "manual"` field (default `"agent"` for backward compatibility with the ~all-existing documents that predate this milestone). ITAM fields (`assetTag`, `statusLabel`, `manufacturerId`, `modelId`, `categoryId`, `supplierId`, `locationId`, `purchase`, `warranty`, `depreciation`, `customFields`, `currentAssignment`) are additive optional fields present on *every* asset document regardless of source — so an agent-discovered laptop can also be ITAM-managed (checked out to a person, tracked for warranty) without becoming a separate record. This is the single highest-risk decision in this milestone and this is the recommended resolution: **one CMDB, two ingestion paths, shared lifecycle fields.**

**When to use:** Any time a new feature needs to attach data to an entity that already exists under agent ownership. The `assets` collection already has precedent for optional/best-effort fields (`ramDetails`, `securityFeatures`, `disks` are all `| None` or default-empty in `models.py`).

**Why not a separate `manual_assets` collection:** Snipe-IT's own data model doesn't distinguish "how the asset was created," and neither should this one — reporting, search, bulk-update, and criticality gating (`PATCH /{asset_id}/criticality`, already used by the autonomous-remediation confidence gate) all currently assume `assets` is the single source of truth. Forking would require every existing consumer of `db.assets` (compliance evidence processor, vulnerability findings, remediation playbooks, agent linking) to be taught about a second collection, and would make "show me every asset with an open CVE AND an expiring warranty" require an application-level join instead of one query.

**ID scheme:** Agent-discovered assets are keyed `asset-{hostname}` (see `agent_registry_endpoints.py:120`, `agent_heartbeat_endpoints.py:208`). Manual assets have no hostname, so they need a different key — there is already a precedent for this exact case in `seed_vulns_for_super.py:60`: `f"asset-{uuid.uuid4().hex[:8]}"`. Use that scheme for every asset created through the new `POST /api/assets` endpoint.

**Critical gap this milestone must close:** `asset_endpoints.py` currently has **no `POST /api/assets` endpoint at all** — line 349's own comment says so ("Add other asset endpoints here if needed (GET, POST, etc. are currently distributed or missing specific router)"). Every existing asset document is created either by the heartbeat/registry upsert path (`agent_registry_endpoints.py:156`, keyed by hostname) or by one-off scripts. This means manual-asset creation is not a variant of an existing endpoint — it is a wholly new capability, and is the natural Phase-1 building block for this milestone.

**Example (illustrative, matches this codebase's style):**
```python
# itam_models.py
class ManualAssetCreate(BaseModel):
    name: str
    categoryId: str
    assetTag: Optional[str] = None          # auto-generated if omitted
    manufacturerId: Optional[str] = None
    modelId: Optional[str] = None
    supplierId: Optional[str] = None
    locationId: Optional[str] = None
    serialNumber: Optional[str] = None
    purchase: Optional[PurchaseInfo] = None  # cost, date, PO number
    warranty: Optional[WarrantyInfo] = None  # months, expiresAt
    customFields: Dict[str, Any] = {}

# asset_endpoints.py — new endpoint, existing model untouched
@router.post("")
async def create_manual_asset(
    payload: ManualAssetCreate,
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    doc = {
        "id": asset_id,
        "assetSource": "manual",
        "statusLabel": "deployable",
        **payload.model_dump(exclude_none=True),
        "createdAt": _now_iso(), "updatedAt": _now_iso(),
    }
    await db.assets.insert_one(doc)   # TenantIsolatedCollection injects tenantId
    return doc
```

### Pattern 2: Append-only ledger for checkout/checkin, denormalized "current state" on the parent

**What:** Every checkout/checkin/reclaim event writes an immutable row to a ledger collection (`asset_checkouts`, `consumable_checkouts`), using the exact `_append_coc_entry` pattern already proven in `evidence_coc.py` (raw `db._db`, fire-and-forget, swallow-and-log on failure, called **after** the primary mutation succeeds). The parent record (`assets.currentAssignment`, `consumables.qtyRemaining`) is separately updated in the same request so reads that only need "who has it now" don't have to scan the ledger.

**When to use:** Any checkout/checkin, license-seat assign/reclaim, or consumable-quantity change. This is the direct ITAM analog of `evidence_audit_log` and `remediation_escalations` — the codebase already has a strong, tested convention for "mutate current state + append immutable history," and ITAM assignment history is exactly that shape.

**Trade-offs:** Two writes per action instead of one. Accepted — the alternative (embedding a growing `checkoutHistory: []` array directly on the asset document) has a known failure mode in this codebase's own MongoDB usage: unbounded array growth on a document that's also read on every dashboard list view (`GET /api/assets` is cached at `ttl=60` and returns full documents). A frequently-reassigned asset (shared laptop pool, loaner equipment) would otherwise bloat the hot list-read path.

**Example:**
```python
# itam_checkout_service.py
async def _append_checkout_entry(db, asset_id, tenant_id, actor, action, person_id, location_id):
    raw = db._db if hasattr(db, "_db") else db
    await raw.asset_checkouts.insert_one({
        "assetId": asset_id, "tenantId": tenant_id, "actor": actor,
        "action": action,          # "checkout" | "checkin"
        "assignedTo": person_id, "locationId": location_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
```

### Pattern 3: Normalized catalog collections, referenced by ID — not embedded strings

**What:** `manufacturers`, `asset_models`, `asset_categories`, `suppliers`, `locations` are each their own top-level, tenant-isolated collection with `id`/`name` and light metadata (`asset_models` additionally has `manufacturerId`, `categoryId`). Assets store the *ID*, not a copied-in name string.

**When to use:** Always, for this cluster. Snipe-IT's own value proposition is catalog consistency (fixing a manufacturer typo once, everywhere) — that requires normalization. This also matches the codebase's existing pattern for `compliance_frameworks` and `roles`: small reference collections looked up by ID, not duplicated inline.

**Trade-offs:** List views (e.g. "show manufacturer name in the asset table") need either a lookup join at read time or a lightweight cache. Given `cache_service.cached()` is already used throughout this codebase (`asset_endpoints.py` itself caches `GET /api/assets` and `GET /api/assets/search`), the recommended approach is: cache the 5 catalog collections client-side (they change rarely) and resolve IDs → names in the frontend, avoiding a fan-out join on every asset list request.

### Pattern 4: Warranty-expiry alerting as a background scheduler, using the raw-db cross-tenant pattern correctly

**What:** A new coroutine (`warranty_expiry_loop`) added to `app_background_tasks.py`, structured identically to the existing `autonomous_remediation_loop` (lines 14-36) and `monitor_agent_status` (lines 39+): iterate all tenants via `db._db.tenants.find({}, {"id": 1})`, call `set_tenant_id(tid)` before each tenant's work, run the tenant-scoped query, `reset_tenant_id()` in a `finally`. Findings feed into the existing `notification_service.send_notification(db, tenant_id, event_type, payload)` (already used by `ticket_notifications.py` and `notification_endpoints.py`) rather than inventing a new alert-delivery path.

**This is the explicit flag requested by the milestone brief:** the `TenantIsolatedCollection` fail-closed design (`database.py:24-34`) means any *tenant-scoped* collection accessed without a preceding `set_tenant_id()` gets silently redirected to a `NON_EXISTENT_TENANT_ISOLATION_EMERGENCY`/`ORPHANED_DATA_NO_TENANT_CONTEXT` sentinel — a background job that queries `db.assets.find({"warranty.expiresAt": {"$lt": threshold}})` for *all* tenants at once, without the per-tenant `set_tenant_id` loop, will either see zero results (if using the wrapped `db`) or silently leak cross-tenant data (if using `db._db` without re-scoping per tenant). This exact bug class has recurred across multiple past milestones per the project brief — the correct pattern is fully worked out already in `app_background_tasks.py` and must be copied, not reinvented.

**When to use:** Any new scheduler, plus the depreciation/warranty sweep this milestone needs specifically.

### Pattern 5: Compute derived financials at read time, don't persist a mutable "current book value"

**What:** `depreciation` is stored as an *inputs* sub-document on the asset (`{method: "straight_line", purchaseCost, salvageValue, usefulLifeMonths, purchaseDate}`). Current book value is a pure function of those inputs plus "now," computed in `itam_finance_service.py` and returned in API responses — never written back to the document on a schedule.

**When to use:** Depreciation, warranty "days remaining," and any other time-derived ITAM field.

**Trade-offs:** Slightly more CPU per read (negligible — it's arithmetic) versus the alternative of a nightly job that rewrites `currentBookValue` on every asset. The stored-mutable-value approach is rejected because (a) it needs its own scheduler with the same cross-tenant risk as Pattern 4, (b) it drifts if the job doesn't run for a period, and (c) nothing in this milestone's scope needs to *query* or *sort* by book value at a scale where computing it in Mongo aggregation would matter — asset counts per tenant are in the hundreds-to-low-thousands range based on the existing `page_size <= 100` pagination cap already in use.

## Data Flow

### Manual asset creation flow

```
Admin fills "Add Asset" form (name, category, manufacturer, model, cost, warranty)
    ↓
POST /api/assets  (NEW endpoint)
    ↓
itam_models.ManualAssetCreate validated
    ↓
asset_id = f"asset-{uuid4().hex[:8]}"; assetSource="manual"; statusLabel="deployable"
    ↓
db.assets.insert_one(doc)   [TenantIsolatedCollection auto-injects tenantId]
    ↓
invalidate_cache("assets:*")   [existing convention, see delete_asset/bulk_update]
    ↓
Response includes generated assetTag → frontend offers "Print QR label" (itam_label_endpoints)
```

### Check-out flow

```
Admin selects asset + person/location on CheckoutTab.tsx
    ↓
POST /api/assets/{id}/checkout  {personId, locationId?, expectedReturnAt?}
    ↓
itam_checkout_endpoints: validate asset exists (tenant-scoped read),
  validate asset.statusLabel == "deployable" (reject if already deployed/archived/retired)
    ↓
db.assets.update_one({id}, {"$set": {
    "statusLabel": "deployed",
    "currentAssignment": {"personId": ..., "checkedOutAt": ..., "locationId": ...}
}})
    ↓
_append_checkout_entry(db, asset_id, tenant_id, actor, "checkout", personId, locationId)
  [fire-and-forget, raw db._db, AFTER the primary mutation — same ordering rule as
   evidence_coc.py's documented WR-03 lesson]
    ↓
invalidate_cache("assets:*")
    ↓
WebSocket/notification (optional, reuse broadcast pattern from remediation workflow)
```

### Check-in flow

Mirror of check-out: `POST /api/assets/{id}/checkin` clears `currentAssignment`, sets `statusLabel` back to `deployable` (or `broken`/`maintenance` if the admin flags a condition issue), appends a `"checkin"` ledger row.

### License seat assignment flow

```
licenses collection: catalog record (name, manufacturerId, totalSeats, purchaseCost, expiresAt)
    ↓
On license creation: N license_seats docs pre-created ({licenseId, seatIndex, assignedTo: null})
    ↓
POST /api/licenses/{id}/seats/{seatId}/assign  {personId | assetId}
    ↓
db.license_seats.update_one({id: seatId, assignedTo: None}, {"$set": {"assignedTo": ...}})
  [conditional filter on assignedTo: None prevents double-assigning the same seat —
   this is the concurrency-safety mechanism, not an application-level lock]
    ↓
reclaim = same endpoint pattern, $set assignedTo back to null
```

### Consumable checkout flow

```
POST /api/consumables/{id}/checkout  {personId, quantity}
    ↓
db.consumables.update_one(
    {id, qtyRemaining: {"$gte": quantity}},   # atomic guard against overdraw
    {"$inc": {"qtyRemaining": -quantity}}
)
    ↓
if matched_count == 0: raise 409 Conflict "insufficient quantity"
    ↓
consumable_checkouts.insert_one({consumableId, personId, quantity, timestamp})
```

### Warranty-expiry alert flow

```
warranty_expiry_loop() [new, in app_background_tasks.py]
    ↓ every N hours
db._db.tenants.find({}, {"id": 1})
    ↓ for each tenant:
set_tenant_id(tid)
db.assets.find({"warranty.expiresAt": {"$lte": now + 30d}, "warranty.alerted": {"$ne": true}})
    ↓
notification_service.send_notification(db, tid, "warranty_expiring", {assetId, expiresAt, ...})
db.assets.update_one({id}, {"$set": {"warranty.alerted": True}})
    ↓
reset_tenant_id()
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Per-tenant asset count in the hundreds (typical MSP client) | Everything above works as-is; no index changes needed beyond what already exists on `assets.tenantId`/`assets.id` |
| Per-tenant asset count in the thousands+ (large enterprise tenant) | Add compound indexes: `assets` on `(tenantId, statusLabel)` and `(tenantId, warranty.expiresAt)`; `asset_checkouts` on `(tenantId, assetId, timestamp)` for history pagination |
| High checkout churn (shared equipment pools, hundreds of checkouts/day per tenant) | `asset_checkouts` ledger is append-only and grows unboundedly by design — this is correct (it's an audit trail, same as `evidence_audit_log`), but plan for a retention/archival policy consistent with whatever the platform already does for `evidence_audit_log` at scale (not addressed by existing code — flag as an open question, not a blocker for this milestone) |
| Large license seat counts (e.g. a 5,000-seat M365 license) | Use the separate `license_seats` collection (Pattern 3), not an embedded array — an embedded array of 5,000 seat sub-documents on one `licenses` doc would blow past MongoDB's practical per-document performance envelope well before the 16MB hard limit |

### Scaling Priorities

1. **First bottleneck:** `GET /api/assets` list view growing slower as ITAM fields are added to every document — mitigated by the existing `projection={"_id": 0}` + `cached(ttl=60)` pattern already in place; no new work needed unless catalog-name resolution is naively joined per-row (avoid this, resolve IDs client-side per Pattern 3).
2. **Second bottleneck:** the warranty-expiry scheduler's per-tenant loop scanning every tenant every cycle — acceptable at current tenant counts (background jobs already do this exact `db._db.tenants.find()` fan-out for autonomous remediation and compliance scoring); revisit only if tenant count grows by an order of magnitude.

## Anti-Patterns

### Anti-Pattern 1: Forking `assets` into a parallel `manual_assets`/`itam_assets` collection

**What people do:** Create a separate collection for hand-catalogued assets because the existing `Asset` Pydantic model has required hardware fields that don't fit.
**Why it's wrong:** Every existing cross-cutting feature (vulnerability findings, remediation playbook targeting, criticality gating, compliance evidence linkage, agent linking) queries `db.assets` as the single CMDB. A second collection means every one of those features needs to learn about it, or ITAM assets silently don't participate in security/compliance workflows the milestone brief implies should still apply ("turning the security-monitoring asset inventory into a true ITAM system" — singular system, not two).
**Do this instead:** Extend the collection with additive optional fields and an `assetSource` discriminator (Pattern 1); add a separate, leaner Pydantic model (`itam_models.py`) for the request/response shape rather than loosening `models.py::Asset`.

### Anti-Pattern 2: Querying tenant-scoped ITAM collections without `set_tenant_id` in the new warranty/depreciation scheduler

**What people do:** Write a new background loop that calls `db.assets.find(...)` (via the wrapped `TenantIsolatedCollection`) once for all tenants, or worse, calls `db._db.assets.find(...)` once for all tenants and forgets the tenant filter entirely.
**Why it's wrong:** This is the recurring bug class explicitly flagged in the milestone brief. The fail-closed `TenantIsolatedCollection` (first case) returns nothing useful (silently broken feature — no warranty alerts ever fire). The raw-`db._db` case (second case) is worse: it can return every tenant's assets in one unscoped query, a cross-tenant data leak if that data is then included in an alert payload or log line without per-document tenant filtering.
**Do this instead:** Copy the exact pattern already proven in `app_background_tasks.py`'s `autonomous_remediation_loop`/`monitor_agent_status`: iterate `db._db.tenants.find()`, `set_tenant_id(tid)` before each tenant's work, use the wrapped `db` (or re-fetch `get_database()`) inside the per-tenant block, `reset_tenant_id()` in a `finally`.

### Anti-Pattern 3: Embedding unbounded history arrays on the asset document

**What people do:** Add `assets.checkoutHistory: []` and `$push` a new entry on every checkout/checkin, instead of a separate ledger collection.
**Why it's wrong:** `GET /api/assets` (list view) returns full documents and is on a 60-second cache — a frequently-reassigned asset's document grows without bound and that growth is paid on every list-view cache-miss read, not just when viewing that asset's history.
**Do this instead:** Append-only ledger collection (Pattern 2) + a small denormalized `currentAssignment` sub-document for fast "who has it now" reads.

### Anti-Pattern 4: Storing computed depreciation/book-value as a field that's mutated by a scheduled job

**What people do:** A nightly job recalculates `assets.currentBookValue` for every asset and writes it back.
**Why it's wrong:** Needs its own cross-tenant scheduler (another instance of Anti-Pattern 2's risk surface), and the value is stale between runs — showing a wrong number is worse than computing it live for a value that's pure arithmetic.
**Do this instead:** Pattern 5 — store the depreciation *inputs*, compute book value in the response serializer at read time.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| None required | ITAM lifecycle is entirely internal (catalog + assignment + finance tracking) | Milestone brief explicitly scopes out RFID hardware integration; QR/barcode generation uses the already-vendored `qrcode[pil]` (currently used for MFA enrollment in this codebase), no external service call — satisfies the offline-first/air-gapped constraint |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `assets` ↔ catalog collections (`manufacturers`/`asset_models`/`asset_categories`/`suppliers`/`locations`) | Direct Mongo reference by `id` string field, resolved client-side | New foreign keys: `assets.manufacturerId`, `assets.modelId`, `assets.categoryId`, `assets.supplierId`, `assets.locationId` — all optional, all validated as "exists" at write time in `itam_catalog_service.py`, not enforced by a Mongo-level FK (this codebase has none) |
| `assets` ↔ `asset_checkouts` | Denormalized current-state field + append-only ledger insert, same request | See Pattern 2; matches `evidence_coc.py`'s relationship between the primary evidence mutation and `evidence_audit_log` |
| `licenses` ↔ `license_seats` | 1-to-N, `license_seats.licenseId` FK | Seats pre-created at license-creation time (Snipe-IT's own model: seat count is fixed at purchase, not elastic) |
| `consumables` ↔ `consumable_checkouts` | Atomic `$inc`-guarded quantity decrement + ledger insert | See "Consumable checkout flow" above — the `$gte` guard in the update filter is the concurrency-safety mechanism |
| ITAM background scheduler ↔ `notification_service` | Function call, `send_notification(db, tenant_id, event_type, payload)` | Reuses existing delivery/channel infrastructure (`notification_endpoints.py`, `ticket_notifications.py` precedent) instead of building new alert plumbing |
| Frontend `ITAMDashboard.tsx` ↔ `App.tsx`/`Sidebar.tsx` | New `AppView` union member (e.g. `'itam'`), new `case` in `App.tsx`'s view switch, new `Sidebar.tsx` nav entry, new `manage:itam` permission key added to `rbac_utils.py`'s `Permission` enum and the `admin`/`Tenant Admin` `DEFAULT_PERMISSIONS` lists | Exact precedent: `App.tsx:370-371` (`geoSecurity: 'manage:settings'`, `fleetObservability: 'manage:agents'`) + `Sidebar.tsx:416-417`. A dedicated `manage:itam` permission (rather than reusing `manage:agents` or `view:assets`) is recommended because ITAM write actions (checkout, license reclaim, financial data) are a distinct authorization boundary from "can see the security asset inventory" |

## Suggested Build Order

Dependencies flow strictly downward — catalog before assets-reference-catalog, assets before things-that-target-assets:

1. **Catalog collections + CRUD** (`manufacturers`, `asset_models`, `asset_categories`, `suppliers`, `locations`) — no dependencies on anything else in this milestone; `asset_models` depends on `manufacturers`/`asset_categories` existing first (self-contained sub-order).
2. **Manual asset creation** (`POST /api/assets`, `itam_models.py`, `assetSource` discriminator, `statusLabel` field on the extended `assets` model) — depends on (1) for the optional catalog-ID fields to validate against, but can ship with catalog IDs unvalidated/nullable if sequenced in parallel.
3. **Asset tag / QR-barcode generation** (`itam_label_endpoints.py`) — depends on (2) for `assetTag` to exist on the document.
4. **Check-out/check-in + `asset_checkouts` ledger** — depends on (2); assets must exist and have a `statusLabel` lifecycle before they can be checked out.
5. **Licenses + `license_seats`** — independent of (1)-(4) except reusing the same tenant-isolation and RBAC scaffolding; can be built in parallel with (3)/(4).
6. **Consumables + `consumable_checkouts`** — same independence as (5); can parallelize.
7. **Warranty + depreciation fields + finance service** — depends on (2) (needs `purchase`/`warranty` fields on the asset shape decided).
8. **Warranty-expiry background scheduler** — depends on (7) for the fields to scan, and must follow the `app_background_tasks.py` cross-tenant pattern (Pattern 4) exactly.
9. **Frontend `ITAMDashboard.tsx` + `components/itam/*` tabs + `AppView`/`Sidebar`/`manage:itam` permission wiring** — can start in parallel with backend work once endpoint contracts for (2)-(7) are stable enough to mock, but final integration depends on all backend phases landing.

This ordering also maps cleanly onto the milestone brief's four clusters: **Cluster C (catalog)** is step 1, **Cluster A (lifecycle/checkout)** is steps 2-4, **Cluster D (licenses/consumables)** is steps 5-6, **Cluster B (procurement/finance)** is steps 7-8, and frontend (step 9) threads through all of them — meaning Cluster C should be the first phase in the roadmap regardless of how the other three are ordered relative to each other.

## Sources

- Direct code inspection (HIGH confidence — every claim traceable to a specific file/line read during this research pass):
  - `backend/asset_endpoints.py` (existing asset router, no POST endpoint, RBAC pattern, cache invalidation convention)
  - `backend/models.py:70-96` (`Asset` Pydantic model, required hardware fields)
  - `backend/database.py:13-136` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`, fail-closed tenant injection)
  - `backend/evidence_coc.py` (append-only audit-trail pattern, `_append_coc_entry`)
  - `backend/app_background_tasks.py:1-60` (`autonomous_remediation_loop`, `monitor_agent_status` — the correct cross-tenant scheduler pattern, and the documented `db._db` usage note at line 234)
  - `backend/router_registry.py` (router registration conventions, required-vs-optional router lists)
  - `backend/rbac_utils.py:40-140` (`Permission` enum, `DEFAULT_PERMISSIONS` role tables)
  - `backend/notification_service.py:509` (`send_notification` reusable alert-delivery hook)
  - `backend/pagination_utils.py`, `backend/cache_service.py` (existing pagination/caching conventions reused as-is)
  - `App.tsx:165-166, 370-371, 1918-1919`, `components/Sidebar.tsx:416-417` (Phase 47/48 admin-gated nav page precedent — `SecuritySettingsDashboard`/`FleetObservabilityDashboard`)
  - `backend/requirements.txt:24-25` (`qrcode[pil]` already vendored)
  - `backend/agent_registry_endpoints.py:120,156`, `backend/agent_heartbeat_endpoints.py:208`, `backend/seed_vulns_for_super.py:60` (asset ID generation schemes — hostname-keyed vs uuid-keyed precedent)
  - `.planning/PROJECT.md` (milestone scope, constraints, out-of-scope boundaries)

---
*Architecture research for: ITAM lifecycle integration onto Enterprise OmniAgent's existing multi-tenant security/compliance CMDB*
*Researched: 2026-08-04*
