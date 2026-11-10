---
phase: 85-first-line-service-desk
plan: 42
subsystem: service-desk
tags: [gate, records, gap-closure, G-85-3, G-85-4b, G-85-5, review-disposition, security-register]
status: complete

requires:
  - phase: 85-first-line-service-desk
    provides: gap plans 85-37 to 85-41 (citation rule, hand-off rule, create-field and audience fixes, requester controls, staff-action error toasts)
provides:
  - whole-phase gate result for the third gap round (backend 2744 passed, Vitest 1922 passed, build 0)
  - WR-602, WR-603 and IN-604 recorded fixed in 85-REVIEW-DISPOSITION.md (open 32 to 29)
  - AR-85-11 re-recorded as SUPERSEDED; T-85-05 and T-85-20 reworded to the 85-37 rule
  - D-42 and D-43 in 85-CONTEXT.md; rows 85-37..85-41 and the gate line in 85-VALIDATION.md
affects: [gsd-secure-phase 85, gsd-verify-work 85, verifier]

actuals:
  tokens: 14000
  tasks: 2
  commits: 1
plan_head_before: 4041e9c2a75bdb4aa417228b03099871e9ed7262
plan_head_after: b1964f6343a75d51c0a8df4b80b3161b4193308d
commits: 1

tech-stack:
  added: []
  patterns: ["gate on a private mongod, then record dispositions only on a green gate"]

key-files:
  created: []
  modified:
    - .planning/phases/85-first-line-service-desk/85-REVIEW-DISPOSITION.md
    - .planning/phases/85-first-line-service-desk/85-SECURITY.md
    - .planning/phases/85-first-line-service-desk/85-CONTEXT.md
    - .planning/phases/85-first-line-service-desk/85-VALIDATION.md

key-decisions:
  - "Gate was green with no known failure: the two test_catalogue_route_parity.py failures of 85-36 did not recur, so no clean-HEAD worktree was needed"
  - "VALIDATION rows carry the gap plans' own wave numbers (1 to 5)"

requirements-completed: [DESK-01, DESK-02, DESK-03, DESK-04, DESK-05, DESK-06, DESK-07]
---

# Phase 85 Plan 42: Third gap round gate and records Summary

The whole Phase 85 gate is green on the code of 85-37 to 85-41, and the review, security, context and validation records now match the code.

## Task 1 (tracer): the gate

All commands ran on the private mongod 127.0.0.1:27998. Nothing reached the live mongod except the read-only omni_test_ listing.

- Backend (the 85-36 command, unchanged): `2744 passed in 1331.38s (0:22:11)`, exit 0, 0 failed, 0 errors, 0 skipped. That is above the 2694 floor. The two test_catalogue_route_parity.py failures seen at 85-36 (user's uncommitted catalogue files) did not occur on this working tree, so the clean-HEAD worktree proof was not needed and no worktree was created.
- Vitest `npx vitest run src/__tests__`: `Test Files 119 passed (119)`, `Tests 1922 passed (1922)`, exit 0. The ServiceDeskKnowledgeGaps flake the orchestrator saw at wave 5 did not recur here (the gate ran with nothing else running), so no re-run of that file was needed.
- `npm run build`: exit 0 (dist-new, index-yJn7g8ge.js, not published).
- omni_test_ databases on the live mongod: 0 before, 0 after.

## Task 2: records (commit b1964f634)

- 85-REVIEW-DISPOSITION.md: WR-602 fixed 0efe58463 (85-39), WR-603 fixed 6fcb73084 (85-39), IN-604 fixed 3f70dbf6a, 200daaaf9 (85-40), 4415379d6, ac80717e6 (85-41), "screen half; the manifest write-entry note stays open". `disposition: fixed` count 16, `open: 29`, every other row unchanged.
- 85-SECURITY.md: exactly three rows changed (3 insertions, 3 deletions): T-85-05 and T-85-20 with the 85-37 wording (T-85-128, A-85-G33) and the earlier text after "Earlier wording:", and AR-85-11 SUPERSEDED 2026-11-10 (G-85-5, plan 85-39) with its original rationale kept. SUPERSEDED count 5, Earlier wording count 2.
- 85-CONTEXT.md: new subsection "UAT amendments (2026-11-10, gap G-85-5, user-approved in 85-UAT.md)" with D-42 (amends D-39) and D-43 (amends D-33 and D-41); no earlier line changed.
- 85-VALIDATION.md: rows 85-37 to 85-41 added to the Per-Task Verification Map, and a "Third gap round" line in the Validation Audit; nyquist_compliant true and status validated unchanged.
- 85-VERIFICATION.md and 85-UAT.md untouched.

## Deviations from Plan

None - plan executed exactly as written. (Execution note: the Task 2 edits were prepared in the working tree while the gate ran and committed only after it was green.)

## For the user

Deployment steps that stay yours:
- Backend restart (no --reload): ships 85-37 (citation rule), 85-38 (rule-aware hand-off) and 85-39 (create-field drop, no tenant-socket push of audience notices). No migration.
- UI publish of dist-new (`sudo cp` to /var/www): ships 85-40 (requester sees no staff controls) and 85-41 (staff-action failures shown as toasts).

Planner assumptions to confirm (A-85-G33 to A-85-G43):
- A-85-G33: citations that were not given are dropped and articles relabelled A1..An; D-19 still holds.
- A-85-G38: a requester's ticket keeps approval_required true when its template says so (fail closed); the other five template defaults are dropped.
- A-85-G39: API-key callers need manage:tickets in the key's scopes to set the six fields.
- A-85-G40: the platform tenant's untagged pending-agent notice keeps its push; tenant_admins notices are feed-only.
- A-85-G41: requesters no longer see the Work Log and Links tabs, the staff hint above the comment list or the click-to-edit title (History stays).
- A-85-G42: the row delete button and "Delete selected" follow manage:settings.
- A-85-G43: toasts show the fixed sentence apiService throws, not the server detail.

Live re-check of 85-38 (llama3.2:3b, read-only): `service_desk_eval.py --sets` escalation 150/0, injection 33 (25 reached the model, 8 handed off, 0 failed), retrieval 100/0 with margin 0.2268, identical to the UAT round 3 baseline; the printer ticket reproduction passed 3 of 3 with byte-identical replies and rule None. The full path on the live platform needs a UAT round 4 after the restart.

Follow-ups left open: A-85-SCOPE3 (WR-601, WR-604, IN-601 to IN-603, older open rows, the manifest write-entry note of IN-604, UAT test 1 note on --measure), the tray half of UAT test 3 (agent 2.1.18 built, not published), and the re-run of /gsd-secure-phase 85 (to record T-85-128 to T-85-140), the verifier and /gsd-verify-work 85. Phase 85 is not complete until verified.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- 85-42-SUMMARY.md and the four edited records exist; commit b1964f634 is an ancestor of HEAD; `commits: 1` measured from ledger base 4041e9c2a.
