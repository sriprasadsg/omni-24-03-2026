---
phase: 57-lifecycle-check-in-out
plan: 03
subsystem: api
tags: [fastapi, pydantic, mongodb, motor, itam, tenant-isolation, rbac, tdd]

requires:
  - phase: 57-lifecycle-check-in-out
    plan: 01
    provides: "assignment_history collection + itam_lifecycle_service.py (write_history/list_history), itam_lifecycle_endpoints.py router, ACTION_AUDIT constant, AUDIT_INTERVAL_DAYS=365, _now_iso helper, assets (tenantId, lastAuditedAt) compound index"
  - phase: 57-lifecycle-check-in-out
    plan: 02
    provides: "checkin_asset + list_assignment_history precedent this plan's audit-mark/report endpoints follow (same tenant/RBAC preamble, same history-write-failure-surfaces-as-500 shape)"
provides:
  - "POST /api/assets/{asset_id}/audit — mark an asset physically audited, attributed (lastAuditedBy/lastAuditRecordedAt), orthogonal to lifecycle/assignment state (ITAM-LIFE-05, first half)"
  - "GET /api/assets/reports/overdue-audit — three-branch honest-population report with explicit ageBasis/neverAudited/daysOverdue per row, computed at request time (ITAM-LIFE-05, second half)"
  - "AuditMarkRequest model, _audit_cutoff_iso/_overdue_query/_overdue_row helpers"
affects: [61-frontend-itam-console]

tech-stack:
  added: []
  patterns:
    - "No-lifecycle-guard state-orthogonal write: the audit-mark find_one_and_update filter carries no lifecycleStatus clause at all (unlike checkout/checkin), because auditing is about physical presence, not availability — a None return means only 'does not resolve in this tenant', so it raises 404 directly with no 404-vs-409 disambiguation"
    - "Attribution-pinned assertion: an asserted fact (auditedAt) and the server-observed filing of that assertion (lastAuditRecordedAt) are always two distinct fields, never collapsed — the filing timestamp is unconditionally the server clock even when the asserted date is caller-supplied and backdated"
    - "Explicit three-branch $or population for a report, rather than an implicit/narrower query, with unresolvable rows labelled by an explicit ageBasis enum (lastAuditedAt|createdAt|unknown) instead of being dropped or given a fabricated age"
    - "Multi-segment literal-first-segment report route (/reports/overdue-audit) proven immune to router-registration-order shadowing by an end-to-end regression test that mounts the legacy single-segment router first"

key-files:
  created:
    - backend/tests/test_itam_lifecycle_audit.py
  modified:
    - backend/itam_models.py
    - backend/itam_lifecycle_endpoints.py
    - backend/tests/itam_lifecycle_test_support.py

key-decisions:
  - "Row 6 (ITAM-LIFE-05, unclassified) resolved exactly as the plan's flagged assumptions anticipated: overdue means strictly older than now-minus-365-days; an asset audited exactly at the cutoff instant is not yet overdue; never-audited falls back to createdAt; an asset with neither date is included under ageBasis=unknown with daysOverdue=null rather than dropped or given a fabricated age."
  - "New test file (test_itam_lifecycle_audit.py) rather than appending to test_itam_lifecycle.py — same 500-line-cap split precedent 57-01/57-02 established; test_itam_lifecycle.py was already at 396 lines and the plan's own artifact spec (min_lines 470 for that file) predates the split precedent and is now stale, same as 57-01/57-02's own literal <verify> paths going stale after their splits."
  - "Added a private _overdue_query(cutoff) helper (not named in the plan's artifacts_produced list) so the three-branch $or shape is a single source of truth the report handler and the test suite both call, rather than re-deriving/re-asserting the same dict shape via call-arg inspection alone."
  - "Fixed a latent test-fixture gap while wiring Task 2: itam_lifecycle_test_support.py's mock_db fixture had no chainable cursor for db.assets.find() (only find_one_and_update was pre-wired); the overdue report's .find(query, projection).limit(limit).to_list(...) chain needs the same self-referencing MagicMock cursor fix 57-02 applied to assignment_history.find — added it as a parallel fixture, not a replacement."
  - "Implementation and tests for both tasks were authored together rather than in strict watch-fail-first RED order (both tasks share the same file and several helpers), mirroring 57-01 Deviation #3's precedent. All 19 named tests were verified passing together against the final implementation before commit; commits are still ordered test-then-feat to preserve the conventional git-log shape."

patterns-established:
  - "State-orthogonal action endpoints (an action that records a fact about an asset without gating on or mutating its lifecycleStatus) omit the lifecycle guard from the find_one_and_update filter entirely and use a single-branch 404 rather than the transition endpoints' 404-vs-409 disambiguation."

