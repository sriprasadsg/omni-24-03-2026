---
phase: 59-procurement-finance-warranty-depreciation
plan: 02
subsystem: api
tags: [notifications, fastapi, pydantic, warranty-alerts, itam]

# Dependency graph
requires:
  - phase: 21-notification-routing-domain-scanner
    provides: notification_service.py / notification_endpoints.py rule+channel infrastructure (VALID_EVENTS, RuleCreate, send_notification, get_notification_service)
provides:
  - "itam.warranty_expiring" added to notification_service.VALID_EVENTS and notification_endpoints.RuleCreate.event_type's Literal — tenant admins can now create a warranty-expiry notification rule through POST /api/notifications/rules
  - Pinned automated contract for both warranty-alert delivery paths Plan 59-04's sweep will call: rule-routed (send_notification with a `_db`-exposing handle) and raw-handle (send_alert working directly against a raw db with no `_db`)
  - Regression guard for RESEARCH Pitfall 1 — send_notification against a raw db handle with no `_db` and no `__getattr__` fallback raises AttributeError, proven with a plain-class stub that a MagicMock could not have caught
affects: [59-04-warranty-alert-sweep]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vocabulary extension: adding a new event type to a closed Literal + closed set in two files simultaneously, never collapsing them into a shared constant"
    - "Plain-class (non-MagicMock) db stubs to prove a calling contract that an auto-attribute-creating mock would mask"

key-files:
  created:
    - backend/tests/test_itam_warranty_notify.py
  modified:
    - backend/notification_service.py
    - backend/notification_endpoints.py

key-decisions:
  - "PD-01 (recorded in PLAN.md): warranty alerts will use both delivery paths — guaranteed in-app send_alert plus optional rule-routed send_notification — so this plan (the rule-routed enabling half) is required scope, not a nice-to-have"
  - "The two vocabulary definitions (VALID_EVENTS set, RuleCreate Literal) stay separate per plan instruction — no refactor into a shared constant, since one guards the service layer and the other guards the FastAPI request body"

patterns-established:
  - "Adding a new dotted-namespace event type (itam.warranty_expiring) alongside a flat legacy vocabulary (finding_created, control_failed, ...) — future ITAM event types should follow the same itam.* dotted convention"

requirements-completed: [ITAM-FIN-02]

coverage:
  - id: D1
    description: "A tenant admin can create a notification rule for itam.warranty_expiring through POST /api/notifications/rules instead of getting a 422"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_warranty_notify.py::TestWarrantyEventVocabulary -k event_vocabulary"
        status: pass
    human_judgment: false
  - id: D2
    description: "The five pre-existing event types and the closed-vocabulary rejection of unknown event types are unchanged"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_warranty_notify.py::TestWarrantyEventVocabulary::test_event_vocabulary_create_rule_accepts_every_legacy_event_type"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_warranty_notify.py::TestWarrantyEventVocabulary::test_event_vocabulary_create_rule_rejects_unknown_event_type"
        status: pass
    human_judgment: false
  - id: D3
    description: "send_notification resolves a tenant's itam.warranty_expiring rule to its channel and dispatches, with the rule/channel lookup scoped by both tenantId and event_type"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_warranty_notify.py::TestRuleRoutedDelivery -k rule_routed"
        status: pass
    human_judgment: false
  - id: D4
    description: "send_notification against a raw db handle with no _db raises AttributeError (RESEARCH Pitfall 1 regression guard); send_alert works against the same raw handle without any unwrap"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_warranty_notify.py::TestRawDbCallingContract -k raw_db_contract"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-08-05
status: complete
---

# Phase 59 Plan 02: Notification Event Vocabulary Extension for Warranty Alerts Summary

**Extended the closed `itam.warranty_expiring` event-type vocabulary in both `notification_service.VALID_EVENTS` and `notification_endpoints.RuleCreate`'s `Literal`, plus a 14-test pinned contract for both warranty-alert delivery paths Plan 59-04's sweep will call.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-08-05
- **Tasks:** 2
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- `notification_service.VALID_EVENTS` and `notification_endpoints.RuleCreate.event_type`'s `Literal` both now accept `itam.warranty_expiring`, closing RESEARCH Pitfall 2 — a tenant admin creating a warranty-expiry rule through `POST /api/notifications/rules` no longer gets a 422.
- Both files carry an inline comment recording the ITAM addition and why the dotted form is deliberate, so a future reader doesn't mistake it for a typo among the five undotted legacy names.
- 14 tests in a new `backend/tests/test_itam_warranty_notify.py` pin: (a) the vocabulary itself, asserted against the real `VALID_EVENTS` object and the real `Literal` via `typing.get_args` — never a hand-copied list; (b) the rule-routed delivery path (`send_notification` given a `_db`-exposing handle resolves a matching rule to its channel, tenant+event-type-scoped query, severity-filter include/exclude); (c) the raw-handle calling contract from RESEARCH Pitfall 1 — `send_notification` against a raw db with no `_db` and no `__getattr__` fallback raises `AttributeError`, while `get_notification_service(...).send_alert(...)` works against that same raw handle with no unwrap.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend the event-type vocabulary in both hardcoded places** - `c08f3f7` (feat) — `VALID_EVENTS`/`RuleCreate.event_type` extension + `TestWarrantyEventVocabulary` (7 tests)
2. **Task 2: Pin the rule-routed delivery contract Plan 59-04's sweep must satisfy** - `ec58e1f` (test) — `TestRuleRoutedDelivery` (5 tests) + `TestRawDbCallingContract` (2 tests)

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `backend/notification_service.py` - `VALID_EVENTS` gains `"itam.warranty_expiring"` alongside the five pre-existing event types
- `backend/notification_endpoints.py` - `RuleCreate.event_type`'s `Literal` gains the same string
- `backend/tests/test_itam_warranty_notify.py` (new, 247 lines) - `TestWarrantyEventVocabulary`, `TestRuleRoutedDelivery`, `TestRawDbCallingContract`

