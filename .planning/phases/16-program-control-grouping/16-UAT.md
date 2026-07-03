---
status: complete
phase: 16-program-control-grouping
source: [16-01-PLAN.md, 16-REVIEW.md, 16-REVIEW-FIX.md]
started: 2026-07-03T00:00:00Z
updated: 2026-07-04T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Create a new program
expected: |
  On the Programs dashboard, click "+ New Program". Fill in name,
  description, framework, and owner, then submit. The new program appears
  in the list with 0 controls and an "in progress" status badge.
result: pass

### 2. Program list shows status rollup, control count, and progress bar
expected: |
  Each program card shows a status badge (compliant / at risk / in
  progress), the number of controls (e.g. "Controls: 4"), and a progress
  bar reflecting passing vs. total controls.
result: pass

### 3. Manage Controls — add and remove controls via the picker modal
expected: |
  Click "Controls" on a program card. A modal opens with a searchable,
  checkable list of controls pre-selected with the program's current
  controls. Check/uncheck some controls and click "Save". The modal
  closes, the list refreshes, and the program's control count reflects
  your changes.
result: pass

### 4. Status shows "compliant" when passing controls are high and none are failing
expected: |
  For a program where at least 80% of controls pass and none are failing,
  the status badge reads "compliant" and is styled green.
result: pass

### 5. Status shows "at risk" when any control is failing
expected: |
  For a program with at least one control in a failing/non-compliant
  state, the status badge reads "at risk" and is styled red — regardless
  of how many other controls pass.
result: pass

### 6. Controls awaiting evidence show "in progress", not "at risk" (WR-04 fix)
expected: |
  For a program where some controls have status "Pending_Evidence" (no
  pass/fail result yet) and none are actually failing, the status badge
  reads "in progress" (amber) — NOT "at risk". Before this fix, pending
  evidence was miscounted as failing, so this is worth checking carefully.
result: pass

### 7. Deleting a program requires confirmation and does not delete evidence (WR-06)
expected: |
  Click "Delete" on a program. A confirmation dialog appears ("Delete
  this program? This cannot be undone."). Confirming removes the program
  from the list. The underlying control evidence/compliance results are
  NOT deleted — only the program grouping document is removed.
result: pass

### 8. Programs are tenant-isolated
expected: |
  A program created under one tenant/organization is not visible or
  accessible (list or direct fetch) from a different tenant account.
result: pass

### 9. Backend test suite passes
expected: |
  Run the program_service test suite (`pytest backend/tests/test_program_service.py -v`).
  All 7 tests pass green.
result: pass
source: automated

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
