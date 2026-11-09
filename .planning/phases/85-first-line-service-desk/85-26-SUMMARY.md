---
phase: 85-first-line-service-desk
plan: 26
subsystem: service-desk-ui
tags: [reporter-comments, d-11, cr-401, tickets-screen, information-disclosure, defence-in-depth]

requires:
  - phase: 85-first-line-service-desk
    provides: "85-25 server projection and shared/service-desk-requester-comments.json; 85-20 desk view (TicketDeskView.isRequester) and CommentMarks"
provides:
  - "components/serviceDesk/requesterComments.ts: sameUser, requesterMayRead, viewerIsReporter, visibleComments (TypeScript copy of projection.requester_may_read)"
  - "Tickets screen Comments tab and list-row comment count go through visibleComments"
  - "CR-401 recorded fixed in 85-REVIEW-DISPOSITION.md (server 85-25 plus screen 85-26)"
affects: [85-29 phase gate, 85-VERIFICATION gap 2 re-verification]

actuals:
  tokens: 6500
  tasks: 2
  commits: 4
plan_head_before: eddbdd6fef100113cbf4ce6156cb5713394bdadd
plan_head_after: 8862012c1f1fc1c980d157b2f99ec195a043dc0f
commits: 4

tech-stack:
  added: []
  patterns:
    - "UI copy of a server rule pinned by one shared JSON case table read by both test suites"
    - "Viewer decided from the ticket and the signed-in email, not only from an async desk view (fail closed)"

key-files:
  created:
    - components/serviceDesk/requesterComments.ts
    - src/__tests__/ServiceDeskRequesterComments.test.tsx
  modified:
    - components/InternalTicketsDashboard.tsx
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md

key-decisions:
  - "A-85-G09: requesterMayRead is a TypeScript copy of the server rule; the shared case table (16 cases) keeps them from drifting"
  - "A-85-G10: only the comment list and the list-row count changed; the reply picker and panels keep their 85-20 behaviour"
  - "An unknown viewer (empty email) with no desk view is treated as the reporter, so the list fails closed"

requirements-completed: [DESK-01]

coverage:
  - id: D1
    description: "CR-401 UI / D-11: the reporter's Comments tab renders only requesterMayRead comments on first paint (desk view pending), after a failed desk read, with a case-different email and when the desk view says requester; the reporter never sees staff-only, no-flag, ai_draft or withdrawn text"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#the reporter on the first paint of the Comments tab"
        status: pass
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#the reporter after a failed or different desk read"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single source: requesterMayRead gives the readable value of every case of shared/service-desk-requester-comments.json"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#requesterMayRead agrees with the shared case table"
        status: pass
    human_judgment: false
  - id: D3
    description: "Staff keep the full view with marks before and after the desk view loads (D-11 unchanged)"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#staff keep the full view (D-11)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The list row counts only readable comments for the reporter and all comments for staff; with nothing readable no count renders"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#the comment count of the ticket list row"
        status: pass
    human_judgment: false
  - id: D5
    description: "UI-SPEC S5/S6 lifted considerations: listNote line stays, 'No comments yet.' when nothing is readable, marks kept on remaining comments, long text wrapping classes unchanged"
    requirement: "DESK-01"
    verification:
      - kind: unit
        ref: "src/__tests__/ServiceDeskRequesterComments.test.tsx#shows \"No comments yet.\" and keeps the note when only staff-only comments exist"
        status: pass
    human_judgment: true
    rationale: "Long-text wrapping without the marks overlapping the text is a visual property (verification: backstop in the plan); the className whitespace-pre-wrap break-words is unchanged but no test measures the layout."
---

# Phase 85 Plan 26: Reporter's Comments tab filter Summary

**The Tickets screen now renders, for the person who raised a ticket, only the comments they may read (requester-visible and not withdrawn, or their own, never an AI draft), decided from the ticket and the signed-in email so it is already closed on the first paint and after a failed desk read; staff keep the full view, and the list row count follows the same rule (CR-401 UI half, T-85-94).**

## Performance

- **Duration:** about 4 min
- **Started:** 2026-11-09T16:24:27Z
- **Completed:** 2026-11-09T16:28Z
- **Tasks:** 2
- **Files modified:** 4 (2 created)

