---
status: testing
phase: 85-first-line-service-desk
source: [85-VERIFICATION.md]
started: 2026-11-10T13:28:33Z
updated: 2026-11-10T14:09:52Z
---

## Current Test

number: 3
name: Windows tray round trip (agent 2.1.18 published), the tray half of UAT test 3
expected: |
  Raise a Ticket from the tray, see the AI-assisted answer pop-up, and "this fixed it" / "I still need help" behave
  as on the portal.
awaiting: a Windows PC enrolled in ABC with agent 2.1.18 (server side of the tray verified; see test 3)

## Tests

# UAT round 4 (after the third gap round 85-37..85-42). Round 3's file (2 passed, gaps G-85-3, G-85-4b, G-85-5)
# is in git at 31754ff6e / 8c3507d6f; those gaps are closed in code per 85-VERIFICATION.md (811b676e7).

### 1. Restart the backend and re-run the G-85-3 printer ticket end to end
expected: Raised as a requester on the portal at desk mode drafts, "My printer will not print" is drafted (or posted where the gate allows) citing only "Fixing a printer that will not print", not handed off; if any reply is refused, the staff note and the Activity row name the failing rule, and the requester sees only "A person from IT will look at this."
result: pass
note: "Run by Claude against the live API at the user's request, 2026-11-10 13:43 UTC, after the backend restart at 13:38 (PID 3332111, round-3 backend live), with temporary ABC accounts (archived to ~/omni-archives/uat85-r4/ and removed). The requester raised 'My printer will not print' (incident, portal): desk job done, reason drafted; the analyst's desk view shows a draft citing only 'Fixing a printer that will not print' (answer: 'Check the printer's power, paper, and toner/ink, and clear any paper jams. Also, ensure the correct printer is chosen in the print dialog.'); ledger row ticket_answer kept as a draft (ABC is in shadow mode), no rule. Before the send the requester's ticket and desk view showed no comment and no draft; after the analyst sent it the requester saw only the ai_answer (status pending_customer, canConfirm true); 'this fixed it' resolved the ticket. No staff note or unsent draft was ever returned to the requester. No reply was refused, so the rule note was not exercised live (covered by the 85-38 tests)."

### 2. Publish the UI build (dist-new) and check the Tickets screen as a User-role requester, then as an analyst
expected: The requester sees no status buttons, Escalate, Merge, Watchers, Approve/Deny, attachment delete, Work Log / Links tabs, row checkboxes, bulk bar or board drag; New Ticket has no Assignee, Group, Due Date, SLA Hours or approval input; the "staff only" hint is absent; own tickets, the answer panel, comments to IT and file upload/download still work. The analyst sees every control again.
result: pass
note: "Run by Claude in headless Chromium (gstack browse) on the published UI index-jGfWTNYG.js at https://127.0.0.1, 2026-11-10 13:55 UTC, at the user's request; temporary ABC requester (User) and analyst (Analyst) signed in through the login form; data: the printer ticket (drafted, answer sent by the analyst) with an attachment. Requester: list shows only own TKT-0001, no row checkboxes, bulk bar or row delete; ticket panel has the answer panel with 'This fixed it' / 'I still need help', tabs Details, Comments, History, Files only, no status buttons, Escalate, Merge, Watchers, add-watcher box, Approve, title not click-to-edit; Comments tab has no staff hint and shows only the sent AI answer; Files tab shows Download, no Delete; New Ticket has Title, Description, Type, Priority, Tags, Agent/Host only; board has 0 draggable cards. Live actions as the requester: upload (POST attachments 200, file listed with Download only), download (GET .../download 200, 38 B), comment (POST comments 200, shown, toast 'Sent to IT. A person will take over.'). Analyst: row checkboxes and the bulk bar (no Delete option: analyst lacks manage:settings, A-85-G42), status buttons, Escalate, Merge, Watchers + add-watcher box, all six tabs, editable title, staff hint, reply picker, Delete + Download per file, draggable board card, New Ticket with Assignee, Team/Group, Due Date, SLA Hours and 'Requires approval'. Screenshots in ~/omni-archives/uat85-r4-t2/. Observation: ABC requesters now also see the read-only Agents page, because the User role holds view:agents and ABC got screen:agents today. Temporary accounts, ticket, desk job, ledger rows, notices, login events archived and removed; the two uploaded files moved to the archive."

