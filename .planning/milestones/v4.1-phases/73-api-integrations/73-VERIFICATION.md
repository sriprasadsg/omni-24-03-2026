---
phase: 73-api-integrations
verified: 2026-08-19T00:00:00Z
status: human_needed
score: 24/26 must-haves verified
behavior_unverified: 1
overrides_applied: 0
human_verification:

  - test: "Fire two concurrent API-key-authenticated ITAM requests from two different tenants (e.g. two overlapping asset-checkout calls) and confirm neither request's audit log / tenant-scoped write ever shows the other tenant's id."
    expected: "Each request's `get_current_user_or_api_key` -> `set_tenant_id` call is isolated to its own asyncio task; no cross-tenant contamination is observable in the resulting documents or logs."
    why_human: "This is a state-isolation invariant (contextvar scoping across concurrent asyncio tasks). Code inspection confirms `set_tenant_id(token_data.tenant_id)` is called per-request inside `get_current_user_or_api_key` (backend/api_key_auth.py:257-284), which relies on Python's per-task ContextVar copy semantics, but no test in `backend/tests/test_itam_api_integrations.py` (or elsewhere in the 122-test phase suite) issues two concurrent requests from different tenants and asserts non-contamination. Presence and wiring are confirmed; the concurrency guarantee itself is unexercised by any test."

  - test: "At a narrow viewport width, open the ticket-provider-choice dropdown on a LifecyclePanel or RequestsPanel row (with both Jira and ServiceNow configured) and confirm the dropdown stays fully on-screen and readable against the table's right edge."
    expected: "Dropdown does not clip off-screen or become unreadable at narrow widths."
    why_human: "Marked `verification: backstop` in 73-06-PLAN.md must_haves — an explicitly visual/responsive-layout claim that static analysis cannot confirm."

  - test: "Create a ticket whose provider-issued reference is unusually long (e.g. a long ServiceNow sys_id or Jira key) and confirm the LifecyclePanel/RequestsPanel row layout does not break."
    expected: "Row layout remains intact; long reference text wraps/truncates without breaking the table."
    why_human: "Marked `verification: backstop` in 73-06-PLAN.md must_haves — a visual layout claim requiring rendered-page inspection."
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  status: human_needed
---

# Phase 73: API & Integrations Verification Report

