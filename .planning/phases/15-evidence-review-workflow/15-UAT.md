---
status: complete
phase: 15-evidence-review-workflow
source: [15-01-PLAN.md, 15-REVIEW.md, 15-REVIEW-FIX.md]
started: 2026-07-02T00:00:00Z
updated: 2026-07-02T00:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Submit evidence for review
expected: |
  In a control detail view, an uploaded evidence item shows a "Submit for
  Review" button. Clicking it changes the evidence status to "Pending
  Review" and the button is replaced by reviewer actions (for authorized
  users) or a pending-review indicator (for everyone else).
result: pass

### 2. Review panel loads without authentication errors (WR-01)
expected: |
  Open the Evidence Review panel for any evidence item in the running app.
  The review thread and action buttons load successfully with no 401s in
  the browser console/network tab — this was completely broken before the
  WR-01 fix (panel used raw fetch() with no auth header).
result: pass

### 3. Reviewer approves evidence
expected: |
  As an admin / super_admin / compliance_reviewer, click "Approve" on a
  pending-review evidence item. The evidence status updates to "Approved"
  and the review thread shows your username, decision, and timestamp.
result: pass

### 4. Reviewer rejects evidence without a comment
expected: |
  Click "Reject" without entering a comment. The action is blocked with a
  validation message requiring a comment — evidence status does not change.
result: pass

### 5. Reviewer rejects evidence with a comment
expected: |
  Enter a comment and click "Reject". Evidence status updates to
  "Rejected" and the review thread shows the reviewer's comment.
result: pass

### 6. Reviewer requests changes
expected: |
  Enter a comment and click "Request Changes". Evidence status updates to
  "Needs Revision"; a "Submit for Review" button reappears so the uploader
  can resubmit.
result: pass

### 7. Non-reviewer cannot approve/reject
expected: |
  Log in as a regular user (not admin/super_admin/compliance_reviewer).
  Approve/Reject/Request-Changes buttons are not shown, or attempting the
  action is blocked with a 403 permission error. "Submit for Review"
  remains available to any user.
result: pass

### 8. Cross-tenant review isolation (CR-01)
expected: |
  A reviewer in one tenant cannot approve/reject/request-changes on a
  review record belonging to a different tenant, even when given that
  review's ID directly (e.g. via API). The request is rejected rather
  than silently succeeding — this was the cross-tenant IDOR closed by
  the CR-01 fix.
result: pass

### 4. Reviewer rejects evidence without a comment
expected: |
  Click "Reject" without entering a comment. The action is blocked with a
  validation message requiring a comment — evidence status does not change.
result: [pending]

### 5. Reviewer rejects evidence with a comment
expected: |
  Enter a comment and click "Reject". Evidence status updates to
  "Rejected" and the review thread shows the reviewer's comment.
result: [pending]

### 6. Reviewer requests changes
expected: |
  Enter a comment and click "Request Changes". Evidence status updates to
  "Needs Revision"; a "Submit for Review" button reappears so the uploader
  can resubmit.
result: [pending]

### 7. Non-reviewer cannot approve/reject
expected: |
  Log in as a regular user (not admin/super_admin/compliance_reviewer).
  Approve/Reject/Request-Changes buttons are not shown, or attempting the
  action is blocked with a 403 permission error. "Submit for Review"
  remains available to any user.
result: [pending]

### 8. Cross-tenant review isolation (CR-01)
expected: |
  A reviewer in one tenant cannot approve/reject/request-changes on a
  review record belonging to a different tenant, even when given that
  review's ID directly (e.g. via API). The request is rejected rather
  than silently succeeding — this was the cross-tenant IDOR closed by
  the CR-01 fix.
result: [pending]

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