### 3. Windows tray round trip (agent 2.1.18 published), the tray half of UAT test 3
expected: Raise a Ticket from the tray, see the AI-assisted answer pop-up, and "this fixed it" / "I still need help" behave as on the portal.
result: blocked
blocked_by: "No Windows PC enrolled in ABC; the tray (the Windows agent's My tickets window and answer pop-up) cannot run on this Linux VM. Agent 2.1.18 is published (894ca4203)."
note: "SERVER SIDE verified by Claude at the user's request, 2026-11-10 14:08 UTC, against the live API: a temporary Windows agent (UAT85-TRAY-TEST, version 2.1.18) registered in ABC through /api/agents/register (status Online, 1 of 5 seats) and drove the five tray routes as Windows user UAT85TRAY\\dana. Ticket A (printer): create 200, stored raised_via tray, requester_channel {tray, myTickets, windowsUser, template report_issue}; desk drafted; before the analyst's send the tray list showed status 'Received - IT has your ticket.', no entries, canConfirm false; after the send it showed status pending_customer, 'Answer ready - please tell us if it fixed the problem.', one entry headed 'Answer from IT support (AI-assisted)' citing 'Fixing a printer that will not print', canConfirm and canHelp true, plus the footnote naming the Windows user; another Windows user on the same computer (UAT85TRAY\\sam) saw no ticket and got 404 on confirm; 'this fixed it' from the tray resolved it. Ticket B: drafted, sent, 'I still need help' from the tray -> status open, desk phase helped. No staff-only text appeared in any tray response. Not checked live: the cited-article route (a second token could not be issued: re-registering the existing agent answers 409, the enrollment lockout); it is covered by the tray unit tests. Temporary agent, asset, analyst, tickets, desk jobs, ledger rows, login event and the lazily migrated 'Legacy key' enrollment record archived to ~/omni-archives/uat85-r4-t3/ and removed; audit_logs left in place. Remaining human check: the real tray on a Windows PC enrolled in ABC (raise a ticket, the pop-up, the two buttons)."

### 4. After the restart, check G-85-5 live
expected: A ticket created by a requester with watchers, assignee or approval_required in the body keeps none of the six staff-only fields; a pending-agent notice for a tenant with two users is seen only by a tenant admin in the feed, and no non-admin socket receives it.
result: pass
note: "Run by Claude against the live API, same run and accounts as test 1, plus a temporary Tenant Admin enrolled in MFA through /api/mfa/setup + verify-setup. (a) The requester's POST /api/tickets with assignee x@example.com, assignee_group 'Team X', watchers [outsider@example.com], approval_required true, sla_hours 1, due_date 2026-12-01 stored assignee '', group '', watchers [], approval_required false, sla_hours 72 (priority default) and a computed due date; the analyst's identical request stored all six as sent. (b) Socket.IO clients for the requester, analyst and admin were connected first; all three received the untagged 'New Ticket' notices (positive control). Trigger: the Autonomous Ops stop for ABC, whose notice takes the same pending_agents.post_to_recipients -> _post_in_app path as the pending-agent notice (a real pending-agent notice needs an agent enrolling over the seat limit; not faked). The ABC notice was stored once with audience tenant_admins and NO socket (requester, analyst or admin) received it; the requester's and analyst's feeds do not show it. Not shown: the admin's feed did not show it either, because ABC's Tenant Admin does not hold manage:agents (the Agents screen is not ticked for ABC; reader_filter shows tenant_admins notices only to manage:agents holders). Finding: ABC's Tenant Admin holds control:autonomous_ops but not manage:autonomous_ops (only view:autonomous_ops is ticked), so the stop could be pressed but the resume answered 403 'Missing required permission: manage:autonomous_ops'; ABC's stop was put back to null directly in the database (prior value; settings archived) and the test rows archived and removed. 23 hash-chained audit_logs entries left in place."

### 5. Decide on review findings WR-701 and WR-702 before deployment
expected: Either the fixes (reportFailure on the title edit and the Start button of security-incident tickets, a catch in handleComment's staff-note branch, a try/catch in handleUpload; load() in the bulk catch) or a written acceptance.
result: pass
note: "User chose to fix both (2026-11-10, 'fix WR-701 and WR-702 now'). Fixed in 3d8a39763: title rename and Start Remediation go through handlePatch (error toast), a refused staff note and a refused upload show a toast, bulk delete uses allSettled (only the deleted tickets leave the list and the selection, the list reloads after any failure). Seven new cases in src/__tests__/TicketsStaffActionErrors.test.tsx, each failing on the previous code; disposition WR-701/WR-702 fixed (open 33 of 51). Part of the UI build; verify the visible behaviour in test 2 after the publish."

## Summary

total: 5
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 1

## Gaps
