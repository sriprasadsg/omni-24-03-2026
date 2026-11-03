---
phase: 87-partner-and-reseller-channel
plan: 13
subsystem: ui
tags: [react, typescript, vitest, partner-channel, accept-invite]

requires:
  - phase: 87-07
    provides: services/partnerApi.ts fetchInviteStatus and acceptInvite (public, no session)
provides:
  - AcceptInvitePage, the public page an invited customer admin or partner staff member uses to set a password (not yet routed; 87-14 mounts /accept-invite)
affects: [87-14]

actuals:
  tokens: 8670
  tasks: 2
  commits: 4
plan_head_before: 548b2945913f269f4c58f81993ee00d13ff1dba0
plan_head_after: 0d672617aa3dca6b52fdab1ed8541b3fb2198929

tech-stack:
  added: []
  patterns:
    - "The token is read once into a ref and the address bar is cleaned with history.replaceState before the first request; Try again reuses the ref, never the URL"
    - "After the password is set the page calls the existing login once and window.location.replace('/'); it builds no MFA UI"

key-files:
  created:
    - components/AcceptInvitePage.tsx
    - src/__tests__/AcceptInvitePage.test.tsx
  modified: []

key-decisions:
  - "The status-failure (network) card uses the page title 'Set your password' as its heading, with the contract's red block and a Try again button, because the contract gives no heading for that case and 'Checking your invite...' would be wrong once the check has failed"
  - "A 400 from confirm re-asks the status; if the link is still valid the server's words are shown verbatim, and if the re-ask itself fails the 400 message is still shown"
  - "Login that returns no access_token (for example an MFA challenge) or a status with no email falls back to the 'Password set' state, as the contract specifies for a failed sign-in"
  - "Password fields live in a module-level PasswordField component so typing never remounts an input"

patterns-established: []

requirements-completed: [PART-02]

coverage:
  - id: D1
    description: "Link check: token removed from the address bar before the status request, Checking skeleton, valid welcome with read-only email, Expired, Used, Invalid (also for a missing token and unclassifiable state), network error with Try again, h1 focus on every state change, text-only rendering of long names"
    requirement: PART-02
    verification:
      - kind: unit
        ref: "src/__tests__/AcceptInvitePage.test.tsx#AcceptInvitePage link check (PART-02, D-17)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Password form: two new-password fields, five live rules, polite live region only after touch, submit disabled until rules met and fields match, mismatch message, show/hide toggles with aria-pressed, paste allowed"
    requirement: PART-02
    verification:
      - kind: unit
        ref: "src/__tests__/AcceptInvitePage.test.tsx#AcceptInvitePage password form (PART-02, D-20)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Submit and sign-in: Setting password... with fields disabled, one accept call per double click, one login with the invited email, window.location.replace('/'), Signing you in state, fallback Password set state, 400 to Used or Expired, verbatim complexity refusal, other refusals and network failure keep typed values, password and token never logged, stored or put in the URL"
    requirement: PART-02
    verification:
      - kind: unit
        ref: "src/__tests__/AcceptInvitePage.test.tsx#AcceptInvitePage submit and sign-in (D-20)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Visual fit: a 100-character organization name wraps in the 448px card at 360px wide without horizontal scroll; light/dark appearance of the card"
    verification: []
    human_judgment: true
    rationale: "jsdom has no layout, so only the wrapping classes (break-words, break-all) are asserted; the page is not mounted until 87-14 and the UI is not published, so the backstop truth can only be judged in a browser"

duration: about 12 min
completed: 2026-11-03
status: complete
---

# Phase 87 Plan 13: Accept Invite Page Summary

**A public Accept invite page that checks the emailed link, sets the password through the existing confirm route, signs the person in once, and hands them to the app shell so required MFA set-up appears as it does for every admin.**

## Performance

- **Duration:** about 12 min (18:41 to 18:53 UTC)
- **Tasks:** 2
- **Files modified:** 2 (2 created)

## Accomplishments

- `AcceptInvitePage` (398 lines, default export) lives outside the shell on the LoginPage canvas with a `.card max-w-md p-8` card.
  - On mount it reads the token from the query string into a ref and calls `history.replaceState({}, '', '/accept-invite')` before the first request. The status call is a POST body (87-07).
  - It renders Checking (skeleton, `aria-busy`), the valid form with the welcome line and read-only email, Expired (ClockIcon), Used, Invalid and a network-failure state. A missing token or any state it cannot classify is Invalid.
  - The state heading is an `h1` that takes focus on every change.
