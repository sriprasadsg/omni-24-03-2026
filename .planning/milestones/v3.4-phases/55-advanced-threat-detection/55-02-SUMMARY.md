---
phase: 55-advanced-threat-detection
plan: 02
subsystem: security
tags: [remediation, playbook, deterministic-dispatch, anomaly, ueba]

# Dependency graph
requires:
  - phase: 53-autonomous-remediation
    provides: select_playbook()/ACTION_MAP/_finding_attr deterministic YAML playbook dispatcher, kill_process playbook
provides:
  - "select_playbook() anomaly branch — shadow_ai_detected + real agent_id maps to the existing kill_process playbook; every other anomaly returns None -> no_playbook"
affects: [55-03-predictive-containment-trigger]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Extend-not-rebuild dispatch: new finding_type branch reuses _finding_attr accessor and existing by_name lookup, no new ACTION_MAP entry, no parallel dispatch mechanism (D-02)"

key-files:
  created: []
  modified:
    - backend/remediation_playbook_service.py
    - backend/tests/test_remediation_playbook.py

key-decisions:
  - "Only shadow_ai_detected (the one UEBA rule carrying a real agent_id) maps to a dispatchable playbook this phase; the other 9 UEBA rule types resolve to no_playbook — a deliberate scope narrowing per RESEARCH Assumption A2, confirmed at the checkpoint:decision in Plan 55-03 before the trigger is wired"
  - "kill_process.yaml is reused verbatim for the anomaly path rather than adding a near-duplicate shadow_ai_kill.yaml (RESEARCH Open Question 1)"

requirements-completed: [AUT-03]

coverage:
  - id: D1
    description: "select_playbook() anomaly branch: finding_type=='anomaly' with anomaly_rule=='shadow_ai_detected' AND a real agent_id returns the kill_process playbook; any other anomaly (no agent_id / other rule) returns None"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_remediation_playbook.py::test_select_playbook_for_shadow_ai_anomaly_with_agent_returns_kill_process"
        status: pass
      - kind: unit
        ref: "backend/tests/test_remediation_playbook.py::test_select_playbook_for_shadow_ai_anomaly_without_agent_returns_none"
        status: pass
      - kind: unit
        ref: "backend/tests/test_remediation_playbook.py::test_select_playbook_for_other_anomaly_rule_returns_none"
        status: pass
      - kind: unit
        ref: "backend/tests/test_remediation_playbook.py::test_select_playbook_unknown_finding_type_returns_none"
        status: pass
    human_judgment: false
  - id: D2
    description: "No new ACTION_MAP entry introduced — allowlist stays exactly 7 entries; anomaly branch is a pure deterministic if/elif with no LLM"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "grep -c '\"anomaly\"' backend/remediation_playbook_service.py (>=1) and ACTION_MAP entry count confirmed unchanged at 7"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-08-03
status: complete
---

# Phase 55 Plan 02: Anomaly-to-Playbook Mapping (AUT-03) Summary

**select_playbook() gains a deterministic `finding_type == "anomaly"` branch mapping shadow_ai_detected + a real agent_id onto the existing kill_process playbook, with every other anomaly honestly falling through to no_playbook — zero new action surface, zero LLM.**

## Performance

- **Duration:** ~8 min active execution (single task)
- **Started:** 2026-08-03T13:59:00Z (session start, immediately following 55-01)
- **Completed:** 2026-08-03T14:05:23Z (task commit `c951d4d`)
- **Tasks:** 1/1
- **Files modified:** 2 (`backend/remediation_playbook_service.py`, `backend/tests/test_remediation_playbook.py`)

## Accomplishments
- `select_playbook()` gained a new `if finding_type == "anomaly":` branch, placed alongside the existing fim/nscan/vuln branches and before the final `return None`: `anomaly_rule == "shadow_ai_detected"` AND a truthy `agent_id` (both read via the existing `_finding_attr()` accessor) returns `by_name.get("kill_process")`; anything else returns `None`.
- No new `ACTION_MAP` entry, no new YAML playbook file — the branch reuses the already-vendored `kill_process` playbook verbatim (RESEARCH Open Question 1).
- 4 new test cases added to `backend/tests/test_remediation_playbook.py`: shadow_ai+agent -> kill_process, shadow_ai+no-agent -> None, other-rule -> None, plus the pre-existing unknown-finding-type regression test confirming no change to fim/nscan/vuln behavior. `_Finding` test fixture extended with an `agent_id` constructor param.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the anomaly branch to select_playbook() (AUT-03)** - `c951d4d` (feat) — anomaly branch in `remediation_playbook_service.py` + 4 anomaly test cases in `test_remediation_playbook.py`.

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `backend/remediation_playbook_service.py` - new `finding_type == "anomaly"` branch in `select_playbook()`, reuses `_finding_attr` for both `details` and `agent_id`
- `backend/tests/test_remediation_playbook.py` - `_Finding` fixture gained `agent_id` param; 3 new anomaly-specific test functions added (the 4th behavior case — unknown finding_type -> None — was already covered by the pre-existing `test_select_playbook_unknown_finding_type_returns_none`)

## Decisions Made
- Scope deliberately narrowed to the single `shadow_ai_detected` anomaly rule (the one UEBA signal carrying a real `agent_id`) per RESEARCH Assumption A2 — the other 9 UEBA rule types resolve to `no_playbook` this phase; broader user/IP-scoped containment is an explicit follow-up requiring user confirmation (checkpoint:decision in Plan 55-03), not silently added here.
- Reused `kill_process.yaml` verbatim rather than authoring a near-duplicate `shadow_ai_kill.yaml` — same underlying agent action, no meaningful audit-trail loss.

## Deviations from Plan

None - plan executed exactly as written. No Rule 1-3 auto-fixes were required; the acceptance criteria (branch shape, `_finding_attr` reuse, unchanged `ACTION_MAP` count, 4 green tests) were achievable directly as specified.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AUT-03's mapping half is fully delivered: `select_playbook()` deterministically resolves `shadow_ai_detected` anomalies with a real `agent_id` to `kill_process`, and every other anomaly to `no_playbook`, proven by 4 green tests with zero new action types and zero LLM in the selection path.
- Plan 55-03 (predictive containment trigger) builds directly on this branch: it will wire the actual UEBA anomaly detection into a call to `autonomous_remediation_service.remediate()`, which calls `select_playbook()` unchanged — routing a detected shadow_ai anomaly through the existing `_dispatch_and_verify` approval/lease/audit machinery (D-04), never bypassing it.
- The checkpoint:decision confirming the Assumption A2 scope narrowing (only `shadow_ai_detected` reaches a dispatchable playbook) is deferred to Plan 55-03, before the trigger is wired — not resolved in this plan.

---
*Phase: 55-advanced-threat-detection*
*Completed: 2026-08-03*

## Self-Check: PASSED

- FOUND: backend/remediation_playbook_service.py
- FOUND: backend/tests/test_remediation_playbook.py
- FOUND commit: c951d4d
