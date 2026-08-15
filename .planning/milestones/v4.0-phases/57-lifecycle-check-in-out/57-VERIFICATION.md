---
phase: 57-lifecycle-check-in-out
verified: 2026-08-04T18:34:58Z
status: passed
score: 17/17 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 57: Lifecycle & Check-In/Out Verification Report

**Phase Goal:** Give users a real "who has this" workflow — assign assets to a person or
location, return them to stock, and keep a trustworthy, append-only history of every hand-off,
plus a way to confirm assets are still where records say they are.
**Verified:** 2026-08-04T18:34:58Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria + Plan must_haves, merged)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Admin can check out a deployable asset to a user via `POST /api/assets/{id}/checkout`; asset returns `lifecycleStatus: deployed` with `assignedToType`/`assignedToId` (ITAM-LIFE-02) | ✓ VERIFIED | `itam_lifecycle_endpoints.py:93-199` (`checkout_asset`); `test_checkout_to_user_end_to_end` passes |
| 2 | Checkout to a location overwrites `locationId` with the target id (D-02); user checkout leaves it untouched | ✓ VERIFIED | Lines 127-131; `test_checkout_to_location_overwrites_location_id`, `test_checkout_to_user_produces_no_location_id_key` pass |
| 3 | Checkout refused 409 (non-deployable), 404 (unknown/cross-tenant asset), 400 (unresolvable target, no mutation), 403 (no `manage:assets`) | ✓ VERIFIED | Lines 144-161, `_resolve_target` (75-90); 4 refusal tests pass in `test_itam_lifecycle_expansion.py` |
| 4 | Missing-`lifecycleStatus` (agent-discovered) assets are checkoutable (absent key = deployable) | ✓ VERIFIED | `_deployable_guard()` (49-60); `test_checkout_of_agent_asset_without_lifecycle_key_succeeds` passes |
| 5 | Two concurrent checkouts on one asset yield exactly one success, one 409 (real atomic guard, not scripted) | ✓ VERIFIED | Guard lives inside `find_one_and_update` filter (line 144); `test_concurrent_checkout_only_one_succeeds` uses genuine in-memory fake honoring the guard, passes |
| 6 | An admin can check a deployed asset in via `POST /api/assets/{id}/checkin`; returns to stock with `lifecycleStatus: deployable` (ITAM-LIFE-03) | ✓ VERIFIED | `checkin_asset` (202-302); `test_checkin_returns_asset_to_stock` passes |
| 7 | Check-in clears `assignedToType`/`assignedToId`/`checkedOutAt`/`checkedOutBy`/`expectedReturnDate` via `$unset`, retains `locationId` | ✓ VERIFIED | Lines 231-241; `test_checkin_clears_assignment_fields`, `test_checkin_retains_location_id` pass |
| 8 | Check-in of a non-deployed asset refused 409, no history written; two concurrent check-ins yield one success/one 409 | ✓ VERIFIED | `_deployed_guard()` (63-72, no missing-key admission); `test_checkin_of_asset_not_checked_out_returns_409`, `test_concurrent_checkin_only_one_succeeds` pass |
| 9 | Every successful checkout/checkin/audit writes exactly one immutable `assignment_history` entry (asset, action, target, actor, ts); target stored as id reference only, never personal data (ITAM-LIFE-04) | ✓ VERIFIED | `write_history` calls at 176, 278, 402; PD-04 enforced by never reading email/name into the record; `test_checkout_history_entry_stores_reference_not_personal_data` passes |
| 10 | `itam_lifecycle_service.py` exposes exactly `write_history`/`list_history`, no alter/remove path anywhere; no PUT/PATCH/DELETE route on the router | ✓ VERIFIED | Introspection commands re-run directly: public surface == `['list_history','write_history']`; router has zero PUT/PATCH/DELETE routes (confirmed live, not just via SUMMARY claim) |
| 11 | A history-write failure surfaces as 500, not a false success — and (WR-01 fix) the asset mutation is reverted so a retry doesn't hit a stale 409 | ✓ VERIFIED | `_revert_on_history_failure` (`itam_lifecycle_service.py:76-127`) wired at all 3 call sites; `test_checkout_reverts_asset_when_history_write_fails` passes (ran directly) |
| 12 | `GET /api/assets/{id}/history` returns full trail newest-first, deterministic total order (`ts` desc, `_id` desc tiebreak); empty history is 200+`[]`, never 404/null; unknown/cross-tenant id is 404 identically for both (ITAM-LIFE-04) | ✓ VERIFIED | `list_history` sort (service.py:59); `list_assignment_history` (305-344); ordering/empty/tenant tests in `test_itam_lifecycle_history.py` all pass |
| 13 | Admin can mark an asset physically audited via `POST /api/assets/{id}/audit`; record always carries `lastAuditedBy` + server-clock `lastAuditRecordedAt`, even with caller-supplied `auditedAt` (attribution, ITAM-LIFE-05) | ✓ VERIFIED | `mark_asset_audited` (347-423), lines 375-382; `test_audit_mark_records_asserter_and_recording_time` passes |
| 14 | Audit mark is orthogonal to lifecycle/assignment (no `lifecycleStatus`/assignment key touched, no `$unset`), works on any status incl. `deployed` | ✓ VERIFIED | `$set` has exactly 4 keys, no `$unset` (377-382); `test_audit_mark_does_not_touch_lifecycle_or_assignment`, `test_audit_mark_works_on_checked_out_asset` pass |
| 15 | `GET /api/assets/reports/overdue-audit` reports assets overdue by fixed 365-day interval; strictly-older-than boundary; falls back to `createdAt`; assets with neither date included as `ageBasis: unknown`/`daysOverdue: null` rather than dropped or faked (ITAM-LIFE-05) | ✓ VERIFIED | `_overdue_query`/`_overdue_row` (426-481); all 6 boundary/fallback/unknown-basis tests pass; CR-01 fix (removed doubly-suffixed `Z` in `itam_asset_endpoints.py:122`) confirmed present, with regression test `test_overdue_parses_real_create_manual_asset_timestamp` |
| 16 | Overdue report route is multi-segment and provably immune to router-registration-order shadowing; RBAC-gated; tenant-scoped; excludes disposed assets (WR-03 fix) | ✓ VERIFIED | Route `/reports/overdue-audit`; introspection confirms all 5 lifecycle routes have ≥3 segments; `test_overdue_route_is_not_shadowed_by_legacy_asset_lookup`, `test_overdue_query_excludes_disposed_assets` pass |
| 17 | `POST /api/assets` (manual asset creation) returns 201 through the real, non-awaited `cache_service.invalidate_cache` call path, repairing a Phase-56 defect Phase-57 depends on | ✓ VERIFIED | `itam_asset_endpoints.py:145` — `invalidate_cache("assets:*")` unawaited; `test_manual_asset_creation_survives_real_cache_invalidation` passes |