## Accomplishments
- `requesterComments.ts` (67 lines, no strings): `sameUser`, `requesterMayRead`, `viewerIsReporter` (desk view `isRequester`, or `selected.reporter` equals the signed-in email ignoring case and spaces, or no desk view and an empty viewer email), `visibleComments` (generic, returns the caller's comment type).
- `InternalTicketsDashboard.tsx`: the Comments tab maps `shownComments = visibleComments(selected, userEmail, deskView)` (computed once in the render, not a hook); `No comments yet.` uses that list's length; the list row count is `visibleComments(t, userEmail, null).length` with its `> 0` guard. Picker and panels unchanged.
- `ServiceDeskRequesterComments.test.tsx` (253 lines, 33 tests): 16-case parity with the backend table plus the viewer rule, first paint (the desk GET never resolves), failed desk read (500), differing-case email, isRequester true for another email, the empty state with the note kept, staff before/after the desk view, and the list count (4 of 8 for Dana, 8 for Sam, none when nothing is readable).
- CR-401 flipped to fixed in 85-REVIEW-DISPOSITION.md with the server (85-25) and screen hashes; open count 26 to 25; WR-401..405 and all IN rows still open.

## Task Commits

1. **Task 1 (tracer): the reporter's first paint of the Comments tab** - `82e9074c4` (feat)
2. **Task 2 RED: failed desk read, staff view and list-row count tests** - `c862a9965` (test; the two list-count tests failed with 8 and 1 where 4 and none were expected, the other tests passed because Task 1 already covers those paths)
3. **Task 2 GREEN: the list row counts only readable comments** - `3df8d5088` (feat)
4. **Disposition: CR-401 fixed** - `8862012c1` (docs)

**Plan metadata:** the SUMMARY/STATE/ROADMAP docs commit follows this file.

## Files Created/Modified
- `components/serviceDesk/requesterComments.ts` - the UI copy of the server rule
- `components/InternalTicketsDashboard.tsx` - import, `shownComments`, list-row count (user hunks left unstaged)
- `src/__tests__/ServiceDeskRequesterComments.test.tsx` - the tests
- `.planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md` - CR-401 fixed

## Decisions Made
Followed A-85-G09/G10 as planned. The list row evaluates `visibleComments` twice per row (guard and number) rather than introducing a helper component; it is a cheap array filter and keeps the existing markup unchanged.

## Deviations from Plan

None - plan executed exactly as written. One note on TDD: Task 2 has a RED commit (`c862a9965`) in which only the list-count cases fail (the rest were already satisfied by Task 1's helper and tracer, by design of the plan).

**Total deviations:** 0.
**Impact on plan:** none.

## Issues Encountered
None. A first Task 2 test run on the working tree after the list-row change passed 143/143 across the four named test files.

## Known Stubs
None.

## Threat Flags
None. T-85-94 (comment list disclosure on first paint or failed desk read) and T-85-95 (UI rule drift, mitigated by the shared case table) are mitigated as planned; no new endpoint, auth path or schema.

## User WIP
`components/InternalTicketsDashboard.tsx` was committed twice through an index blob built from `HEAD` plus only this plan's edits (`git update-index --cacheinfo 100755`). After each commit `git diff --numstat -- components/InternalTicketsDashboard.tsx` printed the working-tree counts (14 and 1 before this plan's working edits; 20/3 and 15/2 in between, which are the user's hunks plus uncommitted working edits), and after the final commit it is back to `14 1`; `HEAD` plus the saved user diff is byte-identical to the working file (`cmp` silent) after both commits; no added line of either commit mentions `downloadTicketAttachment` or `handleDownloadAttachment`. The index copy was type-checked by placing it temporarily beside the component (tsc, no errors in either file) and removed again. No other user file was staged or changed.

## Verification
- `npx vitest run` for the new file, ServiceDeskReplyVisibility, ServiceDeskTicketPanels and autonomousOpsCopy: 4 files, 143 tests passed.
- `npx eslint` on the helper and the test with `--max-warnings 0`: clean.
- `npm run build`: built (writes dist-new/, nothing published).
- `grep -c "visibleComments(" components/InternalTicketsDashboard.tsx` prints 2 (the Comments tab call is `visibleComments(selected, userEmail, deskView)`, the other is the list row).
- Not run (by plan): backend suites, the whole Vitest suite, publish, push, restart.

## Self-Check: PASSED
Files present: components/serviceDesk/requesterComments.ts, src/__tests__/ServiceDeskRequesterComments.test.tsx, 85-REVIEW-DISPOSITION.md. Commits present: 82e9074c4, c862a9965, 3df8d5088, 8862012c1.
