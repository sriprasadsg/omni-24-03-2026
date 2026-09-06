---
status: testing
phase: 02-manual-evidence-uploads
source:

  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md

started: 2026-07-28T00:00:00Z
updated: 2026-07-28T00:00:00Z
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "testing::scenarios=7"
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Upload manual evidence (happy path)
expected: |
  In a compliance framework's asset control, pick a valid file (PDF/PNG/JPG/DOCX/XLSX, ≤25 MB) and upload it as evidence. Upload succeeds (no 400/boundary error), and the file appears in that control's evidence list as a new row tagged with a green "Manual" badge.
awaiting: user response

## Tests

### 1. Upload manual evidence (happy path)

expected: Pick a valid file (PDF/PNG/JPG/DOCX/XLSX, ≤25 MB) and upload as evidence for an asset control. Upload succeeds with no 400/multipart-boundary error; the new evidence row appears with a green "Manual" badge.
result: [pending]

### 2. Description saved with upload

expected: Type text in the "Description (optional)" input before uploading. After upload, the description is stored on that evidence record (visible on the row / persists after refresh), and the input clears for the next upload.
result: [pending]

### 3. Oversize file rejected (>25 MB)

expected: Attempt to upload a file larger than 25 MB. Server rejects it (413 / size-limit error surfaced in the UI); no evidence row is added.
result: [pending]

### 4. Magic-byte mismatch rejected

expected: Rename a non-matching file to a permitted extension (e.g. a text file saved as `evil.pdf`) and upload. Server rejects it (400 / invalid-file error); no evidence row is added.
result: [pending]

### 5. Manual vs Automated source badges

expected: A control that has both manually-uploaded and system/agent-generated evidence shows a green "Manual" badge on manual rows and a blue "Automated" badge on automated rows.
result: [pending]

### 6. Delete manual evidence (confirm + refresh)

expected: A delete (trash) button appears only on Manual rows, not Automated ones. Clicking it shows a confirm dialog; confirming deletes the evidence, the row disappears after the list re-fetches, and the underlying file is removed.
result: [pending]

### 7. Delete authorization rules

expected: A non-owner, non-admin cannot delete someone else's evidence (403 / denied); an admin can delete any manual evidence including cross-tenant; automated (systemGenerated) evidence cannot be deleted (403), matching the missing/hidden delete button.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]
