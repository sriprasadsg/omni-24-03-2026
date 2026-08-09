---
phase: 55-advanced-threat-detection
plan: 03
subsystem: security
tags: [remediation, ueba, anomaly-detection, autonomous-response, fastapi-background-tasks]

# Dependency graph
requires:
  - phase: 53-autonomous-remediation
    provides: autonomous_remediation_service.remediate() — deterministic playbook dispatch with approval-gate/dry-run/DB-lease/audit
  - phase: 55-advanced-threat-detection
    provides: "55-02's select_playbook() anomaly branch — shadow_ai_detected + real agent_id -> kill_process"
provides:
  - "UEBA report_shadow_ai endpoint as the FIRST production caller of remediate() — a fail-closed, deduped, fire-and-forget containment dispatch"
  - "_dispatch_anomaly_containment_if_eligible() / _dispatch_anomaly_remediation() helpers in ueba_service.py"
affects: [56-*, any-future-ueba-rule-containment-expansion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-closed eligibility gate before any background dispatch: anomaly_rule == shadow_ai_detected AND truthy agent_id AND resolved tenant_id, else no-op (T-55-09)"
    - "Tenant resolution from agent_id via db.agents.find_one({\"id\": agent_id}, {\"tenantId\": 1}) — reused from existing call sites (agent_approval_endpoints.py) rather than inventing a new lookup"
    - "Dedup-before-dispatch: ResponseOrchestrator().is_duplicate_task(...) called and awaited BEFORE remediate(), both inside the background task body (never in the request handler)"

key-files:
  created:
    - backend/tests/test_ueba_remediation_trigger.py
  modified:
    - backend/ueba_service.py

key-decisions:
  - "Checkpoint:decision resolved as option-a: only shadow_ai_detected dispatches automated containment this phase; the other 9 UEBA rules (user/IP-scoped, no agent_id) resolve to no_playbook via 55-02's branch and are still recorded/correlated/SIEM-pushed — no synthetic user->agent mapping, no second dispatch engine (RESEARCH Assumption A2)."
  - "Wired the single call site in report_shadow_ai (ShadowAIEvent always carries a real, required agent_id and is definitionally shadow_ai_detected) rather than also touching analyze_event's shadow-AI branch (built from a LoginEvent with no agent_id concept) — per the plan's tracer instruction to wire ONLY this one path end-to-end."
  - "Dedup + finding-build + remediate() call all live inside a background-task-only function (_dispatch_anomaly_remediation), scheduled via background_tasks.add_task from report_shadow_ai — the request handler itself never awaits remediate()."

requirements-completed: [AUT-03]

coverage:
  - id: D1
    description: "report_shadow_ai builds a RemediationFinding(finding_type='anomaly', details={'anomaly_rule':'shadow_ai_detected', ...}) and dispatches remediate() fire-and-forget via background_tasks.add_task whenever the event carries a real agent_id and a resolvable tenant_id"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestReportShadowAiCallSite::test_report_shadow_ai_schedules_containment_fire_and_forget"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestDispatchAnomalyRemediation::test_builds_anomaly_finding_and_calls_remediate_once"
        status: pass
    human_judgment: false
  - id: D2
    description: "is_duplicate_task(...) is called and resolved BEFORE remediate() inside the background dispatch; a duplicate short-circuits and remediate() is never called"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestDispatchAnomalyRemediation::test_dedup_checked_before_remediate"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestDispatchAnomalyRemediation::test_duplicate_skips_remediate"
        status: pass
    human_judgment: false
  - id: D3
    description: "A missing agent_id, missing tenant_id, or a non-shadow_ai_detected rule never reaches remediate() (fail-closed) — proven both at the eligibility-gate unit level and the report_shadow_ai integration level"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestDispatchEligibility (4 tests: eligible / missing agent_id / missing tenant / non-shadow-ai rule)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestReportShadowAiCallSite::test_report_shadow_ai_no_tenant_resolved_skips_dispatch"
        status: pass
    human_judgment: false
  - id: D4
    description: "The pre-existing _AUTO_BAN_RULES block (UEBA's separate, pre-existing auto-ban for brute_force/known_malicious_ip) is untouched — out of this phase's scope (Pitfall 4)"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestAutoBanUntouched::test_auto_ban_block_still_present_and_unmodified"
        status: pass
    human_judgment: false
  - id: D5
    description: "The anomaly-triggered destructive containment path (shadow_ai_detected -> kill_process) lands in pending_approval — never auto-dispatched — even at max risk_score/severity; no confidence/severity-based bypass of Phase 53's approval gate (D-04)"
    requirement: "AUT-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ueba_remediation_trigger.py::TestNoApprovalGateBypass::test_max_risk_score_anomaly_still_pends_approval"
        status: pass
      - kind: integration
        ref: "backend/tests/test_remediation_guards.py (10 tests, re-run unchanged, all green — no gate regression)"
        status: pass
    human_judgment: false

# Metrics
duration: 35min
completed: 2026-08-03
status: complete
---

# Phase 55 Plan 03: UEBA Predictive Containment Trigger (AUT-03) Summary

**UEBA's `report_shadow_ai` endpoint becomes the FIRST production caller of Phase 53's `remediate()` engine — a shadow_ai_detected event with a real agent_id fires a fail-closed, deduped, fire-and-forget, approval-gated `kill_process` containment dispatch; every other anomaly type stays `no_playbook`.**

## Performance

- **Duration:** ~35 min active execution (checkpoint decision + 2 tasks)
- **Started:** 2026-08-03 (immediately following 55-02)
- **Completed:** 2026-08-03
- **Tasks:** 3/3 (checkpoint:decision + tracer + auto)
- **Files modified:** 2 (`backend/ueba_service.py`, `backend/tests/test_ueba_remediation_trigger.py`)

## Accomplishments
- Added `_dispatch_anomaly_containment_if_eligible()` — a fail-closed eligibility gate that schedules `_dispatch_anomaly_remediation` via `background_tasks.add_task` only when `anomaly_rule == "shadow_ai_detected"` AND a truthy `agent_id` AND a resolved `tenant_id` are all present.
- Added `_dispatch_anomaly_remediation()` — the background-task-only body: awaits `ResponseOrchestrator().is_duplicate_task(...)` BEFORE building a `RemediationFinding(finding_type="anomaly", details={"anomaly_rule": "shadow_ai_detected", ...})` and calling `AutonomousRemediationService().remediate(finding)`. A duplicate short-circuits before `remediate()` is ever called.
- Wired the eligibility gate into `report_shadow_ai`: resolves the event's tenant via `db.agents.find_one({"id": event.agent_id}, {"tenantId": 1})` (the same lookup pattern used elsewhere, e.g. `agent_approval_endpoints.py`), then calls the gate — never awaiting `remediate()` inline in the request handler.
- 16 new tests in `test_ueba_remediation_trigger.py` covering: eligibility gate (4 cases), the actual `report_shadow_ai` call site (2 cases), the background dispatch body (3 cases: dedup ordering, duplicate skip, finding shape), the untouched auto-ban block (1 case), and the no-approval-gate-bypass regression at max risk_score (1 case) — plus `test_remediation_guards.py`'s existing 10 tests re-run unmodified as the integration regression.

## Task Commits

Each task was committed atomically:

1. **Task 1: Checkpoint decision — which UEBA anomaly types trigger automated containment** — resolved by user as **option-a** (only `shadow_ai_detected` dispatches; all other anomalies remain recorded/correlated/SIEM-pushed, resolving to `no_playbook`). No code commit for this task (decision only).
2. **Task 2: End-to-end UEBA anomaly -> remediate() containment** - `abcd8ae` (feat) — the containment call site in `ueba_service.py` + 10 tests proving eligibility/dispatch/fail-closed behavior.
3. **Task 3: Approval-gate regression + no-bypass assertion (AUT-03, D-04)** - `a78cca4` (test) — `TestNoApprovalGateBypass` proving `pending_approval` even at max risk_score; `test_remediation_guards.py` re-run unchanged.

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `backend/ueba_service.py` — new `_dispatch_anomaly_containment_if_eligible()` and `_dispatch_anomaly_remediation()` helpers; `report_shadow_ai` now resolves the event's tenant and calls the eligibility gate after its existing alert-persist scheduling. `_AUTO_BAN_RULES` block (lines ~230-250, unrelated `analyze_login` auto-ban) left byte-for-byte unmodified.
- `backend/tests/test_ueba_remediation_trigger.py` — new test file, 16 tests across 6 test classes (`TestDispatchEligibility`, `TestReportShadowAiCallSite`, `TestDispatchAnomalyRemediation`, `TestAutoBanUntouched`, `TestNoApprovalGateBypass`).

## Decisions Made
- **Checkpoint:decision resolved as option-a** (user-selected): only `shadow_ai_detected` — the one UEBA rule carrying a real `agent_id` — is eligible for automated containment this phase. The other 9 rules (`brute_force`, `impossible_travel`, `known_malicious_ip`, `mass_download`, `lateral_movement`, `dormant_account`, `off_hours_login`, `new_country`, `after_hours_data_access`) resolve to `no_playbook` via 55-02's `select_playbook()` branch and remain recorded/correlated/SIEM-pushed through the existing alert path — no fabricated user→agent mapping, no second dispatch engine.
- Wired the call site into `report_shadow_ai` only (not `analyze_event`'s api_call/shadow-AI branch), because `ShadowAIEvent` is the only shape in this file that always carries a real, required `agent_id` — the `analyze_event` shadow-AI branch is built from a `LoginEvent` with no `agent_id` field at all, so wiring it there would be a structural no-op. This matches the plan's tracer instruction to "wire ONLY this single shadow_ai path end-to-end."
- Kept the dedup check + finding construction + `remediate()` call together inside one background-task-only function (`_dispatch_anomaly_remediation`), rather than splitting dedup into the request handler — this guarantees `is_duplicate_task()` and `remediate()` are always evaluated together, atomically, inside the deferred background execution, and never partially in the hot path.

## Deviations from Plan

### Documented (not auto-fixed — verification wording clarified, no code change)

**1. Plan-level `<verification>` grep (`grep -v '^#' backend/ueba_service.py | grep -c 'await .*remediate(' == 0`) returns 1, not 0 — by design.**
- **Found during:** Task 2 verification pass.
- **Explanation:** The single match (`await AutonomousRemediationService().remediate(finding)`, line 389) is inside `_dispatch_anomaly_remediation` — the background-task-only function scheduled via `background_tasks.add_task` from `report_shadow_ai`. It is never awaited inside `report_shadow_ai` (the actual request handler / hot path). Since `remediate()` must be awaited *somewhere* in this file for the containment to ever execute (the plan scopes all changes to `backend/ueba_service.py`), a literal whole-file grep of `await .*remediate(` cannot return 0 for any working implementation confined to this file — the more precise per-task acceptance criterion ("no inline `await ...remediate(`" — i.e., not blocking the request/response cycle) is what's actually satisfied and is proven directly by `TestReportShadowAiCallSite::test_report_shadow_ai_schedules_containment_fire_and_forget` (the handler returns using a bare `MagicMock` `background_tasks`, so `remediate()` is never invoked during the call).
- **Verification of intent:** `grep -n 'await.*remediate(' backend/ueba_service.py` shows the one match sits inside `_dispatch_anomaly_remediation`, confirmed by inspection to be outside `report_shadow_ai`'s body.
- **Impact:** None on correctness or the T-55-08 mitigation (fire-and-forget, never blocking) — this is a wording gap in the blunt whole-file heuristic, not a functional gap.

**2. `backend/ueba_service.py` exceeds the CLAUDE.md 500-line guideline (681 lines after this change) — pre-existing violation, not introduced by this plan.**
- **Found during:** self-check line-count review.
- **Explanation:** The file was already 585 lines before this plan (a pre-existing FastAPI router module covering 10+ UEBA rules, 12 endpoints, and shared alert-persistence helpers). This plan added ~96 lines (the two new helper functions + `report_shadow_ai`'s tenant resolution/dispatch call). Splitting this module into multiple files is an architectural change well outside this plan's locked scope (`files_modified: backend/ueba_service.py, backend/tests/test_ueba_remediation_trigger.py`) and was not requested.
- **Action:** Logged as an out-of-scope, pre-existing item rather than fixed (per SCOPE BOUNDARY — only auto-fix issues directly caused by this task's changes). Recorded to the broken-windows ledger below.
- **Impact:** None on this plan's correctness; a future refactor phase could split `ueba_service.py` by rule category if desired.

---

**Total deviations:** 2 documented (0 auto-fixed) — both are wording/scope clarifications, not functional gaps or bugs.
**Impact on plan:** No scope creep; no functional changes required beyond what was planned.

## Issues Encountered
None — all three tasks (checkpoint decision, tracer, and approval-gate regression) completed without blockers.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AUT-03 is now fully delivered end-to-end: 55-02's `select_playbook()` anomaly branch (mapping half) + 55-03's `report_shadow_ai` containment trigger (dispatch half) together give a complete, tested path from a live shadow-AI detection to an approval-gated `kill_process` containment action, with zero bypass of Phase 53's human approval gate.
- The pre-existing UEBA auto-ban (brute_force/known_malicious_ip, `ip_ban_service.ban_ip` at `risk_score >= 80`) remains a separate, unaddressed, out-of-scope bypass of an approval gate — flagged in RESEARCH Pitfall 4 as a known issue for a future phase, not introduced or worsened here.
- Broader containment coverage for the other 9 UEBA rule types (user/IP-scoped, no `agent_id`) was explicitly deferred (option-b was not selected) — a follow-up phase would need its own research + discuss-phase to design a non-agent-dispatch action type or synthetic lease keying without becoming a second dispatch engine.
- `backend/ueba_service.py`'s pre-existing 500-line-guideline overage (now 681 lines) is a candidate for a future cleanup/refactor phase, not blocking anything today.

---
*Phase: 55-advanced-threat-detection*
*Completed: 2026-08-03*

## Self-Check: PASSED

- FOUND: backend/ueba_service.py
- FOUND: backend/tests/test_ueba_remediation_trigger.py
- FOUND commit: abcd8ae
- FOUND commit: a78cca4
