---
phase: 73-api-integrations
plan: 05
subsystem: api
tags: [fastapi, webhooks, itam, ticketing, asyncio, tenant-isolation, background-sweep]

# Dependency graph
requires:
  - phase: 73-03
    provides: itam_event_sweeps.py's _dispatch_tenant_scoped_event bracketing helper, the claim-then-act ordering convention, LICENSE_EXPIRY_* constants (module docstring precedent this plan follows)
  - phase: 73-04
    provides: ticketing_bridge.create_ticket_for_itam_event, ITAM_ENTITY_COLLECTIONS (asset/asset_request tenant-field mapping), the mechanical event_type -> ticket-type derivation
provides:
  - "itam_event_sweeps.run_audit_overdue_alert_pass(db) — the asset.audit_overdue webhook event's only producer, built on itam_lifecycle_endpoints's own _overdue_query/_overdue_row/_audit_cutoff_iso (never a re-expressed definition), plus D-10's first automatic ticket trigger from the same pass"
  - "itam_event_sweeps.run_stuck_approval_ticket_pass(db) — D-10's second automatic ticket trigger: a pending high-value asset request stuck past STUCK_APPROVAL_WINDOW_DAYS, ticket-only (no webhook event, per D-05)"
  - "itam_event_sweeps.start_itam_event_sweep_scheduler(db) — the one daily scheduler both new sweeps ride, registered in app_startup.py"
  - "itam_event_sweeps._is_high_value_request(request) — cost-or-quantity high-value classification, with quantity as the fallback that actually fires against real (cost-less) request documents"
  - "itam_models.AssetRequestBase.estimated_cost — additive, optional, cost field the high-value classification's cost arm needs (did not exist before this plan)"
affects: []

tech-stack:
  added: []
  patterns:
    - "A sweep never re-expresses a query/row-shaping definition that already exists on a request-time report route — it imports the report route's own helper functions (deferred, inside the function body) so the two can never drift. This plan's audit-overdue sweep imports itam_lifecycle_endpoints._overdue_query/_overdue_row/_audit_cutoff_iso verbatim, mirroring itam_reporting_prebuilt.py's own precedent for the identical import."
    - "Both new sweeps in this module use claim-then-act ordering (find_one_and_update's own filter carries the marker-absent condition, checked before any dispatch/ticket call) — the claim IS the concurrency guard, per this module's own docstring note from 73-03. Neither sweep uses the warranty sweep's dispatch-then-mark order."
    - "A background-sweep ticket trigger creates a ticket by calling ticketing_bridge.create_ticket_for_itam_event with a raw db handle, the caller's own entity_kind/tenant_id/event_type strings — zero changes needed to the bridge itself, exactly as 73-04's SUMMARY predicted."

key-files:
  created: []
  modified:
    - backend/itam_event_sweeps.py
    - backend/itam_models.py
    - backend/app_startup.py
    - backend/tests/test_itam_webhook_events.py
    - backend/tests/test_itam_ticketing_bridge.py
    - backend/tests/itam_webhook_events_test_support.py

key-decisions:
  - "STUCK_APPROVAL_TICKET_EVENT_TYPE (\"asset_request.stuck_approval\") is a local string constant in itam_event_sweeps.py, not a new EVENT_* constant in itam_webhook_events.py — D-05 defines no webhook event for a stuck approval, and this string exists solely to feed ticketing_bridge's mechanical type-derivation (itam_<event_type>), never dispatched as a webhook."
  - "Fixed constants chosen for the three previously-unspecified numeric thresholds (all fixed per the user's Open Question 3 resolution, none tenant-configurable): STUCK_APPROVAL_WINDOW_DAYS=7, HIGH_VALUE_REQUEST_COST=2000, HIGH_VALUE_REQUEST_QUANTITY=10. ITAM_EVENT_SWEEP_INTERVAL_SECONDS=86400 (a full day, deliberately not the warranty/licence job's hourly cadence)."
  - "Task 3's scheduler-registration test drives the real run_startup_services() startup path (not a source-only check) with asyncio.create_task patched to record and close each scheduled coroutine without running it, and the handful of directly-awaited (non-create_task) calls elsewhere in that function (self-healing migrations, response/XDR policy seeding, stream processor, knowledge-base/YARA seeding) stubbed to AsyncMocks so the test stays hermetic — no live MongoDB dependency, consistent with every other test in this suite, while still exercising a real import and a real call into the new registration block."

patterns-established:
  - "Any future ITAM background-sweep ticket trigger creates its own local event-type string when D-05 defines no corresponding webhook event, rather than inventing an EVENT_* webhook constant that nothing ever dispatches."