- The form has New password and Confirm password with five live rules, a mismatch message, show/hide toggles and paste allowed. Submit is disabled until every rule is met and the fields match.
  - After the accept call it shows `Password set` / `Signing you in...`, calls `login(email, password)` once and `window.location.replace('/')`.
  - A 400 re-asks the status, so a used or expired link moves to that state; a still-valid link shows the server's complexity message verbatim above the button.
  - Failure to sign in falls back to `Password set` with Go to sign in.
- **Verification:**
  - `AcceptInvitePage.test.tsx` has 30 tests (11 for Task 1, 19 for Task 2). The task commands pass together with `SessionEnded.test.tsx` (33 tests).
  - `npx tsc --noEmit` is clean.
  - The full frontend suite passes: 83 files, 1166 tests, no failures. That is the 1136 baseline plus this plan's 30.

## Task Commits

1. **Task 1: Check the link and show the right state.** RED `efb4ca24f` (test), GREEN `f4c9ce4e0` (feat)
2. **Task 2: Set the password and sign in once.** RED `e8ccccb99` (test), GREEN `0d672617a` (feat)

**Plan metadata:** committed with this SUMMARY (docs).

## TDD Gate Compliance

Each task has a `test(87-13)` commit before its `feat(87-13)` commit. `workflow.tdd_mode` is not set, so the RED-evidence classifier was not required.

- Task 1 RED committed a stub component (an empty div) next to the tests, so all 10 RED tests failed on assertions, not on a missing import.
- Task 2 RED ran against the Task 1 component, which has no form yet. All 19 new tests failed on assertions (missing fields, buttons and states).
- Two GREEN commits edited tests: Task 1 added a Try again test with its feature; Task 2 changed one assertion that read `window.location.search` from the mocked location (a test artifact) to read the real location's href.

## Files Created/Modified

- `components/AcceptInvitePage.tsx` - the public page: link check, states, password form, sign-in
- `src/__tests__/AcceptInvitePage.test.tsx` - 30 tests

## Decisions Made

See `key-decisions` above. For 87-14: mount `AcceptInvitePage` (default export) on the public `/accept-invite` route, outside the signed-in shell and before any session restore redirects to the login page. The page reads `window.location.search` on mount and cleans it itself.

## Deviations from Plan

**1. [Rule 2 - Missing functionality] Try again on a status-check network failure.**
- **Found during:** Task 1
- **Issue:** The plan only says a rejected status request shows the network error block. With no action, the invitee would have to reload a link whose token has already left the address bar, which would land on Invalid.
- **Fix:** Added a secondary `Try again` button (a contract-listed CTA) that re-asks the status with the token kept in memory.
- **Files modified:** `components/AcceptInvitePage.tsx`, `src/__tests__/AcceptInvitePage.test.tsx`
- **Commit:** `f4c9ce4e0`

Otherwise the plan ran as written.

## Issues Encountered

- The CLAUDE.md `npm run build && npm test` instruction was met as `npx tsc --noEmit` plus the full vitest run, as in 87-11 and 87-12. `npm run build` was not run.
- Not built here by design: the route and shell wiring belong to 87-14, and nothing was published.
- `components/ResetPasswordModal.tsx` is untracked and was not edited or imported; its rules list was mirrored.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. The Task 1 RED stub was replaced in the Task 1 GREEN commit.

## Threat Flags

None. No new endpoint, auth path or schema.

- **T-87-40 (token disclosure):** mitigated. `replaceState` runs before the first request, the token is held in a ref, and a test asserts the token is absent from the DOM, storage writes, logs and the address bar.
- **T-87-41 (password handling):** mitigated. State is cleared after the accept call or the sign-in, the page has 0 `console` calls and 0 `localStorage` uses, and a test asserts the password is not logged, stored or put in a URL.

## Self-Check: PASSED

- Both files exist, and all four commit hashes are ancestors of HEAD.
- Acceptance greps:
  - `replaceState` appears 1 time
  - `dangerouslySetInnerHTML` and `console.` appear 0 times
  - `localStorage` appears 0 times
  - `autoComplete="new-password"` appears 2 times
  - line count is 398, under 500
