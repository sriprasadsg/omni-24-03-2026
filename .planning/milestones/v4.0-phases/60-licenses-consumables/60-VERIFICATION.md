---
phase: 60-licenses-consumables
verified: 2026-08-09T00:00:00Z
status: passed
score: 3/3 ROADMAP success criteria verified
behavior_unverified: 0
overrides_applied: 1
---

# Phase 60 Verification: Licenses & Consumables

**Goal:** Track software licenses, consumables, and components as first-class ITAM sub-inventory — seats assigned/reclaimed against a real seat count, consumables checked out in quantity, and components attached to a parent asset.

**Method:** Goal-backward verification against ROADMAP.md's 3 success criteria and REQUIREMENTS.md's ITAM-LIC-01/02/03 text, checked against the actual code on disk and actual test runs (not SUMMARY.md claims). This phase's implementation history is unusually fragmented — 6 commits spanning 2026-08-06 through 2026-08-09, none following this project's phase-plan commit convention, no SUMMARY.md existed until this session — so every claim below was independently re-derived from the current tree, not carried forward from prior notes.

---

## Success Criterion 1: "Admin can create a software license with a seat count, assign a seat to a user or asset, reclaim it, and see remaining/expired seats."

**VERIFIED.**

- `POST /api/itam/licenses` creates a license with `seatCount`/`expiryDate` — `itam_license_endpoints.py:22-45`.
- `POST /api/itam/licenses/{id}/assign` assigns a seat to `targetType: "user"|"asset"`, validates target existence, rejects a target already holding a seat (409), rejects assignment past `seatCount` (400 "No seats available"), writes an append-only history record — `itam_license_service.py::assign_license_seat`.
- `DELETE /api/itam/licenses/assignments/{id}` reclaims a seat, with compensation (assignment restored) if the history write fails — `itam_license_service.py::reclaim_license_seat`.
- **Fixed this session:** `GET /api/itam/licenses` and `GET .../{id}` returned the raw stored document only — no way to "see remaining/expired seats" short of manually cross-referencing assignment count against `seatCount` and comparing dates by hand. Added `_enrich_license_seats_and_expiry()` (read-time only, per 60-RESEARCH.md Pattern 4 — no background scheduler, matching this requirement's visibility-only wording against Phase 59 ITAM-FIN-02's explicit alerting wording). Regression test covers both a live and an already-expired license in the same request.
- Tests: `backend/tests/test_itam_license.py` — 10/10 pass (`TestLicenseManagement`, `TestLicenseAssignment`).

### Known Residual Risk (not fixed — documented, accepted)

`assign_license_seat` guards seat capacity with a `count_documents` read followed by a separate `insert_one` — not the atomic `find_one_and_update` guard-in-filter shape 60-RESEARCH.md Pattern 1 specifies (and the sibling `checkout_consumable`/`checkout_asset` functions actually use). Two near-simultaneous assign requests against the same license could both pass the count check before either inserts, over-assigning by one seat. The original implementer already flagged this in-code (`itam_license_service.py:65`, a comment on the tradeoff). Not fixed this session because:
- It requires a schema change (`seatsAvailable` field) and a rewrite of every seat-related test's mocking shape — larger than a verification-pass gap-fix.
- ROADMAP's success criteria describe functional behavior, not a concurrency guarantee.
- Worst case is a correctable over-assignment (reclaim one seat), not data corruption or a security issue.

Recommend a dedicated follow-up if this ITAM console sees concurrent multi-admin usage in practice.

---

## Success Criterion 2: "Admin can create an accessory/consumable and check it out in a quantity greater than one in a single transaction, with available quantity correctly decremented."

**VERIFIED.**

- `POST /api/itam/consumables` creates a consumable with `initialQuantity`; `availableQuantity` initialized equal to it — `itam_consumable_service.py::create_consumable`.
- `POST /api/itam/consumables/{id}/checkout` accepts `quantity >= 1` (Pydantic `Field(ge=1)` on `ConsumableCheckoutRequest`), atomically guards via `find_one_and_update({"availableQuantity": {"$gte": request.quantity}}, {"$inc": {"availableQuantity": -request.quantity}, ...})` — the guard and the mutation are the same atomic call, never a preceding read-then-check. An over-request is rejected in full (400), never partially fulfilled.
- `POST /api/itam/consumables/{id}/checkin` symmetrically increments, rejects `quantity <= 0` before touching the database.
- **Fixed this session:** `test_itam_consumable.py` had exactly 2 tests (create, list) before this session — the checkout/checkin logic that is this requirement's entire substance had zero coverage. Added 5 tests directly exercising the atomic guard's filter/update shape, the over-request rejection, checkout-against-nonexistent-consumable (404), successful checkin, and rejected non-positive checkin.
- Also fixed this session: a hacky dynamic `__import__("motor.motor_asyncio", ...)` `ReturnDocument` lookup, and drift between `ConsumableService`'s and `ComponentService`'s object shape (both now consistently `get_database()` + `self._tenant_id(current_user)`).
- Tests: `backend/tests/test_itam_consumable.py` — 7/7 pass.

---

