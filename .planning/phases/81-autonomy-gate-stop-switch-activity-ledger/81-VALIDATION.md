---
phase: "81"
slug: "autonomy-gate-stop-switch-activity-ledger"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-25"
---

# Phase 81 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `81-RESEARCH.md` § Validation Architecture, amended by `81-CONTEXT.md` D-21..D-24. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`). Frontend: vitest 5.0.0 + @testing-library/react (jsdom). Rust: `cargo test` (folded todo only) |
| **Config file** | `pytest.ini` (root), `backend/pyproject.toml`, `backend/tests/conftest.py` (throwaway `omni_test_<pid>` DB); `vite.config.ts` `test:` block |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/<file> -q -p no:cacheprovider` and `npx vitest run src/__tests__/<file>` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` |
| **Estimated runtime** | quick: seconds per file; full backend ~11 min (real-app probe modules spawn child processes) |

**Verified 2026-10-25 by research:** `pytest tests/test_distributed_lock.py tests/test_scheduler_lock.py` 9 passed in 0.4 s; `npx vitest run src/__tests__/catalogueAccess.test.ts` 44 passed in 2.9 s; `cargo test --offline --test integration` 21 passed (needs `PATH=$HOME/.cargo/bin:$PATH`). Last full-backend baseline (Phase 77): 4048 passed / 47 skipped.

---

## Sampling Rate

