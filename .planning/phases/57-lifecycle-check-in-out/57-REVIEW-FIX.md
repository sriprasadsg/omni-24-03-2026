---
phase: 57-lifecycle-check-in-out
fixed_at: 2026-08-04T18:23:50Z
review_path: .planning/phases/57-lifecycle-check-in-out/57-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 57: Code Review Fix Report

**Fixed at:** 2026-08-04T18:23:50Z
**Source review:** .planning/phases/57-lifecycle-check-in-out/57-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (critical_warning scope: 1 critical + 5 warning; Info findings IN-01/IN-02/IN-03 out of scope, not attempted)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: Malformed `createdAt` timestamp breaks the overdue-audit report's date math for every manually-created asset

**Files modified:** `backend/itam_asset_endpoints.py`, `backend/tests/test_itam_lifecycle_audit.py`
**Commit:** `b982855`
**Applied fix:** Removed the manual `+ 'Z'` suffix in `create_manual_asset`'s timestamp expression. `datetime.now(timezone.utc).isoformat(timespec='milliseconds')` already produces a valid, parseable UTC-offset ISO-8601 string, so appending a literal `'Z'` was producing a doubly-suffixed, unparseable value (`...+00:00Z`) that made `_overdue_row`'s `datetime.fromisoformat` raise on every manually-created, never-audited asset (silently null-ing `daysOverdue`). Added a regression test (`test_overdue_parses_real_create_manual_asset_timestamp`) that round-trips the real `create_manual_asset` timestamp expression through `_overdue_row`'s parsing and asserts `daysOverdue` is a real number, not `None`.

### WR-01: No compensating rollback when the history write fails after the asset mutation already committed

