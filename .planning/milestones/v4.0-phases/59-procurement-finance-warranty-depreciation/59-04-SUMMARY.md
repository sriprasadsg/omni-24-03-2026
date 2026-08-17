---
phase: 59-procurement-finance-warranty-depreciation
plan: 04
subsystem: api
tags: [fastapi, itam, finance, warranty, notifications, scheduler]

# Dependency graph
requires:
  - phase: 59-procurement-finance-warranty-depreciation
    provides: "59-01's warrantyAlertSentAt reset contract on PATCH /purchase; 59-02's itam.warranty_expiring notification vocabulary; 59-03's compute_warranty_status/get_warranty_alert_window, which the sweep calls directly"
provides:
  - "run_warranty_alert_pass(db) — background sweep that alerts on expiring/expired warranties via both the in-app notification feed and tenant-configured notification/webhook rules, with per-asset tenant isolation and a warrantyAlertSentAt idempotency marker"
  - "start_warranty_alert_scheduler(db) registered at application startup with the raw, unwrapped mongodb handle, alongside the three existing raw-database schedulers"
  - "_RawDbForNotificationRules — the minimal _db-exposing adapter that lets the rule-routed notification path accept a raw handle without raising"
affects: [61-frontend-itam-console]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Background sweep never resolves its own database handle — receives it as a parameter from app_startup, same discipline as compliance_remediation_sla_service.py"
    - "Two independent delivery paths (in-app + rule-routed), each in its own try/except, so one tenant's misconfigured channel cannot suppress another tenant's alert or the other delivery path"
    - "Idempotency marker enforced twice: as a query term (db excludes already-alerted docs) and as a Python guard (correctness doesn't depend on the query)"

key-files:
  created:
    - backend/tests/test_itam_finance_sweep_resilience.py
    - backend/tests/itam_finance_sweep_test_support.py
  modified:
    - backend/itam_finance_service.py
    - backend/app_startup.py
    - backend/tests/test_itam_finance_sweep.py

key-decisions:
  - "_RawDbForNotificationRules adapter (not TenantIsolatedDatabase + ContextVar) for the rule-routed delivery call — send_notification's queries already carry explicit tenantId filters, so no ambient tenant context is needed, and mutating a process-wide ContextVar inside a long-lived background task would add real leak risk for zero benefit (PD-03, from 59-04-PLAN.md)"
  - "warrantyAlertSentAt is written unconditionally once an asset reaches the delivery step, even if both delivery paths raise — the alternative (retry until success) turns one permanently misconfigured channel into an unbounded notification storm; re-alerting stays reachable through PATCH /purchase clearing the marker on a genuine warranty change"
  - "Test file split: test_itam_finance_sweep.py (Tasks 1-2, fixtures re-exported from the new itam_finance_sweep_test_support.py), test_itam_finance_sweep_resilience.py (Task 3) — mirrors the itam_finance_test_support.py precedent Plan 59-01 established for the same 500-line reason"

requirements-completed: [ITAM-FIN-02]

coverage:
  - id: D1
    description: "A tenant admin receives an alert as an asset's warranty approaches or passes expiry, without anyone opening a page, delivered through the existing notification/webhook infrastructure (ITAM-FIN-02, ROADMAP success criterion 2 second half)"
    requirement: "ITAM-FIN-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_finance_sweep.py::TestWarrantySweepCore"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_sweep_resilience.py::TestSweepRawDbNoCrash"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_sweep_resilience.py::TestSweepIdempotency"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_sweep_resilience.py::TestSweepResilienceAndTenantScope"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_finance_sweep.py::TestWarrantySchedulerRegistration"
        status: pass
    human_judgment: true
    rationale: "Tests prove the sweep's decisions and delivery logic against stubs; observing a real alert arrive in the running application (GET /api/notifications, or a configured Slack/webhook channel) is explicitly deferred to phase verification per 59-04-PLAN.md's own <verification> section."

# Metrics
duration: unknown — resumed from an interrupted prior session; this close-out session ~45min
completed: 2026-08-06
status: complete
---

