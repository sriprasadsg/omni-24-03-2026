# Phase 59: Procurement & Finance (Warranty & Depreciation) - Context

**Gathered:** 2026-08-05 (auto mode — user requested autonomous continuation through Phases 59-61, checking in only at blocking-human gates)
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend/API-only phase (frontend console is Phase 61 — do not build UI here, same precedent as Phases 57/58). Gives every asset a financial record (ITAM-FIN-01/02/03):

- Purchase cost, purchase date, PO number, supplier reference on an asset.
- Warranty tracking (purchase date + warranty period) with proactive expiry alerts routed through the existing notification/webhook infrastructure.
- Computed-at-read-time book value via a straight-line depreciation schedule assigned at the Model level — no persisted mutable value, no external accounting/GL integration.

</domain>

<decisions>
## Implementation Decisions

### Money Representation
- **D-01 (Claude's discretion, auto-selected):** Purchase cost and computed book value are stored/returned as integer cents (`purchaseCostCents`, not a bare float dollar amount) — avoids floating-point drift in depreciation arithmetic. No prior money-handling convention exists elsewhere in this codebase to follow instead.

### Supplier Reference
- **D-02 (auto-selected):** Purchase record references the existing Phase 56 Supplier catalog entity by id (`supplierId`), not a free-text supplier name — consistent with how `AssetModelCreate` already references `manufacturerId`/`categoryId` by id rather than by name.

### Warranty Expiry Alert Delivery
- **D-03 (auto-selected):** A background sweep (mirroring `compliance_remediation_sla_service.py`'s `run_sla_pass`/`start_remediation_sla_scheduler` pattern — raw `db` handle + explicit per-tenant `set_tenant_id`, never `get_database()`) finds assets whose warranty expiry falls within a per-tenant-configurable alert window and calls `notification_service.send_notification(db, tenant_id, event_type, payload)`. This is the highest-severity risk class flagged in this milestone's research (STATE.md) — the scheduler MUST NOT use the tenant-isolated request-scoped `db` helper.
- **Alert window default:** follow the same lookup-order precedent as `get_sla_at_risk_window` (per-tenant config doc → global config doc → hard-coded default) rather than a single hard-coded constant, so tenants can tune it later without a schema change.

### Depreciation Schedule
- **D-04 (auto-selected):** Straight-line only (per locked requirement text — no reducing-balance or other method). Schedule params (useful-life years, salvage value) live on the Model entity (extend `AssetModelCreate`/`AssetModelUpdate` in `backend/itam_models.py`), not on the individual asset — matches ITAM-FIN-03's explicit "assigned at the model level" wording.
- Book value floors at the salvage value (never goes negative or below salvage) and is computed purely at read time from `purchaseDate`/`purchaseCostCents` + the Model's depreciation params — no stored/cached book value field, no background job for this part.

### Claude's Discretion (deferred to research/planning)
- Exact per-tenant config doc `type` string and field names for the warranty alert window (mirror `evidence_staleness`/`remediation_sla_at_risk` naming convention).
- Whether partial-year depreciation is prorated by day/month or only whole-year — pick the simpler whole-year-boundary approach unless research finds a reason not to.
- Exact webhook/notification `event_type` string for warranty-expiry alerts (e.g. `itam.warranty_expiring`).
- PO number format/validation (free text vs pattern) — no constraint specified, treat as free text.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase source of truth
- `.planning/ROADMAP.md` (Phase 59 section) — goal, success criteria, depends-on Phase 56
- `.planning/REQUIREMENTS.md` (ITAM-FIN-01/02/03) — locked requirement text
- `.planning/PROJECT.md` (Current Milestone: v4.0 ITAM section) — confirms Phase 61 is the sole frontend phase for this milestone; Phase 59 is backend/API-only, mirroring Phase 57/58's precedent

### Phase 56 foundation (must extend, not fork)
- `backend/itam_models.py` — `AssetModelCreate`/`AssetModelUpdate` (line ~141) is the Model entity to extend with depreciation params; `SupplierCreate` (line ~98) is the existing Supplier catalog entity to reference by id
- `backend/itam_catalog_endpoints.py`, `backend/itam_catalog_service.py` — existing catalog CRUD patterns (RBAC gate, tenant isolation, router registration) to follow for any new purchase/finance sub-resource endpoints
- `backend/itam_asset_endpoints.py` — `_require_itam_admin` RBAC dependency, asset lookup pattern

### Recurring risk this phase must avoid (per v4.0 research, STATE.md)
- `backend/compliance_remediation_sla_service.py` — the canonical correct pattern for a tenant-isolation-safe background sweep: raw `_mdb.db` + explicit per-tenant `set_tenant_id(...)`, never `get_database()`. The warranty-expiry-alert sweep in this phase is exactly the kind of background scheduler this warning exists for.

### Existing reusable patterns (analogs for this phase's two new capabilities)
- `backend/notification_service.py` — `send_notification(db, tenant_id, event_type, payload)`, existing channel/rule model; warranty alerts route through this, not a new notification mechanism
- `backend/webhook_service.py`, `backend/webhook_endpoints.py` — existing webhook delivery infra `send_notification` already integrates with
- `backend/compliance_remediation_sla_service.py` — `get_sla_at_risk_window` per-tenant-configurable-window lookup pattern (per-tenant doc → global doc → hard-coded default) — clone for the warranty alert window
- `backend/itam_models.py::_validate_iso8601_date` — existing ISO-8601 date validator to reuse for `purchaseDate`/warranty date fields rather than writing a new one

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AssetModelCreate`/`AssetModelUpdate` (`backend/itam_models.py`) — extend with depreciation policy fields (useful-life years, salvage value)
- `SupplierCreate` (`backend/itam_models.py`, Phase 56) — referenced by id from the new purchase/finance fields
- `notification_service.send_notification` — existing delivery mechanism, no new notification channel type needed
- `compliance_remediation_sla_service.py` — scheduler skeleton and tenant-safe sweep pattern to clone

### Established Patterns
- Backend/API-only phase pattern established in Phases 57/58 — Phase 61 is the sole frontend phase for the entire v4.0 ITAM milestone.
- Tenant isolation convention — `TenantIsolatedDatabase`/`TenantIsolatedCollection` for request-scoped reads/writes; raw `db` + explicit `set_tenant_id` for any background sweep (see Recurring Risk above).
- Model-level policy attached via the existing catalog Model entity, not duplicated per-asset — same shape as Phase 56's fieldsets-at-model-level pattern.

### Integration Points
- Depreciation/book-value computation likely lives alongside `itam_asset_endpoints.py`'s existing asset read path (computed field on GET, not a stored one).
- Warranty alert sweep needs a startup hook registration (mirror `start_remediation_sla_scheduler`'s call site in `app_startup.py`).
- No frontend integration this phase — Phase 61 is the only consumer of these endpoints/fields from the UI side.

</code_context>

<specifics>
## Specific Ideas

None — no particular external product screenshots, vendor integrations, or specific numeric defaults (alert window days, useful-life defaults) were given by the user. These are left to research/planning to set sensible defaults, consistent with the auto-mode discussion this phase ran under.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

### Reviewed Todos (not folded)
None checked this session (auto mode — todo cross-reference skipped to stay in single-pass budget; planner should still run its own scope-boundary check).

</deferred>

---

*Phase: 59-Procurement & Finance (Warranty & Depreciation)*
*Context gathered: 2026-08-05*
