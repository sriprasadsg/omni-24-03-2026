---
status: testing
phase: 15-evidence-review-workflow
source: [15-01-SUMMARY.md, 15-REVIEW.md, 15-REVIEW-FIX.md, 15-REVIEW.iter2.md, 15-REVIEW-FIX.iter2.md, 15-REVIEW.iter3.md, 15-REVIEW-FIX.iter3.md]
started: 2026-07-02T00:00:00Z
updated: 2026-07-02T00:15:00Z
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "testing::scenarios=12"
---

## Current Test

number: 2
name: Reviewer approves evidence
expected: |
  As an admin / super_admin / compliance_reviewer, click "Approve" on a
  pending-review evidence item. The evidence status updates to "Approved"
  and the review thread shows your username, decision, and timestamp.
awaiting: user response

## Tests

### 1. Submit evidence for review

expected: |
  In a control detail view, an uploaded evidence item shows a "Submit for
  Review" button. Clicking it changes the evidence status to "Pending
  Review" and the button is replaced by reviewer actions (for authorized
  users) or a pending-review indicator (for everyone else).
result: pass

### 2. Reviewer approves evidence

expected: |
  As an admin / super_admin / compliance_reviewer, click "Approve" on a
  pending-review evidence item. The evidence status updates to "Approved"
  and the review thread shows your username, decision, and timestamp.
result: [pending]

### 3. Reviewer rejects evidence without a comment

expected: |
  Click "Reject" without entering a comment. The action is blocked with a
  validation message requiring a comment — evidence status does not change.
result: [pending]

### 4. Reviewer rejects evidence with a comment

expected: |
  Enter a comment and click "Reject". Evidence status updates to
  "Rejected" and the review thread shows the reviewer's comment.
result: [pending]

### 5. Reviewer requests changes

expected: |
  Enter a comment and click "Request Changes". Evidence status updates to
  "Needs Revision"; a "Submit for Review" button reappears so the uploader
  can resubmit.
result: [pending]

### 6. Rejected evidence can be resubmitted

expected: |
  On an evidence item with status "Rejected", the "Submit for Review"
  button is visible and clickable — evidence can re-enter the review
  queue instead of being stuck.
result: [pending]

### 7. Non-reviewer cannot approve/reject

expected: |
  Log in as a regular user (not admin/super_admin/compliance_reviewer).
  Approve/Reject/Request-Changes buttons are not shown, or attempting the
  action is blocked with a 403 permission error. "Submit for Review"
  remains available to any user.
result: [pending]

### 8. Deciding one evidence item does not corrupt a different item (CR-01, iteration 3)

expected: |
  On an asset with two evidence items — one "Pending Review" (A) and one
  in some other state, e.g. "Needs Revision" (B) — approve/reject item A.
  Only A's status changes; B's status and review thread are completely
  untouched. Before this fix, the propagation query lacked $elemMatch and
  could silently flip an unrelated evidence item's status on the same
  document — this was empirically reproduced against a live database, so
  it's worth a careful look, not just a glance.
result: [pending]

### 9. Reviewer action buttons only appear for evidence actually pending review (WR-02, iteration 2)

expected: |
  Open an evidence item that is NOT in "Pending Review" status (e.g.
  "Approved", "Rejected", or has no status yet). Approve/Reject/Request-
  Changes buttons are not shown (or are disabled) for it — before this
  fix, the buttons rendered regardless of status, so clicking them on a
  non-pending item would fail against the backend.
result: [pending]

### 10. Resubmitting while a review is already pending reuses it, not duplicates it (CR-01/WR-01, iterations 1-2)

expected: |
  Submit an evidence item for review, then (before it's decided) trigger
  "Submit for Review" again for the same item — e.g. by re-navigating and
  clicking the button again, or via a double-click/double-submit. Only
  one review thread/record exists for that evidence item; no duplicate
  pending review is created.
result: [pending]

### 11. Mismatched evidence_id in the URL is rejected without side effects (CR-01, round 1)

expected: |
  Call PATCH /api/evidence/{evidence_id}/review/{review_id} with an
  evidence_id that does NOT match the review record's actual evidenceId
  (same tenant). The request is rejected (404) and nothing is mutated —
  no status change, no audit-log entry. This is an API-level check (no
  UI path deliberately allows this), so exercise it directly against the
  backend if you have API access; otherwise mark skipped.
result: [pending]

### 12. Already-decided review cannot be re-decided

expected: |
  Attempt to approve/reject/request-changes on a review that is already
  in a decided state (approved/rejected/needs_revision), not "pending".
  The request is rejected rather than silently overwriting the prior
  decision.
result: [pending]

### 13. Pending-review queue is sorted newest-first

expected: |
  Open the tenant's pending-review queue (GET /api/evidence/pending-review
  or its UI equivalent). Items are ordered with the most recently
  submitted-for-review item first.
result: [pending]

## Summary

total: 13
passed: 1
issues: 0
pending: 12
skipped: 0

## Gaps

[none yet]
