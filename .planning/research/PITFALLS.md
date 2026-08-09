# Pitfalls Research — v4.0 ITAM Asset Lifecycle

**Domain:** Adding a full ITAM lifecycle (procurement/checkout/licenses/depreciation/manual-asset-entry) to an existing agent-centric security CMDB
**Researched:** 2026-08-04
**Confidence:** HIGH (majority of findings are primary-source reads of this exact codebase; a small number of generic-domain findings are marked LOW and clearly flagged)

**Method note:** Verified against `backend/tenant_context.py`, `backend/tenant_middleware.py`, `backend/database.py` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`), `backend/compliance_remediation_sla_service.py`, `backend/app_startup.py`, `backend/asset_endpoints.py`, `backend/agent_heartbeat_endpoints.py`, `backend/tickets_models.py`/`tickets_service.py`/`tickets_config_mixin.py`, `backend/requirements.txt`, and `.planning/PROJECT.md`. This milestone's `PITFALLS.md` replaces the prior milestone's (v3.3 fleet-observability) file, which already documented the same recurring background-scheduler tenant-isolation bug for a different feature — that finding is re-verified and re-applied to ITAM below, since the milestone context flags it as a bug class that has recurred across several past milestones in this exact codebase.

## Critical Pitfalls

### Pitfall 1: Background ITAM schedulers bypass (or silently break under) tenant isolation

**What goes wrong:**
A new warranty-expiry alert sweep, depreciation-recompute job, or license-expiry sweep is written the "obvious" way: `db = get_database()` then loop/query. Two failure modes result, and both are silent:
1. If the job calls the wrapped `get_database()` (which returns `TenantIsolatedDatabase`) from a background task, `get_tenant_id()` returns `None` because no HTTP request set it — `TenantIsolatedCollection._inject_tenant_id()` fails closed, forcing every filter to `tenantId: "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` (reads) or `"ORPHANED_DATA_NO_TENANT_CONTEXT"` (writes). The job runs, logs nothing alarming, and simply never finds/updates anything for any tenant, forever.
2. If a developer "fixes" that by looping over tenants and calling `set_tenant_id()` per iteration, but doesn't wrap the reset in a `finally` (per the existing `SEC-03` warning in `tenant_context.py`), an exception mid-iteration leaves a stale tenant_id on the asyncio Task, and the next iteration's write can land on the wrong tenant.

**Why it happens:**
`TenantMiddleware` (`backend/tenant_middleware.py`) only ever calls `set_tenant_id()` inside the HTTP request/response cycle, from the JWT's `tenant_id` claim. Scheduled/background code (APScheduler jobs, `asyncio.create_task` loops started at app startup) never passes through that middleware, so the ContextVar is simply never populated there. This exact bug class has recurred multiple times in this codebase already — it is explicitly called out as an anti-pattern in `backend/compliance_remediation_sla_service.py`'s module docstring, and the same pattern was independently re-discovered and documented for the prior (v3.3) milestone's fleet-observability sweeps.

**How to avoid:**
Follow the established, already-proven pattern in `backend/compliance_remediation_sla_service.py` exactly:
- The service module never resolves its own database handle (no `get_database()` call inside the module).
- Its background-sweep entry point (`run_sla_pass(db)`) is always called with the **raw** Motor handle, wired at startup in `backend/app_startup.py`: `asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))` (note `_mdb.db`, not `get_database()`).
- Inside the sweep, the query is **intentionally unscoped** (queries across all tenants, on purpose — cross-tenant aggregation), but every document's `tenantId` is extracted from the document itself and threaded explicitly through every subsequent write/notification call — never relied on as ambient context.
- Any new ITAM scheduler (warranty-expiry alerts, depreciation recompute, license-seat-expiry sweep) must be written the same way: accept `db` as a parameter, document in the module docstring that it must receive the raw handle, and wire it in `app_startup.py` passing `_mdb.db`.

