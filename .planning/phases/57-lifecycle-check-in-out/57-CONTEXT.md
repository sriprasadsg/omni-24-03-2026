# Phase 57: Lifecycle & Check-In/Out - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Backend/API-only phase (frontend console is Phase 61 — do not build UI here). Delivers the "who has this" workflow on top of the `lifecycleStatus` field and manual-asset model shipped in Phase 56:

- Check an asset **out** to a user or a location (ITAM-LIFE-02) — only allowed when `lifecycleStatus == deployable`.
- Check an asset **in** (ITAM-LIFE-03) — returns it to stock (`lifecycleStatus -> deployable`) and clears its current assignment.
- Record every check-out/check-in as an **append-only** assignment history / audit trail (ITAM-LIFE-04), visible per asset (who, where, when).
- Mark an asset as physically audited on a given date, and produce an **overdue-audit report** (ITAM-LIFE-05).

These status-transition rules (deployable-gated checkout, checkin-returns-to-deployable) are locked by REQUIREMENTS.md text itself, not open questions — carried here so research/planning don't re-derive or re-litigate them.

</domain>

<decisions>
## Implementation Decisions

### Assignee model
- **D-01:** Check-out target for "a user" is an existing platform User account (`backend/models.py` `User`, the `users` collection) — no new lightweight "Person" (non-login) catalog entity is introduced this phase. — **Reversibility:** reversible — a non-login Person type can be added later as an additive alternate target without touching existing checkout records.

### Location field reuse
- **D-02:** Checking an asset out to a location **overwrites the asset's existing `locationId`** field (`backend/itam_models.py` `ManualAssetCreate.locationId`) rather than introducing a separate `assignedLocationId`. `locationId` means "where the asset currently is," whether that's its catalogued home or a checked-out location. — **Reversibility:** costly — once `locationId` is overwritten going forward, splitting it into a separate "home location" + "current location" later requires backfilling home-location values from the append-only assignment-history entries (D-03 of ITAM-LIFE-04), since the original value won't be recoverable from the asset document itself after the first checkout.

### Overdue-audit threshold
- **D-03:** "Overdue for audit" uses a **fixed default interval of 12 months** since the last physical-audit date (or since creation, if never audited) — not a per-tenant or per-model configurable setting. — **Reversibility:** reversible — a config value; can be made tenant- or model-configurable later without a migration.

### Checkout metadata
- **D-04:** Check-out captures an optional free-text **note** and an optional **expected-return date**, in addition to who/where/when. The expected-return date is what enables a future "overdue check-out" report without a later schema change. — **Reversibility:** reversible — both fields are additive and optional.

### Claude's Discretion
- Exact shape of the assignment-history collection/schema (separate collection vs. embedded array), the checkout/checkin endpoint routes and request/response contracts, and how the overdue-audit report is computed (query vs. precomputed) are implementation details for research/planning — the decisions above only fix the *user-facing* semantics.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase source of truth
- `.planning/ROADMAP.md` (Phase 57 section) — goal, success criteria, depends-on Phase 56
- `.planning/REQUIREMENTS.md` (ITAM-LIFE-02 through ITAM-LIFE-05) — locked requirement text

### Phase 56 foundation (must extend, not fork)
- `backend/itam_models.py` — `LifecycleStatus` enum (deployable/deployed/archived/retired/disposed/broken), `DEFAULT_LIFECYCLE_STATUS`, `ManualAssetCreate` (carries `locationId`), `ASSET_SOURCE_AGENT`/`ASSET_SOURCE_MANUAL` discriminators
- `backend/itam_asset_endpoints.py` — `_require_itam_admin` (manage:assets RBAC dependency), `next_asset_tag` helper, shared `/api/assets` prefix convention with legacy `backend/asset_endpoints.py`
- `backend/itam_catalog_endpoints.py` — `CATALOG_KINDS` / `CATALOG_REFERENCE_FIELDS` registry (confirms `locations` kind → `locationId` reference field)
- `.planning/phases/56-catalog-foundation/56-01-SUMMARY.md` — dependency_graph explicitly lists `affects: phase_57_checkout`

### Existing audit-trail pattern (analog for ITAM-LIFE-04)
- `backend/remediation_audit_service.py` — existing append-only audit-trail service in this codebase (native security stack), useful analog for the assignment-history requirement
- `.planning/codebase/ARCHITECTURE.md` §Anti-Patterns "Missing Audit Trail" — project convention that every state-changing endpoint records an audit entry

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_require_itam_admin` (`backend/itam_asset_endpoints.py`) — manage:assets permission dependency; check-out/check-in/audit endpoints should reuse this rather than defining a new RBAC gate.
- `TenantIsolatedDatabase` / `TenantIsolatedCollection` (`backend/database.py`) — any new assignment-history collection must go through this, per project-wide tenant isolation convention.

### Established Patterns
- `manage:assets` permission gate established in Phase 56 for all ITAM admin actions — reuse for checkout/checkin/audit-mark actions.
- The manual-creation path in `itam_asset_endpoints.py` explicitly never writes the `status` key (reserved for agent-liveness); the same care applies to `lifecycleStatus` transitions on checkout/checkin — don't collide with the agent-heartbeat `status` field.
- `lifecycleStatus` applies uniformly to both `ASSET_SOURCE_MANUAL` and `ASSET_SOURCE_AGENT` assets (Phase 56 Task 1 decision) — checkout/checkin must work for both asset sources, not just manual ones.

### Integration Points
- `/api/assets` prefix is shared between `backend/asset_endpoints.py` (legacy agent-discovered) and `backend/itam_asset_endpoints.py` (ITAM/manual), registered in that order for route-priority reasons — new lifecycle endpoints should extend the ITAM router family and follow the same `router_registry.py` registration pattern.
- No frontend integration this phase — Phase 61 (Frontend ITAM Console) is the only consumer of these endpoints from the UI side.

</code_context>

<specifics>
## Specific Ideas

No specific UI/UX references — this is a backend/API-only phase (Phase 61 handles the frontend console). No particular external product screenshots or examples were referenced beyond the general Snipe-IT-parity framing already captured in PROJECT.md.

</specifics>

<deferred>
## Deferred Ideas

- Non-login "Person" checkout targets (e.g. contractors without platform accounts) — deferred; platform Users only for v1 (D-01). Revisit if real usage shows a gap.
- Per-tenant or per-model configurable audit interval — deferred; fixed 12-month default for v1 (D-03).

### Reviewed Todos (not folded)
None — discussion stayed within phase scope

</deferred>

---

*Phase: 57-Lifecycle & Check-In/Out*
*Context gathered: 2026-08-04*