requirements-completed: [ITAM-API-02, ITAM-API-03]

coverage:
  - id: D1
    description: "An asset crossing the physical-audit overdue threshold produces exactly one asset.audit_overdue webhook event and one automatic ticket-creation attempt per pass, using the overdue-audit report route's own _overdue_query/_overdue_row/_audit_cutoff_iso (imported, never re-expressed) — proven by a test comparing the sweep's selected asset id set to the report's own selected set over one shared fixture. A recent, disposed, or already-marked asset produces neither; a second pass over an unchanged fixture produces zero additional events/tickets; a lost concurrent claim skips the document without dispatching or ticketing; a ticket-creation failure never prevents the webhook or aborts the pass; a document with no tenant id is skipped entirely."
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestAuditOverdueWebhookAndTicketDispatch -k audit_overdue (10 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A pending high-value asset request left stuck beyond STUCK_APPROVAL_WINDOW_DAYS gets exactly one automatic ticket via create_ticket_for_itam_event, classified high-value by cost (>= HIGH_VALUE_REQUEST_COST) or, absent any cost field, by quantity (>= HIGH_VALUE_REQUEST_QUANTITY) — the quantity fallback exists because RESEARCH.md Assumption A2 was false (no request document anywhere carried a cost field before this plan). A low-value, too-young, non-pending, already-marked, or already-ticketed request produces nothing; a second pass over an unchanged fixture produces zero additional tickets; the claim filter uses the asset_requests collection's own snake_case tenant_id field."
    requirement: "ITAM-API-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_ticketing_bridge.py::TestAutomaticTicketTriggers -k automatic_trigger (12 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both new sweeps run on one daily scheduler (start_itam_event_sweep_scheduler, ITAM_EVENT_SWEEP_INTERVAL_SECONDS=86400) registered in app_startup.py immediately after the warranty scheduler block, in the identical try/except/_mdb.db shape — and the registration is proven by actually driving run_startup_services() with the scheduling primitive patched and asserting this scheduler's coroutine was scheduled, not merely that its name appears in the source (the Phase 59 defect class this task exists to prevent: a sweep installed but never registered, so it never starts in production)."
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestItamEventSweepSchedulerRegistration -k scheduler_registration (5 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No regression: all three phase test modules pass together, the full backend suite shows no new failures against the documented baseline, and cd backend && python -c 'import app' exits 0."
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "pytest backend/tests/test_itam_webhook_events.py backend/tests/test_itam_ticketing_bridge.py backend/tests/test_itam_api_integrations.py -q (122 passed); full suite 2416 passed / 34 skipped / 10 failed — identical to the 73-04 baseline set (test_agentic_ai, test_e2e_integration, test_itam_audit purchase-route, test_powershell_evidence x2, test_rust_heartbeat_parity, test_secret_manager_service x4), minus one non-deterministic test_mfa flake that did not reproduce this run; import app exits 0"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 05: Audit-Overdue Webhook + Both Automatic Ticket Triggers Summary

**`asset.audit_overdue` — the one D-05 event type that was purely a function of elapsed time and had no producer — now fires from a new daily background sweep built on the existing overdue-audit report's own query/row helpers, and both of D-10's automatic ticket triggers (audit-overdue asset, stuck high-value asset request) now create exactly one Jira/ServiceNow ticket per condition, unattended.**

## Performance

- **Duration:** ~55 min
- **Completed:** 2026-08-18
- **Tasks:** 3/3
- **Files modified:** 3 production files, 3 test files (no new files — all additions to existing 73-03/73-04 modules and their test files)

## Flagged Assumptions — restated with what was actually found

1. **RESEARCH.md Assumption A2 was false, confirmed.** Direct inspection of `backend/itam_models.py`'s pre-plan `AssetRequestBase`/`AssetRequestCreate`/`AssetRequest` confirmed no cost-style field existed anywhere on the asset-request model — only `item_description`, `quantity`, `reason`, plus identity/status/approval fields. A cost-only high-value filter would have matched zero requests in every existing tenant. Resolved per the plan's own instruction: added an additive, optional `estimated_cost` field (never required, absent by default) to `AssetRequestBase` (and, matching `AssetRequestUpdate`'s existing optional-field shape for `item_description`/`quantity`, to `AssetRequestUpdate` too), and `_is_high_value_request` classifies a request as high-value when `estimated_cost` is present and >= `HIGH_VALUE_REQUEST_COST` (2000), **or** when `quantity` >= `HIGH_VALUE_REQUEST_QUANTITY` (10) — the quantity arm is what makes the trigger reachable against real, cost-less data today.
2. **Edge-probe item ITAM-API-02 remains unresolved**, as flagged. Confirmed no test in this plan touches webhook delivery-time behavior (retry policy, ordering, subscriber back-pressure) — those remain owned by the pre-existing `webhook_service` dispatcher, reused unmodified.
3. **Edge-probe item ITAM-API-03 remains unresolved**, as flagged. Confirmed no test in this plan (or 73-04's) exercises real Jira/ServiceNow behavior on a duplicate, malformed, or rate-limited create call — the dedup guard and the non-re-raising failure contract bound the blast radius, but third-party behavior itself is untested.

## Accomplishments

- **Task 1 — `run_audit_overdue_alert_pass(db)`** (`backend/itam_event_sweeps.py`): imports `_audit_cutoff_iso`/`_overdue_query`/`_overdue_row` from `itam_lifecycle_endpoints` (deferred, inside the function body) and never re-expresses the overdue definition — a dedicated test proves the sweep's selected asset id set is identical to the report route's own selected set over one shared fixture. Claims each asset atomically (`find_one_and_update` with the marker-absent condition inside the filter) before dispatching `asset.audit_overdue` via `_dispatch_tenant_scoped_event` and creating an automatic ticket via `ticketing_bridge.create_ticket_for_itam_event` — each inside its own non-re-raising try/except, so a ticket failure never blocks the webhook or aborts the pass. A document with no `tenantId` is skipped entirely.
- **Task 2 — `run_stuck_approval_ticket_pass(db)`** (`backend/itam_event_sweeps.py`) plus `AssetRequestBase.estimated_cost`/`AssetRequestUpdate.estimated_cost` (`backend/itam_models.py`): finds pending asset requests older than `STUCK_APPROVAL_WINDOW_DAYS` (7) with the stuck-approval marker absent, filters to `_is_high_value_request` matches, claims atomically on the collection's own snake_case `tenant_id` field, and creates a ticket (no webhook — D-05 defines none for this condition) via the same `create_ticket_for_itam_event` orchestrator, using a local `STUCK_APPROVAL_TICKET_EVENT_TYPE` string rather than a new webhook constant.
- **Task 3 — `start_itam_event_sweep_scheduler(db)`**, registered in `backend/app_startup.py` immediately after the warranty scheduler block (identical try/except/`_mdb.db` shape): loops both new sweeps unconditionally every `ITAM_EVENT_SWEEP_INTERVAL_SECONDS` (86400 — a full day, distinct from the warranty job's hourly cadence). A dedicated test drives the real `run_startup_services()` startup path with `asyncio.create_task` patched (each scheduled coroutine recorded then closed without running, so none of the many unrelated background loops actually start) and asserts this scheduler's coroutine was genuinely scheduled — the Phase 59 defect class (a sweep fully implemented but never registered, so it would never start in production) this task exists to prevent. A source-only text-presence check is explicitly insufficient per this plan's own threat register (T-73-30) and was not relied on alone.

## Task Commits

Each task followed the RED (`test`) → GREEN (`feat`) TDD cycle for Tasks 1/2 (both `tdd="true"`); Task 3 has no `tdd` attribute and was implemented directly with its own registration test added in the same commit:

1. **Task 1: audit-overdue sweep**
   - `56cc2f23d` (test) — 10 failing tests, `ImportError` (function didn't exist)
   - `996e9f6ca` (feat) — `run_audit_overdue_alert_pass` + constants; all 10 pass
2. **Task 2: stuck high-value approval sweep**
   - `be4bd5b58` (test) — 12 tests, `ImportError` (function/field didn't exist) + `estimated_cost` field added
   - `e0553cf17` (feat) — `run_stuck_approval_ticket_pass` + `_is_high_value_request` + constants; all 12 pass
3. **Task 3: daily scheduler, registered at startup**
   - `5dffc1814` (feat) — `start_itam_event_sweep_scheduler` + `app_startup.py` registration + 5 registration tests; all pass

## Files Created/Modified

- `backend/itam_event_sweeps.py` — `AUDIT_OVERDUE_MARKER_FIELD`, `ITAM_EVENT_SWEEP_INTERVAL_SECONDS`, `STUCK_APPROVAL_MARKER_FIELD`, `STUCK_APPROVAL_WINDOW_DAYS`, `HIGH_VALUE_REQUEST_COST`, `HIGH_VALUE_REQUEST_QUANTITY`, `STUCK_APPROVAL_TICKET_EVENT_TYPE`, `run_audit_overdue_alert_pass`, `_is_high_value_request`, `run_stuck_approval_ticket_pass`, `start_itam_event_sweep_scheduler`
- `backend/itam_models.py` — `AssetRequestBase.estimated_cost` (optional, additive), `AssetRequestUpdate.estimated_cost` (optional, matching the existing update-field shape)
- `backend/app_startup.py` — one new registration block (`[ITAM] Event sweep scheduler started`) immediately after the warranty alert scheduler block
- `backend/tests/test_itam_webhook_events.py` — `TestAuditOverdueWebhookAndTicketDispatch` (10 tests, `-k audit_overdue`), `TestItamEventSweepSchedulerRegistration` (5 tests, `-k scheduler_registration`)
- `backend/tests/test_itam_ticketing_bridge.py` — `TestAutomaticTicketTriggers` (12 tests, `-k automatic_trigger`)
- `backend/tests/itam_webhook_events_test_support.py` — `_overdue_asset`/`_recent_asset` fixtures, `_matches_mongo_filter`, `_AuditOverdueAssetsCollection`, `_RawAuditOverdueSweepDb` (shared support, following 73-03's own precedent of splitting fixtures out of the main test file)

## Final values chosen for the flagged constants

| Constant | Value | Rationale |
|---|---|---|
| `AUDIT_OVERDUE_MARKER_FIELD` | `"auditOverdueAlertSentAt"` | mirrors `warrantyAlertSentAt` naming |
| `ITAM_EVENT_SWEEP_INTERVAL_SECONDS` | `86400` (1 day) | deliberately daily, not the warranty job's hourly cadence — the audit-overdue threshold is measured in a year |
| `STUCK_APPROVAL_MARKER_FIELD` | `"stuckApprovalTicketedAt"` | idempotency marker, same naming convention |
| `STUCK_APPROVAL_WINDOW_DAYS` | `7` | fixed constant, not tenant-configurable, per the user's Open Question 3 resolution |
| `HIGH_VALUE_REQUEST_COST` | `2000` | fixed constant |
| `HIGH_VALUE_REQUEST_QUANTITY` | `10` | fixed constant; the fallback that actually fires against real (cost-less) request data today |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written for all three tasks.

### Design decisions made within the plan's discretion

**1. Task 3's registration test drives `run_startup_services()` with the surrounding real-I/O calls stubbed, not against a live database.** The plan required proving the scheduler is "actually wired" via a test that "drives the real startup path with the scheduling primitive patched" and explicitly rejected a source-only check. `run_startup_services()` performs several directly-awaited (non-`create_task`) calls both before and after the new registration block (self-healing DB migrations, response/XDR policy seeding, the stream processor, knowledge-base/YARA seeding). A live local MongoDB was confirmed reachable in this environment, but calling those functions for real against the shared dev database was judged unnecessarily invasive for a unit test; instead they are stubbed to `AsyncMock()`s so the test remains hermetic (no live MongoDB dependency), consistent with every other test in this suite, while the registration block itself — the real import, the real call to `start_itam_event_sweep_scheduler`, the real (patched) `asyncio.create_task` — executes for real and is asserted on directly.

---

**Total deviations:** 0 auto-fixed; 1 documented design decision within the plan's discretion, not a deviation from any explicit instruction.

## Issues Encountered

None beyond normal TDD RED-phase test-authoring bugs (an argument-index mistake in one test's own assertion, fixed before the RED commit was made — not a deviation, a routine test-writing correction).

## User Setup Required

None — no external service configuration required. Ticket creation reuses the tenant's existing Jira/ServiceNow connection config (D-11, unchanged from 73-04).

## Next Phase Readiness

- **All eight D-05 event types now have a live producer.** `asset.checked_out` (73-01), `asset.checked_in`/`consumable.low_stock`/`asset.request_approved`/`asset.request_denied` (73-02), `asset.warranty_expiring`/`license.expiring_soon` (73-03), `asset.audit_overdue` (this plan).
- **Both of D-10's automatic ticket triggers now exist and create exactly one ticket per condition**, unattended, through the tenant's existing Jira/ServiceNow connection — closing the gap 73-04 deliberately left open ("plan 73-05's still-undefined 'stuck approval' event type... zero changes needed to this adapter", now resolved as `STUCK_APPROVAL_TICKET_EVENT_TYPE`).
- ROADMAP success criterion 2 ("User can configure webhooks to trigger events") and success criterion 3's automatic half are both fully met.
- Plan 73-06 (already executed, wave 3) built the manual row-action UI and the webhook event picker against 73-04's ticket-reference fields and 73-01/02/03's event constants — this plan adds no new frontend-visible surface (`asset.audit_overdue` was already in 73-01's event constant list and 73-06's picker; this plan only makes it actually fire).
- No blockers. This was the final plan of Phase 73 (wave 4, no downstream dependents).

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*