**Phase Goal:** Extend ITAM capabilities via REST API and external system integrations.
**Success Criteria:** (1) User can use REST API to perform ITAM operations. (2) User can configure webhooks to trigger events. (3) User can integrate with Jira and ServiceNow.
**Verified:** 2026-08-19
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | API key with `manage:assets` scope can perform ITAM write op (asset checkout) previously requiring browser session | ✓ VERIFIED | `backend/itam_asset_endpoints.py:38-65` dual-auth `_require_itam_admin`; test `test_tracer_api_key_checkout_fires_webhook` passes |
| 2 | API key scoped to `read:assets` gets 403 on write op even if owning user has admin role | ✓ VERIFIED | `_scopes_allow` narrowing (`backend/rbac_service.py:179-197`); tests `test_scope_narrowing_enforced_*` pass |
| 3 | Existing JWT session callers keep working unchanged on every `_require_itam_admin`-gated route | ✓ VERIFIED | `test_session_auth_still_works` passes; `scopes=None` bypasses narrowing (`rbac_service.py:194-196`) |
| 4 | LDAP/SSO/user-mgmt/API-key-mgmt routes stay session-auth-only, never reachable by API key | ✓ VERIFIED | All four modules import `_require_itam_admin_session_only as _require_itam_admin` (`ldap_endpoints.py:24`, `sso_endpoints.py:22`, `user_endpoints.py:16`, `api_key_endpoints.py:22`); tests `test_excluded_surfaces_*` pass |
| 5 | `manage:assets` is an issuable scope when creating an API key | ✓ VERIFIED | `AVAILABLE_SCOPES["manage:assets"]` (`api_key_auth.py:53`), consumed by `api_key_endpoints.py:40,88` |
| 6 | Per-key rate limiter (429) still applies on ITAM routes; no new ITAM-specific tier | ✓ VERIFIED | `test_rate_limit_429_via_itam_route` passes |
| 7 | Successful checkout dispatches `asset.checked_out` webhook without blocking the HTTP response | ✓ VERIFIED | `asyncio.create_task(_webhook_service.trigger_webhook(...))` (`itam_lifecycle_endpoints.py:230`); tracer test passes |
| 8 | Two concurrent API-key-authenticated ITAM requests never cross-contaminate tenant context (contextvar scoped per request task) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `set_tenant_id` called per-request in `get_current_user_or_api_key` (`api_key_auth.py:262,281`) — present and wired, but no test issues concurrent requests from two tenants to prove isolation. See Human Verification. |
| 9 | The eight ITAM webhook event-type strings exist in exactly one place | ✓ VERIFIED | `backend/itam_webhook_events.py` — single constants module, imported everywhere else |
| 10 | Check-in dispatches `asset.checked_in` with before/after diff, not awaited inline | ✓ VERIFIED | `itam_lifecycle_endpoints.py:364`; tests `test_lifecycle_checkin_*` (incl. `_not_awaited_inline`) pass |
| 11 | Consumable checkout dispatches `consumable.low_stock` per threshold rule matching the low-stock report | ✓ VERIFIED | `itam_consumable_service.py:171`; tests `test_low_stock_*` pass |
| 12 | Approve/reject dispatch `asset.request_approved`/`asset.request_denied`, not awaited | ✓ VERIFIED | `itam_asset_request_service.py:166-209`; tests `test_asset_request_approve/reject_*` incl. `_dispatch_never_blocks_return` pass |
| 13 | Warranty-expiring sweep dispatches `asset.warranty_expiring` tenant-bracketed via existing scheduler, no new job | ✓ VERIFIED | `itam_finance_service.py:415-431` brackets with `set_tenant_id`/`reset_tenant_id`; tests `test_warranty_expiring_*` pass |
| 14 | License-expiring sweep rides same scheduler loop (D-08), tenant-bracketed | ✓ VERIFIED | `itam_finance_service.py:461-469` deferred-imports and calls `run_license_expiry_alert_pass`; tests `test_license_expiring_*` pass |
| 15 | License-expiry sweep claims atomically (marker-absent in update filter), idempotent across passes | ✓ VERIFIED | `itam_event_sweeps.py:186-188`; tests `test_license_expiring_two_sequential_passes_*`, `test_license_expiring_concurrent_claim_returns_nothing_dispatches_zero` pass |
| 16 | `asset.audit_overdue` fires from a new periodic sweep using the report route's own overdue definition | ✓ VERIFIED | `itam_event_sweeps.py:216-300`; tests `test_audit_overdue_*` incl. `_sweep_selection_matches_report_route_selection` pass |
| 17 | Audit-overdue and stuck-approval sweeps claim atomically and are registered at startup on a daily cadence | ✓ VERIFIED | `app_startup.py:651-653` calls `start_itam_event_sweep_scheduler`; `ITAM_EVENT_SWEEP_INTERVAL_SECONDS = 24*60*60`; tests `test_scheduler_registration_*`, `test_audit_overdue_concurrent_claim_loss_skips_document` pass |
| 18 | High-value stuck asset request gets one automatic ticket (D-10 trigger two) | ✓ VERIFIED | `run_stuck_approval_ticket_pass` (`itam_event_sweeps.py:331-391`); tests `TestAutomaticTicketTriggers::*` pass |
| 19 | ITAM event turned into Jira/ServiceNow ticket via existing connectors unmodified, only a new shape adapter added | ✓ VERIFIED | `_itam_event_to_alert_shape` (`ticketing_bridge.py:91`) feeds unmodified `create_jira_ticket`/`create_servicenow_incident`; adapter-shape tests pass |
| 20 | Manual "Create Ticket" endpoint exists, dedup-guarded (no second ticket), tenant-correct field per collection | ✓ VERIFIED | `POST /api/itam/tickets` (`itam_ticketing_endpoints.py`), registered in `router_registry.py:97`; tests `test_manual_create_*` incl. `_already_ticketed_returns_409_not_a_second_ticket`, `_asset_request_entity_kind_uses_snake_case_tenant_field` pass |
| 21 | Ticket creation reuses tenant's existing ticketing config; no ITAM-specific settings surface | ✓ VERIFIED | `create_ticket_for_itam_event` calls `get_ticketing_config(tenant_id)` bracketed with `set_tenant_id`/`reset_tenant_id` (`ticketing_bridge.py`); no new settings endpoint added |
| 22 | Ticket fields returned to client never include Jira/ServiceNow credentials | ✓ VERIFIED | `ItamTicketResponse` restricted to `ticket_provider`/`ticket_ref`/`ticket_url` (`itam_ticketing_endpoints.py`); test `_response_body_key_set_is_exactly_three_ticket_keys` passes |
| 23 | Eight new ITAM event types appear in the webhook subscription picker, byte-identical to backend dispatch strings | ✓ VERIFIED | `components/WebhookManagement.tsx:23-30` list matches `itam_webhook_events.py` constants exactly |
| 24 | Operator can create a Jira/ServiceNow ticket for any asset or request row from the ITAM console; action hidden when neither provider configured; row shows badge/ref/link once ticketed | ✓ VERIFIED | `LifecyclePanel.tsx`/`RequestsPanel.tsx` wire `getTicketingConfig`, `createItamTicket`, conditional `hasJira`/`hasServiceNow` menu, `ticket_ref`/`ticket_provider`/`ticket_url` badge+link rendering |
| 25 | `AssetRequestBase.estimated_cost` (additive, optional) backs the high-value classification substitute (Flagged Assumption 1) | ✓ VERIFIED | `backend/itam_models.py:580,591` `estimated_cost: Optional[float]` |
| 26 | No unresolved debt markers (TBD/FIXME/XXX) in phase-modified files | ✓ VERIFIED | Grep across all 22 phase-modified backend/frontend files: zero matches |

