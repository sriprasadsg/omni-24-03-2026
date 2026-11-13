---
phase: 86-activity-reporting-hardening-live-validation
plan: 10
subsystem: autonomous-ops-golive-docs
tags: [go-live, runbook, copy-gate, shadow-mode, documentation]
status: complete

requires:
  - phase: 86-07
    provides: the five go-live check ids, the lift gate and the go-live routes the document matches
provides:
  - docs/autonomous-ops-go-live.md (operator runbook for the five live checks, the lift rules and the digest and export spot checks)
  - the document registered in the ACTV-08 copy gate (JSON list, pytest list, vitest list)
affects: [86-12]

actuals:
  tokens: 6500
  tasks: 2
  commits: 1
plan_head_before: 4d84b075c168522af66e871398795f8db6350590
plan_head_after: 09cc2be81a4c4eb1f815661cba52ea0dc4c4e325

tech-stack:
  added: []
  patterns:
    - a runbook whose Summary lines are the authority the Going live card copies (UI-SPEC R15)

key-files:
  created:
    - docs/autonomous-ops-go-live.md
  modified:
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Triggers for checks 1 and 2 are the user's own combination (option-c): two-source path for check 1, Linux and Windows both walked for check 2; see Decisions"
  - "The document carries no IP address literal; check 1 uses the placeholder [public address you control]"
  - "Check 3 stops and starts omni-watchdog.timer, not the service, so the Summary says timer (a correction of UI-SPEC R15)"

requirements-completed: [GATE-09]

coverage:
  - id: D1
    description: "The repo documents how to walk each of the five live checks, one section per check in gate order with Check id and Summary lines, with no address literal"
    requirement: GATE-09
    verification:
      - kind: command
        ref: "grep checks for Check id lines, Summary lines, omni-watchdog.timer, placeholder count and IPv4/IPv6 literal absence"
        status: pass
    human_judgment: true
    rationale: "Whether an operator can walk each check from the text alone, and whether the Linux/Windows reboot and two-source steps match the real UI, is not asserted by a test"
  - id: D2
    description: "The document is in the copy gate list on all three sides and passes the banned-term rules"
    requirement: GATE-09
    verification:
      - kind: test
        ref: "backend/tests/test_autonomous_ops_copy.py (33 passed)"
        status: pass
      - kind: test
        ref: "src/__tests__/autonomousOpsCopy.test.ts (23 passed)"
        status: pass
    human_judgment: false
---

# Phase 86 Plan 10: Go-live runbook Summary

A copy-gated operator runbook, docs/autonomous-ops-go-live.md, that walks the five live go-live checks (firewall round-trip, reboot gate on Linux and Windows, watchdog timer stop and start, test alert, live stop drill), plus the lift rules and the digest and export spot checks.

## Decisions

Task 1 (checkpoint:decision, gate="blocking-human") was answered by the user. The resolution below is the orchestrator's reading of that answer.

- Chosen option id: option-c (the user's own combination of option-a and option-b).
- User answer to the trigger question (options offered: option-a "Linux kernel", option-b "Windows update"): "both Linux and windows"
- User answer to the test tenant question ("Is a test tenant already set up for the live walk?"): "Not yet"

Resolved steps (orchestrator's reading of the user's answer):

- Check 1 (firewall_round_trip): exactly as option-a, the real two-source path. A public test address the operator controls is listed in a threat feed the platform reads and is also flagged by a second source (or the test tenant's two-source rule is switched off in Response settings so one source is enough, and put back afterwards); the test host connects to it; the next sweep blocks it. Documentation and non-global ranges are refused by the agent, so the address must be public and operator-controlled.
- Check 2 (reboot_gate): two parts, Linux AND Windows, both walked. (i) A disposable Linux host with a held-back kernel package gets a rollout whose Reboot line must wait on its approval card. (ii) A disposable Windows host with a Windows cumulative update goes through the same rollout and reboot-approval path (depends on Windows Update offering a cumulative update at walk time, and is slower). Check 2 is recorded once both parts pass.
- Test tenant: none yet. The document tells the operator to create a dedicated test tenant first (agent 2.1.16 or later for check 1, 2.1.17 or later for check 2, shadow off, level Undoable-auto, rings and an open maintenance window for check 2), and never to use a customer organization.

## Tasks

| Task | Name | Commit |
|------|------|--------|
| 1 | The user chooses the operator trigger for checks 1 and 2 (decision only, no code) | none (recorded in Decisions) |
| 2 | Write docs/autonomous-ops-go-live.md and register it in the copy gate | 09cc2be81 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Frontend scanned-file count assertion**
- **Found during:** Task 2
- **Issue:** src/__tests__/autonomousOpsCopy.test.ts asserts `FRONTEND_FILES` has length 22, where FRONTEND_FILES is every listed file not starting with `backend/`. Registering the document (a `docs/` path) makes it 23, so the test failed.
- **Fix:** Changed the expected length to 23. The document is scanned by the vitest side only; the pytest side scans only `backend/` entries and just checks the shared list.
- **Files modified:** src/__tests__/autonomousOpsCopy.test.ts
- **Commit:** 09cc2be81

### Wording choices

- The level is written "Automatic within limits (undoable_auto in the API)", the label the screen shows, instead of "Undoable-auto". The patch rollout reboot step is called the **Restart** line, the label the rollout card uses.
- Check 1 requires a Linux test host and walks a Windows host the same way when the platform has Windows agents; the user's answer fixed only the trigger, so the host list follows the research outline.

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** none on scope.

## Open decision for the user (found while writing the document)

The test organization cannot be lifted out of shadow mode through the app before the walk. Checks 1, 2 and 5 need real actions, so shadow must be off for the test organization, but the server-side lift gate (86-07) refuses every organization, a test one included, until all five checks are recorded and seven days of shadow records exist. The deployment-wide switch AUTONOMOUS_REMEDIATION_DRY_RUN (default on) also forces shadow on and is changed only by the user, with a backend restart. The document states this plainly under "Before you start" and, as a stopgap marked "Open decision", has the platform owner turn the test organization's own flag off directly on the server and say so in each note. Nothing in this plan changes the gate. Decide whether to keep that stopgap, exempt a designated test organization in the gate, or allow checks to be recorded against a test organization before the lift.

## Known Stubs

None.

## Threat Flags

None. The document holds no secret, password, token or real customer host name; the on-call file is named by path only (T-86-26).

## Self-Check: PASSED

- docs/autonomous-ops-go-live.md exists, 235 lines; 5 Check id lines, 5 Summary lines, 8 level-2 headings, placeholder 4 times, no IPv4 or IPv6 literal.
- Commit 09cc2be81 is an ancestor of HEAD; `git rev-list --count 4d84b075c..HEAD` printed 1 before this summary commit.
- pytest test_autonomous_ops_copy.py: 33 passed. vitest autonomousOpsCopy.test.ts: 23 passed.
- `grep -c "docs/autonomous-ops-go-live.md"` prints 1 for each of the three copy-gate files.