**Warning signs:**
- A new scheduler module has `from database import get_database` at the top, or calls `get_database()` internally.
- A new scheduler's sweep silently processes 0 documents across all tenants in staging/QA even though tenant data exists (this is the tell-tale symptom of failure mode 1 — it "looks fine," no errors, just does nothing).
- Code review sees `set_tenant_id()` called inside a `for tenant in tenants:` loop without a matching `reset_tenant_id()` in a `finally` block.
- `logging.error("[SECURITY ALERT] DB Access without tenant context...")` (`database.py`) firing repeatedly at the sweep's cadence — but note this only fires on `insert_one`/`insert_many`, not on read-only `find`/`count_documents`/`aggregate`, so a silent read-only sweep won't even log the alert.

**Phase to address:**
Procurement/finance phase (warranty-expiry, depreciation recompute schedulers) and licenses/consumables phase (seat-expiry alerts) — but the *pattern* should be established/documented once in the catalog/foundation phase so later phases just copy it.

---

### Pitfall 2: Forking a parallel `itam_assets` collection/model instead of extending `assets`

**What goes wrong:**
ITAM fields (assigned-to, checked-out-to, PO number, purchase cost, warranty expiry, depreciation schedule, custom fields, license/seat references) get modeled as a new collection (e.g. `itam_assets`) that references or duplicates the agent-discovered `assets` collection, because it's easier to design a clean ITAM schema from scratch than to extend the existing one. This creates two sources of truth for the same physical machine, and every existing asset-aware surface — `global_search_endpoints.py`, `skill_handlers_queries.py`, dashboards, bulk operations, criticality/status gating — only knows about `assets` and silently misses ITAM data (or worse, shows stale/conflicting data from both).

**Why it happens:**
The existing `assets` collection/`asset_endpoints.py` is agent-centric: fields like `hostname`, `osName`, `serialNumber`, `currentMetrics` assume an agent reported them. It's tempting to treat "hand-catalogued Snipe-IT-style asset" as a fundamentally different entity from "agent-discovered endpoint" and give it its own model. The milestone context (`PROJECT.md`) explicitly flags this as the risk to avoid: "reuse the existing `assets` model / `asset_endpoints.py` where sensible — don't fork it."

**How to avoid:**
Extend the same `assets` document shape with new optional ITAM fields (owner/assignedTo, checkoutHistory reference, poNumber, purchaseCost, purchaseDate, warrantyExpiry, depreciation*, customFields, tagId, category/model/manufacturer/location/supplier refs). Add a `source: "agent" | "manual"` discriminator (see Pitfall 8) rather than a separate collection. Extend existing allowlists/projections (e.g. `_BULK_UPDATE_ALLOWLIST` in `asset_endpoints.py`) to include the new editable fields instead of building parallel bulk-update endpoints. New ITAM-only reference data (manufacturers, models, categories, suppliers, locations — genuinely new catalog concepts with no existing analog) *should* get their own collections; the asset **document itself** should not be forked.

**Warning signs:**
- A new collection name like `itam_assets`, `physical_assets`, or `catalog_assets` appears in a PR that also touches `asset_endpoints.py`.
- Asset search/detail/list endpoints need to query two collections and merge results client-side.
- The existing `assets` unique index on `id` (`backend/database.py`) isn't reused for the new ITAM records.

**Phase to address:**
Catalog/foundation phase — this is the first phase that touches the assets schema and sets the precedent every later phase follows.

---

### Pitfall 3: Reusing the `status` field name for ITAM lifecycle labels