- **After every task commit:** the new or changed test file plus any exact-list test it touches.
- **After every plan wave:** `npx vitest run src/__tests__` and `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_*.py backend/tests/test_rbac_defaults.py backend/tests/test_custom_role_mfa.py backend/tests/test_admin_mfa_required.py backend/tests/test_catalogue_manifest.py backend/tests/test_tenant_feature_switches.py backend/tests/test_remediation_guards.py backend/tests/test_autonomous_remediation_loop.py backend/tests/test_ueba_remediation_trigger.py -q -p no:cacheprovider`
- **Before `/gsd-verify-work`:** full suite green, including `npm run build` and the slow parity modules (`test_catalogue_route_parity.py`, `test_audit_parity.py`, `test_route_auth_baseline.py`).
- **Max feedback latency:** ~60 seconds per task (function-level files).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 81-12-T1, 81-12-T2 | 81-12 | 3 | GATE-01 | — | Migration 024 writes an explicit level for every tenant (idempotent); Platform tenant stored Off (D-24b); new tenants default Undoable-auto | real-Mongo | `pytest backend/tests/test_autonomous_ops_migration.py` (12) | ✅ | ✅ green |
| 81-01-T1, 81-11-T2 | 81-01, 81-11 | 1, 2 | GATE-02 | — | Unticked tenant = Off, refused and nothing recorded (D-23); unreadable settings = Suggest; literal tick membership; Platform tenant always refused | unit | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_gate_order.py` (10 + 21) | ✅ | ✅ green |
| 81-11-T2, 81-08-T3, 81-06-T1 | 81-11, 81-08, 81-06 | 2, 4, 3 | GATE-03 | — | Exhaustive decision-table order (6,480 combinations vs an independent oracle); only the gate writes stamped autonomous instructions (AST structural test) | unit + structural | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_structural.py` (10 + 21) | ✅ | ✅ green |
| 81-01-T2, 81-05-T3, 81-08-T2 | 81-01, 81-05, 81-08 | 1, 3, 4 | GATE-04 | — | Registry classes pinned; only an explicit `gate_class` step key raises; every ACTION_MAP key registered; undo targets exist; every command capability-mapped | unit | `pytest backend/tests/test_autonomous_ops_registry.py backend/tests/test_agent_capabilities.py` (6 + 27) | ✅ | ✅ green |
| 81-03-T3, 81-06-T2, 81-08-T2, 81-08-T3 | 81-03, 81-06, 81-08 | 1, 3, 4 | GATE-05 | — | Legacy `run_cycle`/`generate_plan`/`execute_plan` symbols absent; no LLM imports on the autonomous path; only registry-listed stamped instructions with no `script`; confidence bypass removed; XDR selector/fallback only suggest (D-21) | unit + structural | `pytest backend/tests/test_autonomous_ops_structural.py backend/tests/test_autonomous_remediation_loop.py backend/tests/test_autonomous_ops_xdr_fence.py` (21 + 16 + 20) | ✅ | ✅ green |
| 81-05-T1..T3, 81-04-T2, 81-09-T2, 81-10-T1 | 81-05, 81-04, 81-09, 81-10 | 3, 4, 5 | GATE-06 | — | Platform and tenant stop: decisions refused; queued stamped instructions withheld at both agent poll handlers, the unmounted handler and the response-task poll (D-21); undo delivered; approve refused; clear authority per D-11; no restart | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_stop.py backend/tests/test_agent_instruction_poll_tenant_scoping.py` (32 + 7) | ✅ | ✅ green |
| 81-01-T1, 81-01-T3, 81-08-T2 | 81-01, 81-08 | 1, 4 | GATE-07 | — | Intent written before dispatch (fault injection refuses dispatch); audit mirror per transition; `audit_ledger.verify` valid; retention never touches decision records | real-Mongo | `pytest backend/tests/test_autonomous_ops_ledger.py` (26) | ✅ | ✅ green |
| 81-11-T1, 81-11-T2, 81-09-T2 | 81-11, 81-09 | 2, 4 | GATE-08 | — | Built-in never-touch entries cannot be removed; block of platform IP / management subnet refused at every level; host cap = 1 | unit | `pytest backend/tests/test_autonomous_ops_protected.py backend/tests/test_autonomous_ops_gate_order.py` (21 + 21) | ✅ | ✅ green |
| 81-01-T1, 81-11-T2, 81-09-T2 | 81-01, 81-11, 81-09 | 1, 2, 4 | GATE-09 | — | Env master and tenant flag each force shadow; shadow dispatches nothing; lifting shadow is Super Admin only | unit + real-app probe | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_endpoints_writes.py` (10 + 17) | ✅ | ✅ green |
| 81-04-T1, 81-04-T2, 81-08-T2 | 81-04, 81-08 | 3, 4 | GATE-10 | — | Two and five concurrent approves dispatch once; expired approval refused; expiry keeps running during a stop | real-Mongo | `pytest backend/tests/test_autonomous_ops_approvals.py backend/tests/test_autonomous_ops_reconciler.py` (29 + 22) | ✅ | ✅ green |
| 81-03-T2, 81-04-T3 | 81-03, 81-04 | 1, 3 | GATE-11 | — | Two-tenant isolation of settings, ledger, queue and list; tenant ContextVar reset after each sweep iteration; lock renewal; `is_duplicate_task` tenant filter | real-Mongo | `pytest backend/tests/test_autonomous_ops_isolation.py backend/tests/test_distributed_lock.py backend/tests/test_response_orchestrator_tenant.py` (7 + 10 + 4) | ✅ | ✅ green |
| 81-03-T1 | 81-03 | 1 | GATE-12 | — | Cadence constants pinned (30 s poll / 5 min offline); the offline notification names only the agents flipped this pass (D-24d) | real-Mongo | `pytest backend/tests/test_monitor_agent_status.py` (6) | ✅ | ✅ green |
| 81-02-T1, 81-02-T2, 81-09-T1, 81-09-T2 | 81-02, 81-09 | 1, 4 | GATE-13 | — | Permission matrix over the real app (viewer, analyst, security_analyst, incident_responder, tenant_admin, platform_support, platform_billing, super_admin; API key vs session; level above cap 403; platform routes owner-only); approve tier is admin-tier MFA | real-app probe | `pytest backend/tests/test_autonomous_ops_endpoints.py backend/tests/test_autonomous_ops_endpoints_writes.py backend/tests/test_autonomous_ops_permissions.py backend/tests/test_catalogue_slice_autonomous_ops.py` (11 + 17 + 41 + 4) | ✅ | ✅ green |
| 81-04-T2, 81-11-T2 | 81-04, 81-11 | 2, 3 | GATE-14 | — | 3 bad automatic outcomes within 24 h trip to Suggest once, previous level recorded, no auto re-arm; rate limit trips at 20/h; shadow rows excluded | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_breaker.py backend/tests/test_autonomous_ops_gate_order.py` (15 + 21) | ✅ | ✅ green |
| 81-07-T1, 81-07-T2, 81-09-T1, 81-10-T2 | 81-07, 81-09, 81-10 | 2, 4, 5 | ACTV-01 | — | Six state buckets, display fields (what/why/target/result), pagination, tenant selector gate; Stop/Resume + status readout (D-22) | backend + component | `pytest backend/tests/test_autonomous_ops_endpoints.py` ; `npx vitest run src/__tests__/AutonomousOpsActivity.test.tsx src/__tests__/AutonomousOpsStatusCard*.test.tsx` | ✅ | ✅ green |
| 81-07-T2 | 81-07 | 2 | ACTV-03 | — | Shadow rows labelled as a simulation (client also forces the simulation prefix) | component | `npx vitest run src/__tests__/AutonomousOpsActivity.test.tsx` (34) | ✅ | ✅ green |
| 81-10-T3 | 81-10 | 5 | ACTV-08 | — | Banned terms fail both gates; negative controls; Windows Autopilot screen and `.planning/**` out of scope | pytest + vitest | `pytest backend/tests/test_autonomous_ops_copy.py` (19) ; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ✅ | ✅ green |
| 81-10-T1 | 81-10 | 5 | D-15 | — | Stop banner shown only to users who can view the screen, with who/when/why; cannot be dismissed | component | `npx vitest run src/__tests__/AutonomousOpsStopBanner.test.tsx` | ✅ | ✅ green |
| 81-10-T2, 81-09-T2 | 81-10, 81-09 | 4, 5 | D-25 | — | Super Admin Stop all / Resume all organizations controls render only for `control:platform_autonomous_ops`; resume needs a typed reason | component + real-app probe | `npx vitest run src/__tests__/AutonomousOpsStatusCard.test.tsx src/__tests__/AutonomousOpsStatusCardStates.test.tsx` ; `pytest backend/tests/test_autonomous_ops_endpoints_writes.py` | ✅ | ✅ green |
| 81-09-T1 | 81-09 | 4 | D-25 | — | Platform-scope stop returns `by = "Platform administrator"` to tenant viewers and the real name to platform staff | real-app probe | `pytest backend/tests/test_autonomous_ops_endpoints.py` (11) | ✅ | ✅ green |
| 81-03-T3 | 81-03 | 1 | Folded todo | — | Rust integration suite green; todo moved to completed | cargo | `cd agent-install/omni-agent-rs && PATH=$HOME/.cargo/bin:$PATH cargo test --offline --test integration` (21) | ✅ | ✅ green |
| 81-13-T1, 81-13-T2 | 81-13 | 5 | GATE-03 / GATE-08 (gap 1, decide time) | — | Every playbook step and compensation step is IP-checked with its own params and class-checked (main auto/approve, compensation undo_only); a protected IP in the first, middle, last or rollback step refuses the whole action; the row records the full steps/rollback plan | real-Mongo | `pytest backend/tests/test_autonomous_ops_dispatch_binding.py` (43) | ✅ | ✅ green |
| 81-14-T1, 81-14-T2 | 81-14 | 5 | GATE-07 / GATE-11 / GATE-14 (WR-01, WR-02) | — | A sent/delivered row that never reports fails `no_result` after AUTONOMOUS_OPS_NO_RESULT_MIN (CAS-guarded); setting Undoable-auto by hand clears a tripped breaker in the same update and records `level_restored` | real-Mongo | `pytest backend/tests/test_autonomous_ops_reconciler.py backend/tests/test_autonomous_ops_breaker.py` (30 + 21) | ✅ | ✅ green |
| 81-15-T1, 81-15-T2 | 81-15 | 6 | GATE-03 / GATE-08 / GATE-10 (gap 1, dispatch time) | — | `gate.execute`/`execute_response_task` refuse unregistered commands, foreign agents, undecided command/params and never-touch targets at dispatch (`dispatch_check.bind`); an altered second step is refused | real-Mongo | `pytest backend/tests/test_autonomous_ops_dispatch_binding.py backend/tests/test_autonomous_ops_ledger.py backend/tests/test_autonomous_ops_stop.py` | ✅ | ✅ green |
| 81-16-T1, 81-16-T2 | 81-16 | 6 | GATE-07 / GATE-08 / GATE-11 / GATE-14 / ACTV-01 (gap 1 aggravator, gap 2) | — | Playbook selection is tenant-scoped (vendored + the finding's own tenant); `rolled_back` only when every compensation step returned SUCCESS, else `failed`/`rollback_incomplete` + escalation alert; breaker evaluated after remediation outcomes | real-Mongo | `pytest backend/tests/test_autonomous_ops_remediation_truth.py` (20) | ✅ | ✅ green |
| 81-17-T1..T3 | 81-17 | 7 | GATE-09 / GATE-03 (WR-03, scan robustness) | — | Shadow master off only for 0/false/no/off; remediation reads it live through the gate; the stamp scan survives an unparsable tracked file (fails if one is on the autonomous path) | unit + real-Mongo + structural | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_structural.py` (28 + 26) | ✅ | ✅ green |
| 81-18-T1, 81-18-T2 | 81-18 | 8 | GATE-08 / GATE-10 / ACTV-01 (gap 1, approval time) | — | Approve re-checks every recorded step and compensation step against the current never-touch list (fail closed); a multi-step row returns `no_undo` | real-Mongo | `pytest backend/tests/test_autonomous_ops_dispatch_binding.py backend/tests/test_autonomous_ops_approvals.py` (43 + 29) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/autonomy_support.py` — fake ledger and permissive-settings fixtures reused by the three legacy remediation test files
- [x] `backend/tests/test_autonomous_ops_{registry,gate,ledger,stop,protected,breaker,isolation,structural,endpoints,migration,copy,xdr_fence}.py`, `backend/tests/test_catalogue_slice_autonomous_ops.py`, `backend/tests/test_monitor_agent_status.py`, `backend/tests/test_response_orchestrator_tenant.py`
- [x] `src/__tests__/AutonomousOpsActivity.test.tsx`, `src/__tests__/AutonomousOpsStopBanner.test.tsx`, `src/__tests__/autonomousOpsCopy.test.ts`
- [x] `shared/autonomous-ops-banned-terms.json`
- [x] Updated existing tests: `test_rbac_defaults.py`, `test_custom_role_mfa.py`, `test_admin_mfa_required.py`, `test_catalogue_manifest.py`, `test_closure_delivery.py`, `test_role_visibility.py`, `src/__tests__/catalogueAccess.test.ts` (view counts 203/189 → 204/190), `test_remediation_guards.py`, `test_autonomous_remediation_loop.py`, `test_ueba_remediation_trigger.py`
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 024 applied on the live server | GATE-01 | Runs at backend restart, which is the user's step | Restart the backend; confirm every tenant has a stored level and `platform-admin` is Off |
| Platform stop holds back a queued instruction on a real agent poll without a restart | GATE-06 | Needs a live agent | Queue a stamped test instruction in shadow-off test tenant, press stop, confirm the next real poll does not deliver it |
| Agent status cadence on the live fleet | GATE-12 | Live timing | Stop an agent; confirm it shows Offline within ~5 minutes and the notification names it |
| Security Analyst / Incident Responder MFA enrolment prompt | GATE-13 / D-07 | Live sign-in flow | Sign in as each role; confirm the MFA enrolment prompt |
| UI publish: screen, Stop/Resume, banner | ACTV-01 / D-15 / D-22 | UI publish is the user's step | Open Autonomous Ops as an approver; press Stop; confirm the app-wide banner; Resume with a reason |
| Shadow stays on at first deploy; env master value | GATE-09 | Env value is a secret-file setting the user owns | Confirm `AUTONOMOUS_REMEDIATION_DRY_RUN` is not set to false, and every tenant's shadow flag is on |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-10-26 (all 21 rows green: 444 backend tests across the mapped modules, 0 skipped; 613 vitest; cargo integration 21)

## Validation Audit 2026-10-26

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

## Validation Audit 2026-10-26

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Gap-round rows added | 6 |
