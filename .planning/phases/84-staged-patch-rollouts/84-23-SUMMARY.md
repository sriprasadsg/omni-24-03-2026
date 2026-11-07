---
phase: 84-staged-patch-rollouts
plan: 23
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, canary, approval-lines, suggest-level, circuit-breaker, gap-closure, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-03 approval lines (raise_line, approve_line, deny_line, closed_line), 84-10 ring cards, 84-20 settle
provides:
  - a canary row the gate holds (suggested or awaiting_approval) is the ring's Install line, found by approve, deny, cards and closed_line
  - a refused canary row stores only the attempt and is retried, then fails the host with a reason after MAX_ATTEMPTS
  - lines.track_line, the one helper that remembers an open approval row on its computer
  - dispatcher stores installJobId and installInstructionId when an approved install is sent
  - rollout_not_delivered is transparent to the circuit breaker
affects: [84-24, 84-27]

requirements-completed: [PTCH-06, PTCH-01]

actuals:
  tokens: 5200
  tasks: 3
  commits: 4
commits: 4
plan_head_before: ae44a3e2f66fb03f7fad505cedfb3d03cec84ed4
plan_head_after: d0f68b449dede97bac8691680736c44b44b04e42

tech-stack:
  added: []
  patterns:
    - "every row a person must decide (awaiting_approval or suggested) goes through lines.track_line; the host's installActionId is reserved for the automatic row that was really dispatched"
    - "a recorded refusal is never remembered as the host's install: only the attempt counter moves, so the next pass retries"

key-files:
  created:
    - backend/tests/test_patch_rollout_gap_lines.py
  modified:
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/lines.py
    - backend/autonomous_ops/rollout/cards.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/autonomous_ops/ledger.py

key-decisions:
  - "KD-84-G1: Suggest raises approval lines. A rollout row the gate records as suggested is treated exactly like awaiting_approval: it becomes the ring's Install (or Reboot) line with its own Approve and Deny. A person approves it either way, so one approval per stage still holds, and the circuit breaker or unreadable settings can drop a tenant to Suggest in the middle of a running ring, which a Start-time refusal could never unwedge. Start keeps refusing only off. Reversible: server code only, no stored-shape change, no published contract."
  - "A canary row keeps ruleId rollout:canary_install; lines._approval_filter, lines.closed_line and cards._RULES now accept it for the install line instead of renaming the rule (no stored-shape change)."
  - "dispatcher stores installJobId/installInstructionId only when the host has no automatic row in flight (installActionId empty), so an approved line row can never overwrite the ids of a running automatic canary row."

coverage:
  - id: D1
    description: "A suggested or escalated canary row becomes the Install line (lineActionIds.install, linePatchIds, waitReason approval, no installActionId); approving it sends it once, stores installJobId and installInstructionId, and the agent result settles the host"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_a_suggest_level_canary_row_becomes_the_install_line_and_nothing_is_sent"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_approving_the_held_canary_line_sends_it_stores_its_ids_and_the_result_settles_the_host"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_a_canary_row_the_gate_escalated_to_awaiting_approval_is_the_same_install_line"
        status: pass
    human_judgment: false
  - id: D2
    description: "At Suggest level a later ring raises its Install line and the card offers Approve and Deny; deny or expiry of a held canary line halts the rollout; a held canary row and a deferred patch on one host share one line"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_at_suggest_level_a_later_ring_raises_its_install_line_and_the_card_offers_approve_and_deny"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_denying_the_held_canary_line_halts_the_rollout_with_install_denied"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_a_held_canary_line_nobody_answers_in_24_hours_halts_with_approval_expired"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_a_held_canary_row_and_a_deferred_patch_on_one_host_share_one_install_line"
        status: pass
    human_judgment: false
  - id: D3
    description: "A refused canary row never parks the host: no installActionId, retried as a new attempt, failed with a reason at MAX_ATTEMPTS"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_a_refused_canary_row_never_parks_the_host_it_is_retried_and_then_fails_with_a_reason"
        status: pass
    human_judgment: false
  - id: D4
    description: "Three autoDispatched failed rollout_not_delivered rows do not lower the tenant's level"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_three_not_delivered_rollout_rows_do_not_lower_the_tenants_level"
        status: pass
    human_judgment: false
---

# Phase 84 Plan 23: Held and refused canary rows Summary

**A canary row the gate holds (Suggest level, hourly limit, unreadable settings) is now the ring's Install line with Approve and Deny, a refused one is retried then failed with a reason, and rollout_not_delivered rows no longer count toward the circuit breaker.**

**Duration:** about 35 min | **Tasks:** 3 | **Files:** 5 modified, 1 created

## Accomplishments