requirements-completed: [ITAM-LIFE-05]

coverage:
  - id: D1
    description: "An admin can mark an asset as physically audited via POST /api/assets/{asset_id}/audit; the record always carries who asserted it (lastAuditedBy) and when the claim was filed (lastAuditRecordedAt), never as an unattributed fact"
    requirement: "ITAM-LIFE-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_sets_last_audited_at"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_accepts_caller_supplied_date"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_records_asserter_and_recording_time"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_writes_history_entry"
        status: pass
    human_judgment: false
  - id: D2
    description: "Marking an asset audited leaves lifecycleStatus/assignment completely untouched, and works on an asset in any lifecycle status including deployed — auditing is orthogonal to availability"
    requirement: "ITAM-LIFE-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_does_not_touch_lifecycle_or_assignment"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_works_on_checked_out_asset"
        status: pass
    human_judgment: false
  - id: D3
    description: "Audit-mark refusal surface: 404 for an unknown/cross-tenant asset id (nothing written), 422 for an unexpected body key, 403 without manage:assets"
    requirement: "ITAM-LIFE-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_of_missing_asset_returns_404"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_rejects_unknown_field"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestAuditMark::test_audit_mark_requires_manage_assets_permission"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/assets/reports/overdue-audit returns a fixed-365-day-interval report; the strictly-older-than boundary is pinned (equal-to-cutoff is not overdue, one instant older is); never-audited falls back to createdAt; an asset with neither date appears labelled ageBasis=unknown with daysOverdue=null rather than dropped or given a fabricated age"
    requirement: "ITAM-LIFE-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_includes_stale_audited_asset"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_excludes_recently_audited_asset"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_boundary_is_strictly_older_than_cutoff"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_falls_back_to_created_at"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_includes_asset_with_no_dates_as_unknown_basis"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_marking_audited_removes_from_report"
        status: pass
    human_judgment: false
  - id: D5
    description: "The overdue query's population is explicitly three-branched (no silent narrowing), tenant-scoped, RBAC-gated, and the route resolves correctly regardless of router registration order because it is multi-segment"
    requirement: "ITAM-LIFE-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_query_has_three_or_branches"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_report_is_tenant_scoped"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_report_requires_manage_assets_permission"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_lifecycle_audit.py::TestOverdueAuditReport::test_overdue_route_is_not_shadowed_by_legacy_asset_lookup"
        status: pass
      - kind: other
        ref: "backend/venv/bin/python -c \"import itam_lifecycle_endpoints as m; paths=[r.path for r in m.router.routes]; assert '/api/assets/reports/overdue-audit' in paths; assert all(len([s for s in p.split('/') if s]) >= 3 for p in paths)\""
        status: pass
    human_judgment: false
  - id: D6
    description: "Report-noise judgment: whether unknown-age-basis rows dominate the report on a real fleet with agent-discovered assets, to the point of being unusable"
    verification: []
    human_judgment: true
    rationale: "Requires running the report against a real tenant with agent-discovered assets and a human product judgment call on whether the volume of unknown-basis rows makes the report impractical — explicitly called out as this plan's one <human-check>, not something a unit test can classify. Not exercised this session (no live tenant with real agent-discovered assets available in this sandbox); remains outstanding per the phase's end-of-phase human-verification gate, same as 57-01/57-02's outstanding manual/UAT items."

duration: ~20min
completed: 2026-08-04
status: complete
---

# Phase 57 Plan 03: Physical Audit Mark & Overdue Report Summary

**POST /api/assets/{asset_id}/audit (attributed audit mark, orthogonal to lifecycle/assignment) and GET /api/assets/reports/overdue-audit (three-branch honest-population report with explicit ageBasis/daysOverdue), closing out ITAM-LIFE-05 and Phase 57.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-08-04T14:00Z (session)
- **Completed:** 2026-08-04T14:18:15Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments

