---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 08
subsystem: autonomous-ops
tags: [gate, remediation, playbooks, approvals, structural-tests, llm-removal, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01, 81-11)
    provides: gate.decide / gate.execute, registry.playbook_raises, ledger, the complete GATE-03 order
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-03)
    provides: the scheduled autonomous_remediation_loop already removed
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-04)
    provides: approvals.approve / deny / register_dispatcher
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-05, 81-06)
    provides: delivery hold-back hooks, XDR fence and the grandfathered correlation writers
provides:
  - "AutonomousRemediationService.remediate decided by gate.decide (refuse, shadow, approval card, dispatch)"
  - "every playbook step, verify re-scan and compensation written by gate.execute (action, probe, compensate)"
  - "dispatch_approved_remediation registered as dispatcher remediation; approve/deny through the ledger"
  - "console approve/deny need control:autonomous_ops (D-24 (c)); GET /audit keeps manage:active_response"
  - "the legacy LLM remediation path deleted (GATE-05)"
  - "backend/tests/test_autonomous_ops_structural.py: stamp, queue-writer, LLM-import, legacy-symbol, hold-back and registry-only tests"
affects: [81-09, 81-10]

actuals:
  tokens: 24200
  tasks: 3
  commits: 3

plan_head_before: 595e465416fd4901770646d249c663dbfe6a7e69
plan_head_after: d9defb4c22381b08db2dcb7a5062738aed2e6948
commits: 3

tech-stack:
  added: []
  patterns:
    - "Service-level tenant_scope around remediate / approve / deny / dispatcher so wrapped-database calls carry the finding's tenant"
    - "Ledger transitions at the audit points are best-effort compare-and-set (a lost race with the reconciler is not an error)"
    - "Structural scanners (regex for collection writes, AST for stamp / imports / hook calls), each with a negative control"
    - "agent_that_completes: a stand-in agent patching the poll so real-database tests see completed instructions and scan verdicts"

key-files:
  created:
    - backend/tests/test_autonomous_ops_structural.py
  modified:
    - backend/autonomous_remediation_service.py
    - backend/remediation_control_endpoints.py
    - backend/autonomous_ops/messages.py
    - backend/tests/autonomy_support.py
    - backend/tests/test_autonomous_remediation_loop.py
    - backend/tests/test_remediation_guards.py
    - backend/tests/test_ueba_remediation_trigger.py

key-decisions:
  - "remediate() passes playbook_raise = registry.playbook_raises(steps) so the shipped block_ip playbook (destructive true, no gate_class) is decided by its registry class auto, while kill_process, disable_service, restore_file, rotate_key and patch_package get cards through their registry class approve"
  - "Approve and deny delegate to approvals through the ledger row named by autonomyActionId; a request without one is refused legacy_request; the dispatcher compare-and-sets remediation_requests pending_approval -> dispatching so a double click dispatches once"
  - "A deferral (host lease over cap) moves the row to refused (reason agent_busy), not failed, so it never counts toward the circuit breaker"
  - "A step the host never confirms moves the row to failed (dispatch_failed); a verify that still finds the problem moves executed -> failed, then rolled_back after the compensation steps; an unverified result leaves the row at executed"
  - "'script' is stripped from every rendered step parameter before it reaches the gate (PROH-81-01), whatever an operator-authored playbook contains"
  - "The structural scan reads tracked backend files only, so the user's untracked and deleted working-tree files cannot trip a rule meant for committed code"

requirements-completed: [GATE-03, GATE-04, GATE-05, GATE-07, GATE-10]