**What goes wrong:**
ITAM needs a status-lifecycle enum (deployable/deployed/archived/retired/disposed/broken). The existing `assets` document already has a `status` field with a *different* meaning: the agent heartbeat handler (`backend/agent_heartbeat_endpoints.py`) sets `"status": "active"` via `$setOnInsert` at asset creation (agent-liveness/registration semantics), `_BULK_UPDATE_ALLOWLIST` in `asset_endpoints.py` already treats `status` as a generic bulk-editable field, and `global_search_endpoints.py` / `skill_handlers_queries.py` project and read `status` expecting the existing agent-oriented value space. If ITAM repurposes the same key for the deployable/deployed/archived/retired/disposed/broken vocabulary, every existing consumer that assumes the old value space silently breaks or shows nonsense (e.g. search results showing "retired" where code expected "active"/"inactive").

**Why it happens:**
"Status" is the obvious field name for a status-lifecycle feature, and it's easy to miss that the field is already load-bearing elsewhere in a codebase this size without grepping first.

**How to avoid:**
Use a distinctly named field for the ITAM lifecycle label — e.g. `lifecycleStatus` or `assetStatus` — and leave the existing `status` field's agent-liveness semantics untouched. Before introducing any new field on the shared `assets` document, grep the codebase for the proposed key name (`grep -rn '"status"' backend --include="*.py"`) to catch collisions like this one.

**Warning signs:**
- A PR sets `asset["status"] = "retired"` or similar anywhere in new ITAM code.
- Existing tests around agent heartbeat / online status start failing after an ITAM change with no obvious relation.

**Phase to address:**
Catalog/foundation phase (this is where the lifecycle-status field is first introduced).

---

### Pitfall 4: Non-atomic "find max, add 1" sequential ID generation for asset tags / PO numbers

**What goes wrong:**
Human-readable sequential identifiers (asset tag `IT-0042`, PO number `PO-2026-0007`) are generated by querying the current max and incrementing in application code. Under concurrent creation — two techs adding assets in different browser tabs, or a bulk CSV import racing a manual add — two requests read the same "current max" before either writes, producing duplicate tags/PO numbers.

**Why it happens:**
This codebase currently has **no existing precedent** for atomic sequence generation anywhere in `backend/` (a full-repo grep for `find_one_and_update` combined with `$inc`-based counters returns nothing) — unlike, say, tenant isolation or SLA sweeps, there's no established pattern to copy, so it's easy to reach for the naive read-then-write approach that works fine in manual testing and fails only under concurrency.

**How to avoid:**
Introduce a dedicated tenant-scoped `counters` collection and generate the next value with a single atomic Motor call:
```python
doc = await raw_db.counters.find_one_and_update(
    {"tenantId": tenant_id, "name": "asset_tag"},
    {"$inc": {"seq": 1}},
    upsert=True,
    return_document=ReturnDocument.AFTER,
)
tag = f"IT-{doc['seq']:04d}"
```
Back this with a unique index on the generated tag scoped per tenant (`{tenantId, assetTag}` unique) so any bypass of the counter fails loudly (a 500/duplicate-key error) instead of silently creating a collision.

**Warning signs:**
- Tag/PO-number generation code does a `find(...).sort(...).limit(1)` (or equivalent "get the last one") followed by a separate `insert_one`/`update_one` in a different statement.
- No unique index exists on the generated identifier field.

**Phase to address:**
Catalog/foundation phase (asset tags) and procurement/finance phase (PO numbers) — verify with a concurrent-creation test (fire N create-asset requests in parallel, assert N distinct tags).

---

### Pitfall 5: Checkout/check-in and license-seat/consumable-quantity race conditions

**What goes wrong:**
Checking out an asset to a person, or decrementing available license seats / consumable quantity, is implemented as read-check-then-write (`find_one` to check `available > 0`, then a separate `update_one` to decrement). Two concurrent checkout requests for the same single-unit asset, or the last available seat/unit of a consumable, can both pass the check before either write lands — resulting in double-assignment of one physical laptop, or `available` quantity going negative.

**Why it happens:**
This codebase has no existing "reserve a limited quantity of X" workflow to copy from — ticket assignment (`tickets_service.py`) assigns to a person but isn't quantity-limited, so there's no established pattern here either, and the two-step check-then-write is the natural first implementation.