- New `POST /api/assets/{asset_id}/audit` route: an admin can mark an asset physically audited on a given date. Unlike checkout/checkin, the `find_one_and_update` filter carries **no lifecycle guard** — a physical audit is meaningful in every lifecycle status including `deployed`, `broken` and `retired` — so a `None` return means only "does not resolve in this tenant" and raises 404 directly, no 404-vs-409 disambiguation.
- The `$set` document produced by an audit mark contains exactly four keys (`lastAuditedAt`, `lastAuditedBy`, `lastAuditRecordedAt`, `updatedAt`) and no `$unset` accompanies it — pinned by a dedicated test. `lastAuditRecordedAt` is always the server clock, even when the caller supplies their own `auditedAt` — the plan's authored attribution prohibition (T-57-16, Repudiation) is satisfied structurally: a claimed inspection can never enter the record without also saying who claimed it and when the claim was filed.
- New `GET /api/assets/reports/overdue-audit` route: computed at request time against the fixed 365-day `AUDIT_INTERVAL_DAYS` (D-03), deliberately not a background sweep — this milestone's top recorded risk is the tenant-isolation bug class background schedulers keep reintroducing in this codebase. The `$or` population is exactly three explicit branches (`_overdue_query`): stale-audited, never-audited-with-a-creation-date, and never-audited-with-no-dates-at-all. That third branch is not optional — every agent-discovered asset in this codebase lands there, since the heartbeat upsert writes `lastScanned` (refreshed every heartbeat, measuring recency not age) and never `createdAt`.
- Each row is shaped by `_overdue_row` with three derived fields: `ageBasis` (`lastAuditedAt`/`createdAt`/`unknown`), `neverAudited`, and `daysOverdue` — which is `null`, never a guess, when the basis is unknown. The boundary is strictly older-than: an asset audited exactly at the cutoff instant is not overdue, one an instant older is (pinned directly against the query shape, not just the row-shaping helper).
- Route-shadowing regression: `GET /reports/overdue-audit`'s literal, multi-segment path is proven immune to registration-order shadowing by an end-to-end test that mounts `asset_endpoints.router` (the legacy single-segment `GET /{asset_id}` router) FIRST and the lifecycle router SECOND, then confirms the request still reaches `overdue_audit_report`. The introspection gate (`all routes have ≥3 path segments`) also re-confirmed across the whole router, including the two new routes this plan adds.
- Fixed a latent test-fixture gap discovered while wiring Task 2: `itam_lifecycle_test_support.py`'s shared `mock_db` fixture had `db.assets.find_one_and_update` pre-wired but no chainable cursor for `db.assets.find()` — the report's `.find(query, projection).limit(limit).to_list(...)` chain needs the same self-referencing `MagicMock` cursor fix 57-02 applied to `assignment_history.find` (`_make_col()`'s bare `find()` breaks a multi-hop chain because `AsyncMock`'s unconfigured children default to `AsyncMock` too).

## Task Commits

Task 1 and Task 2's implementations shared the same file and several helper functions (`ACTION_AUDIT`, `AUDIT_INTERVAL_DAYS`, `_now_iso` from 57-01), so both were authored together and committed as two plan-scoped commits (test, then feat) rather than four task-scoped ones — see Deviations.

1. **Test coverage (both tasks)** — `48c0b01` (test)
2. **Implementation (both tasks)** — `c261442` (feat)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `backend/itam_models.py` — added `AuditMarkRequest` (`auditedAt`, `note`, `extra="forbid"`) directly after `CheckinRequest`
- `backend/itam_lifecycle_endpoints.py` — added `_audit_cutoff_iso()`, `mark_asset_audited` handler, `_overdue_query()`, `_overdue_row()`, `overdue_audit_report` handler; imports `AuditMarkRequest` and `timedelta`. 499 lines (under the CLAUDE.md 500-line cap)
- `backend/tests/test_itam_lifecycle_audit.py` — new file: `TestAuditMark` (9 tests) + `TestOverdueAuditReport` (10 tests, including a local `$or`/`$lt`/`$exists` query evaluator used to prove boundary/removal correctness without a live MongoDB)
- `backend/tests/itam_lifecycle_test_support.py` — added a chainable `db.assets.find()` cursor double (`limit`/`to_list`) alongside the existing `assignment_history` one

## Decisions Made