## Success Criterion 3: "Admin can attach a component (RAM/HDD/GPU-style item) to a parent asset and see it listed on that asset's record."

**VERIFIED.**

- `POST /api/itam/components/{id}/attach/{asset_id}` sets `parentAssetId` on the component and `$addToSet`s the component id onto the asset's own `components` array; `detach` clears the reference without deleting the component record (D-05) — `itam_component_service.py`.
- **Fixed this session (correctness bug):** `update_component`/`attach_component`/`detach_component` omitted `return_document=ReturnDocument.AFTER` on their `find_one_and_update` calls. Motor/pymongo defaults to `BEFORE` — on a real database, every one of these calls was returning the **pre-update** document (e.g. attach returning a component with `parentAssetId: null`, the exact opposite of what just happened). Mocked tests never caught it because `find_one_and_update`'s return value is stubbed directly in every test — this is a class of bug functional/integration tests catch and pure-mock unit tests structurally cannot.
- **Fixed this session (missing requirement coverage):** the only pre-existing "listing" mechanism was the bare `components: [id, ...]` array riding along on the generic, non-ITAM-aware `GET /api/assets/{id}` route (`asset_endpoints.py`, no `response_model`, so the array passes through unfiltered) — an accidental side effect of `$addToSet`, not a deliberate feature. No name, type, or any other field; no query capability for a frontend to fetch a hydrated per-asset component list without pulling every component in the tenant and filtering client-side. Added `GET /api/assets/{asset_id}/components`, cloned from `itam_lifecycle_endpoints.py`'s existing `/history` sub-resource shape — this route was actually specified in `60-RESEARCH.md` Pattern 3 and simply never implemented.
- Tests: `backend/tests/test_itam_component.py` — 9/9 pass (`TestComponentManagement` + new `TestAssetComponentsSubResource`).

### Known Gap (not fixed — flagged, not blocking)

No `GET /{component_id}`, `PATCH /{component_id}`, or `DELETE /{component_id}` route exists, though the service methods do. Not required by ITAM-LIC-03's text or this success criterion; flagged for Phase 61 (frontend console) to request explicitly if its component-detail view needs it, rather than added speculatively here.

---

## Cross-Cutting Checks

- **Tenant isolation:** `licenses`/`license_assignments`/`itam_consumables`/`itam_consumable_checkouts`/`components` are all absent from `database.py`'s `TenantIsolatedDatabase` exemption allowlist (`compliance_frameworks`/`tenants`/`roles`/etc. only) — confirmed by direct read of `database.py:117-134`. Every `find`/`find_one`/`find_one_and_update`/`count_documents`/`insert_one` call through `get_database()` is auto-scoped by the ambient per-request `tenant_id`, per `TenantIsolatedCollection._inject_tenant_id`. No raw/unwrapped `_db` handle is used anywhere in this phase's code (unlike the background-scheduler risk class flagged elsewhere in this project's history) — this phase has no background scheduler at all, by design (see Pattern 4 rationale under Criterion 1).
- **Router registration:** `itam_license_endpoints`, `itam_consumable_endpoints`, `itam_component_endpoints` (both `router` and the new `asset_components_router`) all confirmed registered in `router_registry.py`. `python -c "import app"` succeeds cleanly from `backend/` (the real launcher's cwd) — the `backend.`-vs-bare import-path class of bug that broke this exact set of routers in production before (`95ab0d7`) does not reproduce.
- **Full backend suite:** 1831 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity` — confirmed identical to the documented project baseline, unrelated to ITAM), no regressions. `test_graphql.py` excluded per its documented pre-existing collection error.
- **CLAUDE.md 500-line limit:** all Phase 60 files checked — `itam_license_service.py` (155 lines), `itam_license_endpoints.py` (~145 lines), `itam_consumable_service.py` (~157 lines), `itam_consumable_endpoints.py` (123 lines), `itam_component_service.py` (~155 lines), `itam_component_endpoints.py` (~65 lines) — all well under the cap.

## Human Verification Required

None required to pass this phase — every success criterion has a fully automated test path. Two items are inherent to unit/integration testing rather than phase-specific gaps, consistent with how prior ITAM phases (56/57/59) have handled the same limitation:

1. **Real-database concurrency behavior** for the seat-assignment race documented above — mocked tests cannot exercise true concurrent Mongo access; only a load test against a real replica set would.
2. **Live UI round trip** — this phase is backend/API-only by design (D-01, matching the Phase 57/58/59 precedent); Phase 61 is the sole frontend consumer and will need its own verification pass once built.

## Gaps Summary

Three real gaps found and fixed this session (1 correctness bug on real Mongo, 2 missing-requirement-coverage items against ROADMAP's own success-criteria wording), plus a fourth (checkout/checkin test-coverage gap) closed alongside them. One gap intentionally left open and documented (seat-assignment race condition — accepted, low-severity, pre-existing, in-code-flagged). One further gap flagged but not fixed (missing single-component CRUD routes — out of this phase's required scope). All 3 ROADMAP success criteria are now verified against live code and live test runs, not merely against the fact that files exist on disk.

---

*Verified: 2026-08-09*
*Verifier: Claude*
