---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 17
subsystem: autonomous-ops
tags: [shadow-mode, fail-closed, structural-test, gap-closure, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-15)
    provides: dispatch binding; its tests patch the env var and the module constant with create=True
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-16)
    provides: tenant-scoped playbooks and truthful undo
provides:
  - "settings.master_shadow(): shadow off only for 0/false/no/off (stripped, any case); everything else keeps shadow on"
  - "autonomous_remediation_service holds no import-time copy of the master; _remediate calls gate.decide(db, request)"
  - "test_autonomous_ops_structural._parse / stamp_writers / unparsable-file controls"
affects: [81-18]

actuals:
  tokens: 28000
  tasks: 3
  commits: 3

plan_head_before: fe30182b6b74d877edba5ece04e2f3180b0d46b6
plan_head_after: 5211d6fa302a2b692b940e2ad50ab17d74269d64
commits: 3

tech-stack:
  added: []
  patterns:
    - "One live reader for a deployment switch: settings.master_shadow(), read per decision"
    - "Structural scanners never skip a file they cannot parse: textual fallback, and a hard failure on the autonomous path"

key-files:
  created: []
  modified:
    - backend/autonomous_ops/settings.py
    - backend/autonomous_remediation_service.py
    - backend/tests/test_autonomous_ops_gate.py
    - backend/tests/test_ueba_remediation_trigger.py
    - backend/tests/test_remediation_guards.py
    - backend/tests/test_autonomous_remediation_loop.py
    - backend/tests/test_autonomous_ops_structural.py

key-decisions:
  - "A deployment-wide switch fails closed: only an explicit off word turns shadow off, so a typo can never make a deployment live (D-02, PROH-81-23)."
  - "The remediation service no longer reads AUTONOMOUS_REMEDIATION_DRY_RUN at all; the gate is the single reader, so the remediation path and the XDR fence agree and an operator change applies without a restart of the module."
  - "Unparsable tracked sources are matched with a textual regex for the stamp instead of being skipped; banned_imports returns ['<unparsable>'] so the autonomous-path checks fail loudly."

requirements-completed: [GATE-09, GATE-03]

duration: 35min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 17: Fail-closed shadow master and parse-robust stamp scan Summary

**An unrecognised AUTONOMOUS_REMEDIATION_DRY_RUN value now keeps shadow mode on, the remediation service reads the master live through the gate, and the GATE-03 stamp scan no longer crashes on an unparsable tracked file.**

## Accomplishments

- Task 1 (tracer): `settings.master_shadow()` is off only when the stripped, lower-cased value is one of `0`, `false`, `no`, `off`. A 17-value parametrized test (unset, empty, true/TRUE/"true ", 1, yes, on, y, enabled, garbage -> on; false, " FALSE ", 0, no, off, Off -> off) and an end-to-end test on real throwaway Mongo: with `enabled` and the tenant's own flag off, `gate.decide` (no override) records a shadow row whose trace holds `shadow / shadow / deployment` and writes no instruction; with `false` the same request is dispatching.
- Task 2: the module constant and its import-time read are deleted from `autonomous_remediation_service.py`; `_remediate` calls `gate.decide(db, request)` with no override keyword. AST test: no call in the service passes a `master_shadow` keyword and none reads the variable name via getenv/get. Live-read test (real Mongo): with `false` the block_ip finding is dispatched and verified (`resolved`, step SUCCESS); flipping to `true` in the same process makes the next finding a `shadow` row.
- Task 3: `_parse(src)` returns None on SyntaxError/ValueError. `names_the_autonomy_stamp` falls back to a textual regex for an unparsable source; `banned_imports` returns `["<unparsable>"]`; `calls_in_function` returns False. `stamp_writers(sources)` and `autonomous_path_unparsable(sources)` added; `test_only_the_gate_writes_the_autonomy_stamp` now uses them and asserts nothing on the autonomous path is unparsable. Negative controls use synthetic dicts only (no files written).

## Task Commits

1. Task 1 (tracer): `23d4661af` fix(81-17): an unrecognised shadow master value keeps shadow on
2. Task 2: `c12fdf34a` fix(81-17): the remediation path reads the shadow master live through the gate
3. Task 3: `5211d6fa3` fix(81-17): the stamp scan survives an unparsable tracked file without weakening the rule