## Decisions Made
- Kept `VALID_EVENTS` (service-layer guard) and `RuleCreate.event_type`'s `Literal` (request-body guard) as two separate definitions per the plan's explicit instruction — collapsing them into a shared constant is a refactor with no mandate in this phase.
- Followed PD-01 from the plan (both in-app `send_alert` and rule-routed `send_notification` delivery paths are required by ITAM-FIN-02's literal "notification/webhook infrastructure" wording) — this plan is the enabling half for the rule-routed path.

## Deviations from Plan

None — plan executed exactly as written. Both production edits (`VALID_EVENTS`, `RuleCreate.event_type`) are the only two production changes, matching the plan's explicit scope boundary (no touch to `VALID_CHANNEL_TYPES`, `create_channel`, `_validate_webhook_url`, or any delivery branch).

## Issues Encountered
None. `backend/tests/test_graphql.py` fails to collect in this environment due to a pre-existing `strawberry`/`pydantic` version incompatibility unrelated to this plan (confirmed identical before and after this plan's changes) — excluded from full-suite runs via `--ignore`, consistent with the phase's stated baseline exclusion.

**Requirement-tracking correction:** `requirements.mark-complete` mechanically marked `ITAM-FIN-02` fully `[x]` in REQUIREMENTS.md based solely on this plan's own frontmatter `requirements: [ITAM-FIN-02]` field. `ITAM-FIN-02` is actually claimed by three plans in this phase (59-02, 59-03, 59-04 all list it), and only 59-02 (the notification-vocabulary half) has executed — 59-03 (warranty-status computation) and 59-04 (the actual alert sweep) have not run yet, so the requirement's real-world truth ("Asset warranty is tracked... with expiry alerts") is not yet met. Reverted the checkbox to `[ ]` and the traceability row to "In Progress (59-02 done; 59-03/59-04 pending)" so REQUIREMENTS.md doesn't over-claim; the correct requirements-completed marking for this plan is limited to the vocabulary-extension contribution it actually delivered (tracked via this SUMMARY's `coverage:` block instead).

## TDD Gate Compliance

Both tasks in this plan are marked `tdd="true"`, but the plan's own `<action>` blocks describe combined test+implementation work per task (test file creation alongside the two production edits in Task 1; two additional test classes with no production changes in Task 2) rather than a strict separate RED-before-GREEN sequence — the plan's frontmatter `type: execute` (not `type: tdd`) confirms the stricter Plan-Level TDD Gate Enforcement does not apply here. Task 1 is committed as `feat` (production edits + first test class, all green together — RESEARCH's Pitfall 2 fix and its pinning test have no meaningful separate-RED state since the vocabulary change is trivial and additive). Task 2 is committed as `test` (pure test additions, no production code changed). Both commits' tests pass; no regression introduced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 59-04 (warranty-alert sweep) can now call `notification_service.send_notification(wrapped_db, tenant_id, "itam.warranty_expiring", payload)` for tenants who have configured a rule, and `get_notification_service(raw_db).send_alert(...)` unconditionally for guaranteed in-app delivery — both contracts are pinned by this plan's tests.
- No blockers. This plan shares no files with 59-01 (purchase/book-value) or 59-03 (warranty status), and ran independently in wave 1.

---
*Phase: 59-procurement-finance-warranty-depreciation*
*Completed: 2026-08-05*

## Self-Check: PASSED

- FOUND: backend/notification_service.py
- FOUND: backend/notification_endpoints.py
- FOUND: backend/tests/test_itam_warranty_notify.py
- FOUND: .planning/phases/59-procurement-finance-warranty-depreciation/59-02-SUMMARY.md
- FOUND commit: c08f3f7
- FOUND commit: ec58e1f
