# Project Research Summary

**Project:** Enterprise OmniAgent — v4.0 ITAM (IT Asset Management) Lifecycle Milestone
**Domain:** IT Asset Management (Snipe-IT parity), added as new lifecycle capability onto an existing multi-tenant FastAPI + MongoDB + React security/compliance CMDB
**Researched:** 2026-08-04
**Confidence:** HIGH

## Executive Summary

This milestone bolts a full ITAM lifecycle — manual asset cataloging, check-out/check-in, procurement/warranty/depreciation, software licenses, and consumables/accessories/components — onto an existing agent-centric security CMDB (`assets` collection, `asset_endpoints.py`). Experts building ITAM tools (Snipe-IT, GLPI, Freshservice) converge on a common shape: normalized catalog entities (manufacturer/model/category/supplier/location) referenced by ID, a status-typed lifecycle gating checkout, an append-only checkout ledger with a denormalized "current assignment" for fast reads, and model-level depreciation policy. All four research passes independently converge on the same central architectural decision: **extend the existing `assets` collection with a `source`/`assetSource` discriminator and additive optional fields — do not fork a parallel `itam_assets` collection.** This is corroborated by direct code reads (every cross-cutting feature — vuln findings, remediation playbooks, criticality gating, compliance evidence, global search — already assumes one `assets` collection is the CMDB) and is explicitly named in PROJECT.md as the risk to avoid.

The recommended approach requires almost no new stack: one new pure-Python dependency (`python-barcode` for 1D barcodes), reusing three already-installed libraries (`qrcode[pil]`, `reportlab`, `openpyxl`) that already have proven call-sites in this codebase (MFA QR codes, compliance PDF/Excel export). New backend work is organized as five new sibling router files (catalog, checkout, licenses, consumables, labels) plus a `POST /api/assets` endpoint that doesn't currently exist, following the router_registry.py + TenantIsolatedCollection conventions already established. Frontend work mirrors the Phase 47/48 `NativeSecurityConsole` pattern (tabs behind a `manage:itam` permission gate).

The key risks are all well-precedented failure modes this exact codebase has hit before: (1) background schedulers (warranty/depreciation sweeps) bypassing tenant isolation — must copy the raw-`db._db` + explicit per-tenant `set_tenant_id` pattern already proven in `compliance_remediation_sla_service.py`, not the naive `get_database()` approach; (2) forking the assets collection instead of extending it; (3) colliding the new ITAM lifecycle status with the existing agent-liveness `status` field (must be a distinctly named `lifecycleStatus`); (4) non-atomic sequential ID generation and checkout/quantity race conditions, both of which need atomic `find_one_and_update` filters, not read-then-write; and (5) QR/label generation accidentally depending on network access, breaking the platform's air-gapped deployment requirement. All five are addressable with patterns already present elsewhere in this codebase — this is a well-understood integration, not exploratory territory.

## Key Findings

### Recommended Stack

No new core technologies are needed — this is additive collections/endpoints/UI on the existing FastAPI (Python 3.12) + Motor/MongoDB + React/TypeScript stack. The only genuinely new dependency is `python-barcode==0.16.1` for 1D barcode (Code128/Code39) generation; QR codes, PDF label sheets, and Excel export all reuse already-installed and already-proven libraries (`qrcode[pil]`, `reportlab`, `Pillow`, `openpyxl`) via the same call patterns used in `mfa_service.py` and `compliance_reporting_pdf.py`. Straight-line depreciation is hand-rolled arithmetic (~10 lines), matching Snipe-IT's own approach — no accounting/depreciation library is justified. No message queue is needed; checkout and label generation are synchronous, matching the existing sync request/response FastAPI pattern.

**Core technologies:**
- FastAPI + Motor + MongoDB (existing, unchanged): every new ITAM collection is a Mongo collection behind the same `TenantIsolatedCollection` wrapper — no new datastore justified
- `python-barcode` 0.16.1 (new): the one genuinely new dependency, pure-Python 1D barcode generation for asset-tag labels
- `qrcode[pil]` / `reportlab` / `Pillow` / `openpyxl` (already installed): QR codes, PDF label sheets, Excel export — reuse proven call-sites, zero new dependencies

### Expected Features

Table-stakes ITAM functionality is well-defined by cross-referencing Snipe-IT, GLPI, and Freshservice. The current `assets` collection is confirmed (via direct code read) to be an agent-fingerprint record with no concept of manual assets, check-out/in, catalog entities, licenses, or custom fields — validating that this milestone is a genuine gap, not duplicative work.

