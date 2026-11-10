---
phase: 85-first-line-service-desk
plan: 41
subsystem: service-desk
tags: [tickets-screen, error-toast, staff-actions, gap-closure, G-85-4b, PROH-85-35]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: 85-40 isTicketStaff gating of the staff controls on the Tickets screen
provides:
  - reportFailure, one local helper in the Tickets screen that shows the caught error's message (else a fallback sentence) as an error toast
  - try/catch with that helper in every staff mutation handler (status change, escalate, watcher add and remove, work log, link, unlink, approve, reject, attachment delete, ticket delete, merge, bulk update and delete, board drop)
  - watcher add and remove handlers that show the returned watcher list on the open ticket
affects: [gsd-verify-work 85, UAT round 4 of G-85-4b]

actuals:
  tokens: 18000
  tasks: 2
  commits: 3
plan_head_before: 698334f75f3d6453350f087cf56bc83b4ec95236
plan_head_after: ac80717e635756d68de82021ed613bc57ebb1784
commits: 3

tech-stack:
  added: []
  patterns: ["one reportFailure(e, fallback) helper for every staff mutation catch"]

key-files:
  created:
    - src/__tests__/TicketsStaffActionErrors.test.tsx
  modified:
    - components/InternalTicketsDashboard.tsx

key-decisions:
  - "A-85-G43 kept: the toast shows the message the apiService helper throws (fixed sentences such as 'Failed to update ticket'), not the server detail; showing the detail needs an apiService change, left to the user"
  - "A failed bulk delete or update keeps the selection and does not reload the list (success-only, as the plan says)"
  - "A successful watcher add clears the e-mail box; a failed one keeps it so the technician can retry"

requirements-completed: [DESK-01]

coverage:
  - id: E1
    description: "A refused status change, escalate, watcher add or removal shows an error toast with the error's message; a non-Error or empty message shows the handler's fallback sentence; a successful watcher change shows the returned watcher list on the open ticket"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#the actions UAT round 3 saw fail silently"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#a successful watcher change"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#an error that carries no message"
        status: pass
    human_judgment: false
  - id: E2
    description: "Work log, link, unlink, approve, reject, attachment delete, merge (request throws), ticket delete from the row, bulk status change, bulk delete and a board drop each show the toast when the call fails; the merge not-ok message and the successful log-work, approve and bulk update paths are unchanged"
    requirement: DESK-01
    verification:
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#the ticket panel actions"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#the list, the bulk bar and the board"
        status: pass
      - kind: unit
        ref: "src/__tests__/TicketsStaffActionErrors.test.tsx#the successful paths stay as they were"
        status: pass
    human_judgment: false
  - id: E3
    description: "How a failed staff action reads on the published UI"
    requirement: DESK-01
    human_judgment: true
    rationale: "Needs the UI publish (the user's step); the unit tests render the whole screen with mocked services"
---

# Phase 85 Plan 41: no staff action on the Tickets screen fails silently Summary

Every staff mutation on the Tickets screen now catches its failure and shows an error toast through one `reportFailure(e, fallback)` helper; together with 85-40 (requesters no longer see the controls) this closes UAT gap G-85-4b on the screen.

## Accomplishments

- **Task 1 (tracer, 4415379d6):** `handlePatch` (status buttons) and `handleEscalate` catch and report; the inline watcher add and remove calls became `handleAddWatcher` / `handleRemoveWatcher`, which set the returned ticket as selected and update the list row (before, an add showed nothing and a removal never reached the list). The watcher buttons gained `aria-label`s ("Add watcher", "Remove watcher <email>"). New test file with 9 tests.
- **Task 2 (RED dea1e15f5, GREEN ac80717e6):** the same helper wraps `handleDeleteAttachment`, `handleLogWork`, `handleLink`, a new `handleUnlink` (aria-label "Remove link <id>"), `handleApprove`, `handleReject`, `handleDelete`, `handleMerge` (its catch now toasts; the not-ok "Merge failed" toast stays), `handleBulkAction` (delete and update branch; selection cleared and list reloaded only after success) and the board drop (the empty catch is gone). `grep -c "catch(() => {})"` prints 3 (the agents, templates and field-schema loads). 15 more tests; the RED run failed 11 of 24 before the change.
- Verify: Vitest for the new file, TicketsRequesterControls, ServiceDeskRequesterComments, ServiceDeskReplyVisibility, ServiceDeskTicketPanels and autonomousOpsCopy: 6 files, 189 passed, 0 failed; eslint on the new file clean with `--max-warnings 0`; `npm run build` exit 0 (dist-new, not published).

## Deviations from Plan

**1. TDD split in Task 2:** the plan lists one commit; the RED tests went first (dea1e15f5, test-only) and the implementation second, per `tdd="true"`, as in 85-40. The component file is not part of the RED commit.

**2. Small additions, not asked for:** aria-labels on the watcher add and remove buttons and on the unlink button (stable test queries; no control added or removed); `handleAddWatcher` and `handleRemoveWatcher` also update the list row.

**Total deviations:** 0 auto-fixes, 2 small notes. **Impact:** none on scope.

## Needs the user

- A-85-G43: the toast text is the fixed sentence thrown by the ticket helpers in services/apiService.ts (your WIP file, not edited). Showing the server's detail (for example the 403 reason) would need those helpers to throw it.
- A failed bulk delete (Promise.all) can leave some tickets already deleted; the list is not reloaded on failure, as the plan specified. Reloading in the catch is a one-line change if you want it.
- Nothing is live: the UI publish (`sudo cp` of dist-new to /var/www) is the user's step; no backend change was made.

## WIP safety

components/InternalTicketsDashboard.tsx carries the user's uncommitted download-attachment hunks. Both code commits were staged with the index-blob method (one exact-match edit script per task applied to the working file and to a `git show HEAD:` copy, `git update-index --cacheinfo 100755,...`); edits matched HEAD lines only (handleDeleteAttachment anchored on its own two body lines). After each commit: `git diff --numstat` still prints `14 1`, the added/removed lines of the user's diff are identical to the one saved before the plan, HEAD plus the regenerated diff reproduces the working file byte for byte (`cmp`), and the added-line check for `downloadTicketAttachment` / `handleDownloadAttachment` prints 0 for both code commits.

## Known Stubs

None.

## Threat Flags

None. T-85-140 (a staff action that fails silently) is mitigated: one helper in the catch of every staff mutation and a test per action.

## Self-Check: PASSED

- src/__tests__/TicketsStaffActionErrors.test.tsx exists; commits 4415379d6, dea1e15f5, ac80717e6 are ancestors of HEAD.
- Acceptance: `grep -c "catch(() => {})"` prints 3; the added-line check for the user's names prints 0 for both code commits; Vitest 0 failed, eslint 0, build 0.