- **CR-02 / KD-84-G1.** `installs.canary_auto` no longer stores a held row as the host's automatic install (which left the host waiting for ever with no card). A row in `awaiting_approval` or `suggested` goes through the new `lines.track_line` (same bookkeeping `raise_line` does), so it appears on the ring card, approves and denies through the existing line routes, and a deny or 24-hour expiry halts the rollout (`closed_line` now knows `rollout:canary_install`).
- **CR-01.** A recorded refusal stores only the attempt counter; `needs_decision` stays true so the next tick decides again as a new attempt; at `MAX_ATTEMPTS` the host is failed with the gate's reason text (fallback: the not-delivered text).
- An approved held install now writes `installJobId` and `installInstructionId` on the host when it is sent (only when no automatic canary row is in flight on that host).
- **WR-01.** `rollout_not_delivered` added to `BREAKER_IGNORED`. `rollout_no_new_boot` was NOT added: it is only written on reboot rows (`reboots.py`, `revert.py`) which are approve-class and approved by a person, never `autoDispatched`, so the breaker's `_AUTO_ROWS` filter never sees them.
- Cards: `_is_open`, `_pairs` (via one `_OPEN_STATES` list) and `_RULES` accept `suggested` rows and the canary rule; a ring 0 line made only of held canary rows shows the gate's own reason instead of the "not reversible" sentence.

## TDD record

- **RED** (`d2d35dfa5`): 9 tests written; all 9 failed on the planned assertion (host stored `installActionId` with no `lineActionIds`; `approve_line` found no rows; refusal parked the host with `AO-refused-x`; breaker counted three not-delivered rows). Semantic assessment: every failure was the target assertion for the intended reason, none a load, fixture or syntax fault.
- **GREEN** (`b4b12a817`, `96f904ebb`, `d0f68b449`): 9/9 pass; 113 tests across the seven suites named in Task 3 pass; the full `test_patch_rollout_*.py` plus `test_autonomous_ops_ledger.py` and `test_autonomous_ops_verify.py` pass (433 passed).
- No REFACTOR commit needed.

## Commits

| Hash | Message |
|------|---------|
| d2d35dfa5 | test(84-23): add failing tests for held, suggested and refused canary rows |
| b4b12a817 | feat(84-23): a held or refused canary row is an Install line or a retry, never a wedge |
| 96f904ebb | feat(84-23): show suggested and held canary rows on the ring card |
| d0f68b449 | fix(84-23): the circuit breaker ignores rollout_not_delivered rows |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Held canary rows were invisible to the line and card queries**
- **Found during:** Task 1
- **Issue:** `lines._approval_filter` and `cards._RULES` matched only `rollout:install/reboot/revert_reboot`, so a row with `ruleId rollout:canary_install` could not be found by `approve_line`, `deny_line` or the cards even after tracking it. The plan only listed `closed_line`.
- **Fix:** `_approval_filter` accepts the canary rule for the install line; `cards._RULES` includes it.
- **Files modified:** lines.py, cards.py
- **Commits:** b4b12a817, 96f904ebb

**2. [Rule 2 - Missing critical] dispatcher must not overwrite an automatic row's ids**
- **Found during:** Task 1
- **Issue:** storing `installJobId`/`installInstructionId` unconditionally would replace the ids of an automatic canary row in flight on the same host (a host can hold both an automatic and a held row), breaking `_settle_auto`.
- **Fix:** write them with a filter `installActionId: None`.
- **Commit:** b4b12a817

**3. [Plan wording] Test count**
- The plan's Test 5 (deny and expiry) was written as two tests, so the file has 9 tests, not 7/8.

**Total deviations:** 2 auto-fixed, 1 wording. **Impact:** none on scope.

## Findings for later plans

- **WR-04 (plan 84-27):** after a held canary line is denied or expires, the rollout halts correctly, but the host still reads `installed` (settle leaves denied/expired rows alone and, with nothing outstanding, marks the host installed). The same happens for later-ring lines today. Not patched here, as the plan directs; my deny/expiry tests assert the halt and that nothing was sent, not the host state.
- `line_rows` for the install line now also sees automatic canary rows, so a second click on a ring 0 line with only an auto row answers `already_handled` instead of `nothing_open`. No existing test depends on it.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; T-84-65, T-84-66 and T-84-67 mitigated as planned (a suggested row is approvable only through the existing line route and `approvals.approve`).

## Self-Check: PASSED

- backend/tests/test_patch_rollout_gap_lines.py, installs.py, lines.py, cards.py, dispatcher.py, ledger.py present; all under 500 lines.
- Commits d2d35dfa5, b4b12a817, 96f904ebb, d0f68b449 are ancestors of HEAD.
- Acceptance greps: `installActionId` in installs.py only in retry_fields, the needs_decision/canary guards, the shadow branch and `_send`; `suggested` reached in lines.py (`OPEN_ROW_STATES`) and cards.py (`_OPEN_STATES`, used by `_is_open` and `_pairs`); `rollout:canary_install` in `closed_line`; `installInstructionId` in dispatcher.py; `rollout_not_delivered` inside `BREAKER_IGNORED`.
- Private mongod on port 27998 stopped.