**How to avoid:**
Embed the availability condition directly in the update filter so the check-and-decrement is a single atomic operation, matching MongoDB's standard prevention pattern for this exact class of bug:
```python
result = await raw_db.assets.find_one_and_update(
    {"id": asset_id, "tenantId": tenant_id, "lifecycleStatus": "deployable"},
    {"$set": {"lifecycleStatus": "deployed", "assignedTo": user_id, "checkedOutAt": now}},
    return_document=ReturnDocument.AFTER,
)
if result is None:
    raise HTTPException(409, "Asset is not available for checkout")
```
For quantity-based consumables/licenses, the same shape with `{"available": {"$gt": 0}}` in the filter and `{"$inc": {"available": -1}}` in the update. Check-in (return) should be the mirror `$inc: +1`, guarded so it can never push `available` above `totalQuantity`.

**Warning signs:**
- Checkout logic has a `find_one` followed by a separate `update_one`/`update` call with no shared filter condition.
- No 409/"unavailable" response path exists for a checkout attempted against a zero-quantity or already-deployed asset.

**Phase to address:**
Asset+checkout phase (single-asset checkout) and licenses/consumables phase (quantity-based seats/accessories) — verify with a concurrent-request test against a qty=1 resource.

---

### Pitfall 6: QR/label generation quietly depends on network access, breaking air-gapped deployments

**What goes wrong:**
QR/barcode label generation is implemented using a hosted QR-image API (e.g. an `api.qrserver.com`-style URL embedded in a label template) or a CDN-loaded JS barcode library, because it's the fastest way to get a visually correct label working in local dev (which has internet access). It works perfectly in every dev/demo environment and then produces broken/missing labels the moment it's deployed air-gapped — exactly the deployment mode this platform explicitly targets.

**Why it happens:**
Dev machines have internet; the failure is invisible until first air-gapped/offline QA, which may happen late or not at all before ship.

**How to avoid:**
This codebase already vendors everything needed to do this fully offline and server-side — `qrcode[pil]` and `Pillow` are already in `backend/requirements.txt` (currently used only for MFA-enrollment QR codes in `mfa_service.py`), and `reportlab` is already used for PDF generation elsewhere. Generate QR/barcode images server-side with `qrcode`/Pillow, and embed the resulting image bytes directly into a `reportlab`-generated label PDF — no external HTTP calls, no CDN-hosted font/script dependency, no client-side-only canvas rendering that can't be captured into a downloadable/printable sheet. Add an explicit test that generates a label with the process's outbound network access blocked.

**Warning signs:**
- Any `requests.get(...)`/`httpx` call to a third-party host inside label/QR generation code.
- A `<script src="https://cdn...">` reference in a label-rendering template.
- Label generation only exists as client-side canvas rendering with no server-side PDF/image export.

**Phase to address:**
UI/labels phase — verify by generating a label sheet in an environment with network egress disabled.

---

### Pitfall 7: Agent heartbeats silently "resurrect" or corrupt a retired/disposed manual asset

**What goes wrong:**
The heartbeat handler (`backend/agent_heartbeat_endpoints.py`) upserts by `asset-{hostname}` unconditionally on every heartbeat, setting `agentStatus: "Online"` and refreshing hardware fields — with no awareness of any ITAM lifecycle state. If an operator marks an asset `retired`/`disposed` in ITAM but the physical machine is still powered on (not yet wiped/decommissioned) and still sending heartbeats, the very next heartbeat will flip `agentStatus` back to `Online` and refresh telemetry fields on a document ITAM considers gone — with no signal to the ITAM operator that a "disposed" asset is still phoning home.

**Why it happens:**
The heartbeat path and the ITAM lifecycle are two independent write paths into the same `assets` document that don't currently know about each other; this is a direct consequence of correctly *not* forking the model (Pitfall 2) — the fix is coordination between the two paths, not separation.