**Must have (table stakes / MVP):**
- Manual (non-agent) asset creation — nothing else has anything to operate on without this
- Manufacturer/Model/Category/Location catalog entities — hard prerequisite for everything else
- Asset tag (unique per tenant) — needed before checkout and before labels
- Status lifecycle labels (deployable/deployed/archived/retired/disposed/broken), gating checkout correctness
- Check-out/check-in to user or location, with assignment history audit trail
- Purchase cost/date/PO/supplier fields — low cost, unlocks warranty + depreciation
- Admin-gated ITAM nav page (Phase 47/48 pattern)

**Should have (v1.x within milestone):**
- Suppliers as distinct catalog entity, warranty expiry alerts, depreciation schedule + book value, custom fields/fieldsets, QR/barcode label generation, software license seats, accessories/consumables with quantity-aware checkout

**Defer (v2+):**
- Physical audit/inventory-verification workflow, agent-discovered ↔ manual-asset linking (differentiator), compliance-evidence-aware retirement (differentiator), requestable-assets self-service flow, multi-currency/GL integration, RFID/scanner hardware driver integration

**Genuine differentiator:** this platform can link a manually-catalogued ITAM record to its agent-discovered security twin (vuln/patch/criticality data) — something no pure ITAM competitor can do, since none combine ITAM with a security agent. Recommended as a deliberate, later phase, not left implicit.

### Architecture Approach

Extend the single `assets` collection via an `assetSource: "agent" | "manual"` discriminator; add five new normalized catalog collections (manufacturers, asset_models, asset_categories, suppliers, locations) referenced by ID; use an append-only ledger (`asset_checkouts`, `consumable_checkouts`) plus a denormalized `currentAssignment` sub-document for fast reads; compute depreciation/warranty-remaining at read time as a pure function of stored inputs, never persist a mutable computed value; and run any cross-tenant background sweep (warranty-expiry) using the exact raw-db + per-tenant `set_tenant_id`/`reset_tenant_id` pattern already proven in `app_background_tasks.py`.

**Major components:**
1. `assets` collection (extended) — single CMDB source of truth for agent-discovered AND manually catalogued assets
2. Catalog collections (manufacturers/models/categories/suppliers/locations) — normalized reference data, small CRUD routers
3. `asset_checkouts` / `consumable_checkouts` ledgers — immutable audit trail, atomic guarded quantity/availability updates
4. `licenses` / `license_seats` — 1-to-N catalog + per-seat assignment, seats pre-created at license-creation time
5. `itam_finance_service.py` — pure-function depreciation/warranty computation at read time
6. `itam_label_endpoints.py` — offline QR/barcode + PDF label generation
7. Frontend `components/itam/*` + `ITAMDashboard.tsx` — mirrors `components/nativeSecurity/*` pattern, gated by new `manage:itam` permission

### Critical Pitfalls

1. **Background ITAM schedulers bypass tenant isolation** — warranty-expiry, depreciation, and license-expiry sweeps must never call `get_database()` internally; wire them at startup with the raw `_mdb.db` handle and thread `tenantId` explicitly per document, exactly like `compliance_remediation_sla_service.py`. This bug class has recurred across multiple past milestones in this codebase.
2. **Forking a parallel `itam_assets` collection instead of extending `assets`** — creates two sources of truth; every existing asset-aware surface (search, dashboards, bulk ops, criticality gating) only knows about `assets`.
3. **Reusing the `status` field name for ITAM lifecycle labels** — `assets.status` already means agent-liveness (heartbeat sets `"active"`); the new lifecycle enum needs a distinctly named field (`lifecycleStatus`).
4. **Non-atomic ID generation and checkout/quantity race conditions** — no existing precedent for atomic counters in this codebase; must use `find_one_and_update` with `$inc` for tags/PO numbers, and embed availability checks directly in checkout/seat/consumable update filters (not read-then-write).
5. **QR/label generation silently depending on network access** — must generate fully offline via already-vendored `qrcode`/`Pillow`/`reportlab`, verified by testing with outbound network access blocked, consistent with the platform's air-gapped deployment requirement.

## Implications for Roadmap

