---
phase: 84-staged-patch-rollouts
plan: 10
subsystem: api
status: complete
tags: [patch-rollout, approval-cards, needs-your-decision, approvals, routes, mongodb, python, fastapi]

requires:
  - phase: 84-staged-patch-rollouts
    provides: "84-03 lines.approve_line / deny_line and the LineDecisionResult shape; 84-08 reboot line rows; 84-05 windows; 84-02 messages and types.ts"
  - phase: 83-autonomous-response
    provides: "incident_views.stopped_view, views.build_caller and actor_for, DecisionBody, the Needs your decision card rules"
provides:
  - "rollout/cards.py - list_cards: one ApprovalCard per (rollout, ring) with Install, Reboot and Revert restart lines, per-line canApprove / canDeny, settled result texts, countText"
  - "GET /api/autonomous-ops/rollout-cards"
  - "POST /api/autonomous-ops/rollout-lines/{rollout_id}/{ring}/{line}/approve and /deny (DEV-1)"
affects: [84-15, 84-21]

requirements-completed: [PTCH-06]

actuals:
  tokens: 21000
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 78855af67ed86dbfcf692dc94121ff853ac21dc6
plan_head_after: 1cf45bf127214056a6e96c9c3d2b7e93ca8631d7

tech-stack:
  added: []
  patterns:
    - "a card is built from the approval rows of one rollout ring; the permission flags are computed on the server per line (can_control and signed-in session; Approve also off during a stop)"
    - "a whole-line decision answers the LineDecisionResult itself: 200 when something was decided, 409 with the same body plus `detail` otherwise, 404 for a rollout that is not the caller's"

key-files:
  created:
    - backend/autonomous_ops/rollout/cards.py
    - backend/tests/test_patch_rollout_cards.py
  modified:
    - backend/autonomous_ops_response_endpoints.py
    - backend/autonomous_ops/rollout/lines.py
    - backend/autonomous_ops/rollout/messages.py

key-decisions:
  - "DEV-1 (UI-SPEC Planning Deviations, pending user review): Approve and Deny on a rollout line call POST /api/autonomous-ops/rollout-lines/{rolloutId}/{ring}/{line}/approve and /deny instead of the per-action approve route. The engine is the same approvals.approve / approvals.deny, once per computer row, with the same permission (control:autonomous_ops), signed-in session (API keys refused), stop rule (Approve refused, Deny allowed), 24 h expiry and single use."
  - "Ring in the card is the ring index as a string ('0'..'3'), the same number the line routes take; anchorId is approval-rollout-{rolloutId}-{ring}"
  - "A line decided a moment ago stays on its card for 60 seconds (SETTLED_STAY, about two polls), so the result text can be read; a card with neither an open nor a just-decided line is not listed. A denial outranks an expiry, which outranks an approval, when a line has rows in more than one outcome"
  - "Rows ended by the rollout itself (rollout_closed, rollout_halted, rollout_not_delivered) are not a person's decision and never appear on a card"

patterns-established:
  - "Why and What happens for a card line are filled from messages.CARD at read time (previous ring name and pass time in the organization's zone, window clause, failure share), not taken from the row's stored reasonText"

coverage:
  - id: D1
    description: "One card per waiting ring: Install line label, target text (first three patch ids then +m more), at most 10 computer names with the total, Why and What happens with the window clause, the nearest expiry, subtitle and anchor"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_ring_with_five_patches_on_twelve_computers_is_one_card_with_one_install_line"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_closed_window_says_when_it_next_opens"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_canary_computer_that_cannot_be_checked_has_the_not_reversible_why"
        status: pass
    human_judgment: false
  - id: D2
    description: "The Reboot line appears only once raised and lists only computers that need a restart; flags follow the caller, an API key and the stop; shadow tenants and other organizations get no card"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_the_restart_line_appears_only_once_it_is_raised_and_lists_only_computers_that_need_one"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_flags_follow_the_caller_and_the_stop"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_shadow_tenant_has_no_card"
        status: pass
    human_judgment: false
  - id: D3
    description: "Settled lines carry the 83 result texts (approved now or when the window opens, denied by name, expired) for one poll, and cards order by soonest expiry and page"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_denied_line_reads_its_result_for_one_poll_and_then_leaves"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_an_expired_line_reads_the_expired_result"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_cards_are_ordered_soonest_expiry_first_and_page_by_the_limit"
        status: pass
    human_judgment: false
  - id: D4
    description: "One request approves or denies one line of one ring exactly once; control permission and a signed-in session are required, an API key is refused, a stop refuses Approve but not Deny; bad paths 422, foreign or unknown rollout 404"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_person_with_control_approves_a_whole_line_with_one_request_and_a_second_answers_409"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_an_api_key_and_a_role_without_control_cannot_approve_or_deny"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_one_request_decides_one_line_of_one_ring_only"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cards.py#test_a_bad_path_is_422_and_an_unknown_or_foreign_rollout_is_404"
        status: pass
    human_judgment: false

duration: 18 min
completed: 2026-11-06
---

# Phase 84 Plan 10: Rollout Approval Cards and Line Routes Summary