## Test cases moved from the module patch to the environment variable (21)

- test_ueba_remediation_trigger.py: 8 patches (5 `false`, 3 `true`; intent unchanged)
- test_remediation_guards.py: 6 patches (`false`)
- test_autonomous_remediation_loop.py: 6 patches (5 `false`, 1 `true`)
- test_autonomous_ops_structural.py: the `live` fixture (`false`)

The constant moved from the kept-symbol lists to removed-symbol assertions in `test_autonomous_remediation_loop.TestLegacyLlmPathIsGone` and `test_autonomous_ops_structural.test_legacy_symbols_are_gone`. test_autonomous_ops_dispatch_binding.py and test_autonomous_ops_remediation_truth.py were not edited and still pass (their `create=True` patches are harmless).

## Clean-checkout proof (Task 3)

`git worktree add --detach <scratchpad>/wt17/head HEAD` (HEAD 5211d6fa3, which includes every tracked file under backend/backend/ that the user has deleted locally), then in that checkout:

- `pytest backend/tests/test_autonomous_ops_structural.py -k stamp`: 2 passed (no SyntaxError).
- Whole module: 26 passed.
- The worktree was removed afterwards (`git worktree list` shows only the main tree). A direct `ast.parse` over that checkout's backend/backend files confirmed an unparsable tracked file exists there (invalid character U+2014).

## Verification

- Task 1 command (gate, endpoints, xdr_fence): 59 passed, 0 skipped.
- Task 2 command (6 modules): 132 passed, 0 skipped (after the live-read assertion was set to `resolved`).
- `backend/tests/test_autonomous_ops_*.py`: 420 passed, 0 failed, 0 skipped.
- `backend/tests -k "remediation or ueba or rotate_key or playbook or xdr"`: 171 passed, 0 failed.
- UI regression (autonomousOpsCopy, AutonomousOpsActivity, AutonomousOpsStatusCard): 72 passed (UI untouched).
- Acceptance greps: `"0", "false", "no", "off"` in settings.py 1; `gate.decide(db, request)` in the service 1; no patch of `autonomous_remediation_service.AUTONOMOUS_REMEDIATION_DRY_RUN"` left in the four legacy modules; `def _parse` 1; `def stamp_writers` 1.

## Nothing under backend/backend/ was touched

`git diff --cached --name-only -- backend/backend` printed nothing before each commit, and `git show --stat --format= HEAD -- backend/backend` is empty for all three commits. The user's deletions stay unstaged.

## Deviations from Plan

**1. [Test expectation] Live-read first status is `resolved`, not `dispatching`.**
- **Found during:** Task 2
- **Issue:** `remediate()` under `agent_that_completes` returns `resolved` with `steps_dispatched` (dispatch plus verification) rather than the literal word `dispatching` the plan sketched.
- **Fix:** the test asserts `status == "resolved"` and a non-empty `steps_dispatched`, which still proves a live dispatch before the flip.
- **Commit:** c12fdf34a

**2. [Convention] `test_autonomous_ops_structural.py` is now 535 lines** (450 at HEAD), over the 500-line guideline. The plan puts all of this module's new tests there; splitting the file was out of scope. Noted for a later tidy-up.

## Known Stubs

None.

## Threat Flags

None. T-81-62, T-81-63 and T-81-64 are mitigated and covered by tests.

## Notes for the user

- Live value to confirm at deploy: with this change a value such as `enabled` or `True ` no longer matters (shadow stays on), but any deployment that relied on an odd spelling to mean "off" must now set `false`, `0`, `no` or `off`. The backend runs from this checkout without reload, so the change takes effect at the next backend restart (not done here).
- Requirements GATE-09 and GATE-03 marked complete; 81-18 lists neither.

## Self-Check: PASSED

- Files present: backend/autonomous_ops/settings.py, backend/autonomous_remediation_service.py, backend/tests/test_autonomous_ops_structural.py (`def _parse`, `def stamp_writers`).
- Commits 23d4661af, c12fdf34a, 5211d6fa3 are in HEAD history.
