---
phase: 81-autonomy-gate-stop-switch-activity-ledger
verified: 2026-10-26T14:50:00Z
status: gaps_found
score: 4/6 must-haves verified
covered_files:
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-01-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-01-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-02-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-02-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-03-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-03-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-04-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-04-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-05-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-05-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-06-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-06-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-07-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-07-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-08-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-08-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-09-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-09-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-10-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-10-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-11-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-11-SUMMARY.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-12-PLAN.md
  - .planning/phases/81-autonomy-gate-stop-switch-activity-ledger/81-12-SUMMARY.md
  - backend/autonomous_ops/gate.py
  - backend/autonomous_ops/reconciler.py
  - backend/autonomous_ops/settings.py
  - backend/autonomous_remediation_service.py
  - backend/playbook_engine_actions.py
  - backend/remediation_playbook_service.py
covered_digest: "v3:sha256:c5f4224ed4dbd2628198f6e8851bb4e07b2f21a5d906fbe7c9ff8a373612532e"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The platform host, its own IP addresses and the management network can never be blocked, isolated or patched automatically; every action the engine dispatches was decided by the gate (SC2, GATE-03, GATE-08, GATE-10)"
    status: failed
    reason: >
      gate.decide evaluates ONE request built from steps[0] only (autonomous_remediation_service._remediate
      builds first_params from steps[0]; gate._step_protected_targets runs the never-touch IP check on that
      single params dict; _step_class validates only specs[0].cls). _dispatch_and_verify then runs EVERY step
      and every rollback step through gate.execute, which checks only the ledger row state and the stop, not
      that command/agent/params match what was decided and not the never-touch list. Verified by reading
      HEAD:backend/autonomous_ops/gate.py:205-233, :453-472 and HEAD:backend/autonomous_remediation_service.py
      (request build at _remediate, per-step dispatch in _dispatch_step). A playbook [kill_process, block_ip
      <protected ip>] passes the gate and the second step is dispatched unchecked; the approval card shows only
      step 1. AGGRAVATING (found in this verification, not in 81-REVIEW.md): remediation_playbook_service.load_playbooks
      returns every tenant's playbooks and select_playbook builds by_name last-wins with no tenantId filter.
      Reproduced read-only: with a tenant-A operator playbook named kill_process added to the defaults,
      select_playbook returns tenant A's two-step playbook for a tenant-B shadow_ai_detected anomaly. So one
      tenant's operator-authored steps can be dispatched to another tenant's agent, unchecked past step 1.
      Mitigations that hold today: the six vendored playbooks are single-step; the only live caller of remediate()
      is ueba_service (kill_process, approval class, so a person clicks); shadow mode is on by default. The hole
      becomes automatic once Phase 83 wires an automatic block_ip sweep. Orchestrator independently confirmed CR-01.
    artifacts:
      - path: "backend/autonomous_remediation_service.py"
        issue: "ActionRequest params are steps[0] only; _dispatch_step/rollback dispatch later steps with params the gate never saw"
      - path: "backend/autonomous_ops/gate.py"
        issue: "execute() does not bind command/agent_id/params to the decided row, does not re-check registry or never-touch; _step_class only validates specs[0]"
      - path: "backend/remediation_playbook_service.py"
        issue: "load_playbooks/select_playbook are not tenant-scoped; another tenant's same-named playbook is selected"
    missing:
      - "Bind gate.execute to the decided row: refuse unless registry.resolve(command) is set, agent_id is in row.targets, and every ip_params value passes protected.check (or record per-step params and have decide() evaluate every step and rollback step)"
      - "Validate class/registry for every spec (not only specs[0]) and for rollback actions before the row is created, or restrict remediation to single-step playbooks"
      - "Scope load_playbooks/select_playbook to vendored + the finding's own tenantId"
      - "Add a regression test: a two-step playbook whose second step targets a never-touch IP is refused; a tenant-A playbook is never selected for a tenant-B finding"
  - truth: "Each Activity row's state is truthful: 'Undone' means the action was put back (SC5, ACTV-01, GATE-07, GATE-14)"
    status: failed
    reason: >
      autonomous_remediation_service._dispatch_and_verify (rollback branch) dispatches each rollback step but never
      inspects the returned status, then unconditionally moves the ledger row failed -> rolled_back and returns
      rollback_dispatched True. _dispatch_step returns status refused / FAILURE / TIMEOUT when the compensation
      did not happen. views.STATE_RESULT renders rolled_back as "Undone." and the Activity bucket is "undone", and
      the circuit breaker counts it as a clean undo. A block that was never lifted is shown to the operator as
      put back, and the audit chain mirrors the false state. Orchestrator independently confirmed CR-02.
    artifacts:
      - path: "backend/autonomous_remediation_service.py"
        issue: "rolled_back set regardless of rollback step results (~lines 683-692 of the pre-edit module)"
    missing:
      - "Set rolled_back only when every rollback step returned SUCCESS; otherwise fail the row with a rollback_incomplete reason (add it to messages.REASON_TEXT) and raise the human-review alert the no-rollback branch raises"
      - "Test: a rollback step that times out or is refused leaves the row failed, not undone"