**The Needs your decision card for a patch rollout ring (Install, Restart and Revert restart lines, each with its own server-computed Approve and Deny flags and spelled-out consequences) and one-click line approve and deny routes that run the existing per-computer approval engine under the unchanged permission, session, stop and expiry rules.**

## Accomplishments

- `cards.list_cards` groups the approval rows of each rollout ring into lines, fills every sentence from `messages.CARD` (window clause open now / next opens, failure share, previous ring and pass time in the organization's zone), and lists at most 10 computer names with the total. Ring 0 install lines use the "can't be reversed on every computer in this ring" Why.
- Flags: `canApprove` and `canDeny` need `control:autonomous_ops` in a signed-in session; `canApprove` is off during a stop. A view-only role, Platform Support and an API key read every flag false.
- Settled lines carry the four 83 result texts for 60 seconds, then the card leaves. A page returns `items`, `total`, `offset`, `limit`, `stopped`, `serverNow` and `countText` ("1 rollout ring").
- Three routes on the existing response router (already mounted and on the copy-gate lists, so no registry or catalogue edit). Path validation: rollout id 1 to 64 characters, ring 0 to 3, line a literal.

## Task Commits

TDD plan, both tasks with RED then GREEN.

1. **Task 1 RED** - `56ab77452` (test): 10 of 12 failing tests plus a skeleton `list_cards`
2. **Task 1 GREEN** - `4dc388ae7` (feat): card payloads, one restart sentence in messages
3. **Task 2 RED** - `dc994192e` (test): 8 failing route tests (404 on missing routes)
4. **Task 2 GREEN** - `1cf45bf12` (feat): the three routes, `deny_line` name fix

## Decisions Made

See `key-decisions`. DEV-1 is recorded there as the plan asks; it remains pending the user's review with the other UI-SPEC deviations (84-21 hands them over).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `deny_line` named nobody for a real caller**
- **Found during:** Task 2
- **Issue:** `lines.deny_line` (84-03) read `approver["name"]`, but the routes pass the actor dict of `views.actor_for` (`username`, `display`, `tier`), so the message read "Denied by . The rollout halts at ...".
- **Fix:** it now uses display, then name, then username. A route test pins "Denied by ann@example.test. The rollout halts at Everyone else."
- **Files modified:** backend/autonomous_ops/rollout/lines.py
- **Commit:** 1cf45bf12

**2. [Rule 2 - Missing copy] One sentence added to `rollout/messages.py`**
- `CARD.what_happens.restart_no_window` for the restart line when the organization has no next window to name (the existing sentence needs `{opens}`). Commit 4dc388ae7.

**3. [Plan text vs messages.py] Reboot Why wording**
- The UI-SPEC text says "{n} computers need a restart to finish installing."; `messages.CARD.why.reboot` (fixed by 84-02) reads "A restart is needed on {computers} to finish installing." The card uses messages.py, as in 84-09. Same for "Removing the update needs a restart on {computers}." 84-15 should expect the messages.py wording.

**Total deviations:** 3 (1 bug, 1 missing copy, 1 note). **Impact:** none on the plan's truths.

## Issues Encountered

- A canary-ring install line (ring 0) can exist because the computer cannot check reversibility or the package usually needs a restart, not only because a patch is not reversible; its Why uses the plan's "can't be reversed on every computer in this ring" sentence for all of them. The stored per-computer reason on the row is more specific; the card does not show it.
- The 409 answer carries the full `LineDecisionResult` plus `detail` (the same sentence), so the browser can read either `status` or `detail`.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-84-33: `_require_control` plus `_require_interactive_session`, API keys refused, per-row `approvals.approve`. T-84-34: id length cap, ring range, line literal, tenant from `_tenant_for`, platform organization 409, foreign rollout 404. T-84-35: each row records the approver's username (pinned by a test) and the ledger mirrors the transition. PROH-84-04c holds: no approve-all, and one request touches one rollout, ring and line.

## User Setup Required

None. Nothing was deployed, restarted, published or pushed; the private test mongod (port 27998) was stopped. The new routes load on the next backend restart, which is the user's.

## Next Phase Readiness

- 84-15 builds the card from `GET /api/autonomous-ops/rollout-cards` (`ApprovalCard` shape plus page keys `stopped`, `serverNow`, `countText`) and calls the line routes; the `ring` field is the index string used in the route path.

## Verification

- `test_patch_rollout_cards.py` 20 passed; with response endpoints, catalogue slice, route auth baseline, copy gate, lines, dispatcher, incident route and route parity: 196 passed. All tests matching `autonomous_ops` or `patch_rollout` (1367) passed on a private mongod, 0 skipped. ruff clean.
- Acceptance: `def list_cards` 1; `rollout-lines` in the endpoints file 4; endpoints file 269 lines, cards.py 294.

## TDD Gate Compliance

RED `56ab77452` / GREEN `4dc388ae7` (Task 1); RED `dc994192e` / GREEN `1cf45bf12` (Task 2). Task 1's RED was a skeleton plus tests (10 of 12 failed on assertions; the two that passed assert emptiness). The `check tdd-red-evidence` classifier was not run (pytest console output; plan is `type: execute`).

## Self-Check: PASSED

- Created files exist: cards.py, test_patch_rollout_cards.py; commits 56ab77452, 4dc388ae7, dc994192e, 1cf45bf12 are ancestors of HEAD.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
