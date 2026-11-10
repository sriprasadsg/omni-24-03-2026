---
status: testing
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-10T13:28:33Z
updated: 2026-11-10T13:33:23Z
---

## Current Test

number: 1
name: Restart the backend and re-run the G-85-3 printer ticket end to end
expected: |
  Raised as a requester on the portal at desk mode drafts, "My printer will not print" is drafted (or posted where
  the gate allows) citing only "Fixing a printer that will not print", not handed off. If any reply is refused, the
  staff note and the Activity row name the failing rule, and the requester sees only "A person from IT will look at this."
awaiting: user response

## Tests

# UAT round 4 (after the third gap round 85-37..85-42). Round 3's file (2 passed, gaps G-85-3, G-85-4b, G-85-5)
# is in git at 31754ff6e / 8c3507d6f; those gaps are closed in code per 85-VERIFICATION.md (811b676e7).

### 1. Restart the backend and re-run the G-85-3 printer ticket end to end
expected: Raised as a requester on the portal at desk mode drafts, "My printer will not print" is drafted (or posted where the gate allows) citing only "Fixing a printer that will not print", not handed off; if any reply is refused, the staff note and the Activity row name the failing rule, and the requester sees only "A person from IT will look at this."
result: [pending]

### 2. Publish the UI build (dist-new) and check the Tickets screen as a User-role requester, then as an analyst
expected: The requester sees no status buttons, Escalate, Merge, Watchers, Approve/Deny, attachment delete, Work Log / Links tabs, row checkboxes, bulk bar or board drag; New Ticket has no Assignee, Group, Due Date, SLA Hours or approval input; the "staff only" hint is absent; own tickets, the answer panel, comments to IT and file upload/download still work. The analyst sees every control again.
result: [pending]

### 3. Windows tray round trip (agent 2.1.18 published), the tray half of UAT test 3
expected: Raise a Ticket from the tray, see the AI-assisted answer pop-up, and "this fixed it" / "I still need help" behave as on the portal.
result: [pending]

### 4. After the restart, check G-85-5 live
expected: A ticket created by a requester with watchers, assignee or approval_required in the body keeps none of the six staff-only fields; a pending-agent notice for a tenant with two users is seen only by a tenant admin in the feed, and no non-admin socket receives it.
result: [pending]

### 5. Decide on review findings WR-701 and WR-702 before deployment
expected: Either the fixes (reportFailure on the title edit and the Start button of security-incident tickets, a catch in handleComment's staff-note branch, a try/catch in handleUpload; load() in the bulk catch) or a written acceptance.
result: pass
note: "User chose to fix both (2026-11-10, 'fix WR-701 and WR-702 now'). Fixed in 3d8a39763: title rename and Start Remediation go through handlePatch (error toast), a refused staff note and a refused upload show a toast, bulk delete uses allSettled (only the deleted tickets leave the list and the selection, the list reloads after any failure). Seven new cases in src/__tests__/TicketsStaffActionErrors.test.tsx, each failing on the previous code; disposition WR-701/WR-702 fixed (open 33 of 51). Part of the UI build; verify the visible behaviour in test 2 after the publish."

## Summary

total: 5
passed: 1
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
