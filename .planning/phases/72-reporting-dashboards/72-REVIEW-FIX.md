---
phase: 72-reporting-dashboards
fixed_at: 2026-08-17T12:50:00Z
review_path: .planning/phases/72-reporting-dashboards/72-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 72: Code Review Fix Report

**Fixed at:** 2026-08-17T12:50:00Z
**Source review:** .planning/phases/72-reporting-dashboards/72-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (Critical + Warning; Info findings excluded by fix_scope)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### CR-01: Path-traversal guard uses a prefix `startswith` check without a directory-separator boundary

**Files modified:** `backend/itam_reporting_endpoints.py`
**Commit:** 59d41723
**Applied fix:** Replaced the `str(_resolved).startswith(str(_safe_dir))` prefix-match with `Path.relative_to()` inside a `try/except ValueError`, closing the sibling-directory escape (`.../static/reportsEVIL/...`) that the prefix check would incorrectly accept.

### WR-01: Custom-report "between" filter on a date field with reversed bounds silently drops all matching rows

**Files modified:** `backend/itam_reporting_filters.py`
**Commit:** 65ac0c5e
**Applied fix:** `_filters_to_mongo_query`'s `between` branch now also swaps `lo`/`hi` when both are strings and `lo > hi` (ISO-8601 date strings sort correctly under lexical comparison), matching the normalization already done for numeric bounds and mirrored in the Python-side `_condition_passes` re-verification pass. Requires human verification per the logic-bug limitation in the verification strategy — recommend confirming with a reversed-date-range custom report against a seeded asset.

### WR-02: Overdue KPI's `totalCount` double-counts an asset that is overdue on both axes

**Files modified:** `backend/itam_reporting_kpis.py`, `backend/tests/test_itam_reporting_kpis.py`
**Commits:** 6758a9d9 (initial fix), 14ed1ed8 (correction)
**Applied fix:** `_compute_overdue_kpi` now fetches the matching asset `id` sets for the audit-overdue and checkin-overdue queries separately and reports `overdueAuditCount`/`overdueCheckinCount` as `len()` of each set (numerically unchanged from before) while `totalCount` is now `len(audit_ids | checkin_ids)` — the count of distinct overdue assets rather than a sum that double-counts assets overdue on both axes.

**Post-fix verification caught a regression:** the initial commit (6758a9d9) used `async for d in db.assets.find(...)` to iterate the two id-set queries. This codebase's test doubles (`_FakeCursor`, the tenant-isolation mocks in `itam_reporting_test_support.py`) only implement `.to_list()`, matching every other `db.assets.find` call in this file — `async for` isn't supported and broke 2 of 15 tests (`TypeError: 'async for' requires an object with __aiter__ method`). Corrected in 14ed1ed8 to use `.find(...).to_list(length=None)`, the established pattern already used three other places in the same file. Also rewrote `test_audit_and_checkin_counts_separate_and_summed` (which had encoded the pre-fix sum-not-union behavior as its expected result) and added `test_asset_overdue_on_both_axes_is_not_double_counted` as an explicit regression test for the fixed bug. Full backend suite (2301 passed) and frontend suite (124 passed) reconfirmed green after the correction — no longer just "requires human verification," now automated-test-covered.

### WR-03: `ReportBuilderForm`'s "between" inputs don't validate bound ordering, feeding WR-01 directly

**Files modified:** `components/itam/ReportBuilderForm.tsx`
**Commit:** 8fd8acec
**Applied fix:** `handleAddFilter` now swaps `value`/`value2` before constructing the filter condition when the operator is `between`, both are defined, are of the same type, and `value > value2` — preventing the UI from ever emitting a reversed-bound date range that would otherwise silently return zero rows. TypeScript syntax check (`tsc --noEmit`) was unavailable in this environment (no local `typescript` install, no network for `npx`); verification fell back to Tier 1 (re-read modified section, confirmed fix present and surrounding code intact) per the verification strategy's Tier 3 fallback.

## Skipped Issues

None — all in-scope findings were fixed. IN-01 and IN-02 were excluded by `fix_scope: critical_warning` and left for a future `--fix-scope all` pass if desired.

---

_Fixed: 2026-08-17T12:50:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