coverage:
  - id: D1
    description: "A UEBA shadow-AI anomaly at shipped defaults is one simulation row (origin ueba, dispatcher remediation, wouldHave needs_approval) with no instruction and no request; an unticked tenant leaves nothing recorded"
    requirement: GATE-03
    verification:
      - kind: integration
        ref: "backend/tests/test_ueba_remediation_trigger.py#TestGatedAtShippedDefaults"
        status: pass
    human_judgment: false
  - id: D2
    description: "GATE-04 locked split on the vendored path: block_ip dispatches without a card, kill_process pends approval; request rows carry autonomyActionId and the matching remediationId"
    requirement: GATE-04
    verification:
      - kind: integration
        ref: "backend/tests/test_ueba_remediation_trigger.py#TestGate04SplitOnTheVendoredPath"
        status: pass
    human_judgment: false
  - id: D3
    description: "Steps, probes and compensations are written by gate.execute with kinds action, probe, compensate; ledger rows reach executed, verified, failed and rolled_back; deferral is refused, not failed"
    requirement: GATE-07
    verification:
      - kind: integration
        ref: "backend/tests/test_remediation_guards.py#TestLedgerFollowsTheAuditPoints"
        status: pass
      - kind: unit
        ref: "backend/tests/test_remediation_guards.py#TestRollbackAndEscalation"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approve and deny go through the ledger: single dispatch on a double click (ledger CAS and request CAS), legacy requests refused, deny records the override audit, a stop freezes approval"
    requirement: GATE-10
    verification:
      - kind: integration
        ref: "backend/tests/test_remediation_guards.py#TestApprovalThroughTheLedger"
        status: pass
    human_judgment: false
  - id: D5
    description: "Console approve and deny refuse a caller without control:autonomous_ops; GET /audit still needs manage:active_response"
    requirement: GATE-10
    verification:
      - kind: unit
        ref: "backend/tests/test_remediation_guards.py#TestControlEndpoints"
        status: pass
    human_judgment: false
  - id: D6
    description: "The legacy LLM path (run_cycle, generate_plan, execute_plan, verify_remediation, _log_decision, _create_failure_ticket, _is_tenant_enabled, RemediationPlan) is gone and no autonomous-path module imports an LLM client"
    requirement: GATE-05
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_structural.py#test_legacy_symbols_are_gone"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_structural.py#test_no_llm_on_the_autonomous_path"
        status: pass
    human_judgment: false
  - id: D7
    description: "For every vendored playbook, approved or automatic, the agent queue only receives stamped registry commands without a script key"
    requirement: GATE-05
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_structural.py#test_only_registry_actions_reach_the_queue"
        status: pass
    human_judgment: false
  - id: D8
    description: "Only gate.py writes the autonomy stamp; new queue writers outside the committed grandfathered list fail the suite; every delivery path keeps its stop hook"
    requirement: GATE-03
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_structural.py (stamp, queue-writer and hold-back tests with negative controls)"
        status: pass
    human_judgment: false
  - id: D9
    description: "Live behaviour after a backend restart: a real shadow-AI detection producing one simulation entry, and a real approve click on the Native Security console"
    requirement: GATE-03
    human_judgment: true
    rationale: "Needs the user's backend restart and a real agent or console session; every test here uses throwaway databases and stand-in agents"

duration: 55min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 08: Remediation through the gate, LLM path deleted, structural locks Summary

**`remediate()`, every playbook step / probe / compensation and every approval now run only through the autonomy gate and the ledger (stamped registry commands, single-use cards, approve tier on the console); the legacy LLM remediation path is deleted; and a structural test module makes a second autonomous writer, an LLM import or a dropped stop hook fail the suite**

## Performance