# Phase 59 Plan 04: Warranty Alert Background Sweep Summary

**Tenant-isolation-safe background sweep (`run_warranty_alert_pass`) that alerts on expiring/expired asset warranties via both the in-app notification feed and tenant-configured notification rules, registered at application startup with the raw database handle and guarded by a `warrantyAlertSentAt` idempotency marker — completing ITAM-FIN-02 and, with it, all three of Phase 59's requirements.**

## Performance

- **Tasks:** 3 (all previously implemented; this session closed the gap that kept them from being a working, fully-committed feature)
- **Files modified/created:** 5

## Accomplishments
- `run_warranty_alert_pass`, `start_warranty_alert_scheduler`, `_RawDbForNotificationRules`, `_tenant_admin_emails`, `WARRANTY_EVENT_TYPE` in `itam_finance_service.py` — the sweep never resolves its own database handle, extracts `tenantId` from each asset document, and delivers on two independent, failure-isolated paths
- `start_warranty_alert_scheduler` registered in `app_startup.py` with the raw, unwrapped `_mdb.db` handle, alongside the three existing raw-database schedulers — **this session's actual delta**; see Deviations below
- 18 tests across `test_itam_finance_sweep.py` and the new `test_itam_finance_sweep_resilience.py` prove: correct asset selection and marking, the no-tenantId skip guard, tenant-scoped recipient/write filters, the raw-handle-no-crash regression guard for RESEARCH Pitfall 1, two-pass idempotency including the PATCH-triggered reset, per-path failure isolation, cross-tenant delivery isolation, and the app_startup source-level registration guard
- ITAM-FIN-02 complete. With Plan 59-01 (ITAM-FIN-01/03) and this plan, **all three of Phase 59's requirements are now delivered.**

## Task Commits

This plan's history is not the usual one-commit-per-task shape and is documented here in full for traceability:

1. **Task 1 (sweep core) + Task 3 (resilience/idempotency tests):** already present in `itam_finance_service.py` and `test_itam_finance_sweep.py` via two prior, non-conventional commits that predate this session — `72a236f` ("feat(59): warranty alert sweep + ITAM console scaffold + vitest migration") and `490e850` ("feat(59,60): warranty alert sweep + license management"). Neither commit followed this project's phase-plan commit-message convention, neither has a corresponding SUMMARY.md, and both bundle unrelated work: `72a236f` also scaffolds `components/itam/ITAMConsole.tsx` and a Phase 61 `AppView` type change plus a Jest→Vitest Modal test migration; `490e850` also adds Phase 60's `itam_license_service.py`/`itam_license_endpoints.py`/`test_itam_license.py`. **`490e850`'s `test_itam_license.py` is currently broken** — a real `IndentationError` at line 105 that fails collection for the entire `backend/tests` directory when run unfiltered. Out of scope for this plan; flagged for whoever picks up Phase 60.
2. **Task 2 (app_startup registration) — the actual gap:** `git show HEAD:backend/app_startup.py` (prior to this session) contained **no** reference to the warranty scheduler at all. `TestWarrantySchedulerRegistration::test_raw_db_registration_app_startup_uses_raw_mongodb_db` was therefore committed in a failing state — confirmed by checking out `HEAD`'s test file against `HEAD`'s `app_startup.py` in isolation (1 failed, 1 passed). This session's commit `235cd94` ("fix(59-04): wire warranty alert scheduler into app_startup + split sweep tests under 500 lines") adds the missing registration block, dedupes a duplicated `notification_service` import in `itam_finance_service.py` left over from `490e850`'s incomplete "Fixes: duplicate imports" claim, and splits the now-608-line test file (a genuine violation of both CLAUDE.md's 500-line rule and this plan's own Task 3 acceptance criterion) into three files.

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `backend/itam_finance_service.py` — deduped a doubled `notification_service` import (417 lines; the sweep functions themselves were already present from prior commits)
- `backend/app_startup.py` — added the warranty-alert scheduler registration block (raw `_mdb.db` handle), matching the shape of the three existing raw-database scheduler blocks
- `backend/tests/test_itam_finance_sweep.py` — trimmed to `TestWarrantySweepCore` (Task 1) + `TestWarrantySchedulerRegistration` (Task 2); 185 lines (was 608)
- `backend/tests/test_itam_finance_sweep_resilience.py` — new; `TestSweepRawDbNoCrash`, `TestSweepIdempotency`, `TestSweepResilienceAndTenantScope` (Task 3); 259 lines
- `backend/tests/itam_finance_sweep_test_support.py` — new; `_RawSweepDb` and its collection stubs, `_run`, `_asset`, `_user`, shared by both test files above; 216 lines