**How to avoid:**
When the heartbeat handler's upsert filter matches an existing asset, check its `lifecycleStatus` before applying agent-derived fields: if it's `retired`/`disposed`/`archived`, either skip the agent-derived `$set` fields entirely (keep the ITAM record authoritative) or apply them but also set a `lifecycleConflict: true` flag the ITAM UI can surface ("this retired asset is still reporting a live agent"). Never let a heartbeat silently overwrite an ITAM-owned lifecycle field.

**Warning signs:**
- No lifecycle-status check exists anywhere in the heartbeat's asset-upsert code path.
- An asset can show `lifecycleStatus: "disposed"` and `agentStatus: "Online"` simultaneously with no UI indication that's a conflict.

**Phase to address:**
Asset+checkout phase (where `lifecycleStatus` is introduced and wired into checkout eligibility) — verify by simulating a heartbeat for a hostname whose asset is marked retired and asserting the lifecycle field is preserved/conflict is surfaced, not silently overwritten.

---

### Pitfall 8: Manual (non-agent) assets break code paths that assume an agent/hostname/telemetry link exists

**What goes wrong:**
Existing asset-detail and metrics code assumes an agent link: `get_asset_details()` in `asset_endpoints.py` looks up `db.agents.find_one({"hostname": hostname}, ...)` and enriches from `meta`; `get_asset_metrics()` has a three-tier fallback chain (per-metric time series → agent history → telemetry snapshot) that ultimately still expects *some* agent or telemetry data to exist. A manually catalogued ITAM asset (a monitor, a printer, a purchased accessory) has no `hostname`, no `agents` doc, and no telemetry at all — any UI/endpoint built against the agent-asset assumption either 500s, or renders a metrics panel full of misleading zeros for hardware that was never meant to report metrics.

**Why it happens:**
The existing asset detail/metrics code was written exclusively for agent-discovered endpoints; ITAM introduces a genuinely different kind of asset record for the first time, and it's easy to extend the schema (Pitfall 2's correct fix) without also auditing every consumer that implicitly assumed "asset" == "has an agent."

**How to avoid:**
Add an explicit `source: "agent" | "manual"` discriminator field on every asset document. Gate agent-specific enrichment/metrics UI panels on `source == "agent"` rather than presence-checking optional fields at each call site. Audit `get_asset_details`, `get_asset_metrics`, and any dashboard/report code that reads `assets` for hostname/agent assumptions and add an explicit manual-asset branch (e.g. skip the agent-metrics fallback chain entirely and show "no telemetry — manually catalogued asset" instead of a confusing empty chart).

**Warning signs:**
- `GET /api/assets/{id}/metrics` called against a manually created asset returns an error or a chart full of zeros instead of a clear "not applicable" state.
- Asset detail view shows blank/`Unknown` hardware fields for a manual asset styled identically to a mis-reporting agent asset, with no way to tell the difference.