Based on research, suggested phase structure (architecture research's "Suggested Build Order" and feature-dependency graph converge on the same sequence):

### Phase 1: Catalog & Foundation
**Rationale:** Manufacturer/Model/Category/Supplier/Location catalog entities are a hard prerequisite for manual asset creation and everything downstream (feature dependency graph confirms this); this is also where the `assetSource`/`source` discriminator, `lifecycleStatus` field naming, and atomic-counter pattern must be established once so later phases copy it, not reinvent it.
**Delivers:** 5 catalog CRUD collections/routers, `POST /api/assets` (manual asset creation, currently missing entirely), `assetSource` discriminator, `lifecycleStatus` field, tenant-scoped unique asset-tag counter.
**Addresses:** Manual asset creation, catalog entities (Table Stakes, P1) from FEATURES.md.
**Avoids:** Pitfall 2 (forking assets), Pitfall 3 (`status` collision), Pitfall 4 (non-atomic ID generation), Pitfall 8 (manual assets breaking agent-assuming code paths).

### Phase 2: Check-Out/Check-In Lifecycle
**Rationale:** Depends on Phase 1's `lifecycleStatus` and manual asset records existing; this is the milestone's own headline verb ("who has this laptop").
**Delivers:** `asset_checkouts` append-only ledger, denormalized `currentAssignment`, atomic checkout/checkin endpoints, assignment history audit trail, heartbeat-vs-retired-asset conflict handling.
**Uses:** Motor's `find_one_and_update` atomic guard pattern from STACK.md/PITFALLS.md.
**Implements:** Architecture Pattern 2 (append-only ledger + denormalized current state).

### Phase 3: Asset Tags & Offline Labels
**Rationale:** Depends on Phase 1's asset tag field existing and being stable; self-contained increment once the tag exists.
**Delivers:** `itam_label_endpoints.py` — server-side QR (`qrcode[pil]`) + 1D barcode (`python-barcode`, new dependency) generation, `reportlab` label-sheet PDF export, all fully offline.
**Uses:** `python-barcode` (new), `qrcode[pil]`/`reportlab`/`Pillow` (existing) from STACK.md.
**Avoids:** Pitfall 6 (network-dependent label generation breaking air-gapped deployments).

### Phase 4: Procurement & Finance (Warranty/Depreciation)
**Rationale:** Depends on Phase 1's purchase/warranty fields being decided on the asset shape; depreciation requires the Model entity (Phase 1) so policy is assigned once per model, not re-entered per asset.
**Delivers:** Purchase cost/date/PO/supplier fields, warranty tracking, `itam_finance_service.py` (pure-function depreciation, no persisted mutable book value), warranty-expiry background scheduler wired via the raw-db cross-tenant pattern.
**Addresses:** Purchase/warranty/depreciation (Table Stakes P1/P2) from FEATURES.md.
**Avoids:** Pitfall 1 (scheduler tenant-isolation bypass) — the highest-severity, most-recurred pitfall in this codebase.

### Phase 5: Licenses & Consumables
**Rationale:** Independent of Phases 2-4 except reusing tenant-isolation/RBAC scaffolding; can be sequenced in parallel with Phase 3/4 if desired, but is listed after core lifecycle since it's lower urgency per the prioritization matrix.
**Delivers:** `licenses`/`license_seats` collections with atomic seat assign/reclaim, `consumables`/`consumable_checkouts` with atomic quantity-guarded checkout (supporting quantity > 1, deliberately not inheriting Snipe-IT's 1-per-transaction limitation), components attached to parent assets.
**Uses:** Architecture Pattern 2 (ledger) and the atomic `$gte`-guarded `$inc` pattern for quantity decrements.

### Phase 6: Frontend ITAM Console
**Rationale:** Can start in parallel once backend contracts for Phases 1-5 stabilize enough to mock, but final integration depends on all backend phases landing; threads through all prior phases.
**Delivers:** `ITAMDashboard.tsx` + `components/itam/*` tabs (Catalog, Checkout, Licenses, Consumables, Finance, Label printout), new `AppView` entry, `App.tsx`/`Sidebar.tsx` wiring, new `manage:itam` RBAC permission.
**Implements:** Phase 47/48 admin-gated nav pattern (`NativeSecurityConsole.tsx` precedent).

### Phase Ordering Rationale

- Catalog-before-assets-reference-catalog, assets-before-things-that-target-assets is a strict dependency chain confirmed independently by both FEATURES.md's dependency graph and ARCHITECTURE.md's suggested build order.
- Checkout/lifecycle-status must exist before assignment history can be tested or before agent-heartbeat conflict handling is meaningful — sequencing it as its own phase right after foundation avoids the "gating built as an afterthought" rework risk PITFALLS.md flags.
- Licenses/consumables are architecturally independent of lifecycle/procurement (different collections, same conventions) — flagged as safely parallelizable if the team wants to compress the timeline, but sequenced last here since FEATURES.md's prioritization matrix ranks them P2 vs P1 for core lifecycle/catalog/procurement.
- Frontend is deliberately its own phase, threaded last, because all four research files converge on reusing the exact Phase 47/48 pattern (low risk, well-documented) rather than needing dedicated architectural exploration.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Procurement & Finance):** the warranty-expiry background scheduler is the single highest-risk pattern in this milestone (Pitfall 1, HIGH severity, recurring bug class) — worth a focused `--research-phase` pass on the exact `app_startup.py` wiring and index strategy before planning.
- **Phase 5 (Licenses & Consumables):** the concurrency-safety pattern (atomic `$gte`-guarded decrement) has no existing precedent anywhere in this codebase to copy from — first-of-its-kind in this repo, worth verifying the chosen pattern against a concurrent-request test plan during phase planning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Catalog & Foundation):** directly modeled on existing CRUD router conventions already used throughout the codebase (`compliance_frameworks`, `roles`) — no new patterns.
- **Phase 3 (Labels):** fully solved by reusing existing, already-installed, already-proven libraries with a documented call-site to copy (`mfa_service.py`, `compliance_reporting_pdf.py`).
- **Phase 6 (Frontend):** directly modeled on the Phase 47/48 `NativeSecurityConsole` precedent, exact files and line numbers already identified.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified directly against `backend/requirements.txt`, live `pip show` output in the venv, and the PyPI JSON API for the one new dependency |
| Features | MEDIUM | Web-search-verified against Snipe-IT's documented behavior and cross-checked against GLPI/Freshservice, but no official Context7/API-docs source exists for product-behavior research of this kind |
| Architecture | HIGH | Every claim traceable to a specific file/line read in this exact codebase during the research pass, not generic ITAM literature |
| Pitfalls | HIGH | Majority of findings are primary-source reads of this exact codebase (`tenant_context.py`, `database.py`, `compliance_remediation_sla_service.py`, etc.); two generic-domain findings (MongoDB atomic-op pattern, depreciation salvage-floor) are explicitly marked LOW confidence within PITFALLS.md |