- **Duration:** about 55 min of work (wall clock was longer: execution paused for a usage limit and the first attempt stopped after Task 1's code)
- **Started:** 2026-10-26T09:45:31Z
- **Completed:** 2026-10-26
- **Tasks:** 3 (1 tracer, 2 auto)
- **Files:** 1 created, 7 modified

## Accomplishments

- The one live automatic caller (`ueba_service._dispatch_anomaly_remediation`, unchanged) is gated: at shipped defaults a shadow-AI anomaly is one `shadow` row (wouldHave `needs_approval`, because kill_process is an approval action), no instruction, no request row; an unticked tenant gets nothing recorded.
- GATE-04 split holds on the vendored path: the shipped block_ip playbook (destructive true, no `gate_class`) is allowed automatically with `autoDispatched` True; kill_process, and the other approval-class playbooks, produce a card.
- Steps, verify re-scans and verify-failure compensation are written by `gate.execute` with kinds action, probe and compensate. The ledger row moves executed -> verified, or executed -> failed -> rolled_back after compensation; an irreversible failure escalates and the row stays failed.
- Approve/deny delegate to `approvals` through the linked ledger row. A second approve is `already_handled` and the dispatcher's request compare-and-set alone also stops a double dispatch. A stop freezes approval.
- Console approve and deny require `control:autonomous_ops` (JWT session dependency, so API keys never reach them); `GET /audit` keeps `manage:active_response`.
- Structural tests: stamp writer, grandfathered queue writers, LLM-import AST ban, legacy symbols, stop hook on all four delivery paths, and a per-playbook proof that only stamped registry commands without a script key reach the queue.

## Task Commits

1. **Task 1 (tracer): remediate() decided by the gate** - `f0eb8fcff` (feat)
2. **Task 2: steps/probes/compensations via gate.execute, approvals via the ledger, console permission, LLM path deleted** - `3163f9e94` (feat)
3. **Task 3: structural tests** - `d9defb4c2` (test)

**Plan metadata:** committed with this SUMMARY (docs).

Between the Task 1 and Task 2 commits `test_autonomous_remediation_loop.py` and `test_remediation_guards.py` were red (they still described the pre-gate behaviour); both were updated in the Task 2 commit and every commit after it is green.

## GRANDFATHERED_WRITERS (committed literal, 34 modules)

Computed with `git ls-files backend` plus the scanner in the test (the plan estimated about 27; the real count of tracked modules writing `agent_instructions`, `instructions` or `response_tasks` is 34, excluding `autonomous_ops/gate.py`). `autonomous_remediation_service.py` is not in it.

```
agent_auto_update_service.py, agent_capabilities.py, agent_chat_endpoints.py, agent_download_endpoints.py,
agent_instruction_endpoints.py, agent_logic_service.py, agent_tasks_endpoints.py, agentic_service.py,
chaos_engineering_service.py, compliance_auto_evidence_service.py, compliance_automation_api.py,
compliance_remediation_service.py, compliance_scans_endpoints.py, correlation_engine_threat.py,
database_migrations.py, deployment_result_endpoints.py, deployment_service.py, dr_endpoints.py,
native_security_ops_endpoints.py, patch_core_endpoints.py, patch_software_endpoints.py,
persistence_endpoints.py, playbook_engine_actions.py, remote_endpoints.py, response_endpoints.py,
response_orchestrator.py, scheduler.py, simulation_endpoints.py, skill_handlers.py, soar_engine.py,
software_endpoints.py, swarm_endpoints.py, swarm_service.py, tasks.py
```

Allowed separately: `autonomous_ops/gate.py` (writer), `delivery.py` and `stop.py` (status changes on stamped items). Stamp readers allowed to name the stamp: `autonomous_ops/stop.py` and `migrations/024_autonomous_ops.py` (neither inserts into a queue; the test checks that). `correlation_engine_threat.py` (threat hunt and kill-chain pre-staging) is the documented XDR grandfathered writer. The test also fails if a listed module stops writing, so the literal cannot rot.

## Legacy tests changed

| File | Change | Reason |
|---|---|---|
| `test_ueba_remediation_trigger.py` | `test_max_risk_score_anomaly_still_pends_approval` rewritten under `permissive_gate("needs_approval")` (same intent: no severity bypass, request pending, nothing dispatched); added real-database classes for shipped defaults, unticked tenant, no-host refusal and the GATE-04 split | the gate now decides; kill_process is pending because its registry class is approve |
| `test_autonomous_remediation_loop.py` | dispatch / audit / verify tests run under `permissive_gate("allow_auto")` with stamp and ledger-state assertions; `test_remediate_dry_run_does_not_dispatch` now expects status `shadow` plus the ledger id (A-81-SHADOW-STATUS); added refusal, removed-symbol and dispatcher-registered tests | gate in front of remediate; dry_run is now shadow |
| `test_remediation_guards.py` | approval, rollback, cap and lease tests adapted (ledger rows, `action_id`, kinds); mocked `test_approve_resumes_dispatch` and `test_deny_cancels_and_records_override` replaced by real-database equivalents in `TestApprovalThroughTheLedger`; endpoint tests assert the approve tier and the 403s | approve/deny now go through the ledger, which needs real compare-and-set semantics to mean anything |
| `autonomy_support.py` | added `agent_that_completes` (a stand-in agent) | allowed for 81-08 by the module's own note |

No test was deleted. No test of a deleted symbol existed in these files (the old code was never unit-tested directly); the deleted symbols are asserted absent.

`autonomous_remediation_service.py` line count: 1047 before the plan, 1113 after Task 1, 871 after Task 2.

## Decisions Made

See `key-decisions`. Two worth repeating for 81-09 and 81-10: the Activity feed will see remediation rows with `dispatcher: remediation` and `remediationId`; and the remediation dispatcher is registered when `autonomous_remediation_service` is imported (the console router imports it at startup), so a generic ledger approve route in 81-09 reaches it as long as that module has been imported by the app, which it is.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical] Tenant scope around the service entry points**
- **Found during:** Task 1
- **Issue:** `remediate()` is called from a background task with no guaranteed ambient tenant; the tenant-isolating wrapper would stamp `ORPHANED_DATA_NO_TENANT_CONTEXT` on the `remediation_requests` row, hiding the card from the console queue.
- **Fix:** `remediate`, `approve_remediation`, `deny_remediation` and the dispatcher run inside `scope.tenant_scope(finding tenant)`; the instruction poll reads the raw handle with an explicit tenantId.
- **Files modified:** `backend/autonomous_remediation_service.py`
- **Committed in:** `f0eb8fcff`, `3163f9e94`

