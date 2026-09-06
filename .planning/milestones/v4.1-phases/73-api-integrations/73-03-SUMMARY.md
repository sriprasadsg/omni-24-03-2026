---
phase: 73-api-integrations
plan: 03
subsystem: api
tags: [fastapi, webhooks, itam, asyncio, tenant-isolation, background-sweep]

# Dependency graph
requires:
  - phase: 73-02 (ITAM-API-02)
    provides: itam_webhook_events.py's 8 event-type constants, the module-level _webhook_service singleton + trigger_webhook dispatch pattern, backend/tests/test_itam_webhook_events.py's initial 3 test classes
provides:
  - asset.warranty_expiring dispatch wired into itam_finance_service.run_warranty_alert_pass's existing per-asset loop, individually tenant-bracketed
  - backend/itam_event_sweeps.py — new module holding license.expiring_soon's run_license_expiry_alert_pass(db) and the shared _dispatch_tenant_scoped_event(tenant_id, event_type, payload) bracketing helper every future ITAM background sweep (Plan 73-05) must dispatch through
  - licence-expiry sweep riding itam_finance_service.start_warranty_alert_scheduler's existing loop (no new scheduler registered — D-08)
  - the tenant_context_background regression proving both sweeps deliver each tenant's events only under that tenant's ambient context, and never leak context after a pass returns
affects: [73-05, 73-06]

tech-stack:
  added: []
  patterns:
    - "Per-document set_tenant_id/reset_tenant_id bracketing around a single background-sweep webhook dispatch, never batch-bracketed across a whole pass — the bracket brackets exactly the trigger_webhook call, nothing more, so no other code inside the loop iteration ever runs under an incorrect ambient tenant"
    - "Claim-then-dispatch ordering (find_one_and_update's own filter carries the marker-absent condition) for a sweep whose concurrency guard IS the claim, versus dispatch-then-mark ordering for a sweep whose marker instead bounds a misconfigured-subscriber retry storm — itam_event_sweeps.py's module docstring records which ordering to pick and why"
    - "_dispatch_tenant_scoped_event(tenant_id, event_type, payload) as the single tenant-bracketing chokepoint every sweep in a module dispatches through, so a new call site can never forget the bracket — deliberately not an event-dispatch abstraction layer (D-07): no routing, no registry, just the tenant-context guard around one trigger_webhook call"

key-files:
  created:
    - backend/itam_event_sweeps.py
    - backend/tests/itam_webhook_events_test_support.py
  modified:
    - backend/itam_finance_service.py
    - backend/tests/test_itam_webhook_events.py

key-decisions:
  - "The warranty sweep's webhook dispatch is awaited inline inside the tenant-context bracket (not scheduled via asyncio.create_task, unlike the request-scoped call sites 73-02 built) — a background loop has no HTTP response to protect, and awaiting keeps the dispatch inside the window where the tenant context is guaranteed correct; scheduling it would let the bracket's finally reset the tenant before the scheduled task actually ran."
  - "run_license_expiry_alert_pass claims a licence (find_one_and_update with the marker-absent condition inside the same filter) BEFORE dispatching, the opposite of run_warranty_alert_pass's dispatch-then-mark order. The warranty sweep marks unconditionally after delivery to bound a permanently misconfigured subscriber's retry storm; the licence sweep's claim IS the concurrency guard against two overlapping passes double-firing the same licence, so it must happen first. Documented in itam_event_sweeps.py's module docstring for Plan 73-05 to follow."
  - "_enrich_license_seats_and_expiry is imported inside run_license_expiry_alert_pass's function body, not at itam_event_sweeps.py's module top level, following itam_reporting_prebuilt.py's own precedent for importing that same helper — avoids an import cycle at application startup (itam_license_endpoints.py sits behind several routers)."

patterns-established:
  - "Pattern: a background sweep's webhook dispatch is bracketed exactly around the single trigger_webhook call via a small shared helper, never around the whole loop iteration or the whole pass — subsequent ITAM sweeps (Plan 73-05) should call itam_event_sweeps._dispatch_tenant_scoped_event rather than re-deriving the bracket."

