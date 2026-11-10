---
phase: 85-first-line-service-desk
plan: 40
subsystem: service-desk
tags: [tickets-screen, requester-controls, manage-tickets, gap-closure, G-85-4b, IN-604]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: 85-34 server-side staff boundary for the ticket routes, 85-39 server drops the staff-only create fields for requesters
provides:
  - isTicketStaff (hasPermission('manage:tickets') === true, read once) and canDeleteTickets (manage:settings) in the Tickets screen
  - a requester's ticket panel without status buttons, Watchers, Escalate, Merge, Approve/Deny/Reject controls, title edit, attachment delete, Work Log and Links tabs and the staff hint
  - a requester's list without row checkboxes, bulk bar and delete button; a board without draggable cards or a working drop
  - a requester's New Ticket form without Assignee, Team / Group, Due Date, SLA Hours and approval inputs, and a payload without those keys
affects: [85-41 (error toasts for the staff handlers), gsd-verify-work 85, UAT round 4 of G-85-4b]

actuals:
  tokens: 10000
  tasks: 2
  commits: 3
plan_head_before: 25bbc1d16e71675c3050aeee575b816751313e8e
plan_head_after: 200daaaf9aa6eec6706c9e3a92724b75f7f75427
commits: 3

tech-stack:
  added: []
  patterns: ["one permission flag read once in the screen and passed to the modal as a prop", "UserContext test mocks carry hasPermission backed by a hoisted Set"]

key-files:
  created:
    - src/__tests__/TicketsRequesterControls.test.tsx
  modified:
    - components/InternalTicketsDashboard.tsx
    - src/__tests__/ServiceDeskRequesterComments.test.tsx
    - src/__tests__/ServiceDeskReplyVisibility.test.tsx

key-decisions:
  - "A-85-G41: Work Log and Links tabs are hidden for requesters (adding to either is staff-only since 85-34); History stays; the staff hint above the comment list is staff-only"
  - "A-85-G42: the row delete button and the bulk Delete selected option follow manage:settings, the permission of DELETE /api/tickets/{id}"
  - "Rule 2: the click-to-edit ticket title (a PATCH) is also staff-only; a requester's title is plain text"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "A requester opening their own ticket sees no status button, no Escalate, Merge or Watchers block, no Work Log or Links tab, no staff hint, no attachment delete, no Approve or rejection input (the Pending Approval heading and read-only install line stay), and cannot start a title edit; staff see all of it"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "src/__tests__/TicketsRequesterControls.test.tsx#a requester opening their own ticket (G-85-4b)"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsRequesterControls.test.tsx#ticket staff (manage:tickets) on the same ticket"
        status: pass
    human_judgment: false
  - id: D2
    description: "The list shows a requester no checkbox, bulk bar or delete button; staff with manage:tickets get checkboxes and the bulk bar; delete needs manage:settings; board cards are draggable and a drop moves a ticket only for staff"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "src/__tests__/TicketsRequesterControls.test.tsx#the list and the bulk bar"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsRequesterControls.test.tsx#the board"
        status: pass
    human_judgment: false
  - id: D3
    description: "A requester's New Ticket form has none of the five staff-only inputs and createTicket receives none of assignee, assignee_group, watchers, approval_required, sla_hours, due_date; staff keep the inputs and keys"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "src/__tests__/TicketsRequesterControls.test.tsx#the New Ticket form"
        status: pass
    human_judgment: false
  - id: D4
    description: "How the screen looks to a real requester on the published UI"
    requirement: DESK-01
    human_judgment: true
    rationale: "Needs the UI publish (the user's step) and a requester login; the unit tests render the whole screen with mocked services"
---

# Phase 85 Plan 40: requester sees no staff-only control on the Tickets screen Summary

The Tickets screen now asks `hasPermission('manage:tickets')` once and hides every staff-only control from a requester in the ticket panel, the list, the board and the New Ticket form; delete follows `manage:settings`. This is the screen half of UAT gap G-85-4b (IN-604); the error toasts for any staff action that still fails are 85-41.

## Accomplishments