**Score:** 17/17 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_lifecycle_service.py` | Append-only `write_history`/`list_history` module | ✓ VERIFIED | 126 lines; public surface exactly 2 functions (confirmed by live introspection, not SUMMARY claim); also holds private `_apply_known_delta`/`_revert_on_history_failure` (WR-01 fix, correctly excluded from public-surface check by leading underscore) |
| `backend/itam_lifecycle_endpoints.py` | Lifecycle router: checkout/checkin/history/audit/overdue-report | ✓ VERIFIED | 534 lines — **exceeds** the plan's stated <500-line acceptance criterion (documented, deliberate trade-off per REVIEW-FIX.md note; see Anti-Patterns/Gaps below) |
| `backend/itam_models.py` | `CheckoutRequest`, `CheckinRequest`, `AuditMarkRequest`, all `extra=forbid` | ✓ VERIFIED | All 3 classes present with `ConfigDict(extra="forbid")`; `expectedReturnDate`/`auditedAt` ISO-8601 validated (WR-02 fix) |
| `backend/router_registry.py` | `itam_lifecycle_endpoints` registered adjacent to `itam_asset_endpoints` | ✓ VERIFIED | Line 84, immediately after line 83's `itam_asset_endpoints` registration |
| `backend/database.py` | 3 new indexes: `assignment_history` x2, `assets.lastAuditedAt` | ✓ VERIFIED | Lines 295-298; no `expireAfterSeconds` on `assignment_history` (append-only guarantee) |
| `backend/tests/test_itam_lifecycle*.py` (4 files) | Full behavioral test coverage | ✓ VERIFIED | 77 lifecycle+foundation tests, all pass live (not re-stated from SUMMARY) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `router_registry.py` | `itam_lifecycle_endpoints.py` | `_load(app, "itam_lifecycle_endpoints", "router")` | ✓ WIRED | Confirmed at registry line 84 |
| `itam_lifecycle_endpoints.py` | `itam_asset_endpoints.py` | imports `_require_itam_admin` (not redefined) | ✓ WIRED | Line 20 import; `grep -c 'async def _require_itam_admin' itam_lifecycle_endpoints.py` = 0 |
| `itam_lifecycle_endpoints.py` | `itam_lifecycle_service.py` | `write_history`/`list_history`/`_apply_known_delta`/`_revert_on_history_failure` | ✓ WIRED | Import line 22-24; called at every transition endpoint |
| `itam_lifecycle_endpoints.py` | `database.py` | `get_database()` tenant-isolated handle | ✓ WIRED | Line 18 import, called in every handler |
| `itam_lifecycle_endpoints.py` (history route) | `itam_lifecycle_service.list_history` | delegated read, not inline query | ✓ WIRED | Line 343 |

### Behavioral Spot-Checks (live, run by verifier — not SUMMARY-reported)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full lifecycle+foundation test suite | `pytest backend/tests/test_itam_lifecycle*.py backend/tests/test_itam_foundation.py -q` | 77 passed | ✓ PASS |
| Append-only public surface | live introspection of `itam_lifecycle_service` | `['list_history', 'write_history']` | ✓ PASS |
| No mutating routes / all multi-segment | live introspection of `itam_lifecycle_endpoints.router` | 5 routes, all ≥3 segments, zero PUT/PATCH/DELETE | ✓ PASS |
| WR-01 revert-on-history-failure | `pytest -k test_checkout_reverts_asset_when_history_write_fails` | 1 passed | ✓ PASS |
| WR-02 ISO-8601 validation | `pytest -k iso8601` (2 tests) | 2 passed | ✓ PASS |
| WR-03 disposed-asset exclusion | `pytest -k disposed` (2 tests) | 2 passed | ✓ PASS |
| Full backend regression suite | `pytest backend/tests -q --ignore=test_graphql.py` | 1645 passed / 35 skipped / 3 failed | ✓ PASS — the 3 failures (`test_agentic_ai` tool_choice, `test_e2e_integration` golden path, `test_rust_heartbeat_parity`) are the pre-existing, unrelated failures recorded in project memory baseline, not new regressions from this phase |
| Concurrency guard is a real in-memory fake, not a scripted sequence | code inspection, `test_itam_lifecycle_expansion.py:209-233` | Confirmed synchronous stateful fake honoring the guard | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ITAM-LIFE-02 | 57-01 | Check out to user/location, gated on deployable | ✓ SATISFIED | Truths 1-5 |
| ITAM-LIFE-03 | 57-02 | Check in, returns to stock, clears assignment | ✓ SATISFIED | Truths 6-8 |
| ITAM-LIFE-04 | 57-01, 57-02 | Append-only assignment history/audit trail | ✓ SATISFIED | Truths 9-12 |
| ITAM-LIFE-05 | 57-03 | Mark physically audited + overdue-audit report | ✓ SATISFIED | Truths 13-16 |

REQUIREMENTS.md maps exactly these 4 IDs to Phase 57 (lines 76-79, 97) — no orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/itam_lifecycle_endpoints.py` | whole file | 534 lines vs. the plan's stated <500-line acceptance criterion | ℹ️ Info | Deliberate, documented trade-off (REVIEW-FIX.md notes) made to fix WR-01 (compensating rollback) without gutting comments; the bulk of the new logic was deliberately moved to `itam_lifecycle_service.py` to minimize the overage. Not a functional gap — flagged for a future split (checkout/checkin vs. audit/report), not a phase-goal blocker. |