## Decisions Made
See `key-decisions` in frontmatter (PD-03 adapter choice, unconditional marker write, test file split).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2/3 - Missing Critical / Blocking] app_startup registration was never committed**
- **Found during:** Close-out verification (safe-resume check) at the start of this session
- **Issue:** `.continue-here.md` (a session-handoff note, not part of the plan) claimed Tasks 1-3 were implemented and green but uncommitted. Investigation showed the sweep logic and its Task-1/Task-3 tests were **already committed** via two prior non-conventional commits (`72a236f`, `490e850`), but the Task-2 `app_startup.py` registration was genuinely never committed — leaving `TestWarrantySchedulerRegistration` failing at `HEAD` and the feature non-functional (the scheduler would never actually start in production).
- **Fix:** Added the registration block; verified against `HEAD` in isolation that the test failed without it and passes with it.
- **Files modified:** `backend/app_startup.py`
- **Verification:** `test_raw_db_registration_app_startup_uses_raw_mongodb_db` passes; full 18/18 sweep suite passes; live boot log (from the prior session's handoff) already showed `[ITAM] Warranty alert scheduler started`.
- **Committed in:** `235cd94`

**2. [Rule 1 - CLAUDE.md 500-line limit] test_itam_finance_sweep.py was 608 lines**
- **Found during:** Re-verifying this plan's own Task 3 acceptance criteria (`awk 'END{print NR}' backend/tests/test_itam_finance_sweep.py` was specified to print a number below 500; it printed 607/608)
- **Issue:** The two prior non-conventional commits accumulated all of Tasks 1-3's test classes into one file without ever checking the line count the plan itself required.
- **Fix:** Split into `test_itam_finance_sweep.py` (Tasks 1-2) + new `test_itam_finance_sweep_resilience.py` (Task 3) + new shared `itam_finance_sweep_test_support.py`, following the exact precedent `itam_finance_test_support.py` set for Plan 59-01's same problem.
- **Files modified:** `backend/tests/test_itam_finance_sweep.py`; created `backend/tests/test_itam_finance_sweep_resilience.py`, `backend/tests/itam_finance_sweep_test_support.py`
- **Verification:** All three files now under 500 lines (185/259/216); 18/18 tests pass individually and via every `-k` filter the plan's acceptance criteria specify.
- **Committed in:** `235cd94`

---

**Total deviations:** 2 auto-fixed (1 blocking — missing registration, 1 CLAUDE.md rule violation). Both were gaps in already-committed prior work, not scope creep introduced by this session.
**Impact on plan:** Both fixes were necessary for the feature to actually function and for the plan's own acceptance criteria to pass. No functional scope was added beyond what 59-04-PLAN.md specifies.

## Issues Encountered

**Process/history issue, not a code issue — flagged for the user, not fixed here (out of this plan's scope):**
- Commits `72a236f` and `490e850` (both predating this session) do not follow this project's phase-plan commit convention, have no SUMMARY.md, and each bundle unrelated cross-phase work: `72a236f` adds a Phase 61 `ITAMConsole.tsx` scaffold and an `AppView` type change plus an unrelated Modal jest→vitest migration; `490e850` adds Phase 60's license backend (`itam_license_service.py`, `itam_license_endpoints.py`, router registration) and `test_itam_license.py`, **which is currently broken** (`IndentationError` at line 105 — fails collection for the whole `backend/tests` directory if not excluded).
- `.planning/STATE.md` at `HEAD` (before this session's uncommitted corrections) claimed `current_phase: 61`, `completed_phases: 60`, `95%` — i.e., that Phase 61 planning had started and 60 phases were done. That was inaccurate: Phase 59 was not complete (this plan) and Phase 60 is not complete (broken test, no recorded plan execution). The working tree already carried a corrective, uncommitted edit reverting `current_phase` to 59 before this session began; this plan's tracking commit carries that correction forward accurately (Phase 59 complete, Phase 60 next).
- `backend/tests/test_graphql.py` continues to fail collection in this environment due to the pre-existing `strawberry`/`pydantic` version incompatibility documented in prior phase summaries (59-03 and earlier) — unrelated to this plan, excluded from the full-suite run.
- None of the above were modified by this plan. They are surfaced here so the next session (likely Phase 60) starts with accurate information instead of rediscovering it.

## User Setup Required

None — no external service configuration required. The scheduler starts automatically with the application; no new dependency was added.

## Addendum: Code Review Pass (2026-08-06, same session)

`/gsd-code-review 59` ran across all 15 Phase 59 files and found a real critical defect this plan's own tests didn't catch: `run_warranty_alert_pass`'s "guaranteed in-app" delivery path writes through a raw db handle by design, which bypasses `TenantIsolatedCollection.insert_one`'s automatic `tenantId` injection — combined with `notification_service.send_alert` only writing `tenant_id` (snake_case), every warranty alert had no `tenantId` field and was invisible to the tenant it was meant to notify. Fixed in `notification_service.py` (writes `tenantId` explicitly now) with new regression assertions in `test_itam_warranty_notify.py` and `test_itam_finance_sweep_resilience.py`. Two more findings fixed in the same pass: the marker write is now isolated in its own `try/except` (WR-03), and the mislabeled "expiring" test now genuinely exercises that branch (WR-02). Four lower-severity findings against Plan 59-01's already-shipped `compute_book_value` code were deferred — see `59-REVIEW.md`'s Resolution section. Full backend suite after fixes: **1805 passed / 35 skipped / 3 pre-existing unrelated failures**, no regressions. Commits: `f4ccb67` (fixes), `69634e2` (review report).

## Next Phase Readiness
- Phase 59 is complete: all three requirements (ITAM-FIN-01/02/03) delivered and verified, **including a real cross-cutting bug the code review caught and this session fixed** (see Addendum above — do not trust the pre-review commits `72a236f`/`490e850` alone as proof the sweep worked end-to-end). Full backend suite: 1805 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai`, `test_e2e_integration`, `test_rust_heartbeat_parity`) — identical failure set to the documented baseline, no regressions. `test_graphql.py` and `test_itam_license.py` excluded per the documented pre-existing collection errors (the latter newly discovered this session).
- **Blocker for whoever picks up Phase 60:** `backend/tests/test_itam_license.py` has a genuine `IndentationError` and cannot collect. The Phase 60 backend it tests (`itam_license_service.py`, `itam_license_endpoints.py`) was committed alongside Phase 59 work in `490e850` without a plan, without tests passing, and without a SUMMARY.md — Phase 60 should not be assumed to have a working tracer slice just because these files exist on disk.
- Human-only verification deferred per 59-04-PLAN.md: observing a real alert arrive via `GET /api/notifications` or a configured Slack/webhook channel in the running application. Recommend covering this in `/gsd-verify-work` for Phase 59.

---
*Phase: 59-procurement-finance-warranty-depreciation*
*Completed: 2026-08-06*

## Self-Check: PASSED

- FOUND: backend/itam_finance_service.py
- FOUND: backend/app_startup.py
- FOUND: backend/tests/test_itam_finance_sweep.py
- FOUND: backend/tests/test_itam_finance_sweep_resilience.py
- FOUND: backend/tests/itam_finance_sweep_test_support.py
- FOUND: .planning/phases/59-procurement-finance-warranty-depreciation/59-04-SUMMARY.md
- FOUND commit: 235cd94
