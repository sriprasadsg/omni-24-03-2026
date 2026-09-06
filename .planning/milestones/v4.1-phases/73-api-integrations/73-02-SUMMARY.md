---
phase: 73-api-integrations
plan: 02
subsystem: api
tags: [fastapi, webhooks, itam, asyncio, event-dispatch]

# Dependency graph
requires:
  - phase: 73-01 (ITAM-API-02)
    provides: itam_webhook_events.py's 8 event-type constants, the module-level _webhook_service singleton + asyncio.create_task dispatch pattern established on checkout_asset
provides:
  - asset.checked_in dispatch from checkin_asset, mirroring checkout_asset's payload shape key-for-key
  - consumable.low_stock dispatch from ConsumableService.checkout_consumable, gated by a new _is_low_stock(available, threshold) helper that imports (never redefines) itam_reporting_prebuilt.DEFAULT_LOW_STOCK_QUANTITY
  - asset.request_approved / asset.request_denied dispatch from ItamAssetRequestService.approve_asset_request / reject_asset_request
affects: [73-03, 73-04, 73-05, 73-06]

tech-stack:
  added: []
  patterns:
    - "Deferred (call-time, not module-top-level) cross-module import to break a circular-import risk: itam_consumable_service imports itam_reporting_prebuilt.DEFAULT_LOW_STOCK_QUANTITY inside _is_low_stock's function body, not at module top level, since itam_reporting_prebuilt imports from several itam_*_endpoints modules"
    - "Webhook payload built from the raw find_one_and_update result dict, never the validated Pydantic response model, when that model's extra=\"ignore\" config would silently drop fields a future plan adds (asset-request payload)"
    - "Gated slow-trigger_webhook test pattern (asyncio.Event released only after asserting the HTTP/service call already returned) as the proof technique for 'dispatch never blocks the caller', reused across all three call sites"

key-files:
  created:
    - backend/tests/test_itam_webhook_events.py
  modified:
    - backend/itam_lifecycle_endpoints.py
    - backend/itam_consumable_service.py
    - backend/itam_asset_request_service.py

key-decisions:
  - "_is_low_stock's DEFAULT_LOW_STOCK_QUANTITY import is deferred to call time inside the function body rather than hoisted to module top level, specifically to avoid a circular import (itam_reporting_prebuilt.py imports itam_lifecycle_endpoints and itam_license_endpoints, and itam_consumable_service is itself imported by itam_consumable_endpoints which several routers pull in) — confirmed clean via a real `cd backend && venv/bin/python -c \"import app\"` run after each task, not by reasoning alone"
  - "asset-request webhook payloads build from the raw `result` dict returned by find_one_and_update, not `AssetRequest.model_validate(result)` — that model's `model_config = ConfigDict(extra=\"ignore\")` would silently strip any field a later plan (73-04's ticket_ref) adds to the document before this plan's payload builder ever sees it"

patterns-established:
  - "Pattern 3: a threshold/heuristic value with an existing single source of truth (DEFAULT_LOW_STOCK_QUANTITY) is always imported by the new call site, never restated as a local constant, even at the cost of a deferred import to dodge a circular dependency"

requirements-completed: [ITAM-API-02]