No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers found in any file this phase created or modified. No stub returns, no hardcoded-empty data paths, no console.log-only implementations.

### Code Review Findings (57-REVIEW.md / 57-REVIEW-FIX.md cross-check)

1 critical (CR-01, malformed `createdAt` breaking overdue-report date math) + 5 warnings (WR-01 through WR-05) were found by the phase's code review and independently confirmed fixed here by re-reading the modified source and re-running each fix's dedicated regression test live:
- CR-01 (malformed `Z`-suffixed timestamp): fixed, `itam_asset_endpoints.py:122`, confirmed.
- WR-01 (no compensating rollback on history-write failure): fixed via `_revert_on_history_failure`, confirmed wired at all 3 call sites and test passes.
- WR-02 (unvalidated date strings): fixed via `_validate_iso8601_date` field validator, confirmed on both `CheckoutRequest.expectedReturnDate` and `AuditMarkRequest.auditedAt`.
- WR-03 (disposed assets never excluded from overdue report): fixed via `$ne` clause in `_overdue_query`, confirmed.
- WR-04 (stale routing-order comment): fixed, confirmed by reading the corrected comment.
- WR-05 (duplicate router registrations): fixed, confirmed `saas_posture_checks_endpoints`/`oscal_endpoints` each registered once now.