**Overall confidence:** HIGH

### Gaps to Address

- Checkout-ledger retention/archival policy at scale is flagged as an open question in ARCHITECTURE.md, not resolved — the append-only ledger grows unboundedly by design, and the codebase has no existing precedent for archiving `evidence_audit_log`-style collections either. Should be flagged during Phase 2 planning, not blocking for this milestone.
- Custom fields/fieldsets architecture (Snipe-IT's fieldset-per-model pattern) is named as a should-have but not detailed in ARCHITECTURE.md beyond "mirror `tickets_models.py`'s unstructured `custom_fields: dict` precedent for MVP" — worth a lightweight design decision during whichever phase picks this up, since PITFALLS.md flags unstructured custom fields as acceptable only if a `custom_field_definitions` collection is planned before reporting/filtering needs arise.
- Whether Cluster D (licenses/consumables) should actually be parallelized with Cluster B (procurement/finance) rather than sequenced after, as ARCHITECTURE.md suggests it's architecturally independent — a scheduling/resourcing decision for the roadmapper, not a research gap per se.

## Sources

### Primary (HIGH confidence)
- `backend/requirements.txt`, `backend/venv` `pip show` output — confirmed dependency versions
- `backend/asset_endpoints.py`, `backend/models.py`, `backend/database.py`, `backend/tenant_context.py`, `backend/tenant_middleware.py` — direct code reads establishing tenant-isolation and existing asset-model constraints
- `backend/compliance_remediation_sla_service.py`, `backend/app_startup.py`, `backend/app_background_tasks.py` — proven cross-tenant scheduler pattern to replicate
- `backend/mfa_service.py`, `backend/compliance_reporting_pdf.py`, `backend/evidence_coc.py` — proven reuse patterns for QR generation, PDF export, and append-only audit ledgers
- `backend/agent_heartbeat_endpoints.py`, `backend/agent_registry_endpoints.py`, `backend/seed_vulns_for_super.py` — asset ID generation and heartbeat-upsert behavior
- `App.tsx`, `components/Sidebar.tsx`, `backend/rbac_utils.py` — Phase 47/48 admin-gated nav precedent
- `.planning/PROJECT.md` — milestone scope and explicit constraints (reuse `assets`, no RFID, no GL integration, offline-first)
- PyPI JSON API (`python-barcode` 0.16.1, `requires_python >=3.9`)

### Secondary (MEDIUM confidence)
- Snipe-IT documentation (Barcodes, Managing Assets, Custom Fields, Asset Labels, Importing Licenses, Depreciation Types) — product-behavior reference for table-stakes convergence
- GLPI/Freshservice feature comparisons (SoftwareSuggest) — used only for the discovery-vs-manual-catalog convergence point
- grokability/snipe-it GitHub issues/discussions (#15679, #18890, #11342, #5140, #7348) — corroborating product-behavior detail (status typing, depreciation math, accessory quantity limitation)

### Tertiary (LOW confidence)
- Generic MongoDB atomic-operation race-condition prevention pattern (web search) — well-established pattern, not verified against this codebase's future implementation
- Generic straight-line depreciation salvage-value-floor edge case (web search) — standard accounting behavior, not yet verified against this codebase's implementation

---
*Research completed: 2026-08-04*
*Ready for roadmap: yes*