coverage:
  - id: D1
    description: "Checking an asset back in dispatches asset.checked_in with a before/after diff over lifecycleStatus/assignedToType/assignedToId, mirroring checkout_asset's payload shape"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestLifecycleCheckinWebhook -k lifecycle (5 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A check-in that fails its guard (asset not found, or not currently checked out) dispatches nothing"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::TestLifecycleCheckinWebhook::test_lifecycle_checkin_not_found_dispatches_nothing, ::test_lifecycle_checkin_not_deployed_dispatches_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "Consumable checkout fires consumable.low_stock only when the post-decrement quantity is at or below the effective threshold (configured, including zero, or the shared DEFAULT_LOW_STOCK_QUANTITY default) — never firing when it isn't"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py -k low_stock (10 tests: 5 pure _is_low_stock cases + 5 checkout-integration cases)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approving an asset request dispatches asset.request_approved and rejecting one dispatches asset.request_denied, each with the flat request record; a non-pending request dispatches nothing on either path"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py -k asset_request (5 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No dispatch at any of the three new call sites is awaited inline — a stalled subscriber can never delay the check-in, consumable-checkout, or approve/reject HTTP response"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_webhook_events.py::test_lifecycle_checkin_dispatch_is_not_awaited_inline, ::test_asset_request_approve_dispatch_never_blocks_return (both use a gated-forever trigger_webhook stand-in)"
        status: pass
    human_judgment: false
  - id: D6
    description: "No pre-existing ITAM test suite (consumable, lifecycle, asset-request, api-integrations) regressed; the full backend suite has no new failures beyond the documented pre-existing baseline"
    requirement: "ITAM-API-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_consumable.py, test_itam_lifecycle.py, test_itam_lifecycle_expansion.py, test_itam_asset_request_service.py, test_itam_asset_request_endpoints.py, test_itam_api_integrations.py (78 tests, all green); full backend suite 2329 passed / 34 skipped / 12 pre-existing unrelated failures"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-08-18
status: complete
---

# Phase 73 Plan 02: ITAM-API-02 Request-Scoped Webhook Expansion Summary

**Five request-scoped ITAM webhook events now fire from their real mutation points — plan 73-01's tracer proved `asset.checked_out`; this plan adds `asset.checked_in`, `consumable.low_stock` (report-consistent threshold rule), and `asset.request_approved`/`asset.request_denied` — all fire-and-forget via `asyncio.create_task`, none awaited inline.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-08-18
- **Tasks:** 3/3
- **Files modified:** 3 production files, 1 new test file (470 lines, 20 tests)

## Accomplishments

- `itam_lifecycle_endpoints.checkin_asset` now dispatches `EVENT_ASSET_CHECKED_IN` immediately after `invalidate_cache("assets:*")`, mirroring `checkout_asset`'s payload shape key-for-key (`assetId`, `before`/`after` over `lifecycleStatus`/`assignedToType`/`assignedToId`, plus `checkedInAt`/`checkedInBy` in `after`, plus the full post-state `asset`). Reuses the existing module-level `_webhook_service` singleton — no duplicate `WebhookService()` instance.
- `itam_consumable_service.py` gets a new pure-function `_is_low_stock(available, threshold)` expressing the exact rule `itam_reporting_prebuilt.py`'s `low_stock_consumables` report already applies (configured threshold, including an explicit 0, wins; otherwise falls back to the shared `DEFAULT_LOW_STOCK_QUANTITY`, imported at call time to sidestep a circular import). `checkout_consumable` evaluates the post-decrement document `find_one_and_update` returns and, when low, dispatches `EVENT_CONSUMABLE_LOW_STOCK` with `consumableId`/`name`/`availableQuantity`/`reorderThreshold` (the effective threshold actually applied).
- `itam_asset_request_service.py`'s `approve_asset_request`/`reject_asset_request` each dispatch their respective D-05 event (`EVENT_ASSET_REQUEST_APPROVED` / `EVENT_ASSET_REQUEST_DENIED`) after the existing `send_asset_request_notification` call, built from the raw `find_one_and_update` result (not the `extra="ignore"`-configured `AssetRequest` model) with datetime fields ISO-8601-serialized via a small `_isoformat` helper. The deliberate asymmetry between the internal `"rejected"` status value and the outward `asset.request_denied` event name is preserved, not "corrected."
- 20 new tests in `backend/tests/test_itam_webhook_events.py` (this plan's new module), selectable via `-k lifecycle` (5), `-k low_stock` (10), `-k asset_request` (5) — including three dedicated "dispatch never blocks the caller" proofs using a gated-forever `trigger_webhook` stand-in (`asyncio.Event` released only after the response/return-value assertion already passed).

## Task Commits

1. **Task 1: asset.checked_in dispatch, mirrored from the proven check-out slice** - `6a486f883` (feat)
2. **Task 2: consumable.low_stock dispatch using the report's own threshold rule** - `746d2b68e` (feat)
3. **Task 3: asset.request_approved and asset.request_denied dispatch** - `e194c1032` (feat)

## Files Created/Modified

- `backend/itam_lifecycle_endpoints.py` — `checkin_asset` fires `asset.checked_in` via `asyncio.create_task`, imports `EVENT_ASSET_CHECKED_IN` alongside the existing `EVENT_ASSET_CHECKED_OUT`
- `backend/itam_consumable_service.py` — new `_is_low_stock` helper, new module-level `_webhook_service` singleton, `checkout_consumable` dispatches `consumable.low_stock` when crossing the threshold
- `backend/itam_asset_request_service.py` — new `_isoformat`/`_request_webhook_payload` helpers, new module-level `_webhook_service` singleton, `approve_asset_request`/`reject_asset_request` each dispatch their event
- `backend/tests/test_itam_webhook_events.py` (new, 470 lines) — the full ITAM-API-02 request-scoped regression suite

## Decisions Made

- **`DEFAULT_LOW_STOCK_QUANTITY` is imported inside `_is_low_stock`'s function body, not at `itam_consumable_service.py`'s module top level.** `itam_reporting_prebuilt.py` imports from `itam_lifecycle_endpoints` and `itam_license_endpoints`; a top-level import in `itam_consumable_service.py` risked introducing a circular import at app startup. Confirmed clean by actually running `cd backend && venv/bin/python -c "import app"` after this task landed (per the plan's own instruction — "confirm the choice with a real import app run, not by reasoning") rather than assuming the deferred import was sufficient.
- **Asset-request webhook payloads are built from the raw `find_one_and_update` result dict, not `AssetRequest.model_validate(result)`.** `AssetRequest`'s `model_config = ConfigDict(extra="ignore")` silently drops any field not declared on the model — including the `ticket_ref` field plan 73-04 is expected to add to these documents later in this phase. Building from the raw dict means this call site never needs to change when that field lands.

## Deviations from Plan

None — plan executed exactly as written. The one acceptance-criterion grep quirk worth noting: `grep -c "WebhookService()" backend/itam_lifecycle_endpoints.py` returns 2, not 1, because plan 73-01's own explanatory comment above the singleton (`# WebhookService() instance shape. Task 1 wires...`) also contains the literal string `WebhookService()` — the actual instantiation count is still exactly 1 (verified by `grep -n`, not just `-c`), so there is no duplicate instance; this is a pre-existing comment-text artifact from 73-01, not something this plan introduced or needs to fix.

## Issues Encountered

- **`backend/itam_lifecycle_endpoints.py` was already 593 lines before this plan touched it** (over CLAUDE.md's 500-line cap), confirmed via `git show <pre-Task-1-commit>:backend/itam_lifecycle_endpoints.py | wc -l`. This plan's Task 1 change (mirroring `checkout_asset`'s dispatch block onto `checkin_asset`) added ~23 lines, bringing it to 616. Splitting this router file is an architectural change outside this plan's scope (the plan's own file list designates it as a file to edit in place, not restructure) — logged here for visibility, not fixed. A future plan should consider extracting the checkout/checkin/audit routes or the overdue-audit report helpers into a sibling module.
- **Full backend suite has 12 pre-existing, unrelated failures** (`test_webhook_logic.py`'s 2 Jira/Zoho intent-parsing tests — require a live MongoDB connection this sandbox doesn't provide; `test_agentic_ai`, `test_e2e_integration`, `test_itam_audit.py`'s purchase-route 404 — already flagged as pre-existing in 73-01-SUMMARY.md the same session; `test_powershell_evidence.py` (2), `test_rust_heartbeat_parity.py`, `test_secret_manager_service.py`'s 4 Vault-client tests). None import or touch any of this plan's 3 modified files (confirmed via grep across all 12 failing test files). Not fixed — out of scope per this plan's `<verification>` no-*new*-failures contract.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Five of the eight D-05 event types now fire end-to-end from real ITAM mutations: `asset.checked_out` (73-01), `asset.checked_in`, `consumable.low_stock`, `asset.request_approved`, `asset.request_denied` (this plan). Remaining three (`asset.warranty_expiring`, `license.expiring_soon`, `asset.audit_overdue`) are background-sweep-triggered and belong to plans 73-03/73-05 per this plan's objective framing.
- The module-level `_webhook_service = WebhookService()` singleton pattern is now established in three separate modules (`itam_lifecycle_endpoints.py` from 73-01, `itam_consumable_service.py` and `itam_asset_request_service.py` new this plan) — later plans touching these same modules should reuse the existing instance, never construct a second one.
- No blockers.

---
*Phase: 73-api-integrations*
*Completed: 2026-08-18*

## Self-Check: PASSED
- FOUND: backend/tests/test_itam_webhook_events.py
- FOUND: .planning/phases/73-api-integrations/73-02-SUMMARY.md
- FOUND: commit 6a486f883
- FOUND: commit 746d2b68e
- FOUND: commit e194c1032
- FOUND: commit 9717c2c7a