**Files modified:** `backend/itam_lifecycle_endpoints.py`, `backend/itam_lifecycle_service.py`, `backend/tests/test_itam_lifecycle_expansion.py`
**Commit:** `729e9cbb8`
**Applied fix:** All three write paths (`checkout_asset`, `checkin_asset`, `mark_asset_audited`) now capture the pre-mutation document via `return_document=ReturnDocument.BEFORE` on the same guarded `find_one_and_update` call (no extra read — this deliberately preserves an existing test invariant, `test_checkout_guard_is_in_the_update_filter`'s `assert mock_db.assets.find_one.await_count == 0`, that forbids a separate read-then-write pair on the success path). The after-state returned to the caller is reconstructed in Python from the pre-image plus the exact `$set`/`$unset` each handler already issues. If the subsequent `write_history` call raises, a new `_revert_on_history_failure` helper reverts the asset to its pre-image (setting fields back to their prior values, or unsetting fields that were absent before), so the 500 response reflects the asset's real, unchanged state and a caller retry does not hit a stale 409. The helper lives in `itam_lifecycle_service.py` (private, leading-underscore, does not appear in that module's asserted public surface) rather than `itam_lifecycle_endpoints.py`, to help keep the endpoints file within the project's 500-line guideline (see note below). Added a regression test, `test_checkout_reverts_asset_when_history_write_fails`, asserting the compensating `find_one_and_update` call restores `lifecycleStatus` and unsets the newly-added checkout fields when `write_history` raises.

### WR-02: Caller-supplied date strings are unvalidated and feed straight into report date-math and query comparisons

**Files modified:** `backend/itam_models.py`, `backend/tests/test_itam_lifecycle.py`, `backend/tests/test_itam_lifecycle_audit.py`
**Commit:** `222e34a`
**Applied fix:** Added a shared `_validate_iso8601_date` Pydantic `field_validator`, applied to both `CheckoutRequest.expectedReturnDate` and `AuditMarkRequest.auditedAt`. It rejects (422) any value `datetime.fromisoformat` cannot parse after the same `'Z'` → `'+00:00'` normalization `_overdue_row` already applies downstream, so a malformed caller value is refused at the API boundary instead of silently corrupting the overdue report's raw lexicographic `$lt` comparison or falling into the null-`daysOverdue` fallback. Verified the existing `"2026-09-01"` date-only test fixture for `expectedReturnDate` still validates (Python 3.11+'s `fromisoformat` accepts date-only strings). Added regression tests for both fields (`test_checkout_rejects_non_iso8601_expected_return_date`, `test_audit_mark_rejects_non_iso8601_audited_at`).

### WR-03: Disposed assets are never excluded from the overdue-audit report

**Files modified:** `backend/itam_lifecycle_endpoints.py`, `backend/tests/test_itam_lifecycle_audit.py`
**Commit:** `1787ee3`
**Applied fix:** Added `"lifecycleStatus": {"$ne": LifecycleStatus.DISPOSED.value}` as a top-level key in `_overdue_query` (forms an implicit AND with the existing `$or` age-basis branches per MongoDB query semantics), so an asset marked `disposed` is excluded from the report regardless of its age basis. Added two regression tests: one asserting the query shape directly, and one asserting the exclusion is actually wired into the report route's `db.assets.find()` call.

### WR-04: Stale comment misdescribes router registration order and references a route that does not exist in this file

**Files modified:** `backend/itam_asset_endpoints.py`
**Commit:** `0b1183f`
**Applied fix:** Rewrote the module-level comment to state the facts verified against the current codebase: this file defines only `POST ""` (no `GET /{asset_id}`), so it has nothing that could be shadowed by or shadow `asset_endpoints.py`; `router_registry.py` in fact registers this router *before* `asset_endpoints.py` (the opposite of what the stale comment claimed); and the routes that are genuinely shadowing-sensitive live in `itam_lifecycle_endpoints.py`, whose own docstring already covers that reasoning correctly.

### WR-05: Duplicate router registrations in `router_registry.py`

**Files modified:** `backend/router_registry.py`
**Commit:** `9c0b119`
**Applied fix:** Removed the two redundant `_load(app, "saas_posture_checks_endpoints", "router")` calls (was called three times in a row) and the one redundant `_load(app, "oscal_endpoints", "router")` call (was called twice), keeping exactly one registration per module. Also checked the rest of the required/core registration list for any other same-module-and-attribute duplicates (found none — a `trust_endpoints` pair that initially looked duplicate actually registers two distinct attributes, `router` and `public_router`, from the same module, which is a legitimate pattern, not a bug).

## Skipped Issues

None — all 6 in-scope findings (critical_warning scope) were fixed.

## Notes

- **File-length trade-off (WR-01):** `backend/itam_lifecycle_endpoints.py` ends this fix session at 528 lines, modestly over the project's CLAUDE.md 500-line guideline (was 500 before this session). The bulk of the new compensating-rollback logic (`_revert_on_history_failure`, ~50 lines) was moved to `itam_lifecycle_service.py` specifically to minimize this overage, and inline comments at each of the three call sites were compacted. Getting fully under 500 without WR-01's fix would have required either trimming substantial pre-existing, intentionally detailed documentation comments unrelated to this finding, or a larger structural split of the endpoints file into multiple router modules — both judged out of scope for this fix pass. Flagging for awareness; a follow-up phase could split `itam_lifecycle_endpoints.py` (e.g. checkout/checkin vs. audit/report) the same way the test suite for this phase was already split across multiple files.
- Info-tier findings (IN-01 duplicated `_now_iso()`, IN-02 `checkout_asset` docstring precedence wording, IN-03 8-hex-char history id entropy) were out of scope for this run (`fix_scope: critical_warning`) and were not attempted.
- 88 tests pass across all touched test files after all 6 fixes (`test_itam_foundation.py`, `test_itam_lifecycle.py`, `test_itam_lifecycle_expansion.py`, `test_itam_lifecycle_audit.py`, `test_itam_lifecycle_history.py`, `test_saas_posture_checks.py`, `test_oscal_export.py`).

---

_Fixed: 2026-08-04T18:23:50Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