deferred: []
human_verification:
  - test: "Apply migration 024 and restart the backend (operator step; nothing was applied live)"
    expected: "Every tenant has an autonomy_settings document (Platform tenant Off, others Undoable-auto with shadow on); platform stop and reconciler start without error"
    why_human: "Live database and service restart are the user's; verification was read-only against throwaway omni_test_* databases"
  - test: "Flip the platform stop on the live server while an automatic instruction is queued, then poll as a real agent"
    expected: "The poll withholds the instruction (it becomes cancelled_by_stop), no restart needed; pending approvals stay frozen; undo still works"
    why_human: "Needs a real agent poll against the live server"
  - test: "Watch the live agent status refresh"
    expected: "An agent silent for more than 5 minutes flips to Offline within about 30 s, and the notification names only agents that actually went offline"
    why_human: "Live cadence; also see WR-06 race"
  - test: "Open the Autonomous Ops screen in a published UI build as a tenant admin (screen ticked) and as Super Admin"
    expected: "Six states and a labelled Simulation chip render; Stop/Resume dialogs and the app-wide stop banner appear; tenant sees 'Platform administrator' for a platform stop"
    why_human: "UI publish is the user's; visual quality (81-UI-REVIEW scored 19/24)"
  - test: "Decide whether the documented XDR-GRANDFATHERED writers are acceptable under the phase goal wording 'every automatic action in the platform'"
    expected: "Either accept (monitoring/hunt/snapshot/auto-update verbs stay outside gate and stop; fenced later) or require them to be gated before switch-on"
    why_human: "Scope decision. Automatic writers still outside the gate and not held back by a stop: correlation_engine_threat.trigger_threat_hunt and prestage_kill_chain_defenses (run_threat_hunt, create_vss_snapshot, run_vss_rollback_check, enable_*_monitoring), agent_auto_update_service (agent_update pushed on heartbeat), agent_logic_service, plus swarm/SOAR (Phase 83 SC5). Flagged by 81-06 as A-81-XDR-GRANDFATHERED and accepted via D-21; the structural test is an allow-list, not proof that no other autonomous writer exists"
---

# Phase 81: Autonomy Gate, Stop Switch & Activity Ledger - Verification Report

**Phase Goal:** Every automatic action in the platform passes one code-owned decision gate that an operator can stop instantly, that records and audits each decision before anything is dispatched, and whose results appear on a new Autonomous Ops screen, with the legacy LLM-driven remediation path removed, so the engine is safe to switch on.
**Verified:** 2026-10-26T14:50:00Z
**Status:** gaps_found
**Re-verification:** No, initial verification

Deliverable examined = commits on branch `npx` since `6e7664746` (read via `git show HEAD:<file>`); the user's uncommitted working-tree edits were neither credited nor blamed.

## Goal Achievement