**2. [Rule 2 - Critical] `script` stripped from rendered step parameters**
- **Found during:** Task 2
- **Issue:** the old payload always carried a `script` key; an operator-authored playbook step could still carry one. PROH-81-01 forbids a script reaching an agent from the autonomous path.
- **Fix:** `_safe_params` drops `script` before the gate sees the parameters; a structural test proves it.
- **Committed in:** `f0eb8fcff`, `3163f9e94`, `d9defb4c2`

**3. [Rule 3 - Blocking] Two reason texts added to `messages.py`**
- **Found during:** Task 2
- **Issue:** a deferred remediation (`agent_busy`) and a failed verification (`verify_failed`) needed plain-words reason codes on their ledger rows; no existing code fit.
- **Fix:** two entries added to `REASON_TEXT` (no banned term; the 81-11 coverage test still passes).
- **Files modified:** `backend/autonomous_ops/messages.py`
- **Committed in:** `3163f9e94`

**4. [Process] Tests were not all written before the code for Task 2**
Task 1 followed red then green. For Task 2 the code was written first and the legacy tests then updated; the legacy suites were already red against the new code (they failed against the Task 1 behaviour), and the new real-database approval tests were not run red separately.

**Total deviations:** 3 auto-fixed (2 missing critical, 1 blocking), 1 process note.
**Impact on plan:** none on scope; the first two are safety requirements, the third is two dictionary entries.

## Issues Encountered

- A multi-step playbook could in theory lose its `dispatching` state to the 81-04 reconciler between steps (it moves a row to executed once an instruction succeeds), in which case the next action step is refused `not_dispatchable` and the remediation reports unverified. All six vendored playbooks have one step, and the reconciler tick is 60 s; a future multi-step playbook should be reviewed against this.
- Plan-level verification: the five plan test modules plus approvals pass (107), and `-k "remediation or ueba or native_security"` passes (118). A wider run (`-k "autonomous_ops or catalogue or rbac or permission or monitor_agent"`) gives 726 passed and 3 failed, none caused here: `test_catalogue_manifest.py::test_structure_rules_hold_on_the_real_manifest` and `::test_sidebar_and_app_agree_with_manifest` are the known reds, and `test_catalogue_route_parity.py::test_ledger_ratchets` complains about nine modules this plan never touched (audit_program_endpoints, compliance_*, export_report_endpoint, reporting_endpoints, route_aliases, scheduled_reports_endpoints, soa_endpoints). The last one is reported, not fixed (out of scope).

## Known Stubs

None. No placeholder values, empty data sources or TODO text were added.

## Threat Flags

None beyond the plan's threat model. The new surface is the same routes with a stricter permission (T-81-34); T-81-31 (legacy LLM path), T-81-32 (second writer) and T-81-33 (double click) are mitigated and tested.

## User Setup Required

None for the code. These need the user and were not done: restarting the backend (the running service still uses the old remediation code until then), and watching the first real shadow-AI detection and a real console approval after the restart. Nothing was deployed, no service restarted, no live database touched; every database test used a throwaway `omni_test_*` database and no LLM or Ollama call was made.

## Next Phase Readiness

- 81-09 can build the Activity routes on rows that now include remediation-origin rows (`dispatcher: remediation`, `remediationId`, `origin` ueba or remediation).
- Not recorded in `WINDOWS.md`; there are no defects to log. Pre-existing red tests listed above are unchanged.

## Self-Check: PASSED

All files exist (`backend/tests/test_autonomous_ops_structural.py` and the seven modified files); commits `f0eb8fcff`, `3163f9e94`, `d9defb4c2` are ancestors of HEAD; the removed-symbol acceptance command prints ok; `grep -c "gate.decide("` is 1, `"gate.execute("` is 2, `control:autonomous_ops` and `manage:active_response` each appear in the endpoint module; `git diff --quiet -- backend/ueba_service.py` exits 0; the structural module has 21 tests and 4 negative-control tests, all passing.

---
*Phase: 81-autonomy-gate-stop-switch-activity-ledger*
*Completed: 2026-10-26*
