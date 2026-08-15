# Phase 60: Licenses & Consumables - Context

**Gathered:** 2026-08-05 (auto mode — user requested autonomous continuation through Phases 59-61, checking in only at blocking-human gates)
**Status:** Ready for planning

**Note on pre-existing draft plans:** `60-01-PLAN.md`/`60-02-PLAN.md`/`60-03-PLAN.md` already existed in this directory before this session, but are 9-line sketches with no frontmatter, no `<task>` structure, no threat model, no tenant-isolation/RBAC direction, and no evidence of ever passing plan-checker (no `60-PATTERNS.md`/`60-RESEARCH.md`/plan-check artifacts either). They are being treated as superseded — this phase is being replanned properly through research + gsd-planner, which will overwrite them with real GSD-format plans.

<domain>
## Phase Boundary

Backend/API-only phase (frontend console is Phase 61 — do not build UI here, same precedent as Phases 57/58/59). Tracks software licenses, consumables, and components as first-class ITAM sub-inventory (ITAM-LIC-01/02/03):

- Software licenses: seat counts, assign/reclaim a seat to a user or asset, expiry tracking.
- Accessories/consumables: quantity-aware checkout (checkout quantity > 1 in one transaction), available quantity correctly decremented.
- Components (RAM/HDD/GPU-style items): attached to a parent asset, listed on that asset's record.

</domain>

<decisions>
## Implementation Decisions

### Architectural Independence
- **D-01 (locked by ROADMAP):** This phase is architecturally independent of Phases 57-59 — different collections, same tenant-isolation/RBAC conventions. Depends only on Phase 56.

### Assignment/Checkout History Reuse
- **D-02 (auto-selected):** License seat assign/reclaim and consumable checkout both write to the same append-only history pattern Phase 57 established (`backend/itam_lifecycle_service.py`'s `write_history`/`list_history` against `db.assignment_history`) rather than inventing a second history mechanism — reuse the collection and helper functions directly if the record shape generalizes (a license/consumable is a different "asset" reference type, not a different history model), or clone the pattern into parallel `license_history`/`consumable_history` collections only if the record shape genuinely can't be shared (research to confirm which).

### Seat/Quantity Model
- **D-03 (auto-selected):** A license has a fixed total seat count; each assignment consumes one seat (assign to either a user id or an asset id — polymorphic target, mirroring Phase 57's `CheckoutRequest` targetType/targetId pattern per that phase's PD-01 decision, not two separate optional fields). Reclaiming a seat returns it to the available pool. Over-assignment (assigning past the seat count) is rejected, not silently allowed.
- **D-04 (auto-selected):** A consumable has a total quantity and an available quantity; checkout decrements available by the requested amount in one atomic operation (no partial/silent-drop fulfillment — if requested > available, the whole checkout is rejected, mirroring Phase 58's 60-04 "no-silent-drop bulk contract" precedent for label sheets).

### Component Attachment
- **D-05 (auto-selected):** A component references its parent asset by id (`parentAssetId`) and appears on that asset's detail view/response — not a separate top-level "components" list disconnected from the asset. Detaching a component clears the reference (component record persists, not deleted) — mirrors how Phase 57's check-in clears an assignment without deleting the asset.

### Claude's Discretion (deferred to research/planning)
- Exact endpoint/router file names (`itam_license_endpoints.py` vs extending an existing file) — check line counts against the 500-line CLAUDE.md limit during research before deciding.
- Whether license expiry needs a proactive-alert sweep like Phase 59's warranty alerts, or whether ITAM-LIC-01's "expiry tracking" is satisfied by a read-time computed field only (research should check if REQUIREMENTS.md's exact wording implies proactive alerting or just visibility) — do not assume Phase 59's scheduler pattern is required here unless the requirement text actually calls for it.
- Component "attached" vs "detached" as a status enum vs a nullable `parentAssetId` — pick whichever matches the codebase's existing lifecycleStatus-style conventions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase source of truth
- `.planning/ROADMAP.md` (Phase 60 section) — goal, success criteria, depends-on Phase 56 only
- `.planning/REQUIREMENTS.md` (ITAM-LIC-01/02/03) — locked requirement text
- `.planning/PROJECT.md` (Current Milestone: v4.0 ITAM section) — confirms Phase 61 is the sole frontend phase

### Phase 56 foundation (must extend, not fork)
- `backend/itam_models.py` — existing Pydantic model conventions (`CatalogEntityCreate`/`CatalogEntityUpdate` base classes, `extra="forbid"` config) to follow for new `LicenseCreate`/`ConsumableCreate`/`ComponentCreate` models
- `backend/itam_asset_endpoints.py` — `_require_itam_admin` RBAC dependency, asset lookup pattern

### Phase 57 foundation (reusable patterns for assign/checkout/history)
- `backend/itam_lifecycle_service.py` — `write_history`/`list_history` against `db.assignment_history`; the append-only, pre-image-preserving history pattern. `_apply_known_delta`/`_revert_on_history_failure` — failure-handling pattern if a history write fails after a state change.
- `backend/itam_models.py::CheckoutRequest` (~line 180) — the polymorphic `targetType`/`targetId` pattern (PD-01: never two separate optional id fields) — the pattern to mirror for license seat assignment target (user vs asset).
- `.planning/phases/57-lifecycle-check-in-out/57-01-PLAN.md`, `57-02-PLAN.md` — read for the exact tenant-isolation/concurrency-guarantee approach on state-changing operations (relevant to seat/quantity decrement races).

### Phase 58 precedent (no-silent-drop bulk contract)
- `.planning/phases/58-asset-tags-offline-labels/58-04-PLAN.md` / `58-04-SUMMARY.md` — the "no-silent-drop" bulk-operation contract (empty-list/over-cap/unresolved-id all refuse explicitly, never trimmed or silently dropped) — same principle applies to consumable bulk checkout quantities.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `write_history`/`list_history` (`backend/itam_lifecycle_service.py`) — candidate direct reuse or clone-pattern for license/consumable transaction history
- `CheckoutRequest`'s polymorphic target pattern (`backend/itam_models.py`) — candidate direct reuse or mirror for license seat assignment
- `_require_itam_admin` — RBAC gate to reuse, not reinvent

### Established Patterns
- Backend/API-only phase pattern established in Phases 57/58/59 — Phase 61 is the sole frontend phase for the entire v4.0 ITAM milestone.
- Tenant isolation convention — `TenantIsolatedDatabase`/`TenantIsolatedCollection` for request-scoped reads/writes.
- No-silent-drop bulk contract (Phase 58 precedent) applies to consumable quantity checkout.

### Integration Points
- Component attachment needs to surface on the existing asset detail/read endpoint in `itam_asset_endpoints.py` — research should confirm the exact response-shape extension point.
- No frontend integration this phase — Phase 61 is the only consumer of these endpoints from the UI side.

</code_context>

<specifics>
## Specific Ideas

None — no particular external product screenshots or numeric defaults given. Left to research/planning.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

### Reviewed Todos (not folded)
None checked this session (auto mode — todo cross-reference skipped to stay in single-pass budget).

</deferred>

---

*Phase: 60-Licenses & Consumables*
*Context gathered: 2026-08-05*
