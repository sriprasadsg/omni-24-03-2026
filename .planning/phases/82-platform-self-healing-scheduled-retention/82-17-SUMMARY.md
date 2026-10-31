---
phase: 82-platform-self-healing-scheduled-retention
plan: 17
subsystem: retention-ui
tags: [retention, ui, confirm-gate, gap-closure, wr-01, wr-05, t-82-42, ui-spec]

requires:
  - phase: 82-platform-self-healing-scheduled-retention
    provides: "82-15 GET /review incomplete field and 409 REVIEW_INCOMPLETE; 82-16 cert-unreadable rule and the unreadable-certificate wording; 82-13 review card and dialog"
provides:
  - "Confirm deletion disabled until every waiting row is loaded (state.nextOffset null) and while review.incomplete is set"
  - "incompleteNotice(gap) amber status notice and INCOMPLETE_HELPER; helper precedence: running, incomplete, no countable rows, rows not loaded, default"
  - "Dialog: Keep waiting disabled and Esc off while the confirm request is pending"
  - "Run Cleanup Now checks r.ok and a readable ran_at, shows an error toast instead of the green card"
  - "82-UI-SPEC.md amended in place (2026-10-31)"
affects: [82 verification (HEAL-06, T-82-42), 82-UI-REVIEW Fix 3]

requirements-completed: [HEAL-06]

actuals:
  tokens: 21000
  tasks: 3
  commits: 3

key-files:
  modified:
    - services/autonomousOpsApi.ts
    - components/AutonomousOpsRetentionReview.tsx
    - components/AutonomousOpsRetentionConfirmDialog.tsx
    - components/RetentionPolicyDashboard.tsx
    - src/__tests__/_platformHealthHarness.tsx
    - src/__tests__/AutonomousOpsRetentionReview.test.tsx
    - src/__tests__/AutonomousOpsRetentionConfirmDialog.test.tsx
    - src/__tests__/RetentionPolicyDashboard.test.tsx
    - .planning/phases/82-platform-self-healing-scheduled-retention/82-UI-SPEC.md

key-decisions:
  - "allLoaded is state.nextOffset === null; useRetentionReview already keeps nextOffset only while the token is unchanged, so a recount (new token) sends the card back to page 1 and disables the button again without new hook code"
  - "No new branch in the dialog for a refused confirmation: the 82-15 409 REVIEW_INCOMPLETE lands in the existing stale block with Reload review, after which the card shows the reason"
  - "The incomplete notice sits inside the canConfirm block, which is inside the items.length > 0 block, so it never shows before the first count or with nothing waiting"
  - "runCleanup treats a 200 with no string ran_at as a failure (fallback toast), because a card reading Invalid Date is the defect being fixed; the server detail is shown only when it is a non-empty string"

patterns-established:
  - "Table-driven it.each tests for copy variants keep AutonomousOpsRetentionReview.test.tsx under the 500-line limit (498 lines)"

duration: 12min
completed: 2026-10-31
status: complete
plan_head_before: 35622b4d081ebedf4d0e0bcc671934935d51786a
plan_head_after: 57705c85a195c57fdb2d611747cab4f0c4308032
commits: 3
---

# Phase 82 Plan 17: Confirm deletion waits for every row and a complete count Summary

**Confirm deletion is clickable only after every waiting row is on screen and only when the server reports the counted set complete; the dialog can no longer be dismissed while the request is in flight; Run Cleanup Now reports a refusal as an error; and 82-UI-SPEC.md matches all of it.**

## Accomplishments