See `key-decisions` in frontmatter (Row 6 of the phase-wide spec-less-probe roll-up resolved exactly as the plan's flagged assumptions anticipated; plus three execution-time decisions: the new test file for the 500-line cap, the `_overdue_query` extraction, and the test-fixture cursor fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking, test-fixture only] `db.assets.find()` mock had no chainable cursor**
- **Found during:** Task 2, first test run against the new overdue-report route
- **Issue:** `itam_lifecycle_test_support.py`'s shared `mock_db` fixture only pre-wired `db.assets.find_one_and_update`; `db.assets.find` still used `_make_col()`'s default (`MagicMock(return_value=AsyncMock())`), whose own unconfigured child attributes default to `AsyncMock` too — so `.limit(...)` on it returned an unawaited coroutine instead of a chainable cursor, breaking the `.find().limit().to_list()` chain `overdue_audit_report` performs.
- **Fix:** Added a self-referencing `MagicMock` cursor (`limit.return_value` points back to the same cursor, `to_list` is the only `AsyncMock` leaf) to `db.assets.find`, mirroring the identical fix 57-02 applied to `assignment_history.find`.
- **Files modified:** `backend/tests/itam_lifecycle_test_support.py`
- **Verification:** `pytest backend/tests/test_itam_lifecycle_audit.py -q` — all 19 tests pass; full lifecycle suite (58 tests across 4 files) green
- **Committed in:** `48c0b01` (test commit)

**2. [Scope efficiency, not a Rule 1-4 fix] New test file rather than appending to an existing one**
- **Found during:** Planning test placement for both tasks
- **Effect:** `test_itam_lifecycle.py` was already at 396 lines; appending 19 more tests would have breached CLAUDE.md's 500-line cap. Created `backend/tests/test_itam_lifecycle_audit.py` instead, following the exact split precedent 57-01/57-02 established. This makes the plan's own artifact spec (`min_lines: 470` for `test_itam_lifecycle.py`) stale — same situation 57-01/57-02 documented for their own literal `<verify>` paths after their splits.
- **Verification:** `wc -l` confirms every touched file is under 500 lines (largest is `itam_lifecycle_endpoints.py` at 499)

**3. [Scope efficiency, not a Rule 1-4 fix] Added a private `_overdue_query(cutoff)` helper not named in the plan's artifacts**
- **Found during:** Implementing Task 2
- **Effect:** Factoring the three-branch `$or` shape into its own function (rather than inlining it in the handler) gives the handler and the test suite one shared source of truth for the query shape, instead of re-deriving it via call-arg inspection alone. Behavior is unchanged — the handler still queries with exactly the shape `<action>` specifies.
- **Verification:** `test_overdue_query_has_three_or_branches` and `test_overdue_boundary_is_strictly_older_than_cutoff` both exercise it directly and via the HTTP route

**4. [Process note, not a Rule 1-4 fix] Both tasks authored together rather than in strict RED-then-GREEN order**
- **Found during:** Implementation — `mark_asset_audited` and `overdue_audit_report` share the same file, `ACTION_AUDIT`/`AUDIT_INTERVAL_DAYS`/`_now_iso` from 57-01, and largely the same test fixtures, making them straightforward to author together (mirrors 57-01 Deviation #3's precedent for Tasks 1/2 of that plan).
- **Effect:** All 19 tests named in the plan's two `<behavior>` blocks were written and verified passing together against the final implementation, rather than watched failing individually per task before implementation existed. Commits are still ordered test-then-feat to preserve the conventional git-log shape 57-01/57-02 established.
- **Verification:** `pytest backend/tests/test_itam_lifecycle_audit.py -q` — 19/19 pass; full lifecycle suite 58/58 pass

---

**Total deviations:** 4 (1 auto-fixed test-fixture bug [Rule 3], 2 scope-efficiency notes, 1 process note)
**Impact on plan:** No scope creep beyond what the plan itself specified. The fixture fix was necessary for the report's own tests to exercise the real cursor chain; the file split and helper extraction were both CLAUDE.md/clarity-driven and left no coverage or behavior changed; combined authorship followed the exact precedent 57-01 already established for this same plan.

## Issues Encountered

None beyond the deviations documented above.

## Known Stubs

None. Every code path added in this plan reads/writes real (mocked-in-tests) collections; no hardcoded empty values, placeholder text, or unwired data paths.

## User Setup Required

None — no external service configuration required. No new indexes or migrations; this plan reuses the `assets (tenantId, lastAuditedAt)` compound index 57-01 already added.

## Next Phase Readiness

- **Phase 57 (Lifecycle & Check-In/Out) is now fully complete** — all 3 plans executed (checkout/history-write in 57-01, checkin/history-read in 57-02, physical-audit-mark/overdue-report in 57-03). All four requirements (ITAM-LIFE-02/03/04/05) are done.
- **Phase 61 (Frontend ITAM Console)** now has the complete lifecycle backend to render against: checkout/checkin/history/audit-mark/overdue-report, all under `/api/assets/{asset_id}/*` and `/api/assets/reports/*`, all RBAC-gated on `manage:assets`, all tenant-isolated.
- **Outstanding:** the phase's one `<human-check>` (report-noise judgment on a real fleet with agent-discovered assets — coverage D6 above) has not been exercised this session; it is a product-decision item for a later phase (backfill, `ageBasis` filter, or a separate "never verified" view), not a blocker for this plan's completion.
- No blockers. Full backend suite re-run after both tasks: 1639 passed / 35 skipped / 3 failed, all 3 failures pre-existing and confirmed unrelated (`test_agentic_ai` tool_choice, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type) — identical to the 57-01/57-02 baseline (`test_graphql.py` excluded from the run per the pre-existing strawberry/pydantic environment incompatibility noted in project memory).

---
*Phase: 57-lifecycle-check-in-out*
*Completed: 2026-08-04*

## Self-Check: PASSED

All 4 files created/modified by this plan (plus this SUMMARY.md) confirmed present on disk; both commits (`48c0b01`, `c261442`) confirmed present in `git log --all`.