### Observable Truths (ROADMAP success criteria + derived)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: explicit stored level per tenant (migration + new-tenant default), unticked tenant Off, unreadable = Suggest, Super Admin max level, separate permissions | VERIFIED | `settings.py` load/effective_level (eligible only if `view:autonomous_ops` literally in enabledFeatures; `readable` False -> suggest); `ensure_tenant` ($setOnInsert, Platform tenant Off); migration 024 calls it per tenant; `tenant_endpoints` calls it on create + `app_startup` backstop; permissions split `manage:` (level, resume) / `control:` (stop, approve, deny, undo) / `control:platform_` (platform stop, max level); 330 backend tests pass incl. permissions, migration |
| 2 | SC2: one ordered decision function; structural test; classes; protected targets never touched; per-decision host cap | FAILED | Ordered `_STEPS` and registry classes confirmed (gate.py:315); structural stamp test passes. But "can never" is false for multi-step playbooks: CR-01 above (only steps[0] params checked; later/rollback steps unchecked at execute; cross-tenant playbook selection reproduced). Also see grandfathered-writers item in human verification |
| 3 | SC3: legacy LLM path + 0.90 bypass gone, registry-only test, shadow default, stop without restart, hold-back at poll, breaker | VERIFIED (with warnings) | `run_cycle/generate_plan/execute_plan` and `autonomous_remediation_loop` absent from HEAD (git grep clean; `test_legacy_symbols_are_gone` passes); `AUTO_APPROVE_CONFIDENCE_THRESHOLD` removed, `auto_approved` ignored in `backend_safety.evaluate_action`; `test_only_registry_actions_reach_the_queue` x6 pass; master shadow default true (`settings.master_shadow`); stop read uncached each call (`settings.platform_stop`, fail closed); `delivery.hold_back_*` called in all 3 instruction polls + response queue (structural test parametrized x4, and read: hold-back runs before the `sent` update in agent_tasks_endpoints); breaker.py + 15 tests. Warnings: WR-03 (unrecognised env value turns shadow OFF; remediation service reads it once at import), WR-02 (manual level set silently disables a tripped breaker) |
| 4 | SC4: write-ahead intent record, audit mirror, retention, exactly-once approval, expiry = denied, single sweeper, two-tenant isolation, 5-min status | VERIFIED (with warnings) | `ledger.create_intent` inserts before dispatch, `LedgerUnavailable` -> `ledger_unavailable` refusal; every `transition` mirrored via `audit_ledger.event`; collections outside every retention path (`PROTECTED_COLLECTIONS`, test); `approvals.approve` is one CAS with expiry in the filter, loser gets `already_handled`; `expire_due` runs through stops; reconciler under `lock_with_renewal`; isolation tests (7) pass; `monitor_agent_status` polls 30 s with 5-min offline threshold and names only flipped agents. Warnings: WR-01 (rows stuck in dispatching when instruction is `sent`/`delivered` but never reports), WR-06 (read-then-write race can flip a just-seen agent Offline), WR-08 (no cooldown after an `executed` automatic row), WR-07 (UEBA finding id has a timestamp so gate dedupe never matches) |
| 5 | SC5: Autonomous Ops screen opens from the catalogue with six states, what/why/target/result, Simulation labelled, copy check fails the build | VERIFIED | `catalogue-access.json` entry + `App.tsx` route + lazy `AutonomousOpsActivity`; routers mounted in `router_registry` with catalogue guard; Simulation chip and `simulation_result()` wording; banned-terms JSON read by both a pytest and a vitest copy check (19 + frontend tests pass); vitest 6 files / 139 tests pass. Caveat: the "Undone" label can be false (Gap 2) |
| 6 | Derived: each ledger state truthfully describes what happened (Undone = put back) | FAILED | CR-02 above |