- **Task 1 (tracer, 3f70dbf6a):** `isTicketStaff` gates the status quick-action buttons, the Watchers block, the Escalate and Merge boxes, every Approve / Deny / Reject control in the install, access, vulnerability and change panels and in the Approval actions panel (its "Pending Approval" heading and the read-only approved/denied lines stay), the attachment delete button (now `aria-label="Delete <file>"`), the staff hint above the comments, and the Work Log and Links tabs. The two desk screen tests got a `hasPermission` mock (Sam staff; Dana a requester) and their two reporter staff-hint assertions now expect the hint absent. 12 new tests (7 requester, 5 staff).
- **Task 2 (RED b769d276b, GREEN 200daaaf9):** `canDeleteTickets` (manage:settings) gates the row delete button (`aria-label="Delete <ticket number>"`) and the "Delete selected" option; the header and row checkboxes and the bulk bar need `isTicketStaff`; board cards are `draggable` only for staff and `onDrop` does nothing for anyone else; `TicketModal` takes `isTicketStaff`, hides the Assignee, Team / Group, Due Date, SLA Hours and approval inputs for a requester and deletes those six keys from the payload at submit. 10 new tests. The RED run failed 7 of 22 before the change.
- Verify: Vitest for the new file, ServiceDeskRequesterComments, ServiceDeskReplyVisibility, ServiceDeskTicketPanels and autonomousOpsCopy: 5 files, 165 passed, 0 failed; eslint on the new file clean with `--max-warnings 0`; `npm run build` exit 0 (dist-new, not published).

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Title edit hidden for requesters**
- **Found during:** Task 1
- **Issue:** clicking a ticket's title opens an edit box whose save is `PATCH /api/tickets/{id}` (manage:tickets); a requester would get the same silent 403 as the status buttons.
- **Fix:** the h3 click handler, `title` hint and pointer styling apply only for `isTicketStaff`; two tests added.
- **Files modified:** components/InternalTicketsDashboard.tsx, src/__tests__/TicketsRequesterControls.test.tsx
- **Commit:** 3f70dbf6a

**2. Added aria-labels** "Select all tickets" and "Select TKT-n" on the row checkboxes (not asked for; they make the tests' queries stable).

**3. TDD split in Task 2:** the plan lists one commit; the RED tests were committed first (b769d276b, test-only) and the implementation second, per the `tdd="true"` attribute. The file is not touched by the RED commit, so no WIP concern.

**Total deviations:** 1 auto-fixed (Rule 2), 2 small notes. **Impact:** none on scope beyond the title edit.

## Needs the user

- A-85-G41: a requester no longer sees the Work Log and Links tabs, the staff hint above the comment list (this reverses the 85-26 line shown to the reporter, the UAT copy nit) or the click-to-edit title. History stays.
- A-85-G42: a ticket staff member without manage:settings no longer sees the row delete button or "Delete selected" (the server answered 403 for them).
- Nothing is live: the UI publish (`sudo cp` of dist-new to /var/www) is the user's step; no backend change was made.

## WIP safety

components/InternalTicketsDashboard.tsx carries the user's uncommitted download-attachment hunks (import name, `handleDownloadAttachment`, Download button in the Files tab). Both code commits were staged with the index-blob method (exact-match edit scripts applied to the working file and to `git show HEAD:` copies, `git update-index --cacheinfo 100755,...`); `git diff --cached` held no `downloadTicketAttachment` / `handleDownloadAttachment` / `Download ` added line, and `git diff --numstat -- components/InternalTicketsDashboard.tsx` still prints `14 1` after each commit. One note for the byte-for-byte re-check: the Task 1 change wraps the attachment delete button, which sits in the three trailing context lines of the user's third hunk, so the original saved diff no longer applies to HEAD (hunk 3 context moved). The added and removed lines of the user's diff are identical to before (verified by comparing the `+`/`-` lines); a diff regenerated after Task 1 (`user-dashboard.t1.diff` / `user-dashboard.t2.diff` in the scratchpad) applies cleanly to HEAD and reproduces the working file byte for byte.

## Known Stubs

None.

## Threat Flags

None. T-85-136 and T-85-137 are mitigated (screen hides the controls and the form neither shows nor sends the staff-only fields); the server remains the boundary.

## Self-Check: PASSED

- src/__tests__/TicketsRequesterControls.test.tsx exists; commits 3f70dbf6a, b769d276b, 200daaaf9 are ancestors of HEAD.
- Acceptance: `grep -c isTicketStaff` prints 28 (>=12), `grep -c canDeleteTickets` prints 3 (>=2); the added-line check for the user's names prints 0 for both code commits.