**Score:** 25/26 truths verified as behaviorally proven or structurally confirmed (24 fully VERIFIED + truth 25/26 counted; 1 PRESENT_BEHAVIOR_UNVERIFIED excluded from verified count per methodology). Corrected score: **24/26** (truth #8 excluded).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_webhook_events.py` | 8 event constants + tuple | ✓ VERIFIED | 35 lines, constants-only, no dispatch wrapper (per D-07) |
| `backend/tests/test_itam_api_integrations.py` | ITAM-API-01 regression suite | ✓ VERIFIED | 15 tests, all pass |
| `backend/tests/test_itam_webhook_events.py` | ITAM-API-02 regression suite | ✓ VERIFIED | ~50 tests covering all 8 event dispatch points, all pass |
| `backend/itam_event_sweeps.py` | tenant-bracketed background sweeps | ✓ VERIFIED | `run_license_expiry_alert_pass`, `run_audit_overdue_alert_pass`, `run_stuck_approval_ticket_pass`, `start_itam_event_sweep_scheduler`, `_dispatch_tenant_scoped_event` all present, imported, and exercised by tests |
| `backend/itam_ticketing_endpoints.py` | manual create-ticket route | ✓ VERIFIED | Registered in `router_registry.py:97`; `test_manual_create_registered_in_real_app` and `_route_reachable_in_assembled_app_not_a_404` pass |
| `backend/tests/test_itam_ticketing_bridge.py` | ITAM-API-03 regression suite | ✓ VERIFIED | ~40 tests, all pass |
| `components/itam/LifecyclePanel.tsx` | ticket row action | ✓ VERIFIED | `createItamTicket`, `getTicketingConfig`, ticket badge/ref/link rendering present |
| `components/itam/RequestsPanel.tsx` | ticket row action | ✓ VERIFIED | Same pattern mirrored for asset requests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `itam_asset_endpoints._require_itam_admin` | `api_key_auth.get_current_user_or_api_key` | dual-auth swap | ✓ WIRED | `Depends(get_current_user_or_api_key)` at line 38 |
| `itam_asset_endpoints._require_itam_admin` | `rbac_service._scopes_allow` | scope narrowing | ✓ WIRED | Called at line 60 after role check |
| `_require_itam_admin_session_only` | ldap/sso/user/api_key endpoints | 4 excluded surfaces | ✓ WIRED | All four import the session-only sibling under the `_require_itam_admin` alias |
| `api_key_auth.AVAILABLE_SCOPES` | `api_key_endpoints` scope validation | issuance guard | ✓ WIRED | `api_key_endpoints.py:40` rejects unknown scopes |
| `itam_lifecycle_endpoints.checkout_asset` | `webhook_service.WebhookService.trigger_webhook` | dispatch spine | ✓ WIRED | `asyncio.create_task(...)` at line 230 |
| `itam_finance_service.run_warranty_alert_pass` | `webhook_service.trigger_webhook` | tenant-bracketed | ✓ WIRED | Lines 415-431 |
| `itam_finance_service.start_warranty_alert_scheduler` | `itam_event_sweeps.run_license_expiry_alert_pass` | rides existing scheduler (D-08) | ✓ WIRED | Deferred import + call at lines 461-469 |
| `itam_event_sweeps.run_audit_overdue_alert_pass` | `ticketing_bridge.create_ticket_for_itam_event` | D-10 automatic trigger 1 | ✓ WIRED | Line 300 |
| `itam_event_sweeps.run_stuck_approval_ticket_pass` | `ticketing_bridge.create_ticket_for_itam_event` | D-10 automatic trigger 2 | ✓ WIRED | Line 391 |
| `app_startup` | `itam_event_sweeps.start_itam_event_sweep_scheduler` | startup registration | ✓ WIRED | Lines 651-653 |
| `itam_ticketing_endpoints` | `router_registry` | route registration | ✓ WIRED | `router_registry.py:97` |
| `types.ts WebhookEvent` union | `WebhookManagement.availableEvents` | picker entries | ✓ WIRED | 8 new members present in both, byte-identical strings |
| `apiService.createItamTicket` | `POST /api/itam/tickets` | manual ticket client call | ✓ WIRED | `services/apiService.ts:4758` |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full phase-73 backend test suite (3 test files, 122 tests) | `backend/venv/bin/python -m pytest backend/tests/test_itam_api_integrations.py backend/tests/test_itam_webhook_events.py backend/tests/test_itam_ticketing_bridge.py -q` | `122 passed, 12 warnings in 32.85s` | ✓ PASS |
| Requirement ID cross-reference | grep REQUIREMENTS.md | ITAM-API-01/02/03 all mapped to Phase 73, status "Complete" | ✓ PASS |
| Debt-marker scan (TBD/FIXME/XXX) across 22 phase-modified files | grep | 0 matches | ✓ PASS |
| Frontend `tsc --noEmit` | `npx tsc --noEmit -p tsconfig.json` | Pre-existing, unrelated module-resolution errors in `src/router/routes.tsx` (~40 dashboards, e.g. `DeviceConfigProfilesDashboard`, `MSSPDashboard`) — none reference phase 73 files (`LifecyclePanel`, `RequestsPanel`, `WebhookManagement`, `apiService`, `types.ts`) | ? SKIP (pre-existing, out of phase scope) |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ITAM-API-01 | 73-01 | Full REST API coverage for ITAM | ✓ SATISFIED | Dual session/API-key auth + scope narrowing on all `_require_itam_admin`-gated ITAM routers, verified by 15 passing tests |
| ITAM-API-02 | 73-01, 73-02, 73-03, 73-05, 73-06 | Webhook system for events | ✓ SATISFIED | All 8 event types dispatch from their real mutation points/sweeps, tenant-bracketed where needed, frontend picker updated; ~50 tests pass; truth #8 (concurrency isolation) unverified by test — see human verification |
| ITAM-API-03 | 73-04, 73-05, 73-06 | Third-party integrations (Jira, ServiceNow) | ✓ SATISFIED | Manual + 2 automatic ticket triggers via existing unmodified connectors, dedup-guarded, credential-safe response, console row actions; ~40 tests pass |

No orphaned requirements — all three IDs mapped in REQUIREMENTS.md to Phase 73 and all three are claimed across plan frontmatter `requirements:` fields.

### Anti-Patterns Found

None classified as blockers in phase-73-modified files. Code review (`73-REVIEW.md`, standard depth, 26 files) found 3 warnings and 2 info items, all in **pre-existing code the phase's diff sits adjacent to, not code this phase introduced**:

| File | Issue | Severity | Impact | Introduced by Phase 73? |
|------|-------|----------|--------|--------------------------|
| `components/WebhookManagement.tsx:117-128` | `toggleWebhookStatus` uses bare `fetch` (no auth header) | Warning (WR-01) | Toggling a webhook's enabled state may silently 401 | No — confirmed via `git log --follow` this function predates phase 73 (commit `bd2e9097`); phase 73 only added the 8 ITAM event strings to the same file |
| `backend/ticketing_bridge.py:169-200,329-380` | `create_ticket_for_remediation_task` / `run_close_loop_pass` don't tenant-bracket `get_ticketing_config` the way phase 73's own new `create_ticket_for_itam_event` does | Warning (WR-02) | Pre-existing close-loop auto-resolution may silently no-op under background-sweep context | No — these are pre-existing sibling functions; phase 73's own new function correctly applies the bracket |
| `components/WebhookManagement.tsx` | `handleCreateWebhook`/`handleTestWebhook` don't check `response.ok` | Warning (WR-03) | Failed webhook creation can appear to succeed in the UI | No — pre-existing handlers, unmodified by phase 73's diff |

These are legitimate defects worth a follow-up fix but do not block phase 73's own goal — the phase's own new code (webhook dispatch call sites, ticketing bridge's new adapter/orchestrator, manual ticket route, console ticket actions) does not exhibit these patterns.

### Human Verification Required

1. **Concurrent-tenant API-key isolation** — Fire two concurrent API-key-authenticated ITAM requests from two different tenants and confirm no cross-tenant contamination via the `set_tenant_id` contextvar. Code is present and correctly wired (`api_key_auth.py:262,281`), but no test in the 122-test phase suite exercises actual concurrent isolation — this relies on Python asyncio's per-task ContextVar copy semantics, which is a reasonable expectation but was called out in the plan's own must-haves as an edge-probe item and is not proven here.
2. **Ticket-provider dropdown at narrow viewport** — Confirm the provider-choice dropdown (positioned against the table's right edge) stays fully on-screen and readable at a narrow viewport width. Flagged `verification: backstop` in `73-06-PLAN.md`.
3. **Long ticket-reference row layout** — Confirm an unusually long provider-issued ticket reference does not break the LifecyclePanel/RequestsPanel row layout. Flagged `verification: backstop` in `73-06-PLAN.md`.

### Gaps Summary

No gaps found — no missing, stub, or orphaned artifacts; no broken key links; no failed truths; no unresolved debt markers. All 122 phase-specific backend tests pass, covering the great majority of the must-haves across all six plans, including the harder concurrency/idempotency invariants (atomic marker-absent claims, tenant-context bracketing and restoration across sweep passes, dedup guards on ticket creation). The one truth left unverified by test is a genuinely hard-to-test cross-request concurrency isolation guarantee (contextvar scoping across concurrent asyncio tasks), plus two UI must-haves the plan itself pre-flagged as requiring visual/backstop confirmation. None of these represent missing implementation — they represent claims that code inspection and the existing test suite cannot fully close out, which routes this phase to human verification rather than a gap.

---

_Verified: 2026-08-19_
_Verifier: Claude (gsd-verifier)_
