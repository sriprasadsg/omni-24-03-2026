# Requirements: v4.0 ITAM (IT Asset Management Lifecycle)

**Defined:** 2026-08-04
**Core Value:** A full Snipe-IT-parity ITAM lifecycle — procurement → assignment → maintenance → retirement — built on top of the existing security/observability CMDB, without forking it.

## v1 Requirements

### Catalog & Organization (ITAM-CAT)

- [x] **ITAM-CAT-01**: Admin can manage Manufacturer / Model / Category / Location catalog entities (CRUD), referenced by ID from assets.
- [x] **ITAM-CAT-02**: Admin can create and manage a manual (non-agent) asset, with a unique per-tenant asset tag, coexisting with agent-discovered assets via a source discriminator.
- [x] **ITAM-CAT-03**: Admin can manage Suppliers as a distinct catalog entity.
- [x] **ITAM-CAT-04**: Admin can define custom fields grouped into fieldsets, attached at the model level.
- [x] **ITAM-CAT-05**: User can generate a printable QR + 1D barcode label (PDF label sheet) for an asset, fully offline (no external service or network call).

### Lifecycle & Check-in/out (ITAM-LIFE)

- [x] **ITAM-LIFE-01**: Asset carries a status lifecycle label (deployable/deployed/archived/retired/disposed/broken), distinct from the existing agent connectivity status field.
- [x] **ITAM-LIFE-02**: User can check out an asset to a user or a location; checkout is only allowed from a deployable-typed status.
- [x] **ITAM-LIFE-03**: User can check in an asset, returning it to stock and clearing its assignment.
- [x] **ITAM-LIFE-04**: Every check-out/check-in is recorded in an append-only assignment history / audit trail.
- [x] **ITAM-LIFE-05**: User can mark an asset as physically audited on a given date, with an overdue-audit report.

### Procurement & Finance (ITAM-FIN)

- [x] **ITAM-FIN-01**: Asset carries purchase cost, purchase date, PO number, and supplier.
- [x] **ITAM-FIN-02**: Asset warranty is tracked (purchase date + warranty period) with expiry alerts, routed through the existing notification/webhook infrastructure.
- [x] **ITAM-FIN-03**: Asset book value is computed via a straight-line depreciation schedule assigned at the model level, computed at read time (no external accounting/GL integration).

### Licenses & Consumables (ITAM-LIC)

- [x] **ITAM-LIC-01**: Admin can manage software licenses with seat counts, assign/reclaim seats to a user or asset, and track license expiry.
- [x] **ITAM-LIC-02**: Admin can manage accessories/consumables with quantity-aware checkout (supports quantity > 1 per transaction, not limited to 1).
- [x] **ITAM-LIC-03**: Admin can attach components (RAM/HDD/GPU-style sub-inventory) to a parent asset.

### Operator UI (ITAM-UI)

- [x] **ITAM-UI-01**: The ITAM console is reachable via an admin-gated nav entry (new AppView + App.tsx route + Sidebar entry + dedicated `manage:itam` permission), following the Phase 47/48 pattern.

## Gap Closures (post-v4.0, not part of the ITAM milestone above)

Standalone maintenance items promoted from `.planning/ROADMAP.md`'s Backlog section, tracked here because this is the current live requirements file — not because they belong to v4.0 ITAM. Each closes a gap in an earlier, already-shipped milestone.

- [ ] **SLA-03**: The remediation SLA at-risk window (`GET/PATCH /api/settings/remediation-sla`, live since v3.2 Phase 44-03) is exposed in the Settings UI — extends SLA-01/SLA-02 (see `milestones/v3.2-REQUIREMENTS.md`). Phase 62.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Differentiators

- **ITAM-LINK-01**: Link a manually-catalogued ITAM record to its agent-discovered security twin (vuln/patch/criticality data) — optional FK, no competitor combines ITAM with a security agent.
- **ITAM-EVID-01**: Retiring/disposing an asset with linked compliance evidence (FIM baselines, scan history) auto-flags or archives that evidence. Depends on ITAM-LINK-01.
- **ITAM-REQ-01**: Requestable-assets self-service flow, routed through an approval gate mirroring the v3.4 remediation approval pattern.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Full GL/accounting integration (journal entries, multi-currency, tax) | Named out of scope in PROJECT.md; straight-line book-value report + CSV/PDF export is sufficient, same posture as existing compliance export |
| RFID/physical scanner driver integration | Named out of scope in PROJECT.md; standard USB HID barcode scanners against the existing asset-tag search field cover the practical use case |
| Real-time RFID/GPS asset location tracking | Requires hardware infrastructure this platform has no reason to own; location is a manually-selected catalog entity assigned at checkout |
| Forking the existing `assets` collection into a parallel ITAM-only collection | Would create two divergent sources of truth for the same concept — extend `assets` with a source discriminator instead |
| Migrating existing security-CMDB semantics | ITAM is additive, not a replacement for the agent-discovered security asset inventory |
| Requestable-assets self-service (this milestone) | Not named in the 4 target clusters; deferred to v2 (ITAM-REQ-01) with an approval gate when built |
| Agent-discovered ↔ manual-asset linking (this milestone) | High-value differentiator but touches two data models at once; deferred to v2 (ITAM-LINK-01) so both sides can be solid independently first |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ITAM-CAT-01 | Phase 56 | Complete |
| ITAM-CAT-02 | Phase 56 | Complete |
| ITAM-CAT-03 | Phase 56 | Complete |
| ITAM-CAT-04 | Phase 56 | Complete |
| ITAM-CAT-05 | Phase 58 | Complete |
| ITAM-LIFE-01 | Phase 56 | Complete |
| ITAM-LIFE-02 | Phase 57 | Complete |
| ITAM-LIFE-03 | Phase 57 | Complete |
| ITAM-LIFE-04 | Phase 57 | Complete |
| ITAM-LIFE-05 | Phase 57 | Complete |
| ITAM-FIN-01 | Phase 59 | Complete |
| ITAM-FIN-02 | Phase 59 | Complete |
| ITAM-FIN-03 | Phase 59 | Complete |
| ITAM-LIC-01 | Phase 60 | Complete |
| ITAM-LIC-02 | Phase 60 | Complete |
| ITAM-LIC-03 | Phase 60 | Complete |
| ITAM-UI-01 | Phase 61 | Complete |

**Coverage:**

- v1 requirements: 17 total
- Mapped to phases: 17/17 ✓
- Unmapped: 0

**Phase map:**

- Phase 56 — Catalog & Foundation (ITAM-CAT-01/02/03/04, ITAM-LIFE-01)
- Phase 57 — Lifecycle & Check-In/Out (ITAM-LIFE-02/03/04/05)
- Phase 58 — Asset Tags & Offline Labels (ITAM-CAT-05)
- Phase 59 — Procurement & Finance (Warranty & Depreciation) (ITAM-FIN-01/02/03)
- Phase 60 — Licenses & Consumables (ITAM-LIC-01/02/03)
- Phase 61 — Frontend ITAM Console (ITAM-UI-01)

---
*Requirements defined: 2026-08-04*
*Last updated: 2026-08-04 after roadmap creation — 17/17 v1 requirements mapped to phases 56–61*