**Phase to address:**
Catalog/foundation phase (introduce the `source` discriminator) and asset+checkout phase (audit/gate the detail and metrics endpoints) — verify by creating a manual asset with no linked agent and confirming detail/metrics endpoints degrade gracefully.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Storing ITAM custom fields as an unstructured `custom_fields: dict` (mirroring the existing `tickets_models.py` precedent) with no schema/definitions collection | Fast to ship; matches an existing pattern already in the codebase | No per-tenant field-type validation; filtering/reporting on custom fields becomes ad hoc string matching; can't render a proper "add custom field" admin UI | Acceptable for MVP if a `custom_field_definitions` collection is planned before custom fields are exposed to reporting/filtering |
| Computing depreciation on-the-fly at read time instead of persisting a depreciation schedule | No scheduler needed; always consistent with "today" | Reports needing "book value as of date X" (audit snapshot, historical export) can't reconstruct past values without re-deriving purchase-date-relative math, and a manual book-value override won't compose cleanly with on-the-fly computation | Acceptable for MVP as long as no feature needs historical/as-of-date snapshots yet |
| Reusing the existing `criticality` field (security-remediation-escalation gating) for ITAM "business importance" ranking | No new field, one less migration | Couples ITAM prioritization semantics to autonomous-remediation escalation logic that was designed for a different purpose | Never — use a distinct field even if the value space looks similar |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| QR/barcode generation | Calling a hosted QR-image API or CDN barcode script for convenience in dev | Generate server-side with the already-vendored `qrcode`/`Pillow` (used today for MFA) and embed into a `reportlab` PDF — zero external calls |
| `assets` collection cache (`@cached(ttl=60, key_prefix="assets")` on `GET /api/assets`) | New ITAM mutating endpoints (checkout, check-in, lifecycle-status change) forget to call `invalidate_cache("assets:*")`, unlike every existing mutating handler in `asset_endpoints.py` (delete, bulk-update, criticality, link all call it) | Call `invalidate_cache("assets:*")` (and `"agents:*"` if agent-linked fields change) at the end of every new mutating ITAM endpoint, mirroring the existing pattern exactly |
| New unique/tag indexes on `assets` | Adding a unique index on a new `assetTag` field without accounting for the thousands of pre-existing agent-discovered documents that predate ITAM and have no tag yet — the index creation (or first upsert) fails or silently excludes untagged docs | Use a sparse unique index (or per-tenant compound unique index) plus a backfill migration that assigns tags to legacy assets before enforcing uniqueness broadly |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Cross-tenant warranty/depreciation sweep querying `assets` without an index on the new date fields | Sweep latency grows linearly with total assets across *all* tenants, not just the ones with near-term warranty/depreciation events | Add compound indexes in `database.py`'s existing index-creation block (mirroring e.g. `tickets`'s `{tenantId, due_date, status}` pattern) — e.g. `{tenantId, warrantyExpiry}` | Once total asset count across all tenants reaches the point a full collection scan takes multiple seconds — will vary by deployment, but this codebase's existing convention is to index every date-filtered sweep query, so treat it as required from day one, not an optimization |
| Assignment/checkout history stored as an ever-growing embedded array (`$push`) inside the asset document instead of a separate collection | Slow reads of a busy accessory/consumable's full document; risk of approaching MongoDB's 16MB document limit for high-turnover items with years of checkout history | Use a separate `asset_checkout_history` (or similar) collection referencing the asset id, mirroring the existing separate-collection convention this codebase already uses for audit trails (`evidence_audit_log`, `remediation_escalations` are not embedded arrays either) | Noticeable once an individual consumable/accessory accumulates hundreds+ of checkout events |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| QR code payload encodes a raw asset id/deep-link resolved by an endpoint that doesn't scope by tenant | Scanning a printed label from one tenant could resolve/leak another tenant's asset details if the "resolve by tag" endpoint's query isn't tenant-scoped like the rest of `asset_endpoints.py` | Resolve QR/tag lookups through the same `TenantIsolatedCollection`-backed query pattern (or explicit `tenantId` filter) used everywhere else in `asset_endpoints.py` |
| "Assigned to" / checkout recipient stored and trusted as free text | Same class of issue already documented in this codebase for remediation-task `assignee` (`compliance_remediation_sla_service.py`: "assignee is untrusted free text... this never passes it straight through as a recipient") — a free-text ITAM assignee could be used to spoof audit-trail identity or misdirect notifications | Resolve "assigned to" to a real tenant-scoped user document (email/id lookup), never trust the raw string as a notification recipient or audit identity |
| Bulk ITAM operations (bulk check-in, bulk status change) bypass the existing `_BULK_UPDATE_ALLOWLIST` security control | Unfiltered `request.updates` pass-through would let a caller mass-write arbitrary fields (including e.g. `tenantId` itself) across many assets at once | Add new bulk-editable ITAM fields to `_BULK_UPDATE_ALLOWLIST` deliberately; never switch that endpoint to unfiltered field pass-through |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| No visible distinction between agent-discovered and manually catalogued assets | Users try to "check out" a machine that's currently reporting a live agent heartbeat, or see a manual asset with blank hardware fields and assume it's broken data entry rather than "not agent-managed" | Explicit "Agent-Managed" vs "Manually Catalogued" badge (backed by the `source` discriminator from Pitfall 8), with a "complete this record" prompt for manual assets missing ITAM fields |
| Generic error on out-of-stock checkout (consumable/seat with 0 available) | Tech mid-checkout gets an unhelpful 400/500 and doesn't know whether to wait, request more stock, or pick something else | Return a specific "0 of N available" 409 response with current available/total counts, mirroring the existing SLA at_risk/breached status vocabulary in `compliance_remediation_sla_service.py` rather than inventing new copy |
| Warranty/depreciation status shown as raw dates with no at-a-glance urgency | Operators miss upcoming warranty expirations until they've already lapsed | Reuse the existing at-risk/breached visual pattern already established for SLA tracking (`compliance_remediation_sla_service.py`'s `sla_status`) for warranty/depreciation "at risk / expired" badges instead of a new ad hoc scheme |