requirements-completed: [ITAM-API-02]

coverage:
  - id: D1
    description: "asset.warranty_expiring dispatches exactly once per expiring/expired asset from the existing warranty sweep, bracketed with the swept asset's own tenant id, restored after (including when the dispatch raises); active assets and already-marked assets dispatch nothing; the payload carries only assetId/assetTag/warrantyStatus/warrantyExpiresAt"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestWarrantyExpiringWebhookDispatch -k warranty_expiring (7 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "license.expiring_soon dispatches exactly once per in-window or already-expired licence via a new run_license_expiry_alert_pass sweep, atomically claimed (marker-absent condition inside the update filter) so overlapping passes cannot double-fire; a licence with no expiry date or no tenant id, or beyond the window, dispatches nothing; a licence with no tenant id is never written to"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestLicenseExpiringWebhookDispatch -k license_expiring (11 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The licence sweep is driven by the existing warranty scheduler loop (start_warranty_alert_scheduler awaits run_license_expiry_alert_pass each cycle) with no new job registered in application startup — D-08 held"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "grep -c \"run_license_expiry_alert_pass\" backend/itam_finance_service.py returns 2; git diff --name-only -- backend/app_startup.py prints nothing for this plan's commits"
        status: pass
    human_judgment: false
  - id: D4
    description: "A mixed-tenant sweep (2 tenants x 2 alertable documents each, for both the warranty and licence sweeps) delivers each tenant's events only under that tenant's ambient context — no dispatch ever observes an empty/None/fail-closed-sentinel tenant id or another tenant's identifier in its payload — and the ambient tenant context is empty again after each pass returns"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestMixedTenantBackgroundDispatch -k tenant_context_background (3 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No regression to Phase 59/71 warranty tests, the full test_itam_webhook_events.py module, deferred-import cycle safety (import app), or the broader backend suite"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "pytest backend/tests/ -k 'warranty and not webhook' -q (76 passed); pytest backend/tests/test_itam_webhook_events.py -q (41 passed); cd backend && python -c 'import app' exits 0; full suite 2385 passed / 34 skipped / 10 pre-existing unrelated failures (identical to 73-02's documented baseline minus 2 live-mongo-only webhook_logic tests)"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 03: Warranty & Licence Expiry Webhook Sweeps Summary

**`asset.warranty_expiring` and `license.expiring_soon` now dispatch correctly from background sweeps under explicit per-document tenant context — the two window-crossing D-05 events that would otherwise appear in the subscription picker and silently never fire.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-08-18
- **Tasks:** 3/3
- **Files modified:** 2 production files (1 new), 2 test files (1 new)

## Accomplishments

- `itam_finance_service.run_warranty_alert_pass` gained a third, independently-isolated delivery path inside its existing per-asset loop: `EVENT_ASSET_WARRANTY_EXPIRING` is dispatched via a new module-level `_webhook_service = WebhookService()`, bracketed with `set_tenant_id(tenant_id)`/`reset_tenant_id(token)` around the asset's own tenant id, awaited inline (not scheduled — a background loop has no response to protect and awaiting keeps the dispatch inside the correct-context window). A dispatch failure is logged and never aborts the sweep; the marker write and the two existing notification paths still occur unconditionally.
- New `backend/itam_event_sweeps.py` holds `run_license_expiry_alert_pass(db)`: a structural clone of the warranty sweep that finds licences with an expiry date and no `licenseExpiryAlertSentAt` marker, computes expiry via `itam_license_endpoints._enrich_license_seats_and_expiry` (deferred import, following `itam_reporting_prebuilt.py`'s own precedent), and — for licences at or inside the 30-day `LICENSE_EXPIRY_ALERT_WINDOW_DAYS` window (including already-expired) — atomically claims the licence via `find_one_and_update` with the marker-absent condition inside the same filter, then dispatches `EVENT_LICENSE_EXPIRING_SOON` through a new shared `_dispatch_tenant_scoped_event(tenant_id, event_type, payload)` helper every sweep in this module (including Plan 73-05's future ones) must route through.
- `start_warranty_alert_scheduler` now awaits `run_license_expiry_alert_pass(db)` each cycle (deferred import inside the function body) — no new scheduler registered in `app_startup.py`, satisfying D-08 literally.
- A dedicated mixed-tenant regression (`TestMixedTenantBackgroundDispatch`, 3 tests) drives both sweeps over a fixture spanning 2 tenants x 2 alertable documents each, recording the ambient tenant id at every dispatch and asserting it always matches the swept document's own tenant, never the fail-closed sentinel, and is empty again once each pass returns.
- 22 new tests added to `backend/tests/test_itam_webhook_events.py` (7 `-k warranty_expiring`, 11 `-k license_expiring`, 3 `-k tenant_context_background`, plus 1 payload-shape assertion folded into each set), all following this plan's own TDD instruction (tests written first, confirmed RED via `ModuleNotFoundError`/`AssertionError`, then implementation added to reach GREEN).
- Shared background-sweep test fixtures (`_expiring_asset`, `_mock_now_2026_08_15`, `_license`, `_RawLicenseSweepDb`, `_mock_license_now_2026_08_15`, `FAIL_CLOSED_TENANT_SENTINEL`) extracted into a new `backend/tests/itam_webhook_events_test_support.py`, mirroring `itam_finance_sweep_test_support.py`'s precedent for the 59-04 warranty sweep tests.

## Task Commits

1. **Task 1: asset.warranty_expiring, dispatched under explicit tenant context** - `a2cf5e868` (feat)
2. **Task 2: licence expiry sweep riding the existing scheduler** - `67e14a570` (feat)
3. **Task 3: Mixed-tenant background dispatch regression** - `c53169a9b` (test)

## Files Created/Modified

- `backend/itam_finance_service.py` — third delivery path (`asset.warranty_expiring`, tenant-bracketed) added to `run_warranty_alert_pass`'s loop; `start_warranty_alert_scheduler` now also drives `run_license_expiry_alert_pass` each cycle
- `backend/itam_event_sweeps.py` (new, 174 lines) — `run_license_expiry_alert_pass`, `_dispatch_tenant_scoped_event`, `LICENSE_EXPIRY_ALERT_WINDOW_DAYS`, `LICENSE_EXPIRY_MARKER_FIELD`
- `backend/tests/test_itam_webhook_events.py` — 22 new tests across 3 new test classes (`TestWarrantyExpiringWebhookDispatch`, `TestLicenseExpiringWebhookDispatch`, `TestMixedTenantBackgroundDispatch`)
- `backend/tests/itam_webhook_events_test_support.py` (new, 110 lines) — shared sweep-fixture stubs, extracted per this plan's own Task 3 file-size fallback

## Decisions Made

- **The webhook dispatch inside `run_warranty_alert_pass` is awaited inline, inside the `set_tenant_id`/`reset_tenant_id` bracket, rather than scheduled via `asyncio.create_task`** like the request-scoped call sites 73-01/73-02 built. A background sweep has no HTTP response to protect from a slow subscriber, and scheduling the dispatch would let the bracket's `finally` reset the ambient tenant before the scheduled task actually executes — silently reproducing exactly the failure this plan exists to prevent.
- **`run_license_expiry_alert_pass` claims before it dispatches** (`find_one_and_update`'s own filter carries the marker-absent condition), the reverse of the warranty sweep's dispatch-then-mark order. The warranty sweep's unconditional post-delivery marker exists to bound a permanently misconfigured subscriber's retry storm; the licence sweep's claim step is itself the concurrency guard against two overlapping passes double-firing the same licence, so it must run first. This divergence is recorded in `itam_event_sweeps.py`'s module docstring specifically so Plan 73-05 picks the same claim-then-act ordering for its own new sweeps rather than copying the warranty sweep's order by habit.
- **`_dispatch_tenant_scoped_event` is the one bracketing chokepoint every sweep in `itam_event_sweeps.py` dispatches through** — both this plan's licence sweep and Plan 73-05's two future sweeps. It is deliberately not an event-dispatch abstraction layer under D-07 (no routing, no event registry, no indirection about which event fires where) — it is a tenant-context guard wrapped around one `trigger_webhook` call, existing solely so a new call site cannot forget the bracket.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written for both `itam_finance_service.py` and `itam_event_sweeps.py`.

### Accepted CLAUDE.md deviation

**1. [CLAUDE.md 500-line guideline] `backend/tests/test_itam_webhook_events.py` remains at 870 lines after the Task 3 fixture extraction.**
- **Found during:** Task 3, while implementing the plan's own explicit file-size fallback ("if it would exceed [500 lines], extract the shared sweep fixtures into `backend/tests/itam_webhook_events_test_support.py`").
- **Issue:** Every shared, non-test-logic fixture this plan's three tasks use (`_expiring_asset`, `_mock_now_2026_08_15`, `_license`, `_LicensesCollection`, `_RawLicenseSweepDb`, `_mock_license_now_2026_08_15`) was extracted into the new support module, per the plan's own instruction — but the file still sits at 870 lines because the actual test *methods* (41 total, spanning this plan's 3 new classes plus 73-02's original 3) cannot themselves be moved out: this plan's own `<verify>` blocks pin every `-k warranty_expiring` / `-k license_expiring` / `-k tenant_context_background` command to the literal path `backend/tests/test_itam_webhook_events.py`, so relocating any test class into a second `test_*.py` file would break the plan's own verification contract.
- **Fix:** Extracted the full extent of what the plan's fallback authorizes (all shared stubs/fixtures/helpers); left test classes in place since the plan's own `<verify>` commands require it. Documented here per the CLAUDE.md-enforcement instruction to record any CLAUDE.md-driven adjustment that could not be fully resolved.
- **Files modified:** `backend/tests/test_itam_webhook_events.py`, `backend/tests/itam_webhook_events_test_support.py`
- **Verification:** Support module confirmed at 110 lines (well under the cap); main test file confirmed still green at 870 lines (41/41 tests passing) after the extraction — no functional regression, only an unresolved size overage inherent to the plan's own file-pinning design.
- **Committed in:** `c53169a9b` (Task 3 commit)

---

**Total deviations:** 1 documented, unresolved (structural — inherent to the plan's own verify-command design, not a code defect)
**Impact on plan:** No functional impact. The overage is test-file-only (production code — `itam_finance_service.py` at 470 lines, `itam_event_sweeps.py` at 174 lines — both comfortably under the cap).

## Issues Encountered

None beyond the file-size item documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Seven of the eight D-05 event types now deliver end-to-end: `asset.checked_out` (73-01), `asset.checked_in`/`consumable.low_stock`/`asset.request_approved`/`asset.request_denied` (73-02), `asset.warranty_expiring`/`license.expiring_soon` (this plan). The remaining `asset.audit_overdue` is Plan 73-05's scope.
- `backend/itam_event_sweeps.py` and its `_dispatch_tenant_scoped_event` helper are now the established substrate for Plan 73-05's `run_audit_overdue_alert_pass`/`run_stuck_approval_ticket_pass`/`start_itam_event_sweep_scheduler` — those sweeps should dispatch through the same helper and choose the claim-then-act ordering this plan's docstring documents, not the warranty sweep's dispatch-then-mark ordering.
- No blockers.

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*

## Self-Check: PASSED
- FOUND: backend/itam_finance_service.py
- FOUND: backend/itam_event_sweeps.py
- FOUND: backend/tests/test_itam_webhook_events.py
- FOUND: backend/tests/itam_webhook_events_test_support.py
- FOUND: commit a2cf5e868
- FOUND: commit 67e14a570
- FOUND: commit c53169a9b