**Score:** 4/6 truths verified (SC1, SC3, SC4, SC5); SC2 and the derived truthfulness truth FAILED. 0 behavior-unverified (every behavior-dependent truth has a passing behavioral test against throwaway Mongo).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/autonomous_ops/` (14 modules, 2,500+ lines) | gate, ledger, settings, stop, approvals, breaker, reconciler, delivery, protected, registry, messages, views | VERIFIED | Substantive, wired (routers, startup reconciler task, delivery hooks). Gate gaps per CR-01 |
| `backend/autonomous_ops_endpoints.py`, `autonomous_ops_platform_endpoints.py` | tenant and platform APIs with permission matrix | VERIFIED | Mounted in `router_registry.py:340-341`; per-route permission deps; interactive session required for writes |
| `backend/migrations/024_autonomous_ops.py` | stored level for every tenant, indexes | VERIFIED (not applied live) | Idempotent; live apply is a human step |
| `backend/autonomous_remediation_service.py` | gate-routed remediation, legacy deleted | STUB-free but defective | Legacy gone; CR-01, CR-02 live here; `scan_for_remediable_findings` (~250 lines) is dead code (IN-01) |
| `backend/playbook_engine_actions.py`, `correlation_engine_threat.py` | XDR fence, suggest-only selectors | VERIFIED | 20 xdr_fence tests pass; only 4 containment verbs fenced |
| `components/AutonomousOps*.tsx`, `contexts/AutonomousOpsStatusContext.tsx`, `services/autonomousOpsApi.ts` | read-only screen, status card, stop UI | VERIFIED | Wired in App.tsx; real API calls |
| `shared/autonomous-ops-banned-terms.json` + copy tests | ACTV-08 | VERIFIED | Python and TS checks both pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `remediate()` | `gate.decide` | `_remediate` ActionRequest | WIRED (partial) | Single request from steps[0] (CR-01) |
| `_dispatch_step` | `gate.execute` | command/params per step | WIRED but unbound | execute does not verify command/agent/params against the decided row |
| agent poll (3 endpoints + response queue) | `delivery.hold_back_*` | direct call before `sent` | WIRED | Structural test pins all four |
| approve route | `approvals.approve` | CAS + dispatcher registry | WIRED | `remediation` dispatcher registered at import of the service |
| `ledger.transition` | `audit_ledger.event` | `_mirror` | WIRED | Best-effort (never raises); row insert is the guard |
| startup | reconciler loop / `ensure_all_tenants` | `app_startup.py` | WIRED | |
| XDR auto playbook | `gate.decide` / `execute_response_task` | `_fence_automatic_step` | WIRED for 4 verbs | Other automatic writers grandfathered |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real Data | Status |
|----------|------|--------|-----------|--------|
| Activity list | rows/buckets | `views.list_page` over `autonomy_actions` (raw, tenant-filtered) | Yes | FLOWING |
| Status card / banner | stop, level, shadow, breaker | `/api/autonomous-ops/status` -> `settings.load` + `platform_stop` | Yes | FLOWING |
| Result column | `STATE_RESULT` | ledger state | Yes, but `rolled_back` can be asserted without compensation | FLOWING (content wrong in CR-02 case) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend phase suite on real throwaway Mongo | `pytest backend/tests/test_autonomous_ops_*.py -q -p no:cacheprovider -rs` | 330 passed, 0 skipped, 188 s | PASS |
| Frontend Autonomous Ops tests | `npx vitest run src/__tests__/AutonomousOps* autonomousOpsCopy catalogueAccess` | 6 files, 139 tests passed | PASS |
| Cross-tenant playbook selection | read-only `select_playbook` with a tenant-A `kill_process` added | returns tenant A's two-step playbook for a tenant-B finding | FAIL (confirms Gap 1 aggravation) |
| Reported by orchestrator, not re-run | build OK; vitest 613/613; 444 mapped backend tests; cargo 21/21 | green except known non-phase failures | accepted |

No existing test covers a multi-step playbook with a protected second step or a failing rollback, which is why 330 tests pass over both defects.

### Probe Execution

Step 7c: SKIPPED (no probe scripts declared by the phase plans).

### Requirements Coverage

All 17 IDs appear across the 12 PLAN frontmatters and in REQUIREMENTS.md (all marked Complete); none orphaned.

| Requirement | Source Plan(s) | Status | Evidence |
|-------------|----------------|--------|----------|
| GATE-01 | 81-12 | SATISFIED | migration 024, `ensure_tenant`, tenant create hook, startup backstop |
| GATE-02 | 81-01, 81-11 | SATISFIED | eligibility + fail-closed Suggest in settings/gate |
| GATE-03 | 81-01, 81-06, 81-08, 81-11 | PARTIAL | ordered gate and stamp-structural test hold; multi-step dispatch not gated per step (Gap 1); grandfathered writers outside the gate (human decision) |
| GATE-04 | 81-01, 81-08, 81-11 | SATISFIED for step 1; later steps not class-checked (CR-01) | registry raise-only pinned on vendored playbooks |
| GATE-05 | 81-03, 81-06, 81-08 | SATISFIED | legacy path and 0.90 bypass removed; registry-only tests |
| GATE-06 | 81-04, 81-05, 81-09, 81-10 | SATISFIED in tests; live proof pending | stop + hold-back + freeze; live poll is a human step |
| GATE-07 | 81-01, 81-08 | SATISFIED for write-ahead and mirror; state truthfulness defect (Gap 2) | |
| GATE-08 | 81-09, 81-11 | BLOCKED for multi-step/cross-tenant playbook path | Gap 1 |
| GATE-09 | 81-01, 81-09, 81-11 | SATISFIED (WR-03 hardening gap) | shadow default on |
| GATE-10 | 81-04, 81-08 | SATISFIED | single CAS; expiry = denied. (Approved card shows only step 1 of a multi-step playbook, Gap 1) |
| GATE-11 | 81-03, 81-04 | SATISFIED | lock_with_renewal, explicit tenantId, isolation tests |
| GATE-12 | 81-03 | SATISFIED (WR-06 race) | 30 s poll, 5-min threshold, pinned by test_monitor_agent_status |
| GATE-13 | 81-02, 81-09 | SATISFIED | four permission strings, max level enforced in `set_level` |
| GATE-14 | 81-04 | SATISFIED (WR-02) | breaker; counts false "rolled_back" as clean undo (Gap 2) |
| ACTV-01 | 81-02, 81-07, 81-09, 81-10 | SATISFIED; "Undone" can be false (Gap 2) | |
| ACTV-03 | 81-07 | SATISFIED | Simulation chip, labelled wording |
| ACTV-08 | 81-10 | SATISFIED | shared JSON + pytest + vitest |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `backend/autonomous_remediation_service.py` | gate decided on steps[0]; rolled_back unconditional | BLOCKER | Gaps 1 and 2 |
| `backend/remediation_playbook_service.py` | untenanted `load_playbooks`/`by_name` | BLOCKER (part of Gap 1) | cross-tenant playbook selection |
| `backend/autonomous_ops/settings.py:100-103`, service line 28 | shadow master parsed fail-open, read once at import | WARNING | WR-03 |
| `backend/autonomous_ops/reconciler.py:37-41,89-105` | `sent`/`delivered` never reconciled | WARNING | WR-01 |
| `backend/autonomous_ops/settings.py:159-171` | set_level ignores tripped breaker | WARNING | WR-02 |
| `backend/app_background_tasks.py:38-51` | read-then-write offline race | WARNING | WR-06 |
| `backend/autonomous_remediation_service.py:448` / `ueba_service.py` | timestamped finding id defeats dedupe | WARNING | WR-07 |
| `backend/playbook_engine_actions.py` fenced path | no cooldown after executed | WARNING | WR-08 |
| `views.visible_entries`, `remediation_control_endpoints` deny | platform never-touch entries visible to tenants; unbounded deny reason | WARNING | WR-04, WR-09 |
| `backend/tests/_mongo_test_db.py` | core safety suite skips silently without Mongo | WARNING | IN-04 |
| `autonomous_remediation_service.scan_for_remediable_findings` | ~250 dead lines | INFO | IN-01 |

No unreferenced TBD/FIXME/XXX debt markers were found in the phase's changed files.

### Human Verification Required

See `human_verification` in the frontmatter: migration 024 apply and restart, live platform-stop hold-back, live status cadence, published UI check, and the scope decision on grandfathered automatic writers.

### Gaps Summary

The scaffold is real and the large majority of the phase is genuinely delivered and tested: a stored per-tenant level with fail-closed eligibility, an ordered gate with a write-ahead ledger mirrored to the audit chain, a stop switch that is read uncached and held back at every agent delivery path, a single-use approval with expiry, a circuit breaker, a one-at-a-time reconciler, removal of the LLM path and the 0.90 bypass, and a read-only Autonomous Ops screen with banned-term checks. 330 backend and 139 frontend tests pass with no skips.

The goal also says "safe to switch on", and two defects in the seam between the gate and the remediation service falsify that:

1. **The gate does not check what is dispatched (CR-01).** It decides on step 1 only; later steps and rollback steps reach the agent queue through `gate.execute`, which re-checks neither the registry, the target, nor the never-touch list. I additionally reproduced that playbook selection is not tenant-scoped, so one tenant's operator-authored playbook can be selected for another tenant's finding. Today this is contained by single-step vendored playbooks, approval-class `kill_process` as the only live caller, and shadow mode; it becomes automatic when Phase 83 wires automatic `block_ip`. It should be closed before shadow mode is lifted for any tenant.
2. **"Undone" is not proof of an undo (CR-02).** A failed or refused compensation is recorded and shown as Undone, and the circuit breaker treats it as a clean undo.

Both fixes are small and local (bind `execute` to the decided row, evaluate all steps or restrict to single-step, scope playbook selection, gate `rolled_back` on all-SUCCESS). Recommended: close these two with a gap plan (`/gsd-plan-phase 81 --gaps`), and fix WR-03 (shadow master parsing), WR-01 (stuck dispatching rows) and WR-02 (level set vs breaker) in the same round because they sit on the same "safe to switch on" path. The remaining warnings can be triaged separately.

The grandfathered automatic writers (threat-hunt fan-out, kill-chain pre-staging, agent auto-update push, agent_logic_service, swarm/SOAR) are a documented, user-approved scope choice (D-21, A-81-XDR-GRANDFATHERED) but are outside both the gate and the stop switch; the user should confirm that is acceptable for the "every automatic action" wording.

No overrides applied. No deferrals: Phase 83 covers swarm/SOAR fencing and automatic block wiring, but not these two defects, which exist in code Phase 81 owns.

---

_Verified: 2026-10-26T14:50:00Z_
_Verifier: Claude (gsd-verifier)_