## "Looks Done But Isn't" Checklist

- [ ] **Single-asset checkout:** Often missing the atomic double-checkout guard — verify two simultaneous checkout requests for the same asset can't both succeed (fire them concurrently in a test).
- [ ] **License seat / consumable checkout:** Often missing an atomic decrement — verify `available` never goes negative under concurrent checkout requests against a qty=1 resource.
- [ ] **License seat reclaim:** Often missing seat reclaim on user deactivation/offboarding — verify a deactivated tenant user's assigned seats return to the pool (or are explicitly flagged) rather than being permanently consumed.
- [ ] **QR/label PDF export:** Often only tested with network access available — verify label generation succeeds end-to-end with outbound network access blocked on the server process.
- [ ] **Asset tag / PO number uniqueness:** Often only enforced in application code, not the database — verify a real unique index exists (and is scoped correctly per tenant vs. globally, per the actual requirement) so a bypassed counter fails loudly instead of silently duplicating.
- [ ] **Depreciation schedule at end of useful life:** Often missing the salvage-value floor — verify computed book value clamps at salvage value and never goes negative or keeps decreasing past the asset's useful life.
- [ ] **New ITAM collections vs. the tenant-isolation exemption list:** Often not double-checked — verify no new ITAM collection was accidentally added to `TenantIsolatedDatabase`'s global-reference-data exemption list in `backend/database.py` (which would make it shared across all tenants).
- [ ] **Agent heartbeat vs. retired/disposed lifecycle state:** Often not tested — verify a heartbeat for a hostname whose asset is marked retired/disposed doesn't silently flip it back to "Online" with no conflict signal.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|-----------------|
| Tenant-isolation bypass in a new scheduler (orphaned/leaked ITAM data) | HIGH | Audit new ITAM collections for `tenantId: "ORPHANED_DATA_NO_TENANT_CONTEXT"` docs, write a migration to reassign or purge them, patch the scheduler to the raw-db pattern, add a regression test asserting the scheduler never resolves `get_database()` itself |
| `status` field collision shipped | MEDIUM | Introduce the correctly-named `lifecycleStatus` field, migrate existing lifecycle values out of `status` into it, update every consumer (`global_search_endpoints.py`, `skill_handlers_queries.py`, `_BULK_UPDATE_ALLOWLIST`, frontend) in lockstep, add a regression test asserting agent-liveness `status` values are untouched by ITAM code |
| Duplicate asset tags / PO numbers from a non-atomic counter | LOW–MEDIUM | Add the missing unique index (will surface existing duplicates as an error), write a one-off dedupe script that appends a disambiguating suffix to collided tags, backfill the atomic counter to the current max before re-enabling creation |
| Manual asset breaks detail/metrics endpoint | LOW | Add the `source` discriminator retroactively (default existing docs to `"agent"`), add the missing manual-asset branch to the affected endpoint(s), backfill/verify against existing manually-entered records if any already exist |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Scheduler tenant-isolation bypass | Procurement/finance (warranty/depreciation schedulers), licenses/consumables (expiry alerts) — pattern documented in catalog/foundation | Code review checklist: new scheduler modules never call `get_database()` internally; wired at startup with the raw `_mdb.db` handle, mirroring `compliance_remediation_sla_service.py` |
| Forking `assets` into a parallel collection | Catalog/foundation | Diff review: new ITAM fields land on the existing `assets` document shape; no new `itam_assets`-style collection introduced |
| `status` field name collision | Catalog/foundation | Grep for `"status"` reuse before merging any schema change; lifecycle field is named distinctly (`lifecycleStatus`/`assetStatus`) |
| Non-atomic sequential ID generation | Catalog/foundation (asset tags), procurement/finance (PO numbers) | Concurrent-creation test: N parallel create requests produce N distinct tags/PO numbers; unique index exists |
| Checkout/seat-quantity race conditions | Asset+checkout, licenses/consumables | Concurrent-request test against a qty=1 asset/consumable/seat: exactly one request succeeds |
| QR/label generation depends on network | UI/labels | Generate a label sheet with the server process's outbound network access blocked; confirm it still succeeds |
| Heartbeat resurrects retired/disposed asset | Asset+checkout | Simulate a heartbeat for a hostname whose asset is `retired`/`disposed`; assert lifecycle field preserved or conflict flagged, not silently overwritten |
| Manual asset breaks agent-assuming code paths | Catalog/foundation (introduce `source` field), asset+checkout (audit detail/metrics endpoints) | Create a manual asset with no linked agent doc; confirm detail and metrics endpoints degrade gracefully instead of erroring |

