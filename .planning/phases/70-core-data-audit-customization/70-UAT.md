---
status: testing
phase: 70-core-data-audit-customization
source: [65-VERIFICATION.md]
started: 2026-08-12T15:30:00Z
updated: 2026-08-12T15:30:00Z
---

## Current Test

number: 1
name: Custom field persistence + usage warning (65-01)
expected: |
  Catalog → Models → Manage Fields: add a select field with two options, save, reload the page,
  confirm it persists with its options; then remove a field that reports a non-zero usage count
  and confirm the warning names it before saving. Field definition survives reload; removal
  warning names the affected key and asset count before Save.
awaiting: user response

## Tests

### 1. Custom field persistence + usage warning (65-01)
expected: Field definition survives reload; removal warning names the affected key and asset count before Save.
result: [pending]

### 2. Activity tab live confirmation (65-02)
expected: |
  Create/check out an asset, open the Activity tab, confirm the change appears with
  username/action/asset id; filter by entity id to that asset alone; click "Verify ledger
  integrity" and confirm it reports a valid chain.
result: [pending]

### 3. CSV round trip (65-03)
expected: |
  Export downloads a CSV with a header and asset rows; edit two rows (one valid, one with a bad
  select-type custom-field value), dry-run re-upload and confirm the report names only the bad
  row and nothing is created; untick dry run, import for real, and confirm the good row appears
  in the asset list and both the creation and the batch appear in Activity.
result: [pending]

### 4. Settings live application + non-admin refusal (65-04)
expected: |
  Settings tab: set company name/logo URL/primary colour, save, confirm header and active-tab
  underline change immediately; reload and confirm persistence; switch interface language and
  confirm tab labels change; confirm the settings change appears in Activity; sign in as a
  non-admin and confirm save is refused with a clear message.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