- Task 1 (tracer) `c157feb10`: `RetentionIncompleteReason`, `RetentionIncomplete` and `RetentionReview.incomplete` in `services/autonomousOpsApi.ts`. The review card disables Confirm deletion on `running || incomplete !== null || countable <= 0 || !allLoaded`, with the helper chain running, incomplete, no countable rows, `Load all {total} rows before confirming.`, default. An amber `role="status"` notice names the reason in singular and plural through `plural()`; an unknown reason still reads. `retentionReview()` in the harness defaults `incomplete: null`.
- Task 2 `bdb6bf0d2`: `closeOnEsc={!pending}` on the Modal and `disabled={pending}` on Keep waiting, with a comment stating why. After a 409 or a 500 both work again. 82-UI-SPEC.md amended.
- Task 3 `57705c85a`: `runCleanup` reads the body with `.catch(() => null)`, shows an error toast (server `detail` when a non-empty string, else `Couldn't run cleanup.`) for `!r.ok` or a missing `ran_at`, never calls `setLastResult`, and a `catch` covers a network error. Success path unchanged.

## UI-SPEC lines changed (82-UI-SPEC.md, post-edit line numbers)

- Line 9: `revised_at: "2026-10-31"` (status stays `approved`).
- Lines 307-308: Section 6 state table rows `Rows not loaded` and `Review incomplete`.
- Line 330: Confirm deletion button sentence (disabled order decides the helper).
- Lines 334-336: Section 7 `Amendment 2026-10-31 (gap plan 82-17)` note, `closeOnEsc={!pending}`, Keep waiting disabled while in flight.
- Line 343: Confirm bullet (`Keep waiting` disabled too, Esc does not close).
- Line 382: Section 8 row `Certificate unreadable`; line 392: `cert-unreadable` rule-id note.
- Line 416: Section 9 row for a refused or failed Run Cleanup Now.
- Lines 448-451: Copywriting rows Helper (rows not loaded), Helper (review incomplete), Notice (review incomplete), Error (Run Cleanup Now).
- Lines 503-504 and 509: UI Considerations, two new S6 partial lines and the replaced S7 loading line.

## RED evidence

Task 1: 11 of 39 tests failed before the implementation (no notice, button enabled on page 1, no Load all line). Task 2: the renamed pending test failed (Keep waiting was enabled); the two after-the-request cases passed on today's code and are guards, as the plan expected. Task 3: all 7 new failure cases failed first (no toast, unhandled rejection for the unreadable body and the network error).

## Verification

- `npx vitest run` of AutonomousOpsRetentionReview, AutonomousOpsRetentionConfirmDialog, RetentionPolicyDashboard, AutonomousOpsPlatformHealth and autonomousOpsCopy: 5 files, 124 tests, exit 0 (read directly in the foreground).
- `npx tsc --noEmit -p .`: exit 0, no output.
- `npm run build`: exit 0, writes `dist-new` only.
- Acceptance greps: `nextOffset === null` 2, `Load all` 1, `RetentionIncomplete` 4, `incomplete: null` 1, `closeOnEsc={!pending}` 1, `disabled={pending}` 1, `stays enabled` 0, `Amendment 2026-10-31` 1, `Load all {total} rows before confirming.` 3, `cert-unreadable` 1, `^status: approved` 1, `showToast` 3, `Couldn't run cleanup.` 2, `r.ok` 1. File sizes: review card 368 lines, review test 498.
- `git status --short` shows no path of this plan uncommitted; `App.tsx` is in none of the three commits.

## Deviations from Plan

None - plan executed as written. The paged WR-01 test trimmed a redundant default-helper assertion and one blank-line block so the review test stays under 500 lines (498), as the plan requires.

## Requirements

HEAL-06 is listed in `requirements-completed` as the template asks, but per the plan no requirement was marked complete in REQUIREMENTS.md; the HEAL ticks stay Pending until phase verification.

## Known Stubs

None.

## Threat Flags

None. T-82-53, T-82-54 and T-82-55 are mitigated as planned; the server `detail` reaches the toast as plain text only when it is a string.

## Authentication Gates

None.

## Not deployed

The UI is built in `dist-new` but not published: nothing was copied to /var/www, there was no backend restart and no `git push`. No MongoDB was started or touched.

## Self-Check: PASSED

Files exist; commits c157feb10, bdb6bf0d2 and 57705c85a are ancestors of HEAD; `git rev-list --count 35622b4d0..57705c85a` is 3.