## Sources

- `backend/tenant_context.py`, `backend/tenant_middleware.py`, `backend/database.py` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`) — primary source, HIGH confidence
- `backend/compliance_remediation_sla_service.py` — primary source (documented anti-pattern + established raw-db scheduler fix), HIGH confidence
- `backend/app_startup.py` (scheduler wiring with raw `_mdb.db`) — primary source, HIGH confidence
- `backend/asset_endpoints.py` (`_BULK_UPDATE_ALLOWLIST`, cache invalidation pattern, agent-enrichment logic, metrics fallback chain) — primary source, HIGH confidence
- `backend/agent_heartbeat_endpoints.py` (asset upsert `$set`/`$setOnInsert` shape, `status: "active"` semantics) — primary source, HIGH confidence
- `backend/tickets_models.py`, `backend/tickets_service.py`, `backend/tickets_config_mixin.py` (existing `custom_fields` precedent) — primary source, HIGH confidence
- `backend/requirements.txt` (`qrcode[pil]`, `Pillow`, `reportlab` already vendored) — primary source, HIGH confidence
- `.planning/PROJECT.md` (v4.0 ITAM milestone scope, constraints, offline-first value) — primary source, HIGH confidence
- Prior milestone's `.planning/research/PITFALLS.md` (v3.3) — corroborating source for the recurring scheduler tenant-isolation bug class, HIGH confidence (same repo, independently re-verified here)
- Generic MongoDB atomic-operation race-condition prevention pattern (`findOneAndUpdate` embedding the availability check in the filter) — web search, LOW confidence (not verified against this codebase, but a well-established generic MongoDB pattern)
- Generic straight-line depreciation salvage-value-floor edge case — web search, LOW confidence (standard accounting behavior, not verified against this codebase's future implementation)

---
*Pitfalls research for: ITAM lifecycle addition to an existing agent-centric security CMDB*
*Researched: 2026-08-04*