3 info-tier findings (IN-01/02/03) were explicitly out of scope for the fix pass and remain open — none affect phase-goal achievement (duplicated helper, docstring wording, 8-hex-char ID entropy on an internal identifier).

### Human Verification Required

None required to pass this phase. One item remains explicitly deferred by the phase's own plan as a human/product-decision item, not a phase-completion blocker:

1. **Overdue-report noise on a real fleet** (57-03's one `<human-check>`, coverage row D6 in 57-03-SUMMARY.md)
   - **Test:** Run `GET /api/assets/reports/overdue-audit` against a real tenant with agent-discovered assets and judge whether `ageBasis: unknown` rows dominate the report to the point of being impractical.
   - **Expected:** A human product judgment on whether a follow-up (backfill, `ageBasis` filter, or separate "never verified" view) is needed in a later phase.
   - **Why human:** This is a UX/product-usability judgment on real fleet data volume, not a correctness question — the report's behavior (include, don't hide, don't fabricate) is already fully test-verified and matches the plan's explicit design intent. Not exercised this session per the SUMMARY (no live tenant available); explicitly scoped by the plan as a later-phase product decision, not a Phase-57 completion gate.

### Gaps Summary

None. All 17 must-have truths across the 3 plans are verified against live code and live test runs (not SUMMARY claims). The one prior REVIEW-flagged critical and all 5 warnings are confirmed fixed with passing regression tests re-run directly by this verification. The full backend suite shows no new regressions beyond the 3 pre-existing, unrelated failures already recorded in project memory. The single deviation worth flagging (534 vs. <500 lines on `itam_lifecycle_endpoints.py`) is a documented, deliberate trade-off with no functional impact and does not block phase completion.

---

_Verified: 2026-08-04T18:34:58Z_
_Verifier: Claude (gsd-verifier)_
